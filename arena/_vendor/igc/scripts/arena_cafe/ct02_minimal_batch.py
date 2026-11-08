"""CT-02: exactly TWO predeclared engineering simulations, original D0 + Short E1 M.

No solver is run by prepare/verify. A separately authorized single-shot Actions
job calls OMC once per generated script, with one simulate(...) per script.
No world parameters, heldout values, model revision, Buffalo or scoring enter.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_d_v01 import verify_csv
from scripts.arena_cafe.ct03_d_prepare import prepare as prepare_d, PROFILE
from scripts.arena_cafe.ct03_m_prepare import prepare as prepare_m
from scripts.arena_cafe.ct03_m_construction_diagnostic import _sample, sha_bytes
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA = "igc-ct02-exact-two-technical-simulations/1.0"
RESULT = "igc-ct02-technical-conformity-results/1.0"
IMAGE = "openmodelica/openmodelica:v1.26.5-minimal"


def prepared_commands(out: Path, d: dict, m: dict):
    d0, m0 = d["candidates"][0], m["candidates"][0]
    dn = d0["name"]
    mn = "ArenaCT03M." + m0["class_name"]
    # Modelica runtime library inputs stay as the audited original checkout.
    load = [
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
    ]
    dcmd = [
        "getVersion();",
        'loadFile("/repo/' + (out / "D" / (dn + ".mo")).as_posix() + '");',
        "checkModel(" + dn + ");",
        "print(getErrorString());",
        "simulate(" + dn + ',startTime=0,stopTime=8,numberOfIntervals=64,'
        'method="euler",outputFormat="csv",fileNamePrefix="' +
        (out / "d00").as_posix() + '");',
        "print(getErrorString());",
    ]
    mcmd = load + [
        'loadFile("/repo/' + (out / "M" / "native.mo").as_posix() + '");',
        "checkModel(" + mn + ");",
        "print(getErrorString());",
        "simulate(" + mn + ',startTime=0,stopTime=8,numberOfIntervals=64,'
        'method="euler",outputFormat="csv",fileNamePrefix="' +
        (out / "m00").as_posix() + '");',
        "print(getErrorString());",
    ]
    for name, commands in (("D", dcmd), ("M", mcmd)):
        content = "\n".join(commands) + "\n"
        require(content.count("simulate(") == 1, "CT02_ONE_SIMULATE_PER_SCRIPT")
        (out / (name + "-single.mos")).write_text(content, encoding="utf-8", newline="\n")
    return d0, m0


def prepare(out: Path):
    out = Path(out)
    require(not out.exists(), "CT02_REFUSE_OVERWRITE")
    require(not out.is_absolute(), "CT02_RELATIVE_ARTIFACT_PATH_REQUIRED")
    require(".." not in out.parts, "CT02_PATH_ESCAPE")
    out.mkdir(parents=True)
    d = prepare_d(out / "D")
    m = prepare_m(out / "M")
    d0, m0 = prepared_commands(out, d, m)
    items = [
        {
            "arm": "D", "candidate_id": d0["id"],
            "native_sha256": d0["native_modelica_sha256"],
            "script_sha256": sha_bytes((out/"D-single.mos").read_bytes()),
            "command_file": "D-single.mos", "csv_file": "d00_res.csv",
            "solver_log_file": "D-omc.log", "output_column": "delivered",
        },
        {
            "arm": "M", "candidate_id": m0["canonical_sha256"],
            "parent_ast_sha256": m0["full_ast_sha256"],
            "native_sha256": m["native_modelica_sha256"],
            "script_sha256": sha_bytes((out/"M-single.mos").read_bytes()),
            "command_file": "M-single.mos", "csv_file": "m00_res.csv",
            "solver_log_file": "M-omc.log", "output_column": "deliveredTotal",
        },
    ]
    plan = {
        "schema": SCHEMA, "purpose": "TECHNICAL_CONFORMITY_ONLY_NOT_CT03_G2",
        "authorized": False, "actual_omc_runs": 0, "planned_omc_runs": 2,
        "provider_calls": 0, "des_runs": 0,
        "image": IMAGE, "method": "euler", "start_h": 0, "stop_h": 8,
        "intervals": 64, "dt_h": 0.125, "items": items,
        "selection": "FIXED_FIRST_ORIGINAL_D_AND_M_NO_FIT_NO_RANKING",
        "world_selected": False, "reserved_truth_opened": False,
    }
    (out/"batch.json").write_bytes(canonical(plan)+b"\n")
    return plan


def _full_end(csv_path: Path, column: str):
    import csv
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        require(reader.fieldnames is not None and
                reader.fieldnames.count("time") == 1 and
                reader.fieldnames.count(column) == 1,
                "CT02_NATIVE_EXPECTED_ROOT_CSV_COLUMNS_MISSING")
        times = []
        for row in reader:
            t = float(row["time"])
            v = float(row[column])
            require(math.isfinite(t) and math.isfinite(v),
                    "CT02_CSV_NONFINITE")
            times.append(t)
    require(times and abs(times[0]) <= 1e-8 and
            abs(times[-1] - 8) <= 1e-8,
            "CT02_CSV_NOT_FULL_0_TO_8")
    return len(times)


def _checked_plan(out: Path, *, git_sha: str, run_id: str):
    plan = json.loads((out/"batch.json").read_text(encoding="utf-8"))
    require(plan["schema"] == SCHEMA and plan["planned_omc_runs"] == 2 and
            plan["actual_omc_runs"] == 0 and len(plan["items"]) == 2 and
            [x["arm"] for x in plan["items"]] == ["D", "M"],
            "CT02_TECHNICAL_BATCH_NOT_FIXED")
    require(type(git_sha) is str and len(git_sha) == 40 and
            all(c in "0123456789abcdef" for c in git_sha),
            "CT02_FROZEN_SHA_REQUIRED")
    require(type(run_id) is str and run_id.isdigit(),
            "CT02_GITHUB_ACTIONS_RUN_ID_REQUIRED")
    return plan


def _check_one(out: Path, item: dict):
    """Existing physical/identity checks, immediately after each OMC call."""
    script = out / item["command_file"]
    trace = out / item["csv_file"]
    log = out / item["solver_log_file"]
    require(sha_bytes(script.read_bytes()) == item["script_sha256"] and
            script.read_text().count("simulate(") == 1,
            "CT02_EXECUTED_SCRIPT_CHANGED_OR_MULTIPLE_SIMULATIONS")
    require(trace.is_file() and log.is_file() and log.stat().st_size > 0,
            "CT02_NO_ACTUAL_TRACE_OR_SOLVER_LOG")
    require("v1.26.5" in log.read_text(encoding="utf-8", errors="replace") or
            "1.26.5" in log.read_text(encoding="utf-8", errors="replace"),
            "CT02_UNEXPECTED_SOLVER_VERSION_IN_LOG")
    row_count = _full_end(trace, item["output_column"])
    if item["arm"] == "D":
        d = json.loads((out/"D/manifest.json").read_text())
        c = d["candidates"][0]
        require(sha_bytes((out/"D"/(c["name"]+".mo")).read_bytes()) ==
                item["native_sha256"], "CT02_D_ORIGINAL_MODEL_CHANGED")
        result = verify_csv(trace, len(c["structure"]["stocks"]), PROFILE)
        require(result["status"] == "G2_MASS_BALANCE_PASS_NOT_G3",
                "CT02_D_PHYSICAL_CONFORMITY_FAILED")
    else:
        m = json.loads((out/"M/manifest.json").read_text())
        require(sha_bytes((out/"M/native.mo").read_bytes()) ==
                item["native_sha256"], "CT02_M_ORIGINAL_MODEL_CHANGED")
        sampled, count = _sample(trace.read_bytes(), "deliveredTotal")
        require(len(sampled) == 4 and count == row_count,
                "CT02_M_NATIVE_CONSTRUCTION_CUTS_MISSING")
    return {
        "arm": item["arm"], "candidate_id": item["candidate_id"],
        "native_sha256": item["native_sha256"],
        "script_sha256": item["script_sha256"],
        "csv_sha256": sha_bytes(trace.read_bytes()),
        "solver_log_sha256": sha_bytes(log.read_bytes()),
        "output_column": item["output_column"],
        "csv_rows": row_count, "technical_status": "CSV_CHECKS_PASS_NOT_SCIENTIFIC_G2",
    }


def verify_arm(out: Path, *, arm: str, git_sha: str, run_id: str):
    """Fail the batch before M if D's CSV/log/physical conservation fails."""
    out = Path(out)
    plan = _checked_plan(out, git_sha=git_sha, run_id=run_id)
    require(arm in ("D", "M"), "CT02_UNKNOWN_ARM")
    return _check_one(out, next(item for item in plan["items"] if item["arm"] == arm))


def verify(out: Path, *, git_sha: str, run_id: str):
    out = Path(out)
    plan = _checked_plan(out, git_sha=git_sha, run_id=run_id)
    entries = [_check_one(out, item) for item in plan["items"]]
    report = {
        "schema": RESULT, "status": "TWO_TECHNICAL_CSVS_CHECKED_NOT_CT03_SCIENTIFIC_ACCEPTANCE",
        "run_id": run_id, "git_sha": git_sha,
        "runner": "GitHub Actions per-run logs and uploaded original bytes",
        "solver_image": IMAGE, "planned_omc": 2, "attempted_omc": 2,
        "successful_omc_csvs": 2, "provider_posts": 0,
        "source_plan_sha256": digest(plan),
        "outputs": entries, "world_selected": False,
        "heldout_opened": False,
    }
    dest = out/"conformity.json"
    require(not dest.exists(), "CT02_CONFORMITY_REFUSE_OVERWRITE")
    dest.write_bytes(canonical(report)+b"\n")
    return report


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="mode", required=True)
    a=sub.add_parser("prepare")
    a.add_argument("--out", required=True, type=Path)
    for mode in ("verify", "verify-arm"):
        b=sub.add_parser(mode)
        b.add_argument("--out", required=True, type=Path)
        b.add_argument("--git-sha", required=True)
        b.add_argument("--run-id", required=True)
        if mode == "verify-arm":
            b.add_argument("--arm", required=True, choices=("D", "M"))
    args=p.parse_args()
    if args.mode == "prepare":
        report = prepare(args.out)
    elif args.mode == "verify-arm":
        report = verify_arm(args.out, arm=args.arm,
                            git_sha=args.git_sha, run_id=args.run_id)
    else:
        report = verify(args.out, git_sha=args.git_sha, run_id=args.run_id)
    print(json.dumps({"status": report.get("status", report.get("purpose",
                        report.get("technical_status"))),
                      "planned_omc": 2, "executed_here": 0, "provider_posts": 0}))


if __name__=="__main__":
    main()
