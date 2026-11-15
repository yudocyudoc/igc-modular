"""P08: compare two *existing* authentic GitHub artifacts, no new solver.

A native M continuous order-queue proxy and a specialist discrete-event
reference are deliberately not numerically interchangeable. A small ATMS
justification graph records what evidence would be needed to promote the
proxy to a real-world action; it does not invent that missing evidence.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import argparse
import json

from .common import ArenaError, digest, read_json, write_json
from . import decision_atms as atms
from . import coffee_m_p08 as m
from . import coffee_next_action as reference

SCHEMA="arena.coffee.p08.cross-method-decision/1"
MAP={
    "MANUAL_PREPARATION_TO_DECLARED_LOWER_BOUND":"PREP_CAPACITY_X2",
    "ONE_ADDITIONAL_ESPRESSO_GROUP":"ESPRESSO_CAPACITY_X2",
}
MISSING_PHYSICAL_EVIDENCE=(
    "SAME_POS_TEMPORAL_INPUT",
    "SAME_BEVERAGE_AND_ORDER_UNIT",
    "MEASURED_BARISTA_MACHINE_RESOURCE_COUPLING",
    "MEASURED_REAL_TASK_DURATIONS",
)


def need(ok,reason):
    if not ok:
        raise ArenaError("COFFEE_P08_CROSS_"+reason)


def compare(reference_result,native_result,*,recorded_at):
    need(type(reference_result) is dict and
         reference_result.get("schema")==reference.SCHEMA and
         reference_result.get("status")=="TWO_MECHANISMS_COMPARED_WITH_FIXED_B0" and
         reference_result.get("real_profit_or_new_sales_inferred") is False,
         "REFERENCE_SOURCE_MISMATCH")
    need(type(native_result) is dict and
         native_result.get("schema")==m.SCHEMA and
         native_result.get("status")=="NATIVE_M_P08_SIX_SIMS_SUCCEEDED" and
         native_result.get("new_omc_attempted")==6 and
         native_result.get("failed_models")==[] and
         native_result.get("causal_real_business_evidence") is False,
         "M_SOURCE_NOT_SIX_AUTHENTIC_SIMULATIONS")
    old=reference_result.get("rows")
    new=native_result.get("pairwise_comparisons")
    need(type(old) is list and len(old)==4 and
         type(new) is list and len(new)==4,"EXACTLY_TWO_ACTION_PAIRS_EACH")
    indexed_ref={}
    for row in old:
        need(row.get("mechanism") in MAP and
             row.get("load_label") in m.INPUT_LABELS,
             "UNKNOWN_REFERENCE_ACTION")
        key=(row["load_label"],row["mechanism"])
        need(key not in indexed_ref,"DUPLICATE_REFERENCE_ACTION")
        need(type(row.get("B0_peak_handoffs")) is int and
             type(row.get("intervention_peak_handoffs")) is int and
             row.get("delta_peak_handoffs_not_new_sales") ==
             row["intervention_peak_handoffs"]-row["B0_peak_handoffs"],
             "REFERENCE_DELTA_INVALID")
        indexed_ref[key]=row
    indexed_m={}
    for row in new:
        need(row.get("variant") in MAP.values() and
             row.get("load_label") in m.INPUT_LABELS and
             row.get("correspondence_to_reference") ==
             "NO_EXACT_MAPPING_OF_RECIPES_OR_P90",
             "M_PROJECTION_NOT_DECLARED")
        key=(row["load_label"],row["variant"])
        need(key not in indexed_m,"DUPLICATE_M_ACTION")
        delta=row["delta_continuous_handoffs_at_cut"]
        need(type(delta) in (float,int) and
             abs((row["native_M_policy_continuous_handoffs_at_cut"]-
                  row["native_M_B0_continuous_handoffs_at_cut"])-delta)<1e-4,
             "M_DELTA_INVALID")
        indexed_m[key]=row
    comparisons=[]
    for label in m.INPUT_LABELS:
        for mechanism,variant in MAP.items():
            r=indexed_ref.get((label,mechanism))
            n=indexed_m.get((label,variant))
            need(r is not None and n is not None,"MISSING_CONTEXT_OR_MECHANISM")
            need(r["paid_orders_same_both_cases"] ==
                 n["B0_paid_orders_from_existing_artifact"],
                 "PAID_COUNT_SOURCE_CHANGED")
            # Directional sign only. The reference counts discrete handoffs,
            # M counts continuous stocks and uses a rectangular input pulse.
            dr=r["delta_peak_handoffs_not_new_sales"]
            dm=n["delta_continuous_handoffs_at_cut"]
            direction=lambda x:"UP" if x>1e-6 else "DOWN" if x< -1e-6 else "TIE"
            comparisons.append({
                "load_label":label,
                "physical_reference_intervention":mechanism,
                "M_aggregate_proxy":variant,
                "reference_B0_discrete_peak_handoffs":r["B0_peak_handoffs"],
                "reference_delta_discrete_peak_handoffs":dr,
                "M_B0_continuous_delivered_at_cut":
                    n["native_M_B0_continuous_handoffs_at_cut"],
                "M_delta_continuous_delivered_at_cut":dm,
                "reference_direction":direction(dr),
                "M_direction":direction(dm),
                "direction_same":direction(dr)==direction(dm),
                "numeric_values_commensurable":False,
            })
    # Versioned ATMS evidence is an explanation/decision boundary, not
    # causal identification or a claim that the original M revised itself.
    src=digest({"reference":reference_result,
                "native_m":native_result})
    base=atms.stamp(recorded_at)
    def tick(i):
        return (base+timedelta(microseconds=i)).isoformat(
            timespec="microseconds").replace("+00:00","Z")
    journal=atms.Journal()
    journal.append(atms.event(
        "assumption","A_REF",tick(0),src,
        node="REFERENCE_CONSTRUCTION_SIMULATED",status="SIMULATED"))
    journal.append(atms.event(
        "assumption","A_M",tick(1),src,
        node="M_VERSIONED_NATIVE_CSV_AUTHENTICATED",status="SIMULATED"))
    journal.append(atms.event(
        "justification","J_SCREEN",tick(2),src,
        conclusion="CONDITIONAL_METHOD_COMPARISON_AVAILABLE",
        premises=["REFERENCE_CONSTRUCTION_SIMULATED",
                  "M_VERSIONED_NATIVE_CSV_AUTHENTICATED"]))
    journal.append(atms.event(
        "justification","J_REAL",tick(3),src,
        conclusion="M_VALIDATED_FOR_REAL_COFFEE_INTERVENTION",
        premises=["CONDITIONAL_METHOD_COMPARISON_AVAILABLE",
                  *MISSING_PHYSICAL_EVIDENCE]))
    snapshot=journal.snapshot(as_known_at=tick(4),valid_at=tick(4))
    need(bool(snapshot["labels"].get("CONDITIONAL_METHOD_COMPARISON_AVAILABLE"))
         and not snapshot["labels"].get(
             "M_VALIDATED_FOR_REAL_COFFEE_INTERVENTION"),
         "ATMS_MAY_NOT_PROMOTE_AGGREGATE_PROXY_TO_PHYSICAL_FACT")
    priority=reference_result.get("priority_to_measure",[])
    need(type(priority) is list and set(priority).issubset(MAP),
         "UNKNOWN_REFERENCE_PRIORITY")
    decision={
        "schema":SCHEMA,
        "status":"P08_COMPARISON_COMPLETE_NO_CROSS_METHOD_PHYSICAL_VALIDATION",
        "comparison_rows":comparisons,
        "reference_priority_to_measure":priority,
        "suggested_next_measurement":(
            "TIME_ACTUAL_PREPARATION_AND_MACHINE_PROCESS_WHILE_TRACKING_PEAK_LOAD"
            if priority else "MEASURE_WHICH_REAL_RESOURCE_IS_LIMITING_PEAK_HANDOFFS"),
        "atms":{
            "journal":journal.events,
            "snapshot":snapshot,
            "conditioned_claim":journal.explain(
                "CONDITIONAL_METHOD_COMPARISON_AVAILABLE",
                as_known_at=tick(4),valid_at=tick(4)),
            "unsupported_real_claim":journal.explain(
                "M_VALIDATED_FOR_REAL_COFFEE_INTERVENTION",
                as_known_at=tick(4),valid_at=tick(4)),
            "missing_physical_evidence":list(MISSING_PHYSICAL_EVIDENCE),
        },
        "referenced_github_runs":{
            "specialist":43697007653,"M_native":43702148041},
        "M_original_model_modified":False,
        "D_B_new_OMC_or_revision_attempts":0,
        "new_OMC_or_provider_calls":0,
        "not_an_ROI_or_real_business_recommendation":True,
    }
    return decision


def export(result,out):
    dest=Path(out)
    need(not dest.exists(),"NO_OVERWRITE")
    dest.mkdir(parents=True,exist_ok=False)
    write_json(dest/"cross-method.json",result,exclusive=True)
    lines=[
        "# P08 — two real model methods compared, not conflated",
        "",
        "The specialist uses discrete paid-order events and recipes; M uses",
        "an hourly rectangular pulse and continuous order queue stocks.",
        "**Identical paid totals do NOT imply identical temporal or physical inputs.**",
        "",
        "| Load | Physical candidate | Reference B0 peak | Ref delta (orders) | M B0 (continuous) | M proxy delta | Same direction? |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for c in result["comparison_rows"]:
        lines.append("| "+c["load_label"]+" | "+
                     c["physical_reference_intervention"]+" | "+
                     str(c["reference_B0_discrete_peak_handoffs"])+" | "+
                     str(c["reference_delta_discrete_peak_handoffs"])+" | "+
                     str(c["M_B0_continuous_delivered_at_cut"])+" | "+
                     str(c["M_delta_continuous_delivered_at_cut"])+" | "+
                     ("yes" if c["direction_same"] else "no")+" |")
    lines += ["", "## ATMS disposition",
              "Conditional comparison: SUPPORTED.",
              "Exact real-coffee capacity recommendation: UNSUPPORTED.",
              "Missing: "+", ".join(result["atms"]["missing_physical_evidence"])+".",
              "The original M has NOT calibrated or revised itself.",
              "Physical reference's actions to prioritize measuring: "+
              (", ".join(result["reference_priority_to_measure"]) or "none")+".",
              "Proposed measurement: "+result["suggested_next_measurement"]+".",
              "No OMC or provider calls in this comparison replay."]
    (dest/"DECISION.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--reference",required=True)
    p.add_argument("--native",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    export(compare(read_json(args.reference),read_json(args.native),
                   recorded_at=atms.utc_now()),args.out)


if __name__=="__main__":
    main()
