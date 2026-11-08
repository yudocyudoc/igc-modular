"""CT-03 M: turn each ORIGINAL own_policy revision into one authentic OMC outcome.

This adapter does not invoke OMC, Buffalo or the world evaluator. It consumes
the script+Modelica already rendered by ct03_m_revision_prepare, the native
solver CSV/log and the single-attempt record. A corrupt parent/model/script is
an integrity STOP. A genuine failed numerical attempt is G2_FAILED without a
forecast, not a retry or a fabricated value. All six parent slots persist.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct_feedback_bridge import require
from scripts.arena_cafe.ct03_m_construction_diagnostic import sha_bytes,_sample
from scripts.arena_cafe.ct03_dm_initial_batch import _m_material_conservation
from scripts.arena_cafe.ct03_reuse_ct02 import _points
from scripts.arena_cafe.ct03_m_revision_prepare import SCHEMA as NATIVE_SCHEMA
from scripts.arena_cafe.ct03_dm_feedback_round import SCHEMA as FEEDBACK_SCHEMA

SCHEMA="igc-ct03-m-revisions-original-physical-outcomes/1.0"
SHA=re.compile(r"[0-9a-f]{40}\Z")

def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def _revdir(dm_root, index):
    return Path(dm_root)/"producer-12"/"revisions"/("M"+str(index))

def _integrity(row,dir,manifest,original):
    planned=row["revision_native_manifest"]
    require(row["arm"]=="M" and row["decision"]["status"]=="REVISED" and
            type(planned) is dict and planned["schema"]==NATIVE_SCHEMA and
            planned["status"]=="M2_REVISION_RENDERED_NOT_SOLVED_NOT_SCORED" and
            planned==_read(dir/"manifest.json") and
            planned["parent_full_ast_sha256"]==row["parent_hash"] and
            planned["parent_canonical_topology"]==row["candidate_id"] and
            planned["material_projection_group"]==row["material_group"] and
            planned["feedback_hash"]==row["decision"]["feedback_hash"] and
            planned["planned_new_omc"]==1 and planned["executed_new_omc"]==0 and
            planned["provider_calls"]==0 and
            planned["reserved_truth_read"] is False and
            original["full_ast_sha256"]==row["parent_hash"] and
            original["canonical_sha256"]==row["candidate_id"],
            "CT03_M_REVISION_PARENT_OR_POLICY_INTEGRITY_STOP")
    mo=dir/"revision.mo"
    mos=dir/"simulate.mos"
    require(sha_bytes(mo.read_bytes())==planned["native_modelica_sha256"] and
            sha_bytes(mos.read_bytes())==planned["simulate_script_sha256"],
            "CT03_M_REVISION_NATIVE_SOURCE_OR_SCRIPT_TAMPERED")
    cls=("CT03MR_"+row["candidate_id"][:12]+"_"+
         planned["revised_full_ast_sha256"][7:15])
    model="ArenaCT03MR."+cls
    script=mos.read_text(encoding="utf-8")
    require(script.count("simulate(")==1 and
            script.count("checkModel(")==1 and
            'loadFile("revision.mo");' in script and
            "checkModel("+model+");" in script and
            'simulate('+model+',startTime=0,stopTime=8,numberOfIntervals=64,'
            'method="euler",outputFormat="csv",fileNamePrefix="mrev");' in script and
            'loadFile("/repo/src/modelica/IGCMolecules.mo");' in script and
            'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");' in script,
            "CT03_M_REVISION_COMMAND_DRIFT")
    return model

def assess_one(row,dm_root,original,*,run_id,git_sha):
    dir=_revdir(dm_root,row["index"])
    model=_integrity(row,dir,row["revision_native_manifest"],original)
    log=dir/"mrev-omc.log"
    record=dir/"omc-exit.json"
    require(log.is_file() and log.stat().st_size>0 and record.is_file(),
            "CT03_M_REVISION_REAL_ATTEMPT_LOG_AND_EXIT_REQUIRED")
    meta=_read(record)
    require(type(meta) is dict and set(meta)=={
        "arm","index","run_id","git_sha","exit_code","attempted"
    } and meta["arm"]=="M" and meta["index"]==row["index"] and
            meta["run_id"]==run_id and meta["git_sha"]==git_sha and
            meta["attempted"] is True and
            type(meta["exit_code"]) is int and 0<=meta["exit_code"]<=255,
            "CT03_M_REVISION_EXACT_ATTEMPT_METADATA_MISMATCH")
    text=log.read_text(encoding="utf-8",errors="replace")
    logsha=sha_bytes(log.read_bytes())
    csv=dir/"mrev_res.csv"
    parentsha=row["revision_native_manifest"]["native_modelica_sha256"]
    if meta["exit_code"]==0:
        solver_ok=("OpenModelica 1.26.5" in text and
                   "Check of "+model+" completed successfully" in text and
                   "LOG_SUCCESS" in text and "mrev_res.csv" in text and
                   csv.is_file())
        if not solver_ok:
            # OMC occasionally exits zero while failing the model or leaving
            # no CSV. This is a failed candidate, NOT an executable receipt.
            failure="G2_SOLVER_LOG_OR_TRACE_FAILED"
        else:
            try:
                pts,n=_points(csv,"deliveredTotal")
                cuts,c=_sample(csv.read_bytes(),"deliveredTotal")
                require(c==n and set(cuts)=={0.,1.,2.,4.},
                        "CT03_M_REVISION_CONSTRUCTION_CUTS_MISSING")
                mass=_m_material_conservation(csv,original)
                require(mass["count"]==n,
                        "CT03_M_REVISION_MATERIAL_ROW_COUNT_MISMATCH")
            except ValueError as exc:
                failure=str(exc)
            else:
                state={
                    "status":"PREDICTED",
                    "native_sha256":parentsha,
                    "trace_sha256":sha_bytes(csv.read_bytes()),
                    "receipt_sha256":None,
                    "forecast":[{"time":t,"delivered":pts[t]} for t in (6,8)],
                }
                record_receipt={
                    "schema":SCHEMA,"arm":"M","candidate_id":row["candidate_id"],
                    "parent_hash":row["parent_hash"],"run_id":run_id,"git_sha":git_sha,
                    "exit_code":0,"failure":None,"solver_log_sha256":logsha,
                    "script_sha256":row["revision_native_manifest"]["simulate_script_sha256"],
                    "csv_sha256":state["trace_sha256"],
                    "native_sha256":parentsha,
                    "model_name":model,"mass_max_residual":mass["max_abs_balance"],
                }
                state["receipt_sha256"]=digest(record_receipt)
                return state,record_receipt
    else:
        failure="OMC_EXIT_NONZERO:"+str(meta["exit_code"])
    receipt={
        "schema":SCHEMA,"arm":"M","candidate_id":row["candidate_id"],
        "parent_hash":row["parent_hash"],"run_id":run_id,"git_sha":git_sha,
        "exit_code":meta["exit_code"],"failure":failure,
        "solver_log_sha256":logsha,
        "script_sha256":row["revision_native_manifest"]["simulate_script_sha256"],
        "csv_sha256":sha_bytes(csv.read_bytes()) if csv.is_file() else None,
        "native_sha256":parentsha,"model_name":model,
        "mass_max_residual":None,
    }
    return {
        "status":"G2_FAILED","native_sha256":parentsha,
        "trace_sha256":None,"receipt_sha256":digest(receipt),
        "forecast":None
    },receipt


def collect(dm,dm_root,m_manifest,*,run_id,git_sha):
    require(type(dm) is dict and dm.get("schema")==FEEDBACK_SCHEMA and
            len(dm.get("rows",[]))==12 and
            type(run_id) is str and run_id.isdigit() and
            type(git_sha) is str and SHA.fullmatch(git_sha) is not None and
            m_manifest.get("candidate_count")==6,
            "CT03_M_REVISION_CASE_OR_RUN_ID_INVALID")
    revisions=[r for r in dm["rows"] if r["arm"]=="M" and
               r["decision"]["status"]=="REVISED"]
    require(len(revisions)<=6 and
            len({r["index"] for r in revisions})==len(revisions) and
            all(0<=r["index"]<6 for r in revisions),
            "CT03_M_REVISION_ONLY_SIX_ORIGINALS")
    attempts_path=Path(dm_root)/"producer-12"/"m-revision-attempts.log"
    expected=[("M"+str(r["index"])+" attempted; GitHub run "+run_id+
               "; code "+git_sha) for r in revisions]
    if revisions:
        require(attempts_path.is_file() and
                attempts_path.read_text(encoding="utf-8").splitlines()==expected,
                "CT03_M_REVISION_EXACTLY_ONE_ATTEMPT_PER_SELECTED_PARENT")
    else:
        require(not attempts_path.exists(),
                "CT03_M_REVISION_UNAUTHORIZED_ATTEMPT_LOG")
    out={}
    receipts={}
    for r in revisions:
        original=m_manifest["candidates"][r["index"]]
        state,receipt=assess_one(r,dm_root,original,
                                 run_id=run_id,git_sha=git_sha)
        require(r["candidate_id"] not in out,
                "CT03_M_REVISION_DUPLICATE_PARENT")
        out[r["candidate_id"]]=state
        receipts[r["candidate_id"]]=receipt
    return {
        "schema":SCHEMA,
        "status":"ORIGINAL_M_REVISIONS_CHECKED_NOT_PROSPECTIVELY_SCORED",
        "world_public_id":dm["world_public_id"],
        "source_snapshot_hash":dm["source_snapshot_hash"],
        "dm_feedback_sha256":digest(dm),
        "run_id":run_id,"git_sha":git_sha,
        "revised_count":len(revisions),
        "predicted_count":sum(x["status"]=="PREDICTED" for x in out.values()),
        "failed_count":sum(x["status"]=="G2_FAILED" for x in out.values()),
        "outcomes":out,"receipts":receipts,
        "new_omc_by_verifier":0,"provider_posts":0,"reserved_truth_read":False
    }

def main():
    p=argparse.ArgumentParser()
    for name in ("dm-feedback","dm-root","m-manifest","out"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--git-sha",required=True)
    args=p.parse_args()
    require(not args.out.exists(),"CT03_M_REVISION_OUTCOMES_REFUSE_OVERWRITE")
    d=lambda path:json.loads(path.read_text(encoding="utf-8"))
    result=collect(d(args.dm_feedback),args.dm_root,d(args.m_manifest),
                   run_id=args.run_id,git_sha=args.git_sha)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(result)+b"\n")
    print(json.dumps({"status":result["status"],"revised":result["revised_count"],
                      "failed":result["failed_count"],"new_omc":0,"provider":0}))

if __name__=="__main__":
    main()
