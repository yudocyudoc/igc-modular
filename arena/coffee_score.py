"""Reserved synthetic coffee measurements, callable ONLY after a verified real lock.

No CLI, R2 access, or automatic scoring path is exposed in this increment.
The current P3 READINESS_ONLY lock is deliberately incapable of passing the
scientific gate. This module makes the future evaluator's numeric contract
explicit and testable without leaking any truth to producer jobs.
"""
from __future__ import annotations

from collections import defaultdict
import math

from .coffee_peak import _load_package, _number, _rows, ROOT
from .common import ArenaError
from .coffee_custody import require_real_lock_before_reveal

PREDICTION_CUTS = (80.0, 100.0, 103.237)


def _need(ok, msg):
    if not ok:
        raise ArenaError("COFFEE_SCORE_" + msg)


def _population(cfg, row):
    target = cfg["selection"]
    return (row["scenario_id"] == target["scenario_id"]
            and row["replication"] == str(target["replication"])
            and row["day_of_week"] == str(target["day_of_week"]))


def _pct90(values):
    if not values:
        return None
    # Empirical nearest rank; explicitly not an interpolated estimator.
    v = sorted(values)
    return v[math.ceil(0.9 * len(v)) - 1]


def reserved_measurements(zf, cfg):
    """Compute labeled oracle metrics for one synthetic day; never call in a producer.

    This includes truth-only waiting/abandonment; it is NOT a business forecast.
    POS is only a payment/refund event, not an order completion.
    """
    cut = cfg["construction_end_min"]
    end = cfg["window_end_min"]
    _need(float(cut).is_integer() and 0 < cut < end, "BAD_CUT")
    pos = []
    for row in _rows(zf, ROOT + "pos_observed.csv", ("scenario_id", "replication",
        "day_of_week", "pos_record_type", "timestamp_min_from_peak_start",
        "amount_mxn", "refund_amount_mxn", "synthetic", "source_class")):
        if _population(cfg, row):
            _need(row["synthetic"].lower() == "true"
                  and row["source_class"] == "synthetic_pos_view", "POS_PROVENANCE_INVALID")
            t = _number(row["timestamp_min_from_peak_start"], "pos_time")
            _need(t >= 0, "NEGATIVE_POS_TIME")
            if t <= end:
                pos.append((t, row))
    _need(bool(pos), "EMPTY_SELECTED_POS")
    order_rows = []
    for row in _rows(zf, ROOT + "ordenes_truth.csv", ("scenario_id", "replication",
            "day_of_week", "party_id", "order_id", "status", "arrival_min",
            "payment_min", "ready_min", "prep_wait_min", "variable_cost_mxn_synthetic",
            "synthetic", "source_class")):
        if _population(cfg, row):
            _need(row["synthetic"].lower() == "true"
                  and row["source_class"] == "synthetic_scenario", "TRUTH_PROVENANCE_INVALID")
            arrival = _number(row["arrival_min"], "truth_arrival")
            _need(arrival >= 0, "NEGATIVE_ARRIVAL")
            if arrival <= end:
                order_rows.append(row)
    _need(bool(order_rows), "EMPTY_SELECTED_TRUTH")
    events=[]
    for row in _rows(zf, ROOT + "eventos_truth.csv", ("scenario_id", "replication",
            "day_of_week", "event_id", "party_id", "order_id", "event_type",
            "time_min_from_peak_start", "synthetic", "source_class")):
        if _population(cfg,row):
            _need(row["synthetic"].lower()=="true"
                  and row["source_class"]=="synthetic_scenario", "EVENT_PROVENANCE_INVALID")
            t=_number(row["time_min_from_peak_start"],"event_time")
            _need(t>=0,"NEGATIVE_EVENT_TIME")
            if t<=end:events.append((t,row))
    outputs={}
    for t in PREDICTION_CUTS:
        sales=[row for pt,row in pos if pt<=t and row["pos_record_type"]=="sale"]
        refunds=[row for pt,row in pos if pt<=t and row["pos_record_type"]=="refund"]
        completed={row["order_id"] for et,row in events
                   if et<=t and row["event_type"]=="order_ready_for_pickup"
                   and row["order_id"]}
        pickups={row["order_id"] for et,row in events
                 if et<=t and row["event_type"]=="customer_party_picks_up_order"
                 and row["order_id"]}
        # Abandonment stage belongs to the truth state, not the public POS.
        # Event times, not arrival cohort, determine *when* abandonment occurs.
        abandon={row["party_id"] for et,row in events if et<=t
                 and row["event_type"] in
                 ("customer_party_abandons_after_order",
                  "customer_party_abandons_queue_before_order")
                 and row.get("party_id")}
        waits=[_number(x["prep_wait_min"],"prep_wait") for x in order_rows
               if x["prep_wait_min"] not in (None, "")
               and x["ready_min"] not in (None, "")
               and _number(x["ready_min"],"ready_time")<=t]
        outputs[str(t)]={
            "paid_sales_cumulative": len(sales),
            "paid_revenue_mxn_cumulative": round(sum(_number(x["amount_mxn"], "sale_amount") for x in sales),6),
            "refund_amount_mxn_cumulative": round(sum(_number(x["refund_amount_mxn"], "refund") for x in refunds),6),
            "orders_ready_cumulative": len(completed),
            "orders_picked_up_cumulative": len(pickups),
            "abandonment_count_truth_by_arrival_cohort": len(abandon),
            "prep_wait_p90_min_truth_completed": _pct90(waits),
        }
    # Counts and revenue are not independently observed; all are synthetic.
    return {"schema":"arena.coffee-peak.reserved-metrics/1",
            "evidence_kind":"SYNTHETIC_ORACLE_ONLY_NOT_REAL_CAFE",
            "scenario":dict(cfg["selection"]),
            "construction_end_min":cut,"window_end_min":end,
            "metrics":outputs,
            "profit_mxn":"NOT_IDENTIFIABLE_NO_FIXED_COSTS",
            "policies_S1_to_S5":"NOT_GENERATED_NOT_EVALUABLE"}


def score_prediction(lock, oracle, *, native_attestor=None):
    """Fail closed until engine-native attestation is externally implemented.

    Passing a literal truthy value is never sufficient. The default rejects.
    The future native attestor must validate model bytes, native receipts,
    model/forecast coupling, and the original source identity for every arm.
    """
    _need(callable(native_attestor), "NATIVE_ATTESTATION_NOT_CONFIGURED")
    _need(lock.get("mode") == "SCIENTIFIC" and lock.get("schema") ==
          "arena.coffee-peak.prediction-lock/1", "SCIENTIFIC_LOCK_REQUIRED")
    _need(native_attestor(lock) is True, "NATIVE_ATTESTATION_FAILED")
    scores={}
    for arm in ("D","B","M"):
        candidate=lock["arms"][arm]
        if candidate["status"]!="PREDICTED":
            scores[arm]={"status":candidate["status"],"mae_paid_sales":None}
            continue
        forecast=candidate["predictions"]
        actual=oracle["metrics"]
        _need(isinstance(forecast,dict) and set(forecast)==set(actual), "FORECAST_CUTS_INVALID")
        err=[]
        for t in forecast:
            v=forecast[t].get("paid_sales_cumulative")
            _need(type(v) in (int,float) and math.isfinite(v) and v>=0,
                  "PREDICTION_INVALID")
            err.append(abs(v-actual[t]["paid_sales_cumulative"]))
        scores[arm]={"status":"PREDICTED", "mae_paid_sales":sum(err)/len(err)}
    return {"schema":"arena.coffee-peak.paired-score/1",
            "evidence_kind":"SYNTHETIC_ORACLE_NATIVE_ATTESTED",
            "scores":scores,"business_recommendation":None}


def guarded_reserved_score(storage, cfg, lock, archive, *, native_attestor=None,
                           archive_attestor=None):
    """Only a verified SCIENTIFIC archive can trigger any private R2 read.

    Not wired to GitHub Actions until a genuine coffee-domain engine validator
    exists. Tests assert zero storage.get calls for READINESS_ONLY/fake archive.
    """
    # Caller-supplied booleans are not authentication: require an independently
    # implemented GitHub API/artifact verifier before touching R2.
    _need(callable(archive_attestor) and archive_attestor(lock, archive) is True,
          "EXTERNAL_GITHUB_ARCHIVE_VERIFICATION_REQUIRED")
    require_real_lock_before_reveal(lock, archive)
    _need(callable(native_attestor) and native_attestor(lock) is True,
          "AUTHENTIC_NATIVE_REQUIRED_BEFORE_R2_READ")
    _need(lock["source_package_sha256"] == cfg["source"]["sha256"]
          and lock["construction_end_exclusive"] == cfg["construction_end_min"],
          "LOCK_SOURCE_OR_CUT_MISMATCH")
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from .coffee_custody import source_key
    with TemporaryDirectory() as temp:
        package=Path(temp)/"reserved.zip"
        storage.get(source_key(cfg["source"]["sha256"]),package)
        zf,_=_load_package(package,cfg["source"]["sha256"])
        with zf:oracle=reserved_measurements(zf,cfg)
    return score_prediction(lock,oracle,native_attestor=native_attestor)
