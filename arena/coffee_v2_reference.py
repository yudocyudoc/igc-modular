"""Coffee V2.1 P06/P07/P10: deterministic physical reference, NOT D/M/B.

Frontier: synthetic paid POS -> modeled order handoff. No actual customer
arrivals, observed pickups, service-time calibration, stock of ingredients,
abandonment, real profit, or G3. Only explicit ASSUMED/BOUNDED parameters.
Resource acquisition is atomic and exclusive; automatic espresso releases
the barista to perform compatible work concurrently on other drinks.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import heapq
import itertools
import json
import math
from pathlib import Path
import sys

from .common import ArenaError, digest, write_json
from . import coffee_v2_reference_inputs as ingress

SCHEMA = "arena.coffee-v2.reference-physical/1"
DOSSIER = "arena.coffee-v2.reference-dossier/1"
FRONTIER = "SYNTHETIC_PAID_POS_TO_MODELED_HANDOFF"
RESOURCES = ("barista", "espresso_group", "steam_wand", "prep_space",
             "pickup_pass", "existing_support")
DURATIONS = ("manual_setup_min", "espresso_auto_min",
             "milk_finish_min", "handoff_min")
ARCHETYPES = ("solo_extraccion", "con_leche")
S5 = "S5_TRANSFER_HANDOFF_TO_EXISTING_SUPPORT"
SCOPES = {
    "no_cashier_arrivals": True,
    "no_pre_payment_abandonment": True,
    "no_post_payment_abandonment": True,
    "no_inventory_or_cost_calibration": True,
    "milk_after_extract_serial_per_beverage": True,
    "no_batching": True,
    "no_real_pickup_observations": True,
}


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_V2_REFERENCE_" + code)


def num(value, label, low=0, high=180):
    need(type(value) in (float, int), "NUMERIC_TYPE_" + label)
    n = float(value)
    need(math.isfinite(n) and low <= n <= high, "NUMERIC_RANGE_" + label)
    return n


def config_gate(d):
    need(type(d) is dict and set(d) == {
        "schema", "frontier", "policy", "resources", "durations",
        "initial_open_orders", "scope_limits"}, "DOSSIER_FIELDS")
    need(d["schema"] == DOSSIER and d["frontier"] == FRONTIER,
         "DOSSIER_IDENTITY")
    need(d["policy"] in ("B0", S5), "UNSUPPORTED_POLICY")
    need(d["scope_limits"] == SCOPES, "EXPLICIT_PROCESS_SCOPE_REQUIRED")
    need(type(d["resources"]) is dict and
         set(d["resources"]) == set(RESOURCES), "RESOURCE_DOSSIER")
    need(type(d["durations"]) is dict and
         set(d["durations"]) == set(DURATIONS), "DURATION_DOSSIER")
    resources = {}
    durations = {}
    for name, item in d["resources"].items():
        need(type(item) is dict and
             set(item) == {"units", "status", "evidence"} and
             type(item["units"]) is int and 0 <= item["units"] <= 8,
             "RESOURCE_CONTRACT_" + name)
        need(item["status"] in ("ASSUMED", "BOUNDED") and
             type(item["evidence"]) is str and len(item["evidence"].strip()) >= 8,
             "RESOURCE_NOT_EXPLICIT_SCENARIO_" + name)
        resources[name] = item["units"]
    for r in ("barista", "espresso_group", "prep_space", "pickup_pass"):
        need(resources[r] >= 1, "MISSING_EXCLUSIVE_RESOURCE_" + r)
    if d["policy"] == S5:
        need(resources["existing_support"] >= 1, "S5_NEEDS_EXISTING_SUPPORT")
    for name, item in d["durations"].items():
        need(type(item) is dict and
             set(item) == {"value", "bounds", "status", "evidence"} and
             type(item["bounds"]) is list and len(item["bounds"]) == 2,
             "DURATION_CONTRACT_" + name)
        need(item["status"] in ("ASSUMED", "BOUNDED") and
             type(item["evidence"]) is str and len(item["evidence"].strip()) >= 8,
             "DURATION_NOT_EXPLICIT_SCENARIO_" + name)
        val = num(item["value"], name, 0, 30)
        lo = num(item["bounds"][0], name + "_LOWER", 0, 30)
        hi = num(item["bounds"][1], name + "_UPPER", 0, 30)
        need(0 < lo <= val <= hi, "DURATION_OUT_OF_BOUNDS_" + name)
        durations[name] = val
    initial = d["initial_open_orders"]
    need(type(initial) is dict and
         set(initial) == {"value", "status", "evidence"} and
         type(initial["value"]) is int and initial["value"] == 0 and
         initial["status"] == "ASSUMED" and
         type(initial["evidence"]) is str and
         len(initial["evidence"].strip()) >= 8,
         "UNKNOWN_INITIAL_STOCK_CANNOT_BE_SILENT_ZERO")
    return resources, durations



def counterfactual_pair_gate(base, intervention):
    """For future P11: S5 only reassigns existing handoff, nothing else."""
    config_gate(base)
    config_gate(intervention)
    need(base["policy"] == "B0" and intervention["policy"] == S5,
         "PAIR_REQUIRES_B0_AND_S5")
    left = {k: v for k, v in base.items() if k != "policy"}
    right = {k: v for k, v in intervention.items() if k != "policy"}
    need(left == right, "POLICY_CANNOT_SECRETLY_CHANGE_RESOURCES_OR_TIMES")
    return {"scenario_dossier_sha256": digest(left),
            "comparison_is_conditional_not_executed": True}


def paid_gate(positions, lines, horizon):
    horizon = num(horizon, "HORIZON", 0, 180)
    need(horizon > 0 and type(positions) is list and type(lines) is list and
         len(positions) <= 10000 and len(lines) <= 16000, "INPUT_SIZE")
    paid, seen_pos, seen_lines = {}, set(), set()
    refunds = 0
    beverage_units = 0
    for p in positions:
        need(type(p) is dict and set(p) == {
            "pos_event_id", "order_id", "time_min", "kind", "beverage_count"},
            "PAYMENT_FIELDS")
        pid, oid = p["pos_event_id"], p["order_id"]
        need(type(pid) is str and pid and pid not in seen_pos and
             type(oid) is str and oid, "DUPLICATE_OR_EMPTY_POS")
        seen_pos.add(pid)
        t = num(p["time_min"], "PAID_TIME", 0, horizon)
        need(t < horizon, "PAID_AFTER_PEAK_CUT")
        if p["kind"] == "refund":
            need(p["beverage_count"] is None, "REFUND_NOT_NEW_WORK")
            refunds += 1
            continue
        need(p["kind"] == "sale" and
             type(p["beverage_count"]) is int and
             1 <= p["beverage_count"] <= 30 and
             oid not in paid, "INVALID_UNIQUE_PAID_ORDER")
        paid[oid] = {"pos": pid, "time": t,
                     "beverages": p["beverage_count"], "items": []}
    need(len(paid) <= 5000, "ORDER_CAP")
    for x in lines:
        need(type(x) is dict and set(x) == {
            "line_id", "pos_event_id", "order_id",
            "time_min", "archetype", "quantity"}, "LINE_FIELDS")
        lid = x["line_id"]
        need(type(lid) is str and lid and lid not in seen_lines,
             "DUPLICATE_LINE")
        seen_lines.add(lid)
        o = paid.get(x["order_id"])
        need(o is not None and o["pos"] == x["pos_event_id"],
             "ORPHAN_OR_REFUND_LINE")
        need(abs(num(x["time_min"], "LINE_TIME", 0, horizon) -
                 o["time"]) <= 1e-4, "LINE_PAYMENT_CLOCK")
        need(x["archetype"] in ARCHETYPES and
             type(x["quantity"]) is int and 1 <= x["quantity"] <= 30,
             "UNSUPPORTED_ITEM_OR_QUANTITY")
        o["items"].extend([x["archetype"]] * x["quantity"])
        beverage_units += x["quantity"]
        need(beverage_units <= 16000, "BEVERAGE_CAP")
    need(all(len(o["items"]) == o["beverages"] for o in paid.values()),
         "ORDER_TO_BEVERAGE_MASS_BALANCE")
    return paid, refunds, beverage_units


def percentile(values, fraction):
    if not values:
        return None
    a = sorted(values)
    rank = (len(a)-1)*fraction
    lo, hi = math.floor(rank), math.ceil(rank)
    return a[lo] if lo == hi else a[lo]*(hi-rank)+a[hi]*(rank-lo)


def support_calendar_gate(windows, horizon):
    """Illustrative reserved time for EXISTING support's other duties.

    Windows are hard reservations, not newly hired staff or a measurement.
    A whole handoff must fit inside a free interval; it cannot displace
    other tasks. All reserved intervals end at the peak cut; drain is free.
    """
    need(type(windows) in (list, tuple) and len(windows) <= 100,
         "SUPPORT_CALENDAR_SIZE")
    accepted = []
    last = 0.0
    for pair in windows:
        need(type(pair) in (tuple, list) and len(pair) == 2,
             "SUPPORT_WINDOW_SHAPE")
        start = num(pair[0], "SUPPORT_BUSY_START", 0, horizon)
        end = num(pair[1], "SUPPORT_BUSY_END", 0, horizon)
        need(last <= start < end <= horizon,
             "SUPPORT_CALENDAR_NOT_ORDERED_OR_OVERLAP")
        accepted.append((start, end))
        last = end
    return accepted


def _engine(positions, lines, dossier, horizon, *, support_busy_windows=()):
    cap, dur = config_gate(dossier)
    paid, refunds, beverages = paid_gate(positions, lines, horizon)
    reserved = support_calendar_gate(support_busy_windows, horizon)
    need(cap["steam_wand"] > 0 or not any(
        "con_leche" in o["items"] for o in paid.values()),
        "MILK_REQUIRES_STEAM_WAND")
    events, ready = [], []
    nonce = itertools.count()
    stages = {}
    remaining = {}
    finished = {}
    inuse = Counter()
    maxuse = Counter()
    busy = defaultdict(float)
    ops = Counter()
    private_intervals = []  # available to tests only; never in public result
    for first, end in reserved:
        # Wake blocked handoffs at each availability boundary; these events
        # change no other resource and cannot count as synthetic payments.
        heapq.heappush(events, (end, 0, next(nonce), "calendar", None))
    for oid, order in paid.items():
        remaining[oid] = len(order["items"])
        for index, typ in enumerate(order["items"]):
            stages[(oid, index)] = (
                ("manual_setup", "espresso_auto", "milk_finish")
                if typ == "con_leche" else
                ("manual_setup", "espresso_auto"))
        heapq.heappush(events, (order["time"], 1, next(nonce), "arrive", oid))

    def needed(task):
        stage = task["stage"]
        if stage == "manual_setup":
            return ("barista", "prep_space"), dur["manual_setup_min"]
        if stage == "espresso_auto":
            return ("espresso_group",), dur["espresso_auto_min"]
        if stage == "milk_finish":
            return ("barista", "steam_wand", "prep_space"), dur["milk_finish_min"]
        need(stage == "handoff", "UNKNOWN_STAGE")
        who = "barista" if dossier["policy"] == "B0" else "existing_support"
        return (who, "pickup_pass"), dur["handoff_min"]

    processed = 0
    while events or ready:
        need(bool(events), "RESOURCE_DEADLOCK")
        t = events[0][0]
        need(math.isfinite(t), "CLOCK_NONFINITE")
        while events and events[0][0] == t:
            _, _, _, kind, datum = heapq.heappop(events)
            processed += 1
            need(processed <= 120000, "EVENT_LIMIT")
            if kind == "calendar":
                continue
            if kind == "arrive":
                for index in range(len(paid[datum]["items"])):
                    ready.append({"job": (datum, index), "stage": "manual_setup"})
            else:
                need(kind == "finish", "EVENT_TYPE")
                task, req, started = datum
                for r in req:
                    inuse[r] -= 1
                    need(inuse[r] >= 0, "RESOURCE_UNDERFLOW")
                    busy[r] += t - started
                stage = task["stage"]
                ops[stage] += 1
                private_intervals.append((stage, started, t, req))
                oid, index = task["job"]
                if stage == "handoff":
                    need(oid not in finished and remaining[oid] == 0,
                         "HANDOFF_BEFORE_ALL_ITEMS")
                    finished[oid] = t
                else:
                    sequence = stages[(oid, index)]
                    step = sequence.index(stage)+1
                    if step < len(sequence):
                        ready.append({"job": (oid, index),
                                      "stage": sequence[step]})
                    else:
                        remaining[oid] -= 1
                        need(remaining[oid] >= 0, "NEGATIVE_PENDING_ITEMS")
                        if remaining[oid] == 0:
                            ready.append({"job": (oid, -1),
                                          "stage": "handoff"})
        waiting = []
        for task in ready:
            req, duration = needed(task)
            blocked_by_other_work = (
                dossier["policy"] == S5 and task["stage"] == "handoff"
                and any(t < end and t + duration > first
                        for first, end in reserved))
            if blocked_by_other_work:
                waiting.append(task)
                continue
            if all(inuse[r] < cap[r] for r in req):
                for r in req:
                    inuse[r] += 1
                    need(inuse[r] <= cap[r], "RESOURCE_OVERBOOKED")
                    maxuse[r] = max(maxuse[r], inuse[r])
                heapq.heappush(events, (t+duration, 0, next(nonce),
                                        "finish", (task, req, t)))
            else:
                waiting.append(task)
        ready = waiting

    need(len(finished) == len(paid) and
         all(n == 0 for n in remaining.values()) and
         all(n == 0 for n in inuse.values()),
         "FINAL_MASS_RESOURCE_BALANCE")
    inside = sum(t < horizon for t in finished.values())
    pending = len(paid) - inside
    delays = [t-paid[oid]["time"] for oid, t in finished.items()]
    need(all(x >= 0 for x in delays) and
         ops["handoff"] == len(paid) and
         ops["espresso_auto"] == ops["manual_setup"] == beverages,
         "CONSERVATION_GATE")
    result = {
        "schema": SCHEMA,
        "status": "VERIFIED_CONDITIONAL_REFERENCE_NOT_G3",
        "frontier": FRONTIER,
        "policy": dossier["policy"],
        "synthetic_paid_orders": len(paid),
        "synthetic_refunds_not_negative_handoffs": refunds,
        "synthetic_beverage_units": beverages,
        "modeled_handoffs_during_halfopen_peak": inside,
        "modeled_orders_open_at_peak_cut": pending,
        "modeled_handoffs_after_peak_in_drain": pending,
        "modeled_final_open_orders": 0,
        "modeled_paid_to_handoff_p50_full_drain_min": percentile(delays, .5),
        "modeled_paid_to_handoff_p90_full_drain_min": percentile(delays, .9),
        "stage_operation_counts": {stage: ops[stage] for stage in (
            "manual_setup", "espresso_auto", "milk_finish", "handoff")},
        "resources": {r: {"units_assumed": cap[r],
                          "max_simultaneous_occupied": maxuse[r],
                          "busy_unit_minutes_full_drain": round(busy[r], 10)}
                      for r in RESOURCES},
        "horizon_end_exclusive_min": horizon,
        "existing_support_other_work_reserved_unit_minutes_in_peak_assumed":
            round(sum(end-first for first, end in reserved), 10),
        "support_busy_calendar_is_explicit_unmeasured_scenario": True,
        "existing_support_other_duties_protected_not_simulated": True,
        "initial_unfinished_orders_assumed_zero_not_observed": True,
        "no_observed_pickup_wait_or_real_utilization": True,
        "not_an_observation_of_capacity_or_bottleneck": True,
        "modeled_full_drain_percentiles_not_observed_window_percentiles": True,
        "no_real_contribution_or_policy_recommendation": True,
        "engine_role": "SPECIALIZED_REFERENCE_NOT_D_M_B_OR_GENERATOR",
        "external_cost": {"R2": 0, "OMC": 0, "POST": 0, "G3": 0},
    }
    return result, private_intervals, finished


def simulate(positions, items, dossier, horizon, *, support_busy_windows=()):
    """Only aggregates; optional protected time for existing support work."""
    return _engine(positions, items, dossier, horizon,
                   support_busy_windows=support_busy_windows)[0]


def run(view_dir, case_id, day, dossier):
    records = ingress.select_case_day(view_dir, case_id, day)
    result = simulate(records["positions"], records["items"], dossier,
                      records["horizon"])
    result.update({
        "opaque_case_id": case_id,
        "selected_day": day,
        "partition": records["partition"],
        "producer_manifest_sha256": records["manifest_sha256"],
        "source_package_sha256": records["source_sha256"],
        "dossier_sha256": digest(dossier),
        "source_coverage": records["coverage"],
        "identifiability_register": {
            "modeled_durations": {
                name: {"status": x["status"], "bounds_min": x["bounds"],
                       "source_type": "UNVERIFIED_DECLARED_SCENARIO"}
                for name, x in dossier["durations"].items()},
            "modeled_resources": {
                name: {"status": x["status"], "units": x["units"],
                       "source_type": "UNVERIFIED_DECLARED_SCENARIO"}
                for name, x in dossier["resources"].items()},
            "real_resource_occupation": "NOT_IDENTIFIABLE_FOR_THIS_CASE",
            "real_customer_arrivals": "NOT_IDENTIFIABLE_FOR_THIS_CASE",
            "real_paid_to_pickup_wait": "NOT_IDENTIFIABLE_FOR_THIS_CASE",
            "real_revenue_and_contribution": "NOT_IDENTIFIABLE_FOR_THIS_CASE",
        },
        "fitted_to_private_truth": False,
        "calibrated_to_observed_delivery": False,
    })
    return result


def export(result, path):
    path = Path(path)
    need(not path.exists(), "OUTPUT_ALREADY_EXISTS")
    path.mkdir(parents=True, mode=0o700)
    write_json(path/"reference-conditional.json", result, exclusive=True)
    (path/"REVIEW.md").write_text("\n".join([
        "# P06/P07/P10 — Referencia física condicional",
        "",
        "Borde: POS sintético pagado -> handoff modelado.",
        "No hay medición física de capacidad ni espera real.",
        "Supuestos y recursos explícitos; sin uso de verdad o G3.",
        "No se deduce una recomendación empresarial de este modelo.",
        "Pedidos pagados: " + str(result["synthetic_paid_orders"]),
        "Handoffs dentro de ventana: " +
            str(result["modeled_handoffs_during_halfopen_peak"]),
        "Pendientes al corte: " +
            str(result["modeled_orders_open_at_peak_cut"]),
        "Drenaje posterior separado de la ventana.",
    ]) + "\n", encoding="utf-8")
    write_json(path/"receipt.json", {
        "schema": SCHEMA,
        "source_manifest_sha256": result["producer_manifest_sha256"],
        "reference_result_sha256":
            "sha256:" + ingress.sha_file(path/"reference-conditional.json"),
        "dossier_sha256": result["dossier_sha256"],
        "paid_attempts": 0, "g3_opened": False,
    }, exclusive=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline coffee reference; NO G3")
    parser.add_argument("--views", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--day", type=int, required=True)
    parser.add_argument("--dossier", required=True)
    parser.add_argument("--out", required=True)
    options = parser.parse_args(argv)
    try:
        dossier = json.loads(Path(options.dossier).read_text("utf-8"))
        result = run(options.views, options.case_id, options.day, dossier)
        export(result, options.out)
        print(json.dumps({"status": result["status"],
                          "paid_orders": result["synthetic_paid_orders"],
                          "provider_calls": 0}, sort_keys=True))
        return 0
    except (ArenaError, OSError, TypeError, KeyError, ValueError,
            json.JSONDecodeError) as exc:
        print(json.dumps({"status": "STOPPED",
                          "reason": str(exc) if isinstance(exc, ArenaError)
                          else "INVALID_INPUT_OR_DOSSIER"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
