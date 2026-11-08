"""Native GitHub stages. Data roles are separate jobs; orchestration needs no admin token."""
import argparse
from datetime import datetime,timezone
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.request

from .common import ArenaError,read_json,write_json
from .connections import Secret,public_config
from .github import GitHub
from .runtime import module,execute,libraries,verify_ct02,verify
from .reporting import write_report

LOCK_SCHEMA="arena.native-lock-archive/1"


def native(root,name):
    sys.path.insert(0,str(Path(root).resolve()))
    return importlib.import_module("scripts.arena_cafe."+name)


def identity():
    sha=os.environ.get("GITHUB_SHA","")
    run=os.environ.get("GITHUB_RUN_ID","")
    if not re.fullmatch("[0-9a-f]{40}",sha) or not re.fullmatch("[1-9][0-9]*",run):
        raise ArenaError("Actual GitHub run and frozen commit are required.")
    return sha,run


def admit(mode,authorized,freeze_sha,omc,posts):
    sha,run=identity()
    if mode not in ("integration","live"):
        raise ArenaError("Unknown execution mode.")
    if freeze_sha and freeze_sha!=sha:
        raise ArenaError("Requested freeze differs from the actual workflow commit.")
    if mode=="live":
        if (authorized!="yes" or omc!=19 or posts!=2 or
            os.environ.get("GITHUB_EVENT_NAME")!="workflow_dispatch" or
            os.environ.get("GITHUB_RUN_ATTEMPT")!="1" or
            os.environ.get("GITHUB_REF")!="refs/heads/main"):
            raise ArenaError("One live CT03 lot requires explicit yes, main, first attempt, 19 OMC and 2 POST.")
    verify()
    return {"mode":mode,"frozen_code_sha":sha,"run_id":run,
            "authorized_live":mode=="live","new_omc_max":19 if mode=="live" else 0,
            "provider_posts_max":2 if mode=="live" else 0}


def assert_producer_environment(*,buffalo=False):
    if any(os.environ.get(name) for name in ("CT03_R2_ACCESS_KEY_ID","CT03_R2_SECRET_ACCESS_KEY","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY")):
        raise ArenaError("Storage credentials must not be exported to a producer job.")
    if not buffalo and os.environ.get("CLOUDFLARE_API_TOKEN"):
        raise ArenaError("D/M do not need provider credentials.")


def provider_preflight():
    account=os.environ.get("CLOUDFLARE_ACCOUNT_ID") or public_config()["cloudflare"]["account_id"]
    token=os.environ.get("CLOUDFLARE_API_TOKEN","")
    if not re.fullmatch("[0-9a-f]{32}",account) or not token:
        raise ArenaError("Provider connection requires the account ID and Workers AI token.")
    def get(path):
        req=urllib.request.Request("https://api.cloudflare.com/client/v4"+path,
             headers={"Authorization":"Bearer "+token})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code,None
        except (OSError,ValueError):
            raise ArenaError("Provider preflight network/response failure; no inference was attempted.") from None
    status,body=get("/accounts/"+account+"/ai/models/search?per_page=1")
    if status!=200 or not body.get("success"):
        raise ArenaError("Workers AI metadata access failed before OMC/provider consumption.")
    # A broad token must not let the producer read custody storage.
    r2_status,_=get("/accounts/"+account+"/r2/buckets?per_page=1")
    if r2_status!=403:
        raise ArenaError("Provider token R2 bucket listing is not denied; use its dedicated Workers AI connection.")
    return {"workers_ai_metadata":"AVAILABLE","r2_bucket_listing_denied":True,"credential_policy":"DEDICATED_WORKERS_AI_EDIT_ONLY",
            "inference_write_permission":"NOT_TESTED_WITH_PAID_POST","provider_posts":0,"new_omc":0}


def public_input(root):
    folder=Path(root)/"artifacts/ct03-public"
    expected={"construction.json","world-commitment.json","release-status.json"}
    if not folder.is_dir() or {p.name for p in folder.iterdir()}!=expected or any(p.is_symlink() or not p.is_file() for p in folder.iterdir()):
        raise ArenaError("Public producer input must contain exactly the three released JSON files.")
    validator=native(root,"ct03_public_intake")
    validator.validate(*(read_json(folder/name) for name in ("construction.json","world-commitment.json","release-status.json")))
    return read_json(folder/"construction.json")


def common_environment():
    sha,_=identity()
    return {**os.environ,"CT03_LIVE_BATCH_AUTH":"CT03_ONE_APPROVED_LOT",
            "CT03_FROZEN_SHA":sha,"CT03_OMC_BUDGET_MAX":"19","CT03_OMC_WORLD_ATTEMPTS":"1"}


def dm(root):
    assert_producer_environment()
    public_input(root)
    verify_ct02(root)
    module(root,"ct03_dm_initial_batch","prepare","--out","artifacts/ct03-producer/dm-ten",
           "--reuse-report","artifacts/ct03-reuse/reused-original-two.json")
    libraries()
    env={**common_environment(),"CT03_DM_TEN_AUTH":"EXACTLY_TEN_ORIGINAL_INITIALS"}
    execute(root,["bash","scripts/arena_cafe/ct03_dm_execute_ten_once.sh"],env=env)
    module(root,"ct03_dm_feedback_round","--ten-root","artifacts/ct03-producer/dm-ten",
           "--ct02-root","artifacts/ct03-reuse/original","--reuse-report","artifacts/ct03-reuse/reused-original-two.json",
           "--construction","artifacts/ct03-public/construction.json",
           "--recorded-at",datetime.now(timezone.utc).isoformat(),"--out","artifacts/ct03-producer/dm-feedback")
    env={**common_environment(),"CT03_M_REVISIONS_AUTH":"ORIGINAL_M2_SELECTED_ONLY","CT03_OMC_BEFORE_M_REVISIONS":"11"}
    execute(root,["bash","scripts/arena_cafe/ct03_m_revision_execute_once.sh"],env=env)
    base="artifacts/ct03-producer/"
    module(root,"ct03_dm_lock_projection","--dm-feedback",base+"dm-feedback/producer-12/dm-feedback-report.json",
           "--d-manifest",base+"dm-ten/D/manifest.json","--m-manifest",base+"dm-ten/M/manifest.json",
           "--revision-outcomes",base+"dm-feedback/producer-12/m-revision-outcomes.json","--out",base+"dm-twelve-lock-rows.json")
    sha,run=identity()
    module(root,"ct03_lot_budget","issue","--dm-report",base+"dm-feedback/producer-12/dm-feedback-report.json",
           "--m-revision-report",base+"dm-feedback/producer-12/m-revision-outcomes.json",
           "--initial-attempt-log",base+"dm-ten/attempts.log",
           "--m-revision-attempt-log",base+"dm-feedback/producer-12/m-revision-attempts.log",
           "--run-id",run,"--git-sha",sha,"--out",base+"dm-budget.json")
    return {"status":"TWELVE_ORIGINAL_SLOTS_RECORDED","provider_posts":0}


def b_usage(root):
    root=Path(root)
    sha,run=identity()
    base=root/"artifacts/ct03-producer"
    suffix=r" attempted; GitHub run "+run+"; code "+sha
    def count(name,pattern):
        path=base/name
        if not path.exists(): return None
        rows=path.read_text(encoding="utf-8").splitlines()
        if len(rows)!=len(set(rows)) or any(not re.fullmatch(pattern+suffix,row) for row in rows):
            raise ArenaError("B attempt ledger does not belong to the current lot.")
        return len(rows)
    rounds=count("b-provider-attempts.log",r"B-(initial|revision)")
    physical=count("b-physical-attempts.log",r"B-(initial|revision)")
    receipts=[]
    for phase in ("initial","revision"):
        path=base/"B"/phase/"receipt.json"
        if path.is_file():
            receipt=read_json(path)
            if receipt.get("mode")!="live" or receipt.get("provider_calls") not in (0,1):
                raise ArenaError("B usage receipt is not a live-shaped execution receipt.")
            receipts.append(receipt)
    post_complete=rounds is not None and len(receipts)==rounds
    # The original completed B projection also proves when no physical native existed.
    row_path=base/"B-thirteenth-row.json"
    row=read_json(row_path).get("row") if row_path.is_file() else None
    if physical is None and row and all(row[p]["status"] in ("NO_NATIVE","NOT_EXECUTED","G0_REJECTED","G1_BLOCKED") for p in ("initial","final")):
        physical=0
    value={"schema":"arena.b-usage/1","run_id":run,"frozen_code_sha":sha,
           "reserved_provider_rounds":rounds,"provider_posts_observed":sum(x["provider_calls"] for x in receipts),
           "provider_posts_complete":post_complete,"physical_omc_attempts":physical,
           "physical_count_complete":physical is not None,
           "provider_usage":[x.get("provider_usage") for x in receipts],
           "monetary_cost":None}
    write_json(root/"artifacts/native-b-usage.json",value)
    return value


def buffalo(root):
    assert_producer_environment(buffalo=True)
    public_input(root)
    sha,run=identity()
    receipt="artifacts/ct03-budget/dm-budget.json"
    module(root,"ct03_lot_budget","verify","--receipt",receipt,
           "--construction","artifacts/ct03-public/construction.json","--run-id",run,"--git-sha",sha)
    libraries()
    execute(Path(root)/"upstream/sd-ai",["npm","ci","--ignore-scripts","--omit=optional","--no-audit","--no-fund"])
    env={**common_environment(),"CLOUDFLARE_ACCOUNT_ID":os.environ.get("CLOUDFLARE_ACCOUNT_ID") or public_config()["cloudflare"]["account_id"],
         "SDAI_ROOT":str(Path(root)/"upstream/sd-ai"),
         "CT03_B_PHYSICAL_AUTH":"EXACT_ORIGINAL_B_NATIVE_ONCE","CT03_DM_COUNT_ONLY_BUDGET":receipt,
         "BUFFALO_MODE":"live","BUFFALO_LIVE_AUTH":"ONE_UPSTREAM_CALL",
         "BUFFALO_CT03_LIVE_AUTH":"CT03_ONE_ROUND_EXPRESS_AUTH"}
    try:
        execute(root,["bash","scripts/arena_cafe/ct03_b_producer_rounds_once.sh"],env=env)
    finally:
        b_usage(root)
    return {"status":"THIRTEENTH_ORIGINAL_SLOT_RECORDED"}


def lock(root):
    public_input(root)
    inputs="artifacts/native-lock-input"
    module(root,"ct03_producer_freeze_handoff",
           "--dm-projection","artifacts/dm-join/dm-twelve-lock-rows.json",
           "--b-projection","artifacts/b-join/B-thirteenth-row.json",
           "--construction","artifacts/ct03-public/construction.json",
           "--commitment","artifacts/ct03-public/world-commitment.json",
           "--d-manifest","artifacts/dm-join/dm-ten/D/manifest.json",
           "--m-manifest","artifacts/dm-join/dm-ten/M/manifest.json","--out",inputs)
    archive="artifacts/native-lock"
    module(root,"ct03_prospective_lock","--construction",inputs+"/construction.json",
           "--commitment",inputs+"/world-commitment.json","--d-manifest",inputs+"/D/manifest.json",
           "--m-manifest",inputs+"/M/manifest.json","--entries",inputs+"/entries.json",
           "--out",archive+"/lock.json")
    sealed=read_json(Path(root)/archive/"lock.json")
    sha,run=identity()
    write_json(Path(root)/archive/"archive-metadata.json",{
        "schema":LOCK_SCHEMA,"repository":os.environ["GITHUB_REPOSITORY"],"github_run_id":run,
        "frozen_code_sha":sha,"lock_sha256":sealed["lock_sha256"],"candidate_count":13,
        "producer_execution_attempt":1,
        "reserved_truth_opened":False,"producer_jobs_closed_before_archive":True})
    return {"status":"THIRTEEN_PREDICTIONS_SEALED_NOT_YET_EVALUATED","lock_sha256":sealed["lock_sha256"]}


def verify_archive(root,artifact_id,*,api=None):
    """All checks precede constructing an R2 client or opening any reserve."""
    sha,run=identity()
    if not re.fullmatch("[1-9][0-9]*",str(artifact_id)):
        raise ArenaError("An actual immutable lock artifact ID is required.")
    if api is None:
        token=os.environ.get("GH_TOKEN","")
        if not token: raise ArenaError("Evaluator needs its own read-only GitHub job token.")
        api=GitHub(os.environ["GITHUB_REPOSITORY"],Secret(token,"GITHUB_TOKEN"))
    metadata=api.repo("GET","/actions/artifacts/"+str(artifact_id))
    event=api.run(int(run))
    if (metadata.get("expired") or metadata["workflow_run"]["id"]!=int(run) or
        metadata["workflow_run"]["head_sha"]!=sha or metadata["name"]!="native-lock-"+run or
        event["head_sha"]!=sha or event["event"]!="workflow_dispatch" or event.get("run_attempt",0)<1 or event.get("head_branch")!="main" or
        event["path"]!=".github/workflows/arena-run.yml"):
        raise ArenaError("Lock artifact is not from this frozen native workflow.")
    jobs=api.repo("GET","/actions/runs/"+run+"/attempts/1/jobs?per_page=100")["jobs"]
    expected={"Select and simulate one private world","D and M originals","Buffalo original and own feedback","Lock producer predictions"}
    complete={job["name"] for job in jobs if job["status"]=="completed" and job["conclusion"]=="success"}
    if not expected<=complete:
        raise ArenaError("Producer/lock jobs have not all closed successfully.")
    folder=Path(root)/"artifacts/native-lock"
    if {p.name for p in folder.iterdir()}!={"lock.json","archive-metadata.json"} or any(p.is_symlink() or not p.is_file() for p in folder.iterdir()):
        raise ArenaError("Unexpected files in downloaded lock archive.")
    sealed=read_json(folder/"lock.json")
    info=read_json(folder/"archive-metadata.json")
    native(root,"ct03_prospective_lock").verify_locked(sealed)
    if (info.get("schema")!=LOCK_SCHEMA or info.get("frozen_code_sha")!=sha or
        info.get("github_run_id")!=run or info.get("repository")!=os.environ["GITHUB_REPOSITORY"] or
        info.get("producer_execution_attempt")!=1 or info.get("candidate_count")!=13 or
        info.get("lock_sha256")!=sealed["lock_sha256"] or sealed["candidate_count"]!=13 or
        info.get("reserved_truth_opened") is not False or info.get("producer_jobs_closed_before_archive") is not True):
        raise ArenaError("Frozen archive metadata mismatch; reserve remains closed.")
    construction=public_input(root)
    commitment=read_json(Path(root)/"artifacts/ct03-public/world-commitment.json")
    from scripts.arena_v0_contract import digest
    if sealed["construction_sha256"]!=digest(construction) or sealed["world_commitment_sha256"]!=commitment["private_commitment_sha256"]:
        raise ArenaError("Lock and released public observations describe different worlds.")
    return sealed,jobs


def consumption(root):
    root=Path(root)
    budget=read_json(root/"artifacts/ct03-budget/dm-budget.json")
    sha,run=identity()
    native(root,"ct03_lot_budget").verify_receipt(budget,run_id=run,git_sha=sha,
                   construction=public_input(root))
    b=read_json(root/"artifacts/native-usage/native-b-usage.json")
    world=read_json(root/"artifacts/native-usage/native-world-usage.json")
    if any(x.get("run_id")!=run or x.get("frozen_code_sha")!=sha for x in (b,world)):
        raise ArenaError("Consumption evidence belongs to another lot.")
    if world["world_omc_attempts"]!=1:
        raise ArenaError("Exactly one world attempt must precede scoring.")
    complete=bool(b["physical_count_complete"] and b["provider_posts_complete"])
    known=1+budget["dm_initial_omc_attempts"]+budget["m_revision_omc_attempts"]
    omc=known+(b["physical_omc_attempts"] if b["physical_omc_attempts"] is not None else 0)
    posts=b["provider_posts_observed"]
    if omc>19 or posts>2 or (b["reserved_provider_rounds"] or 0)>2:
        raise ArenaError("Observed native consumption exceeds the authorized lot.")
    return {"omc":{"limit":19,"observed_attempts":omc,"complete":bool(b["physical_count_complete"]),
                   "remaining":19-omc if b["physical_count_complete"] else None,"failed_local_attempts":0},
            "provider_posts":{"limit":2,"observed_attempts":posts,"complete":bool(b["provider_posts_complete"]),
                              "remaining":2-posts if b["provider_posts_complete"] else None,"failed_local_attempts":0},
            "workflow":{"limit":1,"observed_attempts":1,"complete":True,"remaining":0,"failed_local_attempts":0}}


def evaluate(root,artifact_id):
    sealed,jobs=verify_archive(root,artifact_id)
    usage=consumption(root)
    # Imports and constructor deliberately follow archive verification.
    from .custody import R2
    sha,run=identity()
    client=R2()
    private=Path(os.environ["RUNNER_TEMP"])/"arena-evaluator-private"
    client.download("ct03/igc-modular/run-"+run,private)
    result=Path(root)/"artifacts/native-result"
    result.mkdir(parents=True,exist_ok=False)
    scorer=native(root,"ct03_minimal_score")
    ack={"schema":scorer.FREEZE_SCHEMA,"lock_sha256":sealed["lock_sha256"],"github_run_id":int(run),
         "github_artifact_id":int(artifact_id),"frozen_code_sha":sha,
         "verified_by_custodian":"github-native-immutable-artifact-job",
         "archived_before_reveal":True,"producer_write_disabled":True,
         "custody_scope":"PROCEDURAL_HUMAN_NO_EXTERNAL_SIGNER"}
    score=scorer.evaluate(lock=sealed,archive=ack,
          construction=read_json(Path(root)/"artifacts/ct03-public/construction.json"),
          commitment=read_json(Path(root)/"artifacts/ct03-public/world-commitment.json"),
          producer_root=Path(root),private_dir=private/"world-run",out=result/"score-post-lock.json")
    write_json(result/"archive-record.json",ack)
    write_json(result/"consumption.json",usage)
    run_report={"schema":"arena.run/1","experiment":"ct03-native-original-engines","backend":"github",
                "status":"COMPLETED","consumption":usage,
                "cost":{"estimated":None,"billed":None,"currency":None,"note":"Provider invoice not supplied."},
                "stages":[{"name":j["name"],"state":"COMPLETED","detail":{"url":j.get("html_url")}}
                          for j in jobs if j["status"]=="completed" and j["conclusion"]=="success"]}
    report={"schema":"arena.result/1","evidence_kind":"PHYSICAL_NATIVE_WORKFLOW","physical_experiment_executed":True,
            "scientific_scope":score["scientific_scope"],"score":score,"run":run_report,
            "provenance":{"repository":os.environ["GITHUB_REPOSITORY"],"run_id":run,"frozen_code_sha":sha,
                          "lock_artifact_id":int(artifact_id),"engine_sources":verify(),
                          "old_repository_network_reads":0}}
    write_json(result/"result.json",report)
    write_report(report,result)
    return {"status":"PHYSICAL_NATIVE_WORKFLOW_COMPLETED","candidate_denominator":13,"consumption":usage}



def dm_usage(root):
    root=Path(root)
    sha,run=identity()
    base=root/"artifacts/ct03-producer"
    def count(path,pattern):
        if not path.is_file(): return None
        rows=path.read_text(encoding="utf-8").splitlines()
        suffix=r" attempted; GitHub run "+run+"; code "+sha
        if len(rows)!=len(set(rows)) or any(not re.fullmatch(pattern+suffix,row) for row in rows):
            raise ArenaError("D/M attempt evidence differs from the frozen lot.")
        return len(rows)
    initial=count(base/"dm-ten/attempts.log",r"[DM][1-5]")
    revisions=count(base/"dm-feedback/producer-12/m-revision-attempts.log",r"M[0-5]")
    complete=False
    if (base/"dm-budget.json").is_file():
        budget=read_json(base/"dm-budget.json")
        native(root,"ct03_lot_budget").verify_receipt(budget,run_id=run,git_sha=sha,construction=public_input(root))
        if initial!=10 or (revisions if revisions is not None else 0)!=budget["m_revision_omc_attempts"]:
            raise ArenaError("D/M counts differ from original budget evidence.")
        revisions=budget["m_revision_omc_attempts"]
        complete=True
    value={"schema":"arena.dm-usage/1","run_id":run,"frozen_code_sha":sha,
           "initial_omc_attempts":initial,"revised_omc_attempts":revisions,"complete":complete,"provider_posts":0}
    write_json(root/"artifacts/native-dm-usage.json",value)
    return value


def failure_report(root):
    root=Path(root)
    sha,run=identity()
    states=json.loads(os.environ.get("ARENA_JOB_STATES","{}"))
    source=root/"artifacts/native-usage"
    def usage(name):
        path=source/name
        if not path.is_file(): return None
        data=read_json(path)
        if data.get("run_id")!=run or data.get("frozen_code_sha")!=sha:
            raise ArenaError("Failure usage is not from this run.")
        return data
    world=usage("native-world-usage.json")
    dm_info=usage("native-dm-usage.json")
    b=usage("native-b-usage.json")
    skipped=lambda job: states.get(job,{}).get("result")=="skipped"
    world_count=world.get("world_omc_attempts") if world else 0 if skipped("world") else None
    initial=dm_info.get("initial_omc_attempts") if dm_info else 0 if skipped("dm") else None
    revision=dm_info.get("revised_omc_attempts") if dm_info else 0 if skipped("dm") else None
    b_count=b.get("physical_omc_attempts") if b else 0 if skipped("buffalo") else None
    posts=b.get("provider_posts_observed") if b else 0
    posts_complete=bool(b and b.get("provider_posts_complete")) or skipped("buffalo")
    counts=(world_count,initial,revision,b_count)
    total=sum(x for x in counts if x is not None)
    complete=all(x is not None for x in counts)
    resources={
        "omc":{"limit":19,"observed_attempts":total,"complete":complete,"remaining":19-total if complete else None,"failed_local_attempts":0},
        "provider_posts":{"limit":2,"observed_attempts":posts,"complete":posts_complete,"remaining":2-posts if posts_complete else None,"failed_local_attempts":0},
        "workflow":{"limit":1,"observed_attempts":1,"complete":True,"remaining":0,"failed_local_attempts":0}}
    url="https://github.com/"+os.environ["GITHUB_REPOSITORY"]+"/actions/runs/"+run
    run_report={"experiment":"ct03-native-original-engines","backend":"github","status":"FAILED_OR_BLOCKED",
                "consumption":resources,"cost":{"estimated":None,"billed":None,"currency":None},
                "stages":[{"name":name,"state":item.get("result","unknown"),"detail":{"url":url}} for name,item in states.items()]}
    result={"schema":"arena.result/1","evidence_kind":"NATIVE_EXECUTION_DIAGNOSTIC","scientific_conclusion":None,
            "run":run_report,"frozen_code_sha":sha,"note":"Known attempts are lower bounds when evidence is incomplete; no automatic retry."}
    output=root/"artifacts/native-diagnostic"
    write_json(output/"result.json",result)
    write_report(result,output)
    return {"status":"FAILURE_REPORTED","consumption":resources}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("admit","provider-preflight","storage-preflight","world","dm","dm-usage","b","b-usage","lock","verify-lock","evaluate","failure-report"))
    parser.add_argument("--workspace",type=Path)
    parser.add_argument("--artifact-id",default="")
    parser.add_argument("--mode",default="integration")
    parser.add_argument("--authorized",default="no")
    parser.add_argument("--freeze-sha",default="")
    parser.add_argument("--omc",type=int,default=19)
    parser.add_argument("--posts",type=int,default=2)
    args=parser.parse_args(argv)
    if args.stage=="admit":
        result=admit(args.mode,args.authorized,args.freeze_sha,args.omc,args.posts)
        output=os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output,"a",encoding="utf-8") as stream:
                stream.write("mode="+result["mode"]+"\n")
                stream.write("freeze_sha="+result["frozen_code_sha"]+"\n")
    elif args.stage=="provider-preflight": result=provider_preflight()
    elif args.stage=="storage-preflight":
        from .custody import R2
        result=R2().preflight()
    else:
        if args.workspace is None: raise ArenaError("Stage requires its runner workspace.")
        root=args.workspace.resolve()
        if args.stage=="world":
            from .custody import create_world
            libraries()
            result=create_world(root)
        elif args.stage=="dm": result=dm(root)
        elif args.stage=="dm-usage": result=dm_usage(root)
        elif args.stage=="failure-report": result=failure_report(root)
        elif args.stage=="b": result=buffalo(root)
        elif args.stage=="b-usage": result=b_usage(root)
        elif args.stage=="lock": result=lock(root)
        elif args.stage=="verify-lock":
            sealed,_=verify_archive(root,args.artifact_id)
            result={"status":"LOCK_VERIFIED_BEFORE_R2_READ","lock_sha256":sealed["lock_sha256"]}
        else: result=evaluate(root,args.artifact_id)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    try:
        main()
    except ArenaError as error:
        print(json.dumps({"status":"STOPPED","reason":str(error)}),file=sys.stderr)
        raise SystemExit(2)
