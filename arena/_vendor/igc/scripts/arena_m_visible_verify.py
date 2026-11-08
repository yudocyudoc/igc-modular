"""Independent numerical audit of one Arena-M OpenModelica trace.

Material stocks are discovered from typed STATE ports on the native Short E1
graph, NOT from the telemetry variable inTransit (Shipment-only in E1).
This is descriptive construction-data comparison, not heldout G3 or causal proof.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path


def get(row, name):
    matches=[v for k,v in row.items() if k==name or k.endswith("."+name)]
    if len(matches)!=1:
        raise ValueError("MISSING_OR_DUPLICATE_COLUMN:"+name)
    value=float(matches[0])
    if not math.isfinite(value):
        raise ValueError("NONFINITE_VALUE:"+name)
    return value


def material_stock_ports(native, catalog):
    if native.get("arm_id") != "M" or native.get("method") not in {"short-e1-one-minimal-molecular-candidate/0.1", "short-e1-own-feedback-parameter-step/0.1"}:
        raise ValueError("NOT_ORIGINAL_M_NATIVE_SUBMISSION")
    classes={c["id"]:c for c in catalog["classes"]}
    ports=[]
    for instance in native["graph"]["instances"]:
        if instance["class_id"] not in classes:
            raise ValueError("UNREGISTERED_MOLECULE_IN_NATIVE")
        cls=classes[instance["class_id"]]
        for port in cls["ports"]:
            # Terminal delivery is counted once from deliveredTotal, never twice.
            if port["direction"]=="out" and port["type"].startswith("STATE<") and instance["role"]!="receipt":
                if port.get("unit")!="units":
                    raise ValueError("MATERIAL_STOCK_UNIT_NOT_DECLARED")
                ports.append(instance["id"]+"."+port["name"])
    if not ports or len(ports)!=len(set(ports)):
        raise ValueError("MATERIAL_STOCK_PORTS_MISSING_OR_DUPLICATE")
    return ports


def verify(rows, visible, native, catalog):
    material_ports=material_stock_ports(native,catalog)
    times=[]
    for row in rows:
        t=get(row,"time")
        if times and t < times[-1][0]-1e-9:
            raise ValueError("TIME_BACKWARDS")
        if times and abs(t-times[-1][0])<1e-9:
            times[-1]=(t,row)
        else:
            times.append((t,row))
    if len(times)<70:
        raise ValueError("MISSING_REAL_MODELICA_SAMPLES")
    rate=float(visible["construction"]["input_profile"]["rate"])
    duration=float(visible["construction"]["input_profile"]["duration"])
    max_balance=0.0
    for t,row in times:
        d=get(row,"deliveredTotal")
        w=sum(get(row,name) for name in material_ports)
        if min(d,w)<-0.001:
            raise ValueError("NEGATIVE_MATERIAL_STOCK")
        # Also check each individual stock, not just aggregate which could mask negatives.
        if any(get(row,name)<-0.001 for name in material_ports):
            raise ValueError("NEGATIVE_MATERIAL_STOCK")
        residual=abs(d+w - rate*min(t,duration))
        max_balance=max(max_balance,residual)
    if max_balance>0.015:
        raise ValueError("GLOBAL_MATERIAL_BALANCE_FAILURE")
    points=[]
    for obs in visible["construction"]["observations"]:
        wanted=float(obs["t"])
        hits=[row for t,row in times if abs(t-wanted)<1e-6]
        if len(hits)!=1:
            raise ValueError("OBS_TIME_NOT_IN_OM_GRID")
        simulated=get(hits[0],"deliveredTotal")
        observed=float(obs["delivered"])
        points.append({"time":wanted,"observed":observed,"simulated":simulated,
                       "residual":simulated-observed})
    nonzero=[p for p in points if p["time"]>0]
    rmse=math.sqrt(sum(p["residual"]**2 for p in nonzero)/len(nonzero))
    rmse_all=math.sqrt(sum(p["residual"]**2 for p in points)/len(points))
    return {"schema":"igc-arena-m-common-pulse-check/0.3",
       "engine":"OPENMODELICA_REAL_CSV","status":"G2_SIMULATED_CONDITIONALLY",
       "input_pulse":visible["construction"]["input_profile"],
       "material_stock_ports":material_ports,
       "excluded_non_global_stock_telemetry":"inTransit",
       "technical_samples":len(times),"max_material_balance_residual":max_balance,
       "construction_only":True,"observations":points,"rmse_items":rmse,
       "rmse_all_observations_items":rmse_all,
       "rmse_noninitial_observations_items":rmse,
       "rmse_denominators":{"all_observations":len(points),
                            "noninitial_observations":len(nonzero)},
       "g3_construction_status":"DESCRIPTIVE_ONLY_NO_INSTRUMENT_BOUND",
       "reserved_evaluation_status":"NOT_RUN",
       "g3_heldout":"NOT_RUN",  # legacy archived M1 key; DO NOT interpret holdout as G3
       "g0_semantic_role_mapping":"PROVISIONAL",
       "causal_identification":"NOT_DEMONSTRATED",
       "warning":"The E1 inTransit signal only counts Shipment. This audit sums all typed material states and terminal deliveries."}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv",required=True,type=Path)
    ap.add_argument("--visible",required=True,type=Path)
    ap.add_argument("--native",required=True,type=Path)
    ap.add_argument("--catalog",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    a=ap.parse_args()
    with a.csv.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    payload=verify(rows,json.loads(a.visible.read_text()),
                   json.loads(a.native.read_text()),json.loads(a.catalog.read_text()))
    a.out.write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps(payload))


if __name__=="__main__":
    main()
