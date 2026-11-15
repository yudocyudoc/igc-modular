"""Negative S5 claim and next-move regressions; all calculations in GitHub CI."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, digest, read_json
from arena import coffee_decision_disposition as disposition
from arena import coffee_next_action as next_action
from arena import coffee_s5_availability as pilot
from arena import decision_atms as atms
from arena import decision_atms_gate as gate
from test_coffee_v2_reference import dossier, make_view
from test_coffee_v2_p11 import contract


def fixtures():
    first=atms.scenario_predecision(
        dossier(),contract(),recorded_at="2026-11-15T12:00:00.000000Z")
    allowed=gate.gate(first,dossier(),contract())
    return first, allowed


def intentionally_mixed_grid():
    """One positive P90 cherry-pick is NOT a broad service improvement."""
    cases=[]
    for load in disposition.LOADS:
        for available in disposition.FREE:
            s5=9 if available==0 else 10
            p90=9.8 if available==100 and load==disposition.LOADS[1] else (
                12.0 if available==0 else 11.0)
            cases.append({
                "load_label":load,
                "support_available_pct_assumed":available,
                "synthetic_paid_orders":10,
                "B0_handoffs_in_peak":10,
                "S5_handoffs_in_peak":s5,
                "B0_pending_at_peak_cut":0,
                "S5_pending_at_peak_cut":10-s5,
                "delta_S5_minus_B0_handoffs_in_peak":s5-10,
                "B0_p90_full_drain_min":10.0,
                "S5_p90_full_drain_min":p90,
                "delta_S5_minus_B0_p90_min":round(p90-10.0,10),
            })
    return cases


class DispositionTests(unittest.TestCase):
    def test_cherry_pick_counterfactual_is_rejected_and_replayable(self):
        pre, admitted=fixtures()
        rows=intentionally_mixed_grid()
        # Deliberately unsafe (non-ATMS) decision rule: just pick best P90.
        bad_shortcut=any(x["delta_S5_minus_B0_p90_min"]<0 for x in rows)
        self.assertTrue(bad_shortcut)
        evidence=disposition.disposition(pre,admitted,rows)
        self.assertFalse(evidence["claims"][disposition.BROAD]["supported"])
        self.assertTrue(evidence["claims"][disposition.P90_SOME]["supported"])
        self.assertTrue(evidence["claims"][disposition.NO_PEAK_GAIN]["supported"])
        self.assertTrue(evidence["claims"][disposition.HARM]["supported"])
        self.assertTrue(evidence["claims"][disposition.NEXT]["supported"])
        self.assertEqual(evidence["prevented_claim_example"][
            "classification"],"REJECTED_CHERRY_PICK_GENERALIZATION")
        self.assertEqual(evidence["business_choice"],
            "MEASURE_FIRST_NOT_REAL_REASSIGNMENT_RECOMMENDATION")
        journal=atms.Journal(pre["journal"]+
                             evidence["postdecision_events"])
        t=evidence["cuts"]
        observed=journal.snapshot(as_known_at=t["predecision_T"],
                                  valid_at=t["predecision_T"])
        gathered=journal.snapshot(
            as_known_at=t["evidence_T_plus_microseconds"],
            valid_at=t["evidence_T_plus_microseconds"])
        finished=journal.snapshot(
            as_known_at=t["disposition_T_plus_microseconds"],
            valid_at=t["disposition_T_plus_microseconds"])
        self.assertEqual(observed["snapshot_sha256"],
                         evidence["snapshots"]["predecision"])
        self.assertEqual(gathered["snapshot_sha256"],
                         evidence["snapshots"]["evidence"])
        self.assertEqual(finished["snapshot_sha256"],
                         evidence["snapshots"]["disposition"])
        self.assertNotIn(disposition.BROAD,finished["labels"])
        self.assertIn(disposition.P90_SOME,finished["labels"])
        self.assertEqual(observed,pre["snapshot"])

    def test_six_contexts_and_valid_counters_required_before_claim(self):
        pre, admitted=fixtures()
        rows=intentionally_mixed_grid()
        tempting=next(x for x in rows if
                      x["delta_S5_minus_B0_p90_min"]<0)
        with self.assertRaisesRegex(ArenaError,"SIX_CONTEXTS_REQUIRED"):
            disposition.disposition(pre,admitted,[tempting])
        invalid=copy.deepcopy(rows)
        invalid[-1]["support_available_pct_assumed"]=0
        with self.assertRaisesRegex(ArenaError,"DUPLICATE_CONTEXT"):
            disposition.disposition(pre,admitted,invalid)
        invalid=copy.deepcopy(rows)
        invalid[-1]["delta_S5_minus_B0_handoffs_in_peak"]=999
        with self.assertRaisesRegex(ArenaError,"BROKEN_MASS_OR_DELTA"):
            disposition.disposition(pre,admitted,invalid)
        invalid=copy.deepcopy(rows)
        invalid[-1]["S5_p90_full_drain_min"]+=4
        with self.assertRaisesRegex(ArenaError,"BROKEN_P90_DELTA"):
            disposition.disposition(pre,admitted,invalid)
        # Reject a re-stamped or modified predecision and a swapped receipt.
        changed=copy.deepcopy(admitted)
        changed["gate_sha256"]="sha256:"+"f"*64
        with self.assertRaisesRegex(ArenaError,"GATE_RECEIPT_MUTATED"):
            disposition.disposition(pre,changed,rows)

    def test_broad_claim_only_if_all_contexts_nonworse_and_some_better(self):
        pre,admitted=fixtures()
        rows=intentionally_mixed_grid()
        for row in rows:
            row["S5_handoffs_in_peak"]=10
            row["S5_pending_at_peak_cut"]=0
            row["delta_S5_minus_B0_handoffs_in_peak"]=0
            row["S5_p90_full_drain_min"]=9.8
            row["delta_S5_minus_B0_p90_min"]=-0.2
        allowed=disposition.disposition(pre,admitted,rows)
        self.assertTrue(allowed["claims"][disposition.BROAD]["supported"])
        self.assertEqual(allowed["business_choice"],
            "CONDITIONAL_SERVICE_IMPROVEMENT_WORTH_MEASURING")
        self.assertFalse(allowed["claims"][disposition.HARM]["supported"])
        self.assertFalse(allowed["not_a_real_business_recommendation"] is False)

    def test_next_mechanisms_only_change_one_physical_parameter(self):
        base=dossier()
        manual=next_action._candidate(
            base,next_action.MECHANISMS[0])
        machine=next_action._candidate(
            base,next_action.MECHANISMS[1])
        self.assertEqual(manual["durations"]["manual_setup_min"]["value"],
                         base["durations"]["manual_setup_min"]["bounds"][0])
        self.assertEqual(machine["resources"]["espresso_group"]["units"],
                         base["resources"]["espresso_group"]["units"]+1)
        self.assertEqual(base["resources"]["espresso_group"]["units"],1)
        self.assertEqual(base["durations"]["manual_setup_min"]["value"],1)
        self.assertEqual(manual["resources"],base["resources"])
        self.assertEqual(machine["durations"],base["durations"])

    def test_real_synthetic_input_method_keeps_paid_orders_and_economic_limits(self):
        with TemporaryDirectory() as tmp:
            views,_=make_view(tmp)
            result=next_action.compare(views,dossier())
            self.assertEqual(len(result["rows"]),4)
            self.assertEqual(
                set(r["mechanism"] for r in result["rows"]),
                set(next_action.MECHANISMS))
            for row in result["rows"]:
                self.assertEqual(row["paid_orders_same_both_cases"],1)
                self.assertTrue(row[
                    "physical_reference_only_not_original_DM_B"])
            self.assertFalse(result["real_profit_or_new_sales_inferred"])
            self.assertTrue(all(v["actual_capex_training_cost_and_margin_unknown"]
                                for v in result["candidate_assessments"].values()))

    def test_export_includes_gate_and_all_three_knowledge_cuts(self):
        with TemporaryDirectory() as tmp:
            path,_=make_view(tmp)
            result=pilot.compare(path,dossier(),contract())
            out=Path(tmp)/"result"
            pilot.export(result,out)
            self.assertTrue((out/"ATMS_GATE.json").is_file())
            self.assertTrue((out/"ATMS_PREDECISION.json").is_file())
            self.assertTrue((out/"ATMS_DISPOSITION.json").is_file())
            self.assertTrue((out/"NEXT_ACTION.json").is_file())
            self.assertTrue((out/"next-action-service.csv").is_file())
            written=read_json(out/"decision.json")
            proof=read_json(out/"ATMS_DISPOSITION.json")
            self.assertEqual(written["atms"]["disposition_sha256"],
                             proof["disposition_sha256"])
            self.assertEqual(written["atms"]["business_choice"],
                             proof["business_choice"])
            text=(out/"DECISION.md").read_text(encoding="utf-8")
            self.assertIn("Mejoría general del servicio",text)
            self.assertIn("preparación manual",text.lower())
            self.assertIn("SIN_SOPORTE",text)
            self.assertIn("Cadena temporal replayable",text)


if __name__=="__main__":
    unittest.main()
