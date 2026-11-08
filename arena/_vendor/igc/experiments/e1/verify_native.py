#!/usr/bin/env python3
"""Native E1 integration regression. Never a truth oracle or structural scorer."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
FIELDS=("dispatchRate","deliveryRate","inTransit","reportedDeliveryRate","deliveredTotal")
BOUND=1e-4  # E1 regression-only. NOT calibrated for E2 inference.


def val(row,name):
    hits=[float(v) for k,v in row.items() if k==name or k.endswith("."+name)]
    if len(hits)!=1 or not math.isfinite(hits[0]):
        raise ValueError("INVALID_SERIES_FIELD:"+name)
    return hits[0]


def trace(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        raw=list(csv.DictReader(f))
    data=[]
    for r in raw:
        time=val(r,"time")
        if data and time < val(data[-1],"time") - 1e-8:
            raise ValueError("TIME_BACKWARDS")
        for f in FIELDS:val(r,f)
        if data and abs(time-val(data[-1],"time"))<1e-8:
            data[-1]=r
        else:
            data.append(r)
    if len(data)<60:
        raise ValueError("TOO_FEW_REAL_OM_ROWS")
    return data


def compare(a,b,fields):
    if len(a)!=len(b):raise ValueError("TIME_GRID_SIZE_DIFFERENCE")
    err=0.0
    for x,y in zip(a,b):
        if abs(val(x,"time")-val(y,"time"))>1e-7:
            raise ValueError("MISALIGNED_GRID")
        for f in fields:
            err=max(err,abs(val(x,f)-val(y,f)))
    return err


def verify(root):
    results={}
    report={}
    for variant,target in (("base",6),("extended",15)):
        path=root/variant
        models=json.loads((path/"models.json").read_text())
        if len(models)!=target:
            raise ValueError("WRONG_GENERATED_COUNT:"+variant)
        all_traces={}
        for m in models:
            series=trace(path/"results"/(m["model"]+"_res.csv"))
            if val(series[-1],"deliveredTotal")<=0:
                raise ValueError("NO_DELIVERIES:"+m["model"])
            for row in series:
                for f in ("inTransit","deliveredTotal","deliveryRate","reportedDeliveryRate"):
                    if val(row,f)<-BOUND:
                        raise ValueError("NEGATIVE_RATE_OR_STOCK")
            all_traces[m["model"]]=series
        report[variant]={"models":models,"traces":all_traces}
        results[variant]={"generated":target,"native_csv":len(all_traces),
                          "distinct_canonical":len({m["hash"] for m in models})}
    base={m["hash"] for m in report["base"]["models"]}
    ext={m["hash"] for m in report["extended"]["models"]}
    if not base.issubset(ext):
        raise ValueError("ORIGINAL_CANONICALS_LOST")
    if len(ext-base)!=9:
        raise ValueError("REGISTRY_EXTENDED_NO_NEW_STRUCTURES")

    def physical_key(model):
        # The role sequence is a physical composition fingerprint, not a world label.
        return tuple((x["class_id"],x["role"]) for x in model["instances"]
                     if x["role"] not in ("report","amplifier"))
    ref={}
    for variant in report:
        for m in report[variant]["models"]:
            key=physical_key(m)
            series=report[variant]["traces"][m["model"]]
            physical=("dispatchRate","deliveryRate","inTransit","deliveredTotal")
            if key in ref:
                maxdiff=compare(series,ref[key],physical)
                if maxdiff>BOUND:
                    raise ValueError("INFORMATION_MODULE_CHANGED_PHYSICAL_FLOW")
            else:
                ref[key]=series
    filters=[]
    gains=[]
    for m in report["extended"]["models"]:
        roles=m["roles"]
        series=report["extended"]["traces"][m["model"]]
        delta=max(abs(val(r,"reportedDeliveryRate")-val(r,"deliveryRate")) for r in series)
        if roles.get("report",0):filters.append(delta)
        if roles.get("amplifier",0):gains.append(delta)
    if not filters or max(filters)<0.001 or not gains or max(gains)<0.001:
        raise ValueError("INFORMATION_COMPONENTS_WITHOUT_EFFECT")
    return {
        "technical":"PASS","methodological":"COMPOSITION_ENGINEERING_ONLY",
        "world_identification":"NOT_RUN","llm_construction":"NOT_RUN",
        "base":results["base"],"extended":results["extended"],
        "new_canonicals_from_registry_swap":len(ext-base),
        "maximum_physical_variance_with_info_modules":max(
            compare(s,ref[physical_key(m)],("dispatchRate","deliveryRate","inTransit","deliveredTotal"))
            for variant in report for m in report[variant]["models"]
            for s in [report[variant]["traces"][m["model"]]]),
        "filter_report_effect_max":max(filters),
        "gain_report_effect_max":max(gains),
        "warning":"Graphs are inferred from declared molecular contracts, not causal evidence about an unknown world."
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    report=verify(args.root)
    args.out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("E1_REAL_OPENMODELICA",json.dumps(report))


if __name__=="__main__":
    main()
