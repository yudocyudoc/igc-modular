"""CT03 B original native physical output gate, after one authorized OMC run.

The original native and its delivery operator are checked BEFORE parsing a
solver CSV. Never call a solver or the provider. A G1-blocked/ambiguous native
cannot become a prediction. The Modelica translator and native are unmodified.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_b_physical_prepare import SCHEMA as PLAN_SCHEMA,operator
from scripts.arena_cafe.e02_b_feedback import _model_sha
from scripts.arena_cafe.ct03_reuse_ct02 import _points
from scripts.arena_cafe.ct03_m_construction_diagnostic import sha_bytes
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA="igc-ct03-b-own-original-physical-result/1.0"
# Numerical round-off allowance for cumulative delivery in units of items.
# Distinct from the existing 0.008-item MATERIAL conservation tolerance.
CUMULATIVE_MONOTONIC_EPS_ITEMS=1e-8

def check(*,native:dict,receipt:dict,plan:dict,root:Path,
          github_sha:str,github_run_id:str,tolerance:float=.008):
    require(type(github_sha) is str and len(github_sha)==40 and
            all(c in "0123456789abcdef" for c in github_sha) and
            type(github_run_id) is str and github_run_id.isdigit(),
            "CT03_B_PHYS_REAL_RUN_ID_REQUIRED")
    require(type(plan) is dict and plan.get("schema")==PLAN_SCHEMA and
            plan.get("status")=="B_NATIVE_PHYSICAL_PLANNED_NO_OMC" and
            plan.get("native_result_sha256")==receipt.get("result_sha256")==
              _model_sha(native) and
            plan.get("observation_operator")==operator(native) and
            plan.get("new_omc_by_this_step")==0 and
            plan.get("reserved_truth_read") is False and
            type(plan.get("translated_modelica_sha256")) is str and
            type(plan.get("script_sha256")) is str,
            "CT03_B_PHYS_ORIGINAL_NATIVE_PORT_OR_PARENT_DRIFT")
    root=Path(root)
    model_name=plan["translated_model_name"]
    mo=root/(model_name+".mo")
    mos=root/"initial.mos"
    csv_file=root/"b-original_res.csv"
    log=root/"b-original-omc.log"
    require(sha_bytes(mo.read_bytes())==plan["translated_modelica_sha256"] and
            sha_bytes(mos.read_bytes())==plan["script_sha256"] and
            mos.read_text().count("simulate(")==1 and
            "checkModel("+model_name+");" in mos.read_text(),
            "CT03_B_PHYS_SCRIPT_OR_NATIVE_TRANSLATION_DRIFT")
    require(log.is_file() and log.stat().st_size>0 and csv_file.is_file(),
            "CT03_B_PHYS_AUTHENTIC_CSV_LOG_REQUIRED")
    txt=log.read_text(encoding="utf-8",errors="replace")
    require("OpenModelica 1.26.5" in txt and
            "Check of "+model_name+" completed successfully" in txt and
            "LOG_SUCCESS" in txt and
            "b-original_res.csv" in txt,
            "CT03_B_PHYS_UNEXPECTED_REAL_OMC_LOG")
    column=plan["observation_operator"]["modelica_csv_column"]
    points,count=_points(csv_file,column)
    # At the public declared material boundary, all item-valued native stocks
    # must account for accepted input (no invented loss buffer or reporter).
    stock_names=[
        v["name"] for v in native["model"]["variables"]
        if v["type"]=="stock"
    ]
    require(len(stock_names)>=2 and
            all(v.get("units","").strip().lower() in
                ("item","items","work items") for v in native["model"]["variables"]
                if v["type"]=="stock"),
            "CT03_B_PHYS_UNSUPPORTED_MATERIAL_STOCK_UNITS")
    cols=[s.replace(" ","_") for s in stock_names]
    require(len(cols)==len(set(cols)),
            "CT03_B_PHYS_COLLIDING_NATIVE_MATERIAL_STOCK_IDENTIFIERS")
    maximum=0.0
    previous_time=None
    previous_delivered=None
    with csv_file.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        require(reader.fieldnames is not None and
                all(reader.fieldnames.count(c)==1 for c in ("time",*cols)),
                "CT03_B_PHYS_MATERIAL_STOCK_COLUMNS_MISSING")
        n=0
        for row in reader:
            t=float(row["time"])
            states=[float(row[c]) for c in cols]
            delivered=float(row[column])
            require(math.isfinite(t) and math.isfinite(delivered) and
                    all(math.isfinite(x) and x>=-tolerance for x in states),
                    "CT03_B_PHYS_NONFINITE_OR_NEGATIVE_MATERIAL")
            require(previous_delivered is None or
                    delivered >= previous_delivered-CUMULATIVE_MONOTONIC_EPS_ITEMS,
                    "CT03_B_PHYS_CUMULATIVE_DELIVERED_DECREASED")
            # Event-time duplicates may repeat the same cumulative value,
            # allowing ONLY bounded numeric round-off, not a new increment.
            if previous_time is not None and abs(t-previous_time)<=1e-9:
                require(abs(delivered-previous_delivered) <=
                        CUMULATIVE_MONOTONIC_EPS_ITEMS,
                        "CT03_B_PHYS_DUPLICATE_TIME_INCONSISTENT_DELIVERIES")
            previous_time,previous_delivered=t,delivered
            maximum=max(maximum,
                        abs(sum(states)-1.7*min(max(t,0),2)))
            require(maximum<=tolerance,
                    "CT03_B_PHYS_MATERIAL_MASS_BALANCE_FAILED")
            n+=1
    require(n==count,"CT03_B_PHYS_CSV_ROW_COUNT_CHANGED")
    evidence={
        "schema":SCHEMA,
        "status":"B_ORIGINAL_NATIVE_PHYSICAL_CSV_CONFORMING_NOT_HELDOUT",
        "world_public_id":plan["world_public_id"],
        "source_snapshot_hash":plan["source_snapshot_hash"],
        "parent_native_sha256":receipt["result_sha256"],
        "native_modelica_sha256":plan["translated_modelica_sha256"],
        "script_sha256":plan["script_sha256"],
        "csv_sha256":sha_bytes(csv_file.read_bytes()),
        "solver_log_sha256":sha_bytes(log.read_bytes()),
        "observation_operator":plan["observation_operator"],
        "csv_rows":count,
        "max_abs_material_residual":maximum,
        "cumulative_monotonicity_tolerance_items":CUMULATIVE_MONOTONIC_EPS_ITEMS,
        "github_code_sha":github_sha,
        "github_run_id":github_run_id,
        "forecast":[{"time":t,"delivered":points[t]} for t in (6,8)],
        "no_provider_or_solver_call_by_verifier":True,
        "reserved_truth_read":False,
        "not_a_scientific_G3_score":True
    }
    return evidence

def main():
    p=argparse.ArgumentParser()
    for flag in ("native","receipt","plan","root","out"):
        p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--git-sha",required=True)
    p.add_argument("--run-id",required=True)
    a=p.parse_args()
    require(not a.out.exists(),"CT03_B_PHYS_REFUSE_OVERWRITE")
    def load(p):return json.loads(p.read_text(encoding="utf-8"))
    result=check(native=load(a.native),receipt=load(a.receipt),
                 plan=load(a.plan),root=a.root,
                 github_sha=a.git_sha,github_run_id=a.run_id)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes(canonical(result)+b"\n")
    print(json.dumps({"status":result["status"],"new_omc":0,"provider":0}))

if __name__=="__main__":
    main()
