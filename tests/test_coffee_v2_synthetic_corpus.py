"""P01/P02 synthetic corpus admission: all fixtures invented, no private ZIP in CI."""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
import zipfile

from arena.common import ArenaError
from arena import coffee_v2_synthetic_corpus as corpus


def csv_bytes(columns, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def synthetic_archive(*, duplicate_pos=False, bad_hash=False,
                      extra_member=False, broken_pos_origin=False):
    root = corpus.ROOT
    all_scenarios = [f"PRIVATE_regime_{i:02d}_hidden_factors" for i in range(18)]
    summary = []
    pos = []
    lines = []
    for i, scenario in enumerate(all_scenarios):
        for rep in range(1, 4):
            summary.append({
                "scenario_id": scenario, "replication": rep,
                "seed": 710000 + 100*i + rep, "synthetic": "True",
                "net_profit_mxn": "",
            })
            rid = f"PRIVATE_RECORD_{i}_{rep}"
            pos.append({
                "scenario_id": scenario, "replication": rep, "day_of_week": 1,
                "pos_record_id": rid if not duplicate_pos else "DUP" if i == 0 else rid,
                "order_id": f"PRIVATE_ORDER_{i}_{rep}",
                "pos_record_type": "sale", "sale_status": "paid_synthetic",
                "synthetic": "True", "source_class":
                    "bad_source_class" if broken_pos_origin else "synthetic_pos_view",
                "timestamp_min_from_peak_start": "1.2",
            })
            lines.append({
                "scenario_id": scenario, "replication": rep, "day_of_week": 1,
                "pos_record_id": rid if not duplicate_pos else "DUP" if i == 0 else rid,
                "order_id": f"PRIVATE_ORDER_{i}_{rep}",
                "pos_line_id": f"PRIVATE_LINE_{i}_{rep}",
                "quantity": 1, "synthetic": "True",
                "source_class": "synthetic_pos_line_item",
            })
    if duplicate_pos:
        pos.append(dict(pos[0]))
    profile = [
        {"minute_from_peak_start": i, "sample_seconds": 60,
         "source_class": "video_customer_presence_proxy_not_arrival_count",
         "synthetic": "False"}
        for i in range(104)
    ]
    payloads = {
        "resumen_escenarios.csv":
            csv_bytes(["scenario_id", "replication", "seed", "synthetic",
                       "net_profit_mxn"], summary),
        "pos_observed.csv":
            csv_bytes(["scenario_id", "replication", "day_of_week",
                       "pos_record_id", "order_id", "pos_record_type",
                       "sale_status", "synthetic", "source_class",
                       "timestamp_min_from_peak_start"], pos),
        "pos_line_items.csv":
            csv_bytes(["scenario_id", "replication", "day_of_week",
                       "pos_record_id", "order_id", "pos_line_id", "quantity",
                       "synthetic", "source_class"], lines),
        "perfil_carga_video.csv":
            csv_bytes(["minute_from_peak_start", "sample_seconds",
                       "source_class", "synthetic"], profile),
    }
    for name in corpus.FILES:
        if name not in payloads:
            payloads[name] = (
                b'SUPER_PRIVATE_TRUTH_CANARY_889988\n' if "_truth." in name
                else b'NOT_SEMANTICALLY_PARSED_IN_THIS_PR\n')
    config = {
        "schema": "cafeteria.synthetic-scenario/1",
        "interpretation": {"parameters_are_observations": False,
                           "generated_records_are_synthetic": True},
        "source": {"synthetic_peak_window_minutes": 103.23706667},
        "design": {
            "peak_arrivals_per_minute_scenarios": {"a": 0.2, "b": 0.4, "c": 0.65},
            "offpeak_load_factor_scenarios": {"a": .25, "b": .5, "c": .75},
            "queue_abandonment_patience_scenarios_minutes": {"a": [1],
                                                             "b": [2]},
            "replications_per_combination": 3,
        }
    }
    raw_config = json.dumps(config).encode()
    m = {
        "schema": corpus.MANIFEST_SCHEMA,
        "config_sha256": hashlib.sha256(raw_config).hexdigest(),
        "scenario_combinations": 18,
        "replications_per_combination": 3,
        "weekly_runs": 54,
        "video_proxy_minutes": 104,
        "pos_rows_synthetic": len(pos),
        "pos_line_items_synthetic": len(lines),
        "video_receipt_linkage_hypothesis_rows": 4,
        "video_anchor_pos_imputation_rows": 300,
        "video_anchor_pos_imputation_line_rows": 400,
        "outputs": {
            name: {"sha256": hashlib.sha256(payloads[name]).hexdigest(),
                   "bytes": len(payloads[name])}
            for name in corpus.FILES
        },
    }
    if bad_hash:
        m["outputs"]["eventos_truth.csv"]["sha256"] = "0" * 64
    contents = {corpus.MANIFEST: json.dumps(m).encode(),
                corpus.CONFIG: raw_config,
                corpus.ROOT+"LEEME.md": b"FICTIONAL TEST SOURCE",
                corpus.ROOT+"generar_escenarios.py": b"print('never executed')",
                **{corpus.OUT+k: v for k, v in payloads.items()}}
    if extra_member:
        contents["secret_new_generator_truth.json"] = b"LEAK"
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in contents.items():
            z.writestr(name, data)
    return buff.getvalue()


class SyntheticCorpusCensusTests(TestCase):
    def audit(self, tmp, **kwargs):
        raw = synthetic_archive(**kwargs)
        path = Path(tmp) / "fixture.zip"
        path.write_bytes(raw)
        result = corpus.audit(path, expected_sha=hashlib.sha256(raw).hexdigest(),
                              key=b"TEST_CUSTODIAN_KEY_NONPUBLIC_32_BYTE_LONG")
        return path, result

    def test_full_census_private_sqlite_and_aggregate_export(self):
        with TemporaryDirectory() as tmp:
            path, result = self.audit(tmp)
            pub = result["public"]
            self.assertEqual(pub["synthetic_weekly_runs"], 54)
            self.assertEqual(pub["scenario_conditions"], 18)
            self.assertEqual(pub["pos_synthetic_rows"], 54)
            self.assertEqual(pub["pos_line_item_rows"], 54)
            self.assertEqual(pub["video_proxy_minute_rows"], 104)
            self.assertEqual(pub["output_member_sha256_verified"], 19)
            self.assertEqual(pub["partition_case_counts"],
                             {"CONSTRUCTION": 36, "DEVELOPMENT": 9,
                              "EVALUATION": 9})
            self.assertTrue(pub["truth_bytes_hashed_but_truth_rows_not_interpreted"])
            self.assertFalse(pub["source_has_distinct_B0_S1_to_S5_treatments"])
            groups = {}
            for entry in result["cases"]:
                groups.setdefault(entry["scenario_private"], set()).add(
                    entry["partition"])
            self.assertEqual(len(groups), 18)
            self.assertTrue(all(len(v) == 1 for v in groups.values()))
            private_out = Path(tmp) / "custody"
            public_out = Path(tmp) / "released"
            corpus.export(result, private_out=private_out,
                          public_out=public_out,
                          key=b"TEST_CUSTODIAN_KEY_NONPUBLIC_32_BYTE_LONG")
            with sqlite3.connect(private_out / "catalog.sqlite") as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM synthetic_cases").fetchone()[0], 54)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM source_files").fetchone()[0], 19)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(DISTINCT scenario_private) "
                    "FROM synthetic_cases WHERE partition='EVALUATION'").fetchone()[0], 3)
            body = "\n".join(f.read_text() for f in public_out.iterdir())
            for forbidden in ("PRIVATE_regime_", "PRIVATE_ORDER_", "PRIVATE_RECORD_",
                              "PRIVATE_LINE_", "SUPER_PRIVATE_TRUTH_CANARY",
                              "TEST_CUSTODIAN_KEY_NONPUBLIC", "710000"):
                self.assertNotIn(forbidden, body)
            self.assertEqual(len(list(public_out.iterdir())), 4)
            with self.assertRaisesRegex(ArenaError, "PRIVATE_PUBLIC_OUTPUT_COLLISION"):
                corpus.export(result, private_out=private_out,
                              public_out=public_out, key=b"X"*32)

    def test_zip_pin_manifest_private_truth_and_bad_provenance_fail_closed(self):
        with TemporaryDirectory() as tmp:
            raw = synthetic_archive()
            path = Path(tmp) / "fixture.zip"
            path.write_bytes(raw)
            with self.assertRaisesRegex(ArenaError, "ZIP_SHA256_MISMATCH"):
                corpus.audit(path, key=b"0"*32)
        for key, options, message in [
            ("hash", {"bad_hash": True}, "OUTPUT_SHA256_MISMATCH"),
            ("unexpected", {"extra_member": True}, "ZIP_MEMBERS_UNEXPECTED"),
            ("POS", {"broken_pos_origin": True}, "POS_CASE_OR_PROVENANCE"),
            ("duplicate", {"duplicate_pos": True}, "DUPLICATE_POS_ID"),
        ]:
            with self.subTest(key=key), TemporaryDirectory() as tmp:
                raw = synthetic_archive(**options)
                p = Path(tmp) / "file.zip"
                p.write_bytes(raw)
                with self.assertRaisesRegex(ArenaError, message):
                    corpus.audit(p, expected_sha=hashlib.sha256(raw).hexdigest(),
                                 key=b"1"*32)

    def test_partition_stable_but_key_dependent_and_no_replicate_leak(self):
        scenarios = {f"private_scenario_{i}" for i in range(18)}
        a = corpus.allocate(scenarios, b"key-one-private-12345678901234567890")
        b = corpus.allocate(scenarios, b"key-one-private-12345678901234567890")
        c = corpus.allocate(scenarios, b"key-two-private-12345678901234567890")
        self.assertEqual(a, b)
        self.assertEqual(Counter(a.values()),
                         Counter({"CONSTRUCTION": 12, "DEVELOPMENT": 3,
                                  "EVALUATION": 3}))
        self.assertNotEqual(a, c)
        with self.assertRaisesRegex(ArenaError, "PRIVATE_KEY_REQUIRED"):
            corpus.allocate(scenarios, b"short")


if __name__ == "__main__":
    import unittest
    unittest.main()
