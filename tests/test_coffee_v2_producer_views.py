"""V2.1 P02/P05/P12: fictional corpus views, protected split and source lineage."""
import csv
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from arena.common import ArenaError
from arena import coffee_v2_synthetic_corpus as corpus
from arena import coffee_v2_producer_views as views
from test_coffee_v2_synthetic_corpus import synthetic_archive


KEY = b"this-is-a-private-fixture-key-not-for-real-data-123"
ORIGINAL_AUDIT = corpus.audit


def prepare(tmp, raw=None):
    root = Path(tmp)
    raw = synthetic_archive() if raw is None else raw
    src = root/"fictitious-private-source.zip"
    src.write_bytes(raw)
    key = KEY
    audited = ORIGINAL_AUDIT(
        src, key=key, expected_sha=hashlib.sha256(raw).hexdigest()
    )
    private = root/"custody"
    first_review = root/"census-public-aggregates"
    corpus.export(audited, private_out=private,
                  public_out=first_review, key=key)
    return src, private, first_review, audited


def build_fixture(src, private):
    # The real tool requires the pinned real SHA; fixtures get an explicit
    # override ONLY in this test, never in operational code.
    def fake_audit(source, *, key):
        return ORIGINAL_AUDIT(
            source, key=key,
            expected_sha=hashlib.sha256(Path(source).read_bytes()).hexdigest()
        )
    with patch.object(views.corpus, "audit", side_effect=fake_audit):
        return views.build(src, private)


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class ProducerViewsTests(TestCase):
    def test_no_evaluation_and_all_allowed_events_items_bins(self):
        with TemporaryDirectory() as tmp:
            src, private, _, audited = prepare(tmp)
            result = build_fixture(src, private)
            self.assertEqual(result["summary"]["allowed_weekly_cases"], 45)
            self.assertEqual(result["summary"]["reserved_weekly_cases_not_released"], 9)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-case-index.csv"], 45)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-pos-observations.csv"], 45)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-line-items.csv"], 45)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-paid-bins-5min.csv"], 45*7*21)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-video-proxy-minute.csv"], 60)
            self.assertEqual(result["plan"]["weekly_counts"],
                             {"CONSTRUCTION":36, "DEVELOPMENT":9,
                              "EVALUATION":9})
            self.assertFalse(result["plan"]["science_lock_or_G3_created"])
            self.assertTrue(result["plan"]["evaluation_truth_not_accessed"])
            self.assertEqual(result["summary"]["exclusion_counts"][
                "evaluation_pos_never_released"], 9)
            self.assertEqual(result["summary"]["visual_proxy_source_minute_rows"],104)
            self.assertEqual(result["summary"]["visual_proxy_reserved_minutes_not_released"],44)
            allowed = {r["opaque_case_id"] for r in audited["cases"]
                       if r["partition"] != "EVALUATION"}
            eval_cases = {r["opaque_case_id"] for r in audited["cases"]
                          if r["partition"] == "EVALUATION"}
            final_out = Path(tmp)/"producer-released"
            views.export(result, final_out)
            self.assertEqual(len(list(final_out.iterdir())), 8)
            manifest = json.loads((final_out/"producer-manifest.json").read_text())
            self.assertEqual(manifest["evaluation_scenario_rows_released"], 0)
            self.assertEqual(manifest["truth_files_opened_as_rows"], 0)
            for name, sha in manifest["output_sha256"].items():
                self.assertEqual(sha, "sha256:"+corpus.sha_file(final_out/name))
            index = read_csv(final_out/"producer-case-index.csv")
            self.assertEqual({r["case_id"] for r in index}, allowed)
            self.assertFalse(eval_cases & {r["case_id"] for r in index})
            detail = read_csv(final_out/"producer-pos-observations.csv")
            self.assertEqual({r["pos_event_id"] for r in detail},
                             {r["pos_event_id"] for r in
                              read_csv(final_out/"producer-line-items.csv")})
            for r in detail:
                self.assertEqual(r["kind"], "sale")
                self.assertEqual(r["source_kind"],
                    "SYNTHETIC_POS_PAYMENT_NOT_ARRIVAL_OR_PICKUP")
            full_output = "\n".join(
                p.read_text() for p in final_out.iterdir() if p.is_file()
            )
            for secret in ("PRIVATE_regime_", "PRIVATE_RECORD_",
                           "PRIVATE_ORDER_", "PRIVATE_LINE_",
                           "SUPER_PRIVATE_TRUTH_CANARY", "710000",
                           "days_6_7_load_factor_assumption", "scenario_id",
                           "TEST_CUSTODIAN", "this-is-a-private-fixture-key"):
                self.assertNotIn(secret, full_output)
            for r in read_csv(final_out/"producer-paid-bins-5min.csv"):
                self.assertEqual(r["coverage_status"],
                                 "COMPLETE_SYNTHETIC_POS_WINDOW")
                self.assertLess(float(r["bin_start_min"]),
                                float(r["bin_end_min_exclusive"]))
                self.assertLessEqual(float(r["bin_end_min_exclusive"]),104)
            with self.assertRaisesRegex(ArenaError,"OUTPUT_ALREADY_EXISTS"):
                views.export(result, final_out)

    def test_signed_refund_is_financial_not_new_beverage(self):
        self.assertEqual(views.money("-65", "REFUND_AMOUNT", signed=True), "-65")
        self.assertEqual(views.money("65", "REFUNDED_TOTAL"), "65")
        with self.assertRaisesRegex(ArenaError, "BAD_NONNEGATIVE_AMOUNT"):
            views.money("-65", "NONNEGATIVE_AMOUNT")

    def test_cannot_reroll_private_split_or_read_wrong_catalog(self):
        with TemporaryDirectory() as tmp:
            src, private, _, _ = prepare(tmp)
            with closing(sqlite3.connect(private/"catalog.sqlite")) as conn:
                conn.execute("UPDATE synthetic_cases SET partition='EVALUATION' "
                             "WHERE rowid=(SELECT MIN(rowid) FROM synthetic_cases "
                             "WHERE partition='CONSTRUCTION')")
                conn.commit()
            with self.assertRaisesRegex(ArenaError, "PRIVATE_CATALOG_PARTITION_CHANGED"):
                build_fixture(src, private)

    def test_historical_v1_cut_ignored_in_other_cases(self):
        with TemporaryDirectory() as tmp:
            src, private, _, audited = prepare(tmp)
            # The old V1 case is represented only by a private
            # scenario/rep/day tuple, never by output metadata.
            first = next(
                x for x in audited["cases"] if x["partition"] != "EVALUATION"
            )
            with patch.object(views, "HISTORICAL_V1", {
                    "scenario_id": first["scenario_private"],
                    "replication": first["replication_private"],
                    "day_of_week": 1}), patch.object(
                    views, "V1_CONSTRUCTION_END", 1.0):
                result = build_fixture(src, private)
            self.assertEqual(result["summary"]["exclusion_counts"][
                "historical_v1_reserved_pos_excluded"], 1)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-pos-observations.csv"], 44)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-line-items.csv"], 44)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-case-index.csv"], 45)
            self.assertEqual(result["summary"]["released_rows"][
                "producer-paid-bins-5min.csv"], 45*7*21)
            reserved_bins = [row for row in
                             result["tables"]["producer-paid-bins-5min.csv"]
                             if row[-1] == "V1_RESERVED_NOT_RELEASED"]
            self.assertEqual(len(reserved_bins), 20)
            self.assertTrue(all(row[5] == "" and row[6] == "" and row[7] == ""
                                for row in reserved_bins))

    def test_failed_key_and_wrong_zip_hash_do_not_generate_release(self):
        with TemporaryDirectory() as tmp:
            src, private, _, audited = prepare(tmp)
            key_path = private/"custody-key.bin"
            key_path.write_bytes(b"other-valid-private-key-12345678901234567890")
            with self.assertRaisesRegex(ArenaError,"CATALOG_SOURCE_OR_KEY_MISMATCH"):
                build_fixture(src, private)
            key_path.write_bytes(KEY)
            # New/unknown bytes are rejected by real admission.
            with self.assertRaisesRegex(ArenaError, "ZIP_SHA256_MISMATCH"):
                views.build(src, private)
            result = build_fixture(src, private)
            self.assertEqual(result["plan"]["partition_policy"],
                             corpus.PARTITION_POLICY)


if __name__ == "__main__":
    import unittest
    unittest.main()
