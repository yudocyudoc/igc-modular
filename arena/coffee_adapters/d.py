"""D coffee adapter: original six stock-flow graphs, no invented delivery data."""
from __future__ import annotations

import sys
from pathlib import Path

from arena.common import digest
from .shared import VENDOR_ROOT, case_guard, emit, need


def original():
    need((VENDOR_ROOT / "scripts" / "arena_d_v01.py").is_file(), "D_SOURCE_MISSING")
    # Exactly the original vendored grammar; never copy equations into the adapter.
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    from scripts import arena_d_v01
    return arena_d_v01


def generate(case):
    case_guard(case)
    src = original()
    p = case["hypotheses"]["parameters"]
    loss_hazard = p["post_payment_loss_rate"]["value"]
    need(loss_hazard > 0, "D_LOSS_GRAMMAR_REQUIRES_POSITIVE_HAZARD")
    nominal = {
        "capacity": p["service_capacity"]["value"],
        "response_time": p["response_time"]["value"],
        "loss_time": 1.0 / loss_hazard,
    }
    pulse = {"kind": "pulse", "rate": case["input"]["rate_orders_per_hour"],
             "duration": case["time"]["horizon_hours"]}
    rows = []
    files = {}
    # Mirrors the ORIGINAL enumerate order (1..3 stocks, no-loss then loss).
    # Calling generate() would require fictitious construction observations.
    for n in range(1, 4):
        for loss in (False, True):
            graph = src.topology(n, loss)
            lint = src.lint_structure(graph)
            key = src.digest(graph)
            candidate = {"structure": graph, "structure_hash": key,
                         "nominal_parameters": dict(nominal)}
            body = src.modelica(candidate, pulse)
            cls = "DStockFlow_" + key[7:19]
            filename = cls + ".mo"
            need(filename not in files, "D_DUPLICATE_MODEL")
            files[filename] = body
            rows.append({
                "id": "D-" + key[7:19], "modelica_class": cls,
                "modelica_file": filename, "structure_hash": key,
                "structure": graph, "lint": lint,
                "nominal_parameters": dict(nominal),
                "parameter_status": "ASSUMED_NOT_FITTED",
                "source_primitive": "scripts.arena_d_v01.topology/lint_structure/modelica",
                "physical_counter": "delivered", "work_pending": list(graph["stocks"]),
                "lost_after_payment": "lost" if loss else None,
            })
    need(len(rows) == 6 and len(files) == 6, "D_SIX_REQUIRED")
    manifest = {
        "arm": "D", "method": src.METHOD, "method_schema": src.SCHEMA,
        "adapter": "coffee-d-native/1", "original_enumeration": "STOCKS_1_TO_3_NO_LOSS_THEN_LOSS",
        "candidate_count": 6, "candidates": rows, "input_profile": pulse,
        "nominal_parameters": nominal,
        "interpretation": {"input": "paid orders/hour assumed constant after construction",
                           "delivered": "cumulative order pickups, not POS payments",
                           "lost": "possible post-payment loss only, not prepurchase abandonment",
                           "stocks": "aggregate in-progress paid orders"},
        "unsupported": ["cashier", "barista_machine_resource_coupling",
                        "recipes", "individual_wait_p90", "prepayment_abandonment",
                        "S1_to_S5_as_business_policies"],
        "native_preparation": "PRIMITIVES_WITHOUT_FAKE_DELIVERED_OBSERVATIONS",
        "has_measured_pickups_for_calibration": False,
    }
    return files, manifest


def prepare(case, out):
    need(not Path(out).exists(), "REFUSE_OVERWRITE")
    files, manifest = generate(case)
    return emit(out, "D", case, files, manifest)
