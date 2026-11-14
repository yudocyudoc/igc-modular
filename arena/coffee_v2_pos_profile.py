"""Coffee V2.1 P02/P05 *minimum*: canonical paid-POS time operator.

Read-only public construction [0,60) only. No private truth, post-cutoff
extrapolation, arrival inference, service-time calibration or model revision.
A payment is a payment; a video presence proxy is not a customer arrival.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import sys

from .common import ArenaError, digest, read_json, write_json
from .coffee_domain import build_case
from . import coffee_dm_campaign as dm
from .coffee_adapters.shared import sha_bytes

SCHEMA="arena.coffee-v2.public-observation-profiles/1"
CONSTRUCTION_END=Decimal("60")
NOMINAL_END=Decimal("103.237")
# Predeclared operators; NOT selected retrospectively by fit or by G3.
WIDTHS=(5,15)
PAID_OPERATOR="P02-PAID-POS-HALFOPEN-BINS/1"
PRESENCE_OPERATOR="P05-VIDEO-PRESENCE-WEIGHTED-MEAN/1"

def need(ok,reason):
    if not ok:raise ArenaError("COFFEE_V2_PROFILE_"+reason)

def decimal(value,name,*,min_value=Decimal(0),max_value=CONSTRUCTION_END):
    try: out=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):
        raise ArenaError("COFFEE_V2_PROFILE_BAD_"+name) from None
    need(out.is_finite() and min_value<=out<=max_value,"BAD_"+name)
    return out

def observe(public,case,*,widths=WIDTHS):
    """The actual view is reconstructed ONLY by the old custody boundary."""
    need(type(public) is dict and public.get("schema")=="arena.coffee-peak.public-b0/1"
         and public.get("evidence_kind")=="SYNTHETIC_POS_AND_VIDEO_PROXY"
         and public.get("condition")=="B0"
         and type(public.get("selection")) is dict
         and type(case) is dict
         and case.get("public_sha256")==digest(public)
         and case.get("source_package_sha256")==public.get("source_package_sha256")
         and case.get("condition")=="B0"
         and case.get("frontier")=="PAID_ORDER_TO_PICKUP"
         and public.get("time",{}).get("future_pos_and_truth")=="NOT_RELEASED"
         and decimal(public["time"].get("construction_end_exclusive"),
                     "CONSTRUCTION_END")==CONSTRUCTION_END
         and decimal(public["time"].get("window_end"),
                     "NOMINAL_WINDOW",max_value=Decimal(200))==NOMINAL_END,
         "NOT_A_CUSTODY_PUBLIC_B0_CASE")
    need(type(widths) is tuple and bool(widths)
         and len(set(widths))==len(widths)
         and all(type(w) is int and 0<w<=60 and 60%w==0 for w in widths),
         "INVALID_TIME_BIN_OPERATORS")
    pos=public.get("pos_records")
    lines=public.get("pos_line_items")
    proxy=public.get("video_proxy")
    need(type(pos) is list and type(lines) is list and type(proxy) is list,
         "PUBLIC_OBSERVATIONS_UNAVAILABLE")
    payments=[]
    paid_ids={}
    record_ids=set()
    refund=0
    for p in pos:
        need(type(p) is dict and p.get("synthetic")=="True"
             and p.get("source_class")=="synthetic_pos_view"
             and p.get("pos_record_id") not in record_ids
             and type(p.get("pos_record_id")) is str and bool(p["pos_record_id"]),
             "PAYMENT_SOURCE_INVALID")
        record_ids.add(p["pos_record_id"])
        t=decimal(p.get("timestamp_min_from_peak_start"),"PAYMENT_TIME")
        need(t<CONSTRUCTION_END,"FUTURE_PAYMENT_LEAK")
        kind=p.get("pos_record_type")
        if kind=="sale":
            need(p.get("sale_status")=="paid_synthetic"
                 and p.get("order_id") not in paid_ids
                 and bool(p.get("order_id")), "PAID_ORDER_NOT_UNIQUE")
            paid_ids[p["order_id"]]=(p["pos_record_id"],t)
            payments.append(t)
        elif kind=="refund":
            need(p.get("sale_status")=="refunded_synthetic",
                 "REFUND_NOT_DECLARED")
            refund+=1
        else:need(False,"UNSUPPORTED_POS_EVENT_TYPE")
    need(len(payments)>0 and
         len(payments)==case.get("input",{}).get("public_paid_order_count_before_cut")
         and Decimal(str(case["input"]["rate_orders_per_hour"]))==
             Decimal(len(payments)),"POS_COUNT_RATE_NOT_IN_CASE")
    item_ids=set()
    sku_qty={}
    for line in lines:
        need(type(line) is dict and line.get("synthetic")=="True"
             and line.get("source_class")=="synthetic_pos_line_item"
             and bool(line.get("pos_line_id"))
             and line["pos_line_id"] not in item_ids
             and line.get("order_id") in paid_ids
             and line.get("pos_record_id")==paid_ids[line["order_id"]][0],
             "ITEM_PARENT_NOT_AUTHENTIC_PAID_ORDER")
        t=decimal(line.get("timestamp_min_from_peak_start"),"LINE_TIME")
        need(t==paid_ids[line["order_id"]][1],"LINE_NOT_AT_PAID_TIMESTAMP")
        qty=decimal(line.get("quantity"),"LINE_QUANTITY",
                    min_value=Decimal(1),max_value=Decimal(1000))
        need(qty==int(qty),"FRACTIONAL_ITEM_QUANTITY")
        sku=line.get("synthetic_sku")
        need(type(sku) is str and bool(sku) and len(sku)<=64,
             "MISSING_ITEM_ARCHETYPE")
        sku_qty[sku]=sku_qty.get(sku,0)+int(qty)
        item_ids.add(line["pos_line_id"])
    minutes={}
    for row in proxy:
        need(type(row) is dict and row.get("source_class")==
             "video_customer_presence_proxy_not_arrival_count"
             and row.get("synthetic")=="False",
             "PRESENCE_IS_NOT_ARRIVAL")
        minute=decimal(row.get("minute_from_peak_start"),"PROXY_MINUTE")
        need(minute==int(minute) and 0<=minute<CONSTRUCTION_END
             and int(minute) not in minutes,
             "PROXY_MINUTES_NOT_DISJOINT")
        samples=decimal(row.get("sample_seconds"),"SAMPLES_PER_MINUTE",
                         min_value=Decimal(1))
        need(samples==60,"V1_MINUTE_PROXY_MUST_COVER_60_SAMPLE_SECONDS")
        value=decimal(row.get("mean_public_customer_tracklets_per_second"),
                      "TRACKLET_PROXY",max_value=Decimal(1_000_000))
        queue=decimal(row.get("mean_manual_queue_marks_per_second"),
                      "QUEUE_PROXY",max_value=Decimal(1_000_000))
        minutes[int(minute)]=(samples,value,queue)
    need(set(minutes)==set(range(60)),"MISSING_VIDEO_MINUTE_COVERAGE")
    result=[]
    for width in widths:
        bins=[]
        for index in range(60//width):
            begin=Decimal(index*width)
            end=Decimal((index+1)*width)
            count=sum(begin<=t<end for t in payments)
            values=[minutes[m] for m in range(index*width,(index+1)*width)]
            weight=sum((x[0] for x in values),Decimal(0))
            mean_track=sum((x[0]*x[1] for x in values),Decimal(0))/weight
            mean_queue=sum((x[0]*x[2] for x in values),Decimal(0))/weight
            bins.append({
                "start_min":float(begin),"end_min_exclusive":float(end),
                "synthetic_paid_orders":count,
                "paid_rate_equivalent_orders_per_hour":
                    float(Decimal(count)*60/Decimal(width)),
                "mean_public_visible_tracklets_per_sample_second":
                    round(float(mean_track),6),
                "mean_manual_queue_marks_per_sample_second":
                    round(float(mean_queue),6),
                "proxy_seconds_summarized":int(weight),
                "paid_is_not_arrival_or_pickup":True,
                "presence_is_not_unique_customers":True,
            })
        need(sum(x["synthetic_paid_orders"] for x in bins)==len(payments)
             and all(x["proxy_seconds_summarized"]==width*60 for x in bins),
             "BIN_CONSERVATION_FAILED")
        result.append({
            "bin_width_min":width,
            "paid_operator":PAID_OPERATOR,
            "presence_operator":PRESENCE_OPERATOR,
            "interval_semantics":"HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE",
            "bins":bins,
            "sum_paid_orders":len(payments),
            "max_paid_rate_equivalent_orders_per_hour":
                max(b["paid_rate_equivalent_orders_per_hour"] for b in bins),
        })
    need(result[0]["bin_width_min"]==5 and
         result[1]["bin_width_min"]==15 if widths==WIDTHS else True,
         "PRIMARY_WIDTH_NOT_PREDECLARED")
    return {
      "schema":SCHEMA,"phase":"P02_P05_MINIMAL_PUBLIC_CONSTRUCTION",
      "case_sha256":digest(case),"public_sha256":case["public_sha256"],
      "source_package_sha256":"sha256:"+case["source_package_sha256"],
      "data_source":"PUBLIC_SYNTHETIC_POS_OBSERVATION_MODEL",
      "not_an_observation_of_real_business_demand":True,
      "construction_window_minutes":[0,60],
      "post_construction":[60,103.237],
      "post_construction_status":"UNKNOWN_HELDOUT_NOT_ZERO_NOT_EXTRAPOLATED",
      "original_case_v1_constant_rate_orders_per_hour":
          case["input"]["rate_orders_per_hour"],
      "payment_count":len(payments),"refund_count":refund,
      "line_item_count":len(lines),
      "synthetic_item_quantity_by_sku":dict(sorted(sku_qty.items())),
      "sku_quantities_not_resource_time_or_verified_recipes":True,
      "temporal_profiles":result,
      "first_profile_predeclared_not_fit_to_truth":True,
      "events_not_copied_to_outputs":True,
      "no_arrival_pickup_or_service_calibration":True,
      "no_new_models_or_policy_scenarios":True,
      "reserved_truth_access":False,"R2_access":False,"new_omc":0,
      "new_provider_posts":0,"scientific_lock_created":False,
    }

def render(data,out):
    out=Path(out)
    need(not out.exists(),"REFUSE_OVERWRITE")
    out.mkdir(parents=True,mode=0o700)
    write_json(out/"p02-p05-public-profiles.json",data,exclusive=True)
    for profile in data["temporal_profiles"]:
        width=profile["bin_width_min"]
        with (out/f"pos-observations-{width}min.csv").open(
                "x",encoding="utf-8",newline="") as f:
            cols=list(profile["bins"][0])
            writer=csv.DictWriter(f,fieldnames=cols)
            writer.writeheader()
            for row in profile["bins"]:writer.writerow(row)
    report=(
        "# Cafetería V2.1 — perfil temporal público de construcción\n\n"
        "- Fuente B0: pagos **sintéticos** y proxies visuales admitidos en 0–60 min.\n"
        "- Valor histórico V1: tasa constante "
        f"{data['original_case_v1_constant_rate_orders_per_hour']} pedidos/h "
        "**por hipótesis**.\n"
        "- Operadores predefinidos de 5 y 15 minutos; por cada intervalo se "
        "conserva el conteo exacto de pagos y las medias ponderadas de proxies.\n"
        f"- 5 min: máximo equivalente "
        f"{data['temporal_profiles'][0]['max_paid_rate_equivalent_orders_per_hour']} "
        "pagos/h, NO capacidad observada ni saturación demostrada.\n"
        "- Se conservaron el total de pagos, partidas y atributos de carga por "
        "SKU **sin convertirlos en tiempos de máquina**.\n"
        "- No se trasladan IDs ni timestamps individuales a los resultados.\n"
        "- [60,103.237] min queda **desconocido/reservado**, no extrapolado, "
        "y tampoco se imputa como cero.\n"
        "- No hay calibración, G2, G3, políticas ni validación de negocio.\n")
    (out/"REVIEW.md").write_text(report,encoding="utf-8")
    files=sorted(out.iterdir())
    receipt={"schema":SCHEMA,"status":"PUBLIC_PROFILE_REPRODUCED_NOT_FITTED",
             "case_sha256":data["case_sha256"],"public_sha256":data["public_sha256"],
             "outputs":{p.name:sha_bytes(p.read_bytes()) for p in files},
             "new_omc":0,"new_provider_posts":0,"R2_access":False,
             "truth_access":False,"scientific_lock_created":False}
    write_json(out/"receipt.json",receipt,exclusive=True)
    return receipt

def execute(root,*,env=None,api=None):
    from .coffee_dm_campaign import acquire
    root=Path(root)
    need(not root.exists(),"REFUSE_OVERWRITE")
    acquisition=acquire(root/"source",env=env,api=api)
    need(acquisition["case_sha256"]==dm.CASE_SHA256,"HISTORICAL_CASE_DRIFT")
    case=build_case(root/"source/public",dm.ASSUMPTIONS,environment={})
    need(digest(case)==dm.CASE_SHA256,"CASE_HASH_DRIFT")
    public=read_json(root/"source/public/producer-public-b0.json")
    data=observe(public,case)
    need(data["payment_count"]==10 and data["line_item_count"]==13
         and data["temporal_profiles"][0]["max_paid_rate_equivalent_orders_per_hour"]==48.0
         and [b["synthetic_paid_orders"] for b in
              data["temporal_profiles"][0]["bins"]]==
               [1,0,1,4,1,0,1,0,0,0,2,0],
         "HISTORICAL_PUBLIC_B0_PROFILE_UNEXPECTED")
    return render(data,root/"output")

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        status=execute(args.out)
        print(json.dumps({"status":status["status"],"new_omc":0,
           "new_provider_posts":0,"truth_access":False},sort_keys=True))
        return 0
    except (ArenaError,ValueError,TypeError,KeyError,OSError) as exc:
        print(json.dumps({"status":"PUBLIC_OPERATOR_FAILED_NO_PAID_CONSUMPTION",
                          "reason":str(exc) if isinstance(exc,ArenaError)
                                   else "INVALID_INPUT_OR_PROGRAM"}),
              file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
