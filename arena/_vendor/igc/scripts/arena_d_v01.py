"""Arena D v0.1: bounded deterministic stock-flow grammar, not molecular selection.

G0/G1 prototype. Does not claim structural recovery, G3 adequacy, ATMS
reasoning or a private holdout. The nominal values are assumptions for G2 only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

from scripts.arena_v0_contract import (
    arm_view, canonical, digest, validate_submission, trace_event, SUBMISSION_SCHEMA,
)

SCHEMA = "igc-d-stockflow-search/0.1"
METHOD = "generic-conservative-chain-search/0.1"
PRIMITIVES = ("SOURCE", "STOCK", "RATE", "SINK", "CUMULATIVE_OBSERVATION")


class DError(ValueError):
    pass


def check(ok, code):
    if not ok:
        raise DError(code)


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate_case(data):
    view = arm_view(data, "D")
    c, o, r = data["construction"], data["observability"], data["resources"]
    check(type(c) is dict and set(c) == {"input_profile", "nominal_parameters", "observations"},
          "BAD_CONSTRUCTION")
    p = c["input_profile"]
    check(type(p) is dict and set(p) == {"kind", "rate", "duration"} and p["kind"] == "pulse" and
          positive(p["rate"]) and positive(p["duration"]), "BAD_INPUT")
    params = c["nominal_parameters"]
    check(type(params) is dict and set(params) == {"capacity", "response_time", "loss_time"} and
          all(positive(v) for v in params.values()), "BAD_NOMINAL_PARAMETERS")
    readings = c["observations"]
    check(type(readings) is list and len(readings) >= 2, "MISSING_READINGS")
    ts = []
    for row in readings:
        check(type(row) is dict and set(row) == {"t", "delivered"} and
              type(row["t"]) in (int, float) and math.isfinite(row["t"]) and row["t"] >= 0 and
              type(row["delivered"]) in (int, float) and math.isfinite(row["delivered"]),
              "BAD_READING")
        ts.append(row["t"])
    check(ts[0] == 0 and all(b > a for a, b in zip(ts, ts[1:])), "BAD_TIMES")
    check(type(o) is dict and set(o) == {"stock_unit", "time_unit", "observable"} and
          o["observable"] == "cumulative_delivered" and
          all(type(o[k]) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,30}", o[k])
              for k in ("stock_unit", "time_unit")), "BAD_OBSERVABILITY")
    check(type(r) is dict and set(r) == {"max_stocks", "allow_loss", "max_candidates", "max_simulations"} and
          type(r["max_stocks"]) is int and 1 <= r["max_stocks"] <= 3 and
          type(r["allow_loss"]) is bool and type(r["max_candidates"]) is int and
          1 <= r["max_candidates"] <= 6 and type(r["max_simulations"]) is int and
          0 <= r["max_simulations"] <= 6, "BAD_BUDGET")
    return view


def topology(n, loss):
    check(type(n) is int and 1 <= n <= 3 and type(loss) is bool, "BAD_TOPOLOGY")
    edges = [{"from": "source", "to": "s1", "kind": "MATERIAL"}]
    edges += [{"from": f"s{i}", "to": f"s{i+1}", "kind": "MATERIAL"} for i in range(1, n)]
    edges += [{"from": f"s{n}", "to": "delivered", "kind": "MATERIAL"}]
    if loss:
        edges += [{"from": "s1", "to": "lost", "kind": "MATERIAL"}]
    return {"schema": SCHEMA, "primitives": list(PRIMITIVES),
            "stocks": [f"s{i}" for i in range(1, n + 1)],
            "edges": edges, "loss": loss, "observable": "delivered"}


def lint_structure(t):
    check(type(t) is dict and set(t) == {"schema", "primitives", "stocks", "edges", "loss", "observable"},
          "BAD_STRUCTURE")
    check(t["schema"] == SCHEMA and t["primitives"] == list(PRIMITIVES) and
          t["observable"] == "delivered" and type(t["loss"]) is bool and
          type(t["stocks"]) is list and 1 <= len(t["stocks"]) <= 3, "BAD_STRUCTURE_SCOPE")
    expected = topology(len(t["stocks"]), t["loss"])
    check(t == expected, "UNSUPPORTED_GRAPH_OR_DUPLICATED_MATERIAL")
    return {"status": "G1_STRUCTURE_ADMISSIBLE",
            "scope": "LIMITED_GRAMMAR_ONLY_NOT_CAUSAL_VERDICT"}


def generate(data):
    view = validate_case(data)
    r = data["resources"]
    candidates = []
    for n in range(1, r["max_stocks"] + 1):
        for loss in ((False, True) if r["allow_loss"] else (False,)):
            t = topology(n, loss)
            lint_structure(t)
            key = digest(t)
            candidates.append({"id": "D-" + key[7:19], "structure": t,
                               "structure_hash": key, "lint": lint_structure(t),
                               "nominal_parameters": dict(data["construction"]["nominal_parameters"]),
                               "parameter_status": "PUBLIC_ASSUMPTIONS_NOT_FITTED"})
    candidates = candidates[:r["max_candidates"]]
    return {"schema": SCHEMA, "arm_id": "D", "method_version": METHOD,
            "round_id": data["round_id"], "input_hash": view["input_hash"],
            "candidates": candidates,
            "unknowns": ["True stock-flow structure not identified",
                         "Unrepresented mechanisms may exist beyond this grammar"],
            "verdict": "ALTERNATIVES_NOT_IDENTIFIED"}


def modelica(candidate, profile):
    t = candidate["structure"]
    lint_structure(t)
    p = candidate["nominal_parameters"]
    check(type(p) is dict and set(p) == {"capacity", "response_time", "loss_time"} and
          all(positive(v) for v in p.values()), "BAD_MODEL_PARAMETER")
    check(profile.get("kind") == "pulse" and
          positive(profile.get("rate")) and positive(profile.get("duration")), "BAD_MODEL_PULSE")
    n = len(t["stocks"])
    name = "DStockFlow_" + candidate["structure_hash"][7:19]
    lines = [
        f"model {name}",
        "  // Generic balance grammar; no molecular wrapper; no fitted parameter.",
        f"  parameter Real pulseRate = {profile['rate']:.12g};",
        f"  parameter Real pulseDuration = {profile['duration']:.12g};",
        f"  parameter Real capacity = {p['capacity']:.12g};",
        f"  parameter Real responseTime = {p['response_time']:.12g};",
        f"  parameter Real lossTime = {p['loss_time']:.12g};",
        "  Real inputRate;",
        *[f"  Real s{i}(start=0, fixed=true);" for i in range(1, n + 1)],
        *[f"  Real f{i};" for i in range(1, n + 1)],
        "  Real lossRate;",
        "  Real delivered(start=0, fixed=true);",
        "  Real lost(start=0, fixed=true);",
        "equation",
        "  inputRate = if time < pulseDuration then pulseRate else 0;",
        *[f"  f{i} = min(capacity, max(0, s{i}/responseTime));" for i in range(1, n + 1)],
        f"  lossRate = {'max(0, s1/lossTime)' if t['loss'] else '0'};",
        "  der(s1) = inputRate - f1 - lossRate;",
        *[f"  der(s{i}) = f{i-1} - f{i};" for i in range(2, n + 1)],
        f"  der(delivered) = f{n};",
        "  der(lost) = lossRate;",
        f"end {name};", ""
    ]
    return "\n".join(lines)


def prepare(data, out):
    results = generate(data)
    view = arm_view(data, "D")
    out.mkdir(parents=True, exist_ok=False)
    for c in results["candidates"]:
        text = modelica(c, data["construction"]["input_profile"])
        name = "DStockFlow_" + c["structure_hash"][7:19]
        (out / (name + ".mo")).write_text(text, encoding="utf-8", newline="\n")
        c["modelica_file"] = name + ".mo"
        c["modelica_sha256"] = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    (out / "candidates.json").write_bytes(canonical(results) + b"\n")
    submission = {"schema": SUBMISSION_SCHEMA, "arm_id": "D", "round_id": data["round_id"],
                  "iteration": 0, "parent_revision_id": None,
                  "native_artifact_sha256": digest(results), "method_version": METHOD,
                  "hypothesis_ids": [c["id"] for c in results["candidates"]],
                  "status": "PROPOSED", "unknowns": ["STRUCTURE_UNIDENTIFIED"],
                  "assumption_ids": ["PUBLIC_NOMINAL_VALUES"],
                  "evidence_refs": [data["source_snapshot_hash"]],
                  "notes": "No G2/G3 or empirical identification claims"}
    validate_submission(view, submission)
    event = trace_event(arm_id="D", round_id=data["round_id"],
                        event_type="HYPOTHESIS_PROPOSED", iteration=0,
                        source_hash=view["input_hash"], payload_hash=digest(results))
    (out / "submission.json").write_bytes(canonical(submission) + b"\n")
    (out / "memory-event.json").write_bytes(canonical(event) + b"\n")
    return {"generated": len(results["candidates"]), "ids": submission["hypothesis_ids"],
            "state": "G0_G1_ONLY", "input_hash": view["input_hash"]}


def verify_csv(path, n, profile, tolerance=0.008):
    check(1 <= n <= 3, "BAD_STOCK_COUNT")
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    check(len(rows) >= 4, "INSUFFICIENT_SOLVER_OUTPUT")
    prev_t = -1.
    prev_delivered = 0.
    for row in rows:
        t = float(row["time"])
        delivery = float(row["delivered"])
        lost = float(row["lost"])
        stocks = [float(row[f"s{i}"]) for i in range(1, n + 1)]
        check(all(math.isfinite(v) for v in (t, delivery, lost, *stocks)), "NONFINITE_MODEL_OUTPUT")
        check(t >= prev_t and delivery >= prev_delivered - tolerance, "BAD_TIME_OR_DELIVERY")
        check(min(stocks + [delivery, lost]) >= -tolerance, "NEGATIVE_STATE")
        mass = profile["rate"] * min(max(t, 0), profile["duration"])
        check(abs(sum(stocks) + delivery + lost - mass) <= tolerance, "MASS_BALANCE_FAIL")
        prev_t, prev_delivered = t, delivery
    check(abs(float(rows[0]["time"])) <= 1e-9, "MISSING_TIME_ZERO")
    return {"status": "G2_MASS_BALANCE_PASS_NOT_G3", "rows": len(rows),
            "delivered_final": prev_delivered}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare", "verify"])
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--stocks", type=int)
    a = ap.parse_args()
    data = json.loads(a.input.read_text(encoding="utf-8"))
    validate_case(data)
    if a.action == "prepare":
        check(a.out is not None, "MISSING_OUTPUT_PATH")
        result = prepare(data, a.out)
    else:
        check(a.csv is not None and a.stocks is not None, "MISSING_CSV_PATH_OR_STOCKS")
        result = verify_csv(a.csv, a.stocks, data["construction"]["input_profile"])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
