"""A1 read-only H_j evaluator for *supplied* native trajectories.

No model is generated or simulated by this module. Never claim that a fixture,
CSV, or self-declared provenance proves a genuine native solver execution.
No interpolation at observation timestamps; missing samples cause abstention.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from scripts.arena_cafe import observation_ports
from scripts.arena_cafe.native_handoff import need
from scripts.arena_v0_contract import canonical, digest

SCHEMA="igc-arena-cafe-readonly-observation-evaluation/0.1"


def _rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        rd=csv.DictReader(file)
        need(rd.fieldnames is not None and len(set(rd.fieldnames))==len(rd.fieldnames),
             "A1_TRACE_DUPLICATE_COLUMNS")
        records=list(rd)
    need(len(records)>=2,"A1_TRACE_TOO_SHORT")
    return records


def _column(row, name):
    """Resolve a Modelica variable by exact name, never ambiguous suffix."""
    hits=[v for k,v in row.items() if k==name or k.endswith("."+name)]
    need(len(hits)==1,"A1_TRACE_MISSING_OR_AMBIGUOUS_COLUMN:"+name)
    try:
        x=float(hits[0])
    except (ValueError,TypeError) as exc:
        raise ValueError("A1_TRACE_INVALID_NUMERIC:"+name) from exc
    need(math.isfinite(x),"A1_TRACE_NONFINITE:"+name)
    return x


def _candidate_roles(candidate, registry):
    """Original E1 composer authenticates the structural grammar and role IDs."""
    from scripts.arena_m_short_e1 import get_composer
    _, cfg, classes, _ = observation_ports._get_registry(registry)
    composer=get_composer()
    graph=candidate.get("ast")
    need(isinstance(graph,dict),"A1_M_CANDIDATE_AST_REQUIRED")
    composer.check_graph(graph,cfg,classes)
    digest_expected="sha256:"+composer.canonical(graph)
    need(candidate.get("canonical_sha256")==digest_expected,
         "A1_M_CANDIDATE_HASH_MISMATCH")
    originals = {key: ast for key, ast in composer.enumerate_graphs(cfg,classes)}
    need(composer.canonical(graph) in originals,"A1_M_CANDIDATE_NOT_ORIGINAL_E1")
    # The E1 canonical key deliberately omits numerical parameters. Equality
    # with the full frozen AST is needed when NO calibration protocol exists.
    need(graph == originals[composer.canonical(graph)],
         "A1_M_CANDIDATE_PARAMETERS_NOT_FROZEN")
    roles={}
    for instance in graph["instances"]:
        roles.setdefault(instance["role"],[]).append(instance["id"])
    for role in ("source","preparation","receipt"):
        need(len(roles.get(role,[]))==1,"A1_M_CANDIDATE_ROLE_NOT_UNIQUE:"+role)
    return {role:values[0] for role,values in roles.items()}


def _numeric_samples(records, arm, cutoff, roles):
    """Parse solver CSV. All rows must be pre-cutoff or at cutoff, no future."""
    unit_scale=60.0 if arm=="M" else 1.0
    rate_unit_scale=1.0/60.0 if arm=="M" else 1.0
    # flow conversion is applied per minute: units/hour -> orders/minute
    names=("time", "deliveredTotal" if arm=="M" else "delivered",
           roles["source"]+".outflow" if arm=="M" else "inputRate")
    if arm=="M":
        names+= (roles["preparation"]+".completed",)
    parsed=[]
    for row in records:
        fields={name:_column(row,name) for name in names}
        t=fields["time"]*unit_scale
        need(t>=-1e-9 and t<=cutoff+1e-9,"A1_TRACE_FUTURE_OR_NEGATIVE_TIME")
        delivered=fields[names[1]]
        source_rate=fields[names[2]]*rate_unit_scale
        preparation_rate=(fields[names[3]]*rate_unit_scale) if arm=="M" else None
        need(delivered>=-1e-7 and source_rate>=-1e-7 and
             (preparation_rate is None or preparation_rate>=-1e-7),
             "A1_TRACE_NEGATIVE_MATERIAL")
        point={"t_minutes":t,"delivered":delivered,
               "source_per_minute":source_rate,"prep_per_minute":preparation_rate,
               "source_left":source_rate,"prep_left":preparation_rate,
               "source_history":[source_rate],
               "prep_history":[preparation_rate] if arm=="M" else []}
        if parsed and abs(parsed[-1]["t_minutes"]-t)<=1e-9:
            # OMC can emit pre-event, repeated pre-event and post-event
            # at one instant. Stocks must be continuous while flows may jump.
            prior=parsed[-1]
            need(abs(prior["delivered"]-delivered)<=1e-6,
                 "A1_TRACE_CONFLICTING_DUPLICATE_EVENT")
            sh=prior["source_history"]+[source_rate]
            ph=prior["prep_history"]+([preparation_rate] if arm=="M" else [])
            def changes(values):
                return sum(abs(x-y)>1e-6 for x,y in zip(values,values[1:]))
            need(len(sh)<=4 and changes(sh)<=1 and
                 (arm=="D" or changes(ph)<=1),
                 "A1_TRACE_UNRESOLVED_MULTI_EVENT_RATE")
            point["source_left"]=prior["source_left"]
            point["prep_left"]=prior["prep_left"]
            point["source_history"]=sh
            point["prep_history"]=ph
            parsed[-1]=point
        else:
            need(not parsed or t>parsed[-1]["t_minutes"],"A1_TRACE_TIME_BACKWARDS")
            parsed.append(point)
    need(abs(parsed[0]["t_minutes"])<=1e-9 and
         abs(parsed[-1]["t_minutes"]-cutoff)<=1e-8,
         "A1_TRACE_INCOMPLETE_WINDOW")
    need(all(b["delivered"]+1e-7>=a["delivered"]
             for a,b in zip(parsed,parsed[1:])),
         "A1_TRACE_DECREASING_DELIVERED")
    return parsed


def _integrate(samples, field):
    """Trapezoid over declared solver grid; approximate, not exact event counts."""
    cumulative=[0.0]
    for a,b in zip(samples,samples[1:]):
        delta=b["t_minutes"]-a["t_minutes"]
        need(delta>0,"A1_TRACE_NONINCREASING_GRID")
        # Right-hand value at interval start and left-hand value at end.
        # Never interpolate across a legitimate instantaneous rate jump.
        left = b[field.replace("_per_minute","_left")]
        cumulative.append(cumulative[-1]+delta*(a[field]+left)/2)
    return cumulative


def _at(samples, time, values):
    hits=[i for i,p in enumerate(samples) if abs(p["t_minutes"]-time)<=1e-8]
    need(len(hits)==1,"A1_TRACE_SAMPLE_TIME_MISSING_OR_AMBIGUOUS")
    return values[hits[0]]


def evaluate(visible, port, *, trace_csv=None, candidate=None, registry=None):
    """Compare a declared native trajectory without fitting or selecting it.

    Results cannot be promoted to G2/G3: no provenance of the CSV is verified.
    """
    arm=port.get("arm_id")
    condition=port.get("condition_id")
    need(arm in ("D","M"),"A1_HJ_WRONG_ARM")
    expected=observation_ports.port(visible,arm,condition,registry=registry)
    need(port==expected,"A1_HJ_PORT_NOT_BOUND_TO_VISIBLE_EVIDENCE")
    base={
        "schema":SCHEMA,"arm_id":arm,"condition_id":condition,
        "visible_input_hash":digest(visible),
        "source_snapshot_hash":visible["source_snapshot_hash"],
        "port_hash":digest(port),
        "native_generation":"NOT_PERFORMED",
        "native_model_selection":"NOT_PERFORMED",
        "input_trace_provenance":"NOT_AUTHENTICATED_BY_THIS_EVALUATOR",
        "scientific_status":"NOT_ESTABLISHED",
    }
    if trace_csv is None:
        need(candidate is None,"A1_HJ_CANDIDATE_WITHOUT_TRACE")
        return {**base,"status":"ABSTAIN_NO_ADMISSIBLE_NATIVE_TRAJECTORY",
                "comparisons":[],"diagnostic":"H_J_DEFINED_BUT_NOT_EVALUATED"}
    roles={}
    if arm=="M":
        need(candidate is not None and registry is not None,
             "A1_HJ_M_REQUIRES_NATIVE_GRAPH_AND_REGISTRY")
        roles=_candidate_roles(candidate,registry)
    else:
        need(candidate is None,"A1_HJ_D_GRAPH_SHOULD_NOT_BE_E1")
    cutoff=float(visible["observability"]["cutoff_minutes_exact"])
    samples=_numeric_samples(_rows(trace_csv),arm,cutoff,roles)
    source_cumulative=_integrate(samples,"source_per_minute")
    prep_cumulative=_integrate(samples,"prep_per_minute") if arm=="M" else None
    scores=[]
    for point in port["counts_time_grid"]:
        t=float(point["time_minutes_exact"])
        expected_source=int(point["orders_created_cumulative"])
        expected_delivery=int(point["delivered_cumulative"])
        predicted_source=_at(samples,t,source_cumulative)
        predicted_delivery=_at(samples,t,[p["delivered"] for p in samples])
        scores += [
            {"observable":"orders_created_cumulative","t_minutes":t,
             "observed_orders":expected_source,
             "native_prediction":predicted_source,
             "residual_orders":predicted_source-expected_source,
             "operator":"NUMERIC_TRAPEZOID_OVER_MODEL_SOURCE_RATE"},
            {"observable":"delivered_cumulative","t_minutes":t,
             "observed_orders":expected_delivery,
             "native_prediction":predicted_delivery,
             "residual_orders":predicted_delivery-expected_delivery,
             "operator":"DIRECT_NATIVE_DELIVERED_STOCK"},
        ]
    if arm=="M" and condition=="O1":
        n=visible["construction"]["physical_observation"]["n_completed_stage_services"]
        predicted=_at(samples,cutoff,prep_cumulative)
        scores.append({
            "observable":"n_completed_stage_services",
            "t_minutes":cutoff,"observed_orders":n,
            "native_prediction":predicted,"residual_orders":predicted-n,
            "operator":"NUMERIC_TRAPEZOID_OVER_NATIVE_PREPARATION_FLOW",
            "limit":"DISCRETE_COMPLETED_SERVICES_COMPARED_TO_CONTINUOUS_E1_FLOW",
        })
    return {**base,
        "status":"DESCRIPTIVE_HJ_PROBE_ONLY_UNVERIFIED_TRACE",
        "comparisons":scores,
        "sample_count":len(samples),
        "trace_sha256":"sha256:"+__import__("hashlib").sha256(Path(trace_csv).read_bytes()).hexdigest(),
        "notes":[
            "No new original D or M candidate was generated from O0/O1",
            "No native trace origin or solver invocation is authenticated",
            "Trapezoid integration is a numerical approximation, not a recovered event clock",
            "No threshold, ranking, fitting, selection, G2 or G3 verdict is defined",
        ],
    }


def main():
    p=argparse.ArgumentParser(description="Read-only H_j evaluator for native CSVs")
    p.add_argument("--visible",type=Path,required=True)
    p.add_argument("--port",type=Path,required=True)
    p.add_argument("--csv",type=Path)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--registry",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    need(not a.out.exists(),"A1_HJ_REFUSE_OVERWRITE")
    output=evaluate(json.loads(a.visible.read_text()),
                    json.loads(a.port.read_text()),
                    trace_csv=a.csv,
                    candidate=json.loads(a.candidate.read_text()) if a.candidate else None,
                    registry=a.registry)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("xb") as f:
        f.write(canonical(output)+b"\n")
    print(json.dumps({"status":output["status"],"arm_id":output["arm_id"],
                      "condition_id":output["condition_id"],
                      "comparisons":len(output["comparisons"])}))


if __name__=="__main__":
    main()
