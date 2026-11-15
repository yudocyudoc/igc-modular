"""P08: native M typed-composition sensitivity, NOT a calibrated coffee optimizer.

A new, versioned espresso role reuses the EXACT original IGC BoundedQueue
molecule and E1 composer/backend. It processes aggregate paid orders, not
drinks or individual machine cycles. D/B report explicit abstention from the
two physical mechanisms; their original sources and policies are untouched.
Scientific execution and computations occur ONLY in GitHub Actions.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .common import ArenaError, digest, read_json, write_json
from .coffee_adapters import m
from .coffee_adapters.shared import sha_bytes
from .coffee_next_action import SCHEMA as SOURCE_SCHEMA
from . import runtime

SCHEMA = "arena.coffee.p08-m-aggregate-capacity/1"
SOURCE_RUN = 43697007653
PRODUCER_VIEWS_RUN = 43684660729
SOURCE_ARTIFACT = "s5-support-decision-43697007653"
INPUT_HORIZON_MIN = 105.0
START = 0.0
STOP = 8.0
INTERVALS = 1600
MAX_NEW_OMC = 6
INPUT_LABELS = ("LOWER_PAID_INPUT_Q25", "HIGHER_PAID_INPUT_Q75")
VARIANTS = ("BASE", "PREP_CAPACITY_X2", "ESPRESSO_CAPACITY_X2")
ROLE_ASSUMPTIONS = {
    "preparation": {"maxThroughput":12, "responseTime":0.1},
    "espresso": {"maxThroughput":15, "responseTime":0.1},
    "dispatch": {"maxThroughput":100, "responseTime":0.1},
}
REPRESENTABILITY = {
    "D": "ABSTAIN_NO_EXPLICIT_MANUAL_OR_ESPRESSO_RESOURCE",
    "M": "VERSIONED_AGGREGATE_PREPARATION_ESPRESSO_STAGES_NOT_PHYSICAL_EQUIVALENCE",
    "B": "ABSTAIN_NATIVE_BUFFER_NO_TARGETED_RESOURCE_INTERVENTION",
}


def need(value, code):
    if not value:
        raise ArenaError("COFFEE_P08_" + code)


def input_cases(source, receipt):
    need(type(source) is dict and source.get("schema") == SOURCE_SCHEMA
         and source.get("status") == "TWO_MECHANISMS_COMPARED_WITH_FIXED_B0"
         and source.get("real_profit_or_new_sales_inferred") is False,
         "REFERENCE_SOURCE_NOT_P08")
    need(type(receipt) is dict and receipt.get("source_run_id") == PRODUCER_VIEWS_RUN
         and receipt.get("no_reserved_truth") is True,
         "SOURCE_ARTIFACT_RECEIPT_MISMATCH")
    cases = source.get("baseline")
    need(type(cases) is list and len(cases) == 2, "TWO_B0_CASES_REQUIRED")
    result = {}
    for row in cases:
        need(type(row) is dict and row.get("load_label") in INPUT_LABELS
             and type(row.get("paid_orders")) is int
             and 0 < row["paid_orders"] <= 5000
             and row["load_label"] not in result,
             "INPUT_NOT_TWO_DISTINCT_PAID_LOADS")
        result[row["load_label"]] = row["paid_orders"]
    need(set(result) == set(INPUT_LABELS), "INPUT_LOADS_INCOMPLETE")
    rows = source.get("rows")
    need(type(rows) is list and len(rows) == 4 and
         all(r.get("paid_orders_same_both_cases") ==
             result.get(r.get("load_label")) for r in rows),
         "REFERENCE_ROWS_NOT_PAIRED")
    return result


def typed_version():
    """Extend catalog only in an explicit memory copy; originals stay pinned."""
    composer, backend, swap = m.original()
    cfg, classes, _ = composer.load_registry(m.REGISTRY)
    cfg = copy.deepcopy(cfg)
    classes = copy.deepcopy(classes)
    original_queue = classes["bounded-queue"]
    espresso = copy.deepcopy(original_queue)
    espresso["id"] = "espresso-typed-bounded-queue-p08"
    espresso["roles"] = ["espresso"]
    espresso["role_bindings"] = {"espresso":{
        "T":"ReadyOrder", "U":"ReadyOrder"}}
    espresso["mechanism"] = (
        "Existing IGCMolecules.BoundedQueue, aggregate orders per hour; "
        "NOT discrete espresso cup machinery, staffing, milk, or recipe mix")
    cfg["new_classes"] = [copy.deepcopy(espresso)]
    classes[espresso["id"]] = espresso
    cfg["roles"]["espresso"] = {
        "class_id": espresso["id"], "max_instances":1,
        "parameters": copy.deepcopy(ROLE_ASSUMPTIONS["espresso"])}
    cfg["mandatory_roles"] = ["source", "preparation",
                               "espresso", "dispatch", "receipt"]
    for role in ("preparation","dispatch"):
        cfg["roles"][role]["parameters"] = copy.deepcopy(ROLE_ASSUMPTIONS[role])
    cfg["roles"]["transit"]["max_instances"] = 0
    cfg["roles"]["report"]["max_instances"] = 0
    cfg["max_candidates"] = 4
    cfg["experiment_type"] = "P08_VERSIONED_TYPED_STAGE_PROXY_NOT_EXACT_POLICY"
    cfg["scope"] = ("One generic order queue for preparation and one for "
                    "espresso before dispatch; no barista-machine coupling")
    graphs = composer.enumerate_graphs(cfg,classes)
    need(len(graphs) == 1, "ONE_PREDECLARED_MATERIAL_GRAPH")
    graph_hash, graph = graphs[0]
    need([x["role"] for x in graph["instances"]] == [
        "source","preparation","espresso","dispatch","receipt"],
        "TYPED_ORDER_PATH_CHANGED")
    composer.check_graph(graph,cfg,classes)
    need(all(x["class_id"] == espresso["id"]
             for x in graph["instances"] if x["role"]=="espresso"),
         "ESPRESSO_ROLE_NOT_EXPLICIT")
    return composer, backend, swap, cfg, classes, graph_hash, graph


def prepare(source_path, out):
    """Six models with one shared topology, only three predeclared parameters."""
    source_path = Path(source_path)
    directory = source_path.parent
    receipt = read_json(directory/"receipt.json")
    source = read_json(source_path)
    cases = input_cases(source,receipt)
    need(receipt.get("outputs",{}).get("NEXT_ACTION.json") ==
         sha_bytes(source_path.read_bytes()),
         "DOWNLOADED_SOURCE_HASH_CHANGED")
    _, backend, swap, cfg, classes, key, graph = typed_version()
    need(not Path(out).exists(),"NO_OVERWRITE")
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    records, bodies=[],[]
    for marker in INPUT_LABELS:
        paid=cases[marker]
        rate=paid*60.0/INPUT_HORIZON_MIN
        need(0 < rate < 100, "INPUT_RATE_OUT_OF_BOUNDS")
        for variant in VARIANTS:
            alter=copy.deepcopy(graph)
            for node in alter["instances"]:
                if node["role"]=="preparation" and variant=="PREP_CAPACITY_X2":
                    node["parameters"]["maxThroughput"] *= 2
                if node["role"]=="espresso" and variant=="ESPRESSO_CAPACITY_X2":
                    node["parameters"]["maxThroughput"] *= 2
            # Structural typing is unchanged. Only the declared stage's cap
            # differs; no source-equation replacement except the pulse.
            for node in alter["instances"]:
                role=node["role"]
                if role in ROLE_ASSUMPTIONS:
                    base=ROLE_ASSUMPTIONS[role]
                    expected=dict(base)
                    if variant=="PREP_CAPACITY_X2" and role=="preparation":
                        expected["maxThroughput"]*=2
                    if variant=="ESPRESSO_CAPACITY_X2" and role=="espresso":
                        expected["maxThroughput"]*=2
                    need(node["parameters"]==expected,
                         "UNDECLARED_NATIVE_PARAMETER_DELTA")
            name=("P08_"+("LOW" if marker==INPUT_LABELS[0] else "HIGH")
                  +"_"+variant)
            cls="CoffeeMP08."+name
            body=swap(backend.render_model(name,alter,cfg,classes),
                      rate,INPUT_HORIZON_MIN/60.0)
            need("der(" not in body and "when " not in body
                 and body.count("    deliveredTotal=")==1
                 and body.count("Modelica.Blocks.Sources.RealExpression stimulus(")==1,
                 "NATIVE_BACKEND_NOT_PRESERVED")
            bodies.append(body)
            records.append({
                "name":name,"model_class":cls,"load_label":marker,
                "variant":variant,"input_paid_orders":paid,
                "rectangular_rate_orders_per_hour":rate,
                "input_duration_hour":INPUT_HORIZON_MIN/60.0,
                "model_parameter_changes":{
                    "preparation_max_throughput_orders_per_hour":
                        24 if variant=="PREP_CAPACITY_X2" else 12,
                    "espresso_stage_max_throughput_orders_per_hour":
                        30 if variant=="ESPRESSO_CAPACITY_X2" else 15,
                    "dispatch_max_throughput_orders_per_hour":100,
                },
                "csv":"results/"+name+"_res.csv",
                "log":"logs/"+name+".log",
                "script":"scripts/"+name+".mos",
            })
    model="\n".join([
        "within;","package CoffeeMP08","\n\n".join(bodies),
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end CoffeeMP08;",""])
    (out/"native.mo").write_text(model,encoding="utf-8")
    (out/"results").mkdir()
    (out/"logs").mkdir()
    (out/"scripts").mkdir()
    for row in records:
        name=row["name"]
        script="\n".join([
            "getVersion();",
            'loadFile("/models/IGCMolecules.mo");',
            'loadFile("/models/IGCInformationMolecules.mo");',
            'loadFile("/work/native.mo");',
            "checkModel("+row["model_class"]+");",
            "print(getErrorString());",
            "simulate("+row["model_class"]+",startTime=0,stopTime=8,"
            "numberOfIntervals=1600,method=\"euler\","
            'outputFormat="csv",fileNamePrefix="results/'+name+'");',
            "print(getErrorString());","",
        ])
        need(script.count("simulate(")==1 and
             script.count("checkModel(")==1,"EXACTLY_ONE_OMC_PER_MODEL")
        (out/row["script"]).write_text(script,encoding="utf-8")
    manifest={
        "schema":SCHEMA,"status":"SIX_NATIVE_M_MODELS_STAGED_NOT_EXECUTED",
        "source_run_id":SOURCE_RUN,
        "source_input_sha256":sha_bytes(source_path.read_bytes()),
        "native_model_sha256":sha_bytes((out/"native.mo").read_bytes()),
        "registry_version_sha256":digest(cfg),
        "typed_graph_sha256":"sha256:"+key,
        "method":"M_EXISTING_E1_COMPOSER_AND_BACKEND_WITH_VERSIONED_ESPRESSO_ROLE",
        "original_sources_modified":False,
        "new_equations_authored":False,
        "input_approximation":"SAME_PAID_COUNT_RECTANGULAR_RATE_NOT_ORIGINAL_POS_TIME_SERIES",
        "policy_mapping": {
            "manual_setup_min":"UNREPRESENTABLE_EXACTLY_USE_PREP_CAPACITY_PROXY",
            "espresso_group_plus_one":"UNREPRESENTABLE_EXACTLY_USE_ESPRESSO_THROUGHPUT_PROXY",
            "staff_and_machine_coupling":"UNREPRESENTABLE",
        },
        "assumptions":ROLE_ASSUMPTIONS,
        "representability":REPRESENTABILITY,
        "maximum_new_omc_attempts":MAX_NEW_OMC,
        "truth_read":False,"provider_posts":0,"new_worlds":0,
        "models":records,
    }
    write_json(out/"manifest.json",manifest,exclusive=True)
    return manifest


def audit_csv(path, record):
    """Only bounded monotone material output; never claim observed pickups."""
    need(path.is_file(),"MODEL_CSV_MISSING")
    with path.open(encoding="utf-8",newline="") as fp:
        reader=csv.DictReader(fp)
        rows=[]
        for row in reader:
            need(len(rows)<2000,"RESULT_TOO_LARGE")
            rows.append(row)
    need(len(rows)>=INTERVALS+1,"CSV_SAMPLE_COUNT")
    first=rows[0]
    counter=next((c for c in first if c=="deliveredTotal"),None)
    need(counter is not None,"NO_NATIVE_DELIVERY_COUNTER")
    stocks=("preparation0.waiting","espresso0.waiting","dispatch0.waiting")
    need(all(col in first for col in stocks) and
         "time" in first,"NATIVE_STOCK_COLUMNS_MISSING")
    parsed=[]
    previous=-1.0
    previous_delivered=-1.0
    for row in rows:
        try:
            t=float(row["time"])
            deliveries=float(row["deliveredTotal"])
            open_orders=sum(float(row[col]) for col in stocks)
        except (ValueError,TypeError,KeyError):
            raise ArenaError("COFFEE_P08_INVALID_NATIVE_CSV") from None
        need(all(math.isfinite(v) for v in (t,deliveries,open_orders))
             and t>=previous and deliveries>=previous_delivered-1e-3
             and open_orders>=-1e-3 and deliveries>=-1e-3,
             "UNPHYSICAL_MATERIAL_SERIES")
        previous,previous_delivered=t,deliveries
        parsed.append((t,deliveries,open_orders))
    peak=INPUT_HORIZON_MIN/60.0
    at_peak=[p for p in parsed if p[0] <= peak+1e-7]
    need(at_peak,"NO_PREDECLARED_PEAK_CUT")
    t,y,q=at_peak[-1]
    last=parsed[-1]
    paid=record["input_paid_orders"]
    need(abs(t-peak)<0.01 and
         abs((y+q)-paid)<1.0 and
         abs((last[1]+last[2])-paid)<1.0 and
         abs(last[2])<0.3,
         "MATERIAL_BALANCE_OR_DRAIN_FAILURE")
    return {
        "modeled_delivered_continuous_at_cut":round(y,6),
        "modeled_pending_continuous_at_cut":round(q,6),
        "modeled_delivered_after_drain":round(last[1],6),
        "terminal_pending":round(last[2],6),
        "mass_residual_at_cut":round(y+q-paid,6),
        "no_individual_wait_p90":True,
    }


def run(root):
    need(os.environ.get("GITHUB_REPOSITORY")=="yudocyudoc/igc-modular"
         and os.environ.get("GITHUB_REF")=="refs/heads/main"
         and os.environ.get("GITHUB_EVENT_NAME")=="push"
         and os.environ.get("GITHUB_RUN_ATTEMPT")=="1",
         "REAL_OMC_GITHUB_MAIN_FIRST_ATTEMPT_ONLY")
    root=Path(root)
    mfest=read_json(root/"manifest.json")
    need(mfest["schema"]==SCHEMA and
         mfest["status"]=="SIX_NATIVE_M_MODELS_STAGED_NOT_EXECUTED"
         and len(mfest["models"])==MAX_NEW_OMC,
         "MANIFEST_NOT_STAGED")
    need(sha_bytes((root/"native.mo").read_bytes()) ==
         mfest["native_model_sha256"],"STAGED_MODELICA_CHANGED")
    # Each attempt is its own container. A failed attempt consumes the slot.
    # Never retry or silently substitute a projected reference outcome.
    home=Path(os.environ["RUNNER_TEMP"])/"e1-home"
    libs=Path(os.environ["RUNNER_TEMP"])/"e1-libs"
    models=Path(__file__).resolve().parent/"_vendor/igc/src/modelica"
    results=[]
    failures=[]
    for index,row in enumerate(mfest["models"],1):
        need(index<=MAX_NEW_OMC,"OMC_BUDGET_EXCEEDED")
        log=root/row["log"]
        need(not log.exists(),"NO_SOLVER_RETRY")
        cmd=["docker","run","--rm","--network","none",
             "--user",str(os.getuid())+":"+str(os.getgid()),
             "-v",str(root.resolve())+":/work",
             "-v",str(models.resolve())+":/models:ro",
             "-v",str(home.resolve())+":/omhome",
             "-e","HOME=/omhome",
             "-v",str(libs.resolve())+":/thirdparty:ro",
             "-e","OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics",
             "-w","/work",runtime.IMAGE,"omc",row["script"]]
        outcome={"load_label":row["load_label"],"variant":row["variant"],
                 "attempt_number":index,"one_shot_attempted":True}
        try:
            with log.open("xb") as fp:
                process=subprocess.run(cmd,stdout=fp,stderr=subprocess.STDOUT,
                                       timeout=180,check=False)
            evidence=log.read_text(encoding="utf-8",errors="replace")
            outcome["solver_exit_code"]=process.returncode
            outcome["check_model_completed"]=(
                "Check of "+row["model_class"]+" completed successfully"
                in evidence)
            outcome["log_success"]="LOG_SUCCESS" in evidence
            outcome["solver_status"]=(
                "PASS" if process.returncode==0 and
                outcome["check_model_completed"] and outcome["log_success"]
                and (root/row["csv"]).is_file() else "FAILED")
            if outcome["solver_status"]=="PASS":
                outcome.update(audit_csv(root/row["csv"],row))
            else:
                failures.append(row["name"])
        except (OSError,subprocess.TimeoutExpired,ArenaError) as err:
            failures.append(row["name"])
            outcome["solver_status"]="FAILED"
            outcome["error_type"]=type(err).__name__
        results.append(outcome)
        write_json(root/"logs"/(row["name"]+".receipt.json"),
                   outcome,exclusive=True)
    # Analyze only deliveredTotal from native M. No discrete order claims.
    cases=[]
    for label in INPUT_LABELS:
        trio=[r for r in results if r["load_label"]==label]
        if len(trio)!=3 or any(r["solver_status"]!="PASS" for r in trio):
            continue
        grouped={r["variant"]:r for r in trio}
        b0=grouped["BASE"]["modeled_delivered_continuous_at_cut"]
        for action in VARIANTS[1:]:
            alt=grouped[action]["modeled_delivered_continuous_at_cut"]
            cases.append({
                "load_label":label,"variant":action,
                "native_M_B0_continuous_handoffs_at_cut":b0,
                "native_M_policy_continuous_handoffs_at_cut":alt,
                "delta_continuous_handoffs_at_cut":round(alt-b0,6),
                "B0_paid_orders_from_existing_artifact":next(
                    x["input_paid_orders"] for x in mfest["models"]
                    if x["load_label"]==label),
                "correspondence_to_reference":"NO_EXACT_MAPPING_OF_RECIPES_OR_P90",
            })
    report={
        "schema":SCHEMA,
        "status":("NATIVE_M_P08_SIX_SIMS_SUCCEEDED"
                  if not failures and len(cases)==4
                  else "INCOMPLETE_NATIVE_ATTEMPTS_NO_DECISION"),
        "attempts":results,"pairwise_comparisons":cases,
        "failed_models":failures,
        "representability":REPRESENTABILITY,
        "causal_real_business_evidence":False,
        "origin":"GITHUB_ONLY_NATIVE_M_OMC_NO_TRUTH",
        "new_omc_attempted":len(results),
        "new_worlds":0,"provider_posts":0,
    }
    write_json(root/"result.json",report,exclusive=True)
    lines=["# P08 — Does M independently respond to preparation/espresso capacity?",
           "",
           "Native original E1/BoundedQueue dynamics, versioned typed espresso role.",
           "**Aggregate orders, NOT coffee recipes, physical machine cycles,",
           "staff sharing, individual P90, or proven real business capacity.**",
           "",
           "| Synthetic load | M aggregate action | B0 deliveries | Action deliveries | Δ continuous deliveries |",
           "|---|---|---:|---:|---:|"]
    for c in cases:
        lines.append(
            "| "+c["load_label"]+" | "+c["variant"]+" | "+
            str(c["native_M_B0_continuous_handoffs_at_cut"])+" | "+
            str(c["native_M_policy_continuous_handoffs_at_cut"])+" | "+
            str(c["delta_continuous_handoffs_at_cut"])+" |")
    lines += ["","D: abstains from task-level espresso/manual model.",
              "B: abstains from those same unsupported policies.",
              "M: only an order-queue proxy; DO NOT equate its delta",
              "to the specialist's discrete orders or a purchase ROI.",
              "A change in capacity may move the bottleneck to another stage.",
              "Next: measure task and machine timings to identify which",
              "proxy, if any, corresponds to the real physical mechanism.",
              "","OMC attempts: "+str(len(results))+", failure count: "+
              str(len(failures))+" (no retries)."]
    (root/"RESULT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    need(not failures and len(cases)==4,
         "NATIVE_EXECUTION_FAILED_NO_SCIENTIFIC_CONCLUSION")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="mode",required=True)
    item=sub.add_parser("prepare")
    item.add_argument("--source",required=True)
    item.add_argument("--out",required=True)
    item=sub.add_parser("run")
    item.add_argument("--root",required=True)
    args=parser.parse_args(argv)
    if args.mode=="prepare":
        p=prepare(args.source,args.out)
        print(json.dumps({"status":p["status"],
                          "candidate_count":len(p["models"]),
                          "original_sources_modified":False}))
    else:
        run(args.root)


if __name__=="__main__":
    main()
