"""One bounded Arena-M molecular hypothesis from the original Short E1 composer.

No D/B knowledge, no upstream edits, no calibration or secret-world labels.
Select a single simplest typed composition *before looking at observations*.
The sole Modelica adaptation replaces the original E1 synthetic stimulus with
the published Arena input pulse; all molecular classes and ports stay intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from scripts.arena_v0_contract import (
    arm_view, canonical, digest, SUBMISSION_SCHEMA, validate_submission, trace_event
)

ROOT = Path(__file__).resolve().parents[1]
E1 = ROOT / "experiments" / "e1"
METHOD = "short-e1-one-minimal-molecular-candidate/0.1"
REGISTRY = E1 / "registry.base.json"
sys.path.insert(0, str(E1))
import composer  # noqa: E402 -- ORIGINAL Short E1, verified by Git blob manifest.
import backend   # noqa: E402 -- ORIGINAL Short E1, generates only instantiations.


def public_pulse(visible):
    view = arm_view(visible, "M")
    p = visible["construction"].get("input_profile")
    if not isinstance(p, dict) or set(p) != {"kind", "rate", "duration"} or p["kind"] != "pulse":
        raise ValueError("UNSUPPORTED_PUBLIC_INPUT_PROFILE")
    rate, duration = p["rate"], p["duration"]
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in (rate, duration)):
        raise ValueError("INVALID_PULSE_PARAMETERS")
    if not 0 < rate <= 100 or not 0 < duration <= 8:
        raise ValueError("OUT_OF_BOUND_PUBLIC_PULSE")
    if visible["observability"] != {"stock_unit":"items", "time_unit":"hour",
                                     "observable":"cumulative_delivered"}:
        raise ValueError("SEMANTIC_OBSERVABLE_MAPPING_NOT_ESTABLISHED")
    if visible["resources"].get("max_model_proposals", 0) < 1 or visible["resources"].get("max_simulations", 0) < 1:
        raise ValueError("NO_M_ARM_RESOURCE_BUDGET")
    return view, float(rate), float(duration)


def choose_one(graphs):
    if not graphs:
        raise ValueError("NO_MATCHING_MOLECULE")
    # Complexity prior, NOT evidence fit. E1 generates the graphs from open typed ports.
    # No information-only component or transit stage is added unless compulsory.
    ordered = sorted(graphs, key=lambda k: (
        len(k[1]["instances"]),len(k[1]["links"]),k[0]))
    chosen = ordered[0]
    if sum(x["role"] in ("report","transit","amplifier") for x in chosen[1]["instances"]) != 0:
        raise ValueError("MINIMAL_GRAPH_MISSING_OR_REGISTRY_CHANGED")
    return chosen


def stimulus_only_replace(original, rate, duration):
    historical = "\n".join([
        "    Modelica.Blocks.Sources.Pulse pulse(amplitude=6,period=4,width=40,startTime=1);",
        "    Modelica.Blocks.Sources.Step step(height=6,startTime=1);",
        "    Modelica.Blocks.Sources.Ramp ramp(height=6,duration=3,startTime=1);",
        "    Modelica.Blocks.Sources.Pulse highPulse(amplitude=14,period=4,width=40,startTime=1);",
        "    Modelica.Blocks.Sources.RealExpression stimulus(",
        "      y=if probe==1 then pulse.y else if probe==2 then step.y else",
        "        if probe==3 then ramp.y else highPulse.y);",
    ])
    if original.count(historical) != 1:
        raise ValueError("UPSTREAM_E1_STIMULUS_INTERFACE_CHANGED")
    rate_literal=format(rate,".15g")
    duration_literal=format(duration,".15g")
    public = (
        "    // Only publicly supplied experimental stimulus; molecule internals unchanged.\n"
        "    Modelica.Blocks.Sources.RealExpression stimulus("
        f"y=if time < {duration_literal} then {rate_literal} else 0);"
    )
    return original.replace(historical,public)


def build(visible):
    view, rate, duration = public_pulse(visible)
    cfg,classes,_ = composer.load_registry(REGISTRY)
    graphs = composer.enumerate_graphs(cfg,classes)
    key,graph = choose_one(graphs)
    composer.check_graph(graph,cfg,classes)
    model_name="MolecularArena_"+key[:12]
    native = {
        "schema":"igc-arena-m-typed-hypothesis/0.1",
        "arm_id":"M", "method":METHOD,
        "visible_input_sha256":view["input_hash"],
        "registry":"short/E1/registry.base.json",
        "registry_hash":digest(cfg),
        "selection_policy":"MIN_INSTANCES_THEN_LINKS_THEN_CANONICAL_HASH",
        "selection_used_construction_observations":False,
        "candidate_universe_count":len(graphs),
        "canonical_graph_sha256":"sha256:"+key,
        "graph":graph,
        "role_mapping_assumptions":{
            "Order":"abstract incoming work items",
            "ReadyOrder":"latent processed work items",
            "Shipment":"abstract delivered work items",
        },
        "parameters":"FIXED_E1_REGISTRY_NOT_FITTED",
        "methodological_limit":"EXPLICIT_ROLE_PROJECTION_NOT_EMPIRICALLY_VERIFIED"
    }
    model=backend.render_model(model_name,graph,cfg,classes)
    model=stimulus_only_replace(model,rate,duration)
    text="\n".join(["within;","package ArenaMGenerated",model,
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaMGenerated;",""])
    if "der(" in model or "when " in model:
        raise ValueError("DYNAMICS_INJECTED_BY_M_ADAPTER")
    submission={
        "schema":SUBMISSION_SCHEMA,"arm_id":"M",
        "round_id":visible["round_id"],"iteration":0,"parent_revision_id":None,
        "native_artifact_sha256":digest(native),"method_version":METHOD,
        "hypothesis_ids":["M-"+key[:12]],
        "status":"PROPOSED",
        "unknowns":[
            "ROLE_PROJECTION_UNVERIFIED",
            "PARAMETERS_NOT_FIT_TO_OBSERVATIONS",
            "NO_STRUCTURAL_IDENTIFICATION",
        ],
        "assumption_ids":[
            "SOURCE_SHORT_E1_TYPED_ROLES",
            "OCCAM_MIN_COMPLEXITY_WITHOUT_G3",
            "FIXED_E1_PARAMETERS",
        ],
        "evidence_refs":[visible["source_snapshot_hash"]],
        "notes":"One simplest molecular topology submitted before construction-output evaluation; external stimulus only; no claim of best fit."
    }
    validate_submission(view,submission)
    event=trace_event(arm_id="M",round_id=visible["round_id"],
        event_type="HYPOTHESIS_PROPOSED",iteration=0,
        source_hash=view["input_hash"],payload_hash=digest(submission))
    receipt={
        "schema":"igc-arena-m-visible-pulse-translation/0.1",
        "arm_id":"M","source_native_hash":digest(native),
        "source_stimulus":{"kind":"pulse","rate":rate,"duration":duration,
                           "unit":"items/hour"},
        "generated_modelica_sha256":"sha256:"+hashlib.sha256(text.encode()).hexdigest(),
        "rewritten_source":"ONLY_E1_EXTERNAL_PROBE_BLOCK",
        "wrapper_source_edited":False,
        "graph_edited":False,
        "number_models_proposed":1,
        "number_simulations_planned":1,
        "g0_status":"CONDITIONAL_SEMANTIC_ROLE_PROJECTION",
        "g1_status":"NOT_FULLY_CERTIFIED",
        "g2_status":"NOT_RUN_BY_GENERATOR",
        "g3_status":"NOT_RUN_BY_GENERATOR",
    }
    return model_name,text,native,submission,event,receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    a.out = a.out.resolve()
    if not a.out.is_relative_to(ROOT):
        raise ValueError("OUTPUT_OUTSIDE_REPOSITORY")
    if a.out.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    name,modelica,native,submission,event,receipt=build(json.loads(a.input.read_text()))
    a.out.mkdir(parents=True)
    (a.out/"ArenaMGenerated.mo").write_text(modelica)
    for fname,payload in [
        ("native-graph.json",native),("submission.json",submission),
        ("memory-event.json",event),("translation-receipt.json",receipt)]:
        (a.out/fname).write_bytes(canonical(payload)+b"\n")
    # Original backend wrote default probe to test broad behavior; here the
    # public pulse is the *only* experimental source.
    cmds=[
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
        'loadFile("/repo/'+str(a.out.relative_to(ROOT))+'/ArenaMGenerated.mo");',
        'checkModel(ArenaMGenerated.'+name+');',
        'print(getErrorString());',
        'simulate(ArenaMGenerated.'+name+',startTime=0,stopTime=4,numberOfIntervals=80,method="dassl",tolerance=1e-8,outputFormat="csv",fileNamePrefix="'+str(a.out.relative_to(ROOT))+'/m-visible");',
        'print(getErrorString());'
    ]
    (a.out/"simulate.mos").write_text("\n".join(cmds)+"\n")
    print(json.dumps({"arm":"M","model":name,"graph_sha":native["canonical_graph_sha256"],
                      "candidates_enumerated":native["candidate_universe_count"],
                      "submitted":1,"g3":"NOT_RUN","output":str(a.out)}))


if __name__=="__main__":
    main()
