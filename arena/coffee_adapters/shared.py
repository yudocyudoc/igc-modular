"""Common admission, provenance and immutable file emission for coffee D/M.

Only the public coffee case is accepted. This module never touches R2, the ZIP,
private linkage, a provider or the solver. Real vendored producers are invoked
by their respective adapters and are not substituted with local equations.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from arena.common import ArenaError, digest, write_json
from arena.coffee_domain import SCHEMA, validate_assumptions, CUTS_MIN, WINDOW_END_MIN

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "_vendor" / "igc"


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_NATIVE_" + code)


def case_guard(case):
    """Strict public-case gate; no field can be introduced as a truth shortcut."""
    need(isinstance(case, dict) and case.get("schema") == SCHEMA, "CASE_SCHEMA")
    need(case.get("protocol") == "coffee_peak_capacity_v1" and
         case.get("condition") == "B0" and case.get("frontier") == "PAID_ORDER_TO_PICKUP",
         "CASE_FRONTIER")
    t = case.get("time", {})
    need(isinstance(t, dict) and t.get("native_unit") == "hours" and
         t.get("public_unit") == "minutes" and
         t.get("construction_end_min") == 60 and
         t.get("window_end_min") == WINDOW_END_MIN and
         t.get("horizon_hours") == WINDOW_END_MIN / 60.0 and
         t.get("prediction_cuts_min") == list(CUTS_MIN), "CASE_CLOCK")
    inp = case.get("input", {})
    paid = inp.get("public_paid_order_count_before_cut")
    need(type(paid) is int and paid > 0 and
         inp.get("rate_orders_per_hour") == paid and
         inp.get("shape") == "RECTANGULAR_CONSTANT_RATE" and
         inp.get("future_rate_origin") == "ASSUMED_CONSTANT_NOT_OBSERVED" and
         inp.get("meaning") == "ACCEPTED_PAID_ORDERS_NOT_CUSTOMER_ARRIVALS" and
         inp.get("payment_is_pickup") is False, "CASE_INPUT")
    need(case.get("observables", {}).get("primary") == "orders_picked_up_cumulative" and
         case.get("observables", {}).get("prediction_cuts_min") == list(CUTS_MIN),
         "CASE_OBSERVABLE")
    need(isinstance(case.get("selection"), dict) and
         set(case["selection"]) == {"scenario_id", "replication", "day_of_week"} and
         isinstance(case.get("source_package_sha256"), str) and
         isinstance(case.get("public_sha256"), str), "CASE_IDENTITY")
    hypotheses = validate_assumptions(case.get("hypotheses"))
    need(case.get("hypotheses_sha256") == digest(hypotheses), "CASE_PRIORS_HASH")
    restrictions = case.get("restrictions", {})
    need(restrictions.get("physical_model_executed") is False and
         restrictions.get("fitted_to_pickups") is False and
         restrictions.get("truth_access") is False, "CASE_HAS_PRIVATE_EVIDENCE")
    return case


def sha_bytes(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def emit(output, arm, case, files, manifest):
    """Create-once and hash exact bytes; never overwrite an experimental record."""
    out = Path(output)
    need(not out.exists(), "REFUSE_OVERWRITE")
    need(set(files).isdisjoint({"manifest.json"}) and
         all("/" not in name and "\\" not in name and name not in ("", ".", "..")
             for name in files), "UNSAFE_NATIVE_FILE")
    need(manifest.get("arm") == arm, "MANIFEST_ARM")
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, content in sorted(files.items()):
        need(isinstance(content, (str, bytes)), "INVALID_NATIVE_BYTES")
        raw = content.encode("utf-8") if isinstance(content, str) else content
        with (out / name).open("xb") as stream:
            stream.write(raw)
        hashes[name] = {"sha256": sha_bytes(raw), "bytes": len(raw)}
    record = {
        **manifest,
        "schema": "arena.coffee-peak.native-preparation/1",
        "public_case_sha256": digest(case),
        "public_sha256": case["public_sha256"],
        "source_package_sha256": case["source_package_sha256"],
        "selection": case["selection"],
        "frozen_sha": case["frozen_sha"],
        "run_id": case["run_id"],
        "hypotheses_sha256": case["hypotheses_sha256"],
        "files": hashes,
        "provider_posts": 0,
        "new_omc": 0,
        "solver_status": "NOT_RUN",
        "truth_access": False,
        "parameter_status": "PUBLIC_HYPOTHESES_NOT_FITTED_TO_PICKUPS",
        "model_validation": "GENERATED_NOT_COMPILED_OR_SIMULATED",
    }
    write_json(out / "manifest.json", record, exclusive=True)
    return record
