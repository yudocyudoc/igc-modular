"""P49: evidence-led PRE-DISPATCH contract for a SINGLE Q75 milk-priority decision.

Authentic public historical sources are verified by PR48's readback module.
This does not execute D/M/B on Q75, provider calls, OpenModelica or R2 reads.
It must never claim that a prepared producer input is an authentic answer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

from .common import ArenaError, digest, read_json, write_json
from .coffee_three_arms_readback_v2 import readback, load_sources
from .coffee_adapters import d as d_adapter, m as m_adapter
from . import decision_atms, runtime
from . import coffee_v2_hydra_physical_b as physical_b

SCHEMA = "arena.coffee.q75-milk-three-arms-pre-dispatch/1"
REPORT_SCHEMA = "arena.coffee.q75-milk-pre-dispatch-report/1"
FIXED_QUESTION = "PRIORITIZE_MILK_READY versus FCFS_READY_ASSUMED on the same Q75 synthetic construction"
DECISION_BASE = "HOLD_CURRENT_PRACTICE_MILK_ONLY_CANDIDATE_FOR_PILOT_AFTER_VALIDATION"
POLICIES = ("FCFS_READY_ASSUMED", "PRIORITIZE_MILK_READY")
ARCHIVED_SOURCE_RUN = 44234407455
ARCHIVED_SOURCE_ZIP_SHA = "sha256:2fa54c8b64927140e918c693886a11c9fb3e69f80d8ec1b2dabdf16be12d2cb5"
ARCHIVED_Q75_CASE_SHA = "sha256:a7c3cae597302f7a46daf136c5b584e6a411a4c13d01319a81fcd0fd467171b9"
EXPECTED_DOSSIER_SHA = "sha256:48559d79c91d03fa2196f449e03ed78ab3c0710680c44849152e5d8dc192f00a"
# These are audit-only logical ticks, NOT observed or claimed real-time clocks.
CLOCK = "2026-11-18T23:50:00."


def require(condition, code):
    if not condition:
        raise ArenaError("COFFEE_Q75_MILK_" + code)


def _sha(value):
    require(type(value) is str and value.startswith("sha256:") and
            len(value) == 71 and all(c in "0123456789abcdef" for c in value[7:]),
            "INVALID_SHA256")
    return value


def _at(tick):
    return CLOCK + f"{tick:06d}Z"


def _exact_hydra_source(z):
    hydra = json.loads(z["hydra"].read("D_Q25_Q75_AGGREGATE.json"))
    require(hydra["schema"] == "arena.coffee.p46.public-eight-scenario-aggregate/1" and
            hydra["scope"] == "SYNTHETIC_VERIFIED_CONSTRUCTION_ONLY_NOT_REAL_CAFE" and
            hydra["scenario_count"] == 8 and
            hydra["execution_and_consumption"]["github_run_id"] == ARCHIVED_SOURCE_RUN and
            hydra["execution_and_consumption"]["github_commit_sha"] ==
            "e2da7eeaadd7c9e361ca38090a3de25a161916f3",
            "HYDRA_ARCHIVED_IDENTITY_MISMATCH")
    require(hydra["results"] and len(hydra["results"]) == 2,
            "HYDRA_LOADS_INCOMPLETE")
    q75 = next((r for r in hydra["results"] if r["load_label"] ==
                "HIGHER_PAID_INPUT_Q75"), None)
    q25 = next((r for r in hydra["results"] if r["load_label"] ==
                "LOWER_PAID_INPUT_Q25"), None)
    require(q75 is not None and q25 is not None and
            q75["paid_orders"] == 46 and q75["synthetic_beverages"] == 53 and
            q75["source_provenance"]["selected_case_day_digest"] == ARCHIVED_Q75_CASE_SHA and
            q75["physical_dossier_sha256"] == EXPECTED_DOSSIER_SHA,
            "HYDRA_Q75_SOURCE_NOT_ACCEPTED")
    arms = {x["policy"]: x for x in q75["arms"]}
    require(len(arms) == 4 and set(POLICIES).issubset(arms),
            "HYDRA_Q75_POLICIES_NOT_COMPLETE")
    base, milk = (arms[x] for x in POLICIES)
    delta = (milk["p90_paid_to_handoff_full_drain_min"]-
             base["p90_paid_to_handoff_full_drain_min"])*60
    require(abs(delta-(-3.837)) < 1e-7 and
            milk["orders_handoff_earlier"] == 5 and
            milk["orders_handoff_later"] == 4 and
            milk["orders_handoff_unchanged"] == 37 and
            milk["handoffs_before_source_cut"] == base["handoffs_before_source_cut"] == 46 and
            milk["rule_changed_assignment_count"] == 4,
            "HYDRA_Q75_PAIRED_VALUES_CHANGED")
    q25_milk = next((x for x in q25["arms"] if x["policy"] == "PRIORITIZE_MILK_READY"), None)
    require(q25_milk is not None and q25_milk["orders_handoff_earlier"] == 0 and
            q25_milk["orders_handoff_later"] == 0 and
            q25_milk["delta_p90_min_positive_is_worse"] == 0,
            "Q25_MILK_ONLY_TIE_CHANGED")
    return hydra, q75, q25, delta


def _check_physics(dossier, q75):
    require(type(dossier) is dict and
            dossier["schema"] == "arena.coffee.p44.hydra-physical-b/1" and
            digest(dossier) == q75["physical_dossier_sha256"],
            "DOSSIER_HASH_OR_VERSION_MISMATCH")
    require(dossier["enabled_group_ids"] == ["G01","G02","G03"] and
            set(dossier["operators"]) == {"B01","B02"} and
            dossier["durations_min"]["espresso_auto_min"]["value"] == 1.5 and
            dossier["dispatch_policy"] == "FCFS_READY_ASSUMED" and
            dossier["milk_precedence"] == "AFTER_GROUP_RELEASE_ASSUMED",
            "DOSSIER_PHYSICAL_ASSUMPTIONS_DRIFT")
    # The effective physical constraints MUST be carried through to every arm.
    # Use the SAME live stage requirements and resource accounting as Hydra;
    # no hand-written default for the number of wands/stations/passes.
    cap = physical_b.capabilities(dossier)
    required = {stage:list(physical_b.STAGE_CLASSES[stage])
                for stage in physical_b.STAGES}
    require(cap["resource_units"] == {
                "barista": len(dossier["operators"]),
                "prep_space": len(dossier["prep_stations"]),
                "espresso_group": len(dossier["enabled_group_ids"]),
                "steam_wand": len(dossier["steam_wands"]),
                "pickup_pass": len(dossier["pickup_passes"])},
            "HYDRA_RESOURCE_CAPABILITY_DRIFT")
    require(physical_b.D_DISPATCH_STAGE.get("PRIORITIZE_MILK_READY") == "milk"
            and required["milk"] == ["barista", "steam_wand"]
            and required["prepare"] == ["barista", "prep_space"]
            and required["load"] == ["barista", "espresso_group"]
            and required["handoff"] == ["barista", "pickup_pass"],
            "HYDRA_STAGE_AND_PRIORITY_CONTRACT_DRIFT")
    return {
        "resource_units_from_hydra": cap["resource_units"],
        "resource_ids_from_dossier": {
            "barista": sorted(dossier["operators"]),
            "prep_space": list(dossier["prep_stations"]),
            "espresso_group": list(dossier["enabled_group_ids"]),
            "steam_wand": list(dossier["steam_wands"]),
            "pickup_pass": list(dossier["pickup_passes"]),
        },
        "task_stage_resource_requirements_from_hydra": required,
        "stage_predecessors_from_hydra":
            dict(physical_b.STAGE_PREDECESSOR),
        "policy_selection_semantics": {
            "source":"arena.coffee_v2_hydra_physical_b._engine / choose / dispatch",
            "ready_order":"stable eligibility FIFO, nonpreemptive manual tasks",
            "task_executable_now":"manual stage requires a simultaneously free "
                "eligible barista and its extra resource, including steam_wand "
                "for milk. No future reservation; blocked tasks are skipped.",
            "FCFS_READY_ASSUMED":"take first executable task in ready queue; "
                "skip earlier tasks that cannot start now",
            "PRIORITIZE_MILK_READY":"take earliest executable milk task; "
                "if no milk task is executable now, take the first "
                "executable task under FCFS, even with W01 occupied",
            "steam_wand_busy":"milk cannot start without available wand AND "
                "barista; an eligible barista may perform another executable "
                "task, never wait idly solely because the wand is occupied",
            "resource_claim":"atomic nonpreemptive reservation at task start; "
                "one W01 cannot serve two milk tasks simultaneously",
            "not_documented_shop_dispatch":"the two policies are synthetic "
                "counterfactual rules, not observed practice",
        },
        "installed_groups": dossier["installed_group_ids"],
        "enabled_groups_assumed": dossier["enabled_group_ids"],
        "operator_ids": sorted(dossier["operators"]),
        "operator_skills_declared_not_measured":
            {k:v["skills"] for k,v in sorted(dossier["operators"].items())},
        "operator_availability_assumed_not_observed":
            {k:v["availability_windows_min"] for k,v in sorted(dossier["operators"].items())},
        "duration_min_assumed_not_calibrated":
            {k:v["value"] for k,v in dossier["durations_min"].items()},
        "group_retained_until_manual_removal": True,
        "milk_precedence": dossier["milk_precedence"],
        "baseline_dispatch_is_assumption_not_observed_policy": True,
        "physical_scope": dossier["scope"],
    }


def _check_b0_prompt(z):
    first = json.loads(z["buffalo_initial"].read("input.json"))
    require(first["schema"] == "arena.coffee-peak.buffalo-public-input/1" and
            first["case_sha256"].startswith("sha256:"),
            "BUFFALO_B0_INPUT_SCHEMA_OR_CASE")
    prompt = first["prompt"]
    require("shared barista/espresso coupling" in prompt and
            "Do not invent measurements" in prompt and
            "The only requested primary output is cumulative picked-up orders" in prompt,
            "BUFFALO_B0_SCOPE_UNVERIFIED")
    return {"old_prompt_digest":digest(prompt),
            "excluded_barista_espresso_coupling":True,
            "old_question":"cumulative picked-up orders in B0",
            "old_parent_compatible_with_new_Q75_policy":"NOT_DEMONSTRATED",
            "requires_new_initial_generation_if_no_compatible_parent":True,
            "historical_B0_authentic_R1_is_not_a_Q75_response":True}


def _native_generator_scope():
    """Invoke original D topology/linter and E1 composer, not a duplicate simulator.

    These operations establish a bounded search scope only. They do not
    simulate the milk question or claim own feedback from the producers.
    """
    verified = runtime.verify(include_history=False)
    require(verified["unchanged"] is True and verified["files"] > 0,
            "UNVERIFIED_VENDORED_METHODS")
    d_src = d_adapter.original()
    structures = [d_src.topology(n,loss) for n in (1,2,3)
                  for loss in (False,True)]
    for shape in structures:
        d_src.lint_structure(shape)
    comp, backend, _ = m_adapter.original()
    cfg, classes, _ = comp.load_registry(m_adapter.REGISTRY)
    graphs = comp.enumerate_graphs(cfg, classes)
    require(len(structures) == 6 and len(graphs) == 6 and
            cfg["new_classes"] == [] and
            set(classes) >= {"accepted-source","bounded-queue",
                             "delivery-counter","first-order-report-filter"},
            "D_M_ORIGINAL_SEARCH_SCOPE_CHANGED")
    return {
        "verified_original_manifest": {
            "igc_commit":verified["igc_commit"],
            "buffalo_commit":verified["buffalo_commit"],
            "unchanged":True},
        "D": {"method":d_src.METHOD,"six_structures_linted":len(structures),
              "stock_counts":[1,2,3],"post_payment_loss_variants":[False,True],
              "q75_policy_execution":"NOT_RUN_NO_Q75_POLICY_ENCODER"},
        "M": {"method":"short-e1-original-typed-graph-enumeration",
              "registry":str(m_adapter.REGISTRY.name),
              "six_real_graphs_enumerated":len(graphs),
              "used_class_ids":sorted({node["class_id"] for _,graph in graphs
                                       for node in graph["instances"]}),
              "q75_policy_execution":"NOT_RUN_NO_Q75_POLICY_ENCODER"},
        "B": {"old_method":"UB-IAD/sd-ai::Engine.generate",
              "new_api_post":"NOT_SENT_REQUIRES_SEPARATE_AUTHORIZATION"}
    }


def _common_process(q75, physics):
    return {
        "question":FIXED_QUESTION,
        "case":"Q75_CONSTRUCTION_SYNTHETIC_ONLY",
        "case_day_sha256":q75["source_provenance"]["selected_case_day_digest"],
        "paid_orders":q75["paid_orders"],
        "beverages":q75["synthetic_beverages"],
        "units":{"order":"paid ticket", "beverage":"individual drink",
                 "time":"minutes"},
        "horizon_min":q75["source_horizon_min"],
        "source_profile":"INDIVIDUAL_Q75_PAYMENTS_NOT_PUBLIC_IN_AGGREGATE",
        "private_sequence_not_reconstructed":True,
        "physical":physics,
        "alternatives":list(POLICIES),
        "exact_policy_selection_semantics":physics["policy_selection_semantics"],
        "decision_outcome":"P90_PAID_TO_HANDOFF_FULL_DRAIN_MIN_PER_ORDER",
        "harm_checks":["HANDOFFS_BEFORE_SOURCE_CUT",
                       "ADVANCED_DELAYED_UNCHANGED_ORDER_COUNTS"],
        "known_workflow":["paid", "prepare_off_group", "load",
                          "extract_auto", "remove", "milk_finish", "handoff"],
        "evidence_kinds":{"paid_events":"SYNTHETIC_CONSTRUCTION_PRIVATE",
                          "group_ids":"INSTALLED_AND_ENABLED_AS_SCENARIO",
                          "staff_windows":"ASSUMED_NOT_OBSERVED_FULL_SHIFT",
                          "full_extraction_duration":"ASSUMED_NOT_CALIBRATED",
                          "baseline_policy":"ASSUMED_NOT_MEASURED_LOCAL"},
        "no_Hydra_outcomes_in_producer_prompt": True,
        "not_a_new_observation_or_private_data_release":True,
    }


def _effective_packets(common, scope, b0):
    """Prepare full case but NOT claim delivery to the original producers."""
    items={}
    for arm in ("D","M","B"):
        payload={
            "case":common["case"],"question":common["question"],
            "operation_known":common,
            "request":{"first_result":"BASE_AND_MILK_COMPARISON_IF_REPRESENTABLE",
                       "explanation":"MECHANISM_AND_DISPLACED_MANUAL_TASK",
                       "observation":"DECLARE_UNIT_WINDOW_AND_COVERAGE",
                       "own_feedback":"REVISE_RATIFY_ABSTAIN_ON_RETRIEVED_DIAGNOSIS"},
            "never_share_rival_results_or_Hydra_delta":True,
            "status":"PREPARED_NOT_DELIVERED_TO_PRODUCER",
            "producer_response":"NOT_EXECUTED",
            "method":"gramática D" if arm=="D" else
                     "moléculas M" if arm=="M" else "Buffalo",
        }
        if arm == "D":
            payload["adapter_provenance"]={
                "original":scope["D"]["method"],
                "planned_role":"ASSESS_POLICY_COVERAGE_AND_OWN_RULE",
                "no_invented_p90_for_stock_chain":True,
                "new_effective_route_needs_eligibility_check":True}
        elif arm == "M":
            payload["adapter_provenance"]={
                "original":scope["M"]["method"],
                "original_registry":scope["M"]["registry"],
                "planned_role":"ASSESS_COMPOSITION_AND_OWN_POLICY",
                "missing_two_late_residuals_m2_if_same_feedback_rule":True,
                "no_fake_resource_via_signal_filter":True}
        else:
            payload["adapter_provenance"]={
                "original":scope["B"]["old_method"],
                "earlier_parent_compatibility":b0["old_parent_compatible_with_new_Q75_policy"],
                "new_model_if_needed":"INITIAL_GENERATION_NOT_A_REVIEW",
                "new_currentModel_revision":"SEPARATE_AUTHORIZED_CALL_AFTER_OWN_DIAGNOSIS",
                "old_prompt_excluded_required_mechanism":True}
        payload["input_sha256"]=digest({k:v for k,v in payload.items() if k!="input_sha256"})
        items[arm]=payload
    return items


def _historical_baseline(q75, delta):
    return {
        "status":"RECORDED_RETROSPECTIVELY_AFTER_PR46_PUBLICATION_NOT_BLIND",
        "question":FIXED_QUESTION,
        "scenario":"Q75_90S_SYNTHETIC_UNCALIBRATED",
        "policy_comparator":"FCFS_READY_ASSUMED_NOT_MEASURED_LOCAL",
        "milk_delta_p90_sec_positive_is_worse":round(delta,9),
        "milk_p90_better_orders":5,"milk_p90_worse_orders":4,
        "milk_unchanged_orders":37,"handoffs_at_source_cut_both":46,
        "current_operational_choice": DECISION_BASE,
        "real_pilot_decision":"NOT_AUTHORIZED_OR_SUPPORTED_BY_CURRENT_EVIDENCE",
        "criterion_if_E1_30s_loses_or_ties":"WITHDRAW_DUAL_DURATION_STABILITY_CLAIM",
        "criterion_if_E1_30s_better":"RETAIN_CONDITIONAL_CANDIDATE_NOT_REAL_BENEFIT",
        "practical_effect_threshold":"NOT_SUPPLIED_BY_SHOP_OWNER",
        "no_extrapolation_to_real_shop":True,
    }


def _atms_public_hydra_proof(source_sha):
    """REAL Journal API with archived Q75 digest; no invented D/M/B support.

    The existence of logical nodes does not turn an assumed duration into
    observed data or a public artifact into new source information.
    """
    source_sha=_sha(source_sha)
    journal=decision_atms.Journal()
    events=[
        decision_atms.event("assumption","A_Q75_ARCHIVED_RESULT",_at(1),source_sha,
                            node="Q75_ARCHIVED_MILK_90S_P90_RESULT",status="EVIDENCED"),
        decision_atms.event("assumption","A_Q75_90S_SCENARIO",_at(2),source_sha,
                            node="Q75_90S_ASSUMED_EXTRACTION",status="ASSUMED"),
        decision_atms.event("assumption","A_NO_VERIFIED_REAL_BASELINE",_at(3),source_sha,
                            node="REAL_BASELINE_RULE_NOT_MEASURED",status="EVIDENCED"),
        decision_atms.event("justification","J_90S_CONDITIONAL_ADVANTAGE",_at(4),source_sha,
                            conclusion="Q75_MILK_ADVANTAGE_APPLIES_AT_90S_ONLY",
                            premises=["Q75_ARCHIVED_MILK_90S_P90_RESULT",
                                      "Q75_90S_ASSUMED_EXTRACTION"]),
        decision_atms.event("justification","J_HOLD_NO_REAL_POLICY_EVIDENCE",_at(5),source_sha,
                            conclusion="HOLD_REAL_OPERATION_PENDING_BASELINE_OBSERVATION",
                            premises=["REAL_BASELINE_RULE_NOT_MEASURED"]),
    ]
    for e in events:journal.append(e)
    before=journal.snapshot(as_known_at=_at(5),valid_at=_at(5))
    what_if=journal.what_if(as_known_at=_at(5),valid_at=_at(5),candidate_events=[
        decision_atms.event("retract","W_REMOVE_90S_EXTRAPOLATION",_at(6),source_sha,
                            target="A_Q75_90S_SCENARIO")])
    after=what_if["hypothetical_snapshot"]
    require("Q75_MILK_ADVANTAGE_APPLIES_AT_90S_ONLY" in before["labels"] and
            "Q75_MILK_ADVANTAGE_APPLIES_AT_90S_ONLY" not in after["labels"] and
            "Q75_ARCHIVED_MILK_90S_P90_RESULT" in after["labels"] and
            "HOLD_REAL_OPERATION_PENDING_BASELINE_OBSERVATION" in after["labels"] and
            what_if["canonical_journal_sha256_unchanged"] == digest(journal.events),
            "ATMS_HISTORICAL_RETRACTION_INVARIANT_FAILED")
    return {"status":"PUBLIC_HYDRA_CONDITIONAL_ATMS_PROOF_NOT_DMB_FEEDBACK",
            "original_ATMS_module":"arena.decision_atms.Journal",
            "historical_source_sha256":source_sha,
            "provenance":"Q75_ARCHIVED_PUBLIC_DIGEST_PLUS_EVALUATOR_JUSTIFICATIONS",
            "logical_time_not_observed_wall_clock":True,
            "public_hydra_support_before":before["labels"],
            "what_if_remove_90s":what_if["changed_labels"],
            "historical_result_survives_after":True,
            "three_method_diag_recovered_and_consumed":False,
            "not_a_new_scientific_approval":True}


def _budget(common, packets):
    require(all(p["status"]=="PREPARED_NOT_DELIVERED_TO_PRODUCER"
                for p in packets.values()),"CANNOT_BUDGET_AGAINST_FAKE_RUNS")
    return {
        "status":"ESTIMATE_ONLY_NOT_AUTHORIZATION_AND_NOT_A_DISPATCH",
        "public_artifact_read_count":8,
        "new_cloudflare_posts_executed":0,
        "new_omc_executed":0,
        "new_private_R2_gets_executed":0,
        "new_worlds":0,
        "private_q75_sequence_required_for_exact_per_order_policy_effects":True,
        "public_totals_are_insufficient_to_reconstruct_private_arrival_sequence":True,
        "private_R2_read_count_future":"VERIFY_VIEW_SELECTION_AND_REQUEST_SEPARATE_AUTHORIZATION",
        "Buffalo_new_generation_if_no_compatible_parent":{"min":0,"max":1,
                    "condition":"CHECK_R1_COMPATIBILITY_FIRST; B0 PROMPT FORBADE COUPLING"},
        "Buffalo_new_review_after_own_feedback":{"min":0,"max":1,
                    "condition":"ONLY_WITH_COMPATIBLE_CURRENT_MODEL_AND_RECEIPT"},
        "D_candidate_count_upper":6,"M_candidate_count_upper":6,
        "D_M_new_omc_on_policy_baseline_and_milk_if_eligible_upper":24,
        "B_new_omc_on_two_policies_if_executable_upper":2,
        "revised_child_omc_per_policy_conditional_upper":"UP_TO_2_PER_CHANGED_CHILD_ONLY_IF_NEW_SOURCE_AUTHORIZED",
        "no_numeric_OMC_budget_authorized":True,
        "any_new_calls_require_a_new_explicit_budget_and_user_approval":True,
        "no_data_access_scheduled_by_this_workflow":True,
    }


def _decision_status():
    return {"Hydra_only":DECISION_BASE,
            "Hydra_plus_new_D_M_B":"PENDING_NO_AUTHENTIC_NEW_Q75_RESPONSES",
            "D":"NOT_EXECUTED_FOR_NEW_Q75_DECISION",
            "M":"NOT_EXECUTED_FOR_NEW_Q75_DECISION",
            "B":"NOT_EXECUTED_FOR_NEW_Q75_DECISION",
            "the_archived_B0_dispositions_are_not_Q75_replies":True,
            "ATMS_cross_arm_support_consolidation":"PENDING_METHOD_RECEIPTS",
            "prospective_contrast":"NOT_AVAILABLE",
            "scientific_closure":"NOT_ALLOWED_AT_PRE_DISPATCH_STAGE",
            "scientific_incremental_value":"UNDETERMINED_NOT_ZERO",
            "actual_shop_service_improvement":"NOT_DEMONSTRATED"}


def prepare(zip_dir, dossier_path):
    # source verification BEFORE evaluating producer or policy claims
    report = readback(zip_dir)
    require(report["schema"] == "arena.coffee.three-methods-v2.retrospective-readback/1" and
            report["mode"] == "RETROSPECTIVE_PUBLIC_ARTIFACT_READBACK_NOT_BLIND" and
            report["source_registry"]["hydra"]["zip_sha256"] == ARCHIVED_SOURCE_ZIP_SHA and
            report["source_registry"]["hydra"]["run_id"] == ARCHIVED_SOURCE_RUN,
            "PR48_SOURCE_READBACK_NOT_AUTHENTIC")
    archives = load_sources(zip_dir)  # identical pinned eight ZIPs
    raw, q75, q25, delta = _exact_hydra_source(archives)
    physics = _check_physics(read_json(dossier_path), q75)
    b0 = _check_b0_prompt(archives)
    scope = _native_generator_scope()
    common = _common_process(q75,physics)
    packets = _effective_packets(common,scope,b0)
    baseline = _historical_baseline(q75,delta)
    atms = _atms_public_hydra_proof(report["source_registry"]["hydra"]["zip_sha256"])
    output={"schema":SCHEMA,
            "purpose":"ONE_EXISTING_MILK_VS_ASSUMED_FCFS_Q75_DECISION_NO_FIFTH_POLICY",
            "historical_source_provenance":report["source_registry"],
            "Q75_case_day_sha256":ARCHIVED_Q75_CASE_SHA,
            "Q75_public_case":common,
            "frozen_reference_decision":baseline,
            "original_generator_scope":scope,
            "historical_buffalo_B0_prompt_scope":b0,
            "producer_effective_inputs_NOT_SENT":packets,
            "ATMS_public_reference_what_if":atms,
            "new_execution_budget":_budget(common,packets),
            "current_decision":_decision_status(),
            "do_not_expose_private_order_rows":True,
            "source_data_not_real_cafe":True,
            "not_a_new_scientific_lock":True}
    return output


def render_markdown(report):
    require(report["schema"]==SCHEMA,"INVALID_REPORT_SCHEMA")
    baseline=report["frozen_reference_decision"]
    budget=report["new_execution_budget"]
    scope=report["original_generator_scope"]
    return "\n".join([
        "# Q75 · Decisión única: prioridad de leche contra FCFS supuesto",
        "",
        "**Respuesta vigente:** conservar la operación actual; la prioridad de leche queda",
        "como candidata condicional, no como mejora demostrada en barra.",
        "",
        "**Alcance:** pre-despacho auténtico con ocho ZIP públicos. Los tres brazos",
        "**NO han recibido todavía esta nueva pregunta**. Esta entrega no demuestra",
        "aportación incremental ni mejora real; tampoco puede declarar aporte cero.",
        "",
        "## Referencia Hydra sola, registrada retrospectivamente",
        "",
        f"- Caso Q75: {report['Q75_public_case']['paid_orders']} pedidos pagados, "
        f"{report['Q75_public_case']['beverages']} bebidas sintéticas.",
        f"- P90 leche − FCFS supuesto: {baseline['milk_delta_p90_sec_positive_is_worse']:.3f} s.",
        f"- Pedidos adelantados / demorados / iguales: 5 / 4 / 37; entregados al corte: 46 en ambas políticas.",
        "- Extracción automática de 90 s asumida y no calibrada; FCFS NO describe",
        "  necesariamente la práctica observada del local.",
        "- Si E1 a 30 s empata o invierte, pierde apoyo la extrapolación a ambas",
        "  duraciones. Si mejora, la candidatura sigue siendo condicional.",
        "- El resultado histórico ya era público: este registro no crea ceguera retrospectiva.",
        "",
        "## Tres rutas originales verificadas, pero no convocadas aún con Q75",
        "",
        f"- **D**: {scope['D']['six_structures_linted']} estructuras originales, "
        "  sin política de leche en esas ecuaciones. No equivale a predicción cero.",
        f"- **M**: {scope['M']['six_real_graphs_enumerated']} grafos originales bajo el "
        "  registro de cafetería; sin disputa entre tareas manuales en el grafo.",
        "- **Buffalo**: el prompt B0 anterior prohibía inventar acoplamiento",
        "  barista/espresso. Reusar su padre para Q75 requiere demostrar compatibilidad.",
        "- Los tres paquetes Q75 incluyen el proceso conocido, mecanismos y límites,",
        "  pero permanecen **PREPARED_NOT_DELIVERED_TO_PRODUCER**.",
        "",
        "## ATMS: prueba real de lógica, no circuito nuevo D/M/B",
        "",
        "- Se ejecutó el Journal real sobre una justificación declarada por el evaluador",
        "  anclada al agregado público Q75. Retirar hipotéticamente el supuesto de 90 s",
        "  quita su aplicación condicionada y conserva el resultado histórico.",
        "- No hubo diagnósticos Q75 consumidos por métodos, ni nueva persistencia",
        "  de disposiciones D/M/B. Esto sigue pendiente de la ronda autorizada.",
        "",
        "## Presupuesto y autorización: pendientes",
        "",
        "- Esta entrega: 8 ZIP públicos leídos, **0 POST Cloudflare, 0 OMC,",
        "  0 GET R2 privados, 0 mundos nuevos**.",
        "- Paso siguiente: determinar compatibilidad efectiva y qué rutas representan",
        "  la prioridad; obtener secuencia Q75 autorizada antes de calcular efectos",
        "  por pedido; presupuestar sólo los modelos/llamadas indispensables.",
        "- Cuenta de planificación no autorizada: hasta 1 generación Buffalo si no",
        "  hay padre compatible + hasta 1 revisión; hasta 24 ejecuciones OMC de",
        "  D/M y 2 de Buffalo para dos políticas **solo si son representables**.",
        "  Los hijos revisados y lecturas privadas se presupuestan aparte.",
        "- No se transfieren permisos de PR47/E1 a este ciclo.",
        "",
        "## Regla de cierre",
        "",
        "No se puede afirmar que Arena aportó valor cero o positivo mientras",
        "falte la respuesta auténtica de cualquiera de los tres productores.",
        "Una vez ejecutadas y revisadas, el dictamen comparará Hydra sola y",
        "Hydra + D/M/B, usando ATMS y evidencia apta para ese contraste.",
        "",
        "**PR de preparación; no es la ejecución científica completa.**",
        ""
    ])


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--public-zips",type=Path,required=True)
    parser.add_argument("--dossier",type=Path,default=Path(
        "experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json"))
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    require(not args.out.exists(),"REFUSE_OVERWRITE")
    report=prepare(args.public_zips,args.dossier)
    args.out.mkdir(parents=True)
    write_json(args.out/"Q75_MILK_PRE_DISPATCH.json",report,exclusive=True)
    (args.out/"Q75_MILK_PRE_DISPATCH.md").write_text(render_markdown(report),encoding="utf-8")
    print(json.dumps({"schema":REPORT_SCHEMA,"status":"PUBLIC_SOURCES_REAL_PRODUCERS_NOT_DISPATCHED",
                      "hydra_run":ARCHIVED_SOURCE_RUN,"d_original_enumerated":6,
                      "m_original_enumerated":6,"new_cloudflare_posts":0,"new_omc":0,
                      "new_private_r2_gets":0,"scientific_closure":False},sort_keys=True))

if __name__=="__main__":
    main()
