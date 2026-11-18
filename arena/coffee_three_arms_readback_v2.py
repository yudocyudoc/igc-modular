"""P48 / V2 PR1: authentic public artifact readback of D, M, Buffalo and Hydra.

This is a RETROSPECTIVE, source-pinned examination, not a new model run,
blind comparison, empirical physical validation, or ATMS rule execution.
No R2, provider calls or OpenModelica; only archived GitHub artifact ZIPs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

SCHEMA = "arena.coffee.three-methods-v2.retrospective-readback/1"
REPO = "yudocyudoc/igc-modular"
CASE_B0 = "sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f"
# SHA256 of the GitHub Actions ZIP bytes, not of JSON-canonical content.
# All IDs/run SHAs are frozen from the public GitHub Actions API.
SOURCES = {
    "g2": (43550618982, 14094919865, "69638301626dd482556f58eaead298a5c620d9bf", "1f10695e4dcd27ad4f29552c3c954b4ce26efb131594b0b18076f52a26701925"),
    "feedback": (43561168032, 14100770369, "227e7f20137d99d5da122ffb8a0ee93b069548c7", "51b56dc28e5c229a280adf3f38062744992a61dc21dff48973e18f48105d10d8"),
    "buffalo_initial": (43537333254, 14090920829, "399eddbc0d674e8b2370f908a75ba73e694153c3", "70f9e9f846a33cd470b00dbaf0bf189b0b6c7a029b68bd84485f7c6bbe748265"),
    "buffalo_r1": (43565759793, 14102098459, "402cfe945839ca29718c385def6aab9e846ef117", "686db7b34ca177e055a0c4d6fbbef771368baaa412491dad2ed07c1a20a59b65"),
    "buffalo_score": (43686325127, 14150642285, "00ed50a9311a0864b323492935802cbfb86e5101", "1e06057a1d31476ca3df75a2558db8aec54ffe27652aa66db334aa780bfe81b2"),
    "m_p08": (43702148041, 14157186844, "68e874821d74bb26c492625e9061716a40333dda", "4391d036017140ec65931f0f6a1aba221c5fba81fbb1bc2e6107b8f406ae42a8"),
    "d_p08": (43705604955, 14157799232, "072cd372bb020cef9cee48f70b5403fe992dbe9f", "9fcab78e7a04afeca9fc9b4543f05df76ca58c7b2044194be540471c11120799"),
    "hydra": (44234407455, 14396368697, "e2da7eeaadd7c9e361ca38090a3de25a161916f3", "2fa54c8b64927140e918c693886a11c9fb3e69f80d8ec1b2dabdf16be12d2cb5"),
}
# Invariant: labels are not inferred from a user-supplied ZIP filename.
METHODS = {"g2": "D_M_ORIGINAL_B0", "feedback": "D_M_B_FEEDBACK_B0",
           "buffalo_initial": "BUFFALO_ORIGINAL_B0", "buffalo_r1": "BUFFALO_REVIEW_R1_B0",
           "buffalo_score": "D_M_BUFFALO_SEALED_B0", "m_p08": "MOLECULES_M_P08",
           "d_p08": "GRAMMAR_D_P08", "hydra": "HYDRA_Q75_90S"}


class SourceError(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise SourceError("COFFEE_THREE_ARMS_V2_" + code)


def sha_bytes(blob):
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def load_sources(zip_dir):
    """Verify all raw GitHub ZIPs *before* parsing one model or conclusion."""
    root = Path(zip_dir)
    archives = {}
    for name, (run, artifact, commit, expected) in SOURCES.items():
        src = root / ("artifact-" + str(artifact) + ".zip")
        need(src.is_file(), "MISSING_PUBLIC_ARTIFACT_" + name)
        contents = src.read_bytes()
        need(sha_bytes(contents) == "sha256:" + expected,
             "PUBLIC_ZIP_DIGEST_MISMATCH_" + name)
        try:
            archives[name] = zipfile.ZipFile(src)
            need(archives[name].testzip() is None, "DAMAGED_ZIP_" + name)
        except (zipfile.BadZipFile, OSError) as e:
            raise SourceError("COFFEE_THREE_ARMS_V2_BAD_ZIP_" + name) from e
    return archives


def member(archives, name, path):
    try:
        return archives[name].read(path)
    except KeyError as e:
        raise SourceError("COFFEE_THREE_ARMS_V2_MISSING_MEMBER_" + name + ":" + path) from e


def doc(archives, name, path):
    try:
        value = json.loads(member(archives, name, path))
    except (ValueError, UnicodeError) as e:
        raise SourceError("COFFEE_THREE_ARMS_V2_BAD_JSON_" + name + ":" + path) from e
    need(type(value) is dict, "JSON_OBJECT_REQUIRED_" + name)
    return value


def public_provenance():
    return {key: {"repository": REPO, "run_id": run, "artifact_id": artifact,
                  "commit_sha": commit, "zip_sha256": "sha256:" + hash_,
                  "github_run_url": f"https://github.com/{REPO}/actions/runs/{run}",
                  "archive_kind": METHODS[key], "read_only_public": True}
            for key, (run, artifact, commit, hash_) in SOURCES.items()}


def validate_comparable(a, b, *, numeric=False):
    """Numerical differences require *same* case, time profile, material,
    horizon/cut, intervention semantics and observable; labels alone never do.
    """
    fields = ("case", "input_profile", "material_unit", "horizon_min",
              "cut_min", "intervention", "observable", "observable_unit")
    missing = [x for x in fields if x not in a or x not in b]
    need(not missing, "COMPARABILITY_FIELDS_MISSING_" + ",".join(missing))
    differences = [x for x in fields if a[x] != b[x]]
    if numeric:
        need(not differences, "NUMERIC_COMPARISON_FORBIDDEN_" + ",".join(differences))
    return {"numeric_comparable": not differences,
            "mismatches": differences,
            "allowed": "NUMERIC_COMPARISON" if not differences else "MECHANISM_ONLY",
            "not_an_empirical_confirmation": True}


def validate_r1_parent(initial_bytes, review, revised_bytes):
    parent_hash = sha_bytes(initial_bytes)
    revised_hash = sha_bytes(revised_bytes)
    need(review["parent_native_file_sha256"] == parent_hash,
         "BUFFALO_REVIEW_PARENT_IDENTITY_MISMATCH")
    need(review["revised_native_file_sha256"] == revised_hash,
         "BUFFALO_REVIEW_CHILD_IDENTITY_MISMATCH")
    need(review["original_model_revised_by_original_Engine_generate"] is True,
         "BUFFALO_REVISION_NOT_ORIGINAL_METHOD")
    return {"parent_sha256": parent_hash, "child_sha256": revised_hash}


def readback(zip_dir):
    z = load_sources(zip_dir)
    g2 = doc(z, "g2", "result.json")
    g2d = doc(z, "g2", "input/native/D/manifest.json")
    g2m = doc(z, "g2", "input/native/M/manifest.json")
    fb = doc(z, "feedback", "summary.json")
    packet = doc(z, "feedback", "B-own-review-packet.json")
    initial_bytes = member(z, "buffalo_initial", "provider/native-engine-result.json")
    revised_bytes = member(z, "buffalo_r1", "provider/native-engine-result.json")
    initial = json.loads(initial_bytes)["model"]
    revised = json.loads(revised_bytes)["model"]
    review = doc(z, "buffalo_r1", "review-analysis.json")
    review_final = doc(z, "buffalo_r1", "final.json")
    score = doc(z, "buffalo_score", "result.json")
    mp = doc(z, "m_p08", "result.json")
    mp_manifest = doc(z, "m_p08", "manifest.json")
    dp = doc(z, "d_p08", "result.json")
    dp_manifest = doc(z, "d_p08", "manifest.json")
    hydra = doc(z, "hydra", "D_Q25_Q75_AGGREGATE.json")
    # Fail closed: source-specific schemas, versions, receipt statuses, arms.
    need(g2["schema"] == "arena.coffee-peak.dm-g2-physical-batch/1" and
         g2["run_id"] == SOURCES["g2"][0] and
         g2["head_sha"] == SOURCES["g2"][2] and
         g2["case_sha256"] == CASE_B0 and
         g2["simulations_authenticated"] == 12 and
         len(g2["results"]) == 12, "G2_PROVENANCE_OR_COUNT_INVALID")
    need(g2d["method"] == "generic-conservative-chain-search/0.1" and
         g2d["candidate_count"] == 6 and
         g2m["method"] == "short-e1-original-typed-graph-enumeration" and
         g2m["candidate_count"] == 6 and
         g2d["public_case_sha256"] == CASE_B0 == g2m["public_case_sha256"],
         "D_M_ORIGINAL_METHOD_OR_CASE_INVALID")
    need(fb["schema"] == "arena.coffee-peak.own-ledger-atms-consumption/2" and
         fb["case_sha256"] == CASE_B0 and
         fb["status"] == "OWN_FEEDBACK_RETRIEVED_DM_POLICIES_INVOKED_B_PACKET_NOT_SENT" and
         set(fb["arms"]) == {"D", "M", "B"}, "FEEDBACK_PROVENANCE_INVALID")
    # This is an inventory of what the archived coffee-specific M registry
    # actually selected. It is NOT a search of other possible libraries or
    # alternative molecules for a newly posed H1/H2/H3 question.
    m_B0_classes = sorted({instance["class_id"]
        for candidate in g2m["candidates"]
        for instance in candidate["full_ast"]["instances"]})
    need(m_B0_classes == ["accepted-source", "bounded-queue",
                           "delivery-counter", "first-order-report-filter"] and
         g2m["candidate_count"] == 6,
         "M_B0_RESTRICTED_CLASS_INVENTORY_DRIFT")
    by_g2 = {(x["arm"], x["candidate_id"]): x for x in g2["results"]}
    need(len(by_g2) == 12, "G2_DUPLICATE_CANDIDATE")
    original_rows = []
    for arm, manifest in (("D", g2d), ("M", g2m)):
        expected = {x["id"]: x for x in manifest["candidates"]}
        need(len(expected) == 6 and
             set(expected) == {key[1] for key in by_g2 if key[0] == arm},
             "ORIGINAL_CANDIDATES_NOT_MATCHING_" + arm)
        feedback = fb["arms"][arm]
        need(feedback["candidate_count"] == 6 and
             feedback["own_original_policy_invoked"] is True and
             feedback["as_of_replay_verified_after_all_dispositions"] is True,
             "ORIGINAL_POLICY_NOT_VERIFIED_" + arm)
        dispositions = {x["candidate_id"]: x for x in feedback["candidates"]}
        need(len(dispositions) == 6 and set(dispositions) == set(expected),
             "FEEDBACK_CANDIDATE_SET_MISMATCH_" + arm)
        for index, (cid, candidate) in enumerate(expected.items()):
            g = by_g2[(arm, cid)]
            f = dispositions[cid]
            parent = (candidate["structure_hash"] if arm == "D" else
                      candidate["full_ast_sha256"])
            need(g["model_sha256"] == f["native_model_sha256"] and
                 f["parent_hash"] == parent and
                 f["csv_sha256"] == g["csv_sha256"] and
                 f["retrieved_before_policy"]["projection_hash"] ==
                    f["final_sqlite_as_of_replay"]["projection_hash"] and
                 f["original_policy_status"] ==
                    ("RATIFIED" if arm == "D" else "ABSTAINED") and
                 f["retrieved_before_policy"]["item_id"] and
                 f["final_sqlite_as_of_replay"]["status"] ==
                    "ASOF_REPLAYED_FROM_CLOSED_FINAL_SQLITE",
                 "ORIGINAL_EVIDENCE_MISMATCH_" + arm)
            # Verify all twelve actual solver CSV bytes, not merely a pair
            # of mutually agreeing digest declarations in G2 and feedback.
            csv_path = f"results/{arm}/{arm.lower()}{index:02d}_res.csv"
            need(sha_bytes(member(z, "g2", csv_path)) == g["csv_sha256"],
                 "ORIGINAL_SOLVER_CSV_BYTES_MISMATCH_" + arm)
            # Compare a single G2 Modelica native's bytes with its recorded
            # SHA for D; M uses the shared modelica file + exact full AST.
            if arm == "D":
                native_path = "input/native/D/" + candidate["modelica_file"]
                need(sha_bytes(member(z,"g2",native_path)) == g["model_sha256"],
                     "D_NATIVE_BYTES_MISMATCH")
            else:
                need("class_id" in candidate["full_ast"]["instances"][0] and
                     candidate["modelica_class"].split(".")[-1] in member(
                         z, "g2", "input/native/M/native.mo").decode(),
                     "M_AST_OR_NATIVE_CLASS_MISSING")
            original_rows.append({
                "method": "gramática D" if arm == "D" else "moléculas M",
                "arm": arm, "version": manifest["method"], "case": "B0",
                "candidate_id": cid, "parent_sha256": parent,
                "native_sha256": g["model_sha256"],
                "g2_csv_sha256": g["csv_sha256"],
                "g2_status": g["status"],
                "policy_status": f["original_policy_status"],
                "policy_reason": f.get("original_policy_reason"),
                "policy_id": f["original_policy"],
                "feedback_as_known_at": f["retrieved_before_policy"]["as_known_at"],
                "feedback_projection_hash": f["retrieved_before_policy"]["projection_hash"],
                "model_revision": f["new_model"],
                "claims_by": "original_method_policy_for_disposition; evaluator_for_H1_H2_H3",
            })
    need(packet["status"] == "OWN_G1_FEEDBACK_RETRIEVED_PACKET_PREPARED_NOT_SENT" and
         packet["parent_native_file_sha256"] == sha_bytes(initial_bytes) and
         fb["arms"]["B"]["parent_hash"] == sha_bytes(initial_bytes) and
         fb["arms"]["B"]["own_original_policy_invoked"] is False,
         "BUFFALO_OWN_FEEDBACK_PACKET_INVALID")
    bproof = validate_r1_parent(initial_bytes, review, revised_bytes)
    need(review_final["status"] == "REVIEW_NATIVE_RETURNED_NOT_G2" and
         review["scientific_gate"] == "G1_ONLY_NOT_G2_NOT_G3" and
         review["translation_status"] == "TRANSLATABLE_G1_ONLY_NOT_SIMULATED" and
         len(revised["relationships"]) > len(initial["relationships"]),
         "BUFFALO_REVISION_G1_INVALID")
    need(score["schema"] == "arena.coffee-e2e/1" and
         score["native_evaluation"]["candidate_denominator"] == 13 and
         len(score["native_evaluation"]["scores"]) == 13 and
         set((x["arm"],x["candidate_id"]) for x in score["native_evaluation"]["scores"])
         == set(by_g2) | {("B","B_ORIGINAL_R1")},
         "SEALED_SCORE_NOT_13_HISTORICAL_MODELS")
    buffalo_score = next(x for x in score["native_evaluation"]["scores"]
                         if x["arm"] == "B")
    # Historical scoring belongs to B0 and does NOT validate task mechanisms.
    buffalo = {**bproof, "arm":"B", "method":"Buffalo",
               "version":"Engine.generate currentModel R1",
               "case":"B0", "original_variables":len(initial["variables"]),
               "revised_variables":len(revised["variables"]),
               "original_relationships":len(initial["relationships"]),
               "revised_relationships":len(revised["relationships"]),
               "revised_variable_names":[v["name"] for v in revised["variables"]],
               "own_feedback_packet_sent_in_first_feedback_run": False,
               "later_original_currentModel_review_invoked": True,
               "revised_g1_admissible":review["native_semantic_admissible"],
               "r1_scientific_gate":review["scientific_gate"],
               "sealed_b0_pickups_mae_orders":buffalo_score["mae_pickups_orders"],
               "score_on_synthetic_B0_not_Q75":True,
               "claims_by":"Engine.generate for revision; evaluator for mechanism/score"}
    # P08 M and D are separate method versions, not renamed original B0.
    need(mp["schema"] == "arena.coffee.p08-m-aggregate-capacity/1" and
         mp["status"] == "NATIVE_M_P08_SIX_SIMS_SUCCEEDED" and
         mp_manifest["method"] ==
            "M_EXISTING_E1_COMPOSER_AND_BACKEND_WITH_VERSIONED_ESPRESSO_ROLE" and
         mp_manifest["original_sources_modified"] is False and
         len(mp["attempts"]) == 6 and
         all(x["solver_status"] == "PASS" for x in mp["attempts"]),
         "M_P08_WRONG_VERSION_OR_UNAUTHENTIC_SIMULATION")
    need(dp["schema"] == "arena.coffee.p08-d-stage-capacity/1" and
         dp["status"] == "D_SIX_NATIVE_OMC_PASS_NOT_REAL_CAUSAL_VALIDATION" and
         dp_manifest["original_source_edited"] is False and
         len(dp["attempts"]) == 6 and
         all(x["solver_status"] == "PASS" for x in dp["attempts"]),
         "D_P08_WRONG_VERSION_OR_UNAUTHENTIC_SIMULATION")
    for stem in ("AcceptedSource","BoundedQueue","DeliveryCounter"):
        need(stem in member(z,"m_p08","native.mo").decode(),
             "M_P08_MISSING_MOLECULAR_CLASS_" + stem)
    rows = []
    m_attempts={(x["load_label"],x["variant"]):x for x in mp["attempts"]}
    d_attempts={(x["load_label"],x["variant"]):x for x in dp["attempts"]}
    need(set(m_attempts) == set(d_attempts) and len(m_attempts) == 6,
         "D_M_P08_CASES_DIFFER")
    for label in ("LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75"):
        for action in ("BASE","PREP_CAPACITY_X2","ESPRESSO_CAPACITY_X2"):
            m, drow = m_attempts[(label,action)],d_attempts[(label,action)]
            need(abs(m["modeled_delivered_continuous_at_cut"] -
                     drow["modeled_delivered_continuous_at_cut"]) < 1e-6,
                 "P08_D_M_TRAJECTORY_DIFFERENCE")
            rows.append({"load":label,"action":action,
                         "D_continuous_deliveries":drow["modeled_delivered_continuous_at_cut"],
                         "M_continuous_deliveries":m["modeled_delivered_continuous_at_cut"],
                         "same_rectangular_pulse":dp["input_temporal_profile_identical_to_M_proxy"],
                         "not_independent_empirical_confirmation":True})
    need(dp["input_temporal_profile_identical_to_specialist"] is False and
         dp["stage_mapping_validated"] is False and
         mp["causal_real_business_evidence"] is False,
         "P08_PHYSICAL_EQUIVALENCE_FALSIFIED_AS_TRUE")
    # Hydra D is POLICY comparison, NOT the native grammar D.
    need(hydra["schema"] == "arena.coffee.p46.public-eight-scenario-aggregate/1" and
         hydra["execution_and_consumption"]["github_run_id"] == SOURCES["hydra"][0] and
         hydra["execution_and_consumption"]["github_commit_sha"] == SOURCES["hydra"][2] and
         hydra["source_view_run_id"] == 43684660729 and
         hydra["scenario_count"] == 8 and
         hydra["selected_loads"] == ["LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75"],
         "HYDRA_PROVENANCE_INVALID")
    q75 = hydra["results"][1]
    need(q75["paid_orders"] == 46 and q75["synthetic_beverages"] == 53 and
         q75["load_label"] == "HIGHER_PAID_INPUT_Q75" and
         len(q75["arms"]) == 4, "HYDRA_Q75_MISMATCH")
    hp={x["policy"]:x for x in q75["arms"]}
    need(set(hp)=={"FCFS_READY_ASSUMED","PRIORITIZE_LOAD_READY_WITH_FREE_GROUP",
                  "PRIORITIZE_MILK_READY","PRIORITIZE_HANDOFF_READY"},
         "HYDRA_UNKNOWN_POLICY")
    fc=hp["FCFS_READY_ASSUMED"]; load=hp["PRIORITIZE_LOAD_READY_WITH_FREE_GROUP"]; milk=hp["PRIORITIZE_MILK_READY"]
    hv={"case":"Q75","source_run_id":SOURCES["hydra"][0],
        "paid_orders":q75["paid_orders"],"synthetic_beverages":q75["synthetic_beverages"],
        "horizon_min":q75["source_horizon_min"],"automatic_extraction_s_assumed":90,
        "FCFS_P90_min":fc["p90_paid_to_handoff_full_drain_min"],
        "load_priority_P90_delta_s":round(60*(load["p90_paid_to_handoff_full_drain_min"]-fc["p90_paid_to_handoff_full_drain_min"]),6),
        "milk_priority_P90_delta_s":round(60*(milk["p90_paid_to_handoff_full_drain_min"]-fc["p90_paid_to_handoff_full_drain_min"]),6),
        "fcfs_loading_wait_task_min":fc["waits_from_C_diagnosis"]["stage_breakdown"]["load"]["resource_wait_task_min"],
        "load_policy_loading_wait_task_min":load["waits_from_C_diagnosis"]["stage_breakdown"]["load"]["resource_wait_task_min"],
        "fcfs_all_groups_extracting_task_min":fc["waits_from_C_diagnosis"]["strict_extraction_signal_task_min"],
        "fcfs_manual_block_group_free_task_min":fc["waits_from_C_diagnosis"]["manual_block_with_group_free_task_min"],
        "load_earlier":load["orders_handoff_earlier"],"load_later":load["orders_handoff_later"],
        "milk_earlier":milk["orders_handoff_earlier"],"milk_later":milk["orders_handoff_later"],
        "FCFS_not_observed_policy":True,"H3_group_retained_in_B_state_machine_but_no_real_episode_attributed":True,
        "provenance":q75["source_provenance"]}
    need(hv["milk_priority_P90_delta_s"]<0 and hv["load_priority_P90_delta_s"]>0,
         "HYDRA_POLICY_DIRECTION_DRIFT")
    # These are findings about ARCHIVED NATIVES, not the maximal expressive
    # power of the underlying deterministic grammar, molecular compositor,
    # provider-backed Buffalo, or any unexamined Vensim .mdl library. PR1
    # never submitted the new H1/H2/H3 question to those producers.
    method_matrix = [
        {"method":"gramática D", "version":"original B0 6-candidate stock-flow family", "case":"B0",
         "native_location":"g2:input/native/D/manifest.json; G2 Modelica + CSV",
         "observable":"delivered cumulative at 80/100/103.237 min", "H1":"NOT_ENCODED_IN_ARCHIVED_NATIVE","H2":"NOT_ENCODED_IN_ARCHIVED_NATIVE","H3":"NOT_ENCODED_IN_ARCHIVED_NATIVE",
         "method_decision":"RATIFIED_6_CANDIDATES", "question_H123_asked":"NO", "attribution":"evaluator_from_native_and_method_policy"},
        {"method":"moléculas M","version":"Short E1 original B0", "case":"B0",
         "native_location":"g2:input/native/M/native.mo; six full ASTs in manifest",
         "observable":"deliveredTotal cumulative at 80/100/103.237 min","H1":"NOT_ENCODED_IN_ARCHIVED_NATIVE","H2":"NOT_ENCODED_IN_ARCHIVED_NATIVE","H3":"NOT_ENCODED_IN_ARCHIVED_NATIVE",
         "method_decision":"ABSTAINED_6_NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS", "question_H123_asked":"NO", "attribution":"evaluator_from_native_and_method_policy"},
        {"method":"Buffalo", "version":"original B0→R1 currentModel","case":"B0",
         "native_location":"buffalo_initial + buffalo_r1:provider/native-engine-result.json",
         "observable":"Picked Up Orders Cumulative at three B0 cuts; MAE in synthetic orders", "H1":"NOT_ENCODED_IN_ARCHIVED_NATIVE","H2":"NOT_ENCODED_IN_ARCHIVED_NATIVE","H3":"NOT_ENCODED_IN_ARCHIVED_NATIVE",
         "method_decision":"REVISION_EXECUTED_G1; G2_RESULT_RECOVERED", "question_H123_asked":"NO", "attribution":"evaluator_from_R1_and_sealed_score"},
        {"method":"gramática D", "version":"P08 3-stage capacity extension","case":"P08 Q25/Q75",
         "native_location":"d_p08:DP08_*.mo + result.json",
         "observable":"continuous deliveries at 105-minute rectangular pulse cut","H1":"AGGREGATE_ESPRESSO_PROXY_NOT_GROUP","H2":"NO_SHARED_OPERATOR","H3":"NO_RETAINED_GROUP",
         "method_decision":"NOT_ASKED_TO_REVISE_H123","question_H123_asked":"NO", "attribution":"evaluator_from_equations_and_result"},
        {"method":"moléculas M", "version":"P08 versioned BoundedQueue espresso role","case":"P08 Q25/Q75",
         "native_location":"m_p08:native.mo + result.json","observable":"continuous deliveredTotal at 105-minute rectangular pulse cut",
         "H1":"AGGREGATE_ESPRESSO_PROXY_NOT_GROUP","H2":"NO_SHARED_OPERATOR","H3":"NO_RETAINED_GROUP",
         "method_decision":"NOT_ASKED_TO_REVISE_H123", "question_H123_asked":"NO", "attribution":"evaluator_from_AST_and_result"},
        {"method":"referencia Hydra", "version":"B physical + C diagnostics + policies D","case":"Q75 90s",
         "native_location":"hydra:D_Q25_Q75_AGGREGATE.json + PR44 B state-machine", "observable":"per-order simulated P90 and task-minute waits",
         "H1":"MODEL_SIGNAL_EXTRACTION_BUSY","H2":"MODEL_SIGNAL_MANUAL_BLOCK","H3":"STATE_RETAINED_AFTER_EXTRACTION_NO_OBSERVED_LOCAL_DURATION",
         "method_decision":"ASSUMED_FCFS_MODEL_DIAGNOSTIC", "question_H123_asked":"PARTIALLY", "attribution":"evaluator_from_reference_results_and_B_contract"},
    ]
    for row in method_matrix:
        row["full_method_H123_capacity_tested"] = False
        row["interpretation_scope"] = (
            "ARCHIVED_NATIVE_AND_EXISTING_RESULTS_ONLY" if
            row["method"] != "referencia Hydra" else
            "ASSUMED_PHYSICAL_REFERENCE_NOT_FIELD_OBSERVATION")
    # Numeric scope/type controls: P08 D and M can be compared under their
    # shared pulse at cut; P08 vs Hydra is NOT a comparable numeric experiment.
    p08_scope={"case":"P08_Q75","input_profile":"RECTANGULAR_105_MIN","material_unit":"orders_as_continuous_flow",
               "horizon_min":105,"cut_min":105,"intervention":"PREP_CAPACITY_X2","observable":"delivered_at_cut","observable_unit":"continuous_orders"}
    hydra_scope={"case":"Q75","input_profile":"POSITION_LEVEL_ORDER_ARRIVALS","material_unit":"orders_with_53_beverages",
               "horizon_min":q75["source_horizon_min"],"cut_min":q75["source_horizon_min"],
               "intervention":"PRIORITIZE_MILK_READY","observable":"paid_to_handoff_p90","observable_unit":"minutes_per_order"}
    p08_vs_hydra=validate_comparable(p08_scope,hydra_scope)
    need(not p08_vs_hydra["numeric_comparable"],"P08_HYDRA_FALSE_PARITY")
    # Do not claim the existing ATMS executed a new cross-arm dependency graph.
    shared={"claim":"D/M P08 same quantitative trajectory under same pulse and capacities",
            "shared_premises":["RECTANGULAR_105_MIN_INPUT","NOMINAL_CAPACITIES_12_15_100_PER_H","AGGREGATE_CONTINUOUS_ORDERS"],
            "evidence":["d_p08:result.json","m_p08:result.json"],
            "two_independent_empirical_confirmations":False,
            "cross_arm_ATMS_what_if_executed_in_PR1":False}
    return {"schema": SCHEMA, "mode":"RETROSPECTIVE_PUBLIC_ARTIFACT_READBACK_NOT_BLIND",
            "source_registry":public_provenance(),
            "coverage_audit":{
                "question_H123_newly_asked_of_D_M_B_in_PR1":False,
                "full_producer_capability_to_construct_H123_models_tested":False,
                "new_cloudflare_Buffalo_generate_or_review_POST":0,
                "D_B0_grammar_version":"generic-conservative-chain-search/0.1",
                "D_B0_grammar_examined":"ONE_TO_THREE_SERIAL_STOCKS_WITH_OPTIONAL_LOSS",
                "D_B0_direct_topology_primitives_not_new_fitted_search":True,
                "M_B0_registry":"arena/coffee_adapters/registry.coffee.v1.json",
                "M_B0_declared_e0_catalog":"arena/_vendor/igc/experiments/e0/catalog.json",
                "M_B0_distinct_classes_used":m_B0_classes,
                "M_B0_archived_graph_count":6,
                "M_P08_distinct_classes_used":["accepted-source","bounded-queue","delivery-counter"],
                "M_P08_archived_topologies":1,
                "M_P08_parameter_scenarios":6,
                "additional_unexamined_molecules_may_exist":True,
                "other_Vensim_MDL_or_alternative_catalogs_tested":False,
                "D_accuracy_on_B0_not_causal_mechanism_identification":True,
            },
            "original_B0":{"case_sha256":CASE_B0,"D_candidate_count":6,"M_candidate_count":6,
                           "G2_authenticated":12,"candidate_receipts":original_rows,
                           "feedback_original_policies_invoked":{"D":True,"M":True,"B":False},
                           "historical_B_packet_prepared_not_sent":True},
            "buffalo_R1":buffalo,
            "b0_sealed_scores":{"status":score["native_evaluation"]["status"],
                                "score_scope":"SYNTHETIC_B0_ONLY_NOT_FIELD_OPERATIONS",
                                "candidates":score["native_evaluation"]["scores"]},
            "p08":{"D_method_version":dp_manifest["translation"],
                   "M_method_version":mp_manifest["method"],
                   "D_M_same_pulse":True,"stage_mapping_to_physical_groups_validated":False,
                   "six_native_attempts_each":True,"same_values_rows":rows,
                   "same_model_not_two_independent_confirmations":True},
            "hydra_q75":hv,
            "H1_H2_H3_method_matrix":method_matrix,
            "numeric_comparability_p08_vs_hydra":p08_vs_hydra,
            "shared_premises_example":shared,
            "decision_with_Hydra_only":{
                "action":"NO_SHOP_POLICY_CHANGE", "next_observation":"ONE_ELIGIBLE_LOADING_OPPORTUNITY_WITH_ALL_GROUP_STATES_AND_ELIGIBLE_OPERATOR_ACTIVITY",
                "reason":"CONDITIONAL_AND_UNCALIBRATED_90S_MODEL; H1_H2_COINCIDE; H3_POSSIBLE_IN_STATE_MACHINE"},
            "decision_with_Hydra_plus_DMB":{
                "action":"NO_SHOP_POLICY_CHANGE", "next_observation":"ONE_ELIGIBLE_LOADING_OPPORTUNITY_WITH_ALL_GROUP_STATES_AND_ELIGIBLE_OPERATOR_ACTIVITY",
                "incremental_operational_observation_demonstrated":False,
                "representational_insight":"P08 AGGREGATE_PREPARATION_PROXY_SEPARATE_FROM_PHYSICAL_DISPATCH",
                "reason":"ARCHIVED_D_M_B_NATIVES_LACK_EXPLICIT_H123_STATES_METHOD_CAPABILITIES_NOT_TESTED"},
            "contribution_assessment":{"representational":"D_M_P08_AGGREGATE_STAGE_CAPACITY_CONDITIONAL_MECHANISM; BUFFALO_G1_CAUSAL_REVIEW",
                "informative":"NO_ADDITIONAL_H1_H2_H3_OBSERVATION_DEMONSTRATED_RETROSPECTIVELY",
                "decisional":"PENDING_INDEPENDENT_PROSPECTIVE_CONTRAST",
                "retrospective_no_blinding":True,"no_method_was_asked_H123_in_historic_B0_P08":True},
            "limits":{"no_real_shop_capacity_or_dispatch_validation":True,
                      "source_data_synthetic":True,
                      "no_new_synthetic_world":True,"no_model_rerun_or_provider_calls_or_R2":True,
                      "H3_timer_stopping_not_proof_of_group_release":True,
                      "no_E1_private_30s_result_assumed":True,
                      "no_new_cross_method_ATMS_what_if_executed":True}}


def markdown(report):
    src=report["source_registry"];h=report["hydra_q75"];b=report["buffalo_R1"]
    lines=[
       "# Arena cafetería · PR1 v2 · reconstrucción auténtica de D/M/B y Hydra",
       "", "**RETROSPECTIVA, NO CIEGA.** Los ocho artefactos son resultados auténticos ya publicados.",
       "No se ejecutó un productor, OpenModelica, R2 privado ni un nuevo ATMS transversal.",
       "", "## Las cuatro respuestas para la decisión",
       "", "**Hydra sola:** no cambiar prioridades del local; observar una oportunidad",
       "de carga con el estado simultáneo de los tres grupos, extracción, retirada",
       "y tareas/aptitudes de los operadores. H1, H2 y H3 pueden coexistir.",
       "", "**Qué aportaron los métodos:** D ratificó 6 candidatos B0, M se abstuvo de",
       "revisar 6 candidatos por no disponer de dos observaciones tardías; Buffalo",
       "revisó su propio padre mediante `currentModel` y produjo un nativo G1 R1.",
       "P08 D/M añadió una hipótesis de capacidad agregada de preparación, no",
       "una representación de competencia entre barista y grupo concreto.",
       "", "**Decisión tras añadir D/M/B:** no cambia la acción ni se demuestra",
       "otra observación operativa que distinga H1/H2/H3 frente a Hydra.",
       "D/M P08 añaden perspectiva estructural; esto NO es confirmación independiente.",
       "", "**Única observación dirigida:** cuando una bebida pueda cargarse,",
       "registrar en una misma ventana grupos G01/G02/G03 extrayendo / libres /",
       "esperando retirada, elegibilidad de la tarea y ocupación/aptitud manual.",
       "Si la visibilidad es parcial, clasificar episodio indeterminado.",
       "", "## Evidencia original B0: seis D, seis M y Buffalo R1",
       "", "| Método | Modelo / regla | Resultado comprobado | Límite |",
       "|---|---|---|---|",
       "| Gramática D (original B0) | 6 modelos stock-flow; 12 G2 D/M | 6 RATIFIED | Ratificar no valida física |",
       "| Moléculas M (Short E1 original B0) | 6 AST completos; cola acotada | 6 ABSTAINED (sin dos retiros tardíos) | Abstenerse de revisión no cancela predicción |",
       f"| Buffalo R1 | padre `{b['parent_sha256'][:27]}…` → hijo `{b['child_sha256'][:27]}…` | {b['original_variables']}→{b['revised_variables']} variables; {b['original_relationships']}→{b['revised_relationships']} relaciones | R1 G1, no identifica recursos físicos |",
       "", "**Buffalo B0:** error absoluto medio en tres cortes sintéticos = " +
       f"{b['sealed_b0_pickups_mae_orders']:.6f} pedidos; un acierto del contador no valida H1/H2/H3.",
       "La disposición B en el run inicial de feedback fue **PAQUETE PREPARADO, NO ENVIADO**;",
       "la revisión original ocurrió **después, en otro run**. No fusionar ambos eventos.",
       "", "### Artefactos de respaldo por candidato y origen",
       "", "El JSON adjunto incluye 12 filas de candidato con `parent_sha256`, `native_sha256`,",
       "`g2_csv_sha256`, regla, disposición y la proyección temporal del Ledger.",
    ]
    for key in ("g2","feedback","buffalo_initial","buffalo_r1","buffalo_score"):
        a=src[key];lines.append(f"- **{key}**: [run {a['run_id']}]({a['github_run_url']}), artifact `{a['artifact_id']}`, commit `{a['commit_sha']}`; ZIP `{a['zip_sha256']}`")
    lines.extend(["", "## Extensiones posteriores D/M P08: mismo resultado, soporte compartido",
                  "", "| Carga | Acción | D entregas continuas | M entregas continuas |",
                  "|---|---|---:|---:|"])
    for x in report["p08"]["same_values_rows"]:
        lines.append(f"| {x['load']} | {x['action']} | {x['D_continuous_deliveries']:.6f} | {x['M_continuous_deliveries']:.6f} |")
    lines.extend(["", "D/M comparten el pulso rectangular de 105 minutos y capacidades nominales",
                  "de preparación/espresso/despacho 12/15/100 pedidos/h. La igualdad de",
                  "sus trayectorias **no son dos observaciones empíricas independientes**.",
                  "Ni duplicar el máximo de espresso en pedidos/h ni esa cola agregada",
                  "equivalen a habilitar un grupo físico o disputar trabajo manual.",
                  "", "## Referencia Hydra Q75 (90 segundos supuestos)",
                  "", f"- 46 pedidos pagados / 53 bebidas sintéticas; horizonte `{h['horizon_min']}` min.",
                  f"- FCFS P90 `{h['FCFS_P90_min']:.6f}` min; priorizar carga ΔP90 `{h['load_priority_P90_delta_s']:+.3f}` s, priorizar leche ΔP90 `{h['milk_priority_P90_delta_s']:+.3f}` s.",
                  f"- Espera de carga: `{h['fcfs_loading_wait_task_min']:.4f}` → `{h['load_policy_loading_wait_task_min']:.4f}` min-tarea; 9 pedidos antes/9 después bajo prioridad de carga.",
                  f"- FCFS H1 señal `{h['fcfs_all_groups_extracting_task_min']:.4f}` min-tarea; H2 señal `{h['fcfs_manual_block_group_free_task_min']:.4f}` min-tarea. Son esperas de tareas, **no tiempo de reloj sumable**.",
                  "- H3 es estado representado en el motor B; el agregado publicado no permite atribuir un episodio real ni cuantificar su duración en barra.",
                  "", "## Alcance exacto: modelos archivados, no productores completos",
                  "", "Esta reconstrucción **NO ejecutó de nuevo D/M/B** ni les formuló H1/H2/H3.",
                  "El veredicto de la tabla habla exclusivamente de la representación nativa archivada:",
                  "NO codificar una variable no demuestra incapacidad del método para construirla.",
                  "", "**D B0:** gramática determinista `generic-conservative-chain-search/0.1`,",
                  "seis cadenas de 1–3 stocks con/sin pérdida y parámetros supuestos.",
                  "La ruta de cafetería invocó primitivas de topología, no una nueva búsqueda",
                  "ajustada a observaciones de tareas. Su MAE sintético de retiros acumulados",
                  "no identifica qué recurso originó una espera.",
                  "", "**M B0:** seis grafos enumerados del registro específico de cafetería",
                  "con cuatro clases distintas: " + ", ".join(report["coverage_audit"]["M_B0_distinct_classes_used"])+".",
                  "Las alternativas varían tránsito y filtrado de reporte, no operadores",
                  "ni reservas de grupos físicos. **M P08:** una sola topología",
                  "`AcceptedSource → BoundedQueue preparación → BoundedQueue espresso →",
                  "BoundedQueue despacho → DeliveryCounter` en seis casos de parámetros.",
                  "No se probaron otras moléculas, catálogos alternativos o archivos Vensim .mdl.",
                  "", "**Buffalo:** B0→R1 es una revisión real y su modelo sellado,",
                  "pero de una pregunta sobre retiros acumulados. El nativo R1 no codifica",
                  "operadores ni grupos identificados. **PR1 no hizo un nuevo POST Cloudflare**",
                  "ni probó si Buffalo puede generar ese detalle bajo otra consigna.",
                  "", "## Capacidad de distinguir H1 / H2 / H3",
                  "", "**Unidad de análisis:** una oportunidad de carga sobre grupo concreto, no el contador acumulado de pedidos.",
                  "Los códigos `NOT_ENCODED_IN_ARCHIVED_NATIVE` describen el modelo",
                  "publicado; `full_method_H123_capacity_tested=false` impide extrapolarlos",
                  "a la capacidad de construcción del método completo.",
                  "", "| Método (versión) | H1 | H2 | H3 | ¿Se le preguntó históricamente? |",
                  "|---|---|---|---|---|"])
    for row in report["H1_H2_H3_method_matrix"]:
        lines.append("| "+" | ".join([row["method"]+" ("+row["version"]+")",row["H1"],row["H2"],row["H3"],row["question_H123_asked"]])+" |")
    p=report["numeric_comparability_p08_vs_hydra"]
    lines.extend(["", "## Comparabilidad, memoria y atribución",
       "", "**P08 vs Hydra Q75:** NO se permite restar cuantías, ni comparar P90",
       "con flujos continuos. Cambian: " + ", ".join(p["mismatches"])+".",
       "Por contraste, D P08 y M P08 sí permiten comparar la dinámica",
       "agregada **bajo supuestos compartidos**; eso no prueba independencia.",
       "", "**ATMS:** PR1 **lee** disposiciones y proyecciones históricas con",
       "cortes `as_known_at`. No ejecuta una nueva retirada de soporte ni",
       "atribuye a ATMS una justificación transversal inexistente.",
       "La prueba de retirar por separado un brazo o la premisa compartida",
       "queda para PR2; dos métodos sobre un supuesto común no equivalen a",
       "dos confirmaciones observacionales.",
       "", "**Nivel representacional:** demostrado, con límites.",
       "**Nivel informativo:** no se demuestra una observación H1/H2/H3 adicional.",
       "**Nivel decisional:** PENDIENTE DE CONTRASTE PROSPECTIVO INDEPENDIENTE.",
       "No se seleccionó un modelo ganador por MAE retrospectivo.",
       "", "## Procedencia de las extensiones y de Hydra",
       ""])
    for key in ("m_p08","d_p08","hydra"):
        a=src[key];lines.append(f"- **{key}**: [run {a['run_id']}]({a['github_run_url']}), artifact `{a['artifact_id']}`, commit `{a['commit_sha']}`; ZIP `{a['zip_sha256']}`")
    lines.extend(["", "## Qué queda abierto", "",
        "PR47/E1 tiene autorización y ejecución separadas. Este lector no presupone",
        "resultado privado Q75 a 30s y no convierte ninguno de los archivos",
        "históricos en una predicción nueva o confirmación empírica independiente.",
        "Los productores nunca respondieron prospectivamente a H1/H2/H3;",
        "PR2 deberá formular la pregunta, preservar padres/versiones y las",
        "disposiciones propias. Sin datos reales comparables, la decisión es",
        "**OBSERVAR, NO CAMBIAR OPERACIÓN**.", ""])
    return "\n".join(lines)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--public-zips",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    target=Path(a.out)
    need(not target.exists(),"OUTPUT_ALREADY_EXISTS")
    result=readback(a.public_zips)
    target.mkdir(parents=True)
    (target/"THREE_ARMS_V2_READBACK.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (target/"THREE_ARMS_V2_DECISION.md").write_text(
        markdown(result),encoding="utf-8")
    print("THREE_ARMS_V2_AUTHENTIC_READBACK","ARTIFACTS",len(SOURCES),
          "D_CANDIDATES",6,"M_CANDIDATES",6,"BUFFALO_R1",1,
          "NEW_POST",0,"NEW_OMC",0,"PRIVATE_R2_GET",0,
          "RETROSPECTIVE_ONLY",True)


if __name__=="__main__":
    main()
