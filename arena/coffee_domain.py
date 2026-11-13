"""Versioned public domain contract for coffee B0, paid order -> pickup.

This module sees ONLY the public admission artifact and public, explicitly
uncalibrated design assumptions. It never opens the source ZIP, R2 or truth.
No D/B/M generation, simulation, calibration or scoring is performed here.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .common import ArenaError, digest, read_json, write_json
from .coffee_custody import producer_boundary

SCHEMA = "arena.coffee-peak.public-case/1"
ASSUMPTIONS_SCHEMA = "arena.coffee-peak.public-assumptions/1"
CUTS_MIN = (80.0, 100.0, 103.237)
CONSTRUCTION_END_MIN = 60.0
WINDOW_END_MIN = 103.237
PARAMETERS = {
    "initial_paid_orders": "orders",
    "service_capacity": "orders/hour",
    "response_time": "hours",
    "post_payment_loss_rate": "1/hour",
    "workload_per_paid_order": "orders/order",
}
PROVENANCE = "PUBLIC_DESIGN_HYPOTHESIS_NOT_IDENTIFIED"
ARM_COUNTER = {"D": "delivered", "M": "deliveredTotal"}


def _need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_DOMAIN_" + code)


def _finite(value, code):
    _need(type(value) in (int, float) and math.isfinite(value), code)
    return float(value)


def validate_assumptions(hypotheses):
    """Reject truth-derived/undeclared assumptions and unit-swapped parameters."""
    _need(isinstance(hypotheses, dict) and set(hypotheses) ==
          {"schema", "version", "frontier", "parameters"}, "ASSUMPTIONS_FIELDS")
    _need(hypotheses["schema"] == ASSUMPTIONS_SCHEMA and
          hypotheses["frontier"] == "PAID_ORDER_TO_PICKUP" and
          isinstance(hypotheses["version"], str) and hypotheses["version"],
          "ASSUMPTIONS_SCHEMA")
    params = hypotheses["parameters"]
    _need(isinstance(params, dict) and set(params) == set(PARAMETERS),
          "ASSUMPTION_PARAMETERS_INVALID")
    for key, unit in PARAMETERS.items():
        p = params[key]
        _need(isinstance(p, dict) and set(p) ==
              {"value", "unit", "admissible_range", "origin", "identification"},
              "ASSUMPTION_RECORD_INVALID:" + key)
        v = _finite(p["value"], "ASSUMPTION_NONFINITE:" + key)
        bounds = p["admissible_range"]
        _need(isinstance(bounds, list) and len(bounds) == 2,
              "ASSUMPTION_RANGE_INVALID:" + key)
        lo, hi = (_finite(b, "ASSUMPTION_RANGE_NONFINITE:" + key) for b in bounds)
        _need(p["unit"] == unit and 0 <= lo <= v <= hi and
              p["origin"] == PROVENANCE and
              p["identification"] == "ASSUMED_NOT_MEASURED",
              "ASSUMPTION_PROVENANCE_OR_UNIT_INVALID:" + key)
        if key == "initial_paid_orders":
            _need(v == lo == hi == 0, "INITIAL_BACKLOG_MUST_BE_ZERO_IN_V1")
        if key == "workload_per_paid_order":
            # D/M v1 material balances count paid orders, not cups or workload units.
            # A non-unit conversion needs an explicit, versioned physical model;
            # accepting it here would silently leave native equations unchanged.
            _need(v == lo == hi == 1, "NONUNIT_WORKLOAD_UNSUPPORTED_V1")
        if key in ("service_capacity", "response_time", "workload_per_paid_order"):
            _need(lo > 0, "ASSUMED_POSITIVE_PARAMETER_REQUIRED:" + key)
    return hypotheses


def _payment_ledger(public, end):
    """Payments are input events; they are neither arrivals nor pickups."""
    orders = set()
    total = 0
    refunds = 0
    for row in public["pos_records"]:
        _need(isinstance(row, dict), "POS_RECORD_INVALID")
        try:
            t = float(row["timestamp_min_from_peak_start"])
        except (ValueError, TypeError, KeyError):
            raise ArenaError("COFFEE_DOMAIN_POS_TIME_INVALID") from None
        _need(math.isfinite(t) and 0 <= t < end, "POS_OUTSIDE_CONSTRUCTION")
        _need(row.get("synthetic", "").lower() == "true" and
              row.get("source_class") == "synthetic_pos_view",
              "POS_PROVENANCE_NOT_SYNTHETIC")
        kind = row.get("pos_record_type")
        if kind == "sale":
            _need(row.get("sale_status") == "paid_synthetic" and
                  row.get("order_id") not in orders, "PAID_ORDER_UNIQUE_REQUIRED")
            orders.add(row["order_id"])
            total += 1
        elif kind == "refund":
            _need(row.get("sale_status") == "refunded_synthetic",
                  "REFUND_STATUS_INVALID")
            refunds += 1
        else:
            _need(False, "POS_EVENT_TYPE_INVALID")
    _need(total > 0, "NO_PAID_ORDERS_FOR_RATE")
    # No identity inference: a refund may refer to a payment outside the window.
    return total, refunds


def build_case(public_dir, assumptions_path, *, environment=None):
    """Single common case for D/B/M from exactly one already-filtered view."""
    with TemporaryDirectory() as temp:
        producer_boundary(public_dir, Path(temp) / "public-proof.json",
                          environment=environment)
    folder = Path(public_dir)
    public = read_json(folder / "producer-public-b0.json")
    release = read_json(folder / "release.json")
    hypotheses = validate_assumptions(read_json(assumptions_path))
    time = public["time"]
    _need(time.get("unit") == "minutes_from_peak_start" and
          time.get("window_start") == 0 and
          time.get("future_pos_and_truth") == "NOT_RELEASED" and
          time.get("construction_end_exclusive") == CONSTRUCTION_END_MIN and
          abs(time.get("window_end", -1) - WINDOW_END_MIN) < 1e-9,
          "CASE_WINDOW_NOT_PREDECLARED")
    _need(release.get("condition") == "B0" and
          release.get("public_sha256") == digest(public) and
          public.get("evidence_kind") == "SYNTHETIC_POS_AND_VIDEO_PROXY" and
          type(public.get("selection")) is dict and
          set(public["selection"]) == {"scenario_id", "replication", "day_of_week"},
          "PUBLIC_CASE_IDENTITY_INVALID")
    paid, refunded = _payment_ledger(public, CONSTRUCTION_END_MIN)
    # Unit conversion is mandatory: orders / 60 minutes -> orders per hour.
    rate = paid * 60.0 / CONSTRUCTION_END_MIN
    return {
        "schema": SCHEMA, "protocol": "coffee_peak_capacity_v1",
        "condition": "B0", "frontier": "PAID_ORDER_TO_PICKUP",
        "source_package_sha256": release["source_package_sha256"],
        "public_sha256": release["public_sha256"],
        "run_id": release["run_id"], "frozen_sha": release["frozen_sha"],
        "selection": dict(public["selection"]),
        "time": {
            "native_unit": "hours", "public_unit": "minutes",
            "construction_end_min": CONSTRUCTION_END_MIN,
            "window_end_min": WINDOW_END_MIN,
            "horizon_hours": WINDOW_END_MIN / 60.0,
            "prediction_cuts_min": list(CUTS_MIN),
            "minutes_per_hour": 60.0,
        },
        "input": {
            "meaning": "ACCEPTED_PAID_ORDERS_NOT_CUSTOMER_ARRIVALS",
            "shape": "RECTANGULAR_CONSTANT_RATE",
            "public_paid_order_count_before_cut": paid,
            "refund_events_before_cut": refunded,
            "rate_orders_per_hour": rate,
            "construction_interval_min": [0.0, CONSTRUCTION_END_MIN],
            "future_interval_min": [CONSTRUCTION_END_MIN, WINDOW_END_MIN],
            "future_rate_origin": "ASSUMED_CONSTANT_NOT_OBSERVED",
            "public_pos_temporal_detail": "RETAINED_ONLY_IN_PUBLIC_SOURCE",
            "payment_is_pickup": False,
        },
        "hypotheses": hypotheses,
        "hypotheses_sha256": digest(hypotheses),
        "observables": {
            "primary": "orders_picked_up_cumulative",
            "prediction_cuts_min": list(CUTS_MIN),
            "status": "RESERVED_SYNTHETIC_TRUTH_NOT_OBSERVED_PUBLICLY",
            "secondary_only_if_native_supported": [
                "orders_ready_cumulative", "work_pending_orders",
                "post_payment_loss_cumulative"],
        },
        "units": {
            "accepted_orders": "orders",
            "work_pending": "orders",
            "orders_picked_up_cumulative": "orders",
            "rate": "orders/hour",
            "clock": "hours",
        },
        "representability": {
            "D": {"counter": "delivered", "status": "NOT_YET_DEMONSTRATED_FOR_COFFEE"},
            "M": {"counter": "deliveredTotal", "status": "NOT_YET_DEMONSTRATED_FOR_COFFEE",
                  "unchanged_catalog_response_time_min_hours": 0.1},
            "B": {"counter": None, "status": "NATIVE_OUTPUT_MAPPING_REQUIRED"},
        },
        "restrictions": {
            "initial_backlog": "ASSUMED_ZERO_NOT_OBSERVED",
            "cannot_infer": ["pre_payment_abandonment", "cashier_arrival_rate",
                             "barista_machine_parallelism", "customer_wait_p90",
                             "counterfactual_S1_to_S5", "net_profit"],
            "physical_model_executed": False,
            "fitted_to_pickups": False,
            "truth_access": False,
            "proprietary_generator_params_access": False,
        },
    }


def project_native_counter(raw_rows, *, arm, native_counter, time_unit):
    """Projection operator for trace *fixtures*, not proof that a model ran.

    Stable right-continuous sample-and-hold at all three prediction cuts.
    All duplicate time stamps are retained and the last emitted row at or before
    the cut is used; no artificial dt=0 derivative or future interpolation.
    A native validator must separately authenticate equations, model and CSV.
    """
    _need(arm in ARM_COUNTER and ARM_COUNTER[arm] == native_counter,
          "NATIVE_COUNTER_NOT_ATTESTED")
    _need(time_unit in ("hours", "minutes"), "TRACE_TIME_UNIT_INVALID")
    _need(isinstance(raw_rows, list) and bool(raw_rows), "EMPTY_NATIVE_TRACE")
    points = []
    previous_time, previous_value = -1.0, -1.0
    duplicate_times = 0
    for row in raw_rows:
        _need(isinstance(row, dict) and set(row) == {"time", native_counter},
              "NATIVE_TRACE_FIELDS_INVALID")
        try:
            t = float(row["time"])
            value = float(row[native_counter])
        except (TypeError, ValueError):
            raise ArenaError("COFFEE_DOMAIN_TRACE_NONNUMERIC") from None
        _need(math.isfinite(t) and math.isfinite(value) and
              t >= previous_time and t >= 0 and value >= 0 and
              value + 1e-8 >= previous_value,
              "TRACE_NOT_FINITE_MONOTONE_NONNEGATIVE")
        if t == previous_time:
            duplicate_times += 1
        previous_time, previous_value = t, value
        points.append((t * 60.0 if time_unit == "hours" else t, value))
    _need(points[0][0] <= CUTS_MIN[0] and points[-1][0] + 1e-8 >= CUTS_MIN[-1],
          "NATIVE_TRACE_COVERAGE_INCOMPLETE")
    values = {}
    for cut in CUTS_MIN:
        eligible = [value for t, value in points if t <= cut + 1e-8]
        _need(bool(eligible), "NO_NATIVE_SAMPLE_BEFORE_CUT")
        values[str(cut)] = {"orders_picked_up_cumulative": eligible[-1]}
    return {
        "schema": "arena.coffee-peak.trace-projection/1",
        "status": "ENGINEERING_PROJECTION_ONLY_NOT_NATIVE_VALIDATED",
        "arm": arm,
        "source_counter": native_counter,
        "time_unit": time_unit,
        "rule": "LAST_NATIVE_EMITTED_ROW_AT_OR_BEFORE_CUT_RIGHT_CONTINUOUS",
        "raw_samples_retained": len(points),
        "duplicate_timestamp_rows": duplicate_times,
        "predictions": values,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Public coffee case, no R2, vendor or solver")
    parser.add_argument("--public-dir", required=True)
    parser.add_argument("--assumptions", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        output = Path(args.out)
        _need(not output.exists(), "REFUSE_CASE_OVERWRITE")
        case = build_case(args.public_dir, args.assumptions)
        write_json(output, case, exclusive=True)
        print(json.dumps({"status": "PUBLIC_COFFEE_CASE_BUILT_NO_NATIVE",
                          "case_sha256": digest(case),
                          "paid_orders": case["input"]["public_paid_order_count_before_cut"],
                          "rate_orders_per_hour": case["input"]["rate_orders_per_hour"]},
                         sort_keys=True))
        return 0
    except (ArenaError, OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "STOPPED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
