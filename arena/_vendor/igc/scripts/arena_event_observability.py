#!/usr/bin/env python3
"""ARENA EV01: generic observable-event projection and timing analysis.

No CAF model imports. Never infer hidden stage count, queue residence time,
or unknown mechanism from aggregate latency. PM4Py only discovers observed
direct-follow sequences, which do not prove causal topology.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction as Q

VIEWS=("POS","POS_KDS","FULL")
SOURCES={"pedido_creado":"pos","pago_confirmado":"pos",
         "pedido_entregado":"pos"}
POS_TYPES=frozenset(SOURCES)
KDS_TYPES=frozenset({"servicio_inicio","servicio_fin"})
FULL_TYPES=frozenset({"etapa_entrada","servicio_inicio","servicio_fin"})
KDS_STAGE="preparacion"
GATE="BLOCKED_SYNTHETIC_EVENT_LOG_NO_EMPIRICAL_SENSOR_SEMANTICS_OR_EXTERNAL_VALIDATION"
ORIGIN=datetime(2026,1,1,tzinfo=timezone.utc)


def require(condition,code):
    if not condition:
        raise ValueError(code)


def exact(value):
    require(type(value) in (Q,int,str),"EV01_INVALID_EXACT_TIME_TYPE")
    q=Q(value)
    require(q>=0,"EV01_NEGATIVE_EVENT_TIME")
    return q


def public_event(event,view):
    """Explicit allowlist and new dict, NEVER a truth dict with fields removed."""
    require(view in VIEWS,"EV01_UNKNOWN_VIEW")
    event_type=event["event_type"]
    stage=event.get("stage")
    visible=(event_type in POS_TYPES
        or (view=="POS_KDS" and event_type in KDS_TYPES and stage==KDS_STAGE)
        or (view=="FULL" and event_type in FULL_TYPES))
    if not visible:
        return None
    basic={
        "case_id":event["case_id"],
        "event_seq":event["event_seq"],
        "activity":event["activity"],
        "event_type":event_type,
        "t_minutes_exact":event["t_minutes_exact"],
        "source":("pos" if event_type in POS_TYPES else
                  "kds_idealizado" if view=="POS_KDS" else
                  "instrumentacion_fisica"),
    }
    if view in ("POS_KDS","FULL") and event_type not in POS_TYPES:
        basic["stage"]=stage
    if view=="FULL" and event_type in KDS_TYPES:
        basic["resource_id"]=event["resource_id"]
    return basic


def project_events(truth,view):
    require(view in VIEWS,"EV01_UNKNOWN_VIEW")
    require(all(type(row.get("event_seq")) is int and
                type(row.get("case_id")) is str for row in truth),
            "EV01_MALFORMED_TRUTH")
    require(all(exact(x["t_minutes_exact"])>=0 for x in truth),
            "EV01_INVALID_TIMESTAMPS")
    rows=[public_event(x,view) for x in truth]
    rows=[x for x in rows if x is not None]
    # CRITICAL: the raw event ordinal has holes for hidden stages.
    # Exposing it would leak the number/location of redacted events.
    for index,row in enumerate(rows):
        row["event_seq"]=index
    return rows


def group_by_case(events):
    groups=defaultdict(list)
    require(len({x["event_seq"] for x in events})==len(events),
            "EV01_DUPLICATE_PUBLIC_EVENT")
    for row in events:
        groups[row["case_id"]].append(row)
    for case,rows in groups.items():
        rows.sort(key=lambda r:(exact(r["t_minutes_exact"]),r["event_seq"]))
        require(all(exact(x["t_minutes_exact"])<=exact(y["t_minutes_exact"])
                    for x,y in zip(rows,rows[1:])),
                "EV01_NONMONOTONE_CASE_EVENTS")
    return dict(groups)


def one(rows,event_type,stage=None):
    match=[x for x in rows if x["event_type"]==event_type
           and (stage is None or x.get("stage")==stage)]
    require(len(match)==1,"EV01_MISSING_OR_DUPLICATE_REQUIRED_EVENT")
    return exact(match[0]["t_minutes_exact"])


def analyze_view(events,view,ordered_stages=("caja","preparacion","despacho","transferencia_final")):
    """Only measures durations with endpoints present in THIS view."""
    require(view in VIEWS,"EV01_UNKNOWN_VIEW")
    require(all("resource_id" not in x for x in events) if view!="FULL"
            else True,"EV01_RESOURCE_LEAK")
    base_fields={"case_id","event_seq","activity","event_type",
                 "t_minutes_exact","source"}
    for row in events:
        if row["event_type"] in POS_TYPES:
            require(set(row)==base_fields and row["source"]=="pos",
                    "EV01_POS_INTERNAL_EVENT_LEAK" if view=="POS"
                    else "EV01_KDS_INTERNAL_EVENT_LEAK")
        elif view=="POS":
            raise ValueError("EV01_POS_INTERNAL_EVENT_LEAK")
        elif view=="POS_KDS":
            require(set(row)==base_fields|{"stage"} and
                    row["event_type"] in KDS_TYPES and
                    row.get("stage")==KDS_STAGE and
                    row["source"]=="kds_idealizado",
                    "EV01_KDS_INTERNAL_EVENT_LEAK")
        else:
            expected=base_fields|{"stage"}
            if row["event_type"] in KDS_TYPES:
                expected|={"resource_id"}
            require(set(row)==expected and
                    row["event_type"] in FULL_TYPES and
                    row.get("stage") in ordered_stages and
                    row["source"]=="instrumentacion_fisica",
                    "EV01_FULL_EVENT_SCHEMA_INVALID")
    by_case=group_by_case(events)
    metrics=[]
    for case,rows in sorted(by_case.items()):
        created=one(rows,"pedido_creado")
        paid=one(rows,"pago_confirmado")
        delivered=one(rows,"pedido_entregado")
        require(created==paid and created<=delivered,
                "EV01_INVALID_POS_MILESTONES")
        cycle=delivered-created
        result={
            "case_id":case,"cycle_minutes_exact":str(cycle),
            "identifiable_from_view":["cycle_time","order_created","order_delivered"],
            "not_identifiable_from_view":[],
            "observed_stage_count_not_total_stage_count":None,
        }
        if view=="POS":
            result["not_identifiable_from_view"]=[
                "service_time_by_stage","waiting_time_by_stage",
                "resource_occupancy","internal_stage_count","hidden_mechanism"]
            result["timing_only_counterexamples"]=[
                {"waiting":str(Q(0)),"service":str(cycle)},
                {"waiting":str(cycle/2),"service":str(cycle/2)},
            ]
        elif view=="POS_KDS":
            start=one(rows,"servicio_inicio",KDS_STAGE)
            finish=one(rows,"servicio_fin",KDS_STAGE)
            require(created<=start<=finish<=delivered,
                    "EV01_INVALID_KDS_MILESTONES")
            prep=finish-start
            post=delivered-finish
            result.update({
                "prep_service_minutes_exact":str(prep),
                "post_prep_elapsed_minutes_exact":str(post),
                "post_prep_is_not_evidence_of_hidden_stage":True,
                "identifiable_from_view":result["identifiable_from_view"]+
                    ["prep_service_if_kds_timestamps_are_physical",
                     "post_prep_elapsed_unallocated"],
                "not_identifiable_from_view":[
                    "prep_wait_without_stage_entry","other_service_times",
                    "other_waiting_times","resource_occupancy",
                    "internal_stage_count","hidden_mechanism"],
                "timing_only_counterexamples_post_prep":[
                    {"unallocated_wait":str(Q(0)),"unallocated_work":str(post)},
                    {"unallocated_wait":str(post/2),"unallocated_work":str(post/2)},
                ],
            })
        else:
            stages={}
            prev_end=created
            for stage in ordered_stages:
                enter=one(rows,"etapa_entrada",stage)
                start=one(rows,"servicio_inicio",stage)
                end=one(rows,"servicio_fin",stage)
                require(enter==prev_end and enter<=start<=end,
                        "EV01_INVALID_PHYSICAL_STAGE_CHAIN")
                stages[stage]={
                    "wait_minutes_exact":str(start-enter),
                    "service_minutes_exact":str(end-start),
                    "start_minutes_exact":str(start),
                    "finish_minutes_exact":str(end),
                }
                prev_end=end
            require(prev_end==delivered,"EV01_CYCLE_NOT_CLOSED")
            closure=sum((Q(d["wait_minutes_exact"])+Q(d["service_minutes_exact"]))
                        for d in stages.values())
            require(closure==cycle,"EV01_TIME_BALANCE_FAIL")
            result.update({
                "per_stage_observed":stages,
                "sum_wait_and_service_minutes_exact":str(closure),
                "cycle_balance_exact":True,
                "identifiable_from_view":result["identifiable_from_view"]+
                    ["observed_stage_wait_and_service","observed_stage_resources",
                     "complete_stage_chain_from_instrumentation"],
                "not_identifiable_from_view":[
                    "unobserved_external_causes_not_in_instrumentation"],
                "observed_stage_count_not_total_stage_count":len(stages),
            })
        metrics.append(result)
    if view=="FULL":
        intervals=defaultdict(list)
        for case,rows in by_case.items():
            for stage in ordered_stages:
                starts=[r for r in rows if r["event_type"]=="servicio_inicio"
                        and r.get("stage")==stage]
                ends=[r for r in rows if r["event_type"]=="servicio_fin"
                      and r.get("stage")==stage]
                require(len(starts)==len(ends)==1,
                        "EV01_RESOURCE_INTERVAL_MISSING")
                a,z=starts[0],ends[0]
                resource=a["resource_id"]
                require(type(resource) is str and
                        resource.startswith(stage+"-r") and
                        z["resource_id"]==resource,
                        "EV01_RESOURCE_ID_CHANGED")
                intervals[resource].append((
                    exact(a["t_minutes_exact"]),
                    exact(z["t_minutes_exact"]),case))
        for resource,times in intervals.items():
            times.sort()
            require(all(previous_end<=next_start
                        for (_,previous_end,_),(next_start,_,_)
                        in zip(times,times[1:])),
                    "EV01_RESOURCE_OVERLAP")
    return {
        "view":view,
        "n_cases":len(metrics),
        "n_events":len(events),
        "observability_claim":{
            "POS":"CYCLE_ONLY_NO_INTERNAL_DECOMPOSITION",
            "POS_KDS":"PREPARATION_SERVICE_ONLY_POST_PREP_UNALLOCATED",
            "FULL":"INTERNAL_STAGE_TIMES_DIRECTLY_OBSERVED",
        }[view],
        "cases":metrics,
        "unknown_stage_inferred":False,
        "same_business_not_independent_worlds":True,
    }


def pm4py_dfg(events):
    """PM4Py's standard DFG over observed rows, not causal inference."""
    import pandas as pd
    import pm4py
    records=[]
    for ev in events:
        q=exact(ev["t_minutes_exact"])
        # PM4Py timestamps rounded to microseconds; the exact Fraction stays
        # preserved in raw event logs for all scientific timing calculations.
        micro=int(q*60000000+Q(1,2))
        records.append({
            "case:concept:name":ev["case_id"],
            "concept:name":ev["activity"],
            "time:timestamp":ORIGIN+timedelta(microseconds=micro),
            "event_seq":ev["event_seq"],
        })
    frame=pd.DataFrame(records).sort_values(
        ["case:concept:name","time:timestamp","event_seq"],
        kind="stable")
    edges,start,end=pm4py.discover_dfg(
        frame,activity_key="concept:name",
        timestamp_key="time:timestamp",
        case_id_key="case:concept:name")
    return {
        "method":"PM4Py.discover_dfg",
        "pm4py_version":pm4py.__version__,
        "n_cases":len({r["case_id"] for r in events}),
        "n_activities":len({r["activity"] for r in events}),
        "edges":[{"from":a,"to":b,"count":int(v)}
                 for (a,b),v in sorted(edges.items())],
        "start_activities":dict(sorted((str(k),int(v)) for k,v in start.items())),
        "end_activities":dict(sorted((str(k),int(v)) for k,v in end.items())),
        "exact_timestamps_used_for_durations_not_pandas":True,
        "dfg_is_observed_succession_not_causal_proof":True,
    }
