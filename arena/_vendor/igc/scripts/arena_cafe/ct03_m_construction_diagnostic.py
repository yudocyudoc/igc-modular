"""CT-02: typed construction-only diagnostic from one original CT-03 M CSV.

No solver or provider. A receipt ties native source, one original full AST,
the exact original simulation command, native root-variable CSV bytes and the
common public construction observations. The CSV column alone cannot identify
which candidate was executed.
A receipt is not itself independent proof that a solver ran: provenance must
also be audited at the runner boundary before any scientific interpretation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_cafe.ct03_m_prepare import SCHEMA as M_PREP_SCHEMA
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT, validate_construction as _check_public
from scripts.arena_cafe.ct_feedback_bridge import require, _sha

SCHEMA = "igc-ct02-m-native-construction-diagnostic/1.0"
OBS_SCHEMA = "igc-ct03-public-construction-observations/1.0"
RECEIPT_SCHEMA = "igc-ct03-numerical-run-receipt/1.0"
CUTS = (0., 1., 2., 4.)
RESERVED = (6., 8.)


def sha_bytes(data: bytes):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _column(row, name, *, exact=False):
    matches = [v for k, v in row.items() if k == name or
               (not exact and k is not None and k.endswith("." + name))]
    require(len(matches) == 1, "CT02_M_CSV_OUTPUT_MISSING_OR_AMBIGUOUS:" + name)
    try:
        x = float(matches[0])
    except (ValueError, TypeError) as error:
        raise ValueError("CT02_M_CSV_OUTPUT_NOT_NUMERIC") from error
    require(math.isfinite(x), "CT02_M_CSV_NONFINITE")
    return x


def _check_manifest(manifest, parent):
    require(type(manifest) is dict and manifest.get("schema") == M_PREP_SCHEMA and
            manifest.get("source") == PUBLIC_INPUT and
            manifest.get("candidate_count") == 6 and
            manifest.get("executed_new_omc") == 0 and
            manifest.get("provider_calls") == 0 and
            manifest.get("scientific_status") ==
              "PREPARED_NOT_PHYSICALLY_ADJUDICATED",
            "CT02_M_PREPARED_MANIFEST_NOT_AUTHENTICATED")
    require(type(parent) is dict and
            parent.get("G2") == "NOT_EXECUTED" and
            parent.get("G3") == "NOT_EXECUTED" and
            type(parent.get("original_ast")) is dict and
            parent.get("full_ast_sha256") == digest(parent["original_ast"]),
            "CT02_M_MISSING_FULL_ORIGINAL_AST")
    require(sum(x == parent for x in manifest["candidates"]) == 1,
            "CT02_M_PARENT_NOT_FROM_THE_SIX_ORIGINALS")


def _expected_simulation_command(parent):
    """One native OpenModelica invocation for this exact prepared candidate."""
    return (
        "simulate(ArenaCT03M." + parent["class_name"] +
        ',startTime=0,stopTime=8,numberOfIntervals=64,'
        'method="euler",outputFormat="csv",fileNamePrefix="' +
        parent["csv_prefix"] + '");'
    )


def _check_receipt(receipt, parent, manifest, native_bytes, csv_bytes,
                   script_bytes, csv_filename):
    require(type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA and
            receipt.get("candidate_canonical_sha256") == parent["canonical_sha256"] and
            receipt.get("full_ast_sha256") == parent["full_ast_sha256"] and
            receipt.get("source_definition_sha256") == manifest["source_definition_sha256"] and
            receipt.get("modelica_sha256") == sha_bytes(native_bytes) ==
                manifest["native_modelica_sha256"] and
            receipt.get("csv_sha256") == sha_bytes(csv_bytes) and
            receipt.get("simulate_script_sha256") == sha_bytes(script_bytes) ==
                manifest["planned_script_sha256"] and
            receipt.get("simulation_command") == _expected_simulation_command(parent) and
            script_bytes.decode("utf-8").count(receipt["simulation_command"]) == 1 and
            receipt.get("csv_filename") == csv_filename ==
                parent["csv_prefix"] + "_res.csv" and
            receipt.get("solver") == "euler" and
            receipt.get("start_time") == 0 and
            receipt.get("stop_time") == 8 and
            receipt.get("number_of_intervals") == 64 and
            receipt.get("exit_code") == 0 and
            receipt.get("output_role") == "deliveredTotal" and
            receipt.get("model_name") == "ArenaCT03M." + parent["class_name"] and
            receipt.get("csv_prefix") == parent["csv_prefix"] and
            receipt.get("csv_column") == "deliveredTotal",
            "CT02_M_NATIVE_CSV_OR_RUNTIME_RECEIPT_MISMATCH")
    require(set(receipt) == {
        "schema", "candidate_canonical_sha256", "full_ast_sha256",
        "source_definition_sha256", "modelica_sha256", "csv_sha256",
        "solver", "start_time", "stop_time", "number_of_intervals",
        "exit_code", "output_role", "model_name", "csv_prefix", "csv_column",
        "simulate_script_sha256", "simulation_command", "csv_filename",
    }, "CT02_M_RECEIPT_CONTAINS_UNKNOWN_FIELDS")


def _sample(csv_bytes, expected_column):
    try:
        content = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CT02_M_CSV_INVALID_UTF8") from exc
    reader = csv.DictReader(content.splitlines())
    require(reader.fieldnames is not None and
            len(reader.fieldnames) == len(set(reader.fieldnames)),
            "CT02_M_DUPLICATE_OR_MISSING_CSV_COLUMNS")
    # OpenModelica writes root Real deliveredTotal as "deliveredTotal":
    # a class prefix is NOT added by simulate(qualified_class_name, ...).
    # Keep class identity in the command/manifest/receipt; do not synthesize
    # a prefixed CSV header or accept another model's dotted output.
    require(expected_column == "deliveredTotal" and
            reader.fieldnames.count("deliveredTotal") == 1 and
            all(name == "deliveredTotal" or
                not name.endswith(".deliveredTotal") for name in reader.fieldnames),
            "CT02_M_WRONG_OR_AMBIGUOUS_CANDIDATE_CSV_COLUMN")
    sampled = {}
    seen = 0
    last_time = -math.inf
    last_delivery = -1e-7
    for row in reader:
        seen += 1
        t = _column(row, "time")
        delivered = _column(row, expected_column, exact=True)
        require(0 <= t <= 8 + 1e-8 and t >= last_time - 1e-9,
                "CT02_M_UNSORTED_OR_OUTSIDE_HORIZON")
        require(delivered >= -1e-7 and
                delivered + 1e-7 >= last_delivery and
                delivered <= 3.4 + 1e-5,
                "CT02_M_INVALID_NATIVE_DELIVERY_OR_CONSERVATION")
        last_time, last_delivery = t, delivered
        for cut in CUTS:
            if abs(t - cut) <= 1e-8:
                # Multiple solver rows at one exact time are permitted only
                # when the accumulated state agrees.
                if cut in sampled:
                    require(abs(sampled[cut] - delivered) <= 1e-7,
                            "CT02_M_CONFLICTING_SAME_TIME_STOCK")
                sampled[cut] = delivered
    require(seen >= 5 and len(sampled) == 4,
            "CT02_M_EXACT_CONSTRUCTION_CSV_SAMPLES_REQUIRED")
    return sampled, seen


def build(context, *, manifest, parent, construction, receipt,
          modelica_file: Path, simulate_script_file: Path,
          trace_csv: Path) -> dict:
    require(context.get("arm") == "M", "CT02_M_WRONG_ARM")
    _check_manifest(manifest, parent)
    observed = _check_public(context, construction)
    modelica_bytes = Path(modelica_file).read_bytes()
    csv_bytes = Path(trace_csv).read_bytes()
    script_bytes = Path(simulate_script_file).read_bytes()
    _check_receipt(receipt, parent, manifest, modelica_bytes, csv_bytes,
                   script_bytes, Path(trace_csv).name)
    sample, count = _sample(csv_bytes, receipt["csv_column"])
    points = [
        {"time": int(cut), "observed": float(obs["delivered"]),
         "simulated": sample[cut],
         "residual": sample[cut] - float(obs["delivered"])}
        for cut, obs in zip(CUTS, observed)
    ]
    parent_hash = digest(parent["original_ast"])
    return {
        "arm": "M", "condition": context["condition"],
        "source_hash": context["source_hash"],
        "parent_hash": parent_hash,
        "evidence": "G3",
        "trace_sha256": sha_bytes(csv_bytes),
        "modelica_sha256": sha_bytes(modelica_bytes),
        "solver_receipt_sha256": digest(receipt),
        "simulation_command_sha256": sha_bytes(
            receipt["simulation_command"].encode("utf-8")),
        "native_output_column": "deliveredTotal",
        "native_output_filename": receipt["csv_filename"],
        "diagnostic_schema": SCHEMA,
        "numerical_provenance": "BYTE_BOUND_SOLVER_RECEIPT_NOT_INDEPENDENT_PROOF",
        "construction_evidence": "ACTUAL_PUBLIC_VALUES_NOT_MOCK_DEFAULT",
        "own_evidence_only": True, "no_future_truth": True,
        "observations": points, "native_samples": count,
        "reserved_world_truth_visible": False,
        "G2": "RECEIPT_CROSS_CHECKED_PHYSICAL_RUN_NOT_INDEPENDENTLY_CERTIFIED",
        "G3": "CONSTRUCTION_RESIDUALS_ONLY_NO_HELDOUT",
    }


def main():
    p = argparse.ArgumentParser()
    for arg in ("manifest", "parent", "construction", "receipt", "context"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--native", type=Path, required=True)
    p.add_argument("--simulate-script", type=Path, required=True)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    require(not args.out.exists(), "CT02_REFUSE_OVERWRITE")
    def get(path):
        return json.loads(path.read_text(encoding="utf-8"))
    result = build(get(args.context), manifest=get(args.manifest),
                   parent=get(args.parent), construction=get(args.construction),
                   receipt=get(args.receipt), modelica_file=args.native,
                   simulate_script_file=args.simulate_script,
                   trace_csv=args.csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"schema": SCHEMA, "status": result["G3"],
                      "provider_calls": 0, "new_omc": 0}))


if __name__ == "__main__":
    main()
