"""CT-02/03: prepare original D grammar/renderer six alternatives without fake data.

Only public pulse and explicit nominal parameters enter preflight. When actual
construction observations exist, bind them through D0.generate() and verify
the six original grammar IDs before any solver. D2 reset-trial path is not
activated. No solver, provider, fitting, grid search or world selection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from scripts.arena_v0_contract import INPUT_SCHEMA, canonical, digest
from scripts.arena_d_v01 import topology, lint_structure, modelica, generate
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT, validate_construction

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "igc-ct03-d-original-six-preparation/1.0"
D_BLOB = "9dcab2bf1ee3a3c7430595385f381d89ba023a6d"
NOMINAL = {"capacity": 2, "response_time": 1, "loss_time": 3}
PROFILE = {"kind": "pulse", "rate": PUBLIC_INPUT["pulse_rate"],
           "duration": PUBLIC_INPUT["pulse_end"]}


def need(cond, message):
    if not cond:
        raise ValueError(message)


def _sha(content: bytes):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _original_source():
    raw = (ROOT/"scripts/arena_d_v01.py").read_bytes()
    blob = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    need(blob == D_BLOB, "CT03_D_ORIGINAL_GENERATOR_SOURCE_DRIFT")


def original_six():
    _original_source()
    rows, sources = [], []
    for n in (1, 2, 3):
        for loss in (False, True):
            structure = topology(n, loss)
            lint_structure(structure)
            structural_hash = digest(structure)
            candidate = {
                "id": "D-" + structural_hash[7:19],
                "structure": structure,
                "structure_hash": structural_hash,
                "nominal_parameters": dict(NOMINAL),
                "parameter_status": "PUBLIC_ASSUMPTIONS_NOT_FITTED",
                "lint": lint_structure(structure),
            }
            source = modelica(candidate, PROFILE)
            name = "DStockFlow_" + structural_hash[7:19]
            rows.append({**candidate, "name": name,
                         "csv_prefix": "d" + str(len(rows)).zfill(2),
                         "native_modelica_sha256": _sha(source.encode("utf-8")),
                         "G2": "NOT_EXECUTED", "G3": "NOT_EXECUTED"})
            sources.append(source)
    need(len(rows) == 6 and len({r["id"] for r in rows}) == 6,
         "CT03_D_SIX_GRAMMAR_STRUCTURES_REQUIRED")
    return rows, sources


def prepare(out: Path):
    out = Path(out)
    need(not out.exists(), "CT03_D_REFUSE_OVERWRITE")
    rows, sources = original_six()
    out.mkdir(parents=True,exist_ok=False)
    commands = ["getVersion();"]
    for row, source in zip(rows, sources):
        fname = row["name"] + ".mo"
        (out/fname).write_text(source, encoding="utf-8", newline="\n")
        commands.extend([
            'loadFile("'+fname+'");',
            "checkModel(" + row["name"] + ");",
            "print(getErrorString());",
            "simulate(" + row["name"] +
              ',startTime=0,stopTime=8,numberOfIntervals=64,method="euler",'
              'outputFormat="csv",fileNamePrefix="'+row["csv_prefix"]+'");',
            "print(getErrorString());",
        ])
    (out/"simulate.mos").write_text("\n".join(commands)+"\n",encoding="utf-8",newline="\n")
    report = {
        "schema": SCHEMA,
        "source_definition": PUBLIC_INPUT,
        "source_definition_sha256": digest(PUBLIC_INPUT),
        "original_D_blob": D_BLOB,
        "nominal_parameters": NOMINAL,
        "nominal_parameters_status": "EXPLICIT_UNVALIDATED_ASSUMPTION",
        "candidate_count": 6, "candidates": rows,
        "D2": "NOT_APPLICABLE_MISSING_RESET_TRIAL",
        "construction_observations_read": False,
        "world_parameters_read": False, "reserved_truth_read": False,
        "candidate_selection": "NONE",
        "planned_script_sha256": _sha((out/"simulate.mos").read_bytes()),
        "planned_new_omc": 6, "executed_new_omc": 0, "provider_calls": 0,
        "status": "SIX_NATIVE_D_ALTERNATIVES_PREPARED_NOT_SOLVED"
    }
    (out/"manifest.json").write_bytes(canonical(report)+b"\n")
    return report


def bind_authentic_construction(construction: dict, context: dict, manifest: dict):
    """Invoke original D0.generate on actual four public cuts; no placeholders."""
    need(manifest.get("schema") == SCHEMA and
         manifest.get("nominal_parameters") == NOMINAL and
         manifest.get("candidate_count") == 6, "CT03_D_MANIFEST_MISMATCH")
    points = validate_construction(context, construction)
    data = {
        "schema": INPUT_SCHEMA,
        "investigation_id": "ct03-abstract-aggregate",
        "round_id": "ct03-d-initial",
        "question": "Model the aggregate conserved material pulse with six D alternatives",
        "construction": {
            "input_profile": dict(PROFILE),
            "nominal_parameters": dict(NOMINAL),
            "observations": [{"t": x["time"], "delivered": x["delivered"]} for x in points],
        },
        "observability": {"stock_unit":"items","time_unit":"hour",
                          "observable":"cumulative_delivered"},
        "source_snapshot_hash": context["source_hash"],
        "iteration_limit": 2,
        "resources": {"max_stocks":3,"allow_loss":True,
                      "max_candidates":6,"max_simulations":6},
    }
    original = generate(data)
    ids = [x["id"] for x in original["candidates"]]
    expected = [x["id"] for x in manifest["candidates"]]
    need(ids == expected and
         all(c["structure"] == e["structure"] and
             c["nominal_parameters"] == e["nominal_parameters"]
             for c,e in zip(original["candidates"],manifest["candidates"])),
         "CT03_D_ORIGINAL_GENERATE_NOT_SAME_SIX")
    return {"schema":"igc-ct03-d-original-generator-public-binding/1.0",
            "source_snapshot_hash":context["source_hash"],
            "actual_construction_hash":digest(construction),
            "native_generator_output_hash":digest(original),
            "candidate_ids":ids,"D2":"NOT_APPLICABLE_MISSING_RESET_TRIAL",
            "G2":"NOT_EXECUTED","new_omc":0,"provider_calls":0}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    x = prepare(args.out)
    print(json.dumps({"status":x["status"],"candidates":x["candidate_count"],
                      "planned_omc":6,"executed_omc":0}))


if __name__ == "__main__":
    main()
