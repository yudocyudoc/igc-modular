"""P08 D/M/reference ATMS selection, GitHub synthetic fixtures only."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError
from arena import coffee_p08_threeway as three
from arena import coffee_d_p08 as d
from test_coffee_p08_cross import example


def scenario():
    r,m=example()
    D={
        "schema":d.SCHEMA,
        "status":"D_SIX_NATIVE_OMC_PASS_NOT_REAL_CAUSAL_VALIDATION",
        "omc_attempts_reserved":6,
        "failures":[],
        "physical_model_identified":False,
        "stage_mapping_validated":False,
        "pairwise_comparisons":[],
    }
    # Deliberate conflict: physical reference reports espresso gain, while
    # D and M generic proxies still classify it as unchanged.
    for row in r["rows"]:
        if row["mechanism"]=="ONE_ADDITIONAL_ESPRESSO_GROUP":
            row["intervention_peak_handoffs"]+=1
            row["delta_peak_handoffs_not_new_sales"]+=1
    for label in d.LOADS:
        for variant in d.VARIANTS[1:]:
            delta=1.1 if variant=="PREP_CAPACITY_X2" else 0.0
            D["pairwise_comparisons"].append({
                "load_label":label,"variant":variant,
                "native_D_B0_continuous_at_cut":10.0,
                "native_D_policy_continuous_at_cut":10+delta,
                "delta_continuous_at_cut":delta,
                "B0_paid_orders_from_source":20,
                "representation":"D_THREE_STOCKS_GENERIC_STAGE_CAPACITY_PROXY",
            })
    return r,m,D


class ThreewayMethodTests(unittest.TestCase):
    def test_disagreement_selects_field_stage_measurement(self):
        r,m,D=scenario()
        result=three.compare(
            r,m,D,recorded_at="2026-11-15T12:00:00.000000Z")
        self.assertEqual(len(result["rows"]),4)
        self.assertEqual(result["same_direction_contexts"],2)
        self.assertEqual(result["different_direction_contexts"],2)
        self.assertEqual(result["selected_next_experiment"]["priority"],
                         "FIELD_DISCRIMINATION_OF_MODEL_DISAGREEMENT")
        self.assertEqual(result["disputed_stage_mechanisms"],
                         ["ONE_ADDITIONAL_ESPRESSO_GROUP"])
        self.assertTrue(result["atms"]["supported_comparison"])
        self.assertTrue(result["atms"]["disputed_stage_measurement_supported"])
        self.assertFalse(result["atms"]["real_business_claim_supported"])
        self.assertEqual(result["new_OMC_or_provider_calls"]
                         if "new_OMC_or_provider_calls" in result else 0,0)
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/"decision"
            three.export(result,out)
            text=(out/"DECISION.md").read_text()
            self.assertIn("ESPRESSO",text)
            self.assertIn("No",text)

    def test_replay_predecision_does_not_gain_future_simulated_evidence(self):
        r,m,D=scenario()
        res=three.compare(r,m,D,recorded_at="2026-11-15T12:00:00.000000Z")
        from arena import decision_atms as atms
        journal=atms.Journal(res["atms"]["journal"])
        start=res["atms"]["first_cut"]
        earlier=journal.snapshot(as_known_at=start,valid_at=start)
        self.assertEqual(earlier,res["atms"]["predecision_snapshot"])
        self.assertNotIn("D_NATIVE_SIX_SIMULATIONS",earlier["labels"])
        later=journal.snapshot(
            as_known_at=res["atms"]["final_cut"],
            valid_at=res["atms"]["final_cut"])
        self.assertEqual(later,res["atms"]["disposition_snapshot"])
        self.assertNotIn("REAL_COFFEE_MECHANISM_AND_ROI_ESTABLISHED",
                         later["labels"])

    def test_no_spurious_agreement_when_d_physical_link_missing(self):
        r,m,D=scenario()
        D["stage_mapping_validated"]=True
        with self.assertRaisesRegex(ArenaError,
                                    "D_NATIVE_RESULT_NOT_COMPLETE_OR_OVERCLAIMED"):
            three.compare(r,m,D,recorded_at="2026-11-15T12:00:00.000000Z")
        r,m,D=scenario()
        D["pairwise_comparisons"][-1][
            "B0_paid_orders_from_source"]=46
        with self.assertRaisesRegex(ArenaError,
                                    "D_AND_M_DO_NOT_SHARE_PAID_COUNT"):
            three.compare(r,m,D,recorded_at="2026-11-15T12:00:00.000000Z")
        r,m,D=scenario()
        D["pairwise_comparisons"][-1]["delta_continuous_at_cut"]=500
        with self.assertRaisesRegex(ArenaError,"D_DELTA_NOT_FROM_NATIVE"):
            three.compare(r,m,D,recorded_at="2026-11-15T12:00:00.000000Z")

    def test_three_methods_agree_changes_measurement_status_not_business_truth(self):
        r,m,D=scenario()
        for row in r["rows"]:
            if row["mechanism"]=="ONE_ADDITIONAL_ESPRESSO_GROUP":
                row["intervention_peak_handoffs"]=row["B0_peak_handoffs"]
                row["delta_peak_handoffs_not_new_sales"]=0
        result=three.compare(r,m,D,recorded_at="2026-11-15T12:00:00.000000Z")
        self.assertEqual(result["same_direction_contexts"],4)
        self.assertEqual(result["selected_next_experiment"]["priority"],
                         "FIELD_VALIDATION_OF_CONCORDANT_PROXY")
        self.assertFalse(result["atms"]["disputed_stage_measurement_supported"])
        self.assertFalse(result["atms"]["real_business_claim_supported"])
        self.assertFalse(result["not_business_investment_or_profit"] is False)


if __name__=="__main__":
    unittest.main()
