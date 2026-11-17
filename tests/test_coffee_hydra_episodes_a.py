"""P43 A fixtures and provenance guards. CI fixture success is NOT video validation."""
from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena import coffee_hydra_episodes_a as a
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
        self.assertEqual(by["two_operators_vs_single_global_barista"][
            "status"],"CONTRADICTED")
        self.assertEqual(by["counter_90s_as_timer_elapsed"]["status"],
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
        with self.assertRaisesRegex(ArenaError,"OPERATOR_SAMPLED_EVIDENCE"):
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
        # A is scoped to the original historical B0, not a hypothetical B.
        with self.assertRaisesRegex(ArenaError,"EXPECTED_UNCHANGED_HISTORICAL"):
            a.check(self.data(),d)

    def test_source_byte_claim_requires_exact_original_zip(self):
        with TemporaryDirectory() as td:
            wrong=Path(td)/"not-original.zip"
            wrong.write_bytes(b"not the source")
            with self.assertRaisesRegex(ArenaError,"ZIP_DIGEST_MISMATCH"):
                a.authenticate_original_zip(wrong,self.data())


if __name__=="__main__":
    unittest.main()
