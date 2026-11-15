"""Two actionable physical mechanisms after S5: manual work vs espresso group.

Same verified CONSTRUCTION paid orders, recipes, equipment and staff except
one explicitly changed parameter per candidate. Outcomes belong exclusively
to the specialist reference, NOT to original D/M/B native engines.
"""
from __future__ import annotations

import copy

from .common import ArenaError, digest
from . import coffee_v2_reference as reference
from . import coffee_v2_p11 as p11
from . import coffee_v2_reference_inputs as views

SCHEMA="arena.coffee.v2.next-physical-actions/1"
MECHANISMS=("MANUAL_PREPARATION_TO_DECLARED_LOWER_BOUND",
            "ONE_ADDITIONAL_ESPRESSO_GROUP")
LOADS=("LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75")


def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_NEXT_ACTION_"+code)


def _candidate(dossier, mechanism):
    reference.config_gate(dossier)
    need(dossier["policy"]=="B0","BASELINE_MUST_BE_B0")
    alternate=copy.deepcopy(dossier)
    if mechanism == MECHANISMS[0]:
        item=alternate["durations"]["manual_setup_min"]
        need(item["bounds"][0] < item["value"],
             "LOWER_MANUAL_TIME_NOT_DECLARED_POSSIBLE")
        item["value"]=item["bounds"][0]
        before=copy.deepcopy(alternate)
        before["durations"]["manual_setup_min"]=dossier[
            "durations"]["manual_setup_min"]
        need(before==dossier,"MANUAL_VARIANT_CHANGED_OTHER_RESOURCES")
    elif mechanism == MECHANISMS[1]:
        item=alternate["resources"]["espresso_group"]
        need(item["units"] < 8,"ESPRESSO_GROUP_CAPACITY_LIMIT")
        item["units"]+=1
        before=copy.deepcopy(alternate)
        before["resources"]["espresso_group"]=dossier[
            "resources"]["espresso_group"]
        need(before==dossier,"MACHINE_VARIANT_CHANGED_OTHER_RESOURCES")
    else:
        need(False,"UNKNOWN_MECHANISM")
    reference.config_gate(alternate)
    return alternate


def compare(view_dir,dossier,*,selection=None):
    reference.config_gate(dossier)
    need(dossier["policy"]=="B0","REFERENCE_B0_REQUIRED")
    selected=selection or p11._verified_load_choices(view_dir)
    need(type(selected) is dict and
         type(selected.get("selected")) is list and
         len(selected["selected"])==2,
         "INPUT_SELECTION_NOT_TWO_CONSTRUCTION_DAYS")
    scenarios=[]
    baseline_rows=[]
    for row in selected["selected"]:
        need(row["load_label"] in LOADS,
             "LOAD_LABEL_NOT_PREDECLARED")
        safe=views.select_case_day(
            view_dir,row["case_id"],row["day"])
        need(safe["partition"]=="CONSTRUCTION",
             "NEVER_USE_NONCONSTRUCTION")
        b0=reference.simulate(safe["positions"],safe["items"],
                              dossier,safe["horizon"])
        baseline_rows.append({
            "load_label":row["load_label"],
            "paid_orders":b0["synthetic_paid_orders"],
            "B0_peak_handoffs":b0["modeled_handoffs_during_halfopen_peak"],
            "B0_p90_full_drain_min":b0[
                "modeled_paid_to_handoff_p90_full_drain_min"],
        })
        for mechanism in MECHANISMS:
            candidate=_candidate(dossier,mechanism)
            alternative=reference.simulate(
                safe["positions"],safe["items"],candidate,safe["horizon"])
            need(b0["synthetic_paid_orders"]==
                 alternative["synthetic_paid_orders"] and
                 b0["synthetic_beverage_units"]==
                 alternative["synthetic_beverage_units"] and
                 b0["synthetic_paid_orders"]==
                 b0["modeled_handoffs_during_halfopen_peak"]+
                 b0["modeled_orders_open_at_peak_cut"] and
                 alternative["synthetic_paid_orders"]==
                 alternative["modeled_handoffs_during_halfopen_peak"]+
                 alternative["modeled_orders_open_at_peak_cut"],
                 "MASS_OR_INPUT_CHANGED")
            delta=(alternative["modeled_handoffs_during_halfopen_peak"]-
                   b0["modeled_handoffs_during_halfopen_peak"])
            p90=(alternative["modeled_paid_to_handoff_p90_full_drain_min"]-
                 b0["modeled_paid_to_handoff_p90_full_drain_min"])
            scenarios.append({
                "load_label":row["load_label"],
                "mechanism":mechanism,
                "paid_orders_same_both_cases":b0["synthetic_paid_orders"],
                "assumed_change":(
                    "manual_setup_min: "+str(dossier[
                        "durations"]["manual_setup_min"]["value"])+" -> "+
                    str(candidate["durations"]["manual_setup_min"]["value"])
                    if mechanism==MECHANISMS[0] else
                    "espresso_group_units: "+
                    str(dossier["resources"]["espresso_group"]["units"])+" -> "+
                    str(candidate["resources"]["espresso_group"]["units"])
                ),
                "B0_peak_handoffs":b0["modeled_handoffs_during_halfopen_peak"],
                "intervention_peak_handoffs":
                    alternative["modeled_handoffs_during_halfopen_peak"],
                "delta_peak_handoffs_not_new_sales":delta,
                "B0_p90_min":round(
                    b0["modeled_paid_to_handoff_p90_full_drain_min"],10),
                "intervention_p90_min":round(
                    alternative["modeled_paid_to_handoff_p90_full_drain_min"],10),
                "delta_p90_min":round(p90,10),
                "physical_reference_only_not_original_DM_B":True,
            })
    need(len(scenarios)==4 and
         len(set((x["load_label"],x["mechanism"]) for x in scenarios))==4
         and {x["load_label"] for x in scenarios}==set(LOADS),
         "FIXED_FOUR_COMPARISONS_REQUIRED")
    evaluations={}
    for mechanism in MECHANISMS:
        rows=[x for x in scenarios if x["mechanism"]==mechanism]
        gains=sum(x["delta_peak_handoffs_not_new_sales"]>0 for x in rows)
        losses=sum(x["delta_peak_handoffs_not_new_sales"]<0 for x in rows)
        p90_gains=sum(x["delta_p90_min"]<0 for x in rows)
        if gains and not losses:
            status="CONDITIONAL_PEAK_GAIN_WORTH_COST_MEASUREMENT"
        elif losses:
            status="MIXED_OR_HARMFUL_IN_TESTED_LOADS"
        elif p90_gains:
            status="P90_ONLY_POSSIBLE_WITHOUT_PEAK_COUNT_GAIN"
        else:
            status="NO_SERVICE_GAIN_IN_TESTED_LOADS"
        evaluations[mechanism]={
            "status":status,
            "strict_peak_gain_contexts":gains,
            "strict_peak_loss_contexts":losses,
            "p90_improved_contexts":p90_gains,
            "changed_parameter_not_calibrated":True,
            "actual_capex_training_cost_and_margin_unknown":True,
        }
    promising=[name for name in MECHANISMS if
               evaluations[name]["status"]==
               "CONDITIONAL_PEAK_GAIN_WORTH_COST_MEASUREMENT"]
    return {
        "schema":SCHEMA,
        "status":"TWO_MECHANISMS_COMPARED_WITH_FIXED_B0",
        "dossier_sha256":digest(dossier),
        "selection_method":p11.SELECTION,
        "baseline":baseline_rows,
        "rows":scenarios,
        "candidate_assessments":evaluations,
        "priority_to_measure":promising,
        "business_disposition":(
            "MEASURE_COST_AND_FEASIBILITY_OF_PROMISING_MECHANISM"
            if promising else
            "NO_TESTED_PEAK_GAIN_MEASURE_BOTTLENECK_BEFORE_INVESTING"),
        "real_profit_or_new_sales_inferred":False,
        "limitations":[
            "Manual time is the DECLARED lower bound, not an empirically validated productivity improvement.",
            "Adding a machine assumes physical space, power and required barista work remain feasible.",
            "Only two preselected construction demand profiles, no real-world optimization.",
            "One extra handoff in peak does not establish another paid order.",
            "These are specialist reference comparisons, not independently generated D/M/B counterfactual models.",
        ],
    }
