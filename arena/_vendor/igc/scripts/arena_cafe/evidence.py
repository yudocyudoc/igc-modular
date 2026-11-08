"""A1 cafe: evaluator-side O0/O1 projections from *already projected* event logs.

This is a source-preparation interface, not a replacement D/B/M inference
engine.  No invocation of EV01's private generator or DES is permitted here.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from typing import Any

from scripts.arena_event_observability import exact, project_events, public_event
from scripts.arena_v0_contract import (
    INPUT_SCHEMA, ARMS, ArenaContractError, assert_same_evidence,
    arm_view, digest, validate_visible_input,
)

SCHEMA = "igc-arena-cafe-o0-o1-projection/0.2"
INTERFACE_SCHEMA = "igc-arena-cafe-interface-audit/0.1"
CONDITIONS = ("O0", "O1")
PREP = "preparacion"
SAMPLE_TIMES = ("0", "2", "4", "6", "8", "10")
QUESTION = "What can the permitted observations establish about cafe deliveries and mechanisms?"


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ArenaContractError(code)


def _precut(rows: list[dict[str, Any]], cutoff: Fraction) -> list[dict[str, Any]]:
    require(isinstance(rows, list), "CAFE_EVENTS_NOT_LIST")
    return [dict(row) for row in rows if exact(row["t_minutes_exact"]) < cutoff]


def _validate_visible_rows(rows: list[dict[str, Any]], mode: str) -> None:
    require([r["event_seq"] for r in rows] == list(range(len(rows))),
            "CAFE_EVENT_SEQUENCE_NOT_LOCAL")
    for row in rows:
        event = public_event(row, mode)
        require(event is not None, "CAFE_NOT_VISIBLE_IN_VIEW")
        require(set(row) == set(event) and
                all(row[k] == event[k] for k in row if k != "event_seq"),
                "CAFE_UNAUTHORIZED_VISIBLE_FIELD")
        require(row["source"] == (
            "pos" if row["event_type"] in
            {"pedido_creado", "pago_confirmado", "pedido_entregado"}
            else "instrumentacion_fisica"),
            "CAFE_SOURCE_SEMANTICS_INVALID")


def _pos_and_full(pos: list[dict[str, Any]],
                  full: list[dict[str, Any]],
                  cutoff: Fraction) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Work only with public projections. Neither object may be the raw truth.
    _validate_visible_rows(pos, "POS")
    _validate_visible_rows(full, "FULL")
    p = _precut(pos, cutoff)
    f = _precut(full, cutoff)
    # Locally reindex after truncation; event_seq is never the private ordinal.
    for rows in (p, f):
        for i, row in enumerate(rows):
            row["event_seq"] = i
    predicted_pos = project_events(f, "POS")
    require(predicted_pos == p, "CAFE_POS_FULL_NOT_SAME_SOURCE")
    return p, f


def _counts(pos: list[dict[str, Any]], grid: list[Fraction]) -> list[dict[str, Any]]:
    cases: dict[str, dict[str, Fraction]] = defaultdict(dict)
    for row in pos:
        event_type, case = row["event_type"], row["case_id"]
        require(event_type not in cases[case], "CAFE_DUPLICATE_POS_EVENT")
        cases[case][event_type] = exact(row["t_minutes_exact"])
    for events in cases.values():
        require("pedido_creado" in events, "CAFE_POS_MISSING_CREATION")
        if "pago_confirmado" in events:
            require(events["pago_confirmado"] == events["pedido_creado"],
                    "CAFE_POS_PAYMENT_INCONSISTENT")
        if "pedido_entregado" in events:
            require(events["pedido_creado"] <= events["pedido_entregado"],
                    "CAFE_POS_DELIVERY_BEFORE_CREATION")
    result = []
    for t in grid:
        result.append({
            "t_minutes_exact": str(t),
            "orders_created_cumulative": sum(
                ev["pedido_creado"] < t for ev in cases.values()),
            "delivered_cumulative": sum(
                "pedido_entregado" in ev and ev["pedido_entregado"] < t
                for ev in cases.values()),
        })
    for item in result:
        require(item["delivered_cumulative"] <= item["orders_created_cumulative"],
                "CAFE_CONSERVATION_FAIL")
    return result


def _preparation(full: list[dict[str, Any]]) -> dict[str, Any]:
    times: dict[str, dict[str, Fraction]] = defaultdict(dict)
    seen: dict[str, str] = {}
    for row in full:
        if row.get("stage") != PREP:
            continue
        kind = row["event_type"]
        require(kind not in times[row["case_id"]], "CAFE_DUPLICATE_PREP_EVENT")
        times[row["case_id"]][kind] = exact(row["t_minutes_exact"])
        if kind == "servicio_inicio":
            seen[row["case_id"]] = row["resource_id"]
        elif kind == "servicio_fin" and row["case_id"] in seen:
            require(row["resource_id"] == seen[row["case_id"]],
                    "CAFE_PREP_RESOURCE_CHANGED")
    waits: list[Fraction] = []
    durations: list[Fraction] = []
    for events in times.values():
        if "servicio_fin" not in events:
            continue
        require(set(events) == {"etapa_entrada", "servicio_inicio", "servicio_fin"},
                "CAFE_PREP_INTERVAL_INCOMPLETE")
        enter, start, end = (events[k] for k in
                             ("etapa_entrada", "servicio_inicio", "servicio_fin"))
        require(enter <= start <= end, "CAFE_PREP_NEGATIVE_DURATION")
        waits.append(start - enter)
        durations.append(end - start)
    n = len(durations)
    return {
        "stage_disclosed": PREP,
        "source_semantics": "synthetic_direct_physical_instrumentation",
        "n_completed_stage_services": n,
        "mean_wait_minutes_exact": str(sum(waits, Fraction(0)) / n) if n else None,
        "mean_service_minutes_exact": str(sum(durations, Fraction(0)) / n) if n else None,
        "measurement_limit": "completed_preparation_intervals_only_pre_cutoff",
    }


def build(pos_projected: list[dict[str, Any]],
          full_projected: list[dict[str, Any]],
          *,
          cutoff_minutes_exact: str = "10",
          sample_times: tuple[str, ...] = SAMPLE_TIMES,
          investigation_id: str = "cafeteria-known-control-a1",
          world_public_id: str = "w001") -> dict[str, Any]:
    """Construct O0 and O1 only; the caller is the evaluator, not D/B/M."""
    cutoff = exact(cutoff_minutes_exact)
    grid = [exact(t) for t in sample_times]
    require(cutoff > 0 and len(grid) >= 2 and grid[0] == 0 and
            grid[-1] == cutoff and
            all(a < b for a, b in zip(grid, grid[1:])),
            "CAFE_INVALID_CUTOFF_OR_GRID")
    pos, full = _pos_and_full(pos_projected, full_projected, cutoff)
    counts = _counts(pos, grid)
    prep = _preparation(full)
    payloads: dict[str, Any] = {}
    matrices: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        arrival_events = [
            {"case_id": row["case_id"], "t_minutes_exact": str(exact(row["t_minutes_exact"]))}
            for row in pos if row["event_type"] == "pedido_creado"
        ]
        arrival_events.sort(key=lambda row: (exact(row["t_minutes_exact"]), row["case_id"]))
        construction = {
            "pos_arrival_events": arrival_events,
            "observation_series": counts,
            "units": {"time": "minutes", "counts": "orders"},
            "observation_window": "[0,cutoff)",
            "data_origin": "synthetic_event_projection_not_real_POS",
        }
        if condition == "O1":
            construction["physical_observation"] = prep
        source_snapshot_hash = digest({
            "schema": SCHEMA, "condition": condition,
            "cutoff_minutes_exact": str(cutoff),
            "construction": construction,
        })
        payload = {
            "schema": INPUT_SCHEMA,
            "investigation_id": investigation_id,
            "round_id": "a1-" + condition.lower() + "-known",
            "question": QUESTION,
            "construction": construction,
            "observability": {
                "condition_id": condition,
                "world_public_id": world_public_id,
                "cutoff_minutes_exact": str(cutoff),
                "window": "[0,cutoff)",
                "sample_rule": "each_count_uses_events_strictly_before_sample_t",
                "published_source": "POS" if condition == "O0" else "POS+authorized_prep_aggregate",
            },
            "source_snapshot_hash": source_snapshot_hash,
            "iteration_limit": 1,
            "resources": {"shared_source_only": True, "no_provider_calls": True},
        }
        validate_visible_input(payload)
        views = [arm_view(payload, arm) for arm in ("D", "B", "M")]
        assert_same_evidence(views)
        payloads[condition] = payload
        for v in views:
            arm = v["arm_id"]
            status = ("NOT_VERIFIED" if arm == "B"
                      else "UNSUPPORTED_DOCUMENTED")
            reason = {
                "D": "D_REQUIRES_PULSE_AND_DECLARED_NOMINAL_PARAMETERS;NO_EVENT_AGGREGATE_PORT",
                "B": "BACKGROUND_KNOWLEDGE_TRANSPORT_POSSIBLE;NO_NATIVE_RUN_OR_PROVEN_READ",
                "M": "E1_ENUMERATOR_HAS_NO_EVIDENCE_TO_ROLE_BINDING_OR_CALIBRATION",
            }[arm]
            matrices.append({
                "arm_id": arm,
                "condition_id": condition,
                "context_id": investigation_id + ":" + world_public_id + ":" + arm + ":" + condition,
                "common_input_hash": v["input_hash"],
                "source_snapshot_hash": payload["source_snapshot_hash"],
                "transport": "VALIDATED_PUBLIC_ENVELOPE_ONLY",
                "native_method_run": False,
                "read_proven": False,
                "used_proven": False,
                "interface_status": status,
                "reason": reason,
            })
    require(payloads["O0"]["source_snapshot_hash"] !=
            payloads["O1"]["source_snapshot_hash"],
            "CAFE_CONDITIONS_INCORRECTLY_IDENTICAL")
    return {
        "schema": SCHEMA,
        "world_public_id": world_public_id,
        "cutoff_minutes_exact": str(cutoff),
        "physical_origin": "SYNTHETIC_KNOWN_CONTROL",
        "views": payloads,
        "interface": {"schema": INTERFACE_SCHEMA, "entries": matrices,
                      "conditions_are_isolated_by_id_only": True,
                      "actual_process_cache_ledger_acl": "NOT_IMPLEMENTED",
                      "gate": "INTERFACE_01_PARTIAL_NOT_CONSUMPTION"},
        "claims": {"EVIDENCE-01": "OFFLINE_PROJECTION_VALIDATED",
                   "INTERFACE-01": "PARTIAL_NO_NATIVE_CONSUMPTION",
                   "A1": "PARTIAL", "A3": "NOT_RUN"},
    }

def load_public_csv(path, view):
    """Read EV-01 exported public CSV, reject unknown columns and truth fields."""
    import csv
    from pathlib import Path
    require(view in ("POS", "FULL"), "CAFE_UNSUPPORTED_CSV_VIEW")
    expected = ["case_id", "event_seq", "activity", "event_type",
                "t_minutes_exact", "source"]
    if view == "FULL":
        expected += ["stage", "resource_id"]
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == expected, "CAFE_CSV_COLUMN_MISMATCH")
        rows = []
        for row in reader:
            require(row.get("event_seq", "").isdigit(), "CAFE_BAD_EVENT_SEQ")
            converted = {key: value for key, value in row.items()
                         if key in expected and (key not in ("stage", "resource_id") or value)}
            converted["event_seq"] = int(converted["event_seq"])
            rows.append(converted)
    _validate_visible_rows(rows, view)
    return rows


def cli() -> None:
    """Evaluator-only filesystem exporter; never opens a raw private trace."""
    import argparse
    from pathlib import Path
    from scripts.arena_v0_contract import canonical
    parser = argparse.ArgumentParser(description="A1 public cafe evidence projection")
    parser.add_argument("--pos", required=True, type=Path)
    parser.add_argument("--full", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cutoff", default="10")
    parser.add_argument("--world-public-id", default="w001")
    args = parser.parse_args()
    pos = load_public_csv(args.pos, "POS")
    full = load_public_csv(args.full, "FULL")
    result = build(pos, full, cutoff_minutes_exact=args.cutoff,
                   world_public_id=args.world_public_id)
    args.out.mkdir(parents=True, exist_ok=False)
    for condition in CONDITIONS:
        (args.out / (condition + "_VISIBLE.json")).write_bytes(
            canonical(result["views"][condition]) + b"\n")
    (args.out / "INTERFACE01.json").write_bytes(canonical(result["interface"]) + b"\n")
    (args.out / "EVIDENCE01.json").write_bytes(canonical({
        "schema": result["schema"],
        "cutoff_minutes_exact": result["cutoff_minutes_exact"],
        "world_public_id": result["world_public_id"],
        "claims": result["claims"],
        "public_source_hashes": {
            c: result["views"][c]["source_snapshot_hash"] for c in CONDITIONS},
        "no_evaluator_truth_exported": True,
    }) + b"\n")


if __name__ == "__main__":
    cli()
