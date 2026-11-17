"""P45 C: causal-wait accounting in explicitly fictional software worlds."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, read_json
from arena import coffee_v2_hydra_physical_b as b
from arena import coffee_v2_hydra_causes_c as c
from test_coffee_v2_reference import paid,item

ROOT=Path(__file__).resolve().parents[1]
DOSSIER=ROOT/"experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json"
VIEW=ROOT/"experiments/coffee_v2/VIDEO2_EPISODE_REVIEW_A.json"
HIST=ROOT/"experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json"
TOY=ROOT/"experiments/coffee_v2/C_FIXED_TOY_PAID_INPUT.json"


def initial():
    return read_json(DOSSIER)


def scene(n=3,d=None,milk=False):
    d=d or initial()
    positions=[paid(str(i)) for i in range(n)]
    lines=[item(str(i),"con_leche" if milk else "solo_extraccion")
           for i in range(n)]
    result,trace,completed=b._engine(positions,lines,d,10)
    report=c.diagnose_trace(result,trace,d,
                            fixture_label="SOFTWARE_TOY_C_UNIT")
    return result,trace,completed,report


def events(trace,name,stage=None):
    return [x for x in trace if x["event"]==name and
            (stage is None or x.get("stage")==stage)]


class CausalWaitTests(unittest.TestCase):
    def test_fixed_toy_input_is_explicitly_synthetic_and_versioned(self):
        toy=read_json(TOY)
        self.assertEqual(toy["schema"],c.FIXTURE_SCHEMA)
        self.assertEqual(toy["scope"],"SOFTWARE_TOY_ONLY")
        self.assertEqual(len(toy["positions"]),3)
        self.assertEqual(len(toy["lines"]),3)
        report=c.diagnose(toy["positions"],toy["lines"],initial(),
                          toy["horizon_min"],
                          fixture_label="SOFTWARE_TOY_P45_FIXED")
        self.assertEqual(report["schema"],c.SCHEMA)
        self.assertTrue(report["limits"]["not_a_policy_effect"])

    def test_predecessor_pending_is_distinct_from_resource_wait(self):
        _,trace,_,report=scene(1)
        pending=events(trace,"pending_precedence")
        eligible=events(trace,"eligible")
        load_start=events(trace,"start","load")[0]
        load_eligible=next(x for x in eligible if x["stage"]=="load")
        self.assertGreater(len(pending),0)
        self.assertAlmostEqual(load_eligible["time"],0.5)
        self.assertAlmostEqual(load_start["time"],0.5)
        self.assertAlmostEqual(load_start["resource_wait_min"],0)
        self.assertEqual(report["causal_accounting"][
            "total_resource_wait_task_min"],0)
        self.assertGreater(report["causal_accounting"][
            "precedence_pending_markers_not_timed"],0)
        self.assertTrue(any(x["stage"]=="load" for x in pending))

    def test_resource_wait_intervals_partition_each_task_wait(self):
        _,trace,_,report=scene(3)
        spans=events(trace,"blocked_interval")
        self.assertGreater(len(spans),0)
        summed=sum(x["minutes"] for x in spans)
        self.assertAlmostEqual(summed,report["causal_accounting"][
            "total_resource_wait_task_min"])
        self.assertTrue(all(x["blocking"]["all_routes_blocked"] for x in
                            spans))
        self.assertTrue(all(x["end_time"]>x["start_time"] for x in spans))
        self.assertGreater(report["causal_accounting"][
            "stage_breakdown"]["prepare"]["tasks_with_resource_wait"],0)

    def test_loading_group_all_extracting_only_counts_when_actor_eligible(self):
        d=initial()
        d["enabled_group_ids"]=["G01"]
        _,trace,_,report=scene(3,d)
        signal=report["hypotheses"]["extraction_limits"]
        self.assertGreater(signal["signal_task_min"],0)
        self.assertEqual(signal["status"],"SIGNAL_IN_ASSUMED_MODEL")
        load_spans=events(trace,"blocked_interval","load")
        self.assertTrue(any(all(
            route["group_state"]=="EXTRACTING" for route in
            span["blocking"]["alternative_routes"]) for span in load_spans))
        self.assertEqual(signal["external_evidence"],
                         "NOT_IDENTIFIED_FROM_VIDEO")

    def test_post_counter_group_state_is_not_automatic_extraction(self):
        d=initial()
        d["enabled_group_ids"]=["G01"]
        d["operators"]["B01"]["availability_windows_min"]=[
            [0,1],[3,30]]
        d["operators"]["B02"]["availability_windows_min"]=[[0,1]]
        _,trace,_,report=scene(2,d)
        self.assertGreater(report["hypotheses"]["extraction_limits"][
            "post_auto_group_held_load_wait_task_min"],0)
        self.assertTrue(any(x["event"]=="group_state" and
                            x["to"]=="AWAITING_REMOVAL"
                            for x in trace))
        self.assertTrue(any(
            any(route["group_state"]=="AWAITING_REMOVAL" for route
                in x["blocking"]["alternative_routes"])
            for x in events(trace,"blocked_interval","load")))

    def test_multiple_blockers_never_duplicate_total_wait(self):
        d=initial()
        d["enabled_group_ids"]=["G01"]
        d["operators"]["B02"]["availability_windows_min"]=[
            [0,0.5],[3,240]]
        _,trace,_,report=scene(3,d)
        acc=report["causal_accounting"]
        self.assertGreater(acc[
            "multi_blocker_candidate_task_min_NOT_EXCLUSIVE"],0)
        multi=[span for span in events(trace,"blocked_interval")
               if any(len(route["blockers"])>1 for route in span[
                   "blocking"]["alternative_routes"])]
        self.assertTrue(multi)
        self.assertAlmostEqual(acc["total_resource_wait_task_min"],
                               sum(x["minutes"] for x in events(
                                   trace,"blocked_interval")))
        self.assertGreater(sum(acc[
            "reason_presence_task_min_OVERLAPPING_NOT_ADDITIVE"].values()),
            acc["total_resource_wait_task_min"])
        self.assertIn("NOT_EXCLUSIVE",json.dumps(acc))

    def test_milk_handoff_are_eligible_and_wait_only_for_resources(self):
        d=initial()
        d["steam_wands"]=["W01"]
        _,trace,_,report=scene(4,d,milk=True)
        milk=events(trace,"start","milk")
        handoff=events(trace,"start","handoff")
        self.assertEqual(len(milk),4)
        self.assertEqual(len(handoff),4)
        self.assertEqual(report["causal_accounting"][
            "stage_breakdown"]["milk"]["completed_tasks"],4)
        self.assertTrue(all(x["precedence_satisfied"] for x in milk))
        self.assertTrue(all(x["resource_wait_min"]>=0 for x in handoff))
        self.assertTrue(report["limits"]["not_an_empirical_bottleneck_measure"])

    def test_a_b_representational_difference_does_not_claim_wait_cause(self):
        toy=read_json(TOY)
        report=c.diagnose(
            toy["positions"],toy["lines"],initial(),toy["horizon_min"],
            fixture_label="SOFTWARE_TOY_P45_FIXED",
            episode_view=read_json(VIEW),historical_dossier=read_json(HIST))
        rep=report["hypotheses"]["representation_artifact"]
        self.assertEqual(rep["status"],
                         "A_B_CONSTRUCTION_FEASIBILITY_RECONCILED")
        changes=rep["observational_A_B_check"]["historical_vs_B_status"]
        row=changes[
            "manual_preparation_concurrency_vs_resource_capacity"]
        self.assertEqual(row["historical"],"CONTRADICTED")
        self.assertEqual(row["physical_B"],"COMPATIBLE")
        self.assertFalse(rep["observational_A_B_check"][
            "independent_validation"])
        self.assertNotIn("operadores.jpg",json.dumps(report))

    def test_report_aggregates_without_order_identifiers_or_policy_claims(self):
        toy=read_json(TOY)
        report=c.diagnose(toy["positions"],toy["lines"],initial(),
                          toy["horizon_min"],
                          fixture_label="SOFTWARE_TOY_P45_FIXED")
        s=json.dumps(report)
        self.assertNotIn("payCtoy",s)
        self.assertNotIn("Ctoy0",s)
        self.assertNotIn("order_id",s)
        self.assertEqual(report["dispatch_policy"],"FCFS_READY_ASSUMED")
        self.assertTrue(report["limits"]["not_a_real_minutes_saved_estimate"])
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/"report"
            c.export(report,out)
            self.assertTrue((out/"C_CAUSAL_DIAGNOSIS.json").exists())
            self.assertIn("task-min",(out/"C_CAUSAL_DIAGNOSIS.md"
                                     ).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ArenaError,
                                        "OUTPUT_ALREADY_EXISTS"):
                c.export(report,out)

    def test_missing_wait_interval_fails_closed_not_imputed_zero(self):
        d=initial()
        result,trace,_,_=scene(3,d)
        altered=copy.deepcopy(trace)
        altered.remove(next(x for x in altered if x["event"]==
                            "blocked_interval"))
        with self.assertRaisesRegex(ArenaError,
              "RESOURCE_WAIT_NOT_PARTITIONED_BY_INTERVALS|GAP_OVERLAP"):
            c.diagnose_trace(result,altered,d,
                             fixture_label="SOFTWARE_TOY_C_UNIT")

    def test_stage_wait_is_not_sum_of_order_percentiles(self):
        result,_,_,report=scene(3)
        p90=result["modeled_paid_to_handoff_p90_full_drain_min"]
        self.assertEqual(report[
            "service_metrics_not_derived_from_stage_wait_sums"][
                "modeled_paid_to_handoff_p90_full_drain_min"],p90)
        self.assertIn("not real elapsed minutes",
                      report["causal_accounting"]["counting_rule"])

    def test_scope_requires_an_explicit_toy_not_fabricated_real_source(self):
        d=initial()
        result,trace,_,_=scene(1,d)
        with self.assertRaisesRegex(ArenaError,
                                    "REQUIRES_EXPLICIT_TOY_SCOPE"):
            c.diagnose_trace(result,trace,d,fixture_label="REAL_CAFE")


if __name__=="__main__":
    unittest.main()
