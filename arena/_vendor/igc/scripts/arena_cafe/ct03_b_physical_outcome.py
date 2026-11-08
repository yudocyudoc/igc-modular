"""CT-03 B: collect a consumed original OMC attempt, including failed ones.

The producer supplies an exit record, solver log and original model/script
bytes. Integrity failures stop the pipeline; after those checks a genuine
failed physical/solver attempt is retained as G2_FAILED with NO forecast.
Neither this module nor its tests call OpenModelica or Buffalo. A local
receipt is not independent proof that its claimed runner executed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical
from scripts.arena_cafe.ct_feedback_bridge import require
from scripts.arena_cafe.ct03_b_physical_prepare import SCHEMA as PLAN_SCHEMA,operator
from scripts.arena_cafe.ct03_b_physical_result import check
from scripts.arena_cafe.ct03_m_construction_diagnostic import sha_bytes
from scripts.arena_cafe.e02_b_feedback import _model_sha

SCHEMA="igc-ct03-b-own-original-physical-failed-attempt/1.0"
STATUS="B_ORIGINAL_NATIVE_PHYSICAL_ATTEMPT_G2_FAILED_NOT_HELDOUT"
# Expected output/verifier failures only. Native, plan, source or script
# mismatches are never converted to a failed physical experiment.
G2_CHECK_FAILURES=frozenset({
    "CT03_B_PHYS_AUTHENTIC_CSV_LOG_REQUIRED",
    "CT03_B_PHYS_UNEXPECTED_REAL_OMC_LOG",
    "CT03_B_PHYS_NONFINITE_OR_NEGATIVE_MATERIAL",
    "CT03_B_PHYS_CUMULATIVE_DELIVERED_DECREASED",
    "CT03_B_PHYS_DUPLICATE_TIME_INCONSISTENT_DELIVERIES",
    "CT03_B_PHYS_MATERIAL_MASS_BALANCE_FAILED",
    "CT03_B_PHYS_CSV_ROW_COUNT_CHANGED",
    "CT03_B_PHYS_MATERIAL_STOCK_COLUMNS_MISSING",
    "CT03_REUSE_EXACT_NATIVE_OUTPUT_COLUMN_REQUIRED",
    "CT03_REUSE_INVALID_NATIVE_TRACE",
    "CT03_REUSE_CONFLICTING_PREDICTION_AT_EVENT",
    "CT03_REUSE_FULL_HORIZON_OR_PREDICTIONS_MISSING",
})

def preflight(*,native,receipt,plan,root):
    """Fail closed on parent/translation/script BEFORE any actual OMC attempt."""
    require(type(receipt) is dict and type(plan) is dict and
            plan.get("schema")==PLAN_SCHEMA and
            plan.get("status")=="B_NATIVE_PHYSICAL_PLANNED_NO_OMC" and
            plan.get("round_kind") in ("initial","revision") and
            receipt.get("round_kind")==plan["round_kind"] and
            receipt.get("status")=="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED" and
            receipt.get("mode")=="live" and
            receipt.get("case_id")=="CT-03" and
            receipt.get("condition_id")=="C0" and
            receipt.get("world_public_id")==plan.get("world_public_id") and
            receipt.get("source_snapshot_hash")==plan.get("source_snapshot_hash") and
            receipt.get("result_sha256")==plan.get("native_result_sha256")==
                _model_sha(native) and
            plan.get("native_result_bytes_bound") is True and
            plan.get("model_repair_performed") is False and
            plan.get("reserved_truth_read") is False and
            plan.get("observation_operator")==operator(native) and
            plan.get("new_omc_by_this_step")==0,
            "CT03_B_OUTCOME_NATIVE_OR_PLAN_INTEGRITY_STOP")
    root=Path(root)
    model=plan["translated_model_name"]
    mo=root/(model+".mo")
    mos=root/"initial.mos"
    require(mo.is_file() and mos.is_file() and
            sha_bytes(mo.read_bytes())==plan.get("translated_modelica_sha256") and
            sha_bytes(mos.read_bytes())==plan.get("script_sha256") and
            mos.read_text(encoding="utf-8").count("simulate(")==1 and
            "checkModel("+model+");" in mos.read_text(encoding="utf-8") and
            'fileNamePrefix="'+(root/"b-original").as_posix()+'"' in
                mos.read_text(encoding="utf-8"),
            "CT03_B_OUTCOME_NATIVE_SCRIPT_INTEGRITY_STOP")
    return {"status":"B_PHYSICAL_SOURCE_PREFLIGHT_OK_NOT_EXECUTED",
            "round_kind":plan["round_kind"],
            "parent_native_sha256":receipt["result_sha256"],
            "new_omc":0,"provider_calls":0}

def collect(*,native,receipt,plan,root,github_sha,github_run_id):
    require(type(github_sha) is str and len(github_sha)==40 and
            all(c in "0123456789abcdef" for c in github_sha) and
            type(github_run_id) is str and github_run_id.isdigit(),
            "CT03_B_OUTCOME_REAL_RUN_ID_REQUIRED")
    preflight(native=native,receipt=receipt,plan=plan,root=root)
    root=Path(root)
    meta_path=root/"omc-exit.json"
    log=root/"b-original-omc.log"
    require(meta_path.is_file() and log.is_file() and log.stat().st_size>0,
            "CT03_B_OUTCOME_CONSUMED_ATTEMPT_AND_LOG_REQUIRED")
    meta=json.loads(meta_path.read_text(encoding="utf-8"))
    require(type(meta) is dict and set(meta)=={
                "arm","round_kind","run_id","git_sha","exit_code","attempted"
            } and meta["arm"]=="B" and
            meta["round_kind"]==plan["round_kind"] and
            meta["run_id"]==github_run_id and meta["git_sha"]==github_sha and
            meta["attempted"] is True and type(meta["exit_code"]) is int and
            0<=meta["exit_code"]<=255,
            "CT03_B_OUTCOME_EXACT_ATTEMPT_METADATA_MISMATCH")
    if meta["exit_code"]==0:
        try:
            return check(native=native,receipt=receipt,plan=plan,root=root,
                         github_sha=github_sha,github_run_id=github_run_id)
        except ValueError as exc:
            failure=str(exc)
            require(failure in G2_CHECK_FAILURES,
                    "CT03_B_OUTCOME_NON_PHYSICAL_FAILURE_MUST_STOP")
            failure_class="G2_PHYSICAL_CHECK_FAILED"
    else:
        failure="OMC_EXIT_NONZERO:"+str(meta["exit_code"])
        failure_class="OMC_EXIT_NONZERO"
    csv=root/"b-original_res.csv"
    return {
        "schema":SCHEMA,"status":STATUS,
        "world_public_id":plan["world_public_id"],
        "source_snapshot_hash":plan["source_snapshot_hash"],
        "round_kind":plan["round_kind"],
        "parent_native_sha256":receipt["result_sha256"],
        "native_modelica_sha256":plan["translated_modelica_sha256"],
        "script_sha256":plan["script_sha256"],
        "observation_operator":plan["observation_operator"],
        "attempt_record_sha256":sha_bytes(meta_path.read_bytes()),
        "solver_log_sha256":sha_bytes(log.read_bytes()),
        "csv_sha256":sha_bytes(csv.read_bytes()) if csv.is_file() else None,
        "github_code_sha":github_sha,"github_run_id":github_run_id,
        "omc_exit_code":meta["exit_code"],"attempted":True,
        "failure_class":failure_class,"failure_reason":failure,
        "forecast":None,"reserved_truth_read":False,
        "independent_solver_execution_proven":False,
        "no_provider_or_solver_call_by_collector":True
    }

def main():
    p=argparse.ArgumentParser()
    for flag in ("native","receipt","plan","root","out"):
        p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--git-sha",required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--preflight-only",action="store_true")
    a=p.parse_args()
    require(a.preflight_only or not a.out.exists(),
            "CT03_B_OUTCOME_REFUSE_OVERWRITE")
    def read(path): return json.loads(path.read_text(encoding="utf-8"))
    if a.preflight_only:
        result=preflight(native=read(a.native),receipt=read(a.receipt),
                         plan=read(a.plan),root=a.root)
        print(json.dumps(result))
        return
    result=collect(native=read(a.native),receipt=read(a.receipt),
                   plan=read(a.plan),root=a.root,
                   github_sha=a.git_sha,github_run_id=a.run_id)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes(canonical(result)+b"\n")
    print(json.dumps({"status":result["status"],
                      "new_omc":0,"provider_calls":0,
                      "failed":result["status"]==STATUS}))

if __name__=="__main__":
    main()
