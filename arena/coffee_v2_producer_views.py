"""Arena Coffee V2.1 P02/P05 + early P12: custodian-prepared producer views.

Requires the exact ZIP, persistent private key and SQLite catalog from P01.
Emits sanitized CONSTRUCTION/DEVELOPMENT observations only; no evaluation
cases, raw scenario labels, latent configuration, seed, truth or private map.
A distinct source ZIP is never selected using a mutable 'latest' pointer.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import argparse
import csv
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import zipfile

from .common import ArenaError, write_json
from . import coffee_v2_synthetic_corpus as corpus
from .coffee_dm_campaign import SELECTION as HISTORICAL_V1

SCHEMA = "arena.coffee-v2.producer-views/1"
TEMPORAL_OPERATOR = "P05-SYNTHETIC-PAID-POS-5MIN/1"
LINE_OPERATOR = "P05-SYNTHETIC-PAID-ITEM-ARCHETYPE/1"
VISUAL_OPERATOR = "P05-VIDEO-PRESENCE-PROXY-MINUTE/1"
SPLIT_DECLARATION = "P12-SCENARIO-GROUPED-EXPLORATORY/1"
ALLOWED_PARTS = {"CONSTRUCTION", "DEVELOPMENT"}
FIVE_MINUTES = 5
V1_CONSTRUCTION_END = 60.0
CSV_COLUMNS = {
    "producer-case-index.csv": (
        "case_id", "partition", "replication", "days_in_week",
        "pos_observations_released", "line_items_released",
    ),
    "producer-pos-observations.csv": (
        "case_id", "partition", "day_of_week", "pos_event_id", "order_id",
        "time_min_from_peak_start", "kind", "status",
        "order_archetype_synthetic", "beverages_synthetic",
        "amount_mxn_assumption", "refund_amount_mxn_assumption",
        "source_kind",
    ),
    "producer-line-items.csv": (
        "case_id", "partition", "day_of_week", "pos_event_id", "order_id",
        "line_id", "time_min_from_peak_start", "synthetic_sku",
        "item_archetype", "quantity", "unit_price_mxn_assumption",
        "unit_variable_cost_mxn_assumption", "source_kind",
    ),
    "producer-paid-bins-5min.csv": (
        "case_id", "partition", "day_of_week", "bin_start_min",
        "bin_end_min_exclusive", "synthetic_payments", "synthetic_refunds",
        "payments_equivalent_per_hour", "observable", "coverage_status",
    ),
    "producer-video-proxy-minute.csv": (
        "minute_from_peak_start", "sample_seconds",
        "mean_public_customer_tracklets_per_second",
        "mean_manual_queue_marks_per_second", "source_kind",
    ),
}
ENUM_SAFE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def need(test, why):
    if not test:
        raise ArenaError("COFFEE_V2_VIEWS_" + why)


def text_enum(raw, field):
    if raw == "":
        return "UNSPECIFIED_IN_SOURCE"
    need(type(raw) is str and ENUM_SAFE.fullmatch(raw) is not None,
         "INVALID_SAFE_VALUE_" + field)
    return raw


def money(raw, name):
    if raw == "":
        return ""
    return format(corpus.floating(raw, 0, 1_000_000, name), ".10g")


def opaque(key, typ, *values):
    return corpus.stable_id(key, "producer-" + typ, "\0".join(map(str, values)))


def catalog_attestation(private_dir, result):
    """Read private mapping strictly; no SQL map is added to producer outputs."""
    folder = Path(private_dir)
    database = folder / "catalog.sqlite"
    key_file = folder / "custody-key.bin"
    need(database.is_file() and key_file.is_file(),
         "PRIVATE_CATALOG_AND_KEY_REQUIRED")
    key = key_file.read_bytes()
    need(len(key) >= 32, "PRIVATE_KEY_INVALID")
    expected_fingerprint = hashlib.sha256(key).hexdigest()
    need(expected_fingerprint == result["key_fingerprint"],
         "CUSTODY_KEY_NOT_MATCHING_CORPUS")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro",
                                 uri=True)) as conn:
        meta = dict(conn.execute("SELECT key, value FROM private_meta"))
        cases = conn.execute(
            "SELECT scenario_private, replication_private, partition, "
            "opaque_case_id FROM synthetic_cases"
        ).fetchall()
    need(meta.get("source_zip_sha256") == result["public"]["source_zip_sha256"]
         and meta.get("key_fingerprint") == expected_fingerprint,
         "CATALOG_SOURCE_OR_KEY_MISMATCH")
    actual = {(sc, rep): (part, oid) for sc, rep, part, oid in cases}
    expected = {
        (r["scenario_private"], r["replication_private"]):
        (r["partition"], r["opaque_case_id"]) for r in result["cases"]
    }
    need(actual == expected and len(actual) == 54,
         "PRIVATE_CATALOG_PARTITION_CHANGED")
    assignment_message = json.dumps(
        sorted((oid, part) for part, oid in actual.values()),
        separators=(",", ":"),
    ).encode("utf-8")
    commitment = hmac.new(key, b"arena-coffee-P12-split\0" + assignment_message,
                          hashlib.sha256).hexdigest()
    return key, actual, commitment


def build(source, private_dir):
    source = Path(source)
    private_dir = Path(private_dir)
    need(source.is_file(), "PINNED_CORPUS_REQUIRED")
    key_path = private_dir / "custody-key.bin"
    need(key_path.is_file(), "FROZEN_CUSTODY_KEY_REQUIRED")
    key = key_path.read_bytes()
    # Recheck all 19 output byte hashes, but do not parse truth rows.
    verified = corpus.audit(source, key=key)
    key, mapped, commitment = catalog_attestation(private_dir, verified)
    with zipfile.ZipFile(source, "r") as z:
        pos = corpus.read_csv(z, "pos_observed.csv", (
            "scenario_id", "replication", "day_of_week", "pos_record_id",
            "order_id", "timestamp_min_from_peak_start", "pos_record_type",
            "sale_status", "synthetic", "source_class"), 20000)
        items = corpus.read_csv(z, "pos_line_items.csv", (
            "scenario_id", "replication", "day_of_week", "pos_record_id",
            "order_id", "pos_line_id", "quantity", "synthetic", "source_class"),
            20000)
        profile = corpus.read_csv(z, "perfil_carga_video.csv", (
            "minute_from_peak_start", "sample_seconds", "synthetic",
            "source_class"), 200)
        # Original configuration has already been authenticated by corpus.audit.
        config = json.loads(z.read(corpus.CONFIG))
    horizon = corpus.floating(config["source"]["synthetic_peak_window_minutes"],
                              60, 180, "SYNTHETIC_PEAK_HORIZON")
    private_filter = (HISTORICAL_V1["scenario_id"],
                      HISTORICAL_V1["replication"],
                      HISTORICAL_V1["day_of_week"])
    outputs = {name: [] for name in CSV_COLUMNS}
    pos_keep = {}
    pos_time = {}
    counts = Counter()
    allowed = {}
    for (sc, rep), (part, oid) in mapped.items():
        if part in ALLOWED_PARTS:
            allowed[(sc, rep)] = (part, oid)
    need(len(allowed) == 45, "ALLOWED_WEEKS_MUST_BE_45")
    paid_by_bin = Counter()
    pos_by_case = Counter()
    line_by_case = Counter()
    for row in pos:
        sc = row["scenario_id"]
        rep = corpus.integer(row["replication"], 1, 3, "REPLICATION")
        day = corpus.integer(row["day_of_week"], 1, 7, "DAY")
        t = corpus.floating(row["timestamp_min_from_peak_start"],
                            0, 1440, "POS_TIME")
        part_and_id = allowed.get((sc, rep))
        if part_and_id is None:
            counts["evaluation_pos_never_released"] += 1
            continue
        if t >= horizon:
            counts["after_peak_pos_not_in_producer_input"] += 1
            continue
        if (sc, rep, day) == private_filter and t >= V1_CONSTRUCTION_END:
            counts["historical_v1_reserved_pos_excluded"] += 1
            continue
        part, case_id = part_and_id
        kind = row["pos_record_type"]
        status = row["sale_status"]
        need((kind, status) in {
            ("sale", "paid_synthetic"), ("refund", "refunded_synthetic")
        }, "POS_KIND_STATUS_MISMATCH")
        record_id = row["pos_record_id"]
        order_id = row["order_id"]
        source_key = (sc, rep, day, record_id)
        need(source_key not in pos_keep, "DUPLICATE_RELEASED_POS")
        safe_record_id = opaque(key, "pos", sc, rep, day, record_id)
        safe_order_id = opaque(key, "order", sc, rep, day, order_id)
        pos_keep[source_key] = (case_id, part, safe_record_id, safe_order_id,
                                kind)
        pos_time[source_key] = t
        outputs["producer-pos-observations.csv"].append((
            case_id, part, day, safe_record_id, safe_order_id,
            row["timestamp_min_from_peak_start"], kind, status,
            text_enum(row.get("archetype", ""), "ORDER_ARCHETYPE"),
            (corpus.integer(row["beverage_count"], 1, 30, "BEVERAGES")
             if row.get("beverage_count") else ""),
            money(row.get("amount_mxn", ""), "POS_AMOUNT"),
            money(row.get("refund_amount_mxn", ""), "POS_REFUND"),
            "SYNTHETIC_POS_PAYMENT_NOT_ARRIVAL_OR_PICKUP",
        ))
        counts["released_pos_events"] += 1
        counts["released_pos_" + kind] += 1
        pos_by_case[(sc, rep)] += 1
        bin_start = math.floor(t/FIVE_MINUTES)*FIVE_MINUTES
        paid_by_bin[(sc, rep, day, bin_start, kind)] += 1

    for row in items:
        sc = row["scenario_id"]
        rep = corpus.integer(row["replication"], 1, 3, "ITEM_REPLICATION")
        day = corpus.integer(row["day_of_week"], 1, 7, "ITEM_DAY")
        source_key = (sc, rep, day, row["pos_record_id"])
        ref = pos_keep.get(source_key)
        if ref is None:
            # The parent payment was evaluation-only, reserved or after-horizon.
            counts["items_excluded_with_parent_payment"] += 1
            continue
        case_id, part, pos_id, order_id, kind = ref
        need(kind == "sale", "REFUND_CANNOT_CREATE_LINE_ITEMS")
        t = pos_time[source_key]
        if row.get("timestamp_min_from_peak_start", ""):
            declared = corpus.floating(row["timestamp_min_from_peak_start"],
                                       0, 1440, "ITEM_TIME")
            need(abs(declared-t) <= 1e-4, "LINE_PAYMENT_CLOCK_CONFLICT")
        item_id = opaque(key, "line", sc, rep, day,
                         row["pos_record_id"], row["pos_line_id"])
        qty = corpus.integer(row["quantity"], 1, 30, "QUANTITY")
        outputs["producer-line-items.csv"].append((
            case_id, part, day, pos_id, order_id, item_id,
            row.get("timestamp_min_from_peak_start") or
            format(t, ".10g"),
            text_enum(row.get("synthetic_sku", ""), "SKU"),
            text_enum(row.get("item_archetype", ""), "ITEM_ARCHETYPE"),
            qty,
            money(row.get("unit_price_mxn_assumption", ""), "ITEM_UNIT_PRICE"),
            money(row.get("unit_variable_cost_mxn_assumption", ""), "ITEM_COST"),
            "SYNTHETIC_ITEM_NOT_MEASURED_RECIPE",
        ))
        line_by_case[(sc, rep)] += 1
        counts["released_line_items"] += 1

    bins = 0
    for (sc, rep), (part, case_id) in sorted(allowed.items()):
        outputs["producer-case-index.csv"].append(
            (case_id, part, rep, 7, pos_by_case[(sc, rep)],
             line_by_case[(sc, rep)])
        )
        for day in range(1, 8):
            for bin_start in range(0, 105, FIVE_MINUTES):
                end = min(bin_start + FIVE_MINUTES, horizon)
                historical_day = (sc, rep, day) == private_filter
                if historical_day and bin_start >= V1_CONSTRUCTION_END:
                    # Explicitly missing: never turn withheld V1 data into zero.
                    outputs["producer-paid-bins-5min.csv"].append((
                        case_id, part, day, bin_start, format(end, ".10g"),
                        "", "", "",
                        "PAID_POS_EQUIVALENT_RATE_NOT_ARRIVALS_OR_THROUGHPUT",
                        "V1_RESERVED_NOT_RELEASED",
                    ))
                else:
                    visible_end = (min(end, V1_CONSTRUCTION_END)
                                   if historical_day else end)
                    need(visible_end > bin_start, "EMPTY_OBSERVED_BIN")
                    paid = paid_by_bin[(sc, rep, day, bin_start, "sale")]
                    refunds = paid_by_bin[(sc, rep, day, bin_start, "refund")]
                    hours = (visible_end-bin_start)/60.0
                    outputs["producer-paid-bins-5min.csv"].append((
                        case_id, part, day, bin_start,
                        format(visible_end, ".10g"), paid, refunds,
                        format(paid/hours, ".10g"),
                        "PAID_POS_EQUIVALENT_RATE_NOT_ARRIVALS_OR_THROUGHPUT",
                        ("V1_CONSTRUCTION_ONLY" if historical_day
                         else "COMPLETE_SYNTHETIC_POS_WINDOW"),
                    ))
                bins += 1
    need(len(outputs["producer-case-index.csv"]) == 45
         and bins == 45*7*21, "CASE_AND_BIN_COVERAGE")
    need(sum(r[4] for r in outputs["producer-case-index.csv"]) ==
         counts["released_pos_events"], "POS_NOT_CONSERVED_BY_CASE")
    need(sum(r[5] for r in outputs["producer-case-index.csv"]) ==
         counts["released_line_items"], "ITEMS_NOT_CONSERVED_BY_CASE")
    need(sum(r[5] for r in outputs["producer-paid-bins-5min.csv"]
             if isinstance(r[5], int)) ==
         counts["released_pos_sale"], "BIN_PAID_COUNT_NOT_CONSERVED")
    need(sum(r[6] for r in outputs["producer-paid-bins-5min.csv"]
             if isinstance(r[6], int)) ==
         counts["released_pos_refund"], "BIN_REFUND_COUNT_NOT_CONSERVED")

    seen_minute = set()
    for row in profile:
        minute = corpus.integer(row["minute_from_peak_start"],
                                0, 103, "PROFILE_MINUTE")
        need(minute not in seen_minute
             and row["synthetic"].lower() == "false"
             and row["source_class"] ==
             "video_customer_presence_proxy_not_arrival_count",
             "VISUAL_PROFILE_PROVENANCE")
        seen_minute.add(minute)
        sampled = corpus.integer(row["sample_seconds"], 1, 60,
                                 "PROFILE_SAMPLE_SECONDS")
        values = []
        for name in ("mean_public_customer_tracklets_per_second",
                     "mean_manual_queue_marks_per_second"):
            raw = row.get(name, "")
            values.append(format(corpus.floating(raw, 0, 1000, name),
                                 ".10g") if raw else "")
        # The full source's 104 minutes are validated, but historical V1
        # reserve [60,103.237] cannot be released for V2 model development.
        if minute < V1_CONSTRUCTION_END:
            outputs["producer-video-proxy-minute.csv"].append((
                minute, sampled, *values,
                "VISUAL_PRESENCE_PROXY_NOT_ARRIVAL_OR_RESOURCE_UTILIZATION",
            ))
    need(seen_minute == set(range(104)) and
         len(outputs["producer-video-proxy-minute.csv"]) == 60,
         "VISUAL_PROFILE_INCOMPLETE")

    output_case_ids = {r[0] for r in outputs["producer-case-index.csv"]}
    need(len(output_case_ids) == 45 and all(
        r[0] in output_case_ids and r[1] in ALLOWED_PARTS
        for name, rows in outputs.items()
        for r in rows if name != "producer-video-proxy-minute.csv"
    ), "CASE_PARTITION_LEAK")
    # Labels, scenario factor names and seeds cannot be present in public data.
    flat = json.dumps(outputs, ensure_ascii=False)
    need(not any(sc in flat for sc, _ in mapped)
         and all(source_name not in flat for source_name in (
             "scenario_id", "peak_arrivals_per_minute_assumption",
             "days_6_7_load_factor_assumption", "patience_scenario",
             "customer_id", "group_id", "person_id", "seed")),
         "PRIVATE_FIELD_OR_SCENARIO_LEAK")

    plan = {
        "schema": SPLIT_DECLARATION,
        "source_sha256": verified["public"]["source_zip_sha256"],
        "partition_policy": corpus.PARTITION_POLICY,
        "commitment_hmac_sha256": commitment,
        "partition_unit": "COMPLETE_SCENARIO_3_REPLICATIONS_7_DAYS",
        "scenario_counts": {"CONSTRUCTION":12,"DEVELOPMENT":3,"EVALUATION":3},
        "weekly_counts": {"CONSTRUCTION":36,"DEVELOPMENT":9,"EVALUATION":9},
        "release_partitions": ["CONSTRUCTION", "DEVELOPMENT"],
        "excluded_partition": "EVALUATION",
        "historical_V1_reserved_interval_not_used":
            "ON_MATCHING_V1_CASE_DAY1_REP1_EXCLUDE_T_GE_60",
        "historical_visual_proxy_scope_released": "[0,60) MINUTES",
        "historical_visual_proxy_scope_withheld": "[60,103.237) MINUTES",
        "synthetic_peak_horizon_minutes": horizon,
        "operators": [TEMPORAL_OPERATOR, LINE_OPERATOR, VISUAL_OPERATOR],
        "declared_before_reference_model_tuning": True,
        "predeclared_metrics": [
            "synthetic_paid_count_by_five_minute_bin",
            "synthetic_refunds_by_five_minute_bin",
            "item_archetype_mix_by_paid_case",
        ],
        "evaluation_truth_not_accessed": True,
        "evaluation_not_yet_authorized": True,
        "science_lock_or_G3_created": False,
        "real_world_generalization_not_demonstrated": True,
    }
    return {
        "tables": outputs, "plan": plan,
        "summary": {
            "schema": SCHEMA,
            "status": "PRODUCER_VIEWS_READY_FOR_REFERENCE_DEVELOPMENT_NOT_EVALUATION",
            "source_sha256": verified["public"]["source_zip_sha256"],
            "allowed_weekly_cases": 45,
            "visual_proxy_source_minute_rows": len(profile),
            "visual_proxy_released_minute_rows": 60,
            "visual_proxy_reserved_minutes_not_released": 44,
            "reserved_weekly_cases_not_released": 9,
            "released_rows": dict(sorted((k, len(v)) for k, v in outputs.items())),
            "exclusion_counts": dict(sorted(counts.items())),
            "temporal_operator": TEMPORAL_OPERATOR,
            "item_operator": LINE_OPERATOR,
            "visual_operator": VISUAL_OPERATOR,
            "synthetic_not_empirical": True,
            "no_truth_or_latent_parameters_exported": True,
            "physical_interventions_B0_S1_S5_not_present": True,
            "no_prediction_g3_or_business_validation": True,
            "provider_calls": 0, "omc_runs": 0, "new_worlds": 0,
        },
    }


def export(result, out):
    out = Path(out).resolve()
    need(not out.exists(), "OUTPUT_ALREADY_EXISTS")
    out.mkdir(parents=True, mode=0o700)
    for name, fields in CSV_COLUMNS.items():
        with (out/name).open("x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            writer.writerows(result["tables"][name])
    write_json(out/"p12-split-plan.json", result["plan"], exclusive=True)
    write_json(out/"producer-view-summary.json", result["summary"], exclusive=True)
    hashes = {
        path.name: "sha256:" + corpus.sha_file(path)
        for path in sorted(out.iterdir())
        if path.is_file()
    }
    write_json(out/"producer-manifest.json", {
        "schema": SCHEMA,
        "status": result["summary"]["status"],
        "operator_versions": [TEMPORAL_OPERATOR, LINE_OPERATOR, VISUAL_OPERATOR],
        "source_sha256": result["summary"]["source_sha256"],
        "output_sha256": hashes,
        "truth_files_opened_as_rows": 0,
        "evaluation_scenario_rows_released": 0,
        "real_business_service_capacity_identified": False,
        "external_consumption": {"R2":0, "OMC":0, "POST":0},
    }, exclusive=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline custodian release; no G3")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        source = options.source.resolve()
        private = options.private_dir.resolve()
        out = options.out.resolve()
        need(out != private and private not in out.parents and
             out not in private.parents and
             out != source and source not in out.parents,
             "OUTPUT_CUSTODY_BOUNDARY")
        result = build(source, private)
        export(result, out)
        print(json.dumps({
            "status": result["summary"]["status"],
            "released_cases": 45,
            "evaluation_cases_released": 0,
            "paid_consumption": 0,
        }, sort_keys=True))
        return 0
    except (ArenaError, OSError, ValueError, TypeError, KeyError,
            sqlite3.Error, zipfile.BadZipFile, UnicodeDecodeError,
            csv.Error) as exc:
        print(json.dumps({
            "status": "STOPPED_NO_EXTERNAL_CONSUMPTION",
            "reason": str(exc) if isinstance(exc, ArenaError)
            else "INVALID_CUSTODIAL_INPUT",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
