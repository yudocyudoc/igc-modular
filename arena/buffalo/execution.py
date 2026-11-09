"""Manual BF-03/04/05 orchestrator. No CT03 replay, custodian, D/M or DES.

A single explicit workflow_dispatch authorizes up to two sequential original
Engine.generate calls and one pinned OMC attempt. The historical CT03 and
buffalo-only runs never count as part of this new, fixed batch ID.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from arena.common import ArenaError, read_json, write_json
from arena.connections import Secret, public_config
from arena.github import GitHub
from arena.runtime import module, verify
from arena.cloud import public_input
from .adjust import offline_bundle, BATCH_ID, SOURCE
from .gates import validate_candidate, CandidateBlocked
from .physical import simulate as simulate_physical

REPO="yudocyudoc/igc-modular"
WORKFLOW=".github/workflows/buffalo-only.yml"
LIVE_JOB="Buffalo-adjust v1 BF03-BF04-BF05 (2 POST, 1 OMC)"
EXPECTED_PUBLISHED_PARENT_RUN=42536740649
PER_BATCH_POST_CAP=2
PER_BATCH_OMC_CAP=1
MAX_HISTORY=100
PHASES=("bf03","bf04")
PAID_GENERATION_STEP="BF03 then BF04 - original Engine.generate max two POST total no retries"
PAID_OMC_STEP="BF05 - at most one pinned isolated OpenModelica simulation"
KNOWN_JOB_NAMES={
    LIVE_JOB,
    "Original Buffalo - archived public CT03 input - 0 OMC",
    "BF00-02 - archived real evidence, no provider or OMC",
}


def _previous_live_job_proven_no_consumption(job):
    """Only positively skipped paid steps allow a new FIRST manual attempt.

    Pre-provider download, dependencies or environment failure is recoverable
    if Actions shows both spending-capable steps never started. A timeout,
    missing step record, cancellation during a paid step, or unknown status
    is NOT proof of zero usage.
    """
    if job.get("name")!=LIVE_JOB or job.get("status")!="completed":
        return False
    if job.get("conclusion")=="skipped":
        # Job-level skip: no checkout/credentials/Node/OMC were started.
        return True
    if job.get("conclusion") not in ("failure","cancelled"):
        return False
    steps=job.get("steps")
    if not isinstance(steps,list):
        return False
    paid={}
    for name in (PAID_GENERATION_STEP,PAID_OMC_STEP):
        found=[step for step in steps if step.get("name")==name]
        if len(found)!=1:
            return False
        paid[name]=found[0]
    for step in paid.values():
        # "skipped" is a real Actions conclusion, not an inference from a
        # failed job. A paid step with an observed start is consumed/unknown.
        if (step.get("status")!="completed"
            or step.get("conclusion")!="skipped"
            or step.get("started_at") not in (None,"")
            or type(step.get("number")) is not int):
            return False
    first_paid_number=min(step["number"] for step in paid.values())
    # The failure must be demonstrably in a PREPAID preparation step.
    prior=[step for step in steps if
           type(step.get("number")) is int and
           step["number"]<first_paid_number]
    return any(step.get("status")=="completed"
               and step.get("conclusion") in ("failure","cancelled")
               for step in prior)




def identity():
    if (os.environ.get("GITHUB_EVENT_NAME")!="workflow_dispatch"
        or os.environ.get("GITHUB_REF")!="refs/heads/main"
        or os.environ.get("GITHUB_REPOSITORY")!=REPO
        or os.environ.get("GITHUB_RUN_ATTEMPT")!="1"
        or os.environ.get("BUFFALO_ADJUST_AUTH")!="yes"
        or os.environ.get("BUFFALO_ADJUST_MODE")!="adjust-live"):
        raise ArenaError("BF_BATCH_MANUAL_ONE_FIRST_ATTEMPT_MAIN_REQUIRED")
    sha=os.environ.get("GITHUB_SHA","")
    run=os.environ.get("GITHUB_RUN_ID","")
    if not re.fullmatch(r"[a-f0-9]{40}",sha) or not re.fullmatch(r"[1-9][0-9]*",run):
        raise ArenaError("BF_BATCH_ACTUAL_RUN_AND_SHA_REQUIRED")
    return sha,int(run)


def reconcile_history(api, current_id):
    """Only affirmative proof of *no paid step ever starting* permits first POST.

    Pre-provider preparation failures can be retried by a new manual dispatch
    only when the original BF03/BF04 and OMC steps are provably unstarted.
    Any spending-capable step started/uncertain fails closed. No automatic retries.
    """
    listing=api.repo("GET",
      "/actions/workflows/buffalo-only.yml/runs?event=workflow_dispatch&per_page=100")
    rows=listing.get("workflow_runs")
    count=listing.get("total_count")
    if (type(count) is not int or count>MAX_HISTORY or count<0
        or not isinstance(rows,list) or len(rows)!=count):
        raise ArenaError("BF_CANNOT_RECONCILE_ALL_PRIOR_MANUAL_DISPATCHES")
    verified=[]
    for row in rows:
        rid=row.get("id")
        if type(rid) is not int:
            raise ArenaError("BF_INVALID_HISTORY_RUN_ID")
        if rid==current_id:
            continue
        run=api.run(rid)
        if (run.get("id")!=rid or run.get("status")!="completed"
            or run.get("run_attempt")!=1 or run.get("event")!="workflow_dispatch"
            or run.get("path")!=WORKFLOW):
            raise ArenaError("BF_PRIOR_DISPATCH_UNKNOWN_OR_RERUN_BLOCKED")
        jobs=api.repo("GET",f"/actions/runs/{rid}/jobs?per_page=100")
        items=jobs.get("jobs")
        if (type(jobs.get("total_count")) is not int
            or jobs.get("total_count")!=len(items or [])
            or not isinstance(items,list)):
            raise ArenaError("BF_PRIOR_DISPATCH_JOBS_INCOMPLETE")
        live_jobs=[job for job in items if job.get("name")==LIVE_JOB]
        if len(live_jobs)>1:
            raise ArenaError("BF_PRIOR_DISPATCH_DUPLICATE_LIVE_JOBS")
        for job in items:
            if job.get("name") not in KNOWN_JOB_NAMES:
                raise ArenaError("BF_PRIOR_DISPATCH_UNKNOWN_JOB_BLOCKED")
        if live_jobs and not _previous_live_job_proven_no_consumption(live_jobs[0]):
            raise ArenaError("BF03_TO_BF05_BATCH_ALREADY_STARTED_OR_UNCERTAIN")
        verified.append(rid)
    return verified


def admit(root, evidence, *, api=None):
    sha,run=identity()
    verify()
    root=Path(root).resolve()
    evidence=Path(evidence).resolve()
    if api is None:
        token=os.environ.get("GH_TOKEN")
        if not token:
            raise ArenaError("GITHUB_ACTIONS_READ_TOKEN_REQUIRED")
        api=GitHub(REPO,Secret(token,"GITHUB_TOKEN"))
    history=reconcile_history(api,run)
    if (root/"artifacts"/BATCH_ID).exists():
        raise ArenaError("BF_BATCH_ALREADY_ADMITTED")
    offline=offline_bundle(root,evidence)  # 6 pinned original hashes, only public inputs
    if (offline["parent_diagnostic_run"]!=EXPECTED_PUBLISHED_PARENT_RUN
        or offline["actual_consumption"]!={"provider_posts":0,"new_omc":0,"new_worlds":0}):
        raise ArenaError("BF_OFFLINE_PUBLIC_SOURCE_PROVENANCE_FAILED")
    receipt={"schema":"buffalo-adjust-v1/manual-admission/1",
        "batch_id":BATCH_ID,"run_id":run,"sha":sha,
        "event":"workflow_dispatch","mode":"adjust-live","authorized":True,
        "source_ct03_run":offline["source_ct03_run"],
        "parent_run":offline["parent_diagnostic_run"],
        "prior_manual_runs_outside_this_batch":history,
        "bf03_provider_posts_max":1,"bf04_provider_posts_max":1,
        "bf05_omc_attempts_max":1,"new_worlds_max":0,
        "D_M_DES_custodian_used":False,"separate_from_ct03_lock_and_score":True,
        "profile_sha256":read_json(root/"artifacts"/BATCH_ID/"bf02-profile.json")["utf8_sha256"]}
    write_json(root/"artifacts"/BATCH_ID/"live-admission.json",receipt,exclusive=True)
    return {"status":"LIVE_ADMITTED_NO_PROVIDER_CALLED",
            "provider_posts":0,"omc_attempts":0,"history_checked":len(history)}


def generate(root, evidence, *, runner=None):
    """BF03 -> G1 -> BF04 -> G1. Any failed phase leaves remaining budget unused."""
    sha,run=identity()
    root=Path(root).resolve()
    evidence=Path(evidence).resolve()
    batch=root/"artifacts"/BATCH_ID
    admission=read_json(batch/"live-admission.json")
    if admission["run_id"]!=run or admission["sha"]!=sha:
        raise ArenaError("BF_BATCH_ADMISSION_MISMATCH")
    if (batch/"bf03-attempt.json").exists():
        raise ArenaError("BF_BATCH_RETRY_OR_SECOND_GENERATE_COMMAND_BLOCKED")
    if any(os.environ.get(k) for k in ("CT03_R2_ACCESS_KEY_ID",
          "CT03_R2_SECRET_ACCESS_KEY","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY")):
        raise ArenaError("BF_BATCH_CUSTODY_CREDENTIALS_FORBIDDEN")
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        raise ArenaError("BF_PROVIDER_SECRET_NOT_AVAILABLE")
    # The actual generated model must come from Engine.generate and only
    # after the original parent has been read from verified historical bytes.
    parent=evidence/SOURCE["parent_native"][0]
    parent_doc=read_json(parent)
    profile=batch/"bf02-profile.json"
    feedback=batch/"bf02-own-feedback.json"
    if read_json(feedback)["parent_native_sha256"]!=admission_parent_hash(parent_doc):
        raise ArenaError("BF03_PARENT_HASH_CHANGED")
    construction=public_input(root)
    for phase in PHASES:
        if phase=="bf04" and not (batch/"bf03-g1.json").is_file():
            raise ArenaError("BF04_REQUIRES_BF03_APPROVED")
        visible=batch/(phase+"-visible.json")
        module(root,"ct03_b_visible","--construction",
            "artifacts/ct03-public/construction.json",
            "--world",construction["world_public_id"],
            "--round","revision" if phase=="bf03" else "initial",
            "--out",visible)
        if not visible.is_file():
            raise ArenaError("BF_PUBLIC_VISIBLE_INPUT_FAILED")
        output=batch/phase
        if output.exists() or (batch/(phase+"-attempt.json")).exists():
            raise ArenaError("BF_PAID_ATTEMPT_ALREADY_STARTED")
        write_json(batch/(phase+"-attempt.json"),{
            "schema":"buffalo-adjust-v1/paid-attempt/1",
            "phase":phase,"run_id":run,"sha":sha,"max_provider_posts":1,
            "state":"RESERVED_BEFORE_ORIGINAL_ENGINE","no_retry":True},exclusive=True)
        env={**os.environ,"SDAI_ROOT":str(root/"upstream/sd-ai"),
            "BUFFALO_SCRIPTS_ROOT":str(root/"scripts"),
            "BUFFALO_ADJUST_OUTPUT":str(output),
            "BUFFALO_ADJUST_ROUND":phase,"BUFFALO_VISIBLE_INPUT":str(visible),
            "BUFFALO_PROFILE_INPUT":str(profile),
            "BUFFALO_OWN_FEEDBACK":str(feedback) if phase=="bf03" else "",
            "BUFFALO_PARENT_NATIVE":str(parent) if phase=="bf03" else "",
            "CLOUDFLARE_ACCOUNT_ID":os.environ.get("CLOUDFLARE_ACCOUNT_ID")
              or public_config()["cloudflare"]["account_id"]}
        argv=["node",str(Path(__file__).with_name("original_runner.mjs").resolve())]
        with (batch/(phase+"-runner.log")).open("wb") as log:
            proc=(runner or subprocess.run)(argv,cwd=root,env=env,
                stdout=log,stderr=subprocess.STDOUT,check=False,timeout=600)
        write_json(batch/(phase+"-process.json"),{
            "exit_code":proc.returncode,"node_invocations":1,
            "max_provider_posts":1,"omc_attempts":0,"retry":False},exclusive=True)
        receipt_file=output/"receipt.json"
        receipt=read_json(receipt_file) if receipt_file.is_file() else None
        if (receipt is None or receipt.get("provider_calls")!=1
            or receipt.get("proxy_requests")!=1
            or not receipt.get("raw_provider_saved")
            or not (output/"provider-raw.json").is_file()
            or receipt.get("generation_profile_sha256")!=admission["profile_sha256"]
            or receipt.get("round_kind")!=phase
            or receipt.get("source_snapshot_hash")!=construction["source_snapshot_hash"]
            or receipt.get("world_public_id")!=construction["world_public_id"]
            or proc.returncode!=0 or receipt.get("runner_error")
            or not receipt.get("model_returned")):
            raise ArenaError("BF_"+phase.upper()+"_FAILED_OR_CONSUMPTION_UNCERTAIN_STOP")
        native=read_json(output/"native-engine-result.json")
        try:
            gate=validate_candidate(native)
        except CandidateBlocked as exc:
            write_json(batch/(phase+"g1-block.json"),{
                "phase":phase,"status":"G1_BLOCKED","reason":str(exc),
                "no_provider_retry":True},exclusive=True)
            raise ArenaError(phase.upper()+"_G1_BLOCKED_STOP:"+str(exc)) from exc
        # Separate the full translated code from the G1 audit. Never replace native.
        modelica=gate.pop("translated_modelica_text")
        gate["translated_modelica_sha256"]="sha256:"+hashlib.sha256(modelica.encode()).hexdigest()
        write_json(batch/(phase+"-g1.json"),gate,exclusive=True)
    return {"status":"BF03_AND_BF04_G1_ADMITTED","provider_posts_reported":2,
            "new_omc":0,"bf05_ready":True}


def admission_parent_hash(value):
    from .capabilities import native_hash
    return native_hash(value)


def physical(root):
    identity()
    root=Path(root).resolve()
    batch=root/"artifacts"/BATCH_ID
    if not (batch/"bf03-g1.json").is_file() or not (batch/"bf04-g1.json").is_file():
        raise ArenaError("BF05_BOTH_G1_ADMISSIONS_REQUIRED")
    return simulate_physical(root)


def finalize(root):
    """Never call the provider/solver. Preserve observed vs unknown consumption."""
    batch=Path(root).resolve()/"artifacts"/BATCH_ID
    if not batch.is_dir():
        return {"status":"NO_BATCH_ARTIFACT_DIRECTORY","provider_posts":0,"omc_attempts":0}
    attempts=[]
    known_post_count=0
    for phase in PHASES:
        a=(batch/(phase+"-attempt.json")).exists()
        rfile=batch/phase/"receipt.json"
        receipt=read_json(rfile) if rfile.is_file() else None
        observed=receipt.get("provider_calls") if receipt else None
        if a and observed==1:
            known_post_count+=1
        attempts.append({"phase":phase,"attempt_reserved":a,
            "provider_posts_reported":observed,
            "provider_consumption_complete":bool(receipt and receipt.get("provider_usage") is not None),
            "provider_usage":receipt.get("provider_usage") if receipt else None,
            "finish_reason":receipt.get("provider_finish_reason") if receipt else None,
            "native_model_returned":receipt.get("model_returned") if receipt else None,
            "g1_admissible":(batch/(phase+"-g1.json")).exists(),
            "provider_raw_archived":(batch/phase/"provider-raw.json").is_file(),
            "attempt_may_have_consumed_when_unobserved":a and observed is None})
    omc_attempt=(batch/"bf05/attempt.json").is_file()
    omc_result=(read_json(batch/"bf05/physical-result.json")
                if (batch/"bf05/physical-result.json").is_file() else None)
    status=("G2_RECORDED" if omc_result is not None
            else "STOPPED_BEFORE_OR_DURING_OMC" if omc_attempt
            else "STOPPED_AFTER_BF04" if attempts[1]["attempt_reserved"]
            else "STOPPED_AFTER_BF03" if attempts[0]["attempt_reserved"]
            else "NO_PAID_ATTEMPT")
    report={"schema":"buffalo-adjust-v1/final/1","batch_id":BATCH_ID,
        "status":status,"attempts":attempts,"provider_posts_observed":known_post_count,
        "provider_attempts_reserved":sum(x["attempt_reserved"] for x in attempts),
        "omc_attempt_reserved":omc_attempt,"omc_attempts_max":1,
        "physical_result":omc_result,
        "ct03_lock_score_or_denominator_touched":False,
        "heldout_truth_accessed":False,
        "other_arms_or_custodian_used":False,
        "retries":0,"unobserved_post_is_not_zero":True}
    write_json(batch/"live-result.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=("admit","generate","physical","finalize"))
    parser.add_argument("--workspace",required=True,type=Path)
    parser.add_argument("--evidence",type=Path)
    args=parser.parse_args(argv)
    if args.phase in ("admit","generate") and args.evidence is None:
        raise ArenaError("BF_PUBLIC_EVIDENCE_DIRECTORY_REQUIRED")
    if args.phase=="admit":
        out=admit(args.workspace,args.evidence)
    elif args.phase=="generate":
        out=generate(args.workspace,args.evidence)
    elif args.phase=="physical":
        out=physical(args.workspace)
    else:
        out=finalize(args.workspace)
    print(json.dumps(out,indent=2))


if __name__=="__main__":
    try:
        main()
    except (ArenaError,ValueError,KeyError,subprocess.TimeoutExpired) as error:
        print(json.dumps({"status":"STOPPED_NO_RETRY",
                          "error":str(error)}),file=sys.stderr)
        raise SystemExit(2)
