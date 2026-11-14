"""Coffee B0: exactly twelve original D/M Modelica attempts, no CT-03 reuse.

The model input is the proven GitHub artifact from the D/M native campaign.
No R2, Cloudflare AI, secret, holdout, feedback revision, or scientific lock.
CheckModel and simulate are distinguishable and their logs/CSV are retained.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

from .common import ArenaError, digest, read_json, write_json
from .connections import Secret
from .github import GitHub
from .coffee_domain import project_native_counter
from .coffee_adapters.shared import sha_bytes
from . import coffee_dm_campaign as dm
from . import runtime

REPO = "yudocyudoc/igc-modular"
SOURCE_RUN = 43547506584
SOURCE_SHA = "ad939be28597139eb7868dfc37f3f39fa5475205"
ARTIFACT_ID = 14095080561
ARCHIVE_SHA = "d7d91f825c4d63fe334592f282fea5acf33844ac8487f94feb8e69d86b55414c"
SOURCE_WORKFLOW = ".github/workflows/coffee-dm-native.yml"
WORKFLOW = ".github/workflows/coffee-dm-modelica.yml"
IMAGE = runtime.IMAGE
MAX_ATTEMPTS = 12
MAX_CHECKS = 12
MAX_SIMULATIONS = 12
INTERVALS = 64
HORIZON = 103.237 / 60.0
MASS_TOLERANCE = 0.015
R2_AND_PROVIDER = dm.NO_R2
MEMBERS = {
    "attestation.json", "audit.json", "native/public-case.json", "native/summary.json",
    "native/D/manifest.json", "native/M/manifest.json",
    "native/M/native.mo", "native/M/check-only.mos",
    "native/M/registry-snapshot.json",
    "public/producer-public-b0.json", "public/release.json",
    "native/D/DStockFlow_1b03f4d80336.mo",
    "native/D/DStockFlow_5bc57655500f.mo",
    "native/D/DStockFlow_5f8781847cb6.mo",
    "native/D/DStockFlow_9a46b6a3ba32.mo",
    "native/D/DStockFlow_b4030cf49cc3.mo",
    "native/D/DStockFlow_ba433938dfc8.mo",
}


def need(ok, reason):
    if not ok:
        raise ArenaError("COFFEE_DM_G2_" + reason)


def identity(env=None):
    env = os.environ if env is None else env
    need(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
         and env.get("GITHUB_REF") == "refs/heads/main"
         and env.get("GITHUB_REPOSITORY") == REPO
         and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and env.get("COFFEE_DM_OMC_AUTH") == "yes"
         and env.get("COFFEE_DM_OMC_MAX") == "12"
         and re.fullmatch(r"[1-9][0-9]{0,19}", env.get("GITHUB_RUN_ID", "")),
         "MANUAL_FIRST_ATTEMPT_BUDGET_REQUIRED")
    need(not any(env.get(name) for name in R2_AND_PROVIDER),
         "FORBIDDEN_PRIVATE_OR_PROVIDER_SECRET")
    return int(env["GITHUB_RUN_ID"])


def history(api, current):
    """A second dispatch cannot silently consume a new G2 initial batch."""
    runs = api.repo("GET", "/actions/workflows/coffee-dm-modelica.yml/runs?event=workflow_dispatch&per_page=100")
    need(type(runs.get("total_count")) is int
         and runs["total_count"] <= 100
         and isinstance(runs.get("workflow_runs"), list)
         and len(runs["workflow_runs"]) == runs["total_count"],
         "G2_RUN_HISTORY_INCOMPLETE")
    previous = [r.get("id") for r in runs["workflow_runs"]
                if r.get("id") != current]
    need(not previous, "G2_PRIOR_RUN_REQUIRES_INDEPENDENT_RECONCILIATION")
    return {"previous_dispatches": 0, "first_g2_batch": True}


def zip_bytes(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 200_000,
         "ORIGINAL_NATIVE_ARTIFACT_ARCHIVE_SIZE")
    need(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA,
         "ORIGINAL_NATIVE_ARTIFACT_HASH_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            need(len(entries) == len(MEMBERS)
                 and {x.filename for x in entries} == MEMBERS
                 and all(not x.is_dir() and
                         not (x.external_attr >> 16 & 0o170000 == 0o120000)
                         and x.file_size < 100_000
                         for x in entries)
                 and sum(x.file_size for x in entries) < 300_000,
                 "ORIGINAL_NATIVE_ZIP_CONTENTS_UNEXPECTED")
            return {x.filename: archive.read(x) for x in entries}
    except (OSError, zipfile.BadZipFile, ValueError):
        raise ArenaError("COFFEE_DM_G2_ORIGINAL_NATIVE_ZIP_UNREADABLE") from None


def stage(root, *, env=None, api=None):
    env = os.environ if env is None else env
    run_id = identity(env)
    root = Path(root)
    need(not root.exists(), "REFUSE_STAGE_OVERWRITE")
    if api is None:
        need(bool(env.get("GH_TOKEN")), "GITHUB_READ_TOKEN_REQUIRED")
        api = GitHub(REPO, Secret(env["GH_TOKEN"], "GITHUB_TOKEN"))
    history(api, run_id)
    run = api.run(SOURCE_RUN)
    need(run.get("id") == SOURCE_RUN and
         run.get("path") == SOURCE_WORKFLOW and
         run.get("head_sha") == SOURCE_SHA and
         run.get("head_branch") == "main" and
         run.get("event") == "push" and
         run.get("run_attempt") == 1 and
         run.get("status") == "completed" and
         run.get("conclusion") == "success",
         "SOURCE_NATIVE_RUN_NOT_VERIFIED")
    meta = api.repo("GET", f"/actions/artifacts/{ARTIFACT_ID}")
    need(meta.get("id") == ARTIFACT_ID
         and meta.get("name") == f"coffee-dm-native-{SOURCE_RUN}"
         and meta.get("expired") is False
         and meta.get("digest") == "sha256:" + ARCHIVE_SHA
         and meta.get("workflow_run", {}).get("id") == SOURCE_RUN,
         "SOURCE_NATIVE_ARTIFACT_NOT_VERIFIED")
    data = zip_bytes(api.repo("GET", f"/actions/artifacts/{ARTIFACT_ID}/zip",
                              binary=True))
    root.mkdir(parents=True,mode=0o700)
    inp = root / "input"
    inp.mkdir(mode=0o700)
    for name, raw in sorted(data.items()):
        target = inp / name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as output:
            output.write(raw)
    with TemporaryDirectory() as temp:
        # Re-audit actual original files instead of trusting a JSON status.
        checked = dm.audit(inp, out=Path(temp) / "audit.json")
        need(checked == read_json(inp / "audit.json")
             and checked["status"] ==
                 "TWELVE_NATIVE_CANDIDATES_STATIC_AUDITED_NOT_SIMULATED"
             and checked["case_sha256"] == dm.CASE_SHA256
             and checked["source_artifact_id"] == dm.ARTIFACT_ID,
             "REAL_NATIVE_AUDIT_UNVERIFIED")
    planned = plan(root)
    write_json(root / "stage-receipt.json", {
        "schema": "arena.coffee-peak.dm-g2-stage/1",
        "status": "TWELVE_ORIGINALS_ADMITTED_FOR_ONE_G2_BATCH_NOT_YET_RUN",
        "execution_run_id": run_id, "native_source_run_id": SOURCE_RUN,
        "native_artifact_id": ARTIFACT_ID,
        "native_artifact_sha256": "sha256:" + ARCHIVE_SHA,
        "case_sha256": dm.CASE_SHA256,
        "planned": len(planned["candidates"]), "max_omc_attempts": MAX_ATTEMPTS,
        "provider_posts": 0, "new_omc": 0,
        "truth_access": False, "r2_access": False,
        "scientific_lock_created": False}, exclusive=True)
    return {"status": "G2_STAGED_ZERO_OMC", "candidates": 12,
            "provider_posts": 0, "new_omc": 0}


def plan(root):
    root = Path(root)
    audit = read_json(root / "input/audit.json")
    need(audit.get("case_sha256") == dm.CASE_SHA256, "PUBLIC_CASE_DRIFT")
    folder = root / "commands"
    need(not folder.exists(), "REFUSE_COMMAND_OVERWRITE")
    folder.mkdir()
    candidates = []
    for arm in ("D", "M"):
        m = read_json(root / f"input/native/{arm}/manifest.json")
        audited = audit["arms"][arm]["candidates"]
        need(len(m["candidates"]) == len(audited) == 6, "SIX_PER_ARM_REQUIRED")
        for i, (candidate, check) in enumerate(zip(m["candidates"], audited)):
            need(candidate["id"] == check["candidate_id"]
                 and check["status"] == "STATIC_STRUCTURE_CHECKED_NOT_COMPILED",
                 "STATIC_REJECTED_CANNOT_RUN_OMC")
            short = arm.lower() + f"{i:02d}"
            cls = candidate["modelica_class"]
            need(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?",
                              cls) is not None, "MODEL_NAME_UNTRUSTED")
            model_file = (f"input/native/D/{candidate['modelica_file']}" if arm=="D"
                          else "input/native/M/native.mo")
            model_bytes = (root / model_file).read_bytes()
            name = candidate["modelica_file"] if arm == "D" else "native.mo"
            need(sha_bytes(model_bytes) == m["files"][name]["sha256"],
                 "NATIVE_MODEL_BYTES_CHANGED")
            prefix = f"/work/results/{arm}/{short}"
            src = [f'loadFile("/work/{model_file}");'] if arm=="D" else [
                'loadFile("/models/IGCMolecules.mo");',
                'loadFile("/models/IGCInformationMolecules.mo");',
                'loadFile("/work/input/native/M/native.mo");',
            ]
            mos = "\n".join([
                "getVersion();", *src, f"checkModel({cls});",
                "print(getErrorString());",
                f'simulate({cls},startTime=0,stopTime={HORIZON:.16g},'
                f'numberOfIntervals={INTERVALS},method="euler",'
                f'outputFormat="csv",fileNamePrefix="{prefix}");',
                "print(getErrorString());", ""
            ])
            need(mos.count("simulate(") == 1 and
                 mos.count("checkModel(") == 1, "ONE_OMC_SCRIPT_PER_CANDIDATE")
            script = folder / f"{short}.mos"
            with script.open("x", encoding="utf-8",newline="\n") as fd:
                fd.write(mos)
            stocks = ([f"s{j}" for j in range(1,len(candidate["structure"]["stocks"])+1)]
                      if arm == "D" else [
                          x["id"]+".waiting" for x in candidate["full_ast"]["instances"]
                          if x["role"] in ("preparation","dispatch","transit")
                      ])
            need(1 <= len(stocks) <= 4, "STOCK_COLUMNS_NOT_DEFINED")
            candidates.append({
                "arm": arm, "index": i, "prefix": short,
                "id": candidate["id"], "modelica_class": cls,
                "model_file": model_file,
                "model_sha256": sha_bytes(model_bytes),
                "script": f"commands/{short}.mos",
                "script_sha256": sha_bytes(script.read_bytes()),
                "csv": f"results/{arm}/{short}_res.csv",
                "log": f"logs/{arm}/{short}.log",
                "counter": "delivered" if arm=="D" else "deliveredTotal",
                "stocks": stocks, "loss_counter": "lost" if arm=="D" else None,
                "material_projection_is_dynamic_equivalence": False,
                "solver_check_status": "NOT_RUN",
                "solver_simulate_status": "NOT_RUN",
            })
    need(len(candidates) == MAX_ATTEMPTS and
         [r["arm"] for r in candidates] == ["D"]*6+["M"]*6,
         "BUDGET_CANDIDATE_PLAN_INVALID")
    plan = {"schema": "arena.coffee-peak.dm-g2-plan/1",
            "status": "TWELVE_MODEL_SCRIPTS_PREPARED_ZERO_OMC",
            "case_sha256": dm.CASE_SHA256,
            "source_native_artifact_id": ARTIFACT_ID,
            "source_native_zip_sha256": "sha256:" + ARCHIVE_SHA,
            "modelica_image": IMAGE,
            "msl_commit": runtime.MSL[1],
            "systemdynamics_commit": runtime.SD[1],
            "method": "euler", "start_hour": 0,
            "stop_hour": HORIZON, "number_of_intervals": INTERVALS,
            "max_new_omc_attempts": MAX_ATTEMPTS,
            "max_check_models": MAX_CHECKS,
            "max_simulations": MAX_SIMULATIONS,
            "policy": "ONE_CONTAINER_PER_CANDIDATE_NO_RETRY; CONTINUE_OTHER_INITIALS",
            "candidates": candidates,
            "truth_access": False, "provider_posts": 0,
            "new_omc_executed": 0, "scientific_lock_created": False}
    write_json(root / "plan.json",plan,exclusive=True)
    return plan


def verify_csv(path, item, *, tolerance=MASS_TOLERANCE):
    """Material state conservation from the real OMC output, not POS pickup data."""
    with Path(path).open(newline="",encoding="utf-8-sig") as fd:
        reader = csv.DictReader(fd)
        names = reader.fieldnames or []
        columns = ["time", item["counter"], *item["stocks"]]
        if item["loss_counter"] is not None:
            columns.append(item["loss_counter"])
        need(len(set(names)) == len(names)
             and all(names.count(column) == 1 for column in columns),
             "MODEL_CSV_REQUIRED_MATERIAL_COLUMNS_MISSING")
        rows = []
        for row in reader:
            need(len(rows) < 100_000, "MODEL_CSV_TOO_MANY_SAMPLES")
            vals = {k: float(row[k]) for k in columns}
            need(all(math.isfinite(v) for v in vals.values()),
                 "MODEL_CSV_NONFINITE")
            rows.append(vals)
    need(len(rows) >= INTERVALS + 1, "MODEL_CSV_INSUFFICIENT_ROWS")
    need(abs(rows[0]["time"]) <= 1e-8
         and abs(rows[-1]["time"] - HORIZON) <= 1e-6,
         "MODEL_CSV_TIME_COVERAGE_MISSING")
    prev_t, prev_y, max_balance = -1.0, -1e-8, 0.0
    trace=[]
    for row in rows:
        t, y = row["time"], row[item["counter"]]
        need(t >= prev_t and t >= -1e-8 and
             t <= HORIZON + 1e-6 and
             y >= prev_y - tolerance, "MODEL_CSV_TIME_OR_COUNTER_NONMONOTONE")
        quantities = [row[k] for k in item["stocks"]]
        if item["loss_counter"]:
            quantities.append(row[item["loss_counter"]])
        need(min(quantities + [y]) >= -tolerance,
             "MODEL_CSV_NEGATIVE_MATERIAL")
        assumed_input = 10.0 * min(max(t,0.0),HORIZON)
        residual = abs(sum(quantities) + y - assumed_input)
        max_balance=max(max_balance,residual)
        need(residual <= tolerance, "MODEL_CSV_MATERIAL_BALANCE_FAILURE")
        trace.append({"time":t,item["counter"]:y})
        prev_t, prev_y = t, y
    from .coffee_domain import project_native_counter
    projected=project_native_counter(trace,arm=item["arm"],
            native_counter=item["counter"],time_unit="hours")
    return {
        "status": "G2_NATIVE_CSV_FINITE_NONNEGATIVE_BALANCED_NOT_G3",
        "samples":len(rows), "last_hours":rows[-1]["time"],
        "max_abs_balance_orders":max_balance,
        "mass_tolerance_orders":tolerance,
        "source_counter":item["counter"],
        "stock_columns":item["stocks"],
        "post_payment_loss_counter":item["loss_counter"],
        "sampling":projected["rule"],
        "provisional_unsealed_predicted_pickups":projected["predictions"],
        "operator_status": "UNSEALED_ENGINEERING_PROJECTION_NOT_SCIENTIFIC_SCORE",
    }


def run_batch(root, *, env=None, cli=subprocess.run):
    env = dict(os.environ if env is None else env)
    run_id = identity(env)
    root=Path(root).resolve()
    plan = read_json(root / "plan.json")
    proof = read_json(root / "stage-receipt.json")
    need(plan.get("schema") == "arena.coffee-peak.dm-g2-plan/1"
         and plan.get("max_new_omc_attempts") == 12
         and plan.get("max_check_models") == 12
         and plan.get("max_simulations") == 12
         and plan.get("source_native_artifact_id") == ARTIFACT_ID
         and proof.get("execution_run_id") == run_id
         and proof.get("status") == "TWELVE_ORIGINALS_ADMITTED_FOR_ONE_G2_BATCH_NOT_YET_RUN"
         and len(plan.get("candidates",[])) == 12,
         "SOURCE_OR_FIXED_BUDGET_MISMATCH")
    need(not (root / "result.json").exists() and
         not (root / "attempts.jsonl").exists(), "REFUSE_RERUN")
    need((Path(env["RUNNER_TEMP"])/"e1-libs/msl").is_dir()
         and (Path(env["RUNNER_TEMP"])/"e1-libs/systemdynamics").is_dir()
         and (Path(env["RUNNER_TEMP"])/"e1-home").is_dir(),
         "PINNED_LIBRARIES_NOT_STAGED")
    # Ensure all inputs and generated .mos were not modified after stage.
    for item in plan["candidates"]:
        need(sha_bytes((root / item["model_file"]).read_bytes()) ==
                item["model_sha256"]
             and sha_bytes((root / item["script"]).read_bytes()) ==
                item["script_sha256"]
             and (root / item["script"]).read_text().count("simulate(") == 1,
             "MODEL_OR_SCRIPT_CHANGED_AFTER_STAGE")
    results=[]
    with (root/"attempts.jsonl").open("x",encoding="utf-8") as log:
        for item in plan["candidates"]:
            need(len(results) < MAX_ATTEMPTS, "G2_ATTEMPT_LIMIT")
            arm, prefix=item["arm"],item["prefix"]
            (root/f"results/{arm}").mkdir(parents=True,exist_ok=True)
            (root/f"logs/{arm}").mkdir(parents=True,exist_ok=True)
            raw_attempt = {
                "schema":"arena.coffee-peak.dm-g2-attempt/1",
                "run_id":run_id,"head_sha":env["GITHUB_SHA"],
                "arm":arm,"candidate_id":item["id"],
                "model_sha256":item["model_sha256"],
                "script_sha256":item["script_sha256"],
                "attempt_number":len(results)+1,
                "reserved_before_omc":True, "max_attempts":MAX_ATTEMPTS,
                "no_retry":True
            }
            log.write(json.dumps(raw_attempt,sort_keys=True)+"\n")
            log.flush()
            (root/f"logs/{arm}/{prefix}.attempt.json").write_text(
                json.dumps(raw_attempt,indent=2)+"\n",encoding="utf-8")
            msl=str(Path(env["RUNNER_TEMP"])/"e1-libs")
            home=str(Path(env["RUNNER_TEMP"])/"e1-home")
            models=str(Path(__file__).resolve().parent/"_vendor/igc/src/modelica")
            argv=["docker","run","--rm","--network","none",
                  "--user",f"{os.getuid()}:{os.getgid()}",
                  "-v",f"{root}:/work",
                  "-v",f"{models}:/models:ro",
                  "-v",f"{home}:/omhome","-e","HOME=/omhome",
                  "-v",f"{msl}:/thirdparty:ro",
                  "-e","OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics",
                  "-w","/work",IMAGE,"omc",item["script"]]
            outcome={"arm":arm,"candidate_id":item["id"],
                     "attempt_reserved":True,"attempt_number":len(results)+1,
                     "model_sha256":item["model_sha256"],
                     "script_sha256":item["script_sha256"],
                     "check_model_completed":False,
                     "simulate_script_submitted":True,
                     "solver_simulation_authenticated":False,
                     "scientific_lock_created":False,
                     "provider_posts":0,"r2_access":False,"retry":False}
            status="UNDETERMINED"
            log_path=root/item["log"]
            try:
                with log_path.open("xb") as stream:
                    # No credentials are mounted, and Docker network is disabled.
                    clean={k:v for k,v in env.items()
                           if k not in ("GH_TOKEN","GITHUB_TOKEN","CLOUDFLARE_API_TOKEN")}
                    result=cli(argv,env=clean,cwd=root,stdout=stream,
                               stderr=subprocess.STDOUT,timeout=150,check=False)
                outcome["omc_exit_code"]=result.returncode
                evidence=log_path.read_text(encoding="utf-8",errors="replace")
                outcome["check_model_completed"] = (
                    f"Check of {item['modelica_class']} completed successfully" in evidence)
                csv_path=root/item["csv"]
                if result.returncode != 0:
                    status="OMC_EXIT_NONZERO"
                elif not outcome["check_model_completed"]:
                    status="G1_MODEL_CHECK_FAILED"
                elif not csv_path.is_file():
                    status="G2_CSV_NOT_PRODUCED"
                elif "LOG_SUCCESS" not in evidence:
                    status="G2_SOLVER_LOG_SUCCESS_MISSING"
                else:
                    try:
                        checked=verify_csv(csv_path,item)
                        outcome.update(checked)
                        outcome["csv_sha256"]=sha_bytes(csv_path.read_bytes())
                        outcome["solver_simulation_authenticated"]=True
                        status="G2_PHYSICAL_PASS_NOT_G3"
                    except (ValueError, TypeError, KeyError, ArenaError,
                            UnicodeError) as err:
                        status="G2_PHYSICAL_REJECTED"
                        outcome["physical_failure_code"]=str(err)[:160]
            except subprocess.TimeoutExpired as err:
                with log_path.open("ab") as stream:
                    if err.stdout:
                        stream.write(err.stdout)
                    stream.write(b"\nOMC_TIMEOUT_NO_RETRY\n")
                status="OMC_TIMEOUT_POSSIBLE_CONSUMPTION"
            except (OSError, subprocess.SubprocessError) as err:
                status="OMC_RUNTIME_FAILED_NO_RETRY"
            outcome["status"]=status
            outcome["solver_log_sha256"]=sha_bytes(log_path.read_bytes()) if log_path.is_file() else None
            write_json(root/f"results/{arm}/{prefix}.json",outcome,exclusive=True)
            results.append(outcome)
    report={
        "schema":"arena.coffee-peak.dm-g2-physical-batch/1",
        "status":"ONE_INITIAL_BATCH_EXECUTED_NO_SCIENTIFIC_LOCK",
        "run_id":run_id,"head_sha":env["GITHUB_SHA"],
        "source_native_run_id":SOURCE_RUN,
        "source_native_artifact_id":ARTIFACT_ID,
        "case_sha256":dm.CASE_SHA256,
        "attempts_reserved":len(results),
        "maximum_allowed_attempts":MAX_ATTEMPTS,
        "simulations_authenticated":sum(x["solver_simulation_authenticated"] for x in results),
        "results":results,
        "provider_posts":0, "r2_access":False,"truth_access":False,
        "scientific_lock_created":False,
        "ledger_atms_feedback_consumed":False,
        "no_retries":True,
        "warning":"All outputs are conditional on public assumptions; no hidden scoring or intervention proof."
    }
    write_json(root/"result.json",report,exclusive=True)
    return report


def main(argv=None):
    ap=argparse.ArgumentParser(description="One budgeted public-only coffee D/M Modelica batch")
    ap.add_argument("action",choices=("stage","run"))
    ap.add_argument("--root",type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        output=stage(args.root) if args.action=="stage" else run_batch(args.root)
        print(json.dumps({"status":output["status"],"run_id":os.environ.get("GITHUB_RUN_ID"),
                          "omc_reserved":output.get("attempts_reserved",0),
                          "provider_posts":0,"truth_access":False},sort_keys=True))
        return 0
    except (ArenaError,ValueError,TypeError,KeyError,OSError,ImportError,
            subprocess.SubprocessError) as err:
        print(json.dumps({"status":"STOPPED_NO_RETRY","reason":str(err)
                          if isinstance(err,ArenaError) else "INTERNAL_ERROR"}),
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
