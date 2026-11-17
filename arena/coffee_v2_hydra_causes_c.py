"""P45 C: auditable *conditional* waiting mechanisms for the P44 fixed DES.

Consumes PRIVATE trace from the unchanged FCFS policy. It neither suggests
an optimal policy nor attributes synthetic waits to the real coffee shop.
Precedence-not-yet-eligible is NOT counted as resource waiting. The same
interval can have multiple blockers: no per-resource causal delay is claimed.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path

from .common import ArenaError, read_json, write_json
from . import coffee_v2_hydra_physical_b as b
from . import coffee_hydra_episodes_a as a

SCHEMA="arena.coffee.p45.causal-wait-diagnosis/1"
FIXTURE_SCHEMA="arena.coffee.p45.causal-toy-input/1"
EPS=1e-7


def require(ok, code):
    if not ok:
        raise ArenaError("COFFEE_P45_C_"+code)


def rounded(value):
    return round(float(value), 9)


def _keys(trace, kind):
    return [row for row in trace if row["event"]==kind]


def diagnose_trace(result, trace, dossier, *, fixture_label,
                   episode_view=None, historical_dossier=None):
    """Aggregate authenticated model trace, never publish private job IDs.

    Every blocked interval is counted ONCE per waiting task. Summing
    concurrent task-minutes yields workload delay, not real elapsed minutes;
    no blocker receives an exclusive attribution when several are feasible.
    """
    b.validate(dossier)
    require(result.get("schema")==b.RESULT_SCHEMA and
            result.get("status")==
            "SIMULATED_CONDITIONAL_PHYSICAL_B_NOT_EMPIRICAL",
            "INCOMPATIBLE_ENGINE_RESULT")
    require(isinstance(fixture_label,str) and fixture_label.startswith(
            "SOFTWARE_TOY_"),"REQUIRES_EXPLICIT_TOY_SCOPE")

    eligible={}
    starts={}
    finishes={}
    intervals=defaultdict(list)
    not_yet_eligible=0
    for item in trace:
        event=item["event"]
        if event=="pending_precedence":
            require(item.get("eligible") is False and
                    item["stage"] in b.STAGE_PREDECESSOR,
                    "MALFORMED_PRECEDENCE_PENDING")
            not_yet_eligible+=1
        elif event=="eligible":
            key=(tuple(item["job"]),item["stage"])
            require(key not in eligible and
                    item["predecessor"]==b.STAGE_PREDECESSOR[item["stage"]],
                    "DUPLICATE_OR_INVALID_ELIGIBILITY")
            eligible[key]=item
        elif event=="start":
            key=(tuple(item["job"]),item["stage"])
            require(key not in starts and
                    item["precedence_satisfied"] is True and
                    item["stage"] in b.STAGES,
                    "DUPLICATE_OR_INVALID_STAGE_START")
            starts[key]=item
        elif event=="finish":
            key=(tuple(item["job"]),item["stage"])
            require(key not in finishes,"DUPLICATE_FINISH")
            finishes[key]=item
        elif event=="blocked_interval":
            key=(tuple(item["job"]),item["stage"])
            require(item["end_time"]>item["start_time"] and
                    item["minutes"]>0 and
                    abs(item["minutes"]-
                        (item["end_time"]-item["start_time"]))<EPS and
                    item["blocking"]["all_routes_blocked"] is True,
                    "MALFORMED_BLOCKED_INTERVAL")
            routes=item["blocking"]["alternative_routes"]
            require(routes and
                    all(route["blockers"] for route in routes),
                    "UNBLOCKED_ALTERNATIVE_RECORDED_AS_WAIT")
            intervals[key].append(item)

    require(eligible.keys()==starts.keys()==finishes.keys(),
            "MISSING_ELIGIBLE_START_OR_FINISH")
    require(set(intervals)<=set(starts),"ORPHAN_BLOCKED_INTERVAL")
    by_stage={s:{"completed_tasks":0,"tasks_with_resource_wait":0,
                 "resource_wait_task_min":0.0,"blocked_intervals":0}
              for s in b.STAGES}
    buckets=defaultdict(float)
    grouped_blocking=defaultdict(lambda:{"intervals":0,"task_min":0.0})
    sample_count=0
    multi_blocker_time=0.0
    group_extract_time=0.0
    group_postauto_time=0.0
    prep_load_pressure=0.0
    milk_handoff_pressure=0.0
    total_task_wait=0.0
    max_wait=0.0
    for key,start in starts.items():
        ready=eligible[key]
        finish=finishes[key]
        stage=key[1]
        wait=start["time"]-ready["time"]
        require(wait>=-EPS and finish["time"]>start["time"] and
                abs(start["eligible_at"]-ready["time"])<EPS and
                abs(start["resource_wait_min"]-max(0,wait))<EPS,
                "PRECEDENCE_AND_RESOURCE_WAIT_INCONSISTENT")
        spans=sorted(intervals[key],key=lambda row:row["start_time"])
        cursor=ready["time"]
        for span in spans:
            require(abs(span["start_time"]-cursor)<EPS and
                    span["end_time"]<=start["time"]+EPS,
                    "GAP_OVERLAP_OR_POST_START_BLOCKED_INTERVAL")
            cursor=span["end_time"]
        require(abs(cursor-start["time"])<EPS,
                "RESOURCE_WAIT_NOT_PARTITIONED_BY_INTERVALS")

        wait=max(0.0,wait)
        total_task_wait+=wait
        max_wait=max(max_wait,wait)
        by_stage[stage]["completed_tasks"]+=1
        by_stage[stage]["resource_wait_task_min"]+=wait
        by_stage[stage]["blocked_intervals"]+=len(spans)
        if wait>EPS:
            by_stage[stage]["tasks_with_resource_wait"]+=1
        for span in spans:
            minutes=span["minutes"]
            details=span["blocking"]
            routes=details["alternative_routes"]
            # Route reasons are an OR-of-allocations with AND-of-blockers.
            # Multiple reasons can coexist, including on the same route.
            # Their intervals are intentionally NOT additive contributions.
            patterns=tuple(sorted({
                "+".join(sorted(set(route["blockers"])))
                for route in routes}))
            signature=stage+" | "+" || ".join(patterns)
            grouped_blocking[signature]["intervals"]+=1
            grouped_blocking[signature]["task_min"]+=minutes
            if any(len(route["blockers"])>1 for route in routes):
                multi_blocker_time+=minutes
            for reason in set(reason for route in routes
                              for reason in route["blockers"]):
                buckets[reason]+=minutes
            if stage in ("prepare","load"):
                prep_load_pressure+=minutes
            if stage in ("milk","handoff"):
                milk_handoff_pressure+=minutes
            if stage=="load":
                all_groups={route["resource"]:route["group_state"]
                            for route in routes}
                actor_feasible=any(
                    not any(reason.startswith("ACTOR_")
                            for reason in route["blockers"])
                    for route in routes)
                if all_groups and all(state=="EXTRACTING" for state in
                                      all_groups.values()) and actor_feasible:
                    group_extract_time+=minutes
                if any(state in ("AWAITING_REMOVAL","REMOVING",
                                 "AWAITING_CLEAN","CLEANING")
                       for state in all_groups.values()):
                    group_postauto_time+=minutes
            sample_count+=1

    require(sum(item["completed_tasks"] for item in by_stage.values())==
            sum(result["stage_counts"].values()),
            "STAGE_COUNTS_MISMATCH")
    by_stage={k:{"completed_tasks":v["completed_tasks"],
                 "tasks_with_resource_wait":v["tasks_with_resource_wait"],
                 "resource_wait_task_min":rounded(
                     v["resource_wait_task_min"]),
                 "blocked_intervals":v["blocked_intervals"]}
              for k,v in by_stage.items()}

    bridge=None
    if episode_view is not None or historical_dossier is not None:
        require(episode_view is not None and
                historical_dossier is not None,
                "INCOMPLETE_A_B_BRIDGE")
        old=a.check(episode_view,historical_dossier)
        new=b.episode_adapter(episode_view,dossier)
        old_by={x["question"]:x["status"] for x in old["checks"]}
        new_by={x["question"]:x["status"] for x in new["checks"]}
        bridge={
            "source":"KNOWN_AST RA_CONSTRUCTION_EPISODES".replace(" ",""),
            "independent_validation":False,
            "historical_vs_B_status":{
                k:{"historical":old_by[k],"physical_B":new_by[k]}
                for k in old_by},
            "interpretation":(
                "A changed feasibility verdict identifies a representation "
                "difference; it is NOT a measured cause of customer waiting. "
                "Two-person visibility is point-sampled, not a full calendar."),
        }

    report={
        "schema":SCHEMA,
        "scope":"SOFTWARE_TOY_SIMULATION_DIAGNOSTIC_NOT_REAL_CAFE",
        "fixture_label":fixture_label,
        "engine_schema":b.RESULT_SCHEMA,
        "dispatch_policy":dossier["dispatch_policy"],
        "source_contract":{
            "synthetic_paid_gate":True,
            "dossier_schema":dossier["schema"],
            "assumed_windows":dossier["operator_calendar_status"],
            "assumed_durations":True,
            "real_order_links":0,
            "manual_duration_observed":False,
            "video_to_scenario_clock_alignment":"NOT_ESTABLISHED",
        },
        "private_trace_sha256":hashlib.sha256(json.dumps(
            trace,sort_keys=True,ensure_ascii=False,
            separators=(",",":")).encode("utf-8")).hexdigest(),
        "causal_accounting":{
            "precedence_pending_markers_not_timed":not_yet_eligible,
            "eligible_stage_tasks":len(eligible),
            "blocked_intervals":sample_count,
            "total_resource_wait_task_min":rounded(total_task_wait),
            "maximum_single_task_resource_wait_min":rounded(max_wait),
            "stage_breakdown":by_stage,
            "multi_blocker_candidate_task_min_NOT_EXCLUSIVE":
                rounded(multi_blocker_time),
            "reason_presence_task_min_OVERLAPPING_NOT_ADDITIVE":{
                k:rounded(v) for k,v in sorted(buckets.items())},
            "route_blocking_patterns":[
                {"stage_and_alternative_route_reasons":k,
                 "intervals":v["intervals"],
                 "task_min_NOT_EXCLUSIVE":rounded(v["task_min"])}
                for k,v in sorted(grouped_blocking.items())],
            "counting_rule":(
                "Each eligible task interval counted once. Concurrent task "
                "waits can overlap; multiple blocking routes and reasons "
                "are evidence, not independently attributable minutes. "
                "Precedence-pending time is not resource waiting."),
        },
        "hypotheses":{
            "extraction_limits":{
                "signal":"load eligible, all enabled groups EXTRACTING, "
                         "at least one qualified free-window actor route",
                "signal_task_min":rounded(group_extract_time),
                "status":("SIGNAL_IN_ASSUMED_MODEL" if group_extract_time>EPS
                          else "NOT_ESTABLISHED_BY_THIS_MODEL_TRACE"),
                "weakens":"group free, or load held by actor/other states; "
                          "group held after counter is not extraction work",
                "post_auto_group_held_load_wait_task_min":
                    rounded(group_postauto_time),
                "external_evidence":"NOT_IDENTIFIED_FROM_VIDEO"},
            "preparation_or_loading_limits":{
                "signal":"eligible prepare/load task blocked by modeled "
                         "actor, preparation station or group",
                "signal_task_min_ANY_CAUSE":rounded(prep_load_pressure),
                "status":("WAIT_IN_ASSUMED_MODEL" if
                          prep_load_pressure>EPS else "NO_WAIT_IN_TOY_TRACE"),
                "weakens":"task still awaits its predecessor; that time is "
                          "not counted as resource waiting",
                "external_evidence":"NOT_IDENTIFIED_FROM_VIDEO"},
            "milk_or_handoff_limits":{
                "signal":"eligible milk/handoff blocked by the declared "
                         "actor and steam wand/pickup pass resources",
                "signal_task_min_ANY_CAUSE":rounded(milk_handoff_pressure),
                "status":("WAIT_IN_ASSUMED_MODEL" if
                          milk_handoff_pressure>EPS else "NO_WAIT_IN_TOY_TRACE"),
                "weakens":"a policy change must be tested in D before "
                          "claiming its effect on paid-to-handoff P90",
                "external_evidence":"NOT_IDENTIFIED_FROM_VIDEO"},
            "representation_artifact":{
                "observational_A_B_check":bridge,
                "status":("A_B_CONSTRUCTION_FEASIBILITY_RECONCILED" if
                          bridge is not None else
                          "NOT_EVALUATED_WITH_OBSERVATIONAL_EPISODES"),
                "external_evidence":"CONSTRUCTION_ONLY_NOT_NEW_VALIDATION"},
        },
        "service_metrics_not_derived_from_stage_wait_sums":{
            "paid_orders":result["paid_orders"],
            "synthetic_beverages":result["synthetic_beverages"],
            "modeled_handoffs_before_cut":result[
                "modeled_handoffs_before_cut"],
            "modeled_paid_to_handoff_p50_full_drain_min":result[
                "modeled_paid_to_handoff_p50_full_drain_min"],
            "modeled_paid_to_handoff_p90_full_drain_min":result[
                "modeled_paid_to_handoff_p90_full_drain_min"],
        },
        "limits":{
            "not_a_policy_effect":True,
            "not_an_empirical_bottleneck_measure":True,
            "not_a_real_minutes_saved_estimate":True,
            "no_order_identity_exposed":True,
            "no_counter_as_group_release":True,
            "no_OMC_provider_R2_or_scientific_campaign":True,
        },
    }
    require(math.isfinite(report["causal_accounting"][
        "total_resource_wait_task_min"]), "NONFINITE_WAIT")
    return report


def diagnose(positions, lines, dossier, horizon, *, fixture_label,
             episode_view=None, historical_dossier=None):
    result,trace,_=b._engine(positions,lines,dossier,horizon)
    return diagnose_trace(result,trace,dossier,fixture_label=fixture_label,
                          episode_view=episode_view,
                          historical_dossier=historical_dossier)


def export(report, destination):
    out=Path(destination)
    require(not out.exists(),"OUTPUT_ALREADY_EXISTS")
    out.mkdir(parents=True)
    write_json(out/"C_CAUSAL_DIAGNOSIS.json",report,exclusive=True)
    acc=report["causal_accounting"]
    lines=[
        "# Entrega C — esperas y bloqueos en escenario sintético",
        "",
        "**Alcance:** microfixture de software; no cola, capacidad ni "
        "ganancia medida en la cafetería real.",
        "**Política:** "+report["dispatch_policy"],
        "**Tiempo de espera por recursos:** "+
            str(acc["total_resource_wait_task_min"])+
            " task-min, NO minutos exclusivos ni P90.",
        "**Tareas pendientes de precedencia:** "+
            str(acc["precedence_pending_markers_not_timed"])+
            " marcadores; no sumados como espera.",
        "",
        "| Etapa | Tareas | Tareas que esperan | Espera recursos (task-min) |",
        "|---|---:|---:|---:|",
    ]
    for stage,x in acc["stage_breakdown"].items():
        lines.append("| "+stage+" | "+str(x["completed_tasks"])+" | "+
                     str(x["tasks_with_resource_wait"])+" | "+
                     str(x["resource_wait_task_min"])+" |")
    lines.extend([
        "",
        "Los intervalos admiten varios bloqueadores simultáneos. Los "
        "minutos de presencia de causas **no son aditivos**.",
        "",
        "## Hipótesis condicionales",
    ])
    for name,x in report["hypotheses"].items():
        lines.extend(["", "### "+name, ""])
        if name=="representation_artifact":
            lines.append("Comparación de representabilidad A/B, no espera "
                         "real inferida. "+x["status"])
        else:
            lines.append("**"+x["status"]+"** — "+x["signal"])
            lines.append("Resultado del fixture, no causalidad en campo. "
                         "Debilita: "+x["weakens"])
    lines.extend([
        "",
        "## Restricciones",
        "",
        "No se ejecutaron políticas D, inferencias, OMC ni nueva extracción "
        "de video. El P90 procede del motor, no de sumas de esperas. "
        "Se requiere un contraste de política con recursos idénticos para "
        "atribuir un efecto; esta entrega sólo diagnostica el modelo.",
    ])
    (out/"C_CAUSAL_DIAGNOSIS.md").write_text(
        "\n".join(lines)+"\n",encoding="utf-8")


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--dossier",required=True)
    p.add_argument("--toy-input",required=True)
    p.add_argument("--episode-view")
    p.add_argument("--historical-dossier")
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    toy=read_json(args.toy_input)
    require(toy.get("schema")==FIXTURE_SCHEMA and
            toy.get("scope")=="SOFTWARE_TOY_ONLY" and
            type(toy.get("positions")) is list and
            type(toy.get("lines")) is list,
            "TOY_FIXTURE_CONTRACT")
    require(bool(args.episode_view)==bool(args.historical_dossier),
            "INCOMPLETE_EPISODE_PAIR")
    report=diagnose(
        toy["positions"],toy["lines"],read_json(args.dossier),
        toy["horizon_min"],fixture_label="SOFTWARE_TOY_P45_FIXED",
        episode_view=read_json(args.episode_view) if
            args.episode_view else None,
        historical_dossier=read_json(args.historical_dossier) if
            args.historical_dossier else None)
    export(report,args.out)
    print("P45_C_DIAGNOSTIC",report["causal_accounting"][
        "blocked_intervals"],"SCIENCE_RUNS",0)


if __name__=="__main__":
    main()
