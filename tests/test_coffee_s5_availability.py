"""S5 support availability: fictional CI tests, real views only on GitHub main."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError
from arena import coffee_s5_availability as pilot
from arena import coffee_v2_reference as ref
from test_coffee_v2_reference import dossier, paid, item, make_view
from test_coffee_v2_p11 import contract


class StaffAvailabilityDecisionTests(unittest.TestCase):
    def test_other_work_reservation_is_not_displaceable(self):
        positions=[paid("A"),paid("B"),paid("C")]
        items=[item("A"),item("B"),item("C")]
        base=dossier()
        special=dossier(ref.S5)
        horizon=13
        idle=ref.simulate(positions,items,special,horizon)
        all_busy=ref.simulate(positions,items,special,horizon,
                              support_busy_windows=[(0,13)])
        partial=ref.simulate(positions,items,special,horizon,
                             support_busy_windows=[(0,5),(10,13)])
        baseline=ref.simulate(positions,items,base,horizon,
                              support_busy_windows=[(0,13)])
        self.assertEqual(idle["synthetic_paid_orders"],3)
        self.assertEqual(all_busy["modeled_handoffs_during_halfopen_peak"],0)
        self.assertEqual(all_busy["modeled_orders_open_at_peak_cut"],3)
        self.assertEqual(baseline["modeled_handoffs_during_halfopen_peak"],
                         ref.simulate(positions,items,base,horizon)[
                             "modeled_handoffs_during_halfopen_peak"])
        self.assertGreaterEqual(
            idle["modeled_handoffs_during_halfopen_peak"],
            partial["modeled_handoffs_during_halfopen_peak"])
        self.assertGreaterEqual(
            partial["modeled_handoffs_during_halfopen_peak"],
            all_busy["modeled_handoffs_during_halfopen_peak"])
        self.assertEqual(all_busy["modeled_final_open_orders"],0)
        self.assertEqual(all_busy["resources"]["existing_support"][
            "busy_unit_minutes_full_drain"],3.0)

    def test_calendar_validation_fail_closed(self):
        for invalid in (
            [(3,2)], [(-1,2)], [(1,6),(5,9)], [(0,20)],
            [(2,2)], [(0,3),(1,5)]):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ArenaError,"SUPPORT_"):
                    ref.support_calendar_gate(invalid,12)
        self.assertEqual(pilot.assumption_windows(20,0),[])
        self.assertEqual(pilot.assumption_windows(20,50),
                         [(0,5),(10,15)])
        self.assertEqual(pilot.assumption_windows(20,100),[(0.0,20.0)])
        with self.assertRaisesRegex(ArenaError,"UNDECLARED_SUPPORT_OCCUPANCY"):
            pilot.assumption_windows(20,75)

    def test_two_construction_loads_three_availabilities_and_business_readout(self):
        with TemporaryDirectory() as tmp:
            views,_=make_view(tmp)
            with patch.object(pilot.knowledge,"utc_now",
                              return_value="2026-11-15T12:00:00.000000Z"):
                result=pilot.compare(views,dossier(),contract())
            rows=result["comparison_rows"]
            self.assertEqual(len(rows),6)
            self.assertEqual(len(result["economic_rows"]),54)
            self.assertEqual(set(r["support_available_pct_assumed"]
                                 for r in rows),{0,50,100})
            for label in pilot.VALID_MARKERS:
                sub=[r for r in rows if r["load_label"]==label]
                self.assertEqual(len({r["B0_handoffs_in_peak"]
                                      for r in sub}),1)
                no_support=next(r for r in sub if
                                r["support_available_pct_assumed"]==0)
                self.assertEqual(no_support["S5_handoffs_in_peak"],0)
                self.assertEqual(no_support["synthetic_paid_orders"],
                                 no_support["B0_handoffs_in_peak"])
                self.assertLess(no_support[
                    "delta_S5_minus_B0_handoffs_in_peak"],0)
                self.assertEqual(no_support["S5_pending_at_peak_cut"],
                                 no_support["synthetic_paid_orders"])
            self.assertEqual(result["decision_readout"]["current_business_choice"],
                             "MEASURE_FIRST_NOT_REAL_REASSIGNMENT_RECOMMENDATION")
            self.assertEqual(result["external_consumption"]["provider_POST"],0)
            out=Path(tmp)/"result"
            pilot.export(result,out)
            self.assertEqual({p.name for p in out.iterdir()},{
                "support-availability-service.csv",
                "support-availability-economics.csv",
                "decision.json","DECISION.md","receipt.json"})
            self.assertEqual(json.loads((out/"receipt.json").read_text())[
                "source_run_id"],pilot.SOURCE_RUN_ID)
            report=(out/"DECISION.md").read_text()
            self.assertIn("Medir",report)
            self.assertIn("no nuevos pedidos",report.lower())
            self.assertNotIn("PRIVATE_ORDER",report)

    def test_no_paid_work_while_staff_is_busy_but_drain_is_allowed(self):
        d=dossier(ref.S5)
        rows=[paid("X",time=0)]
        drinks=[item("X",time=0)]
        result,intervals,_=ref._engine(rows,drinks,d,10,
                                        support_busy_windows=[(0,10)])
        handoff=[x for x in intervals if x[0]=="handoff"]
        self.assertEqual(len(handoff),1)
        self.assertGreaterEqual(handoff[0][1],10)
        self.assertEqual(result["modeled_handoffs_during_halfopen_peak"],0)
        self.assertEqual(result["modeled_handoffs_after_peak_in_drain"],1)
        self.assertEqual(result[
            "existing_support_other_work_reserved_unit_minutes_in_peak_assumed"
        ],10.0)

    def test_economics_are_early_handoffs_not_invented_sales(self):
        with TemporaryDirectory() as tmp:
            views,_=make_view(tmp)
            r=pilot.compare(views,dossier(),contract())
            for cell in r["economic_rows"]:
                delta=cell["delta_earlier_handoffs_not_new_sales"]
                v=cell["assumed_timing_value_mxn_per_handoff"]
                c=cell["assumed_cost_of_reassignment_mxn"]
                self.assertEqual(cell["net_illustrative_timing_value_mxn"],
                                 delta*v-c)
                self.assertEqual(
                    cell["break_even_value_mxn_per_handoff_if_delta_positive"],
                    round(c/delta,10) if delta>0 else None)


if __name__=="__main__":
    unittest.main()
