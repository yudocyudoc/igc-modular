"""All P42 tests are fictional fixture tests. Authentic P39 audited via Actions."""
from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, read_json
from arena import coffee_hydra_p42 as p42

DOSSIER=Path(__file__).resolve().parents[1]/"experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json"


def diag(count,wait,busy,groups,peak,prep,milk,handoff):
    return {
        "schema":"arena.coffee-v2.stage-wait-diagnostic/1",
        "espresso_group_assumed_units":groups,
        "diagnostic_does_not_modify_scheduling":True,
        "espresso_tasks_blocked_by_group_count":count,
        "espresso_auto_queued_minutes_before_cut":wait,
        "espresso_group_busy_unit_minutes_before_cut":busy,
        "espresso_group_busy_fraction_of_capacity_before_cut":
            round(busy/(peak*groups),10),
        "manual_setup_queued_minutes_before_cut":prep,
        "milk_finish_queued_minutes_before_cut":milk,
        "handoff_queued_minutes_before_cut":handoff,
    }


def fixture():
    cases=[]
    peak=103.2370666667
    for label,paid,bev,baseline,after,p0,p3,blocked,minutes in (
        ("LOWER_PAID_INPUT_Q25",19,23,19,19,5.28448,4.10432,12,15.1581),
        ("HIGHER_PAID_INPUT_Q75",46,53,45,46,7.54,5.54795,42,85.4108),
    ):
        base={
            "case":"HISTORICAL_ONE_ENABLED",
            "assumed_enabled_group_count":1,
            "assumed_automatic_extraction_min":1.5,
            "paid_orders":paid,"beverage_units":bev,
            "handoffs_before_cut":baseline,
            "p90_paid_to_handoff_full_drain_min":p0,
            "diagnostics":diag(blocked,minutes,bev*1.5,1,peak,5,3,8),
        }
        three={
            "case":"HYDRA_THREE_ENABLED_ASSUMED",
            "assumed_enabled_group_count":3,
            "assumed_automatic_extraction_min":1.5,
            "paid_orders":paid,"beverage_units":bev,
            "handoffs_before_cut":after,
            "p90_paid_to_handoff_full_drain_min":p3,
            "diagnostics":diag(0,0,bev*1.5,3,peak,3.7151,2.0874,5.3164),
        }
        cases.append({
            "load_label":label,"source_horizon_minutes":peak,
            "comparison":[base,three],
            "delta_handoffs_at_cut":after-baseline,
            "delta_p90_min":round(p3-p0,8),
            "same_paid_orders_and_beverage_mix":True,
            "change_only_one_to_three_assumed_enabled_groups":True,
        })
    return {
        "schema":"arena.coffee.p39.hydra-model-consumption/1",
        "status":"THREE_GROUP_HYDRA_SCENARIO_CONDITIONAL_NOT_CALIBRATED",
        "machine_evidence_consumer":{
            "timer_pairs":37,"group_presence_counts":{
                "G01":17,"G02":13,"G03":7},
            "identifiable_complete_auto_extraction_cycles":0},
        "timer_pairs_used_to_calibrate_auto_time":0,
        "automatic_extraction_time_minutes_used":1.5,
        "manual_load_remove_clean_explicitly_modeled":False,
        "simultaneous_availability_observed":False,
        "no_real_business_capacity_or_roi_inferred":True,
        "scenarios":cases,
    }


class P42PostprocessingTests(unittest.TestCase):
    def test_derives_structural_bound_and_publishes_existing_queues(self):
        source=fixture()
        result=p42.analyze(source,read_json(DOSSIER))
        self.assertEqual(result["sufficient_group_count_in_this_scheduler"],3)
        self.assertEqual(result["assumed_serial_setup_seconds"],30)
        self.assertEqual(result["assumed_auto_espresso_seconds"],90)
        self.assertEqual(len(result["scenarios"]),2)
        self.assertTrue(all(x["espresso_wait_minutes_task_1_to_3"][1]==0
                            for x in result["scenarios"]))
        self.assertEqual(result["reviewed_video_episodes"],0)
        self.assertEqual(result["new_simulations"],0)
        with TemporaryDirectory() as temp:
            p42.export(result,Path(temp)/"output")
            report=(Path(temp)/"output/P42_MECHANISM_REVIEW.md").read_text(
                encoding="utf-8")
            self.assertIn("90 / 30 = 3",report)
            self.assertIn("min-tarea",report)
            self.assertIn("SIN FOTOGRAMAS VERIFICADOS",report)

    def test_partial_pair_is_never_certified_extraction_cycle(self):
        result=p42.analyze(fixture(),read_json(DOSSIER))
        episodes=result["targeted_video_review"]
        self.assertEqual([x["record_id"] for x in episodes],
                         ["TM-T31","TM-T33","TM-T12"])
        self.assertEqual(episodes[0]["anchor_video_s"],[12.0,40.011])
        self.assertTrue(all(x["complete_extraction_end_s"] is None
                            and x["censored_or_unknown"]
                            and not x["frames_reviewed"] for x in episodes))

    def test_rejects_fake_empirical_calibration_and_non_zero_three_group_queue(self):
        source=fixture()
        source["timer_pairs_used_to_calibrate_auto_time"]=3
        with self.assertRaisesRegex(ArenaError,"OBSERVATION_UNCERTAINTY_LOST"):
            p42.analyze(source,read_json(DOSSIER))
        source=fixture()
        source["scenarios"][1]["comparison"][1]["diagnostics"][
            "espresso_tasks_blocked_by_group_count"]=1
        with self.assertRaisesRegex(ArenaError,"CLAIMED_ZERO_ESPRESSO_QUEUE_UNTRUE"):
            p42.analyze(source,read_json(DOSSIER))

    def test_rejects_changed_capacity_ratio_or_unbalanced_occupancy(self):
        source=fixture()
        historical=read_json(DOSSIER)
        historical["durations"]["manual_setup_min"]["value"]=0.4
        with self.assertRaisesRegex(ArenaError,"HISTORICAL_90_30_NOT_VERIFIED"):
            p42.analyze(source,historical)
        source=fixture()
        source["scenarios"][0]["comparison"][1]["diagnostics"][
            "espresso_group_busy_fraction_of_capacity_before_cut"]=0.5
        with self.assertRaisesRegex(ArenaError,"OCCUPANCY_MEAN_NOT_CONSISTENT"):
            p42.analyze(source,read_json(DOSSIER))


if __name__=="__main__":
    unittest.main()
