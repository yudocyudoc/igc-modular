"""CT-03 public protocol shared by D/B/M, never true-world metadata.

Only the exogenous waveform, units and time windows live here. Construction
observations enter separately after custodial release. The evaluator has no
import path from this module.
"""
PUBLIC_INPUT = {
    "schema": "igc-ct03-fixed-aggregate-input/1.0",
    "quantity_unit": "items",
    "time_unit": "hours",
    "rate_unit": "items/hour",
    "pulse_rate": 1.7,
    "pulse_start": 0,
    "pulse_end": 2,
    "after_rate": 0,
    "continuous_requested_mass": 3.4,
    "initial_stock": 0,
    "start_time": 0,
    "stop_time": 8,
    "solver": "euler",
    "dt": 0.125,
    "construction_times": [0, 1, 2, 4],
    "reserved_times": [6, 8],
}

OBS_SCHEMA = "igc-ct03-public-construction-observations/1.0"


def validate_construction(context, construction):
    """Common source data only, no D/B/M model, no evaluator or future truth."""
    import math
    if not (type(construction) is dict and
            construction.get("schema") == OBS_SCHEMA and
            construction.get("source_snapshot_hash") == context["source_hash"] and
            construction.get("world_public_id") == context["world"] and
            construction.get("condition_id") == context["condition"] and
            construction.get("time_unit") == "hours" and
            construction.get("observable") == "cumulative_delivered"):
        raise ValueError("CT02_M_WRONG_CONSTRUCTION_SCOPE")
    if set(construction) != {
        "schema", "source_snapshot_hash", "world_public_id", "condition_id",
        "time_unit", "observable", "observations"
    }:
        raise ValueError("CT02_M_EXTRA_FIELDS_IN_CONSTRUCTION")
    points = construction["observations"]
    cuts = PUBLIC_INPUT["construction_times"]
    if not (type(points) is list and len(points) == len(cuts) and
            all(type(x) is dict and set(x) == {"time", "delivered"}
                and type(x["time"]) in (int, float) and x["time"] == t
                for x, t in zip(points, cuts))):
        raise ValueError("CT02_M_FOUR_CONSTRUCTION_CUTS_REQUIRED")
    # Numeric comparison slack only, not an observed score tolerance.
    eps = 1e-8
    previous = 0.0
    for i, x in enumerate(points):
        v = x["delivered"]
        t = x["time"]
        arrivals = PUBLIC_INPUT["pulse_rate"] * min(t, PUBLIC_INPUT["pulse_end"])
        if not (type(v) in (int, float) and math.isfinite(v) and
                (i != 0 or abs(v) <= eps) and
                v >= -eps and v >= previous - eps and v <= arrivals + eps):
            raise ValueError("CT02_M_INVALID_OBSERVED_DELIVERY_OR_INPUT_CAUSAL_BOUND")
        previous = v
    return points
