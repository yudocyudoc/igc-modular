"""A1 observable-to-native port bindings, without fitting or generating models.

D: exposes interval-censored arrival/delivery constraints, never a pulse or
nominal stock-flow parameters.
M: validates literal source/receipt/preparation endpoints in the *original*
Short E1 registry/catalog. Creates observation operators, never selected
graphs or fitted parameters. B is handled by its original native runner.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from scripts.arena_cafe.native_handoff import validate_a1_visible, need
from scripts.arena_v0_contract import canonical, digest

SCHEMA = "igc-arena-cafe-observation-ports/0.1"
CONDITIONS = ("O0", "O1")
NATIVE_STATUS = "TYPED_OBSERVATION_PORT_ONLY_NOT_NATIVE_INFERENCE"


def _grid(payload: dict) -> tuple[list[dict], list[dict]]:
    """Counts are cumulative at strict-before-t sample instants.

    Differences describe each half-open interval [t0,t1). Exact arrival
    timestamps remain separately available in pos_arrival_events; this legacy
    aggregate-only port deliberately does not consume those times.
    """
    points = payload["construction"]["observation_series"]
    bins = []
    for previous, current in zip(points, points[1:]):
        start = Fraction(previous["t_minutes_exact"])
        end = Fraction(current["t_minutes_exact"])
        need(0 <= start < end, "A1_PORT_BAD_INTERVAL")
        arrived = current["orders_created_cumulative"] - previous["orders_created_cumulative"]
        delivered = current["delivered_cumulative"] - previous["delivered_cumulative"]
        need(0 <= arrived and 0 <= delivered, "A1_PORT_NEGATIVE_INCREMENTS")
        bins.append({
            "interval": "[t0,t1)",
            "start_minutes_exact": str(start),
            "end_minutes_exact": str(end),
            "arrivals_observed_count": arrived,
            "deliveries_observed_count": delivered,
            "time_within_bin": "EXACT_POS_EVENTS_SEPARATELY_AVAILABLE_NOT_A_PULSE",
        })
    return points, bins


def _common(payload: dict, arm: str, condition: str) -> dict[str, Any]:
    input_hash = validate_a1_visible(payload, condition)
    points, bins = _grid(payload)
    return {
        "schema": SCHEMA,
        "arm_id": arm,
        "condition_id": condition,
        "visible_input_hash": input_hash,
        "source_snapshot_hash": payload["source_snapshot_hash"],
        "source_semantics": "SYNTHETIC_OBSERVED_ORDER_EVENTS_NOT_EXOGENOUS_KNOWN_PULSE",
        "observation_cutoff": payload["observability"]["cutoff_minutes_exact"],
        "counts_time_grid": [
            {"time_minutes_exact": r["t_minutes_exact"],
             "orders_created_cumulative": r["orders_created_cumulative"],
             "delivered_cumulative": r["delivered_cumulative"]}
            for r in points
        ],
        "observed_interval_counts": bins,
        "no_instantaneous_rate_imputed": True,
        "no_latent_stage_imputed": True,
        "native_engine_executed_from_port": False,
        "native_inference_or_selection": "NOT_RUN",
        "status": NATIVE_STATUS,
    }


def d_port(payload: dict, condition: str) -> dict[str, Any]:
    """Formal observation operators, not a valid D native input.

    D's existing topology grammar, lint and solver remain unchanged.
    The original validate_case still rejects this observed-event source.
    """
    r = _common(payload, "D", condition)
    r.update({
        "native_method": "scripts.arena_d_v01",
        "native_contract": "generic-conservative-chain-search/0.1",
        "observation_operators": [
            {"observed": "orders_created_cumulative",
             "model_expression": "integral(inputRate,0,t)",
             "operator": "CUMULATIVE_MATERIAL_INPUT",
             "observed_unit": "orders",
             "model_rate_unit": "orders/minute",
             "evaluation": "INTERVAL_COUNTS_ONLY_NO_RATE_TRAJECTORY"},
            {"observed": "delivered_cumulative",
             "model_expression": "delivered(t)",
             "operator": "SAMPLE_CUMULATIVE_STOCK",
             "observed_unit": "orders",
             "evaluation": "OBSERVED_CUMULATIVE_COUNTER"},
        ],
        "physical_aggregates": "NOT_MAPPED_TO_GENERIC_D_STOCKS"
            if condition == "O1" else "NOT_AVAILABLE_O0",
        "blocked_requirements": [
            "NO_KNOWN_EXOGENOUS_PULSE",
            "NO_DECLARED_NOMINAL_PARAMETERS",
            "NO_NATIVE_INTERVAL_CENSORED_INPUT_CONTRACT",
        ],
        "native_input_valid": False,
        "next_step": "ADDITIVE_ORIGINAL_D_OBSERVED_STIMULUS_EXTENSION_REQUIRES_SEPARATE_REVIEW",
    })
    return r


def _get_registry(registry: Path):
    from scripts.arena_m_short_e1 import REGISTRIES, get_composer
    path = Path(registry).resolve()
    need(path in REGISTRIES, "A1_M_UNAPPROVED_REGISTRY")
    composer = get_composer()
    cfg, classes, catalog = composer.load_registry(path)
    return path, cfg, classes, catalog


def _verified_port(cfg: dict, classes: dict, role: str, name: str,
                   direction: str, kind: str, unit: str) -> dict[str, str]:
    need(role in cfg["roles"], "A1_M_ROLE_NOT_REGISTERED")
    role_cfg = cfg["roles"][role]
    cl = classes[role_cfg["class_id"]]
    need(role in cl["roles"], "A1_M_ROLE_CLASS_MISMATCH")
    matches = [p for p in cl["ports"] if p["name"] == name]
    need(len(matches) == 1, "A1_M_MISSING_PORT")
    port = matches[0]
    declared = port["type"]
    bindings = cl.get("role_bindings", {}).get(role, {})
    resolved = declared
    for variable, target in sorted(bindings.items()):
        need(variable in ("T", "U") and isinstance(target, str),
             "A1_M_ROLE_BINDING_INVALID")
        resolved = resolved.replace("<" + variable + ">", "<" + target + ">")
    need(port["direction"] == direction and resolved == kind and
         port["unit"] == unit, "A1_M_PORT_TYPE_MISMATCH")
    return {
        "role": role, "class_id": role_cfg["class_id"],
        "port": name, "direction": direction, "type": resolved,
        "catalog_declared_type": declared,
        "role_type_bindings": {k: bindings[k] for k in sorted(bindings)},
        "native_unit": unit,
    }


def m_port(payload: dict, condition: str, registry: Path) -> dict[str, Any]:
    """Bind observable meanings to existing typed E1 ports.

    Integrals constrain trajectories; no observed counts become model
    parameters or instantaneous forcings. The registry is not edited.
    """
    result = _common(payload, "M", condition)
    path, cfg, classes, catalog = _get_registry(registry)
    need(catalog["schema_version"] == "igc-v3/e0.1",
         "A1_M_CATALOG_VERSION_DRIFT")
    source = _verified_port(cfg, classes, "source", "outflow",
                            "out", "FLOW<Order>", "units/hour")
    receipt = _verified_port(cfg, classes, "receipt", "total",
                             "out", "STATE<Delivered>", "units")
    bindings = [
        {"observed": "orders_created_cumulative",
         "target": source,
         "operator": "INTEGRAL_FLOW_UP_TO_SAMPLE_T",
         "native_rate_time_unit": "hour",
         "observed_time_unit": "minute",
         "unit_relation": "orders = integral(hours, units/hour) when one unit represents one order",
         "status": "TYPED_CANDIDATE_OBSERVATION_OPERATOR_NOT_EXECUTED"},
        {"observed": "delivered_cumulative",
         "target": receipt,
         "operator": "SAMPLE_CUMULATIVE_STATE_AT_T",
         "native_rate_time_unit": None,
         "observed_time_unit": "minute",
         "unit_relation": "one delivered unit represents one delivered order",
         "status": "TYPED_CANDIDATE_OBSERVATION_OPERATOR_NOT_EXECUTED"},
    ]
    if condition == "O1":
        prep = _verified_port(cfg, classes, "preparation", "completed",
                              "out", "FLOW<ReadyOrder>", "units/hour")
        bindings.append({
            "observed": "n_completed_stage_services",
            "target": prep,
            "operator": "INTEGRAL_FLOW_OVER_0_TO_CUTOFF",
            "observed_time_unit": "minute",
            "native_rate_time_unit": "hour",
            "unit_relation": "one completed preparation service corresponds to one ReadyOrder",
            "status": "CANDIDATE_ROLE_ASSOCIATION_FROM_DISCLOSED_STAGE_NOT_IDENTIFIED",
            "observed_count": payload["construction"]["physical_observation"][
                "n_completed_stage_services"],
        })
    result.update({
        "native_method": "scripts.arena_m_short_e1",
        "native_registry": path.name,
        "original_catalog_schema": catalog["schema_version"],
        "registry_roles_hash": digest(cfg["roles"]),
        "role_binding_assumption": "ONE_ORDER_EQUALS_ONE_E1_MATERIAL_UNIT_NOT_ESTABLISHED_EMPIRICALLY",
        "observation_operators": bindings,
        "unmapped_measurements": (
            ["mean_wait_minutes_exact", "mean_service_minutes_exact"]
            if condition == "O1" else []),
        "unmapped_reason": (
            "E1_PREPARATION_WAITING_IS_STOCK_NOT_DURATION_AND_RESPONSE_TIME_IS_A_MODEL_PARAMETER_NOT_MEASURED_SERVICE_TIME"
            if condition == "O1" else "NO_DIRECT_STAGE_OBSERVATIONS"),
        "roles_enumerated_by_native": "DECLARED_REGISTRY_NOT_SELECTED_FROM_THIS_EVIDENCE",
        "candidate_selection": "UNRESOLVED",
        "parameter_fitting": "NOT_RUN",
        "common_stimulus_modelica": "NOT_RUN",
        "next_step": "OBSERVATION_OPERATOR_EVALUATOR_AND_INDEPENDENT_CALIBRATION_UNIMPLEMENTED",
    })
    return result


def port(payload: dict, arm: str, condition: str, *, registry=None) -> dict:
    need(arm in ("D", "M"), "A1_PORT_UNSUPPORTED_ARM")
    if arm == "D":
        need(registry is None, "A1_D_DOES_NOT_USE_M_REGISTRY")
        return d_port(payload, condition)
    need(registry is not None, "A1_M_REQUIRES_PINNED_REGISTRY")
    return m_port(payload, condition, Path(registry))


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description="A1 original-engine typed observation ports")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--arm", choices=("D", "M"), required=True)
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    need(not args.out.exists(), "A1_PORT_OUTPUT_EXISTS")
    record = port(json.loads(args.input.read_text(encoding="utf-8")),
                  args.arm, args.condition, registry=args.registry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as f:
        f.write(canonical(record) + b"\n")
    print(json.dumps({"status": record["status"], "arm_id": record["arm_id"],
                      "condition_id": record["condition_id"],
                      "native_inference_or_selection": "NOT_RUN"}))


if __name__ == "__main__":
    main()
