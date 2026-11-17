"""P43 A fixtures and provenance guards. CI fixture success is NOT video validation."""
from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena import coffee_hydra_episodes_a as a
from arena import coffee_v2_reference as reference
from arena.common import ArenaError, read_json

ROOT=Path(__file__).resolve().parents[1]
VIEW=ROOT/"experiments/coffee_v2/VIDEO2_EPISODE_REVIEW_A.json"
HIST=ROOT/"experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json"


class EpisodeA(unittest.TestCase):
    def data(self):
        return read_json(VIEW)

    def test_known_reviewed_layer_has_four_not_four_completed_cycles(self):
        data=self.data()
        reviews,ops=a.inspect(data)
        self.assertEqual(set(reviews),{"T12","T31","T33","T28"})
        self.assertEqual(len(ops),12)
        self.assertTrue(all(reviews[x]["complete_service_seconds"] is None
                            and reviews[x]["group_released_video_s"] is None
                            for x in reviews))
        self.assertEqual(reviews["T31"]["counter_elapsed_seconds"],29)
        self.assertEqual(reviews["T33"]["counter_elapsed_seconds"],32)
        self.assertEqual(reviews["T12"]["counter_elapsed_seconds"],31)
        self.assertIsNone(reviews["T28"]["counter_elapsed_seconds"])

    def test_all_four_outcome_types_and_source_boundaries(self):
        report=a.check(self.data(),read_json(HIST))
        by={x["question"]:x for x in report["checks"]}
        self.assertEqual(len(by),6)
        self.assertEqual({x["status"] for x in by.values()},
                         {"COMPATIBLE","CONTRADICTED","INDETERMINATE",
                          "NOT_REPRESENTED"})
        self.assertEqual(by["manual_preparation_concurrency_vs_resource_capacity"][
            "status"],"CONTRADICTED")
        self.assertEqual(by["automatic_time_vs_displayed_counter"]["status"],
                         "CONTRADICTED")
        self.assertEqual(by["portafilter_remains_after_timer_stop"][
            "status"],"NOT_REPRESENTED")
        self.assertFalse(report["source_zip_digest_verified_in_this_execution"])
        self.assertEqual(report["real_order_id_links"],0)
        self.assertTrue(report["no_new_reference_simulations"])
        with TemporaryDirectory() as temp:
            a.export(report,Path(temp)/"report")
            self.assertTrue((Path(temp)/"report/A_EPISODE_FINDINGS.md").exists())
            self.assertTrue((Path(temp)/"report/episode-checks.json").exists())

    def test_window_is_not_full_duration_and_unseen_calendar_not_filled(self):
        src=self.data()
        src["selected_operations"][0]["window_is_full_task_duration"]=True
        with self.assertRaisesRegex(ArenaError,"WINDOW_IS_NOT_TASK_DURATION"):
            a.inspect(src)
        src=self.data()
        src["selected_operations"][0]["order_id"]="synthetic_order_x"
        with self.assertRaisesRegex(ArenaError,"WINDOW_IS_NOT_TASK_DURATION"):
            a.inspect(src)

    def test_sampled_concurrence_requires_two_distinct_actors(self):
        src=self.data()
        other=next(x for x in src["selected_operations"] if x["id"]=="E062")
        other["actor"]="B02"
        with self.assertRaisesRegex(ArenaError,"SAMPLE_NOT_IN_DECLARED_WINDOW"):
            a.inspect(src)

    def test_partial_timer_cannot_be_made_full_cycle_or_purge_beverage(self):
        src=self.data()
        next(x for x in src["reviewed_episodes"] if x["id"]=="T31")[
            "complete_service_seconds"]=29
        with self.assertRaisesRegex(ArenaError,"EXTRACTION_MUST_REMAIN_ESTIMATE"):
            a.inspect(src)
        src=self.data()
        next(x for x in src["reviewed_episodes"] if x["id"]=="T28")[
            "counter_elapsed_seconds"]=2
        with self.assertRaisesRegex(ArenaError,"PURGE_NOT_EXCLUSION"):
            a.inspect(src)

    def test_original_p39_pins_cannot_be_silently_overwritten(self):
        src=self.data()
        next(x for x in src["reviewed_episodes"] if x["id"]=="T33")[
            "old_pair"]["counter_s"]=[28,31]
        with self.assertRaisesRegex(ArenaError,"OLD_TIMER_PAIR_CHANGED"):
            a.inspect(src)

    def test_baseline_changed_requires_separate_version_not_fake_contradiction(self):
        d=read_json(HIST)
        d["durations"]["espresso_auto_min"]["value"]=1.4
        # Original historical identity remains pinned, but an alternate
        # VALID candidate dossier must be evaluated instead of rejected.
        with self.assertRaisesRegex(ArenaError,"EXPECTED_UNCHANGED_HISTORICAL"):
            a.historical_baseline_gate(d)
        report=a.check(self.data(),d)
        self.assertEqual(report["model_automatic_extraction_seconds"],84)

    def test_source_byte_claim_requires_exact_original_zip(self):
        with TemporaryDirectory() as td:
            wrong=Path(td)/"not-original.zip"
            wrong.write_bytes(b"not the source")
            with self.assertRaisesRegex(ArenaError,"ZIP_DIGEST_MISMATCH"):
                a.authenticate_original_zip(wrong,self.data())


    def test_astra_reproducer_counter_90_must_change_result_and_text(self):
        src=self.data()
        t33=next(x for x in src["reviewed_episodes"] if x["id"]=="T33")
        t33["counter_elapsed_seconds"]=90
        t33["first_final_seen_video_s"]=180
        t33["final_still_seen_video_s"]=184
        # Partial original 28->32 pair remains unchanged; the fabricated
        # fixture is not offered as historical ZIP validation.
        episodes,ops=a.inspect(src)
        d=read_json(HIST)
        report=a.check(src,d)
        outcome=next(x for x in report["checks"]
                     if x["question"]=="automatic_time_vs_displayed_counter")
        self.assertEqual(outcome["status"],"COMPATIBLE")
        self.assertEqual(outcome["observed"]["estimated_counter_elapsed_s"],90)
        self.assertIn("T33 90s",outcome["explanation"])
        self.assertNotIn("T33 32s",outcome["explanation"])
        self.assertEqual(episodes["T33"]["old_pair"]["counter_s"],[28,32])

    def test_counter_semantic_unresolved_and_uncertainty_band(self):
        source=self.data(); d=read_json(HIST)
        result=a.check(source,d,timer_semantics="not_established")
        item=next(x for x in result["checks"] if
                  x["question"]=="automatic_time_vs_displayed_counter")
        self.assertEqual(item["status"],"INDETERMINATE")
        self.assertIn("not_established",item["model"]["timer_semantics"])
        t33=next(x for x in source["reviewed_episodes"] if x["id"]=="T33")
        t33["counter_elapsed_seconds"]=87 # 3s from assumed 90s
        result=a.check(source,d)
        item=next(x for x in result["checks"] if
                  x["question"]=="automatic_time_vs_displayed_counter")
        self.assertEqual(item["status"],"INDETERMINATE")
        self.assertIn("guard",item["explanation"])
        t33["counter_elapsed_seconds"]=90
        self.assertEqual(next(x for x in a.check(source,d)["checks"]
            if x["question"]=="automatic_time_vs_displayed_counter")["status"],
            "COMPATIBLE")

    def test_explicit_sample_required_overlapping_windows_not_enough(self):
        source=self.data()
        self.assertEqual(len(source["operator_activity_samples"]),2)
        source["operator_activity_samples"]=[]
        report=a.check(source,read_json(HIST))
        found=next(x for x in report["checks"]
                   if x["question"]=="manual_preparation_concurrency_vs_resource_capacity")
        self.assertEqual(found["status"],"INDETERMINATE")
        self.assertIsNone(found["observed"]["required_simultaneous_preparations"])

    def test_resource_capacities_from_candidate_dossier_both_resources_required(self):
        original=read_json(HIST)
        alternative=copy.deepcopy(original)
        alternative["resources"]["barista"]["units"]=2
        with_one_space=a.check(self.data(),alternative)
        verdict=next(x for x in with_one_space["checks"]
                     if x["question"]=="manual_preparation_concurrency_vs_resource_capacity")
        self.assertEqual(verdict["status"],"CONTRADICTED")
        self.assertEqual(verdict["model"]["capacities"]["prep_space"],1)
        alternative["resources"]["prep_space"]["units"]=2
        with_both=a.check(self.data(),alternative)
        verdict=next(x for x in with_both["checks"]
                     if x["question"]=="manual_preparation_concurrency_vs_resource_capacity")
        self.assertEqual(verdict["status"],"COMPATIBLE")
        self.assertEqual(verdict["model"]["concurrent_capacity"],2)
        self.assertEqual(alternative["policy"],"B0")

    def test_post_counter_mounted_state_changes_by_capability(self):
        view=self.data()
        e,o=a.inspect(view)
        model=reference.episode_model_capabilities(read_json(HIST))
        self.assertFalse(model["post_counter_mounted_state_supported"])
        r=a.evaluate_cases(view,e,o,model,1.5)
        self.assertEqual(next(x for x in r if
            x["question"]=="portafilter_remains_after_timer_stop")["status"],
            "NOT_REPRESENTED")
        # Only the simulated descriptor for a hypothetical future engine
        # changes here; this test does not claim the present engine has it.
        candidate=copy.deepcopy(model)
        candidate["post_counter_mounted_state_supported"]=True
        r=a.evaluate_cases(view,e,o,candidate,1.5)
        self.assertEqual(next(x for x in r if
            x["question"]=="portafilter_remains_after_timer_stop")["status"],
            "COMPATIBLE")
        e["T31"]["visual_state_note"]="unknown"
        r=a.evaluate_cases(view,e,o,candidate,1.5)
        self.assertEqual(next(x for x in r if
            x["question"]=="portafilter_remains_after_timer_stop")["status"],
            "INDETERMINATE")

    def test_overlap_different_resources_from_real_engine_descriptor(self):
        view=self.data(); e,o=a.inspect(view)
        caps=reference.episode_model_capabilities(read_json(HIST))
        self.assertEqual(caps["stage_requirements"]["espresso_auto"],
                         ["espresso_group"])
        outcomes=a.evaluate_cases(view,e,o,caps,1.5)
        self.assertEqual(next(x for x in outcomes if
            x["question"]=="machine_vs_operator_overlap")["status"],
            "COMPATIBLE")
        caps["stage_requirements"]["espresso_auto"]=["espresso_group","barista"]
        outcomes=a.evaluate_cases(view,e,o,caps,1.5)
        self.assertEqual(next(x for x in outcomes if
            x["question"]=="machine_vs_operator_overlap")["status"],
            "INDETERMINATE")

    def test_purge_exclusion_generated_from_source_classification(self):
        view=self.data(); e,o=a.inspect(view)
        caps=reference.episode_model_capabilities(read_json(HIST))
        e["T28"]["type"]="indeterminate_activation"
        outcomes=a.evaluate_cases(view,e,o,caps,1.5)
        event=next(x for x in outcomes if
            x["question"]=="probable_purge_exclusion")
        self.assertEqual(event["status"],"INDETERMINATE")
        self.assertEqual(event["observed"]["excluded_as_probable_purge"],[])


if __name__=="__main__":
    unittest.main()
