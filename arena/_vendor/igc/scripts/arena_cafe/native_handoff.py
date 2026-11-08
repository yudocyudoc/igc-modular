"""A1 single-arm, single-condition handoff. No native engine is invoked here.

The controller exposes exactly one validated O0/O1 public envelope per call.
Physical truth and sibling-condition paths are not admissible inputs.
Filesystem scope is application-level only, NOT OS/process/ledger ACL.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import re
from scripts.arena_cafe import evidence
from scripts.arena_v0_contract import (
    ArenaContractError, canonical, digest, validate_visible_input
)

SCHEMA = "igc-arena-cafe-native-handoff/0.1"
ARMS = ("D", "B", "M")
ALLOWED = {
    "O0": {"observation_series", "pos_arrival_events", "units", "observation_window", "data_origin"},
    "O1": {"observation_series", "pos_arrival_events", "units", "observation_window",
           "data_origin", "physical_observation"},
}
PREP = {"stage_disclosed", "source_semantics", "n_completed_stage_services",
        "mean_wait_minutes_exact", "mean_service_minutes_exact", "measurement_limit"}
SERIES = {"t_minutes_exact", "orders_created_cumulative", "delivered_cumulative"}


def need(ok, tag):
    if not ok:
        raise ArenaContractError(tag)


def validate_a1_visible(payload, condition):
    """Authenticate the shape and recompute the A1 visible-source digest.

    This detects accidental mix-ups/tampering; without keyed signatures it is
    NOT proof against a malicious writer who controls both data and digest.
    """
    need(condition in ALLOWED, "A1_BAD_CONDITION")
    validate_visible_input(payload)
    need(payload["question"] == evidence.QUESTION, "A1_QUESTION_UNAUTHORIZED")
    c, o = payload["construction"], payload["observability"]
    need(set(o) == {"condition_id", "world_public_id", "cutoff_minutes_exact",
                    "window", "sample_rule", "published_source"},
         "A1_OBSERVABILITY_SHAPE")
    need(o["condition_id"] == condition, "A1_CROSS_CONDITION")
    need(payload["round_id"] == "a1-" + condition.lower() + "-known",
         "A1_ROUND_CONDITION_MISMATCH")
    need(set(c) == ALLOWED[condition], "A1_CONSTRUCTION_SHAPE")
    need(o["window"] == "[0,cutoff)" and
         c["observation_window"] == "[0,cutoff)" and
         o["sample_rule"] == "each_count_uses_events_strictly_before_sample_t",
         "A1_WINDOW_MISMATCH")
    need(o["published_source"] == ("POS" if condition == "O0"
          else "POS+authorized_prep_aggregate"), "A1_SOURCE_MISMATCH")
    need(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", o["world_public_id"]) is not None,
         "A1_WORLD_ID_INVALID")
    need(c["units"] == {"time": "minutes", "counts": "orders"} and
         c["data_origin"] == "synthetic_event_projection_not_real_POS",
         "A1_MEASUREMENT_SEMANTICS")
    need(isinstance(c["observation_series"], list) and
         len(c["observation_series"]) >= 2 and
         all(isinstance(r, dict) and set(r) == SERIES
             for r in c["observation_series"]), "A1_SERIES_SHAPE")
    from fractions import Fraction
    grid = [Fraction(row["t_minutes_exact"]) for row in c["observation_series"]]
    cutoff = Fraction(o["cutoff_minutes_exact"])
    need(cutoff > 0 and grid[0] == 0 and grid[-1] == cutoff and
         all(a < b for a,b in zip(grid, grid[1:])), "A1_TIME_GRID")
    arrivals = c["pos_arrival_events"]
    need(isinstance(arrivals,list) and all(
        type(event) is dict and set(event)=={"case_id","t_minutes_exact"}
        and type(event["case_id"]) is str and
        re.fullmatch(r"[A-Za-z0-9_-]{1,80}",event["case_id"]) is not None
        for event in arrivals), "A1_POS_ARRIVALS_SCHEMA")
    arrival_times = [Fraction(row["t_minutes_exact"]) for row in arrivals]
    need(all(0 <= t < cutoff for t in arrival_times)
         and arrival_times == sorted(arrival_times)
         and len({row["case_id"] for row in arrivals})==len(arrivals),
         "A1_POS_ARRIVALS_TIME_OR_ID")
    need(all(row["orders_created_cumulative"] ==
             sum(t < Fraction(row["t_minutes_exact"]) for t in arrival_times)
             for row in c["observation_series"]),
         "A1_POS_ARRIVALS_COUNT_PARITY")
    prev_creations, prev_delivered = 0, 0
    for r in c["observation_series"]:
        created, delivered = r["orders_created_cumulative"], r["delivered_cumulative"]
        need(type(created) is int and type(delivered) is int and
             0 <= prev_creations <= created and 0 <= prev_delivered <= delivered <= created,
             "A1_COUNT_BALANCE")
        prev_creations, prev_delivered = created, delivered
    if condition == "O1":
        p = c["physical_observation"]
        need(isinstance(p, dict) and set(p) == PREP and
             p["stage_disclosed"] == "preparacion" and
             p["source_semantics"] == "synthetic_direct_physical_instrumentation" and
             p["measurement_limit"] == "completed_preparation_intervals_only_pre_cutoff",
             "A1_PHYSICAL_SOURCE_INVALID")
        n = p["n_completed_stage_services"]
        need(type(n) is int and n >= 0, "A1_PHYSICAL_N_INVALID")
        durations = [p["mean_wait_minutes_exact"], p["mean_service_minutes_exact"]]
        need((n == 0 and durations == [None,None]) or
             (n > 0 and all(x is not None and Fraction(x) >= 0 for x in durations)),
             "A1_PHYSICAL_INTERVAL_INVALID")
    computed = digest({
        "schema": evidence.SCHEMA,
        "condition": condition,
        "cutoff_minutes_exact": str(cutoff),
        "construction": c,
    })
    need(payload["source_snapshot_hash"] == computed, "A1_SOURCE_DIGEST_MISMATCH")
    need(payload["resources"] == {"shared_source_only": True, "no_provider_calls": True}
         and payload["iteration_limit"] == 1, "A1_BUDGET_MISMATCH")
    return digest(payload)


def handoff(payload, arm, condition):
    need(arm in ARMS, "A1_UNKNOWN_ARM")
    input_hash = validate_a1_visible(payload, condition)
    scope = digest({"input": input_hash, "arm": arm, "condition": condition,
                    "world_public_id": payload["observability"]["world_public_id"]})
    status = {
        "D": "BLOCKED_NO_DECLARED_PULSE_OR_NOMINAL_PARAMETERS",
        "B": "BUFFALO_NATIVE_INPUT_PREPARED_NOT_RUN",
        "M": "SHORT_E1_NATIVE_INPUT_PREPARED_NOT_RUN",
    }[arm]
    return {
        "schema": SCHEMA,
        "arm_id": arm, "condition_id": condition,
        "scope_hash": scope, "visible_input_hash": input_hash,
        "source_snapshot_hash": payload["source_snapshot_hash"],
        "status": status,
        "native_method_run": False,
        "prompt_read_proven": False, "native_evidence_use_proven": False,
        "cross_condition_access_control": "APPLICATION_SCOPED_ONLY_NOT_OS_ACL",
        "source_claim": "VALIDATED_VISIBLE_A1_SYNTHETIC_ONLY",
        "limitations": {
            "D": "INPUT_REQUIRES_DECLARED_PULSE_AND_NOMINAL_PARAMETERS",
            "B": "NATIVE_PROMPT_REQUIRES_OFFLINE_REPLAY;MODEL_USE_NOT_ESTABLISHED",
            "M": "E1_ROLE_MAPPING_AND_PARAMETER_ESTIMATION_MISSING",
        }[arm],
    }


def export_one(payload, arm, condition, out):
    """Export one scoped directory; never add other arms or conditions."""
    receipt = handoff(payload, arm, condition)
    out = Path(out)
    need(not out.exists(), "A1_REFUSE_OVERWRITE")
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    path = out / "handoff.json"
    with path.open("xb") as stream:
        stream.write(canonical(receipt) + b"\n")
    path.chmod(0o600)
    if arm != "D":
        inp = out / "visible.json"
        with inp.open("xb") as stream:
            stream.write(canonical(payload) + b"\n")
        inp.chmod(0o600)
    # Directory mode protects other OS users when supported; same-user
    # processes remain able to access siblings. No ACL claim is made.
    return receipt


def main():
    parser = argparse.ArgumentParser(description="One native A1 input handoff")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--condition", choices=tuple(ALLOWED), required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = export_one(json.loads(args.input.read_text(encoding="utf8")),
                         args.arm, args.condition, args.out)
    print(json.dumps({"status": receipt["status"],
                      "scope_hash": receipt["scope_hash"],
                      "native_method_run": False}, sort_keys=True))


if __name__ == "__main__":
    main()
