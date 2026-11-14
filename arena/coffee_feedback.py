"""Coffee B0: real G2/ G1 -> own-lane Ledger/ATMS -> producer-native policy.

No CT03 world reuse. This adapter uses the original Ledger / ATMS / memory
and original D fixed-set / Short E1 M own_policy primitives without altering
the original vendored code. Buffalo's original currentModel review is only
prepared, never called without separate provider authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from tempfile import TemporaryDirectory
import zipfile

from .common import ArenaError, digest, read_json, write_json
from .coffee_adapters.shared import VENDOR_ROOT, sha_bytes
from .coffee_adapters import d as d_adapter, m as m_adapter
from .coffee_adapters.b_translation import generate as translate_b, TranslationBlocked
from . import coffee_dm_solver as g2, coffee_dm_campaign as dm
from .connections import Secret
from .github import GitHub
from .runtime import verify as verify_originals

REPO = "yudocyudoc/igc-modular"
WORKFLOW = ".github/workflows/coffee-b0-feedback.yml"
G2_RUN_ID = 43550618982
G2_SHA = "69638301626dd482556f58eaead298a5c620d9bf"
G2_ARTIFACT_ID = 14094919865
G2_ARCHIVE_SHA = "sha256:1f10695e4dcd27ad4f29552c3c954b4ce26efb131594b0b18076f52a26701925"
B_RUN_ID = 43537333254
B_SHA = "399eddbc0d674e8b2370f908a75ba73e694153c3"
B_ARTIFACT_ID = 14090920829
B_ARCHIVE_SHA = "sha256:70f9e9f846a33cd470b00dbaf0bf189b0b6c7a029b68bd84485f7c6bbe748265"
MAX_ARCHIVE_BYTES = 3_000_000
MAX_CONTENT_BYTES = 12_000_000
MAX_ENTRIES = 1000

G2_WORKFLOW = ".github/workflows/coffee-dm-modelica.yml"
B_WORKFLOW = ".github/workflows/coffee-buffalo-live.yml"


def need(value, code):
    if not value:
        raise ArenaError("COFFEE_FEEDBACK_" + code)


def identity(env=None):
    env = os.environ if env is None else env
    need(env.get("GITHUB_REPOSITORY") == REPO
         and env.get("GITHUB_REF") == "refs/heads/main"
         and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and env.get("GITHUB_EVENT_NAME") in ("push", "workflow_dispatch")
         and re.fullmatch(r"[1-9][0-9]{0,19}", env.get("GITHUB_RUN_ID", "")),
         "MAIN_FIRST_RUN_ONLY")
    need(not any(env.get(x) for x in dm.NO_R2),
         "PRIVATE_OR_PROVIDER_CREDENTIAL_PRESENT")
    return int(env["GITHUB_RUN_ID"])


def _original_bridge():
    original = verify_originals(include_history=False)
    need(original.get("unchanged") is True and original.get("files", 0) > 0,
         "ORIGINAL_METHODS_NOT_VERIFIED")
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    from scripts.arena_cafe import ct_feedback_bridge as bridge
    return bridge


def _safe_archive(raw, *, expected_digest, max_file=MAX_CONTENT_BYTES):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE_BYTES
         and sha_bytes(raw) == expected_digest, "GITHUB_ZIP_SHA256_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            entries = zf.infolist()
            need(0 < len(entries) <= MAX_ENTRIES
                 and sum(x.file_size for x in entries) <= MAX_CONTENT_BYTES,
                 "ARCHIVE_BOUNDS_EXCEEDED")
            result = {}
            for entry in entries:
                path = PurePosixPath(entry.filename)
                need(not entry.is_dir() and
                     not path.is_absolute() and
                     not any(part in ("", ".", "..") for part in path.parts) and
                     "\\" not in entry.filename and
                     not stat.S_ISLNK(entry.external_attr >> 16) and
                     entry.file_size <= max_file and
                     entry.filename not in result,
                     "UNSAFE_OR_DUPLICATE_ZIP_MEMBER")
                result[entry.filename] = zf.read(entry)
        return result
    except (ValueError, zipfile.BadZipFile, OSError, RuntimeError):
        raise ArenaError("COFFEE_FEEDBACK_UNREADABLE_ZIP") from None


def _fetch(api, *, run_id, sha, artifact_id, archive_sha, workflow, artifact_name, event):
    run = api.run(run_id)
    need(run.get("id") == run_id
         and run.get("head_sha") == sha
         and run.get("head_branch") == "main"
         and run.get("path") == workflow
         and run.get("event") == event
         and run.get("run_attempt") == 1
         and run.get("status") == "completed"
         and run.get("conclusion") == "success",
         "SOURCE_RUN_IDENTITY_FAILED")
    meta = api.repo("GET", f"/actions/artifacts/{artifact_id}")
    need(meta.get("id") == artifact_id
         and meta.get("name") == artifact_name
         and meta.get("expired") is False
         and meta.get("digest") == archive_sha
         and meta.get("workflow_run", {}).get("id") == run_id,
         "SOURCE_ARTIFACT_IDENTITY_FAILED")
    raw = api.repo("GET", f"/actions/artifacts/{artifact_id}/zip", binary=True)
    return _safe_archive(raw, expected_digest=archive_sha)


def _json(entries, name):
    need(name in entries, "ARTIFACT_MEMBER_MISSING:" + name)
    return json.loads(entries[name])


def _model_primitives(native, receipt, admission, final):
    """Authenticate own Buffalo native, not a hypothetical repaired structure."""
    need(set(native) == {"model", "supportingInfo"}
         and isinstance(native["model"], dict)
         and isinstance(native["model"].get("variables"), list)
         and isinstance(native["model"].get("relationships"), list),
         "B_NOT_ORIGINAL_NATIVE_ENVELOPE")
    need(receipt.get("schema") == "arena.coffee-peak.b-live-receipt/1"
         and receipt.get("status") == "ORIGINAL_ENGINE_LIVE_NATIVE_NOT_VALIDATED"
         and receipt.get("mode") == "CLOUDFLARE_WORKERS_AI_LIVE_ONE_POST"
         and receipt.get("original_engine") == "Engine.generate"
         and receipt.get("http_status") == 200
         and receipt.get("run_id") == B_RUN_ID
         and receipt.get("source_run_id") == dm.SOURCE_RUN_ID
         and receipt.get("source_artifact_id") == dm.ARTIFACT_ID
         and receipt.get("case_sha256") == dm.CASE_SHA256
         and receipt.get("public_sha256") == dm.PUBLIC_SHA256
         and receipt.get("model_returned") is True
         and receipt.get("provider_posts") == 1
         and receipt.get("cloudflare_requests") == 1
         and receipt.get("sdk_interceptions") == 1
         and receipt.get("raw_provider_saved") is True
         and receipt.get("new_omc") == 0
         and receipt.get("truth_access") is False
         and receipt.get("scientific_lock_created") is False,
         "B_PROVIDER_RECEIPT_NOT_LIVE_PARENT")
    need(admission.get("run_id") == B_RUN_ID
         and admission.get("case_sha256") == dm.CASE_SHA256
         and admission.get("artifact_id") == dm.ARTIFACT_ID
         and admission.get("source_run_id") == dm.SOURCE_RUN_ID,
         "B_ADMISSION_MISMATCH")
    need(final.get("attempt_reserved") is True
         and final.get("provider_posts_observed") == 1
         and final.get("raw_provider_saved") is True
         and final.get("status") == "NATIVE_NOT_VALIDATED"
         and final.get("retries") == 0
         and final.get("scientific_lock_created") is False,
         "B_FINAL_RECEIPT_INCONSISTENT")
    return receipt["native_file_sha256"]


def _verify_b(entries):
    need(set(entries) == {
        "admission.json", "attempt.json", "final.json", "input.json",
        "node.log", "process.json", "provider/cf-call-started.json",
        "provider/cloudflare-effective-request.json",
        "provider/native-engine-result.json",
        "provider/openrouter-compat-envelope.json",
        "provider/provider-raw.json", "provider/receipt.json",
        "provider/sdk-request.json"}, "B_ORIGINAL_ARTIFACT_MEMBER_SET_CHANGED")
    native = _json(entries, "provider/native-engine-result.json")
    receipt = _json(entries, "provider/receipt.json")
    admission = _json(entries, "admission.json")
    final = _json(entries, "final.json")
    public_input = _json(entries, "input.json")
    native_sha = _model_primitives(native, receipt, admission, final)
    need(native_sha == sha_bytes(entries["provider/native-engine-result.json"])
         and public_input.get("case_sha256") == dm.CASE_SHA256
         and public_input.get("source_artifact_id") == dm.ARTIFACT_ID
         and public_input.get("execution_run_id") == B_RUN_ID
         and public_input.get("truth_access") is False
         and public_input.get("scientific_lock_created") is False,
         "B_NATIVE_BYTES_OR_CONTEXT_MISMATCH")
    try:
        translate_b(native)
    except TranslationBlocked as exc:
        translator = {"status": "G1_TRANSLATION_BLOCKED_ORIGINAL_UNCHANGED",
                      "first_failure": str(exc)}
    else:
        translator = {"status": "G1_TRANSLATION_ACCEPTED_NOT_G2",
                      "first_failure": None}
    # Independent audit of native graph/step semantics; not equation repair.
    variables = {v.get("name"): v for v in native["model"]["variables"]}
    invalid_material_ports = sorted({
        port
        for v in variables.values() if v.get("type") == "stock"
        for port in (v.get("inflows", []) + v.get("outflows", []))
        if port not in variables or variables[port].get("type") != "flow"
    })
    specs = native["model"].get("specs", {})
    expected_dt = (103.237/60.0)/64.0
    notes = {
        "material_ports_on_non_flow": invalid_material_ports,
        "native_dt_hours": specs.get("dt"),
        "pinned_translator_dt_hours": expected_dt,
        "native_dt_matches_translator": specs.get("dt") == expected_dt,
        "empty_causal_relationships": not bool(native["model"]["relationships"]),
        "all_findings_are_G1_not_G2": True,
        "no_native_change": True,
    }
    return native, receipt, native_sha, translator, notes


def _verify_g2(entries):
    plan = _json(entries, "plan.json")
    result = _json(entries, "result.json")
    audit = _json(entries, "input/audit.json")
    stage = _json(entries, "stage-receipt.json")
    history = _json(entries, "history-receipt.json")
    case = _json(entries, "input/native/public-case.json")
    dm_d = _json(entries, "input/native/D/manifest.json")
    dm_m = _json(entries, "input/native/M/manifest.json")
    events = entries.get("attempts.jsonl", b"").decode("utf-8").splitlines()
    need(plan.get("schema") == "arena.coffee-peak.dm-g2-plan/1"
         and result.get("schema") == "arena.coffee-peak.dm-g2-physical-batch/1"
         and result.get("run_id") == G2_RUN_ID
         and result.get("head_sha") == G2_SHA
         and result.get("source_native_artifact_id") == g2.ARTIFACT_ID
         and result.get("source_native_run_id") == g2.SOURCE_RUN
         and result.get("case_sha256") == dm.CASE_SHA256
         and result.get("attempts_reserved") == 12
         and result.get("simulations_authenticated") == 12
         and result.get("maximum_allowed_attempts") == 12
         and result.get("historical_omc_invocations_before_this_run") == 12
         and result.get("ledger_atms_feedback_consumed") is False
         and result.get("truth_access") is False
         and result.get("provider_posts") == 0
         and result.get("r2_access") is False
         and result.get("scientific_lock_created") is False
         and result.get("no_retries") is True
         and plan.get("case_sha256") == dm.CASE_SHA256
         and plan.get("source_native_artifact_id") == g2.ARTIFACT_ID
         and plan.get("source_native_zip_sha256") == "sha256:" + g2.ARCHIVE_SHA
         and audit.get("status") ==
             "TWELVE_NATIVE_CANDIDATES_STATIC_AUDITED_NOT_SIMULATED"
         and audit.get("case_sha256") == dm.CASE_SHA256
         and stage.get("execution_run_id") == G2_RUN_ID
         and stage.get("case_sha256") == dm.CASE_SHA256
         and history.get("previous_omc_invocations_spent") == 12
         and history.get("one_verified_execution_bug_recovery") is True
         and case.get("public_sha256") == dm.PUBLIC_SHA256
         and case.get("selection") == dm.SELECTION
         and case.get("input", {}).get("rate_orders_per_hour") == 10.0,
         "G2_NOT_THE_AUTHENTIC_TWELVE_SUCCESSFUL_RUN")
    items = plan.get("candidates")
    receipts = result.get("results")
    need(isinstance(items, list) and isinstance(receipts, list)
         and len(items) == len(receipts) == len(events) == 12
         and [i["arm"] for i in items] == ["D"]*6 + ["M"]*6
         and [i["index"] for i in items] == list(range(6))*2,
         "G2_CANDIDATE_COUNT_OR_ORDER_MISMATCH")
    manifests = {"D": dm_d, "M": dm_m}
    verified = {"D": [], "M": []}
    with TemporaryDirectory() as temporary:
        for i, (item, saved, event) in enumerate(zip(items, receipts, events), 1):
            attempt = json.loads(event)
            arm = item["arm"]
            source = manifests[arm]["candidates"][item["index"]]
            need(source["id"] == item["id"] == saved.get("candidate_id")
                 and item["arm"] == saved.get("arm")
                 and saved.get("attempt_number") == i
                 and attempt.get("attempt_number") == i
                 and attempt.get("candidate_id") == item["id"]
                 and attempt.get("reserved_before_omc") is True
                 and attempt.get("run_id") == G2_RUN_ID
                 and attempt.get("head_sha") == G2_SHA
                 and item["model_sha256"] == saved.get("model_sha256")
                 and item["script_sha256"] == saved.get("script_sha256")
                 and saved.get("status") == "G2_PHYSICAL_PASS_NOT_G3"
                 and saved.get("check_model_completed") is True
                 and saved.get("solver_simulation_authenticated") is True
                 and saved.get("omc_exit_code") == 0
                 and saved.get("provider_posts") == 0
                 and saved.get("scientific_lock_created") is False
                 and saved.get("r2_access") is False
                 and saved.get("retry") is False
                 and item["csv"] in entries and item["log"] in entries
                 and item["script"] in entries and item["model_file"] in entries
                 and sha_bytes(entries[item["csv"]]) == saved.get("csv_sha256")
                 and sha_bytes(entries[item["log"]]) == saved.get("solver_log_sha256")
                 and sha_bytes(entries[item["script"]]) == item["script_sha256"]
                 and sha_bytes(entries[item["model_file"]]) == item["model_sha256"],
                 "G2_MODEL_TRACE_SCRIPT_OR_ATTEMPT_BYTES_CHANGED")
            logfile = entries[item["log"]].decode("utf-8",errors="replace")
            need("LOG_SUCCESS" in logfile and
                 f"Check of {item['modelica_class']} completed successfully" in logfile
                 and "Simulation execution failed" not in logfile,
                 "G2_LOG_NOT_AUTHENTIC_SUCCESS")
            trace = Path(temporary) / f"{item['prefix']}.csv"
            trace.write_bytes(entries[item["csv"]])
            # Independent physical audit of real CSV bytes and projection.
            checked = g2.verify_csv(trace, item)
            need(checked.get("samples") == saved.get("samples")
                 and checked.get("status") ==
                     "G2_NATIVE_CSV_FINITE_NONNEGATIVE_BALANCED_NOT_G3"
                 and abs(checked["max_abs_balance_orders"] -
                         saved["max_abs_balance_orders"]) < 1e-10
                 and checked["provisional_unsealed_predicted_pickups"] ==
                     saved["provisional_unsealed_predicted_pickups"],
                 "G2_REPLAY_PHYSICAL_AUDIT_MISMATCH")
            parent = (source["structure_hash"] if arm == "D"
                      else source["full_ast_sha256"])
            need(re.fullmatch(r"sha256:[0-9a-f]{64}", parent) is not None,
                 "PARENT_HASH_INVALID")
            if arm == "M":
                need(source["physical_counter"] == "deliveredTotal"
                     and source["informational_signal_not_counter"] ==
                         "reportedDeliveryRate",
                     "M_INFORMATION_MISTAKEN_FOR_MATERIAL")
            else:
                need(source["physical_counter"] == "delivered",
                     "D_PHYSICAL_COUNTER_MISMATCH")
            verified[arm].append({
                "arm": arm, "candidate_id": item["id"],
                "parent_hash": parent,
                "model_sha256": item["model_sha256"],
                "modelica_class": item["modelica_class"],
                "csv_sha256": saved["csv_sha256"],
                "omc_script_sha256": item["script_sha256"],
                "solver_log_sha256": saved["solver_log_sha256"],
                "G2": saved["status"],
                "check_model_success": True,
                "physical_balance_max_abs_orders": checked["max_abs_balance_orders"],
                "material_stocks": list(item["stocks"]),
                "observed_pickups": False,
                "observations": [],
                "native_counter": item["counter"],
                "predictions": checked["provisional_unsealed_predicted_pickups"],
                "native_parent": source,
            })
    return verified, {"plan_sha256": sha_bytes(entries["plan.json"]),
                       "result_sha256": sha_bytes(entries["result.json"]),
                       "g2_run": G2_RUN_ID, "g2_artifact": G2_ARTIFACT_ID,
                       "all_12_original_models_passed_G2": True}


def _diagnostic(arm, candidate):
    obs = candidate["observations"]
    need(obs == [], "UNMEASURED_PICKUPS_MUST_NOT_BE_FABRICATED")
    return {
        "schema": "arena.coffee-peak.own-feedback-diagnostic/1",
        "arm": arm, "condition": "B0",
        "source_hash": dm.CASE_SHA256,
        "case_sha256": dm.CASE_SHA256,
        "parent_hash": candidate["parent_hash"],
        "evidence": "G2",
        "trace_sha256": candidate["csv_sha256"],
        "model_sha256": candidate["model_sha256"],
        "script_sha256": candidate["omc_script_sha256"],
        "solver_log_sha256": candidate["solver_log_sha256"],
        "own_evidence_only": True, "no_future_truth": True,
        "observations": obs,
        "G2_status": candidate["G2"],
        "physical_balance_max_abs_orders":
            candidate["physical_balance_max_abs_orders"],
        "assumptions": {
            "paid_order_rate_per_hour": 10.0,
            "preparation_response_hours": 0.1,
            "capacity_orders_per_hour": 12.0,
            "pickups_are_measured": False
        },
        "forecast_provisional_unsealed_sha256": digest(candidate["predictions"]),
        "constraints": [
            "Conservation and G2 solvability are not causal adequacy",
            "No public pickup observations permit empirical residuals",
            "No policy S1-S5 or economic causal effect identified",
        ],
    }


def connect(g2_entries, b_entries, out):
    """Actually call original CT02 bridge and producer-native own decisions."""
    out = Path(out)
    need(not out.exists(), "OUTPUT_ALREADY_EXISTS")
    bridge = _original_bridge()
    verified, g2_attested = _verify_g2(g2_entries)
    native_b, provider_receipt, b_parent, translation, b_g1 = _verify_b(b_entries)
    need(provider_receipt["case_sha256"] == dm.CASE_SHA256,
         "B_AND_DM_DIFFERENT_PUBLIC_CASES")
    # Separate physical DBs by arm: no producer is passed a rival's ledger or
    # model. Bridge then additionally enforces a typed parent-only subcase.
    out.mkdir(parents=True,mode=0o700)
    event_time = datetime.now(timezone.utc).isoformat()
    result = {
        "schema": "arena.coffee-peak.own-ledger-atms-consumption/1",
        "status": "OWN_FEEDBACK_RETRIEVED_DM_POLICIES_INVOKED_B_PACKET_NOT_SENT",
        "case_sha256": dm.CASE_SHA256,
        "source_public_run_id": dm.SOURCE_RUN_ID,
        "source_public_artifact_id": dm.ARTIFACT_ID,
        "G2": g2_attested,
        "B": {"run_id": B_RUN_ID, "artifact_id": B_ARTIFACT_ID,
              "original_engine": "Engine.generate",
              "original_native_file_sha256": b_parent,
              "translation": translation, "native_g1_diagnostics": b_g1},
        "logical_record_time_utc": event_time,
        "arms": {},
        "revisions_proposed_by_adapter": 0,
        "new_omc": 0, "provider_posts": 0,
        "reserved_truth_access": False, "scientific_lock_created": False,
        "G3_completed": False, "cross_arm_model_delivery": False,
    }
    composer, _, _ = m_adapter.original()
    cfg, classes, _ = composer.load_registry(m_adapter.REGISTRY)
    need(cfg["roles"]["transit"]["parameters"]["responseTime"] == 1.6,
         "M_CATALOG_NOT_UNCHANGED")
    for arm in ("D", "M"):
        db = out / f"{arm}-ledger.sqlite"
        rows = []
        for candidate in verified[arm]:
            ctx = bridge.make_context(
                experiment="Coffee",world="Peak",round_id="R0",
                arm=arm,condition="B0",source_hash=dm.CASE_SHA256)
            parent_hash = candidate["parent_hash"]
            diagnostic = _diagnostic(arm, candidate)
            stored = bridge.record_feedback(
                db, ctx, parent_hash=parent_hash, diagnostic=diagnostic,
                recorded_at=event_time)
            # The policy method itself must be the original; retrieving here
            # alone and fabricating a decision would not count as consumption.
            if arm == "D":
                own = bridge.d_fixed_decision(
                    db,ctx,parent_hash=parent_hash,as_known_at=event_time)
                action = "FIXED_STRUCTURE_SET_NO_ORIGINAL_D_REVISION_SUPPORTED"
                need(own["status"] == "RATIFIED" and
                     own["model_revision"] is False,
                     "D_ORIGINAL_FIXED_POLICY_CHANGED")
            else:
                graph = candidate["native_parent"]["full_ast"]
                need(digest(graph) == parent_hash,
                     "M_ORIGINAL_AST_HASH_MISMATCH")
                own = bridge.own_m_decision(
                    db,ctx,parent_graph=graph,as_known_at=event_time,
                    classes=classes)
                action = "NO_REVISION_WITHOUT_OBSERVED_PICKUP_RESIDUALS"
                need(own["status"] == "ABSTAINED"
                     and own.get("reason") == "NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS"
                     and own.get("new_model") is None,
                     "M_POLICY_MUST_ABSTAIN_WITHOUT_EMPIRICAL_RESIDUALS")
            need(own.get("parent_hash") == parent_hash and
                 own.get("feedback_hash") == stored["diagnostic_hash"] and
                 isinstance(own.get("retrieved_before_policy"),dict) and
                 own.get("provider_calls") == 0 and own.get("new_omc") == 0,
                 "OWN_POLICY_DID_NOT_RETRIEVE_SAME_PARENT_FEEDBACK")
            disposition = bridge.persist_disposition(
                db,ctx,decision=own,recorded_at=event_time)
            rows.append({
                "candidate_id": candidate["candidate_id"],
                "parent_hash": parent_hash,
                "native_model_sha256": candidate["model_sha256"],
                "csv_sha256": candidate["csv_sha256"],
                "diagnostic_sha256": stored["diagnostic_hash"],
                "recorded_to_ledger": stored["stored_feedback"],
                "retrieved_before_policy": own["retrieved_before_policy"],
                "original_policy": own["policy"],
                "original_policy_status": own["status"],
                "original_policy_reason": own.get("reason"),
                "adapter_interpretation": action,
                "method_disposition": disposition,
                "new_model": False,
                "new_omc": 0, "provider_posts": 0,
            })
        result["arms"][arm] = {
            "candidate_count": len(rows),
            "own_feedback_retrieved_before_policy": all(
                x["retrieved_before_policy"].get("projection_hash")
                for x in rows),
            "own_original_policy_invoked": True,
            "ledger_sqlite_sha256": sha_bytes(db.read_bytes()),
            "candidates": rows,
        }
    need(len(result["arms"]["D"]["candidates"]) ==
         len(result["arms"]["M"]["candidates"]) == 6,
         "NOT_TWELVE_OWN_PARENT_DISPOSITIONS")
    # B has one authenticated original G1 parent. Its original LLM method
    # cannot be invoked on real feedback with 0 provider calls. Do not invent
    # an engine review or claim a "decision" was made by Buffalo.
    b_db = out/"B-ledger.sqlite"
    b_context = bridge.make_context(
        experiment="Coffee",world="Peak",round_id="R0",
        arm="B",condition="B0",source_hash=dm.CASE_SHA256)
    b_diagnostic = {
        "schema":"arena.coffee-peak.own-feedback-diagnostic/1",
        "arm":"B","condition":"B0","source_hash":dm.CASE_SHA256,
        "parent_hash":b_parent,"evidence":"G1",
        "own_evidence_only":True,"no_future_truth":True,
        "observations":[],
        "original_native_file_sha256":b_parent,
        "original_native_provider_sha256":provider_receipt["native_sha256"],
        "provider_posts_historical":1,
        "provider_posts_this_feedback_phase":0,
        "translation":translation,"native_semantic_diagnostics":b_g1,
        "no_silent_model_repair":True
    }
    saved=bridge.record_feedback(
        b_db,b_context,parent_hash=b_parent,
        diagnostic=b_diagnostic,recorded_at=event_time)
    recovered=bridge.recover_feedback(
        b_db,b_context,parent_hash=b_parent,as_known_at=event_time)
    need(recovered["diagnostic_hash"] == saved["diagnostic_hash"] and
         recovered["diagnostic"] == b_diagnostic and
         recovered["retrieval"].get("projection_hash"),
         "B_G1_FEEDBACK_NOT_RECOVERED")
    packet = {
        "schema":"arena.coffee-peak.buffalo-review-envelope/1",
        "status":"OWN_G1_FEEDBACK_RETRIEVED_PACKET_PREPARED_NOT_SENT",
        "original_method":"UB-IAD/sd-ai::Engine.generate",
        "currentModel":native_b["model"],
        "parent_native_file_sha256":b_parent,
        "parent_provider_receipt_sha256":sha_bytes(
            b_entries["provider/receipt.json"]),
        "diagnostic_sha256":saved["diagnostic_hash"],
        "own_feedback":recovered["diagnostic"],
        "retrieved_before_any_possible_review":recovered["retrieval"],
        "provider_posts_this_phase":0,
        "original_engine_review_invoked":False,
        "revision_budget_authorized":False,
        "new_native_model":None,
        "never_reuse_Engine_generate_without_currentModel":True,
        "truth_access":False,
    }
    write_json(out/"B-own-review-packet.json",packet,exclusive=True)
    result["arms"]["B"]={
        "candidate_count":1,
        "own_feedback_retrieved":True,
        "own_original_policy_invoked":False,
        "original_engine_revision_status":"NOT_INVOKED_REQUIRES_SEPARATE_PROVIDER_AUTH",
        "ledger_sqlite_sha256":sha_bytes(b_db.read_bytes()),
        "parent_hash":b_parent,
        "diagnostic_sha256":saved["diagnostic_hash"],
        "retrieved_before_review":recovered["retrieval"],
        "revision_packet_sha256":sha_bytes(
            (out/"B-own-review-packet.json").read_bytes()),
        "new_omc":0,"provider_posts":0,
    }
    write_json(out/"summary.json",result,exclusive=True)
    return result


def execute(out, *, env=None, api=None):
    env=os.environ if env is None else env
    identity(env)
    if api is None:
        need(bool(env.get("GH_TOKEN")),"GITHUB_READ_TOKEN_REQUIRED")
        api = GitHub(REPO,Secret(env["GH_TOKEN"],"GITHUB_TOKEN"))
    g2_entries=_fetch(api,run_id=G2_RUN_ID,sha=G2_SHA,
                      artifact_id=G2_ARTIFACT_ID,archive_sha=G2_ARCHIVE_SHA,
                      workflow=G2_WORKFLOW,
                      artifact_name=f"coffee-dm-g2-{G2_RUN_ID}",
                      event="workflow_dispatch")
    b_entries=_fetch(api,run_id=B_RUN_ID,sha=B_SHA,
                     artifact_id=B_ARTIFACT_ID,archive_sha=B_ARCHIVE_SHA,
                     workflow=B_WORKFLOW,
                     artifact_name=f"coffee-b-live-{B_RUN_ID}",
                     event="workflow_dispatch")
    return connect(g2_entries,b_entries,out)


def main(argv=None):
    ap=argparse.ArgumentParser(description="Connect real coffee G2/B G1 to own Ledger ATMS")
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        result=execute(args.out)
        print(json.dumps({
            "status":result["status"],"D":len(result["arms"]["D"]["candidates"]),
            "M":len(result["arms"]["M"]["candidates"]),
            "B":result["arms"]["B"]["original_engine_revision_status"],
            "provider_posts":0,"new_omc":0,"reserved_truth_access":False
        },sort_keys=True))
        return 0
    except (ArenaError, ValueError, TypeError, KeyError, OSError, ImportError,
            zipfile.BadZipFile) as exc:
        print(json.dumps({"status":"STOPPED_NO_EXTERNAL_CONSUMPTION",
                          "reason":str(exc) if isinstance(exc,ArenaError)
                                   else "FEEDBACK_INTEGRATION_ERROR"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
