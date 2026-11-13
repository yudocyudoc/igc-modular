"""Offline admission tests: no vendor source, solver, network, or provider required."""
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from arena.coffee_peak import CoffeePeakCapacityV1, _load_package, _build_public, ROOT, REQUIRED_OUTPUTS
from arena.common import ArenaError


def tab(headers, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def make_zip(path, *, tamper=False, mutate=None):
    summary = [{"scenario_id": "case-a", "replication": "1", "synthetic": "True", "seed": "123"}]
    pos = []
    lines = []
    for time in (10, 80):
        order = f"P{time}"
        pos.append({"scenario_id": "case-a", "replication": "1", "day_of_week": "1",
                    "pos_record_id": order, "order_id": order,
                    "timestamp_min_from_peak_start": str(time), "archetype": "test",
                    "beverage_count": "1", "customer_count_synthetic": "1",
                    "pos_record_type": "sale", "sale_status": "paid_synthetic", "amount_mxn": "45",
                    "refund_amount_mxn": "0", "currency_assumption": "MXN", "synthetic": "True",
                    "source_class": "synthetic_pos_view"})
        lines.append({"scenario_id": "case-a", "replication": "1", "day_of_week": "1",
                      "pos_record_id": order, "order_id": order, "pos_line_id": order+"-L1",
                      "timestamp_min_from_peak_start": str(time), "synthetic_sku": "SKU",
                      "item_archetype": "test", "quantity": "1", "synthetic": "True",
                      "source_class": "synthetic_pos_line_item"})
    profile = [{"minute_from_peak_start": str(i), "sample_seconds": "60",
                "mean_public_customer_tracklets_per_second": "1.0",
                "mean_manual_queue_marks_per_second": "0.1",
                "source_class": "video_customer_presence_proxy_not_arrival_count", "synthetic": "False"}
               for i in (0, 59, 60)]
    files = {ROOT+name: tab(list(rows[0]), rows) for name, rows in (
        ("resumen_escenarios.csv", summary), ("pos_observed.csv", pos),
        ("pos_line_items.csv", lines), ("perfil_carga_video.csv", profile))}
    sources = {"source_observation_csv_sha256": "video2/completo_v1/eventos_consolidados.csv",
               "source_person_tracks_csv_sha256": "video2/sintetico_pico_v1/revision_fila/personas_clasificadas_1s.csv",
               "source_video_receipt_master_sha256": "video2/maestro_15m_v2/eventos_maestro.csv",
               "config_sha256": "video2/sintetico_pico_v1/parametros_escenarios.json"}
    for p in sources.values():
        files[p] = b"source fixture\n"
    for name in REQUIRED_OUTPUTS:
        files.setdefault(ROOT + name, b"SECRET-FUTURE-TRUTH\n" if "truth" in name else b"fixture-output\n")
    if mutate is not None:
        mutate(files, sources)
    inner = {"schema": "cafeteria.synthetic-output-manifest/2",
             "outputs": {name.removeprefix(ROOT): {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                         for name, data in files.items() if name.removeprefix(ROOT) in REQUIRED_OUTPUTS}}
    inner.update({key: hashlib.sha256(files[source]).hexdigest()
                  for key, source in sources.items() if source in files})
    files[ROOT+"manifest.json"] = json.dumps(inner).encode()
    registered = {p: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                  for p,data in files.items()}
    if tamper:
        files[ROOT+"pos_observed.csv"] += b"X"
    files["MANIFIESTO_PAQUETE.json"] = json.dumps({"schema": "cafeteria.pilot-package/1", "files": registered}).encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CoffeePeakTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"package.zip"
        self.sha = make_zip(self.path)
        self.config = {"id": "fixture", "protocol": "coffee_peak_capacity_v1", "backend": "fixture",
                       "budget": {"omc": 0, "provider_posts": 0, "workflow": 0},
                       "source": {"path": str(self.path), "sha256": self.sha},
                       "selection": {"scenario_id": "case-a", "replication": 1, "day_of_week": 1},
                       "construction_end_min": 60.0, "window_end_min": 103.237}

    def test_validates_package_and_selects_only_public_before_cut(self):
        zf, _ = _load_package(self.path, self.sha)
        with zf:
            view = _build_public(zf, self.config, self.sha)
        self.assertEqual(len(view["pos_records"]), 1)
        self.assertEqual(len(view["pos_line_items"]), 1)
        self.assertEqual(len(view["video_proxy"]), 2)
        self.assertTrue(re.fullmatch(r"pos-[0-9a-f]{32}", view["pos_records"][0]["pos_record_id"]))
        self.assertTrue(re.fullmatch(r"ord-[0-9a-f]{32}", view["pos_records"][0]["order_id"]))
        self.assertEqual(view["pos_line_items"][0]["order_id"], view["pos_records"][0]["order_id"])
        self.assertEqual(view["pos_line_items"][0]["pos_record_id"], view["pos_records"][0]["pos_record_id"])
        self.assertTrue(re.fullmatch(r"line-[0-9a-f]{32}", view["pos_line_items"][0]["pos_line_id"]))
        self.assertNotIn("P10", json.dumps(view))
        self.assertNotIn("P80", json.dumps(view))
        self.assertNotIn("SECRET", json.dumps(view))
        self.assertNotIn("seed", json.dumps(view))
        self.assertEqual(view["semantics"]["sale"], "POS payment, not a delivery")

    def test_public_ids_do_not_expose_missing_arrival_ordinals(self):
        # With paid P0003 and P0005, the hidden arriving P0004 is NOT inferable
        # from public IDs; source linkage and ordering stay importer-only.
        def gap(files, sources):
            for name in ("pos_observed.csv", "pos_line_items.csv"):
                key = ROOT + name
                text = files[key].decode()
                files[key] = text.replace("P10", "P0003").replace("P80", "P0005").encode()
        self.sha = make_zip(self.path, mutate=gap)
        zf, _ = _load_package(self.path, self.sha)
        with zf:
            view = _build_public(zf, self.config, self.sha)
        serialized = json.dumps(view)
        for secret in ("P0003", "P0004", "P0005"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(len(view["pos_records"]), 1)
        self.assertEqual(view["pos_records"][0]["order_id"], view["pos_line_items"][0]["order_id"])

    def test_refund_and_line_items_keep_join_after_pseudonymization(self):
        def add_refund(files, sources):
            key = ROOT + "pos_observed.csv"
            reader = csv.DictReader(io.StringIO(files[key].decode()))
            original = list(reader)
            refund = dict(original[0], pos_record_id="RF-P10", pos_record_type="refund",
                          timestamp_min_from_peak_start="20", sale_status="refunded_synthetic",
                          amount_mxn="-45", refund_amount_mxn="45")
            original.append(refund)
            files[key] = tab(reader.fieldnames, original)
        self.sha = make_zip(self.path, mutate=add_refund)
        zf, _ = _load_package(self.path, self.sha)
        with zf:
            view = _build_public(zf, self.config, self.sha)
        self.assertEqual(len(view["pos_records"]), 2)
        sale, refund = view["pos_records"]
        self.assertEqual(sale["order_id"], refund["order_id"])
        self.assertNotEqual(sale["pos_record_id"], refund["pos_record_id"])
        self.assertEqual(view["pos_line_items"][0]["pos_record_id"], sale["pos_record_id"])

    def test_sources_missing_with_consistent_rehashed_manifest_are_rejected(self):
        def remove_sources(files, sources):
            for path in sources.values():
                files.pop(path)
        new_sha = make_zip(self.path, mutate=remove_sources)
        with self.assertRaisesRegex(ArenaError, "REQUIRED_SOURCE_MISSING"):
            _load_package(self.path, new_sha)

    def test_empty_or_incomplete_inner_outputs_are_rejected(self):
        def remove_output(files, sources):
            for name in REQUIRED_OUTPUTS:
                files.pop(ROOT + name)
        new_sha = make_zip(self.path, mutate=remove_output)
        with self.assertRaisesRegex(ArenaError, "REQUIRED_OUTPUT_COVERAGE_INVALID"):
            _load_package(self.path, new_sha)

    def test_rejects_fractional_cut_instead_of_exposing_part_of_minute_59(self):
        with self.assertRaisesRegex(ArenaError, "CONSTRUCTION_CUT_MUST_ALIGN_TO_MINUTE"):
            CoffeePeakCapacityV1().validate({**self.config, "construction_end_min": 59.5}, self.path)

    def test_direct_public_export_also_rejects_fractional_cut(self):
        zf, _ = _load_package(self.path, self.sha)
        with zf, self.assertRaisesRegex(ArenaError, "CONSTRUCTION_CUT_MUST_ALIGN_TO_MINUTE"):
            _build_public(zf, {**self.config, "construction_end_min": 59.5}, self.sha)

    def test_rejects_forged_or_inconsistent_line_items(self):
        for field, value in (
            ("order_id", "DIFFERENT_ORDER"),
            ("timestamp_min_from_peak_start", "-9"),
            ("timestamp_min_from_peak_start", "12"),
            ("source_class", "truth_injected_as_pos"),
            ("synthetic", "False"),
        ):
            with self.subTest(field=field, value=value):
                def bad_line(files, sources):
                    key = ROOT + "pos_line_items.csv"
                    reader = csv.DictReader(io.StringIO(files[key].decode()))
                    rows = list(reader)
                    rows[0][field] = value
                    files[key] = tab(reader.fieldnames, rows)
                new_sha = make_zip(self.path, mutate=bad_line)
                zf, _ = _load_package(self.path, new_sha)
                with zf, self.assertRaisesRegex(ArenaError, "LINE_PARENT_TIME_OR_PROVENANCE_INVALID"):
                    _build_public(zf, self.config, new_sha)

    def test_rejects_duplicate_line_ids_even_with_valid_hashes(self):
        def repeat_line(files, sources):
            key = ROOT + "pos_line_items.csv"
            reader = csv.DictReader(io.StringIO(files[key].decode()))
            rows = list(reader)
            rows.insert(0, dict(rows[0]))
            files[key] = tab(reader.fieldnames, rows)
        sha = make_zip(self.path, mutate=repeat_line)
        zf, _ = _load_package(self.path, sha)
        with zf, self.assertRaisesRegex(ArenaError, "DUPLICATE_OR_EMPTY_LINE_ID"):
            _build_public(zf, self.config, sha)

    def test_fails_closed_on_corrupt_member_even_with_new_package_sha(self):
        broken = make_zip(self.path, tamper=True)
        with self.assertRaisesRegex(ArenaError, "SIZE_MISMATCH"):
            _load_package(self.path, broken)

    def test_refuses_wrong_package_hash(self):
        with self.assertRaisesRegex(ArenaError, "PACKAGE_SHA256_MISMATCH"):
            _load_package(self.path, "0"*64)

    def test_invalid_scenario_fails_instead_of_relabeling(self):
        self.config["selection"]["scenario_id"] = "unknown"
        zf, _ = _load_package(self.path, self.sha)
        with zf, self.assertRaisesRegex(ArenaError, "SCENARIO_REPLICATION_NOT_UNIQUE"):
            _build_public(zf, self.config, self.sha)

    def test_rejects_paid_backend_or_budget_and_invalid_cut(self):
        proto = CoffeePeakCapacityV1()
        with self.assertRaisesRegex(ArenaError, "NONZERO_BUDGET_FORBIDDEN"):
            proto.validate({**self.config, "budget": {"omc": 1, "provider_posts": 0, "workflow": 0}}, self.path)
        with self.assertRaisesRegex(ArenaError, "ONLY_ZERO_CONSUMPTION_FIXTURE_AVAILABLE"):
            proto.validate({**self.config, "backend": "github"}, self.path)
        with self.assertRaisesRegex(ArenaError, "INVALID_TEMPORAL_CUT"):
            proto.validate({**self.config, "construction_end_min": 104.0}, self.path)

    def test_adapter_check_runs_without_provider_or_truth_release(self):
        proto = CoffeePeakCapacityV1()
        proto.validate(self.config, self.path)
        result = proto.check(self.config, None)
        self.assertEqual(result["public_pos_records"], 1)
        self.assertFalse(result["external_compute_started"])
        self.assertEqual(result["private_holdout_access"], "NOT_IMPLEMENTED")

    def test_cli_check_and_run_in_new_processes(self):
        import subprocess
        import sys
        config = Path(self.temp.name) / "coffee.toml"
        config.write_text(f"""id = "fixture"
protocol = "coffee_peak_capacity_v1"
backend = "fixture"
construction_end_min = 60.0
window_end_min = 103.237
[source]
path = "{self.path.as_posix()}"
sha256 = "{self.sha}"
[selection]
scenario_id = "case-a"
replication = 1
day_of_week = 1
[budget]
omc = 0
provider_posts = 0
workflow = 0
""", encoding="utf-8")
        root = Path(__file__).resolve().parents[1]
        for args in (("check", str(config)), ("run", str(config), "--out", str(Path(self.temp.name)/"run"))):
            result = subprocess.run([sys.executable, "-m", "arena", *args], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        run = Path(self.temp.name)/"run"
        payload = json.loads((run / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["arms"], {"D": "NOT_EXECUTED", "B": "NOT_EXECUTED", "M": "NOT_EXECUTED"})
        self.assertEqual(payload["new_omc"], 0)
        self.assertEqual(payload["provider_posts"], 0)
        self.assertFalse((run / "inputs" / "events_truth.json").exists())
        public = (run / "inputs" / "producer-public-b0.json").read_text(encoding="utf-8")
        self.assertNotIn("P80", public)
        self.assertNotIn("SECRET-FUTURE-TRUTH", public)


if __name__ == "__main__":
    unittest.main()
