"""CT03 B: append a real own G2/G3 consequence to the existing G1 ledger.

Read only the initial Buffalo native, four public construction cuts and its
own physical attempt. Replay the physical verifier; then append a new
diagnostic revision in the SAME B parent-scoped F1a/ATMS event stream.
Original G1 history remains retrievable. No provider, solver or heldout data.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timedelta
import json
import shutil
import sqlite3
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_b_own_feedback import validate as validate_initial, SCHEMA as OWN_SCHEMA
from scripts.arena_cafe.ct03_b_physical_outcome import collect,STATUS as FAILED
from scripts.arena_cafe.ct03_b_physical_result import SCHEMA as SUCCESS
from scripts.arena_cafe.ct03_dm_feedback_round import construction_samples
from scripts.arena_cafe.ct03_public import validate_construction
from scripts.arena_cafe.ct_feedback_bridge import (
    make_context,b_review_envelope,recover_feedback,require,
    _ids,_ledger,_parent_scope,_utc
)

SCHEMA="igc-ct03-b-physical-consequence-own-ledger-revision/1.0"
CUTS=(0,1,2,4)

def build(*,original,receipt,construction,g1_dir,initial_plan,physical,
          physical_root,recorded_at,out):
    out,g1_dir,physical_root=Path(out),Path(g1_dir),Path(physical_root)
    require(not out.exists(),"CT03_B_PHYSICAL_FEEDBACK_REFUSE_OVERWRITE")
    ctx=validate_initial(original,receipt,construction)
    parent=receipt["result_sha256"]
    report=json.loads((g1_dir/"status.json").read_text(encoding="utf-8"))
    g1=json.loads((g1_dir/"own-g1-diagnostic.json").read_text(encoding="utf-8"))
    initial_packet=json.loads((g1_dir/"own-revision-packet.json").read_text(encoding="utf-8"))
    require(report.get("schema")==OWN_SCHEMA and
            report.get("parent_native_sha256")==parent and
            report.get("world_public_id")==ctx["world"] and
            report.get("source_snapshot_hash")==ctx["source_hash"] and
            report.get("own_diagnostic_sha256")==digest(g1) and
            report.get("revision_packet_sha256")==digest(initial_packet) and
            initial_plan.get("round_kind")=="initial" and
            initial_plan.get("native_result_sha256")==parent and
            initial_plan.get("original_G1_feedback_sha256")==digest(report) and
            initial_plan.get("status")=="B_NATIVE_PHYSICAL_PLANNED_NO_OMC" and
            initial_plan.get("world_public_id")==ctx["world"] and
            initial_plan.get("source_snapshot_hash")==ctx["source_hash"],
            "CT03_B_PHYSICAL_FEEDBACK_G1_LINEAGE_OR_EXECUTABLE_PLAN_MISMATCH")
    require(type(physical) is dict and
            physical.get("status") in
            ("B_ORIGINAL_NATIVE_PHYSICAL_CSV_CONFORMING_NOT_HELDOUT",FAILED) and
            physical.get("parent_native_sha256")==parent and
            physical.get("world_public_id")==ctx["world"] and
            physical.get("source_snapshot_hash")==ctx["source_hash"] and
            physical.get("reserved_truth_read") is False and
            type(physical.get("github_code_sha")) is str and
            type(physical.get("github_run_id")) is str,
            "CT03_B_PHYSICAL_FEEDBACK_REAL_OUTCOME_REQUIRED")
    replay=collect(native=original,receipt=receipt,plan=initial_plan,
                   root=physical_root,github_sha=physical["github_code_sha"],
                   github_run_id=physical["github_run_id"])
    require(replay==physical,
            "CT03_B_PHYSICAL_FEEDBACK_OUTCOME_BYTES_OR_STATUS_CHANGED")
    visible=validate_construction(ctx,construction)
    observed={int(o["time"]):o["delivered"] for o in visible}
    diag={
        "arm":"B","condition":"C0","source_hash":ctx["source_hash"],
        "parent_hash":parent,"own_evidence_only":True,
        "no_future_truth":True,"native_model_sha256":parent,
        "native_provider_receipt_sha256":digest(receipt),
        "original_G1_diagnostic_sha256":digest(g1),
        "G1_status":report["G1_status"],
        "own_physical_outcome_sha256":digest(physical),
        "own_physical_status":physical["status"],
        "scope":"CONSTRUCTION_ONLY_0_1_2_4_NO_RESERVED_TRUTH",
    }
    if physical["status"]==FAILED:
        diag.update({
            "evidence":"G2","observations":[],
            "trace_sha256":None,
            "attempt_record_sha256":physical["attempt_record_sha256"],
            "physical_failure_class":physical["failure_class"],
            "physical_failure_reason":physical["failure_reason"],
            "no_valid_trajectory_or_forecast":True
        })
    else:
        points=construction_samples(
            physical_root/"b-original_res.csv",
            initial_plan["observation_operator"]["modelica_csv_column"])
        diag.update({
            "evidence":"G3","trace_sha256":physical["csv_sha256"],
            "observations":[
                {"time":t,"residual":points[t]-observed[t]} for t in CUTS
            ],
            "own_construction_predicted":[
                {"time":t,"delivered":points[t]} for t in CUTS
            ],
            "max_abs_material_residual":physical["max_abs_material_residual"],
            "numerical_roundoff_not_sensor_error":True
        })
    timestamp=_utc(recorded_at)
    source_db=g1_dir/"b-own-feedback-ledger.sqlite"
    require(source_db.is_file(),"CT03_B_PHYSICAL_FEEDBACK_ORIGINAL_LEDGER_REQUIRED")
    old=recover_feedback(source_db,ctx,parent_hash=parent,as_known_at=timestamp)
    require(old["diagnostic"]==g1 and old["diagnostic_hash"]==digest(g1) and
            old["retrieval"]["item_id"]==report["retrieved_before_policy"]["item_id"],
            "CT03_B_PHYSICAL_FEEDBACK_G1_NOT_SUPPORTED_AT_REVISION_TIME")
    out.mkdir(parents=True,exist_ok=False)
    db=out/"b-own-feedback-ledger.sqlite"
    # Backup rather than copy WAL files: preserve immutable G1 source and
    # reproduce its append-only revisions in the continued ledger.
    with sqlite3.connect(str(source_db)) as src,sqlite3.connect(str(db)) as dst:
        src.backup(dst)
    scope=_parent_scope(ctx,parent)
    ids=_ids(scope)
    ledger=_ledger(db)
    own={
        "kind":"assumption","active":True,"scope":scope,
        "source_hash":ctx["source_hash"],"parent_hash":parent,
        "diagnostic_hash":digest(diag),"diagnostic":diag,
        "supersedes_diagnostic_sha256":digest(g1),
        "assumption_type":"OWN_PHYSICAL_FEEDBACK_WITH_VERIFIED_PROVENANCE_NOT_CAUSAL_TRUTH"
    }
    knowledge={
        "kind":"knowledge","active":True,"scope":scope,
        "node_id":ids["feedback"],"source_id":ids["diagnostic"],
        "title":"Own feedback diagnostic B",
        "text":"Original G1 followed by same-parent physical consequence",
        "item_type":"OWN_FEEDBACK","epistemic_status":"CONSTRUCTION_ONLY",
        "source_revision":2,"diagnostic_hash":digest(diag),
        "parent_hash":parent
    }
    for role,typ,payload in (
        ("diagnostic","ATMSNode",own),("feedback","KnowledgeItem",knowledge)
    ):
        ledger.append_revision(
            entity_id=ids[role],entity_type=typ,case_id=scope["case_id"],
            actor_id="ct03-b-physical-own-feedback",
            idempotency_key=ids[role]+":physical:"+digest(physical),
            payload=payload,recorded_at=timestamp,created_at=timestamp,
            access_policy="lane:B")
    phase=b_review_envelope(
        db,ctx,original_native=original,authenticated_receipt=receipt,
        as_known_at=(datetime.fromisoformat(timestamp)+
                     timedelta(seconds=1)).isoformat())
    require(phase["status"]==
            "READY_NOT_SENT_RECEIPT_REQUIRES_EXTERNAL_BYTE_VERIFICATION" and
            phase["own_feedback"]==diag and
            phase["retrieved_before_policy"]["item_id"]==
                report["retrieved_before_policy"]["item_id"],
            "CT03_B_PHYSICAL_FEEDBACK_NOT_RETRIEVED_BEFORE_REVIEW")
    packet=phase["revision_feedback_packet"]
    feedback={
        **report,"status":"B_OWN_G1_AND_PHYSICAL_RETRIEVED_FOR_REVISION_NOT_SENT",
        "own_diagnostic_sha256":digest(diag),
        "retrieved_before_policy":phase["retrieved_before_policy"],
        "revision_packet_sha256":digest(packet),
        "revision_packet_status":"PREPARED_NOT_SENT",
        "physical_B_G2_or_G3":diag["evidence"],
        "physical_outcome_sha256":digest(physical),
        "previous_G1_diagnostic_sha256":digest(g1),
        "heldout_observations_read":False,"cross_arm_feedback_read":False
    }
    (out/"own-physical-diagnostic.json").write_bytes(canonical(diag)+b"\n")
    (out/"own-revision-packet.json").write_bytes(canonical(packet)+b"\n")
    (out/"status.json").write_bytes(canonical(feedback)+b"\n")
    result={
        "schema":SCHEMA,
        "status":"B_PHYSICAL_FEEDBACK_RETRIEVED_BEFORE_SECOND_DECISION_NOT_SENT",
        "world_public_id":ctx["world"],"source_snapshot_hash":ctx["source_hash"],
        "parent_native_sha256":parent,
        "original_G1_feedback_sha256":digest(report),
        "physical_outcome_sha256":digest(physical),
        "updated_feedback_sha256":digest(feedback),
        "revision_packet_sha256":digest(packet),
        "own_diagnostic_sha256":digest(diag),
        "own_gate":diag["evidence"],
        "construction_residual_count":len(diag["observations"]),
        "ledger_carries_original_G1_cut":True,
        "provider_calls":0,"new_omc":0,
        "reserved_truth_read":False
    }
    (out/"continuation.json").write_bytes(canonical(result)+b"\n")
    return result

def main():
    p=argparse.ArgumentParser()
    for name in ("native","receipt","construction","g1-dir","initial-plan",
                 "physical","physical-root","out"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--recorded-at",required=True)
    a=p.parse_args()
    def read(path):return json.loads(path.read_text(encoding="utf-8"))
    result=build(original=read(a.native),receipt=read(a.receipt),
                 construction=read(a.construction),g1_dir=a.g1_dir,
                 initial_plan=read(a.initial_plan),physical=read(a.physical),
                 physical_root=a.physical_root,
                 recorded_at=a.recorded_at,out=a.out)
    print(json.dumps({"status":result["status"],
                      "own_gate":result["own_gate"],"omc":0,"provider":0}))

if __name__=="__main__":
    main()
