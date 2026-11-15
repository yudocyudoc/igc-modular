"""P08: versioned D stock-flow stage-capacity sensitivity (GitHub OMC only).

The original D grammar is preserved in _vendor. We generate its exact
three-stock, no-loss structure and change ONLY the one shared capacity
parameter to three stage-specific limits. Differential equations, pulse,
observation and mass balances come directly from the original generator.
Stage labels are analogies, not identified espresso or barista machines.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path
import subprocess

from .common import ArenaError, digest, read_json, write_json
from .coffee_adapters import d
from .coffee_adapters.shared import sha_bytes
from . import coffee_m_p08 as m_p08
from . import runtime

SCHEMA = "arena.coffee.p08-d-stage-capacity/1"
SOURCE_RUN = m_p08.SOURCE_RUN
SOURCE_ARTIFACT = m_p08.SOURCE_ARTIFACT
LOADS = m_p08.INPUT_LABELS
VARIANTS = m_p08.VARIANTS
BASE_CAPS = (12.0, 15.0, 100.0)  # abstract orders/hour, not physical units
RESPONSE_HOURS = 0.1
HORIZON_HOURS = m_p08.INPUT_HORIZON_MIN / 60.0
STOP_HOURS = m_p08.STOP
INTERVALS = m_p08.INTERVALS
MAX_OMC = 6


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_D_P08_" + code)


def capacities(variant):
    need(variant in VARIANTS, "UNDECLARED_CAPACITY_VARIANT")
    values = list(BASE_CAPS)
    if variant == "PREP_CAPACITY_X2":
        values[0] *= 2
    if variant == "ESPRESSO_CAPACITY_X2":
        values[1] *= 2
    return tuple(values)


def versioned_model(source, profile, *, name, caps):
    """Make a narrowly bounded derivative-preserving translation of D."""
    need(type(caps) is tuple and len(caps) == 3 and
         all(type(c) in (int,float) and math.isfinite(c) and 0 < c <= 100
             for c in caps), "CAPACITY_VECTOR_OUT_OF_SCOPE")
    need(type(name) is str and name.startswith("DP08_") and
         name.replace("_", "").isalnum(), "MODEL_NAME")
    top = source.topology(3, False)
    source.lint_structure(top)
    key = source.digest(top)
    candidate = {
        "structure": top, "structure_hash": key,
        "nominal_parameters": {
            "capacity": BASE_CAPS[0],
            "response_time": RESPONSE_HOURS,
            "loss_time": 1000000.0,
        },
    }
    original = source.modelica(candidate, profile)
    stem = "DStockFlow_" + key[7:19]
    need(original.count("model "+stem) == 1 and
         original.count("end "+stem+";") == 1,
         "ORIGINAL_D_MODEL_SHAPE_CHANGED")
    revised = original.replace("model "+stem, "model "+name, 1)
    revised = revised.replace("end "+stem+";", "end "+name+";", 1)
    prior = "  parameter Real capacity = 12;"
    need(revised.count(prior) == 1, "ORIGINAL_SHARED_CAPACITY_CHANGED")
    revised = revised.replace(
        prior,
        "\n".join("  parameter Real stageCap"+str(i)+" = "+format(c, ".12g")+";"
                  for i,c in enumerate(caps,1)),1)
    for i in range(1,4):
        old = "  f"+str(i)+" = min(capacity, max(0, s"+str(i)+"/responseTime));"
        new = "  f"+str(i)+" = min(stageCap"+str(i)+", max(0, s"+str(i)+"/responseTime));"
        need(revised.count(old) == 1,"D_FLOW_NOT_ORIGINAL")
        revised = revised.replace(old,new,1)
        need(revised.count(new)==1,"D_VERSIONED_CAPACITY_NOT_APPLIED")
    # Only parameter bindings and model name can change. NEVER rewrite
    # differential equations or synthesize a new topology.
    source_derivatives=[l for l in original.splitlines() if l.lstrip().startswith("der(")]
    revised_derivatives=[l for l in revised.splitlines() if l.lstrip().startswith("der(")]
    need(source_derivatives == revised_derivatives and
         len(source_derivatives)==5 and
         revised.count("  inputRate = if time < pulseDuration") == 1 and
         revised.count("  lossRate = 0;") == 1 and
         "min(capacity," not in revised,
         "D_DIFFERENTIAL_EQUATIONS_OR_INPUT_CHANGED")
    return revised,key


def prepare(source_path,out):
    path=Path(source_path)
    receipt=read_json(path.parent/"receipt.json")
    need(receipt.get("outputs",{}).get("NEXT_ACTION.json") ==
         sha_bytes(path.read_bytes()),"SOURCE_MEMBER_HASH_CHANGED")
    cases=m_p08.input_cases(read_json(path),receipt)
    source=d.original()
    need(not Path(out).exists(),"NO_OVERWRITE")
    root=Path(out)
    root.mkdir(parents=True,exist_ok=False,mode=0o700)
    for sub in ("scripts","logs","results"):
        (root/sub).mkdir()
    records=[]
    for load in LOADS:
        paid=cases[load]
        rate=paid / HORIZON_HOURS
        need(0 < rate <= 100,"ORDER_RATE_OUT_OF_SCOPE")
        profile={"kind":"pulse","rate":rate,"duration":HORIZON_HOURS}
        for variant in VARIANTS:
            name=("DP08_"+("LOW" if load==LOADS[0] else "HIGH")
                  +"_"+variant)
            caps=capacities(variant)
            model,topology_hash=versioned_model(source,profile,name=name,caps=caps)
            model_path=root/(name+".mo")
            model_path.write_text(model,encoding="utf-8",newline="\n")
            script="\n".join([
                "getVersion();",
                'loadFile("/work/'+name+'.mo");',
                "checkModel("+name+");",
                "print(getErrorString());",
                "simulate("+name+
                ',startTime=0,stopTime=8,numberOfIntervals=1600,method="euler",'+
                'outputFormat="csv",fileNamePrefix="results/'+name+'");',
                "print(getErrorString());",""
            ])
            need(script.count("simulate(")==1 and script.count("checkModel(")==1,
                 "SCRIPT_MUST_HAVE_ONE_CHECK_AND_SIMULATION")
            (root/"scripts"/(name+".mos")).write_text(
                script,encoding="utf-8",newline="\n")
            records.append({
                "name":name,"load_label":load,"variant":variant,
                "input_paid_orders":paid,"rectangular_rate_per_hour":rate,
                "stage_caps_per_hour":list(caps),
                "response_time_hours":RESPONSE_HOURS,
                "model_sha256":sha_bytes(model_path.read_bytes()),
                "script_sha256":sha_bytes(
                    (root/"scripts"/(name+".mos")).read_bytes()),
                "model_file":name+".mo",
                "script_file":"scripts/"+name+".mos",
                "csv_file":"results/"+name+"_res.csv",
                "log_file":"logs/"+name+".log",
            })
    need(len(records)==MAX_OMC,"EXACTLY_SIX_PREDECLARED_MODELS")
    manifest={
        "schema":SCHEMA,
        "status":"SIX_D_VERSIONED_CAPACITY_MODELS_STAGED_NOT_SIMULATED",
        "original_method":source.METHOD,
        "original_grammar_schema":source.SCHEMA,
        "original_source_edited":False,
        "source_selected_native_topology_sha256":topology_hash,
        "translation":"ONLY_SHARED_CAPACITY_TO_STAGE_CAP1_2_3",
        "derivative_equations_unchanged":True,
        "model_scope":"THREE_GENERIC_STOCKS_NOT_EXACT_COFFEE_PROCESS",
        "physical_stage_names_are_not_observed":True,
        "response_time_assumed_hours":RESPONSE_HOURS,
        "source_run_id":SOURCE_RUN,
        "source_member_sha256":sha_bytes(path.read_bytes()),
        "input_mapping":"EXACT_PAID_COUNTS_PULSE_APPROXIMATION_105_MIN",
        "models":records,"max_new_omc":MAX_OMC,
        "truth_read":False,"new_worlds":0,"provider_posts":0,
    }
    write_json(root/"manifest.json",manifest,exclusive=True)
    return manifest


def verify_csv(path, record):
    """Continuous mass audit from authentic D OMC CSV, not empirical delivery."""
    path=Path(path)
    need(path.is_file(),"CSV_NOT_PRODUCED")
    with path.open(encoding="utf-8",newline="") as f:
        reader=csv.DictReader(f)
        need(reader.fieldnames is not None and
             {"time","delivered","lost","s1","s2","s3"}.issubset(
                 set(reader.fieldnames)), "NATIVE_D_COLUMNS_REQUIRED")
        rows=list(reader)
    need(INTERVALS+1 <= len(rows) <= 2500,"NATIVE_CSV_SAMPLE_COUNT")
    previous_t=-1.0
    previous_delivery=-1.0
    values=[]
    max_residual=0.0
    for row in rows:
        try:
            t=float(row["time"])
            y=float(row["delivered"])
            lost=float(row["lost"])
            stocks=[float(row["s"+str(i)]) for i in range(1,4)]
        except (TypeError,ValueError,KeyError):
            raise ArenaError("COFFEE_D_P08_NONNUMERIC_CSV") from None
        need(all(math.isfinite(z) for z in [t,y,lost,*stocks])
             and t >= previous_t and y >= previous_delivery-1e-3
             and min(y,lost,*stocks)>=-1e-3,
             "NATIVE_D_NONPHYSICAL_STOCK_OR_COUNTER")
        expected=record["rectangular_rate_per_hour"]*min(
            max(0,t),HORIZON_HOURS)
        residual=abs(y+lost+sum(stocks)-expected)
        max_residual=max(residual,max_residual)
        previous_t,previous_delivery=t,y
        values.append((t,y,lost,stocks))
    need(max_residual < 0.20 and abs(values[0][0]) < 1e-8,
         "NATIVE_D_MASS_RESIDUAL")
    near=[x for x in values if x[0] <= HORIZON_HOURS+1e-8]
    need(near and abs(near[-1][0]-HORIZON_HOURS)<0.01,
         "NATIVE_D_PULSE_CUT_MISSING")
    t,y,lost,stocks=near[-1]
    end=values[-1]
    need(abs(end[0]-STOP_HOURS)<1e-6 and
         abs(end[1]+end[2]+sum(end[3])-
             record["input_paid_orders"]) < 0.20 and
         abs(end[2]) < 1e-3 and
         sum(end[3]) < 0.30,
         "DRAIN_OR_ORDER_CONSERVATION_FAILED")
    return {
        "modeled_delivered_continuous_at_cut":round(y,6),
        "modeled_pending_continuous_at_cut":round(sum(stocks),6),
        "modeled_delivered_after_drain":round(end[1],6),
        "max_material_residual":round(max_residual,6),
        "not_discrete_handoffs_or_revenue":True,
    }


def run(root):
    need(os.environ.get("GITHUB_REPOSITORY")=="yudocyudoc/igc-modular" and
         os.environ.get("GITHUB_REF")=="refs/heads/main" and
         os.environ.get("GITHUB_EVENT_NAME")=="push" and
         os.environ.get("GITHUB_RUN_ATTEMPT")=="1",
         "NATIVE_OMC_ONLY_MAIN_FIRST_ATTEMPT")
    root=Path(root)
    manifest=read_json(root/"manifest.json")
    need(manifest.get("schema")==SCHEMA and
         manifest.get("status")==
         "SIX_D_VERSIONED_CAPACITY_MODELS_STAGED_NOT_SIMULATED" and
         len(manifest.get("models",[]))==MAX_OMC,
         "INVALID_STAGED_MANIFEST")
    for record in manifest["models"]:
        need(sha_bytes((root/record["model_file"]).read_bytes()) ==
             record["model_sha256"] and
             sha_bytes((root/record["script_file"]).read_bytes()) ==
             record["script_sha256"], "STAGED_NATIVE_MODEL_CHANGED")
    home=Path(os.environ["RUNNER_TEMP"])/"e1-home"
    libs=Path(os.environ["RUNNER_TEMP"])/"e1-libs"
    receipts=[]
    failed=[]
    for index,record in enumerate(manifest["models"],1):
        need(index<=MAX_OMC,"OMC_BUDGET_EXCEEDED")
        log=root/record["log_file"]
        need(not log.exists(),"NO_NATIVE_OMC_RETRY")
        # One-shot attempt is recorded before execution to survive a failure.
        attempt={
            "load_label":record["load_label"],"variant":record["variant"],
            "attempt_number":index,"attempt_reserved":True,
            "no_retry":True,"model_sha256":record["model_sha256"],
        }
        write_json(root/"logs"/(record["name"]+".attempt.json"),
                   attempt,exclusive=True)
        cmd=["docker","run","--rm","--network","none",
             "--user",str(os.getuid())+":"+str(os.getgid()),
             "-v",str(root.resolve())+":/work",
             "-v",str(home.resolve())+":/omhome",
             "-e","HOME=/omhome",
             "-v",str(libs.resolve())+":/thirdparty:ro",
             "-e","OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics",
             "-w","/work",runtime.IMAGE,"omc",record["script_file"]]
        receipt=dict(attempt)
        try:
            with log.open("xb") as out:
                proc=subprocess.run(
                    cmd,stdout=out,stderr=subprocess.STDOUT,
                    timeout=180,check=False)
            evidence=log.read_text(encoding="utf-8",errors="replace")
            receipt["omc_exit_code"]=proc.returncode
            receipt["check_model_completed"]=(
                "Check of "+record["name"]+" completed successfully" in evidence)
            receipt["log_success"]="LOG_SUCCESS" in evidence
            if (proc.returncode==0 and receipt["check_model_completed"]
                and receipt["log_success"] and
                (root/record["csv_file"]).is_file()):
                receipt.update(verify_csv(
                    root/record["csv_file"],record))
                receipt["solver_status"]="PASS"
            else:
                receipt["solver_status"]="FAILED"
        except (OSError,subprocess.TimeoutExpired,ArenaError) as err:
            receipt["solver_status"]="FAILED"
            receipt["failure_type"]=type(err).__name__
        if receipt["solver_status"]!="PASS":
            failed.append(record["name"])
        receipts.append(receipt)
        write_json(root/"logs"/(record["name"]+".receipt.json"),
                   receipt,exclusive=True)
    comparisons=[]
    for load in LOADS:
        group={x["variant"]:x for x in receipts if
               x["load_label"]==load and x["solver_status"]=="PASS"}
        if len(group)!=3:
            continue
        baseline=group["BASE"]["modeled_delivered_continuous_at_cut"]
        for variant in VARIANTS[1:]:
            target=group[variant]["modeled_delivered_continuous_at_cut"]
            comparisons.append({
                "load_label":load,"variant":variant,
                "native_D_B0_continuous_at_cut":baseline,
                "native_D_policy_continuous_at_cut":target,
                "delta_continuous_at_cut":round(target-baseline,6),
                "B0_paid_orders_from_source":next(
                    r["input_paid_orders"] for r in manifest["models"]
                    if r["load_label"]==load),
                "representation":"D_THREE_STOCKS_GENERIC_STAGE_CAPACITY_PROXY",
            })
    result={
        "schema":SCHEMA,
        "status":("D_SIX_NATIVE_OMC_PASS_NOT_REAL_CAUSAL_VALIDATION"
                  if not failed and len(comparisons)==4
                  else "D_NATIVE_INCOMPLETE_NO_DECISION"),
        "omc_attempts_reserved":len(receipts),
        "failures":failed,"attempts":receipts,
        "pairwise_comparisons":comparisons,
        "physical_model_identified":False,
        "stage_mapping_validated":False,
        "input_temporal_profile_identical_to_M_proxy":True,
        "input_temporal_profile_identical_to_specialist":False,
        "no_new_worlds_or_provider":True,
    }
    write_json(root/"result.json",result,exclusive=True)
    table=[
        "# P08 D — three independent stage capacities (native OMC)",
        "",
        "Only generic 3-stock D source dynamics; original vendor D unchanged.",
        "Continuous paid-order queue, rectangular source, no recipes or P90.",
        "",
        "| Load | Capacity action | D B0 continuous at cut | D action | Difference |",
        "|---|---|---:|---:|---:|",
    ]
    for row in comparisons:
        table.append(
            f"| {row['load_label']} | {row['variant']} | "
            f"{row['native_D_B0_continuous_at_cut']:.6f} | "
            f"{row['native_D_policy_continuous_at_cut']:.6f} | "
            f"{row['delta_continuous_at_cut']:+.6f} |")
    table.extend([
        "",
        "Six one-shot OMC attempts, failures: "+str(len(failed))+".",
        "No real equipment capacity, sales, staffing, or business ROI inferred.",
    ])
    (root/"RESULT.md").write_text("\n".join(table)+"\n",encoding="utf-8")
    print("\n".join(table))
    need(not failed and len(comparisons)==4,
         "NATIVE_OMC_INCOMPLETE_NO_INFERRED_CONCLUSION")
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("prepare")
    a.add_argument("--source",required=True)
    a.add_argument("--out",required=True)
    b=sub.add_parser("run")
    b.add_argument("--root",required=True)
    args=p.parse_args(argv)
    if args.command=="prepare":
        plan=prepare(args.source,args.out)
        print({"status":plan["status"],"models":len(plan["models"])})
    else:
        run(args.root)


if __name__=="__main__":
    main()
