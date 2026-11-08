"""CT-03 D/M producer-side initial physical batch: 10 NOT YET RUN.

Exactly five original D + five original M (indices 1..5); D0/M0 are
eligible for reuse from authenticated CT-02. This script plans/checks but
NEVER executes OMC. One plan/script per original full candidate: no model
fitting, topology changes, hidden world, competing arm output, B provider,
ledger replay or synthetic physical receipt.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_d_v01 import verify_csv
from scripts.arena_cafe.ct03_d_prepare import prepare as prepare_d, PROFILE
from scripts.arena_cafe.ct03_m_prepare import prepare as prepare_m
from scripts.arena_cafe.ct03_m_construction_diagnostic import _sample, sha_bytes
from scripts.arena_cafe.ct03_reuse_ct02 import _points, SCHEMA as REUSE, RUN_ID
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA="igc-ct03-dm-ten-initial-native-plan/1.0"
RESULT="igc-ct03-dm-one-original-initial-omc-result/1.0"
IMAGE="openmodelica/openmodelica:v1.26.5-minimal"

def _relative(out):
    require(not out.is_absolute() and ".." not in out.parts and
            len(out.parts)>0, "CT03_DM_RELATIVE_NO_ESCAPE_REQUIRED")
    return out

def _parents(d,m):
    require(d["candidate_count"]==m["candidate_count"]==6 and
            d["source_definition_sha256"]==m["source_definition_sha256"] and
            d["D2"]=="NOT_APPLICABLE_MISSING_RESET_TRIAL" and
            m["material_projection_is_dynamic_equivalence"] is False,
            "CT03_DM_ORIGINAL_SIX_MANIFEST_MISMATCH")

def prepare(out:Path,reuse:dict):
    out=_relative(Path(out))
    require(not out.exists(),"CT03_DM_NO_OVERWRITE")
    require(type(reuse) is dict and reuse.get("schema")==REUSE and
            reuse.get("status")=="TWO_ORIGINAL_INITIAL_CONSEQUENCES_ELIGIBLE_FOR_REUSE" and
            reuse.get("source_github_run_id")==RUN_ID and
            [x["arm"] for x in reuse.get("items",[])]==["D","M"] and
            reuse.get("new_omc")==0 and
            reuse.get("own_feedback_or_decision_reused") is False,
            "CT03_DM_REUSE_ORIGINALS_REQUIRED")
    out.mkdir(parents=True)
    d=prepare_d(out/"D")
    m=prepare_m(out/"M")
    _parents(d,m)
    require(reuse["items"][0]["candidate_id"]==d["candidates"][0]["id"] and
            reuse["items"][1]["candidate_id"]==m["candidates"][0]["canonical_sha256"] and
            reuse["items"][0]["model_sha256"]==d["candidates"][0]["native_modelica_sha256"] and
            reuse["items"][1]["model_sha256"]==m["native_modelica_sha256"],
            "CT03_DM_REUSED_INITIAL_PARENT_OR_MODEL_DRIFT")
    (out/"commands").mkdir()
    rows=[]
    for arm,manifest in (("D",d),("M",m)):
        for index in range(1,6):
            candidate=manifest["candidates"][index]
            prefix=candidate["csv_prefix"]
            model=(candidate["name"] if arm=="D" else
                   "ArenaCT03M."+candidate["class_name"])
            source_path=(out/"D"/(candidate["name"]+".mo") if arm=="D"
                         else out/"M/native.mo")
            require(source_path.exists(),"CT03_DM_ORIGINAL_SOURCE_MISSING")
            model_hash=(candidate["native_modelica_sha256"] if arm=="D"
                        else m["native_modelica_sha256"])
            require(sha_bytes(source_path.read_bytes())==model_hash,
                    "CT03_DM_SOURCE_CHANGED_AFTER_PREPARATION")
            libs=([] if arm=="D" else [
                'loadFile("/repo/src/modelica/IGCMolecules.mo");',
                'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
            ])
            script="\n".join([
                "getVersion();",*libs,
                'loadFile("/repo/'+source_path.as_posix()+'");',
                "checkModel("+model+");","print(getErrorString());",
                "simulate("+model+",startTime=0,stopTime=8,numberOfIntervals=64,"
                'method="euler",outputFormat="csv",fileNamePrefix="' +
                (out/arm/prefix).as_posix()+'");',
                "print(getErrorString());",""
            ])
            require(script.count("simulate(")==1 and
                    script.count("checkModel(")==1,
                    "CT03_DM_ONE_NATIVE_SIMULATION_PER_SCRIPT")
            command=out/"commands"/(arm+str(index)+".mos")
            command.write_text(script,encoding="utf-8",newline="\n")
            rows.append({
                "arm":arm,"index":index,
                "candidate_id":candidate["id"] if arm=="D" else candidate["canonical_sha256"],
                "parent_hash":(candidate["structure_hash"] if arm=="D"
                               else candidate["full_ast_sha256"]),
                "model_name":model,"model_sha256":model_hash,
                "source_file":source_path.as_posix(),
                "script_file":command.as_posix(),
                "script_sha256":sha_bytes(command.read_bytes()),
                "csv_file":(out/arm/(prefix+"_res.csv")).as_posix(),
                "solver_log_file":(out/arm/(prefix+"-omc.log")).as_posix(),
                "output_column":"delivered" if arm=="D" else "deliveredTotal"
            })
    require(len(rows)==10 and
            [x["arm"] for x in rows]==["D"]*5+["M"]*5 and
            [x["index"] for x in rows]==[1,2,3,4,5]*2,
            "CT03_DM_EXACTLY_TEN_NEW_INITIAL_PLANS")
    plan={
        "schema":SCHEMA,"status":"TEN_ORIGINAL_NATIVE_PLANNED_ZERO_NEW_OMC",
        "ct03_not_authorized":True,
        "reused_initial_report_sha256":digest(reuse),
        "reuse_only":["D0","M0"],
        "new_initial_indices":[1,2,3,4,5],
        "candidate_total":12, "new_omc_max_this_step":10,
        "new_omc_executed_by_this_module":0,
        "buffalo_calls":0,"reserved_truth_read":False,
        "world_parameters_read":False,"method":"euler",
        "start_h":0,"stop_h":8,"number_of_intervals":64,
        "image":IMAGE,"rows":rows
    }
    (out/"plan.json").write_bytes(canonical(plan)+b"\n")
    return plan

def _m_material_conservation(csv_path:Path,parent:dict,*,tolerance=0.008):
    """Existing original E1 material stocks, not report/derivative variables.

    The actual original E1 native types expose .waiting for bounded queues
    (preparation, dispatch and optional transit) plus deliveredTotal. This is
    the same boundary and pulse as the verified CT02 original M0. No model
    repair, dynamics change or inferred capacity is introduced.
    """
    stocks=[
        x["id"]+".waiting" for x in parent["original_ast"]["instances"]
        if x["role"] in ("preparation","dispatch","transit")
    ]
    require(len(stocks) in (2,3,4) and
            len(stocks)==len(set(stocks)),
            "CT03_DM_M_ORIGINAL_MATERIAL_STOCK_IDENTITIES_REQUIRED")
    with csv_path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        names=reader.fieldnames
        require(names is not None and
                all(names.count(c)==1 for c in ("time","deliveredTotal",*stocks)),
                "CT03_DM_M_ORIGINAL_MATERIAL_STOCK_CSV_COLUMNS_MISSING")
        count=0
        maximum=0.
        for r in reader:
            t=float(r["time"])
            values=[float(r[c]) for c in stocks]
            delivered=float(r["deliveredTotal"])
            require(math.isfinite(t) and
                    all(math.isfinite(v) for v in (*values,delivered)) and
                    all(v>=-tolerance for v in (*values,delivered)),
                    "CT03_DM_M_NONFINITE_OR_NEGATIVE_MATERIAL")
            arrived=1.7*min(max(t,0),2)
            residual=abs(sum(values)+delivered-arrived)
            maximum=max(maximum,residual)
            require(residual<=tolerance,
                    "CT03_DM_M_ORIGINAL_CONSERVATION_FAILED")
            count+=1
    require(count>=65,"CT03_DM_M_MATERIAL_TRACE_TOO_SHORT")
    return {"status":"ORIGINAL_E1_MASS_BALANCE_PASS_NOT_HELDOUT_G3",
            "max_abs_balance":maximum,"stock_columns":stocks,
            "count":count}


def verify_one(out:Path, *, arm:str, index:int, run_id:str, git_sha:str):
    out=Path(out)
    require(arm in ("D","M") and type(index) is int and index in range(1,6),
            "CT03_DM_NOT_A_NONREUSED_INITIAL")
    require(type(run_id) is str and run_id.isdigit() and
            type(git_sha) is str and len(git_sha)==40 and
            all(c in "0123456789abcdef" for c in git_sha),
            "CT03_DM_REAL_RUN_SHA_OR_ID_REQUIRED")
    plan=json.loads((out/"plan.json").read_text(encoding="utf-8"))
    require(plan["schema"]==SCHEMA and len(plan["rows"])==10 and
            plan["new_omc_max_this_step"]==10 and
            [x["arm"] for x in plan["rows"]]==["D"]*5+["M"]*5,
            "CT03_DM_BATCH_PLAN_DRIFT")
    row=next(x for x in plan["rows"] if x["arm"]==arm and x["index"]==index)
    src=Path(row["source_file"])
    command=Path(row["script_file"])
    csv_path=Path(row["csv_file"])
    log_path=Path(row["solver_log_file"])
    require(sha_bytes(src.read_bytes())==row["model_sha256"] and
            sha_bytes(command.read_bytes())==row["script_sha256"] and
            command.read_text().count("simulate(")==1 and
            "checkModel("+row["model_name"]+");" in command.read_text() and
            'fileNamePrefix="'+(out/arm/(row["csv_file"].split("/")[-1].removesuffix("_res.csv"))).as_posix()+'"' in command.read_text(),
            "CT03_DM_ORIGINAL_SCRIPT_OR_MODEL_TAMPERED")
    require(csv_path.is_file() and log_path.is_file() and
            log_path.stat().st_size>0,
            "CT03_DM_REAL_SOLVER_CSV_AND_LOG_REQUIRED")
    rawlog=log_path.read_text(encoding="utf-8",errors="replace")
    require("OpenModelica 1.26.5" in rawlog and
            "Check of "+row["model_name"]+" completed successfully" in rawlog and
            "LOG_SUCCESS" in rawlog and
            row["csv_file"] in rawlog,
            "CT03_DM_REAL_SOLVER_LOG_MISMATCH")
    points,count=_points(csv_path,row["output_column"])
    if arm=="D":
        manifest=json.loads((out/"D/manifest.json").read_text())
        parent=manifest["candidates"][index]
        require(parent["id"]==row["candidate_id"] and
                parent["structure_hash"]==row["parent_hash"] and
                parent["native_modelica_sha256"]==row["model_sha256"],
                "CT03_DM_D_ORIGINAL_PARENT_DRIFT")
        checked=verify_csv(csv_path,len(parent["structure"]["stocks"]),PROFILE)
        require(checked["status"]=="G2_MASS_BALANCE_PASS_NOT_G3",
                "CT03_DM_D_G2_MATERIAL_CONSERVATION_FAILED")
    else:
        manifest=json.loads((out/"M/manifest.json").read_text())
        parent=manifest["candidates"][index]
        require(parent["canonical_sha256"]==row["candidate_id"] and
                parent["full_ast_sha256"]==row["parent_hash"] and
                manifest["native_modelica_sha256"]==row["model_sha256"],
                "CT03_DM_M_FULL_PARENT_DRIFT")
        samples,total=_sample(csv_path.read_bytes(),"deliveredTotal")
        require(total==count and set(samples)=={0.,1.,2.,4.},
                "CT03_DM_M_MISSING_CONSTRUCTION_CUTS")
        checked=_m_material_conservation(csv_path,parent)
        require(checked["count"]==count,
                "CT03_DM_M_MASS_ROWS_DIFFER_FROM_FORECAST")
    result={
        "schema":RESULT,"status":"ONE_REAL_ORIGINAL_INITIAL_NATIVE_CHECKED_NOT_SCORED",
        "arm":arm,"index":index,"candidate_id":row["candidate_id"],
        "parent_hash":row["parent_hash"],"model_sha256":row["model_sha256"],
        "script_sha256":row["script_sha256"],
        "csv_sha256":sha_bytes(csv_path.read_bytes()),
        "solver_log_sha256":sha_bytes(log_path.read_bytes()),
        "run_id":run_id,"git_sha":git_sha,
        "csv_rows":count,"output_column":row["output_column"],
        "forecast":[{"time":t,"delivered":points[t]} for t in (6,8)],
        "G2_material_conservation_status":checked["status"],
        "G2_material_max_residual":(checked.get("max_abs_balance")
                                   if arm=="M" else None),
        "construction_residuals_not_yet_built":True,
        "feedback_or_revision_executed":False,
        "new_omc_by_this_verifier":0,"provider_calls":0,
    }
    dest=out/arm/(row["csv_file"].split("/")[-1].removesuffix("_res.csv")+"-result.json")
    require(not dest.exists(),"CT03_DM_RESULT_REFUSE_OVERWRITE")
    dest.write_bytes(canonical(result)+b"\n")
    return result

def record_failure(out:Path,*,arm:str,index:int,run_id:str,git_sha:str,
                   failure_class:str,omc_exit_code:int):
    """Preserve one consumed physical attempt that cannot become a prediction.

    The authorized runner itself writes the attempt record BEFORE invoking
    OMC. An exception from verify_one creates a G2_FAILED entry; compiler /
    translation / contract failure cannot be converted to NOT_EXECUTED or
    a fake zero. No retry, no model edit, no missing raw logs concealed.
    """
    out=Path(out)
    require(arm in ("D","M") and index in range(1,6) and
            type(run_id) is str and run_id.isdigit() and
            type(git_sha) is str and len(git_sha)==40 and
            all(c in "0123456789abcdef" for c in git_sha) and
            failure_class in ("OMC_EXIT_NONZERO","G1_CHECK_FAILED",
                              "G2_CHECK_FAILED","TIMEOUT","CSV_MISSING") and
            type(omc_exit_code) is int and 0<=omc_exit_code<=255,
            "CT03_DM_FAILURE_INVALID_ATTEMPT_METADATA")
    plan=json.loads((out/"plan.json").read_text(encoding="utf-8"))
    require(plan["schema"]==SCHEMA and len(plan["rows"])==10,
            "CT03_DM_FAILURE_ORIGINAL_PLAN_MISSING")
    row=next(x for x in plan["rows"]
             if x["arm"]==arm and x["index"]==index)
    prefix=row["csv_file"].split("/")[-1].removesuffix("_res.csv")
    dest=out/arm/(prefix+"-result.json")
    require(not dest.exists(),"CT03_DM_FAILURE_REFUSE_OVERWRITE")
    log=Path(row["solver_log_file"])
    require(log.is_file() and log.stat().st_size>0,
            "CT03_DM_FAILURE_REAL_ATTEMPT_LOG_REQUIRED")
    attempts=(out/"attempts.log").read_text(encoding="utf-8").splitlines()
    exact=(arm+str(index)+" attempted; GitHub run "+run_id+
           "; code "+git_sha)
    require(attempts.count(exact)==1,
            "CT03_DM_FAILURE_ONE_ATTEMPT_LOGGED_REQUIRED")
    require(sha_bytes(Path(row["source_file"]).read_bytes())==
            row["model_sha256"] and
            sha_bytes(Path(row["script_file"]).read_bytes())==
            row["script_sha256"],
            "CT03_DM_FAILURE_ORIGINAL_SOURCE_OR_COMMAND_CHANGED")
    require(failure_class=="OMC_EXIT_NONZERO" or
            failure_class=="TIMEOUT" or omc_exit_code==0,
            "CT03_DM_FAILURE_EXIT_CODE_CONTRADICTS_CLASS")
    result={
        "schema":RESULT,
        "status":"G2_FAILED_NATIVE_ATTEMPT_NO_FORECAST",
        "arm":arm,"index":index,"candidate_id":row["candidate_id"],
        "parent_hash":row["parent_hash"],
        "model_sha256":row["model_sha256"],
        "script_sha256":row["script_sha256"],
        "run_id":run_id,"git_sha":git_sha,
        "attempt_log_entry":exact,
        "solver_log_sha256":sha_bytes(log.read_bytes()),
        "failure_class":failure_class,"omc_exit_code":omc_exit_code,
        "trace_sha256":None,"forecast":None,
        "new_omc_by_this_recorder":0,"provider_calls":0,
        "not_a_synthetic_zero":True,
    }
    dest.write_bytes(canonical(result)+b"\n")
    return result


def main():
    p=argparse.ArgumentParser()
    s=p.add_subparsers(dest="mode",required=True)
    a=s.add_parser("prepare");a.add_argument("--out",type=Path,required=True)
    a.add_argument("--reuse-report",type=Path,required=True)
    b=s.add_parser("verify-one");b.add_argument("--out",type=Path,required=True)
    b.add_argument("--arm",required=True,choices=["D","M"])
    b.add_argument("--index",type=int,required=True)
    b.add_argument("--run-id",required=True);b.add_argument("--git-sha",required=True)
    c=s.add_parser("record-failure")
    c.add_argument("--out",type=Path,required=True)
    c.add_argument("--arm",required=True,choices=["D","M"])
    c.add_argument("--index",type=int,required=True)
    c.add_argument("--run-id",required=True);c.add_argument("--git-sha",required=True)
    c.add_argument("--failure-class",required=True,choices=[
        "OMC_EXIT_NONZERO","G1_CHECK_FAILED","G2_CHECK_FAILED","TIMEOUT","CSV_MISSING"])
    c.add_argument("--omc-exit-code",type=int,required=True)
    args=p.parse_args()
    if args.mode=="prepare":
        result=prepare(args.out,json.loads(args.reuse_report.read_text(encoding="utf-8")))
    elif args.mode=="record-failure":
        result=record_failure(args.out,arm=args.arm,index=args.index,
            run_id=args.run_id,git_sha=args.git_sha,
            failure_class=args.failure_class,omc_exit_code=args.omc_exit_code)
    else:
        result=verify_one(args.out,arm=args.arm,index=args.index,
                          run_id=args.run_id,git_sha=args.git_sha)
    print(json.dumps({"status":result["status"],"new_omc_by_this_command":0,
                      "provider_calls":0}))

if __name__=="__main__":
    main()
