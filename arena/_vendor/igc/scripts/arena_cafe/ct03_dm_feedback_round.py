"""CT-03 D/M native initial -> own construction feedback -> ledger -> policies.

Called AFTER all twelve initial native trajectories are authenticated at the
runner boundary (D0/M0 reused from exact CT02 run; D1..D5 and M1..M5 run by
CT03). No provider, OMC, world secrets or other-arm feedback.
It creates its OWN construction-only residuals using only t0/t1/t2/t4.
D retains six original structures (D2 inapplicable); M invokes original
M2 own_policy once PER full original AST, and renders revisions only if chosen.
Revised M requires a separate physical OMC before the 13-slot lock can be made.

Missing physical output is NOT a synthetic zero or silent ratification.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timedelta
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_reuse_ct02 import verify_native_dir,_points
from scripts.arena_cafe.ct03_dm_initial_batch import SCHEMA as PLAN_SCHEMA,RESULT as ONE_SCHEMA
from scripts.arena_cafe.ct03_m_construction_diagnostic import _sample,sha_bytes
from scripts.arena_cafe.ct03_public import validate_construction
from scripts.arena_cafe.ct_feedback_bridge import (
    make_context,record_feedback,own_m_decision,d_fixed_decision,
    persist_disposition,require
)
from scripts.arena_cafe.ct03_m_revision_prepare import prepare_revision

SCHEMA="igc-ct03-dm-own-construction-feedback-and-original-policy/1.0"
CUTS=(0,1,2,4)

def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def construction_samples(trace:Path,column:str):
    with trace.open(encoding="utf-8-sig",newline="") as file:
        reader=csv.DictReader(file)
        require(reader.fieldnames is not None and
                reader.fieldnames.count("time")==1 and
                reader.fieldnames.count(column)==1,
                "CT03_DM_FEEDBACK_AMBIGUOUS_NATIVE_OUTPUT_COLUMN")
        found={}
        prev_t=-1.0
        for record in reader:
            t,y=float(record["time"]),float(record[column])
            require(math.isfinite(t) and math.isfinite(y) and t>=prev_t-1e-9
                    and 0<=t<=8+1e-8 and -1e-8<=y<=3.4+1e-5,
                    "CT03_DM_FEEDBACK_INVALID_NATIVE_TRACE")
            prev_t=t
            for cut in CUTS:
                if abs(t-cut)<1e-8:
                    require(cut not in found or abs(found[cut]-y)<1e-7,
                            "CT03_DM_FEEDBACK_DUPLICATE_EVENT_DISAGREES")
                    found[cut]=y
    require(set(found)==set(CUTS),"CT03_DM_FEEDBACK_PUBLIC_CUTS_MISSING")
    return found

def _validate_frozen_initials(ten_root,ct02_root,reuse):
    from scripts.arena_cafe.ct03_dm_initial_batch import SCHEMA as PLAN
    ten_root,ct02_root=Path(ten_root),Path(ct02_root)
    plan=_load(ten_root/"plan.json")
    d,m=_load(ten_root/"D/manifest.json"),_load(ten_root/"M/manifest.json")
    require(plan["schema"]==PLAN and len(plan["rows"])==10 and
            plan["new_omc_max_this_step"]==10 and
            plan["reused_initial_report_sha256"]==digest(reuse),
            "CT03_DM_FEEDBACK_TEN_PHYSICAL_PLAN_MISMATCH")
    actual_reuse=verify_native_dir(ct02_root,d,m,fresh_root=ten_root)
    require(actual_reuse==reuse,
            "CT03_DM_FEEDBACK_AUTHENTIC_CT02_REUSE_CHANGED")
    records={}
    for arm,manifest in (("D",d),("M",m)):
        for index,candidate in enumerate(manifest["candidates"]):
            cid=candidate["id"] if arm=="D" else candidate["canonical_sha256"]
            parent=(candidate["structure_hash"] if arm=="D"
                    else candidate["full_ast_sha256"])
            if index==0:
                it=next(x for x in reuse["items"] if x["arm"]==arm)
                require(it["candidate_id"]==cid and
                        (it["original_full_ast_sha256"]==parent
                         if arm=="M" else True),
                        "CT03_DM_FEEDBACK_REUSED_PARENT_CHANGED")
                trace=ct02_root/("d00_res.csv" if arm=="D" else "m00_res.csv")
                native=it["model_sha256"]
                csvsha=it["trace_sha256"]
                recsha=it["receipt_sha256"]
                prediction=it["forecast"]
                col="delivered" if arm=="D" else "deliveredTotal"
            else:
                planned=next(x for x in plan["rows"]
                             if x["arm"]==arm and x["index"]==index)
                prefix=candidate["csv_prefix"]
                trace=ten_root/arm/(prefix+"_res.csv")
                receipt=ten_root/arm/(prefix+"-result.json")
                require(receipt.is_file(),
                        "CT03_DM_FEEDBACK_MISSING_REAL_INITIAL_RUN:"+
                        arm+str(index))
                result=_load(receipt)
                require(result.get("schema")==ONE_SCHEMA and
                        result.get("arm")==arm and result.get("index")==index and
                        result.get("candidate_id")==planned["candidate_id"]==cid and
                        result.get("parent_hash")==planned["parent_hash"]==parent and
                        result.get("model_sha256")==planned["model_sha256"] and
                        result.get("script_sha256")==planned["script_sha256"] and
                        result.get("run_id") and result.get("git_sha") and
                        result.get("solver_log_sha256")==
                          sha_bytes((ten_root/arm/(prefix+"-omc.log")).read_bytes()),
                        "CT03_DM_FEEDBACK_NATIVE_RESULT_PROVENANCE_MISMATCH")
                if result.get("status")=="G2_FAILED_NATIVE_ATTEMPT_NO_FORECAST":
                    require(result.get("trace_sha256") is None and
                            result.get("forecast") is None and
                            result.get("not_a_synthetic_zero") is True and
                            result.get("attempt_log_entry")==
                              arm+str(index)+" attempted; GitHub run "+
                                result["run_id"]+"; code "+result["git_sha"],
                            "CT03_DM_FEEDBACK_FAILED_ATTEMPT_NOT_AUTHENTIC")
                    initial={"status":"G2_FAILED",
                             "native_sha256":planned["model_sha256"],
                             "trace_sha256":None,"receipt_sha256":digest(result),
                             "forecast":None}
                    records[(arm,index)]={
                        "arm":arm,"index":index,"candidate_id":cid,
                        "parent_hash":parent,
                        "material_group":(candidate["structure_hash"] if arm=="D"
                              else candidate["material_only_projection_sha256"]),
                        "initial":initial,
                        "trace":None,"column":planned["output_column"],
                        "parent_graph":candidate.get("original_ast"),
                        "parent":candidate,"manifest":manifest,
                        "failed_reason":result["failure_class"]
                    }
                    continue
                require(result.get("status")==
                            "ONE_REAL_ORIGINAL_INITIAL_NATIVE_CHECKED_NOT_SCORED" and
                        trace.is_file() and
                        result.get("csv_sha256")==sha_bytes(trace.read_bytes()) and
                        result.get("construction_residuals_not_yet_built") is True and
                        result.get("feedback_or_revision_executed") is False,
                        "CT03_DM_FEEDBACK_NATIVE_RESULT_PROVENANCE_MISMATCH")
                pts,n=_points(trace,planned["output_column"])
                require(result["forecast"]==
                        [{"time":t,"delivered":pts[t]} for t in (6,8)],
                        "CT03_DM_FEEDBACK_FORECAST_CHANGED")
                native=result["model_sha256"]
                csvsha=result["csv_sha256"]
                recsha=digest(result)
                prediction=result["forecast"]
                col=planned["output_column"]
            require(sha_bytes(trace.read_bytes())==csvsha,
                    "CT03_DM_FEEDBACK_OWN_NATIVE_CSV_TAMPERED")
            records[(arm,index)]={
                "arm":arm,"index":index,"candidate_id":cid,
                "parent_hash":parent,
                "material_group":(candidate["structure_hash"] if arm=="D"
                                  else candidate["material_only_projection_sha256"]),
                "initial":{"status":"PREDICTED","native_sha256":native,
                           "trace_sha256":csvsha,"receipt_sha256":recsha,
                           "forecast":prediction},
                "trace":trace,"column":col,
                "parent_graph":candidate.get("original_ast"),
                "parent":candidate,"manifest":manifest
            }
    require(len(records)==12,
            "CT03_DM_FEEDBACK_ALL_TWELVE_ORIGINAL_INITIALS_REQUIRED")
    # Every newly consumed OMC route must have one prior runner attempt;
    # two D0/M0 slots are explicitly reused and never appear here.
    attempts=(ten_root/"attempts.log").read_text(encoding="utf-8").splitlines()
    expected_attempts=[]
    ids=set()
    for row in plan["rows"]:
        prefix=row["csv_file"].split("/")[-1].removesuffix("_res.csv")
        result=_load(ten_root/row["arm"]/(prefix+"-result.json"))
        ids.add((result["run_id"],result["git_sha"]))
        expected_attempts.append(
            row["arm"]+str(row["index"])+" attempted; GitHub run "+
            result["run_id"]+"; code "+result["git_sha"])
    require(len(ids)==1 and attempts==expected_attempts,
            "CT03_DM_FEEDBACK_TEN_CONSUMED_ATTEMPTS_NOT_PROVEN")
    return records

def build(*,ten_root:Path,ct02_root:Path,reuse:dict,
          construction:dict,recorded_at:str,out:Path):
    """All expected inputs checked before beginning irreversible ledger writes."""
    out=Path(out)
    require(not out.exists(),"CT03_DM_FEEDBACK_REFUSE_OVERWRITE")
    root=Path(ten_root)
    records=_validate_frozen_initials(root,ct02_root,reuse)
    time=datetime.fromisoformat(recorded_at.replace("Z","+00:00"))
    require(time.tzinfo is not None and time.utcoffset() is not None,
            "CT03_DM_FEEDBACK_UTC_TIME_REQUIRED")
    world=construction.get("world_public_id")
    source=construction.get("source_snapshot_hash")
    ctx0=make_context(experiment="CT03",world=world,round_id="R0",
                      arm="M",condition="C0",source_hash=source)
    visible=validate_construction(ctx0,construction)
    obs={int(x["time"]):float(x["delivered"]) for x in visible}
    base=out/"producer-12"
    base.mkdir(parents=True,exist_ok=False)
    db=base/"own-feedback-ledger.sqlite"
    rows=[]
    for arm in ("D","M"):
        for index in range(6):
            item=records[(arm,index)]
            if item["initial"]["status"]=="G2_FAILED":
                rows.append({
                    "arm":arm,"index":index,
                    "candidate_id":item["candidate_id"],
                    "parent_hash":item["parent_hash"],
                    "material_group":item["material_group"],
                    "initial":item["initial"],
                    "own_construction_diagnostic":None,
                    "own_diagnostic_sha256":None,
                    "decision":{
                        "status":"NOT_EXECUTED",
                        "policy":("D-CT03-EXPLICIT-FIXED-SET/1.0" if arm=="D"
                                  else "M-E1-OWN-FEEDBACK-SET/1.0"),
                        "feedback_hash":None,
                        "retrieved_before_policy":None,
                        "new_model_sha256":None,
                    },
                    "retrieved_before_policy":None,
                    "revision_native_manifest":None,
                    "final_state":"FAILED_INITIAL_NO_OWN_POLICY",
                    "failure_reason":item["failed_reason"],
                    "world_private_read":False,
                })
                continue
            ctx=make_context(experiment="CT03",world=world,round_id="R0",
                             arm=arm,condition="C0",source_hash=source)
            samples=construction_samples(item["trace"],item["column"])
            diagnostic={
                "arm":arm,"condition":"C0",
                "source_hash":source,"parent_hash":item["parent_hash"],
                "evidence":"G3","trace_sha256":item["initial"]["trace_sha256"],
                "own_evidence_only":True,"no_future_truth":True,
                "observations":[
                    {"time":t,"residual":samples[t]-obs[t]} for t in CUTS
                ],
                "diagnostic_scope":"CONSTRUCTION_ONLY_NO_RESERVED_TRUTH",
            }
            record_feedback(db,ctx,parent_hash=item["parent_hash"],
                            diagnostic=diagnostic,
                            recorded_at=time.isoformat())
            later=(time+timedelta(seconds=1)).isoformat()
            decision=(d_fixed_decision(db,ctx,parent_hash=item["parent_hash"],
                                       as_known_at=later) if arm=="D" else
                      own_m_decision(db,ctx,
                          parent_graph=item["parent_graph"],as_known_at=later))
            saved=persist_disposition(db,ctx,decision=decision,
                recorded_at=(time+timedelta(seconds=2)).isoformat())
            require(saved["status"]=="DISPOSITION_RECORDED_WITH_OWN_FEEDBACK_SUPPORT",
                    "CT03_DM_FEEDBACK_POLICY_NOT_SUPPORTED_BY_OWN_LEDGER")
            revision=None
            if arm=="M" and decision["status"]=="REVISED":
                dest=base/"revisions"/("M"+str(index))
                revision=prepare_revision(dest,item["manifest"],
                                          item["parent"],decision)
                require(revision["executed_new_omc"]==0,
                        "CT03_DM_FEEDBACK_REVISION_PREEXECUTED")
            row={
                "arm":arm,"index":index,
                "candidate_id":item["candidate_id"],
                "parent_hash":item["parent_hash"],
                "material_group":item["material_group"],
                "initial":item["initial"],
                "own_construction_diagnostic":diagnostic,
                "own_diagnostic_sha256":digest(diagnostic),
                "decision":{k:v for k,v in decision.items()
                            if k not in ("new_model",)},
                "retrieved_before_policy":decision["retrieved_before_policy"],
                "revision_native_manifest":revision,
                "final_state":"AWAITING_M_PHYSICAL_REVISION" if revision else
                              "SAME_NATIVE_INITIAL_BY_OWN_POLICY",
                "world_private_read":False,
            }
            rows.append(row)
    report={
        "schema":SCHEMA,
        "status":"TWELVE_OWN_POLICIES_EXECUTED_SCORES_AND_B_LIVE_STILL_MISSING",
        "world_public_id":world,"source_snapshot_hash":source,
        "construction_sha256":digest(construction),
        "origin_ct02_run":int(reuse["source_github_run_id"]),
        "reused_initial_indices":{"D":[0],"M":[0]},
        "new_initial_indices":{"D":[1,2,3,4,5],"M":[1,2,3,4,5]},
        "rows":rows,
        "D_fixed_count":sum(r["arm"]=="D" and
                             r["decision"]["status"]=="RATIFIED" for r in rows),
        "M_revised_count":sum(r["arm"]=="M" and
                               r["decision"]["status"]=="REVISED" for r in rows),
        "M_ratified_or_abstained_count":sum(r["arm"]=="M" and
                            r["decision"]["status"] in ("RATIFIED","ABSTAINED")
                            for r in rows),
        "failed_initial_count":sum(r["initial"]["status"]=="G2_FAILED"
                                   for r in rows),
        "no_feedback_for_failed_initials":True,
        "new_omc_executed_by_this_module":0,
        "new_provider_calls":0,
        "B_initial_and_revision":"NOT_EXECUTED_BY_THIS_MODULE",
        "ct03_world_scoring":"NOT_PERFORMED",
        "own_feedback_reused_from_ct02":False,
        "reserved_truth_read":False,
    }
    (base/"dm-feedback-report.json").write_bytes(canonical(report)+b"\n")
    return report

def main():
    p=argparse.ArgumentParser()
    for flag in ("ten-root","ct02-root","reuse-report","construction","out"):
        p.add_argument("--"+flag,required=True,type=Path)
    p.add_argument("--recorded-at",required=True)
    a=p.parse_args()
    r=build(ten_root=a.ten_root,ct02_root=a.ct02_root,
        reuse=_load(a.reuse_report),construction=_load(a.construction),
        recorded_at=a.recorded_at,out=a.out)
    print(json.dumps({"status":r["status"],"D":r["D_fixed_count"],
                      "M_revised":r["M_revised_count"],
                      "new_omc":0,"provider_calls":0}))

if __name__=="__main__":
    main()
