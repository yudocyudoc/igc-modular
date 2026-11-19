"""Q75 milk decision: authentic offline D/M parent-scoped own-feedback policies.

Runs IGC vendored CT02 Ledger/ATMS bridge + original D fixed policy and M2
own_policy on a G1 *representation-coverage* objection. Produces no P90,
no simulated Q75 policy effect, no new OMC/provider/R2 calls. Buffalo is
pending a compatible authenticated Q75 parent and a live authorized invoke.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .common import ArenaError, digest, read_json, write_json
from .coffee_adapters import d as d_adapter, m as m_adapter
from . import coffee_feedback as feedback, decision_atms, runtime
from . import coffee_q75_milk_cycle as q75

SCHEMA = "arena.coffee.q75-own-feedback-real-DM-no-solver/1"
REPORT_SCHEMA = "arena.coffee.q75-own-feedback-pre-B-report/1"
# Time is a replay-only logical sequence; never a timestamp of physical work.
T0 = "2026-11-19T05:00:00.000001+00:00"
T1 = "2026-11-19T05:00:00.000002+00:00"
T2 = "2026-11-19T05:00:00.000003+00:00"
T3 = "2026-11-19T05:00:00.000004+00:00"
ATMS_TIME = "2026-11-19T05:01:00."


def require(ok, code):
    if not ok:
        raise ArenaError("COFFEE_Q75_DM_" + code)


def _tick(i):
    return ATMS_TIME + f"{i:06d}Z"


def gate(report):
    """Only a cryptographically verified PR49 Q75 case is eligible.

    Do NOT pass raw provider results or an altered policy/dossier as a parent.
    This validates the output of q75.prepare from verified public sources; the
    caller must have authenticated the 8 archives before invoking this gate.
    """
    require(isinstance(report, dict) and report.get("schema") == q75.SCHEMA
            and report.get("Q75_case_day_sha256") == q75.ARCHIVED_Q75_CASE_SHA,
            "NOT_AUTHENTIC_Q75_PREPARED_CASE")
    baseline = report["frozen_reference_decision"]
    require(baseline["current_operational_choice"] == q75.DECISION_BASE
            and baseline["status"].startswith("RECORDED_RETROSPECTIVELY")
            and baseline["milk_delta_p90_sec_positive_is_worse"] == -3.837,
            "HYDRA_BASELINE_TAMPERED")
    common = report["Q75_public_case"]
    phys = common["physical"]
    require(common["alternatives"] == list(q75.POLICIES)
            and common["private_sequence_not_reconstructed"] is True
            and phys["resource_units_from_hydra"] == {
                "barista":2, "prep_space":2, "espresso_group":3,
                "steam_wand":1, "pickup_pass":1}
            and phys["resource_ids_from_dossier"]["steam_wand"] == ["W01"]
            and phys["task_stage_resource_requirements_from_hydra"]["milk"]
            == ["barista","steam_wand"]
            and "first executable task" in phys["policy_selection_semantics"]
            ["PRIORITIZE_MILK_READY"],
            "PHYSICAL_STAGE_OR_MILK_FALLBACK_LOST")
    packets=report["producer_effective_inputs_NOT_SENT"]
    require(set(packets)=={"D","M","B"}, "MISSING_METHOD_PACKET")
    for arm, packet in packets.items():
        require(packet["status"] == "PREPARED_NOT_DELIVERED_TO_PRODUCER"
                and packet["producer_response"] == "NOT_EXECUTED"
                and packet["operation_known"] == common
                and packet["question"] == q75.FIXED_QUESTION
                and packet["input_sha256"] == digest({k:v for k,v in
                    packet.items() if k != "input_sha256"}),
                "PACKET_TAMPER_OR_FALSE_RESPONSE_" + arm)
    require(report["current_decision"]["scientific_incremental_value"] ==
            "UNDETERMINED_NOT_ZERO", "PREMATURE_INCREMENTAL_CONCLUSION")
    require(report["new_execution_budget"]["new_cloudflare_posts_executed"] == 0
            and report["new_execution_budget"]["new_omc_executed"] == 0
            and report["new_execution_budget"]["new_private_R2_gets_executed"] == 0,
            "PREEXISTING_NEW_PRIVATE_SPEND_UNTRACKED")
    return common, packets


def parents():
    """Original six native structural parents each; no authored substitute."""
    verification = runtime.verify(include_history=False)
    require(verification["unchanged"] and verification["files"] > 0,
            "VENDORED_ORIGINAL_CHANGED")
    d = d_adapter.original()
    structures=[d.topology(n, loss) for n in (1,2,3)
                for loss in (False,True)]
    for candidate in structures:
        d.lint_structure(candidate)
        require(set(candidate["primitives"])=={"SOURCE","STOCK","RATE",
                  "SINK","CUMULATIVE_OBSERVATION"},"UNEXPECTED_D_PRIMITIVE")
    c, _, _ = m_adapter.original()
    cfg, classes, _ = c.load_registry(m_adapter.REGISTRY)
    graphs=c.enumerate_graphs(cfg,classes)
    permitted={"accepted-source","bounded-queue","delivery-counter",
               "first-order-report-filter"}
    require(len(structures)==len(graphs)==6 and cfg["new_classes"]==[]
            and set(classes)>=permitted, "UNEXPECTED_PARENT_SET")
    m_parents=[]
    for _, graph in graphs:
        c.check_graph(graph,cfg,classes)
        active={node["class_id"] for node in graph["instances"]}
        require(active.issubset(permitted),"M_UNDECLARED_MILK_OR_RESOURCE_MOLECULE")
        m_parents.append(graph)
    return {"D":structures,"M":m_parents}, classes


def _coverage_diagnostic(arm, parent, source_hash):
    require(arm in ("D","M"),"UNKNOWN_METHOD")
    # These are observed ABSENCES in the native graph, not observations of
    # the real shop or of candidate policies. They are G1 representation facts.
    return {
        "schema":"arena.coffee.q75-G1-policy-coverage-diagnostic/1",
        "arm":arm,"condition":"MILK", "source_hash":source_hash,
        "parent_hash":digest(parent),"evidence":"G1",
        "own_evidence_only":True,"no_future_truth":True,"observations":[],
        "diagnosis_from":"EVALUATOR_READ_OF_THIS_NATIVE_PARENT_ONLY",
        "question":"FCFS_READY_ASSUMED vs PRIORITIZE_MILK_READY in Q75",
        "operator_resource_and_W01_allocation_not_encoded":True,
        "milk_ready_dispatch_policy_not_encoded":True,
        "observable_limitation":"NO_PER_ORDER_P90_OR_POLICY_DIFFERENCE_IN_THIS_PARENT",
        "physical_case_has_one_wand":"W01",
        "is_not_predicted_zero_effect":True,
        "G1_not_fit_or_assessment_against_Hydra_delta":True,
    }


def _run_arm(bridge, arm, candidates, classes, common_hash, path):
    """Run real CT02 record→recover→policy→persist→as-of reread per parent."""
    db=Path(path)
    context=bridge.make_context(experiment="Coffee",world="Q75",
             round_id="R0",arm=arm,condition="MILK",source_hash=common_hash)
    result=[]
    for index,parent in enumerate(candidates):
        parent_hash=digest(parent)
        diagnostic=_coverage_diagnostic(arm,parent,common_hash)
        stored=bridge.record_feedback(db,context,parent_hash=parent_hash,
                                      diagnostic=diagnostic,recorded_at=T0)
        retrieved=bridge.recover_feedback(db,context,parent_hash=parent_hash,
                                          as_known_at=T1)
        require(retrieved["diagnostic"]==diagnostic
                and retrieved["diagnostic_hash"]==stored["diagnostic_hash"]
                and retrieved["parent_hash"]==parent_hash,
                "FEEDBACK_NOT_RECOVERED_FOR_OWN_PARENT")
        if arm=="D":
            own=bridge.d_fixed_decision(db,context,parent_hash=parent_hash,
                                         as_known_at=T2)
            require(own["status"]=="RATIFIED" and own["model_revision"] is False
                    and own["d2"]=="NOT_APPLICABLE_MISSING_RESET_TRIAL",
                    "D_HISTORIC_FIXED_POLICY_CHANGED")
        else:
            own=bridge.own_m_decision(db,context,parent_graph=parent,
                                      as_known_at=T2,classes=classes)
            require(own["status"]=="ABSTAINED" and
                    own["reason"]=="NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS"
                    and own.get("new_model") is None,
                    "M_OWN_POLICY_CHANGED_WITHOUT_RESIDUALS")
        require(own["parent_hash"]==parent_hash and
                own["feedback_hash"]==stored["diagnostic_hash"] and
                own["retrieved_before_policy"]["projection_hash"]==
                retrieved["retrieval"]["projection_hash"] and
                own["provider_calls"]==own["new_omc"]==0,
                "POLICY_NOT_BOUND_TO_RETRIEVED_FEEDBACK")
        persisted=bridge.persist_disposition(db,context,decision=own,
                                             recorded_at=T3)
        final=bridge.recover_feedback(db,context,parent_hash=parent_hash,
                                      as_known_at=T3)
        require(final["diagnostic"]==diagnostic and
                persisted["method_status"]==own["status"] and
                persisted["case_id"]==retrieved["context"]["case_id"] and
                persisted["status"]=="DISPOSITION_RECORDED_WITH_OWN_FEEDBACK_SUPPORT",
                "PERSISTENCE_OR_POST_DECISION_REPLAY_FAILED")
        result.append({
            "parent_index":index,"parent_sha256":parent_hash,
            "source_sha256":common_hash,
            "G1_diagnostic_sha256":stored["diagnostic_hash"],
            "G1_diagnosis":diagnostic,
            "feedback_ledger_case_id":stored["case_id"],
            "retrieved_at_logical_cut":retrieved["retrieval"],
            "own_method_policy":own["policy"],
            "own_method_disposition":own["status"],
            "own_method_reason":own.get("reason",own.get("d2")),
            "own_policy_feedback_sha256":own["feedback_hash"],
            "policy_generated_new_child":bool(own.get("new_model")),
            "persisted_disposition":persisted,
            "retrievable_after_decision":final["diagnostic_hash"]==stored["diagnostic_hash"],
            "q75_milk_p90_prediction":"NOT_PREDICTED_POLICY_NOT_ENCODABLE_IN_THIS_PARENT",
            "new_provider_calls":0,"new_omc_calls":0,
        })
    require(len(result)==6 and len({v["parent_sha256"] for v in result})==6,
            "MISSING_DISTINCT_AUTHENTIC_PARENTS")
    return result


def _cross_arm_atms(common_hash, d_rows, m_rows):
    """A real decision ATMS projection, evaluator-authored support links.

    Important: a coverage limitation cannot logically support a milk benefit.
    What-if removing any method or their shared unsupported causal mapping
    must leave the decision to retain current practice unchanged.
    """
    require(all(r["retrievable_after_decision"] for r in d_rows+m_rows),
            "NO_VALID_METHOD_RECEIPTS")
    j=decision_atms.Journal()
    events=[
        decision_atms.event("assumption","A_BASELINE_NOT_OBSERVED",_tick(1),
                            common_hash,node="ACTUAL_FCFS_NOT_VERIFIED",status="EVIDENCED"),
        decision_atms.event("assumption","A_D_RECEIPTS",_tick(2),
                            digest(d_rows),node="D_SIX_G1_COVERAGE_RECEIPTS",status="EVIDENCED"),
        decision_atms.event("assumption","A_M_RECEIPTS",_tick(3),
                            digest(m_rows),node="M_SIX_G1_COVERAGE_RECEIPTS",status="EVIDENCED"),
        decision_atms.event("assumption","A_SHARED_ABSENCE",_tick(4),
                            common_hash,node="ARCHIVED_PARENTS_HAVE_NO_MILK_DISPATCH",
                            status="BOUNDED"),
        decision_atms.event("justification","J_HOLD",_tick(5),common_hash,
                            conclusion="HOLD_CURRENT_PRACTICE_NO_REAL_COMPARATOR",
                            premises=["ACTUAL_FCFS_NOT_VERIFIED"]),
        decision_atms.event("justification","J_D_COVERAGE",_tick(6),
                            digest(d_rows),conclusion="D_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY",
                            premises=["D_SIX_G1_COVERAGE_RECEIPTS",
                                      "ARCHIVED_PARENTS_HAVE_NO_MILK_DISPATCH"]),
        decision_atms.event("justification","J_M_COVERAGE",_tick(7),
                            digest(m_rows),conclusion="M_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY",
                            premises=["M_SIX_G1_COVERAGE_RECEIPTS",
                                      "ARCHIVED_PARENTS_HAVE_NO_MILK_DISPATCH"]),
    ]
    for evt in events:j.append(evt)
    snap=j.snapshot(as_known_at=_tick(7),valid_at=_tick(7))
    def remove(name, seq):
        return j.what_if(as_known_at=_tick(7),valid_at=_tick(7),
            candidate_events=[decision_atms.event("retract",name,_tick(seq),common_hash,
                                                   target=name.replace("W_REMOVE_","A_") )])
    # Define explicitly which assumption is removed: do not infer names.
    views={}
    for arm,target,tick in (("D","A_D_RECEIPTS",8),
                            ("M","A_M_RECEIPTS",9),
                            ("SHARED","A_SHARED_ABSENCE",10)):
        fork=j.what_if(as_known_at=_tick(7),valid_at=_tick(7),
            candidate_events=[decision_atms.event("retract","W_REMOVE_"+arm,
                      _tick(tick),common_hash,target=target)])
        labels=fork["hypothetical_snapshot"]["labels"]
        require("HOLD_CURRENT_PRACTICE_NO_REAL_COMPARATOR" in labels,
                "UNJUSTIFIED_DECISION_CHANGED_BY_COVERAGE_RETRACTION")
        if arm=="D":
            require("D_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY" not in labels,
                    "D_SUPPORT_SURVIVES_D_WITHDRAWAL")
        if arm=="M":
            require("M_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY" not in labels,
                    "M_SUPPORT_SURVIVES_M_WITHDRAWAL")
        if arm=="SHARED":
            require("D_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY" not in labels
                    and "M_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY" not in labels,
                    "SHARED_CAUSE_NOT_RETRACTED")
        views[arm]={"changed_labels":fork["changed_labels"],
                    "business_hold_remains_supported":True,
                    "hypothetical_only":True}
    require("HOLD_CURRENT_PRACTICE_NO_REAL_COMPARATOR" in snap["labels"]
            and "D_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY" in snap["labels"]
            and "M_CANNOT_SCORE_MILK_IN_ARCHIVED_FAMILY" in snap["labels"],
            "NO_BASELINE_OR_COVERAGE_SUPPORT")
    return {"projection":"arena.decision_atms.Journal",
            "authorship":"EVALUATOR_RULES_WITH_REAL_CT02_METHOD_RECEIPTS",
            "as_known_at_is_logical_replay_only":True,
            "snapshot_sha256":snap["snapshot_sha256"],
            "supported_labels":snap["labels"],
            "what_if_withdrawal":views,
            "independent_evidence_of_real_benefit":False,
            "decision_support_is_not_empirical_truth":True,
            "cross_arm_feedback_delivery_to_Buffalo":False}


def execute(report, out):
    common, packets=gate(report)
    src=digest({"case_sha256":common["case_day_sha256"],
                "question":common["question"],"physical":common["physical"],
                "policies":common["alternatives"]})
    originals, classes=parents()
    out=Path(out)
    require(not out.exists(),"OUTPUT_ALREADY_EXISTS")
    out.mkdir(parents=True)
    bridge=feedback._original_bridge()
    rows={}
    for arm in ("D","M"):
        rows[arm]=_run_arm(bridge,arm,originals[arm],classes,src,
                           out / (arm+"-q75-ledger.sqlite"))
    atms=_cross_arm_atms(src,rows["D"],rows["M"])
    result={
        "schema":SCHEMA,"case":"Q75","question":q75.FIXED_QUESTION,
        "source_case_sha256":common["case_day_sha256"],
        "common_input_sha256":src,
        "input_sha256_by_arm":{arm:packets[arm]["input_sha256"] for arm in ("D","M","B")},
        "input_includes_W01_and_one_steam_wand":True,
        "method_scope":"ORIGINAL_B0_FAMILY_NATIVE_G1_COVERAGE_OBJECTION_ONLY",
        "arm_D":{"original_policy_involved":True,"parent_count":6,
                 "ratified":6,"q75_policy_effect_not_representable":True,
                 "real_parent_feedback_records":rows["D"]},
        "arm_M":{"original_policy_involved":True,"parent_count":6,
                 "abstained":6,"missing_two_late_observations":True,
                 "q75_policy_effect_not_representable":True,
                 "real_parent_feedback_records":rows["M"]},
        "arm_B":{"status":"NOT_EXECUTED_NO_Q75_COMPATIBLE_AUTHENTIC_PARENT",
                 "live_provider_post_required":True,
                 "currentModel_reuse_of_B0_not_justified":True,
                 "q75_policy_effect_not_predicted":True},
        "decision_atms":atms,
        "decision_Hydra_only":q75.DECISION_BASE,
        "decision_after_D_M":"HOLD_UNCHANGED_COVERAGE_ONLY_NO_NEW_VALID_P90",
        "decision_after_D_M_B":"PENDING_AUTHENTIC_B_AND_POLICY_REPRESENTATIONS",
        "incremental_decision_value":"NOT_DEMONSTRATED_NOT_SCORED_ZERO_FOR_THREE_METHODS",
        "not_a_new_scientific_prediction":True,
        "no_future_truth_or_rival_producer_inputs":True,
        "logical_replay_times_not_real_wall_clock":True,
        "budget":{"new_omc":0,"new_cloudflare_post":0,"new_private_R2_get":0,
                  "own_ledger_record_feedback_calls":12,
                  "own_ledger_original_method_policy_calls":12,
                  "own_ledger_persist_disposition_calls":12,
                  "original_native_parent_count":12,
                  "modelica_p90_predictions":0,
                  "future_spend_authorized":False},
    }
    write_json(out / "Q75_DM_OWN_POLICY.json",result,exclusive=True)
    (out / "Q75_DM_OWN_POLICY.md").write_text(markdown(result),encoding="utf-8")
    return result


def markdown(report):
    return "\n".join([
        "# Cafetería Q75 — misma decisión, D/M original con feedback propio auténtico",
        "",
        "**Elección por ahora:** mantener la práctica, leche solo candidata condicional. "
        "FCFS es supuesto en Hydra; el despacho real no está medido.",
        "",
        "**La entrada contiene W01 (1 lanza), 2 baristas, 2 puestos, 3 grupos, "
        "1 pase**, con la prioridad de leche ejecutable y regreso a FCFS.",
        "",
        "## Qué ejecutó esta etapa",
        "",
        "- Gramática D: **6 padres originales**, diagnósticos de representación G1 "
        "registrados y recuperados individualmente en CT02 Ledger/ATMS; "
        "política original `d_fixed_decision`: **6 RATIFIED**. No revisión D2.",
        "- Moléculas M: **6 AST originales**, diagnósticos G1 registrados y "
        "recuperados en CT02 Ledger/ATMS; política original "
        "`own_m_decision`: **6 ABSTAINED** porque no hay residuos medidos a "
        "2 y 4 horas. No se inventaron esos residuos.",
        "- Tras cada respuesta, disposición persistida y feedback aún recuperable "
        "al corte correspondiente, con identidad del padre y del caso Q75.",
        "- ATMS decisional `Journal` auténtico: retiradas hipotéticas de soporte "
        "D, soporte M y premisa de falta de política de leche en los padres. "
        "La cautela operativa sobrevive; retirar premisa común retira ambas "
        "conclusiones de cobertura, no el resultado histórico Hydra.",
        "",
        "## Qué NO se hizo ni se afirma",
        "",
        "- Estas políticas reaccionan a una **objeción G1 de cobertura** "
        "formulada por el evaluador, no a residuos del P90 Q75. Las "
        "enumeraciones originales de D/M no codifican esta prioridad. La "
        "ratificación de D y la abstención de M NO son predicciones de un efecto cero.",
        "- **Buffalo no invocado**: ningún padre nuevo compatible autorizado "
        "para esta pregunta; su B0/R1 de retiros acumulados no se reutiliza.",
        "- **No hay resultado de las tres vías ni mejora decisional demostrada**. "
        "Tampoco hay comparación independiente con operación real.",
        "- **Presupuesto consumido:** 0 POST Cloudflare, 0 OMC, 0 GET R2 privado, "
        "0 mundos; 12 diagnósticos G1 y 12 decisiones D/M originales.",
        "",
        "## Qué falta para cerrar la misma pregunta",
        "",
        "Entregar el caso Q75 a una ruta productora que codifique las dos políticas "
        "y el recurso W01, presupuestar exactamente llamadas Buffalo, modelos "
        "ejecutables y lecturas privadas estrictamente indispensables, y "
        "completar el feedback propio, revisión/ratificación/abstención, "
        "consecuencias y contraste. Si la política no es representable, "
        "registrar cobertura insuficiente, no efecto cero.",
        "",
        "**Regla de parada:** el caso sigue abierto mientras falte una "
        "respuesta auténtica B. No se cambia la pregunta ni se despacha "
        "un nuevo mundo.", "",
    ])


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--pre-dispatch-json",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    result=execute(read_json(args.pre_dispatch_json),args.out)
    print("Q75_DM_ORIGINAL_POLICIES_RETRIEVED",result["arm_D"]["ratified"],
          result["arm_M"]["abstained"],"NEW_POST=0 NEW_OMC=0 PRIVATE_R2=0")
    return result


if __name__=="__main__":
    main()
