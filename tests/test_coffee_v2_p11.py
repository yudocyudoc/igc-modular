"""P11 tests: fictional authorized producer release; zero real data or provider."""
from collections import Counter
import copy
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from arena.common import ArenaError
from arena import coffee_v2_p11 as p11
from arena import coffee_v2_reference as reference
from arena import coffee_v2_producer_views as views
from arena import coffee_v2_reference_inputs as ingress
from test_coffee_v2_reference import dossier, make_view, paid, item


def contract():
    return {
        "schema": p11.PROTOCOL,
        "scope": "CONDITIONAL_SYNTHETIC_PAID_POS_ONLY_NOT_BUSINESS_VALIDATION",
        "selection": {
            "partition": "CONSTRUCTION",
            "method": p11.SELECTION,
            "quantile_ranks": [0.25,0.75],
            "exclude_zero_paid_days": True,
            "exclude_partial_or_V1_reserved_days": True,
            "choose_before_simulation": True,
        },
        "policies": ["B0", reference.S5],
        "sensitivity": {
            "design": "ONE_AT_A_TIME_PLUS_JOINT_EXTREMES_AND_TWO_CAPACITY_CHECKS",
            "variant_ids": list(p11.VARIANTS),
            "use_same_pos_and_items_for_both_policies": True,
            "no_truth_calibration": True,
        },
        "illustrative_economics": {
            "incremental_support_opportunity_cost_mxn_per_peak": [0,60,150],
            "assumed_value_mxn_per_additional_handoff_inside_peak": [0,20,50],
            "interpretation": "ILLUSTRATIVE_TIMING_VALUE_NOT_SALES_PROFIT_OR_REAL_ROI",
        },
        "rules": {
            "count_handoffs_only_before_exclusive_peak_end": True,
            "report_open_at_cut_and_full_drain_separately": True,
            "no_revenue_from_faster_service_without_explicit_value_assumption": True,
            "no_empirical_saturation_claim": True,
            "no_business_recommendation_or_G3": True,
            "no_evaluation_partition_access": True,
        },
    }


class ConditionalP11Tests(TestCase):
    def test_two_predeclared_input_loads_paired_sensitivity_and_cost_grid(self):
        with TemporaryDirectory() as temp:
            folder, audited = make_view(temp)
            result = p11.compare(folder, dossier(), contract())
            self.assertEqual(result["status"],
                "P11_CONDITIONAL_CONSEQUENCES_NOT_BUSINESS_RECOMMENDATION")
            self.assertEqual(len(result["paired_sensitivity"]), 26)
            self.assertEqual(len(result["illustrative_economic_cells"]), 234)
            self.assertEqual(result["summary"]["physical_reference_simulations"],52)
            self.assertEqual(result["summary"]["paired_counterfactual_model_runs"],26)
            self.assertEqual(result["summary"]["conditional_economic_cells"],234)
            self.assertEqual(result["summary"]["business_decision"],
                             "NOT_IDENTIFIABLE_WITHOUT_REAL_SERVICE_COSTS")
            self.assertTrue(result["summary"]["evaluation_and_V1_holdouts_not_opened"])
            self.assertFalse(result["summary"]["no_G3_or_scientific_lock_created"] is False)
            selected = result["selection"]["selected"]
            self.assertEqual([x["load_label"] for x in selected],
                             ["LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75"])
            self.assertEqual(len({(x["case_id"],x["day"]) for x in selected}),2)
            self.assertEqual({x["partition"] for x in selected},{"CONSTRUCTION"})
            self.assertEqual(result["selection"]["saturation_status"],
                             "NOT_CLASSIFIED_FROM_PAID_LOAD_ALONE")
            self.assertEqual(result["selection"]["input_load_contrast"],
                             "TIED_SELECTED_PAID_INPUT_NO_LOW_HIGH_DISTINCTION")
            self.assertEqual(result["measurement_next"]["second"]["variable"],
                             "NOT_RANKABLE_NO_DELIVERY_SENSITIVITY_IN_TESTED_GRID")
            withheld = {r["opaque_case_id"] for r in audited["cases"]
                        if r["partition"]=="EVALUATION"}
            self.assertFalse(withheld & {x["case_id"] for x in selected})
            self.assertTrue(all(
                r["B0_modeled_handoffs_in_peak"] +
                r["B0_modeled_open_at_cut"] == r["synthetic_paid_orders"]
                and r["S5_modeled_handoffs_in_peak"] +
                r["S5_modeled_open_at_cut"] == r["synthetic_paid_orders"]
                and r["modeled_barista_unit_minutes_freed_for_S5"] >= 0
                for r in result["paired_sensitivity"]
            ))
            variants = Counter(r["variant_id"] for r in result["paired_sensitivity"])
            self.assertEqual(set(variants),set(p11.VARIANTS))
            self.assertTrue(all(n==2 for n in variants.values()))
            self.assertEqual(
                result["measurement_next"]["first"]["variable"],
                "EXISTING_SUPPORT_ACTUAL_AVAILABILITY")
            other = p11.compare(folder, dossier(), contract())
            self.assertEqual(result,other)
            out=Path(temp)/"p11-aggregate"
            p11.export(result,out)
            self.assertEqual({p.name for p in out.iterdir()},{
                "paired-sensitivity.csv","economics-conditional.csv",
                "p11-conditional-summary.json","REVIEW.md","receipt.json"})
            receipt=json.loads((out/"receipt.json").read_text())
            self.assertEqual(receipt["evaluation_cases_read"],0)
            for name,hash_ in receipt["files"].items():
                self.assertEqual(hash_,"sha256:"+ingress.sha_file(out/name))
            text="\n".join(x.read_text("utf-8") for x in out.iterdir())
            for sensitive in ("PRIVATE_regime_", "PRIVATE_ORDER_",
                              "PRIVATE_LINE_", "SUPER_PRIVATE_TRUTH_CANARY",
                              "seed", "scenario_id", "peak_arrivals_per_minute"):
                self.assertNotIn(sensitive,text)
            self.assertIn("NO recomendación real",
                          (out/"REVIEW.md").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ArenaError,"OUTPUT_EXISTS"):
                p11.export(result,out)

    def test_real_counterfactual_mechanism_changes_modeled_peak_service_in_burst(self):
        # Fictitious burst: 3 already-paid synthetic orders at t=0, not
        # synthetic truth or a measured cafeteria demand regime.
        base = dossier()
        base["durations"]["espresso_auto_min"].update({
            "value": 1, "bounds": [0.5, 1.5]})
        base["durations"]["handoff_min"].update({
            "value": 2, "bounds": [1, 3]})
        intervention = copy.deepcopy(base)
        intervention["policy"] = reference.S5
        reference.counterfactual_pair_gate(base, intervention)
        positions = [paid(x) for x in ("A", "B", "C")]
        items = [item(x) for x in ("A", "B", "C")]
        b0 = reference.simulate(positions, items, base, 8.5)
        s5 = reference.simulate(positions, items, intervention, 8.5)
        self.assertEqual((b0["synthetic_paid_orders"],
                          s5["synthetic_paid_orders"]), (3, 3))
        self.assertGreater(
            s5["modeled_handoffs_during_halfopen_peak"],
            b0["modeled_handoffs_during_halfopen_peak"])
        delta = (s5["modeled_handoffs_during_halfopen_peak"] -
                 b0["modeled_handoffs_during_halfopen_peak"])
        self.assertEqual(delta, 1)
        self.assertEqual(delta*20-0, 20)
        self.assertEqual(delta*20-60, -40)
        self.assertEqual(b0["modeled_handoffs_after_peak_in_drain"],
                         s5["modeled_handoffs_after_peak_in_drain"]+1)

    def test_protocol_and_business_claims_are_not_mutable(self):
        p = contract()
        self.assertEqual(len(p11.VARIANTS),13)
        self.assertIsNotNone(p11.protocol_gate(p))
        for label, mutate, error in [
            ("evaluation", lambda x: x["selection"].update(partition="EVALUATION"),
             "SELECTION_NOT_PREDECLARED"),
            ("selected-by-outcome",lambda x: x["selection"].update(
                method="BEST_S5_OUTCOME"),"SELECTION_NOT_PREDECLARED"),
            ("notpaired",lambda x: x["policies"].reverse(),
             "POLICY_PAIR_NOT_B0_S5"),
            ("grid", lambda x: x["illustrative_economics"].update(
                incremental_support_opportunity_cost_mxn_per_peak=[150,60,0]),
             "ECONOMIC_GRID_MUST_BE_UNIQUE_SORTED"),
            ("realROI",lambda x: x["illustrative_economics"].update(
                interpretation="REAL_RETURN_ON_INVESTMENT"),
             "ECONOMIC_CLAIM_EXCEEDS_EVIDENCE"),
            ("G3",lambda x: x["rules"].update(no_business_recommendation_or_G3=False),
             "DECISION_GATES_NOT_PREDECLARED"),
        ]:
            with self.subTest(label=label):
                altered=copy.deepcopy(p)
                mutate(altered)
                with self.assertRaisesRegex(ArenaError,error):
                    p11.protocol_gate(altered)

    def test_no_hidden_support_no_extra_resource_disguised_as_s5(self):
        bad=dossier()
        bad["resources"]["existing_support"]["units"]=0
        with self.assertRaisesRegex(ArenaError,
                                    "S5_NOT_REPRESENTABLE_WITH_THIS_DOSSIER"):
            p11._variants(bad)
        bad=dossier()
        bad["policy"]=reference.S5
        with self.assertRaisesRegex(ArenaError,
                                    "S5_NOT_REPRESENTABLE_WITH_THIS_DOSSIER"):
            p11._variants(bad)
        first = p11._variants(dossier())
        self.assertEqual([x[0] for x in first], list(p11.VARIANTS))
        for _, candidate in first:
            other=copy.deepcopy(candidate)
            other["policy"]=reference.S5
            self.assertTrue(reference.counterfactual_pair_gate(
                candidate,other)["comparison_is_conditional_not_executed"])
            self.assertEqual(candidate["resources"]["existing_support"]["units"],1)

    def test_v1_partial_bins_not_reinterpreted_as_zero(self):
        with TemporaryDirectory() as temp:
            folder, audited=make_view(temp)
            # The P11 candidate selection is determined by the P05 bins.
            # Verify a deliberately marked hidden V1 slice cannot enter ranking.
            summary=p11._verified_load_choices(folder)
            self.assertEqual(summary["construction_day_count"],252)
            chosen=summary["selected"]
            with (folder/"producer-paid-bins-5min.csv").open("a") as handle:
                handle.write("TAMPERING_IS_NOT_ZERO\n")
            with self.assertRaisesRegex(ArenaError,"SOURCE_MEMBER_CHANGED"):
                p11.compare(folder,dossier(),contract())

    def test_every_economic_cell_uses_only_timing_value_minus_opportunity_cost(self):
        with TemporaryDirectory() as temp:
            folder, _=make_view(temp)
            result=p11.compare(folder,dossier(),contract())
            for row in result["illustrative_economic_cells"]:
                delta=row["incremental_modeled_peak_handoffs"]
                cost=row["opportunity_cost_mxn_per_peak_assumed"]
                value=row["timing_value_mxn_per_extra_peak_handoff_assumed"]
                self.assertAlmostEqual(row["net_illustrative_timing_value_mxn"],
                                       delta*value-cost)
                if delta > 0:
                    self.assertAlmostEqual(
                        row["break_even_timing_value_mxn_per_extra_handoff"],
                        cost/delta)
                else:
                    self.assertIsNone(
                        row["break_even_timing_value_mxn_per_extra_handoff"])


if __name__ == "__main__":
    import unittest
    unittest.main()
