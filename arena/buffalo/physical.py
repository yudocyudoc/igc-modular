"""BF-05: exactly one pinned OpenModelica attempt on the BF-04 candidate.

This never reads CT03's held-out truth or R2. A successful compilation is not
upstream Buffalo simulator parity; public fit is reported, not optimized.
"""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

from arena.common import ArenaError, read_json, write_json
from arena.runtime import IMAGE
from .gates import validate_candidate, CandidateBlocked
from arena._vendor.igc.scripts.arena_b_native_to_modelica import ident

DT=0.125
STEPS=64
MASS=3.4
CONSERVATION_ABS_TOL=1e-9


def prepare(root):
    root=Path(root).resolve()
    batch=root/"artifacts/buffalo-adjust-v1"
    source=batch/"bf04/native-engine-result.json"
    if not source.is_file() or (batch/"bf05").exists():
        raise ArenaError("BF05 requires precisely one approved BF04 source and no previous OMC.")
    g1=read_json(batch/"bf04-g1.json")
    if g1.get("status")!="ADMISSIBLE_IN_PINNED_MODELICA_SUBSET_NOT_YET_SIMULATED":
        raise ArenaError("BF05 source G1 not admissible.")
    native=read_json(source)
    result=validate_candidate(native)  # fresh, never trust copied G1.
    if result["observation_operator"]!=g1["observation_operator"] or result["public_input_flow_name"]!=g1["public_input_flow_name"]:
        raise ArenaError("BF05 candidate observation or stimulus identity changed.")
    dest=batch/"bf05"
    dest.mkdir(parents=True,exist_ok=False)
    name=result["translated_model_name"]
    code=result["translated_modelica_text"]
    mo=dest/(name+".mo")
    mo.write_text(code,encoding="utf-8",newline="\n")
    mos=dest/"physical.mos"
    mos_text="\n".join([
        "getVersion();",
        f'loadFile("/repo/artifacts/buffalo-adjust-v1/bf05/{name}.mo");',
        f"checkModel({name});",
        "print(getErrorString());",
        f'simulate({name},startTime=0,stopTime=8,numberOfIntervals=64,'
        f'method="euler",outputFormat="csv",'
        f'fileNamePrefix="artifacts/buffalo-adjust-v1/bf05/physical");',
        "print(getErrorString());",""])
    mos.write_text(mos_text,encoding="utf-8",newline="\n")
    report={"schema":"buffalo-adjust-v1/bf05-plan/1",
            "candidate_source":"bf04/native-engine-result.json",
            "candidate_sha256":"sha256:"+hashlib.sha256(source.read_bytes()).hexdigest(),
            "modelica_file":mo.name,
            "modelica_sha256":"sha256:"+hashlib.sha256(code.encode()).hexdigest(),
            "mos_sha256":"sha256:"+hashlib.sha256(mos_text.encode()).hexdigest(),
            "model_name":name,"solver":"OpenModelica/pinned Euler",
            "solver_image":IMAGE,"start_time":0,"stop_time":8,
            "dt":DT,"intervals":STEPS,"max_omc":1,
            "conservation_abs_tolerance_items":CONSERVATION_ABS_TOL,
            "observation_operator":result["observation_operator"],
            "external_input_flow":result["public_input_flow_name"],
            "xmile_parity_not_proven":True,
            "heldout_read":False,"d_m_used":False}
    write_json(dest/"plan.json",report,exclusive=True)
    return report


def evaluate_csv(root,plan):
    path=Path(root)/"artifacts/buffalo-adjust-v1/bf05/physical_res.csv"
    if not path.is_file():
        raise ArenaError("BF05_CSV_ABSENT_OR_WRONG_LOCATION")
    with path.open(newline="",encoding="utf-8") as stream:
        reader=csv.DictReader(stream)
        rows=list(reader)
        columns=reader.fieldnames or []
    if len(rows)!=STEPS+1 or "time" not in columns:
        raise ArenaError("BF05_CSV_GRID_MISSING")
    native=read_json(Path(root)/"artifacts/buffalo-adjust-v1/bf04/native-engine-result.json")
    stocks=[ident(v["name"]) for v in native["model"]["variables"] if v["type"]=="stock"]
    cumulative=plan["observation_operator"]["modelica_csv_column"]
    inflow=ident(plan["external_input_flow"])
    missing=[name for name in [*stocks,cumulative,inflow] if name not in columns]
    if missing:
        raise ArenaError("BF05_CSV_REQUIRED_VARIABLES_MISSING:"+",".join(missing))
    dataset=[]
    for i,row in enumerate(rows):
        try:
            t=float(row["time"])
            values={name:float(row[name]) for name in set([*stocks,cumulative,inflow])}
        except (ValueError,TypeError,KeyError) as exc:
            raise ArenaError("BF05_NONNUMERIC_CSV") from exc
        if abs(t-i*DT)>1e-9 or not all(map(math.isfinite,values.values())):
            raise ArenaError("BF05_TIME_GRID_OR_FINITE_VALUES_INVALID")
        dataset.append({"time":t,**values})
    source_area=0.
    residuals=[]
    material_initial=sum(dataset[0][s] for s in stocks)
    if abs(material_initial)>1e-9 or abs(dataset[0][cumulative])>1e-9:
        raise ArenaError("BF05_NONZERO_MATERIAL_INITIAL")
    for i,row in enumerate(dataset):
        if i:
            source_area+=DT*dataset[i-1][inflow]
        residuals.append(sum(row[s] for s in stocks)-material_initial-source_area)
    max_res=max(abs(x) for x in residuals)
    nonnegative=all(row[s]>=-CONSERVATION_ABS_TOL for row in dataset for s in stocks)
    monotone=all(b[cumulative]>=a[cumulative]-CONSERVATION_ABS_TOL
                 for a,b in zip(dataset,dataset[1:]))
    total_mass_ok=abs(source_area-MASS)<=CONSERVATION_ABS_TOL
    conservation_ok=max_res<=CONSERVATION_ABS_TOL
    visible=read_json(Path(root)/"artifacts/buffalo-adjust-v1/bf04-visible.json")
    times={round(row["time"],9):row for row in dataset}
    public=[]
    for obs in visible["construction"]["observations"]:
        t=float(obs["time"])
        if round(t,9) not in times:
            raise ArenaError("BF05_PUBLIC_OBSERVATION_TIME_MISSING")
        prediction=times[round(t,9)][cumulative]
        public.append({"time":t,"observed_delivered":float(obs["delivered"]),
                       "model_delivered":prediction,
                       "model_minus_observed":prediction-float(obs["delivered"])})
    rmse=math.sqrt(sum(x["model_minus_observed"]**2 for x in public)/len(public))
    outcome={"schema":"buffalo-adjust-v1/bf05-physical/1",
             "status":"G2_PHYSICAL_VALID" if all((nonnegative,monotone,
                 total_mass_ok,conservation_ok)) else "G2_PHYSICAL_CONSTRAINT_FAILED",
             "omc_attempts":1,
             "source_mass_integral_euler":source_area,
             "expected_continuous_mass":MASS,
             "max_material_conservation_residual":max_res,
             "nonnegative_material_stocks":nonnegative,
             "cumulative_delivery_monotonic":monotone,
             "total_public_input_mass_correct":total_mass_ok,
             "material_conservation_within_1e9":conservation_ok,
             "public_observations":public,
             "public_rmse":rmse,"rmse_denominator":len(public),
             "heldout_truth_accessed":False,
             "prediction_t6":times[6.0][cumulative],
             "prediction_t8":times[8.0][cumulative],
             "predictions_not_reserved_truth":True,
             "no_fit_threshold_pretended":True,
             "original_buffalo_simulator_parity_proven":False}
    return outcome


def simulate(root):
    root=Path(root).resolve()
    plan=prepare(root)
    dest=root/"artifacts/buffalo-adjust-v1/bf05"
    # Write BEFORE Docker/omc: failure, missing CSV and timeouts still cost 1.
    write_json(dest/"attempt.json",{"schema":"buffalo-adjust-v1/omc-attempt/1",
       "attempt_reserved_before_docker":True,"max_omc":1,
       "github_run_id":os.environ.get("GITHUB_RUN_ID"),
       "git_sha":os.environ.get("GITHUB_SHA"),
       "retry":False},exclusive=True)
    if os.environ.get("GITHUB_RUN_ATTEMPT")!="1":
        raise ArenaError("BF05_RERUN_NOT_AUTHORIZED")
    base=Path(os.environ["RUNNER_TEMP"])
    if not (base/"e1-libs/msl").is_dir() or not (base/"e1-libs/systemdynamics").is_dir():
        raise ArenaError("BF05_PINNED_STANDARD_LIBRARIES_MISSING")
    args=["docker","run","--rm","--network","none","--user",
          str(os.getuid())+":"+str(os.getgid()),
          "-v",str(root)+":/repo","-w","/repo",
          "-v",str(base/"e1-home")+":/omhome","-e","HOME=/omhome",
          "-v",str(base/"e1-libs")+":/thirdparty:ro",
          "-e","OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics",
          IMAGE,"omc","artifacts/buffalo-adjust-v1/bf05/physical.mos"]
    log=dest/"omc.log"
    with log.open("wb") as stream:
        process=subprocess.run(args,cwd=root,stdout=stream,stderr=subprocess.STDOUT,
                               timeout=900,check=False)
    write_json(dest/"omc-exit.json",{"exit_code":process.returncode,
           "attempted":True,"omc_invocations":1,"retry":False},exclusive=True)
    if process.returncode:
        outcome={"schema":"buffalo-adjust-v1/bf05-physical/1",
                 "status":"G2_FAILED_OMC", "omc_attempts":1,
                 "omc_exit":process.returncode}
    else:
        try:
            outcome=evaluate_csv(root,plan)
        except ArenaError as error:
            outcome={"schema":"buffalo-adjust-v1/bf05-physical/1",
                    "status":"G2_FAILED_CSV_OR_CONSTRAINT_VALIDATION",
                    "omc_attempts":1, "reason":str(error)}
    write_json(dest/"physical-result.json",outcome,exclusive=True)
    return outcome
