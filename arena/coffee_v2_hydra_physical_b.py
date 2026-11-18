"""P44 B: versioned conditional physical cycle for the already-installed Hydra.

This model is deliberately separate from the historical P06/P39 engine:
it has identity-retaining group occupancy and explicit post-counter release
states that its predecessor cannot express. Reuses the same admitted
synthetic POS gate and percentile semantics; never edits the old engine.

All service durations, continuous availability and skill assignments are
ASSUMED SCENARIO inputs. Astra's visual review supports two people/stations
at isolated instants, NOT full calendars, order identity or cycle times.

B only: fixed FCFS dispatch, no policy comparisons or bottleneck attribution.
"""
from __future__ import annotations

from collections import Counter
import argparse
import heapq
import itertools
import json
import math
from pathlib import Path

from .common import ArenaError, read_json, write_json
from . import coffee_v2_reference as historical
from . import coffee_hydra_episodes_a as episodes_a

SCHEMA="arena.coffee.p44.hydra-physical-b/1"
RESULT_SCHEMA="arena.coffee.p44.physical-scenario/1"
# D uses one versioned dispatch decision at a time. No extra workers or
# resources are created; B without an explicit argument remains unchanged.
D_DISPATCH_STAGE={
    "FCFS_READY_ASSUMED":None,
    "PRIORITIZE_LOAD_READY_WITH_FREE_GROUP":"load",
    "PRIORITIZE_MILK_READY":"milk",
    "PRIORITIZE_HANDOFF_READY":"handoff",
}
SKILLS=("prepare","load","remove","clean","milk","handoff")
STAGES=("prepare","load","extract_auto","remove","clean","milk","handoff")
STAGE_CLASSES={
    "prepare":("barista","prep_space"),
    "load":("barista","espresso_group"),
    "extract_auto":("espresso_group",),
    "remove":("barista","espresso_group"),
    "clean":("barista","espresso_group"),
    "milk":("barista","steam_wand"),
    "handoff":("barista","pickup_pass"),
}
DURATION_KEYS={
    "prepare":"prepare_off_group_min",
    "load":"load_min",
    "extract_auto":"espresso_auto_min",
    "remove":"remove_min",
    "clean":"clean_min",
    "milk":"milk_finish_min",
    "handoff":"handoff_min",
}
# Conservative assumed precedence *within a single beverage*.
# Different beverages and staff may overlap whenever resources allow.
PRECEDENCE=("prepare","load","extract_auto","remove","clean","milk")
GROUP_STATES=("FREE","LOADING","EXTRACTING","AWAITING_REMOVAL",
              "REMOVING","AWAITING_CLEAN","CLEANING")
# Stage becomes eligible AFTER its declared predecessor. Time before
# eligibility is not a resource wait, and is never added to wait metrics.
STAGE_PREDECESSOR={
    "prepare":"PAID_ORDER_ARRIVAL",
    "load":"PREPARE_FINISHED",
    "extract_auto":"LOAD_FINISHED",
    "remove":"EXTRACTION_AUTO_FINISHED",
    "clean":"REMOVE_FINISHED_IF_CLEAN_POLICY_ENABLED",
    "milk":"GROUP_RELEASED_IF_MILK_RECIPE",
    "handoff":"ALL_BEVERAGES_COMPLETED",
}


def need(condition,code):
    if not condition:
        raise ArenaError("COFFEE_P44_B_"+code)


def number(x,label,lower=0,upper=10000):
    need(type(x) in (int,float) and math.isfinite(x) and
         lower<=x<=upper,"INVALID_NUMERIC_"+label)
    return float(x)


def validate(d):
    """Admit *declared* physical scenarios without pretending observation."""
    need(type(d) is dict and d.get("schema")==SCHEMA and
         d.get("scope")=="ASSUMED_CONDITIONAL_PHYSICAL_MODEL_NOT_CALIBRATED",
         "WRONG_VERSION_OR_SCOPE")
    need(d.get("dispatch_policy")=="FCFS_READY_ASSUMED" and
         d.get("milk_precedence")=="AFTER_GROUP_RELEASE_ASSUMED" and
         d.get("group_availability_status")==
             "ASSUMED_FULL_SCENARIO_NOT_EMPIRICALLY_VERIFIED" and
         d.get("operator_calendar_status")==
             "ASSUMED_WINDOWS_NOT_INFERRED_FROM_VIDEO" and
         type(d.get("clean_after_every_beverage_assumed")) is bool and
         d.get("initial_open_orders_assumed")==0,
         "UNDECLARED_POLICY_OR_ASSUMED_STATE")
    installed=d.get("installed_group_ids")
    enabled=d.get("enabled_group_ids")
    need(installed==["G01","G02","G03"] and
         type(enabled) is list and 1<=len(enabled)<=3 and
         set(enabled)<=set(installed) and len(set(enabled))==len(enabled),
         "GROUP_IDENTITY_OR_AVAILABILITY")
    actors=d.get("operators")
    need(type(actors) is dict and set(actors)=={"B01","B02"},
         "OBSERVED_ACTOR_IDENTITIES")
    for aid, actor in actors.items():
        need(type(actor) is dict and set(actor)=={
             "availability_windows_min","skills","status"} and
             actor["status"]=="ASSUMED_NOT_OBSERVED_FULL_SHIFT" and
             type(actor["skills"]) is list and
             len(set(actor["skills"]))==len(actor["skills"]) and
             len(actor["skills"])>0 and
             set(actor["skills"])<=set(SKILLS),
             "ACTOR_DECLARATION_"+aid)
        windows=actor["availability_windows_min"]
        need(type(windows) is list and len(windows)<=12 and len(windows)>0,
             "WINDOW_COUNT_"+aid)
        prior=-1
        for interval in windows:
            need(type(interval) is list and len(interval)==2 and
                 all(type(x) in (int,float) for x in interval) and
                 all(math.isfinite(x) for x in interval) and
                 0<=interval[0]<interval[1]<=10000 and
                 interval[0]>=prior,
                 "INVALID_OR_OVERLAPPING_WINDOWS_"+aid)
            prior=interval[1]
    for skill in SKILLS:
        if skill=="clean" and not d["clean_after_every_beverage_assumed"]:
            continue
        need(any(skill in a["skills"] for a in actors.values()),
             "NO_ACTOR_FOR_"+skill)
    for field in ("prep_stations","steam_wands","pickup_passes"):
        names=d.get(field)
        need(type(names) is list and len(names)>0 and
             len(names)<=8 and len(names)==len(set(names)) and
             all(type(x) is str and x for x in names),
             "RESOURCE_IDENTITIES_"+field)
    need(set(d["prep_stations"])<=
         {"puesto_izquierdo","puesto_derecho"} and
         set(d["prep_stations"]) and
         set(d["steam_wands"])<={"W01","W02"} and
         set(d["pickup_passes"])<={"PASS01","PASS02"},
         "NO_UNDECLARED_EQUIPMENT")
    timing=d.get("durations_min")
    need(type(timing) is dict and set(timing)==set(DURATION_KEYS.values()),
         "DURATION_FIELDS")
    for key,desc in timing.items():
        need(type(desc) is dict and set(desc)==
             {"value","status","evidence"} and
             desc["status"]=="ASSUMED_NOT_CALIBRATED" and
             type(desc["evidence"]) is str and
             len(desc["evidence"].strip())>=12,
             "NOT_EXPLICITLY_ASSUMED_"+key)
        number(desc["value"],key,0.001,30)
    need(d.get("operator_stations_assignment")==
         "DYNAMIC_FCFS_DIFFERENT_STATIONS_NOT_PERMANENT_STAFF_POSITIONS" and
         d.get("operator_skill_status")=="DECLARED_ASSUMPTIONS_NOT_VISUALLY_IDENTIFIED",
         "DO_NOT_INFER_OPERATOR_SKILLS_OR_STATIONS")
    return d


def capabilities(d):
    """A3 checker sees the same resource classes used by stage dispatcher."""
    validate(d)
    return {
        "resource_units":{
            "barista":len(d["operators"]),
            "prep_space":len(d["prep_stations"]),
            "espresso_group":len(d["enabled_group_ids"]),
            "steam_wand":len(d["steam_wands"]),
            "pickup_pass":len(d["pickup_passes"]),
        },
        "stage_requirements":{
            "manual_setup":list(STAGE_CLASSES["prepare"]),
            "espresso_auto":list(STAGE_CLASSES["extract_auto"]),
            "load":list(STAGE_CLASSES["load"]),
            "remove":list(STAGE_CLASSES["remove"]),
            "milk_finish":list(STAGE_CLASSES["milk"]),
        },
        "preparation_constraints":{
            # Identical skills, stations, durations and calendars to _engine.choose.
            "stage":"prepare",
            "operator_skills":{aid:list(actor["skills"])
                               for aid,actor in d["operators"].items()},
            "operator_windows_min":{
                aid:[list(w) for w in actor["availability_windows_min"]]
                for aid,actor in d["operators"].items()},
            "prep_station_ids":list(d["prep_stations"]),
            "duration_min":d["durations_min"]["prepare_off_group_min"]["value"],
            "video_to_scenario_clock_alignment":"NOT_ESTABLISHED",
        },
        "post_counter_mounted_state_supported":True,
        "stage_source":"coffee_v2_hydra_physical_b.STAGE_CLASSES",
        "time_source":"coffee_v2_hydra_physical_b.DURATION_KEYS",
        "engine_verified_descriptor":True,
    }


def actor_available(actor, time, duration):
    return any(start<=time and time+duration<=end+1e-10
               for start,end in actor["availability_windows_min"])


def _engine(positions, lines, d, horizon, *,
            dispatch_policy="FCFS_READY_ASSUMED"):
    """Versioned physical DES: B's FCFS default or one D priority at a time.

    Default argument preserves the accepted B exact result/trace behavior.
    D policy changes only which already-eligible, runnable manual task
    receives the next atomic resource assignment. Nonpreemptive execution,
    actor skills, calendar windows, stage dependencies and group identities
    always use the same functions and dossier.
    """
    validate(d)
    need(dispatch_policy in D_DISPATCH_STAGE,
         "UNDECLARED_D_DISPATCH_POLICY")
    horizon=historical.num(horizon,"HORIZON",0,180)
    need(horizon>0,"HORIZON_POSITIVE")
    paid,refunds,beverages=historical.paid_gate(positions,lines,horizon)
    timing={stage:d["durations_min"][key]["value"]
            for stage,key in DURATION_KEYS.items()}
    resources={
        "actor":tuple(d["operators"]),
        "station":tuple(d["prep_stations"]),
        "group":tuple(d["enabled_group_ids"]),
        "wand":tuple(d["steam_wands"]),
        "pass":tuple(d["pickup_passes"]),
    }
    occupied={}                   # "A:B01" -> job or other task
    group_state={g:"FREE" for g in resources["group"]}
    held={}                       # job -> persistent actual scenario group ID
    states={(oid,i):typ for oid,o in paid.items()
            for i,typ in enumerate(o["items"])}
    remaining={oid:len(o["items"]) for oid,o in paid.items()}
    completed={}
    events=[]
    ready=[]
    trace=[]                     # PRIVATE, IDs not exported in aggregate
    # For D variants identity must survive even when the priority NEVER
    # overrides any assignment. The accepted B default trace stays exact.
    if dispatch_policy!="FCFS_READY_ASSUMED":
        trace.append({"event":"dispatch_policy_identity",
                      "policy":dispatch_policy,
                      "declared_as":"EXECUTED_ENGINE_POLICY_NOT_DIAGNOSIS_HINT"})
    order_counter=itertools.count()
    op_counts=Counter()
    max_group_occupied=0
    def tick(time,priority,kind,obj):
        heapq.heappush(events,(time,priority,next(order_counter),kind,obj))
    def enqueue(job,stage,time):
        need(stage in STAGE_PREDECESSOR,"UNKNOWN_PRECEDENCE_STAGE")
        ready.append({"job":job,"stage":stage,"eligible_at":time})
        trace.append({"event":"eligible","time":time,"job":job,
                      "stage":stage,"predecessor":STAGE_PREDECESSOR[stage],
                      "required_classes":list(STAGE_CLASSES[stage])})
    for oid,order in paid.items():
        tick(order["time"],1,"arrival",oid)
    # Calendar START boundaries wake tasks; no invented actor availability.
    for actor in d["operators"].values():
        for start,end in actor["availability_windows_min"]:
            tick(start,2,"calendar",None)
            tick(end,2,"calendar",None)

    def group_status(g,state,job,time):
        need(state in GROUP_STATES,"UNKNOWN_GROUP_STATE")
        old=group_state[g]
        need(old!=state,"DUPLICATE_GROUP_STATE_TRANSITION")
        group_state[g]=state
        trace.append({"event":"group_state","time":time,"group":g,
                      "from":old,"to":state,"job":job})

    def release_group(job,time):
        need(job in held,"GROUP_NOT_HELD_FOR_RELEASE")
        group=held.pop(job)
        token="G:"+group
        need(occupied.get(token)==job,"GROUP_RELEASE_NOT_OWNED")
        del occupied[token]
        group_status(group,"FREE",job,time)

    def unbook(job,tokens):
        for token in tokens:
            need(occupied.get(token)==job,"TOKEN_NOT_OWNED_AT_END")
            del occupied[token]

    def choose(task,time):
        job,stage=task["job"],task["stage"]
        duration=timing[stage]
        required=STAGE_CLASSES[stage]
        if stage=="extract_auto":
            need(required==("espresso_group",),"AUTO_STAGE_CONTRACT_DRIFT")
            need(job in held,"EXTRACTION_NO_LOCKED_GROUP")
            g=held[job]
            need(occupied.get("G:"+g)==job and
                 group_state[g]=="LOADING",
                 "EXTRACTION_LOST_GROUP_AFTER_LOAD")
            return (),None,g
        need(len(required)==2 and required[0]=="barista",
             "MANUAL_STAGE_RESOURCE_CONTRACT_DRIFT")
        extra=required[1]
        for actor_id,actor in d["operators"].items():
            if stage not in actor["skills"] or not actor_available(
                    actor,time,duration) or "A:"+actor_id in occupied:
                continue
            held_group=None
            if extra=="prep_space":
                pools=[("S:"+x,) for x in resources["station"]]
            elif extra=="espresso_group":
                if stage=="load":
                    pools=[("G:"+x,) for x in resources["group"]
                           if group_state[x]=="FREE"]
                else:
                    need(stage in ("remove","clean"),
                         "GROUP_STAGE_REQUIRES_HELD_OR_FREE")
                    if job not in held:
                        continue
                    held_group=held[job]
                    expected=("AWAITING_REMOVAL" if stage=="remove"
                              else "AWAITING_CLEAN")
                    need(group_state[held_group]==expected and
                         occupied.get("G:"+held_group)==job,
                         "RESUMED_WRONG_GROUP_OR_STATE")
                    pools=[()]  # Locked group retained by SAME job.
            elif extra=="steam_wand":
                pools=[("W:"+x,) for x in resources["wand"]]
            elif extra=="pickup_pass":
                pools=[("P:"+x,) for x in resources["pass"]]
            else:
                need(False,"UNKNOWN_STAGE_RESOURCE_CLASS")
            for pool in pools:
                tokens=("A:"+actor_id,)+pool
                if all(tok not in occupied for tok in tokens):
                    selected_group=(
                        held_group if held_group is not None else
                        pool[0][2:] if stage=="load" else None)
                    return tokens,actor_id,selected_group
        return None

    def blocking_routes(task,time):
        """Explain *all* alternative manual allocations at a fixed instant.

        This is instrumentation, not a dispatcher or an optimizer. A task
        can have multiple simultaneous blockers, or different blockers on
        distinct candidate routes; none is assigned an exclusive duration.
        """
        job,stage=task["job"],task["stage"]
        need(stage!="extract_auto","AUTOMATIC_STAGE_CANNOT_WAIT_FOR_ACTOR")
        extra=STAGE_CLASSES[stage][1]
        unskilled=[]
        routes=[]
        for actor_id,actor in d["operators"].items():
            if stage not in actor["skills"]:
                unskilled.append(actor_id)
                continue
            actor_blockers=[]
            if not actor_available(actor,time,timing[stage]):
                actor_blockers.append("ACTOR_OUTSIDE_ELIGIBLE_WINDOW")
            if "A:"+actor_id in occupied:
                actor_blockers.append("ACTOR_BUSY")
            if extra=="prep_space":
                units=[("S:"+p,"prep_space",None)
                       for p in resources["station"]]
            elif extra=="espresso_group":
                if stage=="load":
                    units=[("G:"+g,"espresso_group",group_state[g])
                           for g in resources["group"]]
                else:
                    need(job in held,"DIAGNOSIS_MISSING_HELD_GROUP")
                    g=held[job]
                    units=[("G:"+g,"espresso_group",group_state[g])]
            elif extra=="steam_wand":
                units=[("W:"+w,"steam_wand",None)
                       for w in resources["wand"]]
            else:
                need(extra=="pickup_pass","DIAGNOSIS_UNKNOWN_RESOURCE")
                units=[("P:"+p,"pickup_pass",None)
                       for p in resources["pass"]]
            for token,kind,state in units:
                blockers=list(actor_blockers)
                if stage=="load":
                    if state!="FREE" or token in occupied:
                        blockers.append("GROUP_OCCUPIED_"+str(state))
                elif stage in ("remove","clean"):
                    need(occupied.get(token)==job,
                         "DIAGNOSIS_MUST_USE_OWN_HELD_GROUP")
                    expected=("AWAITING_REMOVAL" if stage=="remove"
                              else "AWAITING_CLEAN")
                    need(state==expected,"DIAGNOSIS_HELD_GROUP_BAD_STATE")
                elif token in occupied:
                    blockers.append("RESOURCE_BUSY_"+kind.upper())
                routes.append({"actor":actor_id,"resource":token,
                               "resource_class":kind,"group_state":state,
                               "blockers":blockers})
        need(routes and all(x["blockers"] for x in routes),
             "DIAGNOSIS_HAS_RUNNABLE_ROUTE")
        return {"required_classes":list(STAGE_CLASSES[stage]),
                "unskilled_actors":unskilled,
                "alternative_routes":routes,
                # Capture enabled groups for ALL stages. Preparation happens
                # off-group, but its diagnosis still needs group availability.
                "enabled_group_states":dict(group_state),
                "all_routes_blocked":True}

    def start(task,choice,time):
        nonlocal max_group_occupied
        job,stage=task["job"],task["stage"]
        tokens,actor_id,group=choice
        for tok in tokens:
            need(tok not in occupied,"NONATOMIC_DOUBLE_RESOURCE_RESERVATION")
        for tok in tokens:
            occupied[tok]=job
        if stage=="load":
            need(group is not None and job not in held,"LOAD_GROUP_DUPLICATE")
            held[job]=group
            group_status(group,"LOADING",job,time)
        elif stage=="extract_auto":
            group_status(group,"EXTRACTING",job,time)
        elif stage=="remove":
            group_status(group,"REMOVING",job,time)
        elif stage=="clean":
            group_status(group,"CLEANING",job,time)
        group_busy=sum(k.startswith("G:") for k in occupied)
        max_group_occupied=max(max_group_occupied,group_busy)
        need(group_busy<=len(resources["group"]) and
             len(set(held.values()))==len(held),
             "SAME_GROUP_DOUBLE_OCCUPIED")
        trace.append({"event":"start","time":time,"job":job,
                      "stage":stage,"actor":actor_id,"group":group,
                      "tokens":list(tokens),
                      "eligible_at":task["eligible_at"],
                      "resource_wait_min":max(0.0,time-task["eligible_at"]),
                      "required_classes":list(STAGE_CLASSES[stage]),
                      "precedence_satisfied":True})
        tick(time+timing[stage],0,"finish",
             (job,stage,tokens,time,actor_id,group))

    def finish(payload,time):
        job,stage,tokens,started,actor_id,group=payload
        need(time>started,"NONPOSITIVE_DURATION")
        unbook(job,tokens if stage!="load" else
               tuple(t for t in tokens if not t.startswith("G:")))
        trace.append({"event":"finish","time":time,"job":job,
                      "stage":stage,"actor":actor_id,"group":group})
        op_counts[stage]+=1
        if stage=="prepare":
            enqueue(job,"load",time)
        elif stage=="load":
            enqueue(job,"extract_auto",time)
        elif stage=="extract_auto":
            group_status(group,"AWAITING_REMOVAL",job,time)
            enqueue(job,"remove",time)
        elif stage=="remove":
            if d["clean_after_every_beverage_assumed"]:
                group_status(group,"AWAITING_CLEAN",job,time)
                enqueue(job,"clean",time)
            else:
                release_group(job,time)
                after_group(job,time)
        elif stage=="clean":
            release_group(job,time)
            after_group(job,time)
        elif stage=="milk":
            item_done(job,time)
        else:
            need(stage=="handoff","UNKNOWN_FINISHED_STAGE")
            oid,index=job
            need(index==-1 and remaining[oid]==0 and oid not in completed,
                 "HANDOFF_BEFORE_DRINKS_FINISHED")
            completed[oid]=time

    def after_group(job,time):
        if states[job]=="con_leche":
            enqueue(job,"milk",time)
        else:
            item_done(job,time)

    def item_done(job,time):
        oid,index=job
        remaining[oid]-=1
        need(remaining[oid]>=0,"NEGATIVE_REMAINING")
        if remaining[oid]==0:
            enqueue((oid,-1),"handoff",time)

    processed=0
    while events or ready:
        need(events,"NO_FUTURE_EVENT_TO_RESOLVE_PENDING_TASKS")
        time=events[0][0]
        while events and events[0][0]==time:
            _,_,_,kind,obj=heapq.heappop(events)
            processed+=1
            need(processed<=150000,"EVENT_LIMIT")
            if kind=="arrival":
                for i,typ in enumerate(paid[obj]["items"]):
                    job=(obj,i)
                    pending=["load","extract_auto","remove"]
                    if d["clean_after_every_beverage_assumed"]:
                        pending.append("clean")
                    if typ=="con_leche":
                        pending.append("milk")
                    for stage in pending:
                        trace.append({"event":"pending_precedence",
                                      "time":time,"job":job,"stage":stage,
                                      "predecessor":STAGE_PREDECESSOR[stage],
                                      "eligible":False})
                    enqueue(job,"prepare",time)
                trace.append({"event":"pending_precedence",
                              "time":time,"job":(obj,-1),"stage":"handoff",
                              "predecessor":"ALL_BEVERAGES_COMPLETED",
                              "eligible":False})
            elif kind=="finish":
                finish(obj,time)
            else:
                need(kind=="calendar","UNKNOWN_EVENT_TYPE")
        # Fixed deterministic FCFS amongst ELIGIBLE tasks; cannot preempt
        # running tasks or reserve just a group while waiting for actor.
        progress=True
        while progress:
            progress=False
            if dispatch_policy=="FCFS_READY_ASSUMED":
                # Preserve the *exact* accepted B dispatcher in baseline mode.
                for index,task in enumerate(ready):
                    candidate=choose(task,time)
                    if candidate is not None:
                        ready.pop(index)
                        start(task,candidate,time)
                        progress=True
                        break
            else:
                # Stable ready-queue order is the tie-breaker in every policy.
                # Priority is effective only when an entire allocation is
                # feasible NOW; no future group or actor reservation.
                baseline=None
                preferred=None
                preferred_stage=D_DISPATCH_STAGE[dispatch_policy]
                for index,task in enumerate(ready):
                    candidate=choose(task,time)
                    if candidate is None:
                        continue
                    if baseline is None:
                        baseline=(index,task,candidate)
                    if task["stage"]==preferred_stage:
                        preferred=(index,task,candidate)
                        break
                selected=preferred or baseline
                if selected is not None:
                    index,task,candidate=selected
                    if baseline is not None and baseline[0]!=index:
                        trace.append({
                            "event":"dispatch_override",
                            "time":time,
                            "policy":dispatch_policy,
                            "baseline_first_runnable_job":baseline[1]["job"],
                            "baseline_first_runnable_stage":baseline[1]["stage"],
                            "selected_job":task["job"],
                            "selected_stage":task["stage"],
                            "selected_actor":candidate[1],
                            "selected_group":candidate[2],
                            "reason":"PREFERRED_STAGE_ALREADY_RUNNABLE",
                            "work_displaced_is_not_cancelled":True,
                        })
                    ready.pop(index)
                    start(task,candidate,time)
                    progress=True
        need(len(occupied)==len(set(occupied)),"DUPLICATE_TOKEN_MAP")
        # Each waiting task contributes exactly once to each inter-event
        # interval. Concurrent tasks' task-minutes may overlap in clock time.
        # Do not allocate the full interval separately to each blocker.
        if ready and events:
            next_time=events[0][0]
            if next_time>time:
                for task in ready:
                    # At end-duration the actor loses the ability to START
                    # and FINISH a nonpreemptive task within the window, even
                    # before the calendar END event. These diagnostic cuts
                    # do NOT wake, reorder or modify the FCFS dispatcher.
                    stage=task["stage"]
                    cuts={time,next_time}
                    if stage!="extract_auto":
                        duration=timing[stage]
                        for actor in d["operators"].values():
                            if stage not in actor["skills"]:
                                continue
                            for window_start,window_end in actor["availability_windows_min"]:
                                last_start=window_end-duration
                                for threshold in (window_start,last_start,window_end):
                                    if time+1e-10<threshold<next_time-1e-10:
                                        cuts.add(threshold)
                    boundaries=sorted(cuts)
                    for left,right in zip(boundaries,boundaries[1:]):
                        if right-left<=1e-10:
                            continue
                        # Sample INSIDE positive-duration interval: a start
                        # feasible only at the LEFT boundary has zero signal
                        # time. Resource occupancy is constant between events.
                        diagnosis=blocking_routes(task,(left+right)/2)
                        trace.append({"event":"blocked_interval",
                                      "start_time":left,"end_time":right,
                                      "minutes":right-left,
                                      "job":task["job"],"stage":stage,
                                      "eligible_at":task["eligible_at"],
                                      "blocking":diagnosis})
    need(not held and not occupied and
         all(state=="FREE" for state in group_state.values()) and
         len(completed)==len(paid) and
         all(v==0 for v in remaining.values()),
         "FINAL_RESOURCE_AND_ORDER_CONSERVATION")
    delays=[time-paid[oid]["time"] for oid,time in completed.items()]
    inside=sum(t<horizon for t in completed.values())
    result={
        "schema":RESULT_SCHEMA,
        "status":"SIMULATED_CONDITIONAL_PHYSICAL_B_NOT_EMPIRICAL",
        "scope":"SYNTHETIC_PAID_POS_TO_MODELED_HANDOFF",
        "paid_orders":len(paid),
        "synthetic_beverages":beverages,
        "refunds_not_new_work":refunds,
        "modeled_handoffs_before_cut":inside,
        "modeled_handoffs_after_cut":len(paid)-inside,
        "modeled_paid_to_handoff_p50_full_drain_min":
            historical.percentile(delays,.5),
        "modeled_paid_to_handoff_p90_full_drain_min":
            historical.percentile(delays,.9),
        "group_ids_installed":list(d["installed_group_ids"]),
        "group_ids_enabled_assumed":list(resources["group"]),
        "operators_scenario_assumed":list(resources["actor"]),
        "prep_stations_scenario_assumed":list(resources["station"]),
        "max_simultaneous_group_reservations":max_group_occupied,
        "stage_counts":{stage:op_counts[stage] for stage in STAGES},
        "cleaning_each_drink_assumed":d["clean_after_every_beverage_assumed"],
        "group_release_follows_remove_or_optional_clean":True,
        "operator_exclusive_across_all_manual_stages":True,
        "same_synthetic_pos_compatibility_with_historical_paid_gate":True,
        "operator_windows_are_scenario_assumptions":True,
        "service_durations_are_scenario_assumptions":True,
        "no_empirical_capacity_or_wait_conclusion":True,
        "no_new_worlds_or_provider_or_OMC":True,
    }
    need(op_counts["prepare"]==op_counts["load"]==
         op_counts["extract_auto"]==op_counts["remove"]==beverages and
         op_counts["clean"]==(beverages if
             d["clean_after_every_beverage_assumed"] else 0) and
         op_counts["handoff"]==len(paid),
         "STAGE_COUNT_MASS_BALANCE")
    return result,trace,completed


def _reconcile_manual_preparation(row, caps):
    """Check actual B skills and calendars, not only unit counts.

    A3's generic headcount rule remains untouched for the historical model.
    Video seconds are not aligned to the assumed scenario minute clock.
    """
    rules=caps["preparation_constraints"]
    skills=rules["operator_skills"]
    windows=rules["operator_windows_min"]
    stations=set(rules["prep_station_ids"])
    duration=rules["duration_min"]
    samples=row["observed"]["reviewed_samples"]
    if not samples:
        return row

    details=[]
    for sample in samples:
        actors=sample["actor_ids"]
        places=sample["stations"]
        distinct=(len(actors)>=2 and len(set(actors))==len(actors) and
                  len(set(places))==len(places))
        missing_skill=[aid for aid in actors
                       if aid not in skills or "prepare" not in skills[aid]]
        missing_station=[p for p in places if p not in stations]
        structural=(distinct and len(places)==len(actors) and
                    not missing_skill and not missing_station)

        # Concurrent activity need not start at an identical instant.
        # Each nonpreemptive task must fit in its own availability window;
        # those eligible windows must have a positive common intersection.
        joint=[]
        if structural:
            eligible=[
                [(lo,hi) for lo,hi in windows[aid]
                 if hi-lo+1e-10>=duration]
                for aid in actors]
            for combination in itertools.product(*eligible):
                lo=max(w[0] for w in combination)
                hi=min(w[1] for w in combination)
                if hi-lo>1e-10:
                    joint.append([lo,hi])
        feasible=bool(structural and joint)
        details.append({
            "sample_id":sample["id"],
            "actors":actors,
            "stations":places,
            "missing_prepare_skill":missing_skill,
            "unavailable_prep_stations":missing_station,
            "distinct_actors_and_stations":distinct,
            "structure_permits_simultaneous_prepare":bool(structural),
            "joint_feasible_calendar_windows_min":joint,
            "scenario_concurrency_feasible":feasible,
            "instant_specific_status":(
                "INDETERMINATE" if feasible else "CONTRADICTED"),
        })

    all_possible=all(x["scenario_concurrency_feasible"] for x in details)
    row["status"]="COMPATIBLE" if all_possible else "CONTRADICTED"
    row["rule"]=(
        "Each reviewed sample requires distinct operators with prepare skill "
        "and distinct declared stations, plus feasible concurrent actor "
        "calendar windows; video instants require clock alignment.")
    row["model"].update({
        "preparation_constraints":rules,
        "sample_feasibility":details,
        "all_reviewed_samples_feasible_somewhere_in_scenario":all_possible,
        "sample_instant_clock_alignment":"NOT_ESTABLISHED",
        "instant_specific_status":(
            "INDETERMINATE" if all_possible else "CONTRADICTED"),
    })
    row["uncertainty"]+=(
        " Video seconds are not scenario minutes; skills, calendars and "
        "preparation durations are assumed.")
    if all_possible:
        row["explanation"]=(
            "Simultaneous preparations are feasible somewhere under the "
            "assumed B constraints. COMPATIBLE means existential feasibility "
            "only; compatibility at the observed video instants remains "
            "INDETERMINATE because the clocks are not aligned.")
    else:
        failures=[x["sample_id"] for x in details
                  if not x["scenario_concurrency_feasible"]]
        row["explanation"]=(
            "CONTRADICTED for the assumed B scenario: required actors, "
            "prepare skills, stations or overlapping eligible calendar "
            "windows cannot support concurrency for "+", ".join(failures)+
            ". Unknown clock alignment cannot restore impossible overlap.")
    return row


def episode_adapter(view,dossier):
    """A3 evaluates same observed samples against B's actual stage classes."""
    episodes,operations=episodes_a.inspect(view)
    caps=capabilities(dossier)
    rows=episodes_a.evaluate_cases(
        view,episodes,operations,caps,
        dossier["durations_min"]["espresso_auto_min"]["value"],
        timer_semantics="not_established")
    for row in rows:
        if row["question"]=="manual_preparation_concurrency_vs_resource_capacity":
            _reconcile_manual_preparation(row,caps)
    return {"schema":"arena.coffee.p44.a3-b-representation-bridge/1",
            "source":"P43_REVIEWED_EXPLORATORY_EPISODES_NOT_INDEPENDENT",
            "model_capabilities":caps,
            "checks":rows,
            "counter_semantics":"not_established",
            "no_new_simulation":True,
            "no_claim_that_window_is_continuous":True,
            "group_reuse_duration_still_unmeasured":True}


def export_bridge(data,out):
    out=Path(out)
    need(not out.exists(),"OUTPUT_EXISTS")
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/"B_REPRESENTATION_CHECKS.json",data,exclusive=True)
    lines=[
        "# Entrega B — Representabilidad física, no política ganadora",
        "",
        "Fuente observacional: episodios conocidos de Astra, sin nuevos videos.",
        "Capacidades B: "+
        json.dumps(data["model_capabilities"]["resource_units"],
                   sort_keys=True,ensure_ascii=False),
        "Dos operadores observados en instantes aislados NO prueban",
        "plantilla ni disponibilidad continua; B declara ventanas asumidas.",
        "El modelo conserva la reserva de grupo tras terminar el",
        "contador hasta terminar retirada y limpieza si corresponde.",
        "Los tiempos manuales y automáticos NO han sido calibrados.",
        "",
        "| Contraste de A3 | Resultado con representación B |",
        "|---|---|",
    ]
    for row in data["checks"]:
        lines.append("| "+row["question"]+" | "+row["status"]+" |")
    lines += ["",
       "A3 no constituye validación independiente: las observaciones",
       "sirvieron para decidir las características que B debía admitir.",
       "La compatibilidad de los episodios es factibilidad de reglas.",
       "No se hizo una comparación de políticas B/C/D ni de espera real.",
    ]
    (out/"B_REPRESENTATION.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")
    print("P44_B_BRIDGE_CHECKS",len(data["checks"]),"NEW_SCIENTIFIC_RUNS",0)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--dossier",required=True)
    p.add_argument("--episode-view",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    export_bridge(episode_adapter(read_json(args.episode_view),
                                  read_json(args.dossier)),args.out)


if __name__=="__main__":
    main()
