"""P46 D: bounded, paired dispatch-policy comparisons on the accepted B/C world.

Four policies, identical paid demand, recipes, durations, people, calendars,
groups and precedence within each comparison. One runnable stage priority
changes per candidate; never reroutes handoff to historical S5 support.
The public reports use pseudonyms and aggregate outcomes, not raw POS IDs.

CI runs only the existing toy fixture. The Q25/Q75 construction adapter is
read-only, requires an explicit authorized caller, and is NOT dispatched by CI.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .common import ArenaError, digest, read_json, write_json
from . import coffee_v2_hydra_physical_b as b
from . import coffee_v2_hydra_causes_c as c
from . import coffee_v2_reference_inputs as inputs
from . import coffee_v2_p11 as p11

SCHEMA="arena.coffee.p46.paired-policy-comparison/1"
CASE_SET_SCHEMA="arena.coffee.p46.q25-q75-paired-comparisons/1"
POLICIES=tuple(b.D_DISPATCH_STAGE)
ALLOWED_CONSTRUCTION=("LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75")
EPS=1e-8
_VERIFIED_SELECTION_CAPABILITY=object()
SOURCE_RUN_ID=43684660729


def require(ok,code):
    if not ok:
        raise ArenaError("COFFEE_P46_D_"+code)


def round9(x):
    return round(float(x),9)


def task_key(task,stage=None):
    job=task["job"]
    return (job[0],job[1],stage or task["stage"])


def starts_by_task(trace):
    result={}
    for event in trace:
        if event["event"]!="start":
            continue
        key=task_key(event)
        require(key not in result,"DUPLICATE_TASK_START")
        result[key]=event
    return result


def actor_work(trace,dossier):
    duration={stage:dossier["durations_min"][name]["value"]
              for stage,name in b.DURATION_KEYS.items()}
    result={name:{"completed_manual_tasks":0,
                  "busy_manual_minutes":0.0,
                  "stage_counts":{s:0 for s in b.STAGES if
                                  s!="extract_auto"},
                  "stage_busy_manual_min":{s:0.0 for s in b.STAGES if
                                           s!="extract_auto"}}
            for name in dossier["operators"]}
    for event in trace:
        if event["event"]!="start" or event["actor"] is None:
            continue
        actor=event["actor"]
        require(actor in result,"UNDECLARED_ACTOR_ASSIGNMENT")
        record=result[actor]
        record["completed_manual_tasks"]+=1
        record["busy_manual_minutes"]+=duration[event["stage"]]
        record["stage_counts"][event["stage"]]+=1
        record["stage_busy_manual_min"][event["stage"]]+=duration[event["stage"]]
    for rec in result.values():
        rec["busy_manual_minutes"]=round9(rec["busy_manual_minutes"])
        rec["stage_busy_manual_min"]={
            k:round9(v) for k,v in rec["stage_busy_manual_min"].items()}
    return result


def _public_task(key,pseudonym):
    oid,index,stage=key
    require(oid in pseudonym,"MISSING_PAID_PSEUDONYM")
    return {"paid_case_label":pseudonym[oid],
            "beverage_number":index+1 if index>=0 else None,
            "stage":stage}


def compare(positions,lines,dossier,horizon, *,
            source_label="SOFTWARE_TOY_D_FIXED",
            load_label="SOFTWARE_TOY_FIXED",
            _verified_selection_capability=None,
            _source_provenance=None):
    """Four deterministic paired runs; no policy is declared a real winner."""
    b.validate(dossier)
    require(type(positions) is list and type(lines) is list,
            "INPUT_ARRAYS_REQUIRED")
    allowed_labels={"SOFTWARE_TOY_D_FIXED",
                    "CONSTRUCTION_SYNTHETIC_Q25",
                    "CONSTRUCTION_SYNTHETIC_Q75"}
    require(source_label in allowed_labels,"NO_UNDECLARED_SOURCE")
    if source_label=="CONSTRUCTION_SYNTHETIC_Q25":
        require(load_label==ALLOWED_CONSTRUCTION[0],"Q25_LABEL_MISMATCH")
    elif source_label=="CONSTRUCTION_SYNTHETIC_Q75":
        require(load_label==ALLOWED_CONSTRUCTION[1],"Q75_LABEL_MISMATCH")
    else:
        require(load_label=="SOFTWARE_TOY_FIXED","TOY_LABEL_MISMATCH")
    construction=source_label!="SOFTWARE_TOY_D_FIXED"
    if construction:
        require(_verified_selection_capability is
                _VERIFIED_SELECTION_CAPABILITY and
                isinstance(_source_provenance,dict) and
                _source_provenance.get("selected_load_label")==load_label and
                _source_provenance.get("verified_adapter")==
                    "P11_P39_CONSTRUCTION_SELECT_CASE_DAY",
                "CONSTRUCTION_REQUIRES_VERIFIED_SELECTION")
    else:
        require(_verified_selection_capability is None and
                _source_provenance is None,"TOY_CANNOT_IMPERSONATE_CONSTRUCTION")
    paid,refunds,beverages=b.historical.paid_gate(
        positions,lines,horizon)
    paid_ids=sorted(paid,key=lambda oid:(paid[oid]["time"],
                                        list(paid).index(oid)))
    pseudonym={oid:"P%04d"%(index+1) for index,oid in enumerate(paid_ids)}
    input_digest=digest({
        "positions":positions,"lines":lines,"horizon_min":horizon,
        "physical_dossier":dossier})
    snapshots={}
    # Dictionary insertion order fixes publication order and arm comparisons.
    for policy in POLICIES:
        result,trace,completed=b._engine(
            positions,lines,dossier,horizon,dispatch_policy=policy)
        require(set(completed)==set(paid) and
                result["paid_orders"]==len(paid) and
                result["synthetic_beverages"]==beverages and
                result["refunds_not_new_work"]==refunds,
                "MASS_BALANCE_DIFFERS_BETWEEN_POLICIES")
        diagnostic=c.diagnose_trace(
            result,trace,dossier,fixture_label=source_label,
            dispatch_policy=policy,
            _construction_capability=(
                c._VERIFIED_CONSTRUCTION_ADAPTER if construction else None))
        require(diagnostic["dispatch_policy"]==policy,
                "DIAGNOSTIC_POLICY_MISMATCH")
        snapshots[policy]=(result,trace,completed,diagnostic)
    base_result,base_trace,base_completed,base_diag=snapshots[POLICIES[0]]
    base_start=starts_by_task(base_trace)
    base_actors=actor_work(base_trace,dossier)
    policies=[]
    order_csv=[]
    for policy,(result,trace,completed,diagnostic) in snapshots.items():
        current_start=starts_by_task(trace)
        require(set(base_start)==set(current_start),
                "STAGE_TASKS_CHANGED_BY_PRIORITY")
        overrides=[event for event in trace
                   if event["event"]=="dispatch_override"]
        require((policy==POLICIES[0])== (len(overrides)==0)
                or policy!=POLICIES[0],
                "BASE_HAS_POLICY_OVERRIDES")
        require(all(e["policy"]==policy and
                    e["selected_stage"]==b.D_DISPATCH_STAGE[policy] for
                    e in overrides),
                "OVERRIDE_STAGE_DOES_NOT_MATCH_POLICY")
        affected_tasks=[]
        for key in base_start:
            a=base_start[key]
            z=current_start[key]
            delta=z["time"]-a["time"]
            moved_actor=a["actor"]!=z["actor"]
            moved_group=a["group"]!=z["group"]
            if abs(delta)>EPS or moved_actor or moved_group:
                affected_tasks.append({
                    **_public_task(key,pseudonym),
                    "baseline_start_min":round9(a["time"]),
                    "policy_start_min":round9(z["time"]),
                    "start_delta_min_positive_is_later":round9(delta),
                    "baseline_actor":a["actor"],"policy_actor":z["actor"],
                    "actor_changed":moved_actor,
                    "group_changed":moved_group,
                    "direction":("LATER" if delta>EPS else
                                 "EARLIER" if delta<-EPS else
                                 "SAME_TIME_DIFFERENT_RESOURCES"),
                })
        rows=[]
        for oid in paid_ids:
            baseline=base_completed[oid]
            now=completed[oid]
            delta=now-baseline
            stage_changes=[x for x in affected_tasks
                           if x["paid_case_label"]==pseudonym[oid]]
            row={
                "paid_case_label":pseudonym[oid],
                "paid_time_min":round9(paid[oid]["time"]),
                "beverages":paid[oid]["beverages"],
                "policy":policy,
                "baseline_handoff_min":round9(baseline),
                "policy_handoff_min":round9(now),
                "handoff_delta_min_positive_is_later":round9(delta),
                "baseline_paid_to_handoff_min":
                    round9(baseline-paid[oid]["time"]),
                "policy_paid_to_handoff_min":
                    round9(now-paid[oid]["time"]),
                "outcome":("LATER" if delta>EPS else
                           "EARLIER" if delta<-EPS else "UNCHANGED"),
                "changed_stage_count":len(stage_changes),
            }
            rows.append(row)
            order_csv.append(row)
        work=actor_work(trace,dossier)
        work_delta={
            actor:{
                "manual_task_count_change":work[actor][
                    "completed_manual_tasks"]-base_actors[actor][
                        "completed_manual_tasks"],
                "busy_manual_min_change":round9(
                    work[actor]["busy_manual_minutes"]-
                    base_actors[actor]["busy_manual_minutes"]),
                "stage_count_change":{
                    s:work[actor]["stage_counts"][s]-
                    base_actors[actor]["stage_counts"][s]
                    for s in work[actor]["stage_counts"]},
                "stage_busy_manual_min_change":{
                    s:round9(work[actor]["stage_busy_manual_min"][s]-
                             base_actors[actor]["stage_busy_manual_min"][s])
                    for s in work[actor]["stage_busy_manual_min"]},
            } for actor in work}
        override_rows=[]
        for event in overrides:
            earlier_key=task_key({
                "job":event["baseline_first_runnable_job"],
                "stage":event["baseline_first_runnable_stage"]})
            chosen_key=task_key({"job":event["selected_job"],
                                 "stage":event["selected_stage"]})
            override_rows.append({
                "minute":round9(event["time"]),
                "first_runnable_under_fcfs":
                    _public_task(earlier_key,pseudonym),
                "selected_instead":_public_task(chosen_key,pseudonym),
                "selected_actor":event["selected_actor"],
                "selected_group":event["selected_group"],
                "reason":"RUNNABLE_STAGE_PRIORITY_NOT_PREEMPTION",
            })
        p50=result["modeled_paid_to_handoff_p50_full_drain_min"]
        p90=result["modeled_paid_to_handoff_p90_full_drain_min"]
        bp50=base_result["modeled_paid_to_handoff_p50_full_drain_min"]
        bp90=base_result["modeled_paid_to_handoff_p90_full_drain_min"]
        handoff_advanced=sum(x["outcome"]=="EARLIER" for x in rows)
        handoff_later=sum(x["outcome"]=="LATER" for x in rows)
        has_service_delta=(handoff_advanced>0 or handoff_later>0 or
            result["modeled_handoffs_before_cut"]!=
            base_result["modeled_handoffs_before_cut"])
        dp90=(p90-bp90 if p90 is not None and bp90 is not None
               else None)
        before_delta=(result["modeled_handoffs_before_cut"]-
                      base_result["modeled_handoffs_before_cut"])
        if policy==POLICIES[0]:
            classification="ASSUMED_BASE_NOT_REAL_SHOP_DISPATCH"
        elif not overrides:
            classification="NO_RULE_INTERVENTION"
        elif not has_service_delta and (dp90 is None or abs(dp90)<=EPS):
            classification="RULE_INTERVENED_NO_SERVICE_DELTA_DEMONSTRATED"
        elif dp90 is None:
            classification="SERVICE_EFFECT_UNCLASSIFIED_MISSING_P90"
        elif dp90>EPS:
            classification=("MODEL_P90_WORSE_WITH_MIXED_ORDER_EFFECTS"
                            if handoff_advanced else
                            "MODEL_P90_WORSE_NO_ORDER_ADVANCED")
        elif dp90<-EPS:
            classification=("MODEL_P90_BETTER_WITH_LATE_ORDERS"
                            if handoff_later else
                            "MODEL_P90_BETTER_NO_LATE_ORDERS")
        else:
            classification=("MODEL_P90_TIE_WITH_ORDER_TRADEOFF"
                            if handoff_advanced or handoff_later else
                            "MODEL_P90_TIE_WITH_CUT_DIFFERENCE"
                            if before_delta else
                            "RULE_INTERVENED_NO_SERVICE_DELTA_DEMONSTRATED")
        decision_note=(
            "No priority intervention; no service effect attributable "
            "to this rule in this input." if not overrides else
            "P90 worsens and no order advances; do not call this a gain."
            if classification=="MODEL_P90_WORSE_NO_ORDER_ADVANCED" else
            "P90 improves but some orders finish later; report losers."
            if classification=="MODEL_P90_BETTER_WITH_LATE_ORDERS" else
            "P90 ties despite order-level changes; aggregate tie is not "
            "operational equivalence."
            if classification=="MODEL_P90_TIE_WITH_ORDER_TRADEOFF" else
            "Conditional scenario result, not a measured shop outcome.")
        start_by_stage={
            stage:{
                "earlier_tasks":sum(x["direction"]=="EARLIER" and
                                    x["stage"]==stage for x in affected_tasks),
                "later_tasks":sum(x["direction"]=="LATER" and
                                  x["stage"]==stage for x in affected_tasks),
                "earlier_start_minutes":round9(sum(
                    -x["start_delta_min_positive_is_later"]
                    for x in affected_tasks if x["stage"]==stage and
                    x["direction"]=="EARLIER")),
                "later_start_minutes":round9(sum(
                    x["start_delta_min_positive_is_later"]
                    for x in affected_tasks if x["stage"]==stage and
                    x["direction"]=="LATER")),
            } for stage in b.STAGES}
        policies.append({
            "policy":policy,
            "one_rule_changed":(
                "None: unchanged B FCFS ready-queue dispatch" if
                policy==POLICIES[0] else
                "Select an already-runnable "+b.D_DISPATCH_STAGE[policy]+
                " task before earlier runnable tasks, tie by ready order"),
            "rule_changed_assignment_count":len(overrides),
            "override_events_pseudonymous":override_rows,
            "paid_orders":result["paid_orders"],
            "synthetic_beverages":result["synthetic_beverages"],
            "handoffs_before_source_cut":result[
                "modeled_handoffs_before_cut"],
            "orders_pending_at_source_cut":result[
                "modeled_handoffs_after_cut"],
            "p50_paid_to_handoff_full_drain_min":p50,
            "p90_paid_to_handoff_full_drain_min":p90,
            "delta_p50_min_positive_is_worse":
                round9(p50-bp50) if p50 is not None else None,
            "delta_p90_min_positive_is_worse":
                round9(p90-bp90) if p90 is not None else None,
            "delta_handoffs_before_cut":
                result["modeled_handoffs_before_cut"]-
                base_result["modeled_handoffs_before_cut"],
            "orders_handoff_earlier":handoff_advanced,
            "orders_handoff_later":handoff_later,
            "orders_handoff_unchanged":sum(x["outcome"]=="UNCHANGED"
                                          for x in rows),
            "task_start_or_assignment_changes":affected_tasks,
            "task_changes_earlier":sum(x["direction"]=="EARLIER"
                                       for x in affected_tasks),
            "task_changes_later":sum(x["direction"]=="LATER"
                                     for x in affected_tasks),
            "work_assigned_by_actor":work,
            "work_assignment_delta_from_base":work_delta,
            "waits_from_C_diagnosis":{
                "total_resource_wait_task_min":diagnostic[
                    "causal_accounting"][
                        "total_resource_wait_task_min"],
                "stage_breakdown":diagnostic["causal_accounting"][
                    "stage_breakdown"],
                "strict_extraction_signal_task_min":diagnostic[
                    "hypotheses"]["extraction_limits"]["signal_task_min"],
                "manual_block_with_group_free_task_min":diagnostic[
                    "hypotheses"]["preparation_or_loading_limits"][
                        "signal_task_min_MANUAL_BLOCKED_WITH_GROUP_FREE"],
            },
            "classification":classification,
            "decision_note":decision_note,
            "start_shift_by_stage":start_by_stage,
            "not_a_real_intervention":True,
        })
    require(len(policies)==4 and len(order_csv)==4*len(paid),
            "EXACTLY_FOUR_PAIRED_SCENARIOS")
    report={
        "schema":SCHEMA,
        "source":("VERIFIED_EXISTING_CONSTRUCTION_SYNTHETIC_VIEWS" if
                  construction else "SOFTWARE_TOY_ONLY_NOT_REAL_CAFE"),
        "source_provenance":_source_provenance if construction else {
            "verified_adapter":"FIXED_SOFTWARE_TOY_NOT_CONSTRUCTION",
            "selected_load_label":load_label},
        "load_label":load_label,
        "source_label":source_label,
        "source_horizon_min":horizon,
        "scenario_input_sha256":input_digest,
        "physical_dossier_sha256":digest(dossier),
        "same_inputs_dossier_durations_windows_and_precedence":True,
        "same_two_operators_three_installed_groups":
            list(dossier["operators"])==["B01","B02"] and
            dossier["installed_group_ids"]==["G01","G02","G03"],
        "baseline_is_assumed_not_observed_dispatch":True,
        "eight_scenario_construction_plan_not_dispatched_here":
            source_label=="SOFTWARE_TOY_D_FIXED",
        "policies":policies,
        "per_order_pseudonymous":order_csv,
        "limits":{
            "no_real_service_effect_or_economic_threshold":True,
            "no_new_staff_or_historical_S5_support_assignment":True,
            "not_a_new_synthetic_world":True,
            "no_video_P_O_S_join":True,
            "not_robust_beyond_examined_scenarios":True,
            "simulated_policy_comparisons_only":True,
            "no_new_synthetic_corpus_or_OMC_or_provider":True,
            "R2_reads_are_recorded_by_execution_receipt_if_used":True,
        },
    }
    return report


def compare_existing_construction_q25_q75(view_dir,dossier, *,
                                           dispatch_authorized=False,
                                           source_receipt=None):
    """Read only P39/P11 verified construction views, then exactly eight arms.

    Called ONLY by an explicitly authorized main-line execution. Never fetch
    private R2, open truth, create a corpus or run from an ordinary PR CI.
    """
    require(dispatch_authorized is True,
            "Q25_Q75_REQUIRES_EXPLICIT_EXPERIMENTAL_AUTHORIZATION")
    selection=p11._verified_load_choices(view_dir)
    require([x["load_label"] for x in selection["selected"]]==
            list(ALLOWED_CONSTRUCTION),"EXACT_Q25_Q75_SELECTION")
    if source_receipt is not None:
        require(isinstance(source_receipt,dict) and
                source_receipt.get("status")==
                    "EXISTING_CONSTRUCTION_VIEWS_VERIFIED_NO_NEW_CORPUS" and
                source_receipt.get("read_only_source_run_id")==SOURCE_RUN_ID,
                "PRIVATE_SOURCE_RUN_RECEIPT_INVALID")
    compared=[]
    for index,chosen in enumerate(selection["selected"]):
        case=inputs.select_case_day(
            view_dir,chosen["case_id"],chosen["day"])
        require(case["partition"]=="CONSTRUCTION",
                "NO_DEVELOPMENT_OR_EVALUATION")
        require(case["horizon"]>0 and
                chosen["load_label"] in ALLOWED_CONSTRUCTION,
                "SELECTED_CASE_HORIZON_OR_LABEL")
        source_provenance={
            "verified_adapter":"P11_P39_CONSTRUCTION_SELECT_CASE_DAY",
            "selected_load_label":chosen["load_label"],
            "selected_case_day_digest":digest({
                "case_id":chosen["case_id"],"day":chosen["day"]}),
            "selection_receipt_sha256":digest(selection),
            "source_view_run_id":(
                source_receipt["read_only_source_run_id"]
                if source_receipt is not None else None),
            "source_type":(
                "R2_READ_ONLY_VERIFIED_RUN" if source_receipt is not None
                else "LOCAL_FIXTURE_VERIFIED_VIEWS_NO_R2_CLAIM"),
            "source_peak_horizon_min":case["horizon"],
            "partition":"CONSTRUCTION",
            "case_paid_input_digest":digest({
                "positions":case["positions"],"items":case["items"]}),
        }
        report=compare(
            case["positions"],case["items"],dossier,case["horizon"],
            source_label=("CONSTRUCTION_SYNTHETIC_Q25" if index==0 else
                          "CONSTRUCTION_SYNTHETIC_Q75"),
            load_label=chosen["load_label"],
            _verified_selection_capability=_VERIFIED_SELECTION_CAPABILITY,
            _source_provenance=source_provenance)
        compared.append(report)
    require(len(compared)==2 and
            sum(len(r["policies"]) for r in compared)==8,
            "EXACT_EIGHT_SCENARIOS_REQUIRED")
    return {
        "schema":CASE_SET_SCHEMA,
        "scope":"TWO_PREEXISTING_CONSTRUCTION_LOADS_NOT_REAL_SHOP",
        "selected_loads":list(ALLOWED_CONSTRUCTION),
        "scenario_count":8,
        "source":"P39_P11_VERIFIED_CONSTRUCTION_ONLY",
        "source_selection_sha256":digest(selection),
        "source_view_run_id":(
            source_receipt["read_only_source_run_id"]
            if source_receipt is not None else None),
        "results":compared,
        "not_a_new_evidence_collection":True,
    }



def effect_direction(delta):
    if delta is None:
        return "UNKNOWN"
    return "BETTER" if delta<-EPS else "WORSE" if delta>EPS else "TIE"


def _public_construction_summary(case_set, execution_receipt=None):
    """Only aggregates cross the public artifact boundary, never order rows."""
    require(case_set["schema"]==CASE_SET_SCHEMA and
            case_set["scenario_count"]==8 and
            len(case_set["results"])==2 and
            [x["load_label"] for x in case_set["results"]]==
            list(ALLOWED_CONSTRUCTION),"WRONG_CASE_SET")
    results=[]
    for load in case_set["results"]:
        require(load["schema"]==SCHEMA and len(load["policies"])==4 and
                load["source_provenance"]["verified_adapter"]==
                    "P11_P39_CONSTRUCTION_SELECT_CASE_DAY" and
                load["source_provenance"]["selected_load_label"]==
                    load["load_label"],"UNVERIFIED_CASE_IN_SET")
        arm_rows=[]
        for p in load["policies"]:
            arm_rows.append({
                "policy":p["policy"],
                "rule_changed_assignment_count":
                    p["rule_changed_assignment_count"],
                "handoffs_before_source_cut":p["handoffs_before_source_cut"],
                "orders_pending_at_source_cut":p["orders_pending_at_source_cut"],
                "p50_paid_to_handoff_full_drain_min":
                    p["p50_paid_to_handoff_full_drain_min"],
                "p90_paid_to_handoff_full_drain_min":
                    p["p90_paid_to_handoff_full_drain_min"],
                "delta_p50_min_positive_is_worse":
                    p["delta_p50_min_positive_is_worse"],
                "delta_p90_min_positive_is_worse":
                    p["delta_p90_min_positive_is_worse"],
                "delta_handoffs_before_cut":p["delta_handoffs_before_cut"],
                "orders_handoff_earlier":p["orders_handoff_earlier"],
                "orders_handoff_later":p["orders_handoff_later"],
                "orders_handoff_unchanged":p["orders_handoff_unchanged"],
                "task_changes_earlier":p["task_changes_earlier"],
                "task_changes_later":p["task_changes_later"],
                "start_shift_by_stage":p["start_shift_by_stage"],
                "work_assigned_by_actor":p["work_assigned_by_actor"],
                "work_assignment_delta_from_base":
                    p["work_assignment_delta_from_base"],
                "waits_from_C_diagnosis":p["waits_from_C_diagnosis"],
                "classification":p["classification"],
                "decision_note":p["decision_note"],
                "p90_direction_vs_assumed_FCFS":
                    effect_direction(p["delta_p90_min_positive_is_worse"]),
            })
        results.append({
            "load_label":load["load_label"],
            "source_provenance":load["source_provenance"],
            "source_horizon_min":load["source_horizon_min"],
            "scenario_input_sha256":load["scenario_input_sha256"],
            "physical_dossier_sha256":load["physical_dossier_sha256"],
            "arms":arm_rows,
        })
    cross=[]
    for idx in range(4):
        a=results[0]["arms"][idx]
        z=results[1]["arms"][idx]
        require(a["policy"]==z["policy"]==POLICIES[idx],
                "POLICY_PAIR_MISALIGNED")
        direction_a=a["p90_direction_vs_assumed_FCFS"]
        direction_z=z["p90_direction_vs_assumed_FCFS"]
        if idx==0:
            verdict="BASELINE_ASSUMED_NOT_REAL_POLICY"
        elif direction_a!=direction_z:
            verdict="DIRECTION_DIFFERS_BETWEEN_Q25_AND_Q75"
        elif direction_a=="TIE":
            verdict=("P90_TIE_WITH_TASK_OR_ORDER_CHANGE" if
                     any(x["rule_changed_assignment_count"] or
                         x["orders_handoff_earlier"] or
                         x["orders_handoff_later"] for x in (a,z)) else
                     "NO_MEASURED_P90_DIFFERENCE_IN_THESE_TWO_INPUTS")
        elif direction_a=="BETTER" and (
                a["orders_handoff_later"] or z["orders_handoff_later"]):
            verdict="BOTH_P90_BETTER_BUT_SOME_ORDERS_LATER"
        elif direction_a=="WORSE":
            verdict="BOTH_P90_WORSE_IN_ASSUMED_MODEL"
        else:
            verdict="SAME_DIRECTION_WITHOUT_PROVEN_REAL_WORLD_EFFECT"
        cross.append({
            "policy":POLICIES[idx],
            "Q25_p90_direction":direction_a,
            "Q75_p90_direction":direction_z,
            "Q25_advanced_orders":a["orders_handoff_earlier"],
            "Q25_delayed_orders":a["orders_handoff_later"],
            "Q75_advanced_orders":z["orders_handoff_earlier"],
            "Q75_delayed_orders":z["orders_handoff_later"],
            "interpretation":verdict,
        })
    receipt=(dict(execution_receipt) if execution_receipt is not None else {
        "status":"LOCAL_FIXTURE_NOT_GITHUB_RUN",
        "github_run_id":None,
        "github_commit_sha":None,
        "source_view_run_id":None,
        "R2_read_attempts":"NONE_IN_LOCAL_FIXTURE",
        "R2_billing_cost":"UNKNOWN_NOT_BILLED",
        "new_solver_and_provider_attempts":0,
        "no_new_corpus":True,
    })
    if receipt.get("status")=="GITHUB_MANUAL_EIGHT_ARM_DISPATCH":
        require(receipt.get("github_run_id") and
                receipt.get("github_commit_sha") and
                receipt.get("source_view_run_id")==SOURCE_RUN_ID and
                receipt.get("R2_read_attempts")!="NONE_IN_LOCAL_FIXTURE",
                "INCOMPLETE_MANUAL_EXECUTION_RECEIPT")
    return {
        "schema":"arena.coffee.p46.public-eight-scenario-aggregate/1",
        "scope":"SYNTHETIC_VERIFIED_CONSTRUCTION_ONLY_NOT_REAL_CAFE",
        "selected_loads":list(ALLOWED_CONSTRUCTION),
        "scenario_count":8,
        "source_selection_sha256":case_set["source_selection_sha256"],
        "source_view_run_id":case_set["source_view_run_id"],
        "execution_and_consumption":receipt,
        "results":results,
        "paired_interpretation":cross,
        "limits":{
            "not_real_cafe_service_evidence":True,
            "not_a_policy_selection_or_economic_benefit":True,
            "full_per_order_and_task_rows_not_in_public_artifact":True,
            "only_existing_construction_not_reserved_data":True,
        },
    }


def _export_case_set(case_set,output_dir, *, execution_receipt=None):
    aggregate=_public_construction_summary(case_set,execution_receipt)
    target=Path(output_dir)
    require(not target.exists(),"OUTPUT_ALREADY_EXISTS")
    target.mkdir(mode=0o700,parents=True)
    write_json(target/"D_Q25_Q75_AGGREGATE.json",aggregate,exclusive=True)
    rows=[]
    stage_rows=[]
    for load in aggregate["results"]:
        for arm in load["arms"]:
            rows.append({
                "load_label":load["load_label"],
                "policy":arm["policy"],
                "priority_interventions":
                    arm["rule_changed_assignment_count"],
                "handoffs_before_source_cut":arm["handoffs_before_source_cut"],
                "pending_at_source_cut":arm["orders_pending_at_source_cut"],
                "p50_min":arm["p50_paid_to_handoff_full_drain_min"],
                "p90_min":arm["p90_paid_to_handoff_full_drain_min"],
                "delta_p90_positive_is_worse":
                    arm["delta_p90_min_positive_is_worse"],
                "p90_direction":arm["p90_direction_vs_assumed_FCFS"],
                "orders_earlier":arm["orders_handoff_earlier"],
                "orders_later":arm["orders_handoff_later"],
                "classification":arm["classification"],
            })
            for actor,details in arm["work_assigned_by_actor"].items():
                for stage,minutes in details["stage_busy_manual_min"].items():
                    stage_rows.append({
                        "load_label":load["load_label"],
                        "policy":arm["policy"],
                        "operator":actor,
                        "stage":stage,
                        "tasks":details["stage_counts"][stage],
                        "busy_manual_min":minutes,
                        "delta_busy_manual_min":arm[
                            "work_assignment_delta_from_base"][actor][
                                "stage_busy_manual_min_change"][stage],
                        "earlier_task_starts":arm["start_shift_by_stage"][
                            stage]["earlier_tasks"],
                        "later_task_starts":arm["start_shift_by_stage"][
                            stage]["later_tasks"],
                    })
    for name,records in (
            ("D_Q25_Q75_PAIRED.csv",rows),
            ("D_Q25_Q75_OPERATOR_STAGE.csv",stage_rows)):
        require(records,"EMPTY_CONSTRUCTION_AGGREGATE")
        with (target/name).open("x",encoding="utf-8",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    lines=[
        "# D — comparación Q25/Q75 de ocho escenarios de construcción",
        "",
        "**No son pedidos reales ni una medición de desempeño del local.**",
        "**Run:** "+str(aggregate["execution_and_consumption"].get(
            "github_run_id")),
        "**Commit:** "+str(aggregate["execution_and_consumption"].get(
            "github_commit_sha")),
        "**Fuente privada histórica:** "+
            str(aggregate["source_view_run_id"]),
        "**Estado de consumo:** "+
            str(aggregate["execution_and_consumption"].get(
                "R2_billing_cost","UNKNOWN")),
        "**Selección verificada:** "+aggregate["source_selection_sha256"],
        "",
        "| Carga | Política | Cambios de decisión | Entregas antes corte | "
        "Pendientes | P50 | P90 | ΔP90 | Adelantados/Demorados | Lectura |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append("| "+row["load_label"]+" | "+row["policy"]+" | "+
                     str(row["priority_interventions"])+" | "+
                     str(row["handoffs_before_source_cut"])+" | "+
                     str(row["pending_at_source_cut"])+" | "+
                     str(row["p50_min"])+" | "+str(row["p90_min"])+
                     " | "+str(row["delta_p90_positive_is_worse"])+
                     " | "+str(row["orders_earlier"])+"/"+
                     str(row["orders_later"])+" | "+row["classification"]+" |")
    lines+=["","## Consistencia entre cargas",""]
    for cross in aggregate["paired_interpretation"]:
        lines.append("- "+cross["policy"]+": Q25="+cross[
            "Q25_p90_direction"]+", Q75="+cross["Q75_p90_direction"]+
            "; "+cross["interpretation"]+".")
    lines += [
        "",
        "## Trabajo desplazado",
        "",
        "La tabla separada D_Q25_Q75_OPERATOR_STAGE.csv informa minutos "
        "manuales B01/B02 por etapa y cambios relativos a la base; "
        "las cuentas de inicios adelantados/demorados son por etapa.",
        "",
        "## Límites",
        "",
        "P90 se calcula sobre el drenaje completo. Dos políticas con el "
        "mismo P90 pueden cambiar distintos pedidos. Una reducción de "
        "P90 con pedidos más tardíos requiere registrar ese costo.",
        "La ruta de construcción se seleccionó mediante P11 y "
        "select_case_day; no se mezclaron intervalos de video.",
        "El reporte público contiene sólo agregados; nunca incluye los "
        "identificadores de pedidos ni los cambios de tarea individuales.",
        "Un GET a R2 puede tener costo aun si falla; el costo de R2 se "
        "marca UNKNOWN si no existe recibo de facturación.",
        "No se realizó una nueva campaña, un envío a proveedor ni OMC. "
        "Esta ejecución de políticas locales no establece ahorro real.",
    ]
    (target/"D_Q25_Q75_DECISION.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")
    return aggregate


ORDER_FIELDS=("paid_case_label","paid_time_min","beverages","policy",
              "baseline_handoff_min","policy_handoff_min",
              "handoff_delta_min_positive_is_later",
              "baseline_paid_to_handoff_min",
              "policy_paid_to_handoff_min",
              "outcome","changed_stage_count")


def export(report,output_dir, *, execution_receipt=None):
    require(isinstance(report,dict),"INVALID_EXPORT_REPORT")
    if report.get("schema")==CASE_SET_SCHEMA:
        return _export_case_set(
            report,output_dir,execution_receipt=execution_receipt)
    target=Path(output_dir)
    require(not target.exists(),"OUTPUT_ALREADY_EXISTS")
    require(report.get("schema")==SCHEMA,"WRONG_REPORT_FOR_EXPORT")
    target.mkdir(parents=True)
    write_json(target/"D_PAIRED_POLICY_COMPARISON.json",
               report,exclusive=True)
    with (target/"D_ORDER_OUTCOMES_PSEUDONYMOUS.csv").open(
            "x",newline="",encoding="utf-8") as out:
        writer=csv.DictWriter(out,fieldnames=ORDER_FIELDS,
                              extrasaction="raise")
        writer.writeheader()
        writer.writerows(report["per_order_pseudonymous"])
    md=[
        "# Entrega D — comparación condicionada de prioridades",
        "",
        "**Fuente:** "+report["load_label"]+" ("+(
            "microfixture de software ficticio" if
            report["source_label"]=="SOFTWARE_TOY_D_FIXED" else
            "carga sintética de construcción verificada por P11")+
            "; nunca pedidos observados de la cafetería).",
        "**Dossier:** "+report["physical_dossier_sha256"],
        "**Identidad de entradas:** "+report["scenario_input_sha256"],
        "**Horizonte de corte de la fuente:** "+
            str(report["source_horizon_min"])+" min.",
        "",
        "Un resultado de una política frente a FCFS asumido **NO** equivale "
        "a una mejora frente al despacho real de la cafetería.",
        "",
        "| Política | Sobrescrituras de prioridad | Entregas antes del corte | "
        "Pendientes | P50 | P90 | ΔP90 (positivo=peor) | "
        "Pedidos adelantados / demorados |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["policies"]:
        md.append("| "+row["policy"]+" | "+
                  str(row["rule_changed_assignment_count"])+" | "+
                  str(row["handoffs_before_source_cut"])+" | "+
                  str(row["orders_pending_at_source_cut"])+" | "+
                  str(row["p50_paid_to_handoff_full_drain_min"])+" | "+
                  str(row["p90_paid_to_handoff_full_drain_min"])+" | "+
                  str(row["delta_p90_min_positive_is_worse"])+" | "+
                  str(row["orders_handoff_earlier"])+"/"+
                  str(row["orders_handoff_later"])+" |")
    for row in report["policies"]:
        if row["policy"]==POLICIES[0]:
            continue
        md.extend([
            "",
            "## "+row["policy"],
            "",
            "**Clasificación:** "+row["classification"],
            "**Regla:** "+row["one_rule_changed"],
            "**Asignaciones cambiadas por prioridad:** "+
                str(row["rule_changed_assignment_count"]),
            "**Tareas adelantadas / demoradas por inicio:** "+
                str(row["task_changes_earlier"])+"/"+
                str(row["task_changes_later"]),
            "**Espera por recursos (C):** "+
                str(row["waits_from_C_diagnosis"][
                    "total_resource_wait_task_min"])+" min-tarea",
            "**Lectura direccional:** "+row["decision_note"],
            "**Inicios cambiados por etapa:** "+
                ", ".join(stage+":"+
                    str(summary["earlier_tasks"])+"/"+
                    str(summary["later_tasks"]) for stage,summary in
                    row["start_shift_by_stage"].items()),
            "**Trabajo reasignado (minutos por operador y etapa):** "+
                ", ".join(actor+"="+
                    ", ".join(stage+":"+str(minutes) for stage,minutes in
                    record["stage_busy_manual_min"].items()) for actor,record
                    in row["work_assigned_by_actor"].items())+
                " (min, recursos existentes; deltas en JSON).",
        ])
    md.extend([
        "",
        "## Límites",
        "",
        "Se mantienen dos operadores, tres grupos instalados, calendario, "
        "recetas, duraciones y reglas físicas dentro de cada comparación. "
        "Una política mueve trabajo; no crea ventas ni personal.",
        "La entrega usa un operador existente B01/B02, no el recurso "
        "existing_support del S5 histórico.",
        "La evaluación causal C cuenta esperas por tareas sin doble "
        "atribución de recursos; no equivale a una mejora monetaria.",
        "Las pruebas de CI usan sólo el microcaso ficticio; el lote "
        "Q25/Q75 de ocho escenarios requiere acceso privado verificado "
        "y autorización vigente en main.",
    ])
    (target/"D_PAIRED_POLICY_COMPARISON.md").write_text(
        "\n".join(md)+"\n",encoding="utf-8")



def _verified_github_manual_execution():
    from . import coffee_e2e as e2e
    require(os.environ.get("GITHUB_EVENT_NAME")=="workflow_dispatch",
            "ONLY_EXPLICIT_WORKFLOW_DISPATCH")
    require(os.environ.get("GITHUB_WORKFLOW_REF","").endswith(
            "/.github/workflows/coffee-hydra-p46-d-manual.yml@refs/heads/main"),
            "WRONG_MANUAL_WORKFLOW_OR_NONMAIN_REF")
    run_id,sha=e2e.execution_identity()
    return run_id,sha


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("toy","fetch-private-views",
                                           "construction"),default="toy")
    parser.add_argument("--toy-input")
    parser.add_argument("--dossier")
    parser.add_argument("--out",required=True)
    parser.add_argument("--source-receipt")
    parser.add_argument("--construction-views")
    parser.add_argument("--source-run-id",type=int)
    parser.add_argument("--authorize-eight-scenarios",action="store_true")
    args=parser.parse_args(argv)
    if args.mode=="toy":
        require(args.toy_input and args.dossier and
                not args.construction_views and
                not args.authorize_eight_scenarios and
                args.source_run_id is None and
                args.source_receipt is None,
                "TOY_ARGUMENTS_ONLY")
        fixture=read_json(args.toy_input)
        require(fixture.get("schema")==c.FIXTURE_SCHEMA and
                fixture.get("scope")=="SOFTWARE_TOY_ONLY",
                "CLI_ONLY_PREEXISTING_SOFTWARE_TOY")
        report=compare(fixture["positions"],fixture["lines"],
                       read_json(args.dossier),fixture["horizon_min"])
        export(report,args.out)
        print("P46_D_SOFTWARE_FIXTURE",len(report["policies"]),
              "NEW_SCIENTIFIC_RUNS",0)
        return
    require(args.authorize_eight_scenarios and
            args.source_run_id==SOURCE_RUN_ID and
            args.source_receipt and not args.toy_input,
            "PRIVATE_CONSTRUCTION_REQUIRES_EXACT_AUTHORIZATION")
    run_id,sha=_verified_github_manual_execution()
    receipt_path=Path(args.source_receipt)
    if args.mode=="fetch-private-views":
        require(not receipt_path.exists() and
                not Path(args.out).exists() and
                not args.dossier and not args.construction_views,
                "PRIVATE_SOURCE_RECEIPT_OUTPUTS_ALREADY_EXIST")
        from . import coffee_s5_availability as s5
        initial={
            "status":"R2_READ_ATTEMPT_STARTED_OUTCOME_UNKNOWN",
            "github_run_id":run_id,
            "github_commit_sha":sha,
            "read_only_source_run_id":SOURCE_RUN_ID,
            "R2_read_attempts":"UNKNOWN_IF_PARTIAL_FAILURE",
            "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
            "new_solver_and_provider_attempts":0,
            "no_new_corpus":True,
        }
        write_json(receipt_path,initial,exclusive=True)
        # If an R2 GET fails, the attempt receipt remains and CI fails;
        # never assert a zero cost or assume all view objects were retrieved.
        source=s5.fetch_existing_construction_views(args.out)
        require(source["read_only_source_run_id"]==SOURCE_RUN_ID,
                "SOURCE_RUN_MISMATCH")
        from . import coffee_e2e as e2e
        final=dict(initial,**source)
        final.update({
            "github_run_id":run_id,
            "github_commit_sha":sha,
            "R2_read_attempts":len(e2e.VIEW_FILES),
            "R2_views_successfully_retrieved":len(e2e.VIEW_FILES),
            "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
        })
        write_json(receipt_path,final)
        print("P46_D_SOURCE_VERIFIED",SOURCE_RUN_ID,
              "VIEW_GET_ATTEMPTS",len(e2e.VIEW_FILES),
              "R2_BILLING_COST_UNKNOWN",True)
        return
    require(args.mode=="construction" and args.dossier and
            args.construction_views and
            Path(args.construction_views).is_dir() and
            not Path(args.out).exists() and
            Path(args.source_receipt).is_file(),
            "CONSTRUCTION_ARGS_OR_MISSING_SOURCE_RECEIPT")
    receipt=read_json(args.source_receipt)
    require(receipt.get("status")==
                "EXISTING_CONSTRUCTION_VIEWS_VERIFIED_NO_NEW_CORPUS" and
            receipt.get("read_only_source_run_id")==SOURCE_RUN_ID and
            receipt.get("github_run_id")==run_id and
            receipt.get("github_commit_sha")==sha,
            "PRIVATE_VIEW_RECEIPT_NOT_FROM_THIS_RUN")
    report=compare_existing_construction_q25_q75(
        args.construction_views,
        read_json(args.dossier),dispatch_authorized=True,
        source_receipt=receipt)
    execution_receipt={
        "status":"GITHUB_MANUAL_EIGHT_ARM_DISPATCH",
        "github_run_id":run_id,
        "github_commit_sha":sha,
        "source_view_run_id":SOURCE_RUN_ID,
        "R2_read_attempts":receipt["R2_read_attempts"],
        "R2_views_successfully_retrieved":receipt.get(
            "R2_views_successfully_retrieved"),
        "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
        "new_solver_and_provider_attempts":0,
        "new_synthetic_worlds":0,
        "new_corpus":False,
    }
    export(report,args.out,execution_receipt=execution_receipt)
    print("P46_D_VERIFIED_CONSTRUCTION",report["scenario_count"],
          "SOURCE_RUN_ID",SOURCE_RUN_ID,"GITHUB_RUN_ID",run_id,
          "R2_BILLING_COST_UNKNOWN",True)


if __name__=="__main__":
    main()
