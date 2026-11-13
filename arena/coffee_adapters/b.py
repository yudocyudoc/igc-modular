"""Public-only Buffalo coffee construction; never executes a provider or solver.

The real original Engine.generate is exercised separately in coffee_runner.mjs
with an explicitly offline JSON-mode transport fixture. A fixture is not a
native scientific model and must never be eligible for the scientific lock.
"""
from __future__ import annotations
import json
from pathlib import Path

from arena.common import ArenaError, digest, read_json, write_json
from arena.coffee_adapters.shared import case_guard

SCHEMA = "arena.coffee-peak.buffalo-public-input/1"
MODE = "OFFLINE_FIXTURE_CONTRACT_ONLY"


def need(condition, reason):
    if not condition:
        raise ArenaError("COFFEE_B_" + reason)


def make_payload(case):
    case_guard(case)
    time = case["time"]
    source = case["input"]
    params = case["hypotheses"]["parameters"]
    need(source["future_rate_origin"] == "ASSUMED_CONSTANT_NOT_OBSERVED" and
         source["payment_is_pickup"] is False, "INPUT_NOT_ACCEPTED_PAID_ORDERS")
    need(params["workload_per_paid_order"]["value"] == 1 and
         params["workload_per_paid_order"]["admissible_range"] == [1, 1],
         "UNSUPPORTED_NONUNIT_WORKLOAD")
    # No diagrams, equations, source ZIP, rival hypotheses, or holdout are sent.
    common = {
        "frontier": "PAID_ORDER_TO_PICKUP",
        "input_meaning": "ACCEPTED_PAID_ORDERS_NOT_CUSTOMER_ARRIVALS",
        "input_rate_orders_per_hour": source["rate_orders_per_hour"],
        "future_input": "RECTANGULAR_RATE_ASSUMPTION_NOT_OBSERVED_AFTER_MINUTE_60",
        "construction_end_min_exclusive": time["construction_end_min"],
        "horizon_hours": time["horizon_hours"],
        "requested_prediction_minutes": time["prediction_cuts_min"],
        "observable": "orders_picked_up_cumulative",
        "units": {"time": "hour", "material": "orders", "flow": "orders/hour"},
        "assumptions": {key: {"value": item["value"], "unit": item["unit"],
                             "origin": item["origin"],
                             "identification": item["identification"]}
                        for key, item in params.items()},
        "not_observed": ["pickups", "individual_wait", "prepayment_abandonment",
                         "barista_machine_resources", "future_pos"],
    }
    prompt = (
        "Generate an original quantitative stock-flow diagram for a cafeteria's "
        "PAID ORDER to PICKUP frontier. Paid POS transactions are input orders, "
        "never observed pickups or customer arrivals. Develop your own stock-flow "
        "structure using ONLY the public assumptions below. Do not invent measurements, "
        "calibration, private truth, shared barista/espresso coupling or intervention "
        "effects. Time in hours, material in orders, rates in orders/hour. "
        "Set simulation startTime=0, stopTime=" + format(time["horizon_hours"], ".15g") +
        " (NOT eight hours), timeUnits=hour and integrationMethod=Euler. "
        "If the exact finite-horizon input cannot be expressed in the native language, "
        "report limitations; do not manufacture observations. Input is constant at " +
        format(source["rate_orders_per_hour"], ".15g") +
        " orders/hour from t=0 through the specified horizon, by hypothesis. "
        "The only requested primary output is cumulative picked-up orders."
    )
    return {
        "schema": SCHEMA, "mode": MODE, "protocol": case["protocol"], "arm": "B",
        "condition": case["condition"], "case_sha256": digest(case),
        "source_package_sha256": case["source_package_sha256"],
        "public_sha256": case["public_sha256"], "run_id": case["run_id"],
        "frozen_sha": case["frozen_sha"], "selection": case["selection"],
        "horizon_hours": time["horizon_hours"],
        "construction_end_min": time["construction_end_min"],
        "input_rate_orders_per_hour": source["rate_orders_per_hour"],
        "hypotheses_sha256": case["hypotheses_sha256"],
        "public_context": common, "prompt": prompt,
        "problemStatement": "Paid orders wait in aggregate for preparation and pickup. "
                            "The service dynamic is unknown; no pickups have been measured.",
        "backgroundKnowledge": json.dumps(common, sort_keys=True, ensure_ascii=False),
        "scientific_lock_created": False, "truth_access": False,
        "provider_posts": 0, "new_omc": 0,
    }


def validate_payload(payload, case):
    need(isinstance(payload, dict) and payload == make_payload(case),
         "PUBLIC_CASE_PAYLOAD_MISMATCH")
    return True


def prepare(case, out):
    result = make_payload(case)
    write_json(out, result, exclusive=True)
    return result


def audit_fixture_result(folder, payload):
    """Retain fixture provenance; never promote offline output to a real native."""
    need(payload.get("schema") == SCHEMA and payload.get("mode") == MODE,
         "PAYLOAD_MODE_MISMATCH")
    folder = Path(folder)
    receipt = read_json(folder / "receipt.json")
    native = read_json(folder / "native-engine-result.json")
    need(receipt.get("schema") == "arena.coffee-peak.b-offline-receipt/1"
         and receipt.get("mode") == MODE
         and receipt.get("case_sha256") == payload["case_sha256"]
         and receipt.get("provider_posts") == 0
         and receipt.get("sdk_interceptions") == 1
         and receipt.get("native_file_sha256") == "sha256:" + __import__("hashlib").sha256(
             (folder / "native-engine-result.json").read_bytes()).hexdigest(),
         "FIXTURE_RECEIPT_INVALID")
    return {
        "schema": "arena.coffee-peak.b-offline-audit/1",
        "status": "ORIGINAL_ENGINE_INVOKED_WITH_MOCKED_PROVIDER_NOT_SCIENTIFIC",
        "native_sha256": digest(native), "model_returned": receipt["model_returned"],
        "native_observed_unsupported": receipt.get("stop_reason"),
        "translation": "NOT_AUTHORIZED_UNTIL_COFFEE_HORIZON_ADAPTER",
        "provider_posts": 0, "new_omc": 0, "truth_access": False,
        "scientific_lock_created": False,
    }


def translate_offline_fixture(folder, payload, out):
    """Render the EXACT fixture native with a versioned coffee horizon adapter.

    This is a test of translation compatibility only. It does NOT establish
    Buffalo authorship from a real provider, conservation, G2, or science.
    """
    from arena.coffee_adapters import b_translation
    from arena.common import canonical
    from hashlib import sha256
    audit = audit_fixture_result(folder, payload)
    receipt = read_json(Path(folder) / "receipt.json")
    need(receipt.get("status") == "ORIGINAL_ENGINE_OUTPUT_ON_OFFLINE_FIXTURE"
         and receipt.get("model_returned") is True,
         "OFFLINE_NATIVE_NOT_ADMITTED_FOR_TRANSLATION")
    native = read_json(Path(folder) / "native-engine-result.json")
    try:
        model_name, modelica, translation = b_translation.generate(native)
    except b_translation.TranslationBlocked as exc:
        raise ArenaError("COFFEE_B_TRANSLATION_BLOCKED:" + str(exc)) from None
    out = Path(out)
    need(not out.exists(), "REFUSE_TRANSLATION_OVERWRITE")
    out.mkdir(parents=True)
    code_path = out / (model_name + ".mo")
    code_path.write_text(modelica, encoding="utf-8", newline="\n")
    receipt_payload = {
        "schema": "arena.coffee-peak.b-offline-translation/1",
        "status": "TRANSLATED_FIXTURE_NOT_COMPILED_NOT_SCIENTIFIC",
        "native_file_sha256": receipt["native_file_sha256"],
        "native_payload_sha256": receipt["native_sha256"],
        "modelica_sha256": "sha256:" + sha256(code_path.read_bytes()).hexdigest(),
        "modelica_file": code_path.name,
        "native_scope": translation,
        "case_sha256": payload["case_sha256"],
        "scientific_lock_created": False,
        "provider_posts": 0, "new_omc": 0,
        "truth_access": False,
        "fixture_validation": audit["status"],
    }
    write_json(out / "translation-receipt.json", receipt_payload, exclusive=True)
    return receipt_payload
