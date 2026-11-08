"""Arena M2: one bounded, own-feedback parameter revision of Short E1 molecule.

Reads M1 native artifact, real OpenModelica CSV and G2 diagnostic. The feedback
is restricted to this M hypothesis. One predeclared direction-only step is
allowed (responseTime x2 on late overshoot), with no grid search, no extra
candidate Modelica executions, no structural substitution, and no D/B inputs.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import (
    arm_view, canonical, digest, validate_submission, feedback_to_own_arm,
    trace_event, SUBMISSION_SCHEMA,
)
from scripts.arena_m_visible_pulse import ROOT, REGISTRY, composer, backend, build as m1_build, stimulus_only_replace, public_pulse
from scripts.arena_m_visible_verify import verify

METHOD = "short-e1-own-feedback-parameter-step/0.1"
POLICY = "LATE_OVERSHOOT_BOTH_POINTS_DOUBLE_SHARED_RESPONSE_TIME_ONCE"
BASE_DIR = ROOT / "experiments" / "e1"
PARENT_RUN = "https://github.com/yudocyudoc/IGC/actions/runs/40271768284"
PARENT_SOURCE_SHA = {
    "native-graph.json": "6cfa1d29c6f46743dbff0888e234a69d9c928b382f33608ef9206b4b4cd695cd",
    "submission.json": "294ddb56d011a72fc0ecf34bae1f947590c10f2a7a31bce4fb3aad4421254615",
    "memory-event.json": "4e1e6f036e32951bc707a0d0c8ca6e551bcbf4fea72e709d22e7c74c01f620cb",
    "g2-construction-report.json": "130379385992b0be7a6fe3aa56bd3492abfb568e6e128f04af9eff37f2c604a1",
    "m-visible_res.csv": "6201a54912096fa96178d8b641016730f8c0a835f637af7f65003a3fce129af9",
}


def read_parent(directory):
    directory = Path(directory).resolve()
    loaded = {}
    for name, expected in PARENT_SOURCE_SHA.items():
        path = directory / name
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError("PARENT_M1_ARTIFACT_BYTES_CHANGED:" + name)
        loaded[name] = raw
    return (
        json.loads(loaded["native-graph.json"]),
        json.loads(loaded["submission.json"]),
        json.loads(loaded["memory-event.json"]),
        json.loads(loaded["g2-construction-report.json"]),
        list(csv.DictReader(loaded["m-visible_res.csv"].decode("utf-8-sig").splitlines())),
    )


def preflight_parent(visible, parent_native, parent_sub, parent_event, reported, rows, catalog):
    view,_,_ = public_pulse(visible)
    # Use parent from historical CI, but additionally reconstruct the same M1
    # independent model with current unchanged M1 generator to detect drift.
    _,_, expected_native, expected_sub, expected_event,_ = m1_build(visible)
    if (parent_native != expected_native or parent_sub != expected_sub
            or parent_event != expected_event):
        raise ValueError("M1_PARENT_NOT_IDENTICAL_TO_INDEPENDENT_SOURCE")
    if parent_sub["iteration"] != 0 or parent_sub["status"] != "PROPOSED":
        raise ValueError("INVALID_M1_LINEAGE")
    if validate_submission(view, parent_sub) != digest(parent_sub):
        raise ValueError("INVALID_PARENT_SUBMISSION")
    if digest({k:v for k,v in parent_event.items() if k != "event_hash"}) != parent_event["event_hash"]:
        raise ValueError("PARENT_LEDGER_HASH_MISMATCH")
    result = verify(rows, visible, parent_native, catalog)
    if result["status"] != "G2_SIMULATED_CONDITIONALLY":
        raise ValueError("INVALID_M1_G2_STATUS")
    if (reported.get("construction_only") is not True
        or reported.get("g3_heldout") != "NOT_RUN"
        or abs(reported.get("rmse_items", float("nan")) - result["rmse_items"]) > 1e-7
        or len(reported.get("observations",[])) != len(result["observations"])):
        raise ValueError("M1_REPORT_DOES_NOT_MATCH_ACTUAL_CSV")
    for a,b in zip(reported["observations"], result["observations"]):
        if any(abs(a[k]-b[k]) > 1e-7 for k in ("time","observed","simulated","residual")):
            raise ValueError("M1_REPORT_TAMPERED")
    return view, result


def own_policy(verified_report, parent_graph, classes):
    points={p["time"]:p["residual"] for p in verified_report["observations"]}
    if not (2.0 in points and 4.0 in points):
        return None, "NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS"
    if not (points[2.0]>0.1 and points[4.0]>0.1):
        return None, "NO_CONSISTENT_LATE_OVERSHOOT_OVER_THRESHOLD"
    revised=copy.deepcopy(parent_graph)
    edits=[]
    for instance in revised["instances"]:
        if instance["role"] not in ("preparation","dispatch"):
            continue
        spec=classes[instance["class_id"]]["parameters"]["responseTime"]
        previous=instance["parameters"]["responseTime"]
        value=previous*2
        if type(previous) not in (int,float) or not math.isfinite(previous):
            raise ValueError("INVALID_PARENT_RESPONSE_TIME")
        if not spec["min"]<=value<=spec["max"]:
            return None, "RESPONSE_TIME_DOUBLING_OUT_OF_CATALOG_BOUNDS"
        instance["parameters"]["responseTime"]=value
        edits.append({"instance_id":instance["id"],"parameter":"responseTime",
                      "before":previous,"after":value,"catalog_bounds":[spec["min"],spec["max"]]})
    if len(edits)!=2:
        raise ValueError("EXPECTED_TWO_ORIGINAL_E1_QUEUES")
    # Both delays share one scalar multiplier, reducing degrees of freedom.
    if len({e["before"] for e in edits})!=1:
        raise ValueError("UNIDENTIFIABLE_ASYMMETRIC_DELAY_STEP")
    return (revised, edits), None


def revise(visible, parent_native, parent_sub, parent_event, parent_report, rows, catalog):
    view, rate, duration = public_pulse(visible)
    if (visible.get("iteration_limit") != 2 or
        visible.get("resources", {}).get("max_model_proposals") != 1 or
        visible.get("resources", {}).get("max_simulations") != 2):
        raise ValueError("M2_REQUIRES_EXACT_ORIGINAL_TWO_ITERATION_ONE_PROPOSAL_TWO_SIMULATION_BUDGET")
    view, checked=preflight_parent(visible,parent_native,parent_sub,parent_event,
                                  parent_report,rows,catalog)
    cfg,classes,_ = composer.load_registry(REGISTRY)
    model=parent_native["graph"]
    if parent_native.get("arm_id")!="M":
        raise ValueError("CROSS_ARM_NATIVE_MODEL")
    selection, reason=own_policy(checked, model, classes)
    if selection is None:
        return {"status":"ABSTAINED","reason":reason,
                "parent_sha256":digest(parent_native),"no_model_proposed":True}, None
    graph,edits=selection
    composer.check_graph(graph,cfg,classes)
    orig_key=parent_native["canonical_graph_sha256"].split(":")[-1]
    if composer.canonical(graph)!=orig_key:
        raise ValueError("M2_CHANGED_MOLECULAR_TOPOLOGY")
    # Render through ORIGINAL Short backend. M2 changes nothing in molecules;
    # only their two catalog-bounded instance parameters.
    name="MolecularArenaM2_"+orig_key[:12]
    text=stimulus_only_replace(backend.render_model(name,graph,cfg,classes),rate,duration)
    package="\n".join(["within;","package ArenaM2Generated",text,
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaM2Generated;",""])
    if "der(" in text or "when " in text:
        raise ValueError("UNAUTHORIZED_DYNAMIC_EQUATION")
    feedback=feedback_to_own_arm(view,parent_sub,submission_hash=digest(parent_sub),
         technical_diagnostics=[
         {"gate":"G2","status":"PASS","details":"M1 OpenModelica simulated; typed material conservation verified",
          "source_artifact_hash":digest(checked)},
         {"gate":"G3","status":"PARTIAL","details":"Construction residuals only; heldout NOT_RUN; M1 late overshoot",
          "source_artifact_hash":digest(checked)},
         ])
    native={
        "schema":"igc-arena-m-typed-hypothesis-revision/0.1",
        "arm_id":"M","method":METHOD,
        "visible_input_sha256":view["input_hash"],"parent_native_hash":digest(parent_native),
        "parent_revision_id":parent_sub["hypothesis_ids"][0]+":r0",
        "canonical_graph_sha256":parent_native["canonical_graph_sha256"],
        "graph":graph,
        "selection_policy":POLICY,
        "selection_input":"VERIFIED_OWN_M1_G2_CONSTRUCTION_RESIDUALS",
        "parameter_edits":edits,
        "not_fitted":"ONE_HEURISTIC_MULTIPLICATIVE_STEP_NO_OPTIMIZER",
        "candidate_universe_count":1,
        "role_mapping_assumptions":parent_native["role_mapping_assumptions"],
        "experimental_status":"REVISED_USING_CONSTRUCTION_NOT_NEW_PREDICTION",
    }
    submission={
        "schema":SUBMISSION_SCHEMA,"arm_id":"M",
        "round_id":visible["round_id"],"iteration":1,
        "parent_revision_id":native["parent_revision_id"],
        "native_artifact_sha256":digest(native),"method_version":METHOD,
        "hypothesis_ids":[parent_sub["hypothesis_ids"][0]+":r1"],
        "status":"PROPOSED",
        "unknowns":["ROLE_PROJECTION_UNVERIFIED","M2_NOT_IDENTIFIED_FROM_HELDOUT",
                    "SHARED_RESPONSE_TIME_HEURISTIC_NOT_CALIBRATION"],
        "assumption_ids":["SHORT_E1_ORIGINAL_MOLECULES","M1_PARENT_FIXED_TOPOLOGY",
                          "MULTIPLICATIVE_LATE_OVERSHOOT_POLICY"],
        "evidence_refs":[visible["source_snapshot_hash"]],
        "notes":"One M-own-feedback revision, same E1 topology and public construction pulse; no optimizer, rival models or hidden evidence."
    }
    validate_submission(view,submission)
    event_feedback=trace_event(arm_id="M",round_id=visible["round_id"],
         event_type="FEEDBACK_DELIVERED",iteration=0,
         source_hash=view["input_hash"],payload_hash=digest(feedback),
         previous_event_hash=parent_event["event_hash"])
    event_revised=trace_event(arm_id="M",round_id=visible["round_id"],
         event_type="HYPOTHESIS_REVISED",iteration=1,
         source_hash=view["input_hash"],payload_hash=digest(submission),
         previous_event_hash=event_feedback["event_hash"])
    receipt={
        "schema":"igc-arena-m2-translation/0.1","source_native_hash":digest(native),
        "generated_modelica_hash":"sha256:"+hashlib.sha256(package.encode()).hexdigest(),
        "graph_topology_unchanged":True,"wrapper_source_edited":False,
        "explicit_parameters_only":edits,"source_stimulus":{"rate":rate,"duration":duration},
        "one_revision_model":True,"g0":"CONDITIONAL_ROLE_PROJECTION",
        "g2":"NOT_RUN_BY_GENERATOR","g3":"CONSTRUCTION_ONLY_NOT_HELDOUT",
        "parent_technical_run":PARENT_RUN
    }
    return {"status":"PROPOSED","model_name":name,"modelica":package,
            "native":native,"submission":submission,"feedback":feedback,
            "events":[event_feedback,event_revised],"translation_receipt":receipt,
            "parent_rmse":checked["rmse_items"]},None


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--visible",required=True,type=Path)
    p.add_argument("--parent-dir",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT):
        raise ValueError("OUTPUT_DIRECTORY_EXISTS_OR_OUTSIDE_REPOSITORY")
    visible=json.loads(a.visible.read_text())
    parent=read_parent(a.parent_dir)
    catalog=json.loads((ROOT/"experiments/e0/catalog.json").read_text())
    result,_=revise(visible,*parent,catalog)
    out.mkdir(parents=True)
    if result["status"]!="PROPOSED":
        (out/"abstention.json").write_bytes(canonical(result)+b"\n")
        print(json.dumps(result))
        return
    for key,fn in [("native","native-graph.json"),("submission","submission.json"),
                   ("feedback","feedback.json"),("events","memory-events.json"),
                   ("translation_receipt","translation-receipt.json")]:
        (out/fn).write_bytes(canonical(result[key])+b"\n")
    (out/"ArenaM2Generated.mo").write_text(result["modelica"])
    name=result["model_name"]
    relative=out.relative_to(ROOT)
    script=[
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
        f'loadFile("/repo/{relative}/ArenaM2Generated.mo");',
        f'checkModel(ArenaM2Generated.{name});',
        'print(getErrorString());',
        f'simulate(ArenaM2Generated.{name},startTime=0,stopTime=4,numberOfIntervals=80,method="dassl",tolerance=1e-8,outputFormat="csv",fileNamePrefix="{relative}/m2-visible");',
        'print(getErrorString());'
    ]
    (out/"simulate.mos").write_text("\n".join(script)+"\n")
    print(json.dumps({"status":"ONE_OWN_M_REVISION_PROPOSED",
        "parent_rmse_construction":result["parent_rmse"],
        "revised_parameters":result["native"]["parameter_edits"],
        "candidate_simulations_planned":1,"out":str(out)}))


if __name__=="__main__":
    main()
