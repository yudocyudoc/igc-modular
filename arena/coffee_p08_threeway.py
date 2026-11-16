"""P08 three-method comparison: independent D and M proxies against reference.

This does NOT calibrate D or M. It compares directional outputs under the
same paid totals, but different temporal/physical representations, and
asks ATMS which field measurement best discriminates their disagreement.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

from .common import ArenaError, digest, read_json, write_json
from . import coffee_d_p08 as d
from . import coffee_m_p08 as m
from . import coffee_p08_cross as prior
from . import decision_atms as atms

SCHEMA = "arena.coffee.p08.three-method-disposition/1"
MISSING = [
    "IDENTICAL_INTRA_PEAK_POS_TIMING",
    "MEASURED_PREPARATION_AND_ESPRESSO_STAGE_THROUGHPUT",
    "MEASURED_BARISTA_AND_MACHINE_OVERLAP",
    "VERIFIED_MAPPING_OF_AGGREGATE_ORDER_TO_PHYSICAL_BEVERAGE",
    "OBSERVED_REAL_DELIVERY_TIMES_AND_ACTION_COSTS",
]


def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_P08_THREEWAY_"+code)


def sign(value):
    need(type(value) in (int,float) and abs(value)<100000,
         "DELTA_INVALID")
    return "UP" if value>1e-5 else ("DOWN" if value< -1e-5 else "TIE")


def compare(reference_result, m_result, d_result, *, recorded_at):
    # The existing cross adapter validates M/ref paid totals and four pairs;
    # do not introduce a less strict parallel validation method.
    two=prior.compare(reference_result,m_result,recorded_at=recorded_at)
    need(type(d_result) is dict and d_result.get("schema")==d.SCHEMA and
         d_result.get("status")=="D_SIX_NATIVE_OMC_PASS_NOT_REAL_CAUSAL_VALIDATION"
         and d_result.get("omc_attempts_reserved")==6 and
         d_result.get("failures")==[] and
         d_result.get("physical_model_identified") is False and
         d_result.get("stage_mapping_validated") is False,
         "D_NATIVE_RESULT_NOT_COMPLETE_OR_OVERCLAIMED")
    drows=d_result.get("pairwise_comparisons")
    need(type(drows) is list and len(drows)==4,
         "D_FOUR_METHOD_PAIRS_REQUIRED")
    index={}
    for row in drows:
        key=(row.get("load_label"),row.get("variant"))
        need(key[0] in d.LOADS and key[1] in d.VARIANTS[1:] and
             key not in index and
             row.get("representation")==
             "D_THREE_STOCKS_GENERIC_STAGE_CAPACITY_PROXY" and
             type(row.get("B0_paid_orders_from_source")) is int,
             "D_SOURCE_PAIR_OR_REPRESENTATION_INVALID")
        old=row.get("native_D_B0_continuous_at_cut")
        new=row.get("native_D_policy_continuous_at_cut")
        delta=row.get("delta_continuous_at_cut")
        need(all(type(v) in (int,float) for v in (old,new,delta)) and
             abs((new-old)-delta)<1e-4,"D_DELTA_NOT_FROM_NATIVE")
        index[key]=row
    joint=[]
    for row in two["comparison_rows"]:
        key=(row["load_label"],row["M_aggregate_proxy"])
        item=index.get(key)
        need(item is not None and
             item["B0_paid_orders_from_source"]==
             next(x["B0_paid_orders_from_existing_artifact"]
                  for x in m_result["pairwise_comparisons"]
                  if (x["load_label"],x["variant"])==key),
             "D_AND_M_DO_NOT_SHARE_PAID_COUNT")
        rd=row["reference_direction"]
        md=row["M_direction"]
        dd=sign(item["delta_continuous_at_cut"])
        joint.append({
            "load_label":key[0],
            "physical_action":row["physical_reference_intervention"],
            "M_proxy":key[1],
            "D_proxy":key[1],
            "reference_discrete_delta":row[
                "reference_delta_discrete_peak_handoffs"],
            "M_continuous_delta":row[
                "M_delta_continuous_delivered_at_cut"],
            "D_continuous_delta":item["delta_continuous_at_cut"],
            "reference_direction":rd,"M_direction":md,"D_direction":dd,
            "all_three_same_direction":rd==md==dd,
            "reference_vs_M":rd==md,
            "reference_vs_D":rd==dd,
            "M_vs_D":md==dd,
            "same_paid_total_different_model_representations":True,
            "quantitative_deltas_incommensurable":True,
        })
    need(len(joint)==4 and
         len(set((r["load_label"],r["physical_action"]) for r in joint))==4,
         "INCOMPLETE_FIXED_COMPARISON")
    disagreements=[r for r in joint if not r["all_three_same_direction"]]
    concordant=[r for r in joint if r["all_three_same_direction"]]
    disputed_mechanisms=sorted(set(r["physical_action"] for r in disagreements))
    # The selection rule is defined *before* observing this new D outcome.
    # Disagreement -> measure stage-specific occupancy and queue times; no
    # disagreement -> measure costs/physical transfer instead. Neither
    # outcome automatically approves machine purchase.
    next_measurement={
        "priority":"FIELD_DISCRIMINATION_OF_MODEL_DISAGREEMENT" if disagreements
            else "FIELD_VALIDATION_OF_CONCORDANT_PROXY",
        "test":"SIMULTANEOUS_TIMESTAMPED_PREPARATION_AND_ESPRESSO_OCCUPANCY",
        "capture":[
            "paid_order_timestamp_and_beverage_mix",
            "manual_preparation_start_and_finish",
            "espresso_cycle_start_and_finish_per_equipment_group",
            "barista_occupied_or_waiting_at_each_stage",
            "ready_and_collected_timestamp",
            "space_power_staff_coverage_and_cost_of_any_proposed_change",
        ],
        "prioritize_stage_mechanisms":disputed_mechanisms if disagreements else
            sorted(prior.MAP),
        "target_demand_profiles":[
            "LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75"],
        "reason":"Resolve whether nonmatching model directions are due to "
                 "the shared paid-order pulse approximation, stage capacities, "
                 "or real barista/machine coupling",
        "not_authorization_to_purchase_or_reassign":True,
    }
    source=digest({"D":d_result,"M":m_result,"reference":reference_result})
    base=atms.stamp(recorded_at)
    def t(i):
        return (base+timedelta(microseconds=i)).isoformat(
            timespec="microseconds").replace("+00:00","Z")
    journal=atms.Journal()
    journal.append(atms.event(
        "assumption","A_PLANNED",t(0),source,
        node="P08_COMPLETE_THREEWAY_PLAN",status="ASSUMED"))
    pre=journal.snapshot(as_known_at=t(0),valid_at=t(0))
    journal.append(atms.event(
        "assumption","A_REFERENCE",t(1),source,
        node="REFERENCE_SIMULATED_COMPLETED",status="SIMULATED"))
    journal.append(atms.event(
        "assumption","A_M_NATIVE",t(2),source,
        node="M_NATIVE_SIX_SIMULATIONS",status="SIMULATED"))
    journal.append(atms.event(
        "assumption","A_D_NATIVE",t(3),source,
        node="D_NATIVE_SIX_SIMULATIONS",status="SIMULATED"))
    if disagreements:
        journal.append(atms.event(
            "assumption","A_DISAGREEMENT",t(4),source,
            node="SOME_TESTED_METHODS_DISAGREE",status="SIMULATED"))
        evidence=t(4)
    else:
        journal.append(atms.event(
            "assumption","A_CONCORDANCE",t(4),source,
            node="ALL_TESTED_DIRECTIONS_AGREE",status="SIMULATED"))
        evidence=t(4)
    journal.append(atms.event(
        "justification","J_COMPARE",t(5),source,
        conclusion="CONDITIONAL_THREE_METHOD_COMPARISON",
        premises=["P08_COMPLETE_THREEWAY_PLAN",
                  "REFERENCE_SIMULATED_COMPLETED",
                  "M_NATIVE_SIX_SIMULATIONS",
                  "D_NATIVE_SIX_SIMULATIONS"]))
    journal.append(atms.event(
        "justification","J_DISCRIMINATE",t(6),source,
        conclusion="PRIORITIZE_DISCRIMINATING_MEASUREMENT",
        premises=["CONDITIONAL_THREE_METHOD_COMPARISON",
                  "SOME_TESTED_METHODS_DISAGREE"]))
    journal.append(atms.event(
        "justification","J_PHYSICAL",t(7),source,
        conclusion="REAL_COFFEE_MECHANISM_AND_ROI_ESTABLISHED",
        premises=["CONDITIONAL_THREE_METHOD_COMPARISON",*MISSING]))
    post=journal.snapshot(as_known_at=t(7),valid_at=t(7))
    need(bool(post["labels"].get("CONDITIONAL_THREE_METHOD_COMPARISON")) and
         not post["labels"].get("REAL_COFFEE_MECHANISM_AND_ROI_ESTABLISHED") and
         journal.snapshot(as_known_at=t(0),valid_at=t(0))==pre,
         "ATMS_MAY_NOT_INVENT_REAL_OR_RETROACTIVE_EVIDENCE")
    report={
        "schema":SCHEMA,
        "status":"THREE_METHODS_COMPARED_WITH_EXPLICIT_REPRESENTATION_GAP",
        "rows":joint,
        "same_direction_contexts":len(concordant),
        "different_direction_contexts":len(disagreements),
        "disputed_stage_mechanisms":disputed_mechanisms,
        "selected_next_experiment":next_measurement,
        "atms":{
            "journal":journal.events,
            "predecision_snapshot":pre,
            "evidence_time":evidence,
            "disposition_snapshot":post,
            "supported_comparison":bool(post["labels"].get(
                "CONDITIONAL_THREE_METHOD_COMPARISON")),
            "disputed_stage_measurement_supported":bool(post["labels"].get(
                "PRIORITIZE_DISCRIMINATING_MEASUREMENT")),
            "real_business_claim_supported":False,
            "missing_real_physical_evidence":MISSING,
            "first_cut":t(0),"final_cut":t(7),
        },
        "source_github_runs":{
            "reference":43697007653,"M":43702148041,
            "D":"THIS_GITHUB_RUN",
        },
        "method_independence_limited_by_shared_synthetic_paid_counts":True,
        "D_and_M_share_rectangular_pulse_but_not_equations":True,
        "reference_has_distinct_discrete_order_events":True,
        "D_and_M_not_independently_calibrated_on_real_pickups":True,
        "not_business_investment_or_profit":True,
    }
    return report


def export(result,out):
    out=Path(out)
    need(not out.exists(),"RESULT_OVERWRITE")
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/"THREEWAY_ATMS.json",result,exclusive=True)
    lines=[
        "# PR37 — D / M / reference: which bottleneck should we measure?",
        "",
        "**No calibration and no real commercial or causal validation.**",
        "The reference uses discrete events/recipes; D and M use hourly",
        "rectangular paid-order pulses and continuous stocks.",
        "",
        "| Synthetic load | Proposed lever | Reference Δ discrete | M Δ continuous | D Δ continuous | All directions same? |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in result["rows"]:
        lines.append(
            f"| {row['load_label']} | {row['physical_action']} | "
            f"{row['reference_discrete_delta']:+d} | "
            f"{row['M_continuous_delta']:+.6f} | "
            f"{row['D_continuous_delta']:+.6f} | "
            f"{'yes' if row['all_three_same_direction'] else 'NO'} |")
    x=result["selected_next_experiment"]
    lines.extend([
        "",
        "## Decision driven by the disagreement",
        "",
        "Concordant tested directions: "+
            str(result["same_direction_contexts"])+"/4.",
        "Disputed tested directions: "+
            str(result["different_direction_contexts"])+"/4.",
        "Selected measurement: "+x["test"]+".",
        "Prioritize: "+(", ".join(x["prioritize_stage_mechanisms"]) or "none")+".",
        "Record payment/recipe and stage starts/finishes together; identify",
        "barista-machine overlap before touching equipment or staffing.",
        "",
        "ATMS supported a conditional comparison: "+
            str(result["atms"]["supported_comparison"])+".",
        "ATMS supports real ROI or physical equivalence: False.",
        "No modification of original D/M/B, no new world, no R2 or provider.",
    ])
    (out/"DECISION.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--reference",required=True)
    p.add_argument("--M",required=True)
    p.add_argument("--D",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    export(compare(read_json(args.reference),read_json(args.M),
                   read_json(args.D),recorded_at=atms.utc_now()),args.out)


if __name__=="__main__":
    main()
