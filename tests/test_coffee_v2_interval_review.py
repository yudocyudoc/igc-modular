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
        "max_dual_endpoint_delta_s": 1.0,
        "agreement_tolerance_reason": "one frame of nominal observation resolution",
        "sampling_design": review.DIRECTED_PLAN,
        "custom_selection_rationale": "fictional narrow targeted windows for unit tests only",
        "review_scope": "EXPLORATORY_DESCRIPTIVE_NO_G3",
        "study_question": "S2_MACHINE_BUSY_LIMIT_VS_S5_MANUAL_WORK_LIMIT",
        "windows": [
            {"id": "w1", "start_s": 0, "end_s": 30,
             "stratum": "ACTIVITY",
             "selection_reason": "predeclared active contrast window",
             "coverage_state": "REVIEWED",
             "reviewer_ids": ["W_REVIEWER_1", "W_REVIEWER_2"],
             "coverage_evidence_ref": "LOCAL_PRIVATE_COVERAGE_ATTESTATION"},
            {"id": "w2", "start_s": 40, "end_s": 70,
             "stratum": "QUIET",
             "selection_reason": "predeclared quiet comparison window",
             "coverage_state": "REVIEWED",
             "reviewer_ids": ["W_REVIEWER_1", "W_REVIEWER_2"],
             "coverage_evidence_ref": "LOCAL_PRIVATE_COVERAGE_ATTESTATION"},
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
        "second_start_s": "2.5",
        "second_end_s": "12.5",
        "second_start_boundary": "OBSERVED",
        "second_end_boundary": "OBSERVED",
    }
    row.update(kw)
    if "start_s" in kw and "second_start_s" not in kw:
        row["second_start_s"] = str(float(row["start_s"]) + 0.5)
    if "end_s" in kw and "second_end_s" not in kw:
        row["second_end_s"] = str(float(row["end_s"]) + 0.5)
    if "start_boundary" in kw and "second_start_boundary" not in kw:
        row["second_start_boundary"] = row["start_boundary"]
        if row["start_boundary"] == "CENSORED":
            row["second_start_s"] = row["start_s"]
    if "end_boundary" in kw and "second_end_boundary" not in kw:
        row["second_end_boundary"] = row["end_boundary"]
        if row["end_boundary"] == "CENSORED":
            row["second_end_s"] = row["end_s"]
    return row


class P07Intervals(unittest.TestCase):
    def test_init_template_no_fabricated_events(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "blank"
            review.create_template(output)
            manifest = json.loads((output / "manifest.template.json").read_text())
            self.assertEqual(manifest["sampling_design"], review.SYSTEMATIC_PLAN)
            self.assertEqual(len(manifest["windows"]), 6)
            self.assertEqual([(w["start_s"], w["end_s"]) for w in manifest["windows"]],
                             [(60, 240), (660, 840), (1260, 1440),
                              (1860, 2040), (2460, 2640), (3060, 3240)])
            self.assertTrue(all(w["coverage_state"] == "PENDING"
                                for w in manifest["windows"]))
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
            self.assertEqual(a["paired_complete_task_candidates"], 1)
            self.assertEqual(a["dual_endpoint_checked"], 2)
            self.assertEqual(a["max_dual_endpoint_delta_s"], 0.5)
            self.assertTrue(result["candidate_intervals_not_yet_model_calibration"])
            self.assertEqual(result["status"],
                             "PAIRED_INTERVAL_CANDIDATES_NEED_IDENTIFIABILITY_REVIEW")
            self.assertEqual(result["reviewed_window_seconds"], 60)

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
            self.assertEqual(empty["aggregate"], {
                "overlap_pairs_manual_machine": 0,
                "overlap_pair_seconds_not_union": 0,
                "same_task_overlap_pairs": 0,
                "paired_complete_task_candidates": 0,
                "unpaired_manual_task_candidates": 0,
                "unpaired_machine_task_candidates": 0,
            })
            self.assertTrue(empty["no_POS_or_reserved_truth_access"])
            self.assertEqual(empty["external_consumption"],
                             {"R2": 0, "OMC": 0, "provider_POST": 0})

    def test_single_phase_cannot_count_as_paired_mechanism_evidence(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            result = review.analyze(manifest, [interval()], media_file=media)
            self.assertEqual(result["status"], "MEASURE_FIRST")
            self.assertEqual(result["aggregate"]["paired_complete_task_candidates"], 0)
            self.assertEqual(result["aggregate"]["unpaired_manual_task_candidates"], 1)
            self.assertTrue(result["no_S2_S5_recommendation"])

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
                ([interval(second_start_s="8.0")],
                 "DUAL_ENDPOINT_DISAGREEMENT"),
                ([interval(second_start_boundary="CENSORED",
                           second_start_s="0")],
                 "DUAL_CENSORING_DISAGREEMENT"),
                ([interval(second_end_s="")],
                 "PARTIAL_SECOND_OBSERVATION"),
                ([interval(review_state="DRAFT", second_end_s="")],
                 "PARTIAL_SECOND_OBSERVATION"),
                ([interval(second_reviewer="REVIEWER_PRIVATE_1")],
                 "DUAL_REVIEW_PROVENANCE"),
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
                ("reserved", {"media_duration_s": 4000, "windows": [
                    {"id": "heldout", "start_s": 3600, "end_s": 3650,
                     "stratum": "UNCERTAIN",
                     "selection_reason": "must not review historical reserve here"}]}),
                ("no_tolerance", {"max_dual_endpoint_delta_s": None}),
                ("no_tolerance_justification", {"agreement_tolerance_reason": ""}),
                ("missing_sampling", {"sampling_design": None}),
                ("bad_sampling", {"sampling_design": "BLINDED_RANDOM"}),
                ("bad_coverage", {"windows": [
                    {**manifest["windows"][0], "coverage_state": "PENDING"}]}),
                ("reviewed_without_dual_custody", {"windows": [
                    {**manifest["windows"][0], "reviewer_ids": []}]}),
                ("invalid_review_scope", {"review_scope": "G3_VALIDATED"}),
            ]
            for key, change in cases:
                with self.subTest(key=key), self.assertRaises(ArenaError):
                    review.analyze({**manifest, **change}, [], media_file=media)

    def test_systematic_plan_is_fixed_and_no_rows_in_pending_windows(self):
        with TemporaryDirectory() as tmp:
            media, manifest = fixture(tmp)
            m = copy.deepcopy(manifest)
            m["sampling_design"] = review.SYSTEMATIC_PLAN
            m["custom_selection_rationale"] = ""
            m["media_duration_s"] = 3600
            m["windows"] = review.planned_windows()
            self.assertEqual(review.validate_manifest(m)["S01"][3], "PENDING")
            first = copy.deepcopy(m)
            first["windows"][0]["start_s"] = 61
            with self.assertRaisesRegex(ArenaError, "SYSTEMATIC_SAMPLING_FRAME_CHANGED"):
                review.validate_manifest(first)
            row = interval(window_id="S01", start_s="70", end_s="100")
            with self.assertRaisesRegex(ArenaError, "INTERVAL_IN_UNREVIEWED_WINDOW"):
                review.analyze(m, [row], media_file=media)
            m["windows"][0]["coverage_state"] = "PARTIAL"
            m["windows"][0]["reviewer_ids"] = ["W_REVIEWER_1"]
            result = review.analyze(m, [row], media_file=media)
            self.assertEqual(result["status"], "MEASURE_FIRST")
            self.assertEqual(result["reviewed_window_seconds"], 0)
            self.assertEqual(result["aggregate"]["not_qualified"], 1)
            self.assertEqual(result["window_coverage_counts"]["PENDING"], 5)
            self.assertEqual(result["window_coverage_counts"]["PARTIAL"], 1)

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
