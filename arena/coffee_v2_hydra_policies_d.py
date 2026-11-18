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
                                           dispatch_authorized=False):
    """Read only P39/P11 verified construction views, then exactly eight arms.

    Called ONLY by an explicitly authorized main-line execution. Never fetch
    private R2, open truth, create a corpus or run from an ordinary PR CI.
    """
    require(dispatch_authorized is True,
            "Q25_Q75_REQUIRES_EXPLICIT_EXPERIMENTAL_AUTHORIZATION")
    selection=p11._verified_load_choices(view_dir)
    require([x["load_label"] for x in selection["selected"]]==
            list(ALLOWED_CONSTRUCTION),"EXACT_Q25_Q75_SELECTION")
    compared=[]
    for index,chosen in enumerate(selection["selected"]):
        case=inputs.select_case_day(
            view_dir,chosen["case_id"],chosen["day"])
        require(case["partition"]=="CONSTRUCTION",
                "NO_DEVELOPMENT_OR_EVALUATION")
        report=compare(
            case["positions"],case["items"],dossier,case["horizon"],
            source_label=("CONSTRUCTION_SYNTHETIC_Q25" if index==0 else
                          "CONSTRUCTION_SYNTHETIC_Q75"),
            load_label=chosen["load_label"])
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
        "results":compared,
        "not_a_new_evidence_collection":True,
    }


ORDER_FIELDS=("paid_case_label","paid_time_min","beverages","policy",
              "baseline_handoff_min","policy_handoff_min",
              "handoff_delta_min_positive_is_later",
              "baseline_paid_to_handoff_min",
              "policy_paid_to_handoff_min",
              "outcome","changed_stage_count")


def export(report,output_dir):
    target=Path(output_dir)
    require(not target.exists(),"OUTPUT_ALREADY_EXISTS")
    require(report["schema"]==SCHEMA,"WRONG_REPORT_FOR_EXPORT")
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
        "**Fuente:** "+report["load_label"]+" (sintética de construcción, "
        "nunca observación de pedidos reales).",
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
            "**Trabajo reasignado entre B01/B02:** ver JSON y CSV. "
                "Los tiempos de ocupación no representan contratación.",
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


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--toy-input",required=True)
    parser.add_argument("--dossier",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args(argv)
    fixture=read_json(args.toy_input)
    require(fixture.get("schema")==c.FIXTURE_SCHEMA and
            fixture.get("scope")=="SOFTWARE_TOY_ONLY",
            "CLI_ONLY_PREEXISTING_SOFTWARE_TOY")
    report=compare(
        fixture["positions"],fixture["lines"],
        read_json(args.dossier),fixture["horizon_min"])
    export(report,args.out)
    print("P46_D_SOFTWARE_FIXTURE",len(report["policies"]),
          "NEW_SCIENTIFIC_RUNS",0)


if __name__=="__main__":
    main()
