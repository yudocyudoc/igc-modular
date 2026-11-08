"""CT-03: reuse TWO authentic CT-02 initial native trajectories without new OMC.

A source archive is provided by the GitHub Actions artifact downloader. This
module checks its original content, models, manifests, solver logs, and runtime
identity against CT-03's freshly generated fixed D/M native originals, but
does NOT sign evidence, run a solver, open a private world or generate feedback.
A GitHub Actions runner must separately verify the selected artifact ID/run
came from GitHub; reading a copied local directory cannot independently
authenticate its origin.

The four construction cuts are NOT used to select these initial candidates.
Only deterministic output of IDENTICAL model+input+runtime may be reused.
Feedback, revision decisions and the actual CT-03 world are NEVER reused.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_d_v01 import verify_csv
from scripts.arena_cafe.ct03_d_prepare import prepare as prepare_d, PROFILE
from scripts.arena_cafe.ct03_m_prepare import prepare as prepare_m
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT
from scripts.arena_cafe.ct03_m_construction_diagnostic import _sample, sha_bytes
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA = "igc-ct03-reuse-two-ct02-initial-consequences/1.0"
RUN_ID = "42409210062"
RUN_SHA = "6534ec6bbbe0c48265d1e4eb0d1d243c7fe55b4d"
ARTIFACT_ID = 13588621967
ARTIFACT_SHA256 = "sha256:7c77650e2d49a8e4dea64eeb0053e80da5b9137a3607a3b26edbf7c7b358ccac"
IMAGE = "openmodelica/openmodelica:v1.26.5-minimal"
IMAGE_DIGEST = "openmodelica/openmodelica@sha256:8993c8273224aeacbc018f351c00d60879c5aec386c77a58019318c44c938c9b"
MSL_REF = "6626538a236a34a390655b55d5e8c906bfe31772"
SD_REF = "b986a2ea354ab550d627a392f857ad7c9997d961"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _points(path, column):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames is not None and reader.fieldnames.count("time")==1
                and reader.fieldnames.count(column)==1,
                "CT03_REUSE_EXACT_NATIVE_OUTPUT_COLUMN_REQUIRED")
        result = {}
        first, last, count = None, None, 0
        for row in reader:
            t, y = float(row["time"]), float(row[column])
            require(math.isfinite(t) and math.isfinite(y) and
                    0 <= t <= 8+1e-8 and -1e-8 <= y <= 3.4+1e-5 and
                    (last is None or t >= last - 1e-9),
                    "CT03_REUSE_INVALID_NATIVE_TRACE")
            if first is None:
                first = t
            last = t
            count += 1
            for cut in (6, 8):
                if abs(t-cut)<1e-8:
                    require(cut not in result or abs(result[cut]-y)<1e-7,
                            "CT03_REUSE_CONFLICTING_PREDICTION_AT_EVENT")
                    result[cut]=y
        require(count >= 65 and first is not None and abs(first)<1e-8 and
                abs(last-8)<1e-8 and set(result)=={6,8} and
                result[8]+1e-7 >= result[6],
                "CT03_REUSE_FULL_HORIZON_OR_PREDICTIONS_MISSING")
        return result, count


def _runtime(path):
    content = path.read_text(encoding="utf-8")
    pairs = [line.split("=",1) for line in content.strip().splitlines()]
    require(len(pairs)==5 and all(len(p)==2 for p in pairs) and
            len({p[0] for p in pairs})==5,
            "CT03_REUSE_RUNTIME_IDENTITY_MALFORMED")
    found=dict(pairs)
    require(found=={
        "github_sha":RUN_SHA,"github_run_id":RUN_ID,
        "msl_ref":MSL_REF,"systemdynamics_ref":SD_REF,
        "image_digest":IMAGE_DIGEST,
    },"CT03_REUSE_NUMERICAL_RUNTIME_DRIFT")
    return found


def _simulation(script_bytes, arm, model_name, prefix):
    script=script_bytes.decode("utf-8")
    require(script.count("simulate(")==1 and
            script.count("checkModel(")==1 and
            "getVersion();" in script and
            "checkModel("+model_name+");" in script and
            "simulate("+model_name+",startTime=0,stopTime=8,"
            'numberOfIntervals=64,method="euler",outputFormat="csv",'
            'fileNamePrefix="artifacts/ct02-exact-two/'+prefix+'");' in script,
            "CT03_REUSE_NOT_SAME_NUMERICAL_EXPERIMENT")
    require(('/repo/artifacts/ct02-exact-two/D/'+model_name+'.mo' in script)
            if arm=="D" else
            ('/repo/artifacts/ct02-exact-two/M/native.mo' in script),
            "CT03_REUSE_MODEL_SOURCE_PATH_MISMATCH")


def verify_native_dir(source: Path, fresh_d: dict, fresh_m: dict, *, fresh_root: Path):
    """Run with source dir downloaded from original GitHub run, not a fixture."""
    source, fresh_root = Path(source), Path(fresh_root)
    require(source.resolve()!=fresh_root.resolve() and
            source.is_dir() and fresh_root.is_dir(),
            "CT03_REUSE_SEPARATE_ORIGINAL_AND_NEW_PREPARATION_REQUIRED")
    batch=_read(source/"batch.json")
    conform=_read(source/"conformity.json")
    require(batch.get("schema")=="igc-ct02-exact-two-technical-simulations/1.0"
            and batch.get("planned_omc_runs")==2
            and batch.get("actual_omc_runs")==0
            and batch.get("method")=="euler"
            and batch.get("start_h")==0 and batch.get("stop_h")==8
            and batch.get("intervals")==64 and batch.get("dt_h")==0.125
            and batch.get("image")==IMAGE
            and batch.get("provider_calls")==0
            and batch.get("reserved_truth_opened") is False
            and [x["arm"] for x in batch["items"]]==["D","M"],
            "CT03_REUSE_ORIGINAL_BATCH_INCOMPATIBLE")
    require(conform.get("status")==
            "TWO_TECHNICAL_CSVS_CHECKED_NOT_CT03_SCIENTIFIC_ACCEPTANCE"
            and conform.get("git_sha")==RUN_SHA
            and conform.get("run_id")==RUN_ID
            and conform.get("attempted_omc")==2
            and conform.get("successful_omc_csvs")==2
            and conform.get("provider_posts")==0
            and conform.get("source_plan_sha256")==digest(batch)
            and len(conform.get("outputs",[]))==2,
            "CT03_REUSE_ORIGINAL_RUN_OR_BUDGET_NOT_PROVEN")
    attempts=(source/"attempts.log").read_text(encoding="utf-8").splitlines()
    require(attempts==[
        "D attempted; GitHub run "+RUN_ID+"; code "+RUN_SHA,
        "M attempted; GitHub run "+RUN_ID+"; code "+RUN_SHA],
        "CT03_REUSE_ORIGINAL_ATTEMPTS_NOT_EXACTLY_TWO")
    _runtime(source/"runtime-identity.txt")
    require(_read(source/"D/manifest.json")==fresh_d and
            _read(source/"M/manifest.json")==fresh_m and
            fresh_d["source_definition_sha256"]==
                fresh_m["source_definition_sha256"]==digest(PUBLIC_INPUT),
            "CT03_REUSE_CURRENT_ORIGINAL_PARENT_CHANGED")
    require(sha_bytes((source/"M/native.mo").read_bytes())==
            sha_bytes((fresh_root/"M/native.mo").read_bytes())==
            fresh_m["native_modelica_sha256"],
            "CT03_REUSE_ORIGINAL_M_SOURCE_CHANGED")
    entries=[]
    for i,arm in enumerate(("D","M")):
        row=batch["items"][i]
        rec=conform["outputs"][i]
        candidate=(fresh_d if arm=="D" else fresh_m)["candidates"][0]
        cid=candidate["id"] if arm=="D" else candidate["canonical_sha256"]
        require(row["candidate_id"]==rec["candidate_id"]==cid and
                row["csv_file"]==(arm.lower()+"00_res.csv") and
                row["solver_log_file"]==arm+"-omc.log" and
                row["command_file"]==arm+"-single.mos" and
                row["native_sha256"]==rec["native_sha256"] and
                row["script_sha256"]==rec["script_sha256"] and
                row["output_column"]==rec["output_column"] and
                rec["technical_status"]=="CSV_CHECKS_PASS_NOT_SCIENTIFIC_G2",
                "CT03_REUSE_FIRST_ORIGINAL_CANDIDATE_MISMATCH")
        expected_col="delivered" if arm=="D" else "deliveredTotal"
        require(row["output_column"]==expected_col,
                "CT03_REUSE_WRONG_OUTPUT_ROLE")
        if arm=="D":
            expected=source/"D"/(candidate["name"]+".mo")
            present=fresh_root/"D"/(candidate["name"]+".mo")
            require(sha_bytes(expected.read_bytes())==
                    sha_bytes(present.read_bytes())==
                    candidate["native_modelica_sha256"]==
                    row["native_sha256"],
                    "CT03_REUSE_ORIGINAL_D_MODEL_CHANGED")
            model=candidate["name"]
        else:
            require(row["parent_ast_sha256"]==candidate["full_ast_sha256"],
                    "CT03_REUSE_ORIGINAL_M_PARENT_CHANGED")
            model="ArenaCT03M."+candidate["class_name"]
        script_bytes=(source/row["command_file"]).read_bytes()
        require(sha_bytes(script_bytes)==row["script_sha256"],
                "CT03_REUSE_ORIGINAL_COMMAND_CHANGED")
        _simulation(script_bytes,arm,model,arm.lower()+"00")
        logfile=(source/row["solver_log_file"]).read_bytes()
        csv_path=source/row["csv_file"]
        csv_bytes=csv_path.read_bytes()
        require(sha_bytes(logfile)==rec["solver_log_sha256"] and
                sha_bytes(csv_bytes)==rec["csv_sha256"] and
                b"OpenModelica 1.26.5" in logfile and
                b"LOG_SUCCESS" in logfile and
                row["csv_file"].encode() in logfile,
                "CT03_REUSE_NATIVE_LOG_OR_TRACE_MISMATCH")
        pts, count=_points(csv_path,expected_col)
        require(count==rec["csv_rows"],
                "CT03_REUSE_NATIVE_CSV_ROW_COUNT_CHANGED")
        if arm=="D":
            checked=verify_csv(csv_path,len(candidate["structure"]["stocks"]),PROFILE)
            require(checked["status"]=="G2_MASS_BALANCE_PASS_NOT_G3",
                    "CT03_REUSE_D_MASS_BALANCE_FAILED")
        else:
            cuts,n=_sample(csv_bytes,"deliveredTotal")
            require(n==count and set(cuts)=={0.,1.,2.,4.},
                    "CT03_REUSE_M_ORIGINAL_CONSTRUCTION_CUTS_MISSING")
        entries.append({
            "arm":arm,
            "candidate_id":cid,
            "original_full_ast_sha256": (
                candidate["full_ast_sha256"] if arm=="M" else None),
            "model_sha256":row["native_sha256"],
            "script_sha256":row["script_sha256"],
            "trace_sha256":rec["csv_sha256"],
            "solver_log_sha256":rec["solver_log_sha256"],
            "receipt_sha256":digest(rec),
            "forecast":[{"time":t,"delivered":pts[t]} for t in (6,8)],
            "status":"REUSED_ORIGINAL_NATIVE_INITIAL_NOT_CT03_SCORE",
        })
    return {
        "schema":SCHEMA,
        "status":"TWO_ORIGINAL_INITIAL_CONSEQUENCES_ELIGIBLE_FOR_REUSE",
        "source_github_run_id":RUN_ID,
        "source_github_artifact_id":ARTIFACT_ID,
        "source_artifact_sha256":ARTIFACT_SHA256,
        "source_code_sha":RUN_SHA,
        "runtime_image_digest":IMAGE_DIGEST,
        "input_source_sha256":digest(PUBLIC_INPUT),
        "items":entries,
        "new_omc":0,"new_provider_posts":0,"world_selected":False,
        "construction_observations_read":False,
        "own_feedback_or_decision_reused":False,
        "reserved_world_truth_read":False,
        "custody_limit":"LOCAL_CONTENT_CHECKS_REQUIRE_GITHUB_ACTIONS_ARTIFACT_ORIGIN_CHECK",
        "scientific_limit":"NOT_ALL_THIRTEEN_CT03_OR_EXTERNAL_VALIDATION",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original-artifact-dir",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    require(not args.out.exists(),"CT03_REUSE_REFUSE_OVERWRITE")
    # Fresh source from frozen original generators and registry, not edited copies.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        root=Path(temp)
        d=prepare_d(root/"D")
        m=prepare_m(root/"M")
        result=verify_native_dir(args.original_artifact_dir,d,m,fresh_root=root)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(result)+b"\n")
    print(json.dumps({"status":result["status"],
                      "eligible_reuses":len(result["items"]),
                      "new_omc":0,"provider_posts":0}))


if __name__=="__main__":
    main()
