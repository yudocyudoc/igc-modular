"""Project 12 real D/M own-ledger decisions into lock-shaped rows, no seal.

The final 13-slot seal belongs only AFTER authentic B initial/revision and
after any M revision has its own new OMC G2 CSV/receipt. No absent trace is
replaced by a zero, a copy of initial or a fake B row. The existing exact
CT-03 prospective-lock registry/validate_row remain the sole row contract.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_dm_feedback_round import SCHEMA as DM_SCHEMA
from scripts.arena_cafe.ct03_prospective_lock import registry,validate_row
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA="igc-ct03-dm-twelve-lock-ready-rows-no-B/1.0"

def project(dm:dict,d_manifest:dict,m_manifest:dict,revisions:dict):
    require(type(dm) is dict and dm.get("schema")==DM_SCHEMA and
            len(dm.get("rows",[]))==12 and
            dm.get("new_provider_calls")==0 and
            type(revisions) is dict,
            "CT03_DM_LOCK_REQUIRES_ALL_TWELVE_OWN_INITIALS")
    world=dm["world_public_id"]
    expected=registry(d_manifest,m_manifest)
    rows=[]
    seen=set()
    for r in dm["rows"]:
        arm,cid=r["arm"],r["candidate_id"]
        require(arm in ("D","M") and (arm,cid) in expected and
                (arm,cid) not in seen and
                r["parent_hash"]==expected[(arm,cid)]["parent_hash"] and
                r["material_group"]==expected[(arm,cid)]["group"],
                "CT03_DM_LOCK_WRONG_CANDIDATE_OR_PARENT")
        seen.add((arm,cid))
        initial=r["initial"]
        require(initial["status"] in ("PREDICTED","G2_FAILED") and
                initial.get("receipt_sha256") and
                (initial.get("trace_sha256") is not None
                 if initial["status"]=="PREDICTED" else
                 initial.get("trace_sha256") is None and
                 initial.get("forecast") is None),
                "CT03_DM_LOCK_REQUIRES_REAL_INITIAL_OR_FAILED_ATTEMPT")
        raw=r["decision"]
        decision={
            "status":raw["status"],
            "policy":raw["policy"],
            "feedback_hash":raw["feedback_hash"],
            "retrieved_item_id":(r["retrieved_before_policy"]["item_id"]
                                 if r["retrieved_before_policy"] else None),
            "new_model_sha256":None
        }
        if initial["status"]=="G2_FAILED":
            require(raw["status"]=="NOT_EXECUTED" and
                    raw["feedback_hash"] is None and
                    r["retrieved_before_policy"] is None and
                    r["revision_native_manifest"] is None and
                    cid not in revisions and
                    r["final_state"]=="FAILED_INITIAL_NO_OWN_POLICY",
                    "CT03_DM_LOCK_FAILED_INITIAL_CANNOT_INVENT_FEEDBACK")
            final=initial
        elif raw["status"]=="REVISED":
            require(arm=="M" and cid in revisions and
                    r["revision_native_manifest"] is not None,
                    "CT03_DM_LOCK_REVISED_M_MISSING_PHYSICAL_OUTCOME")
            final=revisions[cid]
            native=r["revision_native_manifest"]
            require(type(final) is dict and
                    set(final)=={"status","native_sha256","trace_sha256",
                                 "receipt_sha256","forecast"} and
                    final["status"] in ("PREDICTED","G2_FAILED") and
                    final["native_sha256"]==native["native_modelica_sha256"] and
                    final["native_sha256"]!=initial["native_sha256"],
                    "CT03_DM_LOCK_REVISED_NATIVE_OR_G2_RESULT_MISMATCH")
            # The separate revision OMC runner must authenticate source and
            # receipt; no in-process signatures/phantom truth claimed here.
            decision["new_model_sha256"]=native["native_modelica_sha256"]
        else:
            require(raw["status"] in ("RATIFIED","ABSTAINED") and
                    r["revision_native_manifest"] is None,
                    "CT03_DM_LOCK_UNREVISED_CANNOT_HAVE_NEW_NATIVE")
            final=initial
            require(cid not in revisions,
                    "CT03_DM_LOCK_UNAUTHORIZED_EXTRA_REVISION_OUTCOME")
        row={
            "arm":arm,"candidate_id":cid,"parent_hash":r["parent_hash"],
            "material_group":r["material_group"],"initial":initial,
            "decision":decision,"final":final
        }
        validate_row(row,expected,world)
        rows.append(row)
    require(len(seen)==12 and
            sum(x["arm"]=="D" for x in rows)==6 and
            sum(x["arm"]=="M" for x in rows)==6 and
            set(revisions)=={
                r["candidate_id"] for r in dm["rows"]
                if r["arm"]=="M" and r["decision"]["status"]=="REVISED"
            },
            "CT03_DM_LOCK_WRONG_TWELVE_OR_EXTRA_REVISIONS")
    return {
        "schema":SCHEMA,
        "status":"TWELVE_D_M_LOCK_ROWS_VALID_B_NOT_INCLUDED_NOT_SEALED",
        "world_public_id":world,
        "source_snapshot_hash":dm["source_snapshot_hash"],
        "dm_feedback_sha256":digest(dm),
        "candidate_count":12,
        "D_count":6,"M_count":6,
        "M_physical_revised_count":len(revisions),
        "B_status":"REQUIRES_SEPARATE_REAL_ORIGINAL_B_EVIDENCE",
        "reserved_world_truth_read":False,
        "new_omc_by_projection":0,
        "new_provider_calls":0,
        "rows":rows,
    }

def project_from_revision_report(dm,d_manifest,m_manifest,report):
    """Bind actual one-attempt M physical receipt hashes before 12-slot output.

    Do not manually extract a naked outcomes dict and lose attempt provenance.
    The CI tests use synthetic JSON; the live workflow must still verify its
    origin artifact before invoking this routine.
    """
    from scripts.arena_cafe.ct03_m_revision_physical import SCHEMA as R_SCHEMA
    require(type(report) is dict and report.get("schema")==R_SCHEMA and
            report.get("status")==
              "ORIGINAL_M_REVISIONS_CHECKED_NOT_PROSPECTIVELY_SCORED" and
            report.get("world_public_id")==dm["world_public_id"] and
            report.get("source_snapshot_hash")==dm["source_snapshot_hash"] and
            report.get("dm_feedback_sha256")==digest(dm) and
            report.get("reserved_truth_read") is False and
            report.get("provider_posts")==0 and
            type(report.get("outcomes")) is dict and
            type(report.get("receipts")) is dict and
            set(report["outcomes"])==set(report["receipts"]) and
            report.get("revised_count")==len(report["outcomes"])<=6 and
            report.get("predicted_count")+report.get("failed_count")==
                report["revised_count"],
            "CT03_DM_LOCK_REVISION_REPORT_SCOPE_OR_ACCOUNTING_MISMATCH")
    for cid,state in report["outcomes"].items():
        receipt=report["receipts"][cid]
        require(type(receipt) is dict and receipt.get("arm")=="M" and
                receipt.get("candidate_id")==cid and
                receipt.get("run_id")==report["run_id"] and
                receipt.get("git_sha")==report["git_sha"] and
                digest(receipt)==state.get("receipt_sha256") and
                ((state["status"]=="PREDICTED" and
                  receipt.get("failure") is None and
                  receipt.get("csv_sha256")==state["trace_sha256"])
                 or (state["status"]=="G2_FAILED" and
                     receipt.get("failure") and
                     state["trace_sha256"] is None and
                     state["forecast"] is None)),
                "CT03_DM_LOCK_REVISION_ATTEMPT_RECEIPT_MISMATCH")
    return project(dm,d_manifest,m_manifest,report["outcomes"])


def main():
    p=argparse.ArgumentParser()
    for key in ("dm-feedback","d-manifest","m-manifest","revision-outcomes","out"):
        p.add_argument("--"+key,required=True,type=Path)
    a=p.parse_args()
    require(not a.out.exists(),"CT03_DM_LOCK_PROJECTION_REFUSE_OVERWRITE")
    def read(x):return json.loads(x.read_text(encoding="utf-8"))
    dm=read(a.dm_feedback)
    d,m=read(a.d_manifest),read(a.m_manifest)
    revisions=read(a.revision_outcomes)
    report=(project_from_revision_report(dm,d,m,revisions)
            if revisions.get("schema")==
                "igc-ct03-m-revisions-original-physical-outcomes/1.0"
            else project(dm,d,m,revisions))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes(canonical(report)+b"\n")
    print(json.dumps({"status":report["status"],"rows":12,
                      "new_omc":0,"provider_posts":0}))

if __name__=="__main__":
    main()
