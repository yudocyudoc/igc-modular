"""Strict read-only adapter for P06 physical reference from P02/P05 producer view.

Reads only the eight published view files; verifies every digest and P12
coverage. Rejects reserved V1 temporal bins and all evaluation partitions.
Never reads original ZIP, SQLite custodial catalog, truth or model generator.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from .common import ArenaError
from . import coffee_v2_producer_views as views
from . import coffee_v2_synthetic_corpus as corpus

FILES = (set(views.CSV_COLUMNS) |
         {"producer-manifest.json", "p12-split-plan.json",
          "producer-view-summary.json"})
HEX_ID = re.compile(r"[0-9a-f]{32}\Z")


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_V2_REFERENCE_INPUT_" + code)


def sha_file(p):
    return corpus.sha_file(p)


def read_rows(p, cols):
    need(p.is_file() and not p.is_symlink() and
         p.stat().st_size <= 24_000_000, "VIEW_CSV_SIZE_OR_PATH")
    with p.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        need(tuple(reader.fieldnames or []) == tuple(cols),
             "VIEW_CSV_HEADERS")
        rows = []
        for row in reader:
            need(len(rows) < 35000 and None not in row and
                 all(v is not None for v in row.values()),
                 "VIEW_CSV_ROW")
            rows.append(row)
    return rows


def flt(x, label, low=0, high=180):
    try:
        y = float(x)
    except (ValueError, TypeError):
        raise ArenaError("COFFEE_V2_REFERENCE_INPUT_BAD_" + label) from None
    need(math.isfinite(y) and low <= y <= high, "NUMBER_" + label)
    return y


def integer(x, label, low=0, high=1000):
    try:
        n = int(x)
    except (ValueError, TypeError):
        raise ArenaError("COFFEE_V2_REFERENCE_INPUT_BAD_" + label) from None
    need(str(n) == str(x) and low <= n <= high, "INTEGER_" + label)
    return n


def select_case_day(view_dir, case_id, day):
    path = Path(view_dir)
    need(path.is_dir() and not path.is_symlink()
         and type(case_id) is str and HEX_ID.fullmatch(case_id)
         and type(day) is int and 1 <= day <= 7, "SELECTION")
    need({p.name for p in path.iterdir()} == FILES and all(
        p.is_file() and not p.is_symlink() for p in path.iterdir()
    ), "VIEW_SET_ONLY_NO_TRUTH")
    meta = json.loads((path/"producer-manifest.json").read_text("utf-8"))
    plan = json.loads((path/"p12-split-plan.json").read_text("utf-8"))
    summary = json.loads((path/"producer-view-summary.json").read_text("utf-8"))
    need(meta.get("schema") == views.SCHEMA and
         meta.get("status") ==
         "PRODUCER_VIEWS_READY_FOR_REFERENCE_DEVELOPMENT_NOT_EVALUATION" and
         meta.get("evaluation_scenario_rows_released") == 0 and
         meta.get("truth_files_opened_as_rows") == 0,
         "PRODUCER_VIEW_PROVENANCE")
    source = meta.get("source_sha256")
    need(type(source) is str and
         re.fullmatch(r"sha256:[0-9a-f]{64}", source) is not None and
         summary.get("source_sha256") == source and
         plan.get("source_sha256") == source and
         summary.get("schema") == views.SCHEMA and
         summary.get("no_truth_or_latent_parameters_exported") is True and
         summary.get("reserved_weekly_cases_not_released") == 9,
         "SOURCE_PARTITION_LINK")
    need(plan.get("schema") == views.SPLIT_DECLARATION and
         plan.get("partition_policy") == corpus.PARTITION_POLICY and
         plan.get("release_partitions") == ["CONSTRUCTION", "DEVELOPMENT"] and
         plan.get("excluded_partition") == "EVALUATION" and
         plan.get("weekly_counts") == {
             "CONSTRUCTION": 36, "DEVELOPMENT": 9, "EVALUATION": 9
         } and plan.get("evaluation_truth_not_accessed") is True and
         plan.get("evaluation_not_yet_authorized") is True and
         plan.get("science_lock_or_G3_created") is False and
         plan.get("synthetic_POS_cannot_validate_V1_future_independently")
         is True and
         plan.get("operators") == [views.TEMPORAL_OPERATOR,
                                    views.LINE_OPERATOR,
                                    views.VISUAL_OPERATOR],
         "SPLIT_GATE")
    horizon = flt(plan.get("synthetic_peak_horizon_minutes"),
                  "HORIZON", 60, 180)
    expected = meta.get("output_sha256")
    need(type(expected) is dict and
         set(expected) == FILES-{"producer-manifest.json"} and
         all(re.fullmatch(r"sha256:[0-9a-f]{64}", val)
             for val in expected.values()),
         "VIEW_RECEIPT_INCOMPLETE")
    for name, checksum in expected.items():
        need("sha256:"+sha_file(path/name) == checksum,
             "VIEW_CHECKSUM_" + name)
    index = read_rows(path/"producer-case-index.csv",
                      views.CSV_COLUMNS["producer-case-index.csv"])
    need(len(index) == 45 and
         len({r["case_id"] for r in index}) == 45,
         "CASE_INDEX_SIZE_OR_DUPLICATES")
    by_case = {}
    for r in index:
        need(HEX_ID.fullmatch(r["case_id"]) is not None and
             r["partition"] in ("CONSTRUCTION", "DEVELOPMENT") and
             integer(r["replication"], "REPLICATION", 1, 3) in (1, 2, 3) and
             integer(r["days_in_week"], "WEEK_DAYS", 7, 7) == 7,
             "CASE_INDEX_SEMANTICS")
        by_case[r["case_id"]] = r
    need(sum(x["partition"] == "CONSTRUCTION" for x in index) == 36 and
         sum(x["partition"] == "DEVELOPMENT" for x in index) == 9,
         "CASE_PARTITION_COUNTS")
    need(case_id in by_case, "CASE_NOT_AUTHORIZED")
    part = by_case[case_id]["partition"]
    rows = read_rows(path/"producer-pos-observations.csv",
                     views.CSV_COLUMNS["producer-pos-observations.csv"])
    lines = read_rows(path/"producer-line-items.csv",
                      views.CSV_COLUMNS["producer-line-items.csv"])
    bins = read_rows(path/"producer-paid-bins-5min.csv",
                     views.CSV_COLUMNS["producer-paid-bins-5min.csv"])
    # Producer input can have no corresponding POS for a day. Do not turn
    # a censored bin into zero; only complete synthetic days are simulated.
    selected = [r for r in rows if
                r["case_id"] == case_id and
                integer(r["day_of_week"], "DAY", 1, 7) == day]
    selected_lines = [r for r in lines if
                      r["case_id"] == case_id and
                      integer(r["day_of_week"], "LINE_DAY", 1, 7) == day]
    selected_bins = [r for r in bins if
                     r["case_id"] == case_id and
                     integer(r["day_of_week"], "BIN_DAY", 1, 7) == day]
    need(len(selected_bins) == 21 and
         {integer(b["bin_start_min"], "BIN_START", 0, 100)
          for b in selected_bins} == set(range(0, 105, 5)),
         "BIN_COVERAGE")
    need(all(b["partition"] == part and
             b["coverage_status"] == "COMPLETE_SYNTHETIC_POS_WINDOW"
             for b in selected_bins),
         "PARTIAL_OR_RESERVED_BIN_NOT_ALLOWED")
    bins_by_start = {}
    for b in selected_bins:
        start = integer(b["bin_start_min"], "BIN_START", 0, 100)
        end = flt(b["bin_end_min_exclusive"], "BIN_END", 0, horizon)
        need(abs(end-min(start+5, horizon)) < 1e-8 and end > start,
             "BIN_HALFOPEN_HORIZON")
        bins_by_start[start] = {
            "sale": integer(b["synthetic_payments"], "BIN_PAID", 0, 5000),
            "refund": integer(b["synthetic_refunds"], "BIN_REFUNDS", 0, 5000)
        }

    seen_pos = set()
    positions = []
    checked_counts = Counter()
    for x in selected:
        need(x["partition"] == part and
             x["source_kind"] ==
             "SYNTHETIC_POS_PAYMENT_NOT_ARRIVAL_OR_PICKUP" and
             HEX_ID.fullmatch(x["pos_event_id"]) is not None and
             HEX_ID.fullmatch(x["order_id"]) is not None and
             x["pos_event_id"] not in seen_pos,
             "POS_PROVENANCE_OR_ID")
        seen_pos.add(x["pos_event_id"])
        kind = x["kind"]
        need((kind, x["status"]) in (
             ("sale", "paid_synthetic"), ("refund", "refunded_synthetic")),
             "POS_STATUS")
        t = flt(x["time_min_from_peak_start"], "PAYMENT_TIME", 0, horizon)
        need(t < horizon, "PAYMENT_AFTER_CUT")
        if kind == "sale":
            b = integer(x["beverages_synthetic"], "BEVERAGES", 1, 30)
        else:
            need(not x["beverages_synthetic"], "REFUND_NOT_NEW_BEVERAGE")
            b = None
        checked_counts[(int(t//5)*5,kind)] += 1
        positions.append({
            "pos_event_id": x["pos_event_id"], "order_id": x["order_id"],
            "time_min": t, "kind": kind, "beverage_count": b
        })
    for start, values in bins_by_start.items():
        for kind in ("sale", "refund"):
            need(checked_counts[(start,kind)] == values[kind],
                 "BIN_EVENT_NOT_CONSERVED")
    paid_ids = {p["pos_event_id"]: p["order_id"] for p in positions
                if p["kind"] == "sale"}
    selected_item_rows = []
    seen_lines = set()
    for x in selected_lines:
        need(x["partition"] == part and
             x["source_kind"] == "SYNTHETIC_ITEM_NOT_MEASURED_RECIPE" and
             HEX_ID.fullmatch(x["line_id"]) is not None and
             x["line_id"] not in seen_lines and
             paid_ids.get(x["pos_event_id"]) == x["order_id"] and
             x["item_archetype"] in ("solo_extraccion", "con_leche"),
             "LINE_PROVENANCE_OR_PARENT")
        seen_lines.add(x["line_id"])
        selected_item_rows.append({
            "line_id": x["line_id"], "pos_event_id": x["pos_event_id"],
            "order_id": x["order_id"],
            "time_min": flt(x["time_min_from_peak_start"],
                            "LINE_TIME", 0, horizon),
            "archetype": x["item_archetype"],
            "quantity": integer(x["quantity"], "LINE_QUANTITY", 1, 30),
        })
    return {
        "positions": positions, "items": selected_item_rows,
        "horizon": horizon, "partition": part,
        "manifest_sha256": "sha256:"+sha_file(path/"producer-manifest.json"),
        "source_sha256": source, "coverage": "FULL_SYNTHETIC_POS_DAY_NOT_ARRIVALS",
    }
