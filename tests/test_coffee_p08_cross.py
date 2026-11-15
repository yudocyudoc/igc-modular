"""Cross-method P08 comparison is computed only in GitHub Actions."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError
from arena import coffee_p08_cross as cross
from arena import coffee_m_p08 as m
from arena import coffee_next_action as ref


def example():
    r={
        "schema":ref.SCHEMA,
        "status":"TWO_MECHANISMS_COMPARED_WITH_FIXED_B0",
        "real_profit_or_new_sales_inferred":False,
        "priority_to_measure":["MANUAL_PREPARATION_TO_DECLARED_LOWER_BOUND"],
        "rows":[],
    }
    n={
        "schema":m.SCHEMA,
        "status":"NATIVE_M_P08_SIX_SIMS_SUCCEEDED",
        "new_omc_attempted":6,"failed_models":[],
        "causal_real_business_evidence":False,
        "pairwise_comparisons":[],
    }
    for label in m.INPUT_LABELS:
        for mechanism,variant in cross.MAP.items():
            delta=1 if "MANUAL" in mechanism else 0
            r["rows"].append({
                "load_label":label,"mechanism":mechanism,
                "B0_peak_handoffs":19,
                "intervention_peak_handoffs":19+delta,
                "delta_peak_handoffs_not_new_sales":delta,
                "paid_orders_same_both_cases":20,
            })
            md=2.5 if variant=="PREP_CAPACITY_X2" else 0.0
            n["pairwise_comparisons"].append({
                "load_label":label,"variant":variant,
                "B0_paid_orders_from_existing_artifact":20,
                "native_M_B0_continuous_handoffs_at_cut":15.0,
                "native_M_policy_continuous_handoffs_at_cut":15.0+md,
                "delta_continuous_handoffs_at_cut":md,
                "correspondence_to_reference":
                    "NO_EXACT_MAPPING_OF_RECIPES_OR_P90",
            })
    return r,n


class CrossMethodTests(unittest.TestCase):
    def test_atms_supports_comparison_but_not_physical_transfer(self):
        r,n=example()
        outcome=cross.compare(r,n,recorded_at="2026-11-15T11:00:00.000000Z")
        self.assertEqual(len(outcome["comparison_rows"]),4)
        self.assertTrue(outcome["atms"]["conditioned_claim"][
            "logical_support_environments"])
        self.assertFalse(outcome["atms"]["unsupported_real_claim"][
            "logical_support_environments"])
        self.assertIn("SAME_POS_TEMPORAL_INPUT",
                      outcome["atms"]["missing_physical_evidence"])
        self.assertTrue(outcome["not_an_ROI_or_real_business_recommendation"])
        self.assertEqual(outcome["new_OMC_or_provider_calls"],0)
        self.assertEqual(outcome["reference_priority_to_measure"],
            ["MANUAL_PREPARATION_TO_DECLARED_LOWER_BOUND"])
        with TemporaryDirectory() as tmp:
            cross.export(outcome,Path(tmp)/"result")
            text=(Path(tmp)/"result"/"DECISION.md").read_text()
            self.assertIn("UNSUPPORTED",text)
            self.assertIn("M B0",text)

    def test_corrupt_delta_and_missing_model_do_not_produce_decision(self):
        r,n=example()
        broken=copy.deepcopy(n)
        broken["pairwise_comparisons"][-1][
            "delta_continuous_handoffs_at_cut"]=99
        with self.assertRaisesRegex(ArenaError,"M_DELTA_INVALID"):
            cross.compare(r,broken,recorded_at="2026-11-15T11:00:00.000000Z")
        broken=copy.deepcopy(r)
        broken["rows"].pop()
        with self.assertRaisesRegex(ArenaError,
                                    "EXACTLY_TWO_ACTION_PAIRS_EACH"):
            cross.compare(broken,n,
                recorded_at="2026-11-15T11:00:00.000000Z")
        broken=copy.deepcopy(n)
        broken["status"]="INCOMPLETE_NATIVE_ATTEMPTS_NO_DECISION"
        with self.assertRaisesRegex(ArenaError,
                                    "M_SOURCE_NOT_SIX_AUTHENTIC_SIMULATIONS"):
            cross.compare(r,broken,
                recorded_at="2026-11-15T11:00:00.000000Z")

    def test_no_equal_physical_numeric_claim_even_when_directions_match(self):
        r,n=example()
        outcome=cross.compare(r,n,recorded_at="2026-11-15T11:00:00.000000Z")
        for row in outcome["comparison_rows"]:
            self.assertFalse(row["numeric_values_commensurable"])
            self.assertTrue(row["direction_same"])
        self.assertFalse(outcome["atms"]["snapshot"]["labels"].get(
            "M_VALIDATED_FOR_REAL_COFFEE_INTERVENTION"))


if __name__=="__main__":
    unittest.main()
