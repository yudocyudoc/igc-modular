"""P0/P1 of coffee_peak_capacity_v1: ZIP admission and public B0 fixture only.

No producer, solver, provider, or private holdout is executed. This module is
an importer, not a scientific model or an isolation guarantee.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

from .common import ArenaError, write_json

ROOT = "video2/sintetico_pico_v1/salida/"
PACKAGE_MANIFEST = "MANIFIESTO_PAQUETE.json"
INNER_MANIFEST = ROOT + "manifest.json"
CSV = {
    "summary": ROOT + "resumen_escenarios.csv",
    "pos": ROOT + "pos_observed.csv",
    "lines": ROOT + "pos_line_items.csv",
    "profile": ROOT + "perfil_carga_video.csv",
}
ALLOWED_POS = ("pos_record_id", "order_id", "timestamp_min_from_peak_start",
               "archetype", "beverage_count", "customer_count_synthetic",
               "pos_record_type", "sale_status", "amount_mxn", "refund_amount_mxn",
               "currency_assumption", "synthetic", "source_class")
ALLOWED_LINES = ("pos_record_id", "order_id", "pos_line_id", "timestamp_min_from_peak_start",
                 "synthetic_sku", "item_archetype", "quantity", "synthetic", "source_class")
ALLOWED_PROFILE = ("minute_from_peak_start", "sample_seconds",
                   "mean_public_customer_tracklets_per_second",
                   "mean_manual_queue_marks_per_second", "source_class", "synthetic")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _require(ok, message):
    if not ok:
        raise ArenaError("COFFEE_" + message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _rows(zf, path, required):
    with zf.open(path) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        headers = reader.fieldnames or []
        _require(len(headers) == len(set(headers)) and set(required) <= set(headers),
                 "CSV_HEADERS_INVALID:" + path)
        for row in reader:
            _require(None not in row, "CSV_EXTRA_COLUMNS:" + path)
            yield row


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ArenaError("COFFEE_NOT_NUMERIC:" + label) from None
    _require(math.isfinite(result), "NONFINITE:" + label)
    return result


def _load_package(path, expected_sha):
    path = Path(path)
    _require(path.is_file() and path.suffix.lower() == ".zip", "ZIP_REQUIRED")
    _require(bool(SHA.fullmatch(expected_sha)), "SHA256_REQUIRED")
    hasher = hashlib.sha256()
    with path.open("rb") as raw:
        while chunk := raw.read(1024 * 1024):
            hasher.update(chunk)
    _require(hasher.hexdigest() == expected_sha, "PACKAGE_SHA256_MISMATCH")
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise ArenaError("COFFEE_BAD_ZIP") from None
    try:
        names = zf.namelist()
        _require(len(names) == len(set(names)), "DUPLICATE_ZIP_ENTRY")
        _require(all(PurePosixPath(n).parts and not n.startswith("/")
                     and ".." not in PurePosixPath(n).parts and "\\" not in n
                     and not n.endswith("/") for n in names), "UNSAFE_ZIP_ENTRY")
        _require(all(not (info.external_attr >> 16 & 0o170000 == 0o120000)
                     for info in zf.infolist()), "ZIP_SYMLINK_FORBIDDEN")
        package = json.loads(zf.read(PACKAGE_MANIFEST))
        _require(package.get("schema") == "cafeteria.pilot-package/1" and
                 isinstance(package.get("files"), dict), "PACKAGE_MANIFEST_INVALID")
        registered = package["files"]
        _require(set(names) == set(registered) | {PACKAGE_MANIFEST}, "PACKAGE_CONTENTS_MISMATCH")
        for name, info in registered.items():
            _require(isinstance(info, dict) and SHA.fullmatch(str(info.get("sha256", "")))
                     and type(info.get("bytes")) is int, "MANIFEST_RECORD_INVALID")
            _require(zf.getinfo(name).file_size == info["bytes"], "SIZE_MISMATCH:" + name)
            _require(_sha(zf.read(name)) == info["sha256"], "HASH_MISMATCH:" + name)
        inner = json.loads(zf.read(INNER_MANIFEST))
        _require(inner.get("schema") == "cafeteria.synthetic-output-manifest/2" and
                 isinstance(inner.get("outputs"), dict), "INNER_MANIFEST_INVALID")
        for name, info in inner["outputs"].items():
            entry = registered.get(ROOT + name)
            _require(entry == info, "INNER_OUTPUT_MISMATCH:" + name)
        for field, name in (
            ("source_observation_csv_sha256", "video2/completo_v1/eventos_consolidados.csv"),
            ("source_person_tracks_csv_sha256", "video2/sintetico_pico_v1/revision_fila/personas_clasificadas_1s.csv"),
            ("source_video_receipt_master_sha256", "video2/maestro_15m_v2/eventos_maestro.csv"),
            ("config_sha256", "video2/sintetico_pico_v1/parametros_escenarios.json"),
        ):
            _require(inner.get(field) == registered.get(name, {}).get("sha256"),
                     "SOURCE_LINEAGE_MISMATCH:" + field)
        return zf, inner
    except BaseException:
        zf.close()
        raise


def _build_public(zf, settings, source_sha):
    selection = settings["selection"]
    scenario, replication, day = (selection[k] for k in ("scenario_id", "replication", "day_of_week"))
    key = (scenario, str(replication))
    summaries = [r for r in _rows(zf, CSV["summary"], ("scenario_id", "replication", "synthetic"))
                 if (r["scenario_id"], r["replication"]) == key]
    _require(len(summaries) == 1 and summaries[0]["synthetic"].lower() == "true",
             "SCENARIO_REPLICATION_NOT_UNIQUE")
    before = settings["construction_end_min"]
    end = settings["window_end_min"]
    target = (scenario, str(replication), str(day))
    records = []
    for row in _rows(zf, CSV["pos"], (*ALLOWED_POS, "scenario_id", "replication", "day_of_week")):
        if (row["scenario_id"], row["replication"], row["day_of_week"]) != target:
            continue
        t = _number(row["timestamp_min_from_peak_start"], "pos_time")
        _require(t >= 0 and row["synthetic"].lower() == "true" and
                 row["source_class"] == "synthetic_pos_view", "POS_NOT_SYNTHETIC")
        _require(row["pos_record_type"] in ("sale", "refund"), "UNKNOWN_POS_RECORD_TYPE")
        if t < before:
            records.append({k: row[k] for k in ALLOWED_POS})
    record_ids = {r["pos_record_id"] for r in records}
    _require(len(record_ids) == len(records), "DUPLICATE_POS_RECORD")
    lines = []
    for row in _rows(zf, CSV["lines"], (*ALLOWED_LINES, "scenario_id", "replication", "day_of_week")):
        if (row["scenario_id"], row["replication"], row["day_of_week"]) != target:
            continue
        if row["pos_record_id"] in record_ids:
            _require(_number(row["timestamp_min_from_peak_start"], "line_time") < before
                     and row["synthetic"].lower() == "true", "LINE_TIME_OR_PROVENANCE_INVALID")
            lines.append({k: row[k] for k in ALLOWED_LINES})
    profile = []
    for row in _rows(zf, CSV["profile"], ALLOWED_PROFILE):
        minute = _number(row["minute_from_peak_start"], "profile_minute")
        if 0 <= minute < before:
            _require(row["source_class"] == "video_customer_presence_proxy_not_arrival_count"
                     and row["synthetic"].lower() == "false", "VIDEO_PROXY_PROVENANCE_INVALID")
            profile.append({k: row[k] for k in ALLOWED_PROFILE})
    _require(bool(records) and bool(profile), "EMPTY_PUBLIC_CONSTRUCTION")
    return {
        "schema": "arena.coffee-peak.public-b0/1", "evidence_kind": "SYNTHETIC_POS_AND_VIDEO_PROXY",
        "condition": "B0", "source_package_sha256": source_sha,
        "selection": dict(selection),
        "time": {"unit": "minutes_from_peak_start", "window_start": 0,
                 "construction_end_exclusive": before, "window_end": end,
                 "future_pos_and_truth": "NOT_RELEASED"},
        "semantics": {"sale": "POS payment, not a delivery",
                      "refund": "financial event, not negative delivery",
                      "video_proxy": "presence shape, not measured arrivals or unique people",
                      "queue": "not observed in POS", "net_profit": "not identifiable"},
        "pos_records": records, "pos_line_items": lines, "video_proxy": profile,
    }


class CoffeePeakFixtureBackend:
    def execute(self, store, *, authorize=False):
        _require(not authorize, "FIXTURE_AUTHORIZATION_NOT_NEEDED")
        store.status("RUNNING")
        stage = "admission-public-b0"
        _require(store.stage(stage) is None, "FIXTURE_RESTART_NOT_SUPPORTED")
        store.transition(stage, "RUNNING")
        try:
            config = store.config
            zf, _ = _load_package(config["source"]["path"], config["source"]["sha256"])
            with zf:
                public = _build_public(zf, config, config["source"]["sha256"])
            write_json(store.root / "inputs" / "producer-public-b0.json", public)
            result = {"schema": "arena.result/1", "evidence_kind": "COFFEE_PEAK_ADMISSION_FIXTURE",
                      "physical_experiment_executed": False, "scientific_conclusion": None,
                      "arms": {arm: "NOT_EXECUTED" for arm in ("D", "B", "M")},
                      "producer_models_generated": 0, "new_omc": 0, "provider_posts": 0,
                      "holdout": "NOT_OPENED_OR_SCORED", "custody": "NOT_IMPLEMENTED",
                      "isolation": "PROCEDURAL_ONLY_NOT_CERTIFIED",
                      "public_input": "inputs/producer-public-b0.json",
                      "public_counts": {"pos_records": len(public["pos_records"]),
                                        "pos_line_items": len(public["pos_line_items"]),
                                        "video_profile_minutes": len(public["video_proxy"])}}
            store.transition(stage, "COMPLETED")
            store.status("INTEGRATION_COMPLETED")
            result["run"] = store.report()
            write_json(store.root / "result.json", result)
            return result
        except Exception:
            store.transition(stage, "FAILED")
            store.status("FAILED")
            raise


class CoffeePeakCapacityV1:
    def validate(self, config, path):
        _require(set(config) == {"id", "protocol", "backend", "budget", "source", "selection",
                                   "construction_end_min", "window_end_min"}, "CONFIG_FIELDS_INVALID")
        _require(config["backend"] == "fixture", "ONLY_ZERO_CONSUMPTION_FIXTURE_AVAILABLE")
        _require(config["budget"] == {"omc": 0, "provider_posts": 0, "workflow": 0}, "NONZERO_BUDGET_FORBIDDEN")
        source = config["source"]
        _require(isinstance(source, dict) and set(source) == {"path", "sha256"}, "SOURCE_FIELDS_INVALID")
        _require(isinstance(source["path"], str) and bool(SHA.fullmatch(source["sha256"])), "SOURCE_INVALID")
        source["path"] = str((path.parent / source["path"]).resolve())
        selection = config["selection"]
        _require(isinstance(selection, dict) and set(selection) == {"scenario_id", "replication", "day_of_week"}
                 and isinstance(selection["scenario_id"], str) and selection["scenario_id"], "SELECTION_INVALID")
        _require(type(selection["replication"]) is int and 1 <= selection["replication"] <= 3
                 and type(selection["day_of_week"]) is int and 1 <= selection["day_of_week"] <= 7,
                 "SELECTION_INVALID")
        end, before = config["window_end_min"], config["construction_end_min"]
        _require(type(before) in (float, int) and type(end) in (float, int)
                 and math.isfinite(before) and math.isfinite(end) and 0 < before < end,
                 "INVALID_TEMPORAL_CUT")
        _require(abs(end - 103.237) < 1e-6, "PILOT_WINDOW_MUST_BE_PREDECLARED_103_237")

    def verify(self):
        from .runtime import verify
        return verify(include_history=False)

    def backend(self, config, connections):
        return CoffeePeakFixtureBackend()

    def check(self, config, connections):
        zf, inner = _load_package(config["source"]["path"], config["source"]["sha256"])
        with zf:
            public = _build_public(zf, config, config["source"]["sha256"])
        return {"status": "CHECKED", "protocol": "coffee_peak_capacity_v1", "backend": "fixture",
                "evidence_kind": "ADMISSION_AND_PUBLIC_VIEW_ONLY",
                "package_sha256": config["source"]["sha256"],
                "source_manifest_schema": inner["schema"],
                "selection": public["selection"], "public_pos_records": len(public["pos_records"]),
                "public_video_minutes": len(public["video_proxy"]),
                "producer_models_generated": 0, "private_holdout_access": "NOT_IMPLEMENTED",
                "external_compute_started": False,
                "budget": config["budget"]}
