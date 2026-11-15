"""Offline P07 contract tests. Only fabricated bytes, never real video or truth."""
import copy
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError
from arena import coffee_v2_interval_review as review


def fixture(tmp):
    video = Path(tmp) / "dummy-video.bin"
    video.write_bytes(b"FICTIONAL_OFFLINE_MEDIA_NOT_REAL_COFFEE_VIDEO")
    manifest = {
        "schema": review.SCHEMA,
        "clock": review.CLOCK,
        "media_sha256": review.sha_file(video),
        "media_duration_s": 90,
        "review_scope": "EXPLORATORY_DESCRIPTIVE_NO_G3",
        "study_question": "S2_MACHINE_BUSY_LIMIT_VS_S5_MANUAL_WORK_LIMIT",
        "windows": [
            {"id": "w1", "start_s": 0, "end_s": 30,
             "stratum": "ACTIVITY",
             "selection_reason": "predeclared active contrast window"},
            {"id": "w2", "start_s": 40, "end_s": 70,
             "stratum": "QUIET",
             "selection_reason": "predeclared quiet comparison window"},
        ],
    }
    return video, manifest


def interval(event_id="EVENT_PRIVATE_1", phase="MANUAL_ACTIVE", **kw):
    row = {
        "event_id": event_id,
        "window_id": "w1",
        "task_id": "TASK_PRIVATE_1",
        "resource_id": "RESOURCE_PRIVATE_A" if phase == "MANUAL_ACTIVE"
                       else "RESOURCE_PRIVATE_MACHINE",
        "resource_type": "OPERATOR" if phase == "MANUAL_ACTIVE" else "MACHINE",
        "phase": phase,
        "start_s": "2",
        "end_s": "12",
        "start_boundary": "OBSERVED",
        "end_boundary": "OBSERVED",
        "source": "VIDEO_DIRECT",
        "review_state": "DUAL_CONFIRMED",
        "primary_reviewer": "REVIEWER_PRIVATE_1",
        "second_reviewer": "REVIEWER_PRIVATE_2",
        "confidence": "HIGH",
        "evidence_ref": "FRAME_PATH_PRIVATE_WITH_ID",
    }
    row.update(kw)
    return row


class P07Intervals(unittest.TestCase):
    def test_init_template_no_fabricated_events(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "blank"
            review.create_template(output)
            manifest = json.loads((output / "manifest.template.json").read_text())
            self.assertEqual(manifest["windows"], [])
            self.assertEqual(manifest["media_sha256"],
                             "REPLACE_WITH_SHA256_OF_ORIGINAL_MEDIA")
            with (output / "intervals.template.csv").open() as f:
                self.assertEqual(list(csv.reader(f)), [list(review.FIELDS)])
            with self.assertRaisesRegex(ArenaError, "OUTPUT_EXISTS"):
                review.create_template(output)

    def test_overlap_is_pairwise_and_never_equivalent_to_capacity(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            rows = [
                interval(),
                interval("EVENT_PRIVATE_2", "MACHINE_BUSY", start_s="5", end_s="20"),
            ]
            result = review.analyze(manifest, rows, media_file=media)
            a = result["aggregate"]
            self.assertEqual(a["qualified_MANUAL_ACTIVE_seconds"], 10.0)
            self.assertEqual(a["qualified_MACHINE_BUSY_seconds"], 15.0)
            self.assertEqual(a["overlap_pairs_manual_machine"], 1)
            self.assertEqual(a["overlap_pair_seconds_not_union"], 7.0)
            self.assertEqual(a["same_task_overlap_pairs"], 1)
            self.assertEqual(result["status"],
                             "INTERVAL_CANDIDATES_NEED_IDENTIFIABILITY_REVIEW")
            self.assertTrue(result["service_capacity_not_identified"])
            self.assertTrue(result["no_S2_S5_recommendation"])
            out = Path(tmp) / "result"
            review.export(result, out)
            contents = "\n".join(f.read_text() for f in out.iterdir())
            for token in ("EVENT_PRIVATE_", "TASK_PRIVATE_",
                          "RESOURCE_PRIVATE_", "REVIEWER_PRIVATE_", "FRAME_PATH_PRIVATE"):
                self.assertNotIn(token, contents)
            self.assertIn("No se identifica", contents)
            with self.assertRaisesRegex(ArenaError, "OUTPUT_EXISTS"):
                review.export(result, out)

    def test_no_video_no_verified_claims_no_truth(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            with self.assertRaisesRegex(ArenaError, "ORIGINAL_VIDEO_FILE_REQUIRED"):
                review.analyze(manifest, [interval()], media_file=None)
            with self.assertRaisesRegex(ArenaError, "MEDIA_HASH_MISMATCH"):
                broken = copy.deepcopy(manifest)
                broken["media_sha256"] = "sha256:" + "0" * 64
                review.analyze(broken, [interval()], media_file=media)
            empty = review.analyze(manifest, [], media_file=media)
            self.assertEqual(empty["status"], "MEASURE_FIRST")
            self.assertEqual(empty["aggregate"], {})
            self.assertTrue(empty["no_POS_or_reserved_truth_access"])
            self.assertEqual(empty["external_consumption"],
                             {"R2": 0, "OMC": 0, "provider_POST": 0})

    def test_censored_legacy_and_disputed_are_not_qualified(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            rows = [
                interval(start_s="0", start_boundary="CENSORED"),
                interval("EVENT_PRIVATE_2", "MACHINE_BUSY",
                         source="LEGACY_ANNOTATION", review_state="DRAFT",
                         primary_reviewer="legacy", second_reviewer="",
                         evidence_ref=""),
                interval("EVENT_PRIVATE_3", phase="MANUAL_ACTIVE",
                         start_s="16", end_s="20",
                         review_state="DISPUTED", confidence="LOW"),
            ]
            result = review.analyze(manifest, rows, media_file=media)
            self.assertEqual(result["status"], "MEASURE_FIRST")
            self.assertEqual(result["aggregate"]["not_qualified"], 3)
            self.assertEqual(result["aggregate"]["censored_intervals"], 1)
            self.assertNotIn("qualified_MANUAL_ACTIVE_seconds", result["aggregate"])

    def test_detects_conflicts_wrong_censor_and_improper_dual_review(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            cases = [
                ([interval(), interval("EV2", start_s="7", end_s="15")],
                 "EXCLUSIVE_RESOURCE_OVERLAP"),
                ([interval(start_s="2", start_boundary="CENSORED")],
                 "LEFT_CENSOR_BOUNDARY"),
                ([interval(end_s="29", end_boundary="CENSORED")],
                 "RIGHT_CENSOR_BOUNDARY"),
                ([interval(second_reviewer="REVIEWER_PRIVATE_1")],
                 "DUAL_REVIEW_PROVENANCE"),
                ([interval(source="LEGACY_ANNOTATION")],
                 "DUAL_REVIEW_PROVENANCE"),
                ([interval("X", "MACHINE_BUSY", resource_type="OPERATOR")],
                 "INVALID_INTERVAL_CONTRACT"),
                ([interval(), interval()],
                 "DUPLICATE_EVENT_ID"),
                ([interval(window_id="w3")],
                 "INVALID_INTERVAL_CONTRACT"),
            ]
            for rows, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(
                        ArenaError, message):
                    review.analyze(manifest, rows, media_file=media)

    def test_manifest_rejects_overlap_future_and_missing_strata_provenance(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            cases = [
                ("overlap", {"windows": [
                    manifest["windows"][0],
                    {**manifest["windows"][1], "start_s": 29}]}),
                ("end", {"windows": [
                    {**manifest["windows"][0], "end_s": 91}]}),
                ("clock", {"clock": "POS_SYNTHETIC_MINUTES"}),
                ("no_windows", {"windows": []}),
                ("invalid_review_scope", {"review_scope": "G3_VALIDATED"}),
            ]
            for key, change in cases:
                with self.subTest(key=key), self.assertRaises(ArenaError):
                    review.analyze({**manifest, **change}, [], media_file=media)

    def test_csv_strict_fields_and_no_extra_columns(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "intervals.csv"
            with p.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=review.FIELDS)
                writer.writeheader()
                writer.writerow(interval())
            rows = review.parse_rows(p)
            self.assertEqual(len(rows), 1)
            p.write_text("event_id,secret_truth\nNOT_ALLOWED,1\n")
            with self.assertRaisesRegex(ArenaError, "CSV_COLUMNS"):
                review.parse_rows(p)


if __name__ == "__main__":
    unittest.main()
