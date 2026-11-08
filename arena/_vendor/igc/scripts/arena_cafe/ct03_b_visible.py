"""CT-03 B construction-only public view; no engine and no hidden world.

Use the exact common public observations, do not move data between arms.
The original Buffalo quantitative engine remains responsible for proposals.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical
from scripts.arena_cafe.ct03_public import validate_construction as _check_public
from scripts.arena_cafe.ct_feedback_bridge import make_context, require

SCHEMA = "igc-ct03-b-visible/1.0"
QUESTION = (
    "Build a quantitative aggregate stock-flow model for a stream of conserved "
    "work items. External accepted input is 1.7 items/hour from t=0 to t<2 "
    "hours and exactly zero afterwards, for 3.4 continuous items total. "
    "Initial material stocks and cumulative deliveries are zero; horizon "
    "0 to 8 hours, Euler time step 0.125 hour. Use only the observed cumulative "
    "deliveries at t=0,1,2,4 hours supplied below. Express a material model "
    "and its assumptions in the original Buffalo quantitative native format; "
    "do not assume a FIFO individual server, finite buffers, losses or "
    "know the true number of stages. Do not invent missing observations."
)


def view(construction: dict, *, world: str, round_kind: str) -> dict:
    require(round_kind in ("initial", "revision"), "CT03_B_WRONG_ROUND")
    source = construction.get("source_snapshot_hash")
    condition = construction.get("condition_id")
    ctx = make_context(experiment="CT03", world=world, round_id="R0", arm="B",
                       condition=condition, source_hash=source)
    points = _check_public(ctx, construction)
    return {
        "schema": SCHEMA, "case_id": "CT-03", "arm": "B",
        "round_id": "ct03-b-" + round_kind,
        "source_snapshot_hash": source, "world_public_id": world,
        "condition_id": condition, "question": QUESTION,
        "construction": {
            "input": {
                "pulse_rate": 1.7, "pulse_start": 0, "pulse_end": 2,
                "total_mass": 3.4, "unit": "items/hour", "horizon_hours": 8,
                "integration_step_hours": 0.125,
            },
            "observations": points,
            "observation_times_hours": [0,1,2,4],
        },
        "observability": {
            "quantity_unit": "items", "time_unit": "hours",
            "observable": "cumulative_delivered",
            "construction_times_hours": [0,1,2,4],
            "horizon_hours": 8,
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--construction", type=Path, required=True)
    p.add_argument("--world", required=True)
    p.add_argument("--round", choices=("initial", "revision"), required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    require(not args.out.exists(), "CT03_B_REFUSE_OVERWRITE")
    result = view(json.loads(args.construction.read_text()), world=args.world,
                  round_kind=args.round)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"status": "CONSTRUCTION_ONLY_VISIBLE", "round": args.round,
                      "provider_calls": 0, "omc": 0}))


if __name__ == "__main__":
    main()
