"""Arena V2.1 P11: first *conditional* B0/S5 consequence comparison.

Two input-only construction case/days, same paid POS/items for both policies,
13 declared one-at-a-time/corner/resource variants, a transparent illustrative
timing-value/cost grid. No truth, scenario labels, V1 holdout, G3, empirically
measured costs, native D/M/B, additional worlds, provider or OMC.

P11 does not imply S5 is physically available or commercially justified.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import sys

from .common import ArenaError, digest, write_json
from . import coffee_v2_reference as reference
from . import coffee_v2_reference_inputs as reader
from . import coffee_v2_producer_views as producer

SCHEMA = "arena.coffee-v2.p11-conditional-policy/1"
PROTOCOL = "arena.coffee-v2.p11-protocol/1"
SELECTION = "CONSTRUCTION_POS_LOAD_Q25_Q75_INPUT_ONLY/1"
VARIANTS = ("NOMINAL",) + tuple(
    f"{name}_{bound}" for name in reference.DURATIONS
    for bound in ("LOW", "HIGH")
) + ("ALL_DURATIONS_LOW", "ALL_DURATIONS_HIGH",
     "BARISTA_UNITS_PLUS_ONE_BOTH_ARMS",
     "ESPRESSO_GROUP_UNITS_PLUS_ONE_BOTH_ARMS")
LIMIT_PAIRS = 2 * len(VARIANTS)


def strict_preference_reversal(sign_counts):
    """A tie and one strict preference do not reverse B0 versus S5."""
    return (sign_counts.get("S5_IF_ASSUMPTIONS", 0) > 0 and
            sign_counts.get("B0_IF_ASSUMPTIONS", 0) > 0)


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_V2_P11_" + code)


def unsigned(x, label, maximum=1000000):
    need(type(x) in (float, int) and not isinstance(x, bool),
         "INVALID_NUMBER_TYPE_" + label)
    v = float(x)
    need(math.isfinite(v) and 0 <= v <= maximum,
         "INVALID_RANGE_" + label)
    return v


def protocol_gate(p):
    need(type(p) is dict and set(p) == {
        "schema", "scope", "selection", "policies",
        "sensitivity", "illustrative_economics", "rules"
    }, "PROTOCOL_FIELDS")
    need(p["schema"] == PROTOCOL and
         p["scope"] == "CONDITIONAL_SYNTHETIC_PAID_POS_ONLY_NOT_BUSINESS_VALIDATION"
         and p["selection"] == {
             "partition": "CONSTRUCTION",
             "method": SELECTION,
             "quantile_ranks": [0.25, 0.75],
             "exclude_zero_paid_days": True,
             "exclude_partial_or_V1_reserved_days": True,
             "choose_before_simulation": True,
         }, "SELECTION_NOT_PREDECLARED")
    need(p["policies"] == ["B0", reference.S5],
         "POLICY_PAIR_NOT_B0_S5")
    need(p["sensitivity"] == {
        "design": "ONE_AT_A_TIME_PLUS_JOINT_EXTREMES_AND_TWO_CAPACITY_CHECKS",
        "variant_ids": list(VARIANTS),
        "use_same_pos_and_items_for_both_policies": True,
        "no_truth_calibration": True,
    }, "SENSITIVITY_NOT_PREDECLARED")
    economics = p["illustrative_economics"]
    need(type(economics) is dict and set(economics) == {
        "incremental_support_opportunity_cost_mxn_per_peak",
        "assumed_value_mxn_per_additional_handoff_inside_peak",
        "interpretation",
    }, "ECONOMIC_FIELDS")
    need(economics["interpretation"] ==
         "ILLUSTRATIVE_TIMING_VALUE_NOT_SALES_PROFIT_OR_REAL_ROI",
         "ECONOMIC_CLAIM_EXCEEDS_EVIDENCE")
    for key in ("incremental_support_opportunity_cost_mxn_per_peak",
                "assumed_value_mxn_per_additional_handoff_inside_peak"):
        values = economics[key]
        need(type(values) is list and len(values) == 3 and
             all(type(x) in (int, float) and not isinstance(x, bool)
                 for x in values), "ECONOMIC_GRID_INVALID")
        parsed = [unsigned(x, key, 10000) for x in values]
        need(parsed == sorted(set(parsed)), "ECONOMIC_GRID_MUST_BE_UNIQUE_SORTED")
    need(p["rules"] == {
        "count_handoffs_only_before_exclusive_peak_end": True,
        "report_open_at_cut_and_full_drain_separately": True,
        "no_revenue_from_faster_service_without_explicit_value_assumption": True,
        "no_empirical_saturation_claim": True,
        "no_business_recommendation_or_G3": True,
        "no_evaluation_partition_access": True,
    }, "DECISION_GATES_NOT_PREDECLARED")
    return economics


def _verified_load_choices(view_dir):
    """Pick 25th and 75th ranked *paid input load* before any solver calls.

    A case/day with withheld V1 bins is absent, not treated as zero.
    Construction only; no use of development or evaluation outcomes.
    """
    path = Path(view_dir)
    need(path.is_dir() and not path.is_symlink(), "RELEASE_DIRECTORY_REQUIRED")
    manifest = json.loads((path/"producer-manifest.json").read_text("utf-8"))
    hashes = manifest.get("output_sha256")
    need(manifest.get("schema") == producer.SCHEMA and
         manifest.get("evaluation_scenario_rows_released") == 0 and
         type(hashes) is dict and
         set(hashes) ==
         set(producer.CSV_COLUMNS) |
         {"p12-split-plan.json", "producer-view-summary.json"},
         "VIEWS_NOT_ATTESTED")
    for name, claimed in hashes.items():
        need(type(claimed) is str and
             "sha256:"+reader.sha_file(path/name) == claimed,
             "SOURCE_MEMBER_CHANGED")
    index = reader.read_rows(path/"producer-case-index.csv",
                             producer.CSV_COLUMNS["producer-case-index.csv"])
    bins = reader.read_rows(path/"producer-paid-bins-5min.csv",
                            producer.CSV_COLUMNS["producer-paid-bins-5min.csv"])
    need(len(index) == 45, "SCENARIO_INDEX_CHANGED")
    construction = {r["case_id"] for r in index
                    if r["partition"] == "CONSTRUCTION"}
    need(len(construction) == 36 and
         sum(r["partition"] == "DEVELOPMENT" for r in index) == 9,
         "CONSTRUCTION_PARTITION_CHANGED")
    grouped = defaultdict(list)
    for row in bins:
        need(row["case_id"] in {r["case_id"] for r in index}
             and row["partition"] in ("CONSTRUCTION","DEVELOPMENT"),
             "UNEXPECTED_BIN_CASE")
        if row["case_id"] in construction:
            day = reader.integer(row["day_of_week"], "P11_DAY", 1, 7)
            grouped[(row["case_id"], day)].append(row)
    need(len(grouped) == 36*7, "CONSTRUCTION_DAY_COVERAGE_CHANGED")
    eligible, partial = [], 0
    for (cid, day), b in grouped.items():
        starts = [reader.integer(r["bin_start_min"], "P11_BIN", 0, 100)
                  for r in b]
        need(len(starts) == 21 and
             sorted(starts) == list(range(0, 105, 5)),
             "MISSING_OR_DUPLICATE_BIN")
        if any(r["coverage_status"] != "COMPLETE_SYNTHETIC_POS_WINDOW"
               for r in b):
            partial += 1
            continue
        pays = [reader.integer(r["synthetic_payments"], "P11_PAID", 0, 5000)
                for r in b]
        total = sum(pays)
        if total == 0:
            continue
        eligible.append((total, max(pays), cid, day))
    need(len(eligible) >= 4, "TOO_FEW_NONZERO_CONSTRUCTION_DAYS")
    eligible.sort()
    low = math.floor((len(eligible)-1)*.25)
    high = math.ceil((len(eligible)-1)*.75)
    need(low < high, "QUANTILE_SELECTION_NOT_DISTINCT")
    chosen = [eligible[low], eligible[high]]
    need(chosen[0][2:4] != chosen[1][2:4],
         "DUPLICATE_CASE_DAY")
    return {
        "selected": [
            {"load_label": lab, "case_id": cid, "day": day,
             "synthetic_paid_in_peak": total,
             "max_paid_per_five_min": peak,
             "partition": "CONSTRUCTION"}
            for lab, (total, peak, cid, day)
            in zip(("LOWER_PAID_INPUT_Q25", "HIGHER_PAID_INPUT_Q75"), chosen)
        ],
        "eligible_nonzero_construction_days": len(eligible),
        "excluded_partial_or_reserved_days": partial,
        "construction_day_count": 36*7,
        "selection_based_on": "SYNTHETIC_PAID_INPUT_NOT_SERVICE_OUTCOMES",
        "saturation_status": "NOT_CLASSIFIED_FROM_PAID_LOAD_ALONE",
        "input_load_contrast": (
            "DISTINCT_SELECTED_PAID_INPUT_LOAD"
            if chosen[0][:2] != chosen[1][:2] else
            "TIED_SELECTED_PAID_INPUT_NO_LOW_HIGH_DISTINCTION"
        ),
    }


def _variants(base):
    """All variants are predeclared; BOTH arms use identical new dossier."""
    reference.config_gate(base)
    need(base["policy"] == "B0" and
         base["resources"]["existing_support"]["units"] >= 1,
         "S5_NOT_REPRESENTABLE_WITH_THIS_DOSSIER")
    variants = [("NOMINAL", copy.deepcopy(base))]
    for name in reference.DURATIONS:
        for bound, index in (("LOW",0), ("HIGH",1)):
            scenario = copy.deepcopy(base)
            scenario["durations"][name]["value"] = scenario["durations"][name][
                "bounds"][index]
            variants.append((name+"_"+bound, scenario))
    for label, index in (("ALL_DURATIONS_LOW",0),
                         ("ALL_DURATIONS_HIGH",1)):
        scenario = copy.deepcopy(base)
        for item in scenario["durations"].values():
            item["value"] = item["bounds"][index]
        variants.append((label,scenario))
    for label, resource in (
        ("BARISTA_UNITS_PLUS_ONE_BOTH_ARMS","barista"),
        ("ESPRESSO_GROUP_UNITS_PLUS_ONE_BOTH_ARMS","espresso_group")
    ):
        scenario = copy.deepcopy(base)
        old = scenario["resources"][resource]["units"]
        need(old < 8, "RESOURCE_SENSITIVITY_NOT_REPRESENTABLE")
        scenario["resources"][resource]["units"] = old + 1
        variants.append((label,scenario))
    need([label for label, _ in variants] == list(VARIANTS),
         "VARIANT_SET_CHANGED")
    return variants


def compare(view_dir, dossier, protocol):
    economics = protocol_gate(protocol)
    selection = _verified_load_choices(view_dir)
    variation = _variants(dossier)
    comparisons, money_cells = [], []
    for chosen in selection["selected"]:
        safe = reader.select_case_day(
            view_dir, chosen["case_id"], chosen["day"])
        need(safe["partition"] == "CONSTRUCTION",
             "DEVELOPMENT_OR_EVALUATION_FORBIDDEN")
        for name, base in variation:
            intervention = copy.deepcopy(base)
            intervention["policy"] = reference.S5
            proof = reference.counterfactual_pair_gate(base, intervention)
            b0 = reference.simulate(safe["positions"], safe["items"],
                                    base, safe["horizon"])
            s5 = reference.simulate(safe["positions"], safe["items"],
                                    intervention, safe["horizon"])
            need(b0["synthetic_paid_orders"] == s5["synthetic_paid_orders"]
                 and b0["synthetic_beverage_units"] ==
                 s5["synthetic_beverage_units"] and
                 b0["synthetic_refunds_not_negative_handoffs"] ==
                 s5["synthetic_refunds_not_negative_handoffs"] and
                 b0["modeled_handoffs_during_halfopen_peak"] +
                 b0["modeled_orders_open_at_peak_cut"] ==
                 b0["synthetic_paid_orders"] and
                 s5["modeled_handoffs_during_halfopen_peak"] +
                 s5["modeled_orders_open_at_peak_cut"] ==
                 s5["synthetic_paid_orders"],
                 "COUNTERFACTUAL_MASS_OR_INPUT_MISMATCH")
            delta = (s5["modeled_handoffs_during_halfopen_peak"] -
                     b0["modeled_handoffs_during_halfopen_peak"])
            base_p90 = b0["modeled_paid_to_handoff_p90_full_drain_min"]
            s5_p90 = s5["modeled_paid_to_handoff_p90_full_drain_min"]
            need(base_p90 is not None and s5_p90 is not None,
                 "EMPTY_OBSERVABLE_CANNOT_SELECT")
            freed = (
                b0["resources"]["barista"]["busy_unit_minutes_full_drain"] -
                s5["resources"]["barista"]["busy_unit_minutes_full_drain"]
            )
            support = s5["resources"]["existing_support"][
                "busy_unit_minutes_full_drain"]
            need(abs(freed-support) < 1e-6,
                 "HANDOFF_TRANSFER_NOT_CONSERVED")
            item = {
                "load_label": chosen["load_label"],
                "case_id": chosen["case_id"], "day": chosen["day"],
                "partition": "CONSTRUCTION",
                "variant_id": name,
                "scenario_dossier_sha256": proof["scenario_dossier_sha256"],
                "synthetic_paid_orders": b0["synthetic_paid_orders"],
                "synthetic_beverage_units": b0["synthetic_beverage_units"],
                "B0_modeled_handoffs_in_peak":
                    b0["modeled_handoffs_during_halfopen_peak"],
                "S5_modeled_handoffs_in_peak":
                    s5["modeled_handoffs_during_halfopen_peak"],
                "delta_S5_minus_B0_modeled_handoffs_in_peak": delta,
                "B0_modeled_open_at_cut":
                    b0["modeled_orders_open_at_peak_cut"],
                "S5_modeled_open_at_cut":
                    s5["modeled_orders_open_at_peak_cut"],
                "B0_modeled_p90_paid_to_handoff_full_drain_min": base_p90,
                "S5_modeled_p90_paid_to_handoff_full_drain_min": s5_p90,
                "delta_S5_minus_B0_modeled_full_drain_p90_min":
                    round(s5_p90-base_p90, 10),
                "B0_modeled_barista_busy_unit_min":
                    b0["resources"]["barista"]["busy_unit_minutes_full_drain"],
                "S5_modeled_barista_busy_unit_min":
                    s5["resources"]["barista"]["busy_unit_minutes_full_drain"],
                "modeled_barista_unit_minutes_freed_for_S5": round(freed,10),
                "modeled_existing_support_unit_minutes_used_for_S5":
                    round(support,10),
            }
            comparisons.append(item)
            for cost in economics[
                    "incremental_support_opportunity_cost_mxn_per_peak"]:
                for value in economics[
                        "assumed_value_mxn_per_additional_handoff_inside_peak"]:
                    net = round(delta*value-cost,10)
                    choice = ("S5_IF_ASSUMPTIONS" if net > 1e-8 else
                              "B0_IF_ASSUMPTIONS" if net < -1e-8 else
                              "TIE_IF_ASSUMPTIONS")
                    money_cells.append({
                        "load_label": chosen["load_label"],
                        "variant_id": name,
                        "opportunity_cost_mxn_per_peak_assumed": cost,
                        "timing_value_mxn_per_extra_peak_handoff_assumed": value,
                        "incremental_modeled_peak_handoffs": delta,
                        "net_illustrative_timing_value_mxn": net,
                        "conditional_sign_only": choice,
                        "break_even_timing_value_mxn_per_extra_handoff":
                            (round(cost/delta,10) if delta > 0 else None),
                    })
    need(len(comparisons) == LIMIT_PAIRS and
         len(money_cells) == LIMIT_PAIRS*9, "FIXED_DESIGN_COUNT_CHANGED")
    deltas = [row["delta_S5_minus_B0_modeled_handoffs_in_peak"]
              for row in comparisons]
    nominal = {x["load_label"]: x for x in comparisons
               if x["variant_id"] == "NOMINAL"}
    need(len(nominal) == 2, "NOMINAL_PAIRED_ROWS")
    impacts = {}
    for name in reference.DURATIONS:
        magnitude = 0
        for label, baseline in nominal.items():
            for bound in ("LOW","HIGH"):
                changed = next(r for r in comparisons
                               if r["load_label"] == label and
                               r["variant_id"] == name+"_"+bound)
                magnitude = max(magnitude, abs(
                    changed["delta_S5_minus_B0_modeled_handoffs_in_peak"]-
                    baseline["delta_S5_minus_B0_modeled_handoffs_in_peak"]
                ))
        impacts[name] = magnitude
    conditional_signs = dict(sorted(Counter(
        item["conditional_sign_only"] for item in money_cells).items()))
    max_impact = max(impacts.values())
    if max_impact > 0:
        second = {
            "variable": sorted(impacts, key=lambda k: (-impacts[k],k))[0],
            "priority_basis": (
                "largest modeled OAT change among declared duration bounds, "
                "not an observed effect"
            ),
            "modeled_max_absolute_delivery_delta_change": max_impact,
            "method": (
                "paired start/end timings per task and resource; "
                "preserve concurrency/censoring"
            ),
            "unit": "min per task or beverage under declared frontier",
        }
    else:
        second = {
            "variable": "NOT_RANKABLE_NO_DELIVERY_SENSITIVITY_IN_TESTED_GRID",
            "priority_basis": (
                "no tested duration bound changed the peak handoff delta; "
                "do not prescribe an arbitrary next timing measurement"
            ),
            "modeled_max_absolute_delivery_delta_change": 0,
            "method": "revisit mechanism or ask whether another KPI matters",
            "unit": "not applicable",
        }
    return {
        "schema": SCHEMA,
        "status": "P11_CONDITIONAL_CONSEQUENCES_NOT_BUSINESS_RECOMMENDATION",
        "source_scope": "CONSTRUCTION_SYNTHETIC_PAID_POS_ONLY",
        "source_manifest_sha256": safe["manifest_sha256"],
        "source_package_sha256": safe["source_sha256"],
        "reference_schema": reference.SCHEMA,
        "reference_engine": "SPECIALIZED_DETERMINISTIC_DES_NOT_D_M_B",
        "protocol_sha256": digest(protocol),
        "dossier_sha256": digest(dossier),
        "selection": selection,
        "paired_sensitivity": comparisons,
        "illustrative_economic_cells": money_cells,
        "summary": {
            "paired_counterfactual_model_runs": len(comparisons),
            "physical_reference_simulations": len(comparisons)*2,
            "conditional_economic_cells": len(money_cells),
            "sensitivity_variants": list(VARIANTS),
            "min_delta_peak_handoffs": min(deltas),
            "max_delta_peak_handoffs": max(deltas),
            "nominal_delta_by_load": {
                key: row["delta_S5_minus_B0_modeled_handoffs_in_peak"]
                for key, row in sorted(nominal.items())
            },
            "economic_grid_sign_counts": conditional_signs,
            "one_factor_peak_delivery_sensitivity_max_abs_delta":
                dict(sorted(impacts.items())),
            "assumptions_reversal_possible": strict_preference_reversal(conditional_signs),
            "economic_classification_varies": len(conditional_signs) > 1,
            "business_decision": "NOT_IDENTIFIABLE_WITHOUT_REAL_SERVICE_COSTS",
            "real_saturation_or_throughput_measured": False,
            "costs_and_value_are_hypotheses_only": True,
            "no_incremental_sales_implied_by_faster_handoff": True,
            "no_generalization_from_two_selected_synthetic_days": True,
            "evaluation_and_V1_holdouts_not_opened": True,
            "no_G3_or_scientific_lock_created": True,
            "external_consumption": {
                "R2": 0, "OMC": 0, "POST": 0, "new_worlds": 0, "G3": 0},
        },
        "measurement_next": {
            "first": {
                "variable": "EXISTING_SUPPORT_ACTUAL_AVAILABILITY",
                "why": "S5 requires an actually available worker; POS does not show this",
                "method": "obtain anonymized staffing/timesheet and task occupancy during comparable peak",
                "unit": "worker-minutes free per peak and pickup handoff overlap",
                "change_criterion": "if no spare support, S5 is not representable under this scope",
            },
            "second": second,
            "economic": {
                "variables": [
                    "real opportunity cost of moving support away from other tasks",
                    "value or SLA of timely handoff versus eventual delivery",
                ],
                "note": "Do not assume extra peak handoffs equal incremental paid orders or real revenue",
            },
        },
    }


def export(result, out):
    dest = Path(out)
    need(not dest.exists(), "OUTPUT_EXISTS")
    dest.mkdir(mode=0o700, parents=True)
    # No event IDs, raw POS, truth, seed or original scenario labels.
    for file, rows in (
        ("paired-sensitivity.csv", result["paired_sensitivity"]),
        ("economics-conditional.csv", result["illustrative_economic_cells"]),
    ):
        with (dest/file).open("x",newline="",encoding="utf-8") as stream:
            writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    published = {k:v for k,v in result.items()
                 if k not in ("paired_sensitivity",
                              "illustrative_economic_cells")}
    write_json(dest/"p11-conditional-summary.json", published, exclusive=True)
    outcome = result["summary"]
    (dest/"REVIEW.md").write_text("\n".join([
        "# P11 — B0 vs S5: consecuencias condicionales, NO recomendación real",
        "",
        "Entrada: dos días del POS sintético de CONSTRUCTION, seleccionados por",
        "rangos Q25/Q75 de pagos ANTES de simular resultados.",
        "La carga de pagos no acredita saturación ni demanda real.",
        f"Comparaciones pareadas: {outcome['paired_counterfactual_model_runs']} "
        f"({outcome['physical_reference_simulations']} corridas de referencia).",
        f"Delta de handoffs modelados antes del corte en variantes: "
        f"{outcome['min_delta_peak_handoffs']} a "
        f"{outcome['max_delta_peak_handoffs']}.",
        f"Signos económicos en la grilla declarada: "
        f"{outcome['economic_grid_sign_counts']}.",
        "",
        "**Los valores MXN son escenarios de valor del tiempo y coste de",
        "reasignación supuestos; no son ingresos, beneficios ni ROI reales.**",
        "Los handoffs adicionales dentro del pico pueden ser entregas adelantadas",
        "respecto del drenaje, no ventas adicionales.",
        "La primera medición discriminante es disponibilidad real del personal",
        "de apoyo y su coste de oportunidad; ver p11-conditional-summary.json.",
        "",
        "No se consultó truth, EVALUATION, G3 ni datos reservados de V1.",
    ]) + "\n", encoding="utf-8")
    write_json(dest/"receipt.json", {
        "schema": SCHEMA,
        "source_manifest_sha256": result["source_manifest_sha256"],
        "protocol_sha256": result["protocol_sha256"],
        "dossier_sha256": result["dossier_sha256"],
        "files": {
            x.name: "sha256:"+reader.sha_file(x)
            for x in sorted(dest.iterdir())
            if x.name != "receipt.json"
        },
        "evaluation_cases_read": 0,
        "provider_calls": 0, "omc_runs": 0, "new_worlds": 0,
    }, exclusive=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="P11 conditional comparison, no G3")
    p.add_argument("--views",required=True)
    p.add_argument("--dossier",required=True)
    p.add_argument("--protocol",required=True)
    p.add_argument("--out",required=True)
    args = p.parse_args(argv)
    try:
        base = json.loads(Path(args.dossier).read_text(encoding="utf-8"))
        protocol = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
        outcome = compare(args.views,base,protocol)
        export(outcome,args.out)
        print(json.dumps({
            "status": outcome["status"],
            "pairs": outcome["summary"]["paired_counterfactual_model_runs"],
            "real_business_recommendation": False,
            "external_paid_calls": 0,
        },sort_keys=True))
        return 0
    except (ArenaError, OSError, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "STOPPED_NO_EXTERNAL_CONSUMPTION",
            "reason": str(exc) if isinstance(exc,ArenaError)
                      else "INVALID_RELEASE_DOSSIER_OR_PROTOCOL"
        }),file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
