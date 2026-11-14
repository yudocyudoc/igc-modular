"""Coffee B0 Buffalo R1: one original Engine.generate(currentModel) cloud POST.

Parent: the one real B-LIVE-01 output; feedback: finalized as-of replayed B
Ledger/ATMS. Never cross-load D/M models or truth. Separate manual approval
from all previous generation attempts. No automatic retry after reservation.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from .common import ArenaError, digest, read_json, write_json
from .connections import Secret, public_config
from .github import GitHub
from .coffee_adapters.shared import sha_bytes
from .coffee_adapters.b_translation import generate as translate, TranslationBlocked
from .buffalo.validation import diagnose
from . import coffee_feedback as feedback, coffee_dm_campaign as dm
from .runtime import verify

REPO = "yudocyudoc/igc-modular"
WORKFLOW = ".github/workflows/coffee-buffalo-review.yml"
SOURCE_RUN = 43561168032
SOURCE_SHA = "227e7f20137d99d5da122ffb8a0ee93b069548c7"
SOURCE_ARTIFACT = 14100770369
SOURCE_ZIP = "sha256:51b56dc28e5c229a280adf3f38062744992a61dc21dff48973e18f48105d10d8"
RUNNER = Path(__file__).with_name("coffee_review_runner.mjs")
PROVIDER_MODEL = "@cf/zai-org/glm-5.3-flash"
MAX_POSTS = 1

def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_B_REVIEW_" + code)

def identity(env=None):
    env = os.environ if env is None else env
    need(env.get("GITHUB_REPOSITORY") == REPO
         and env.get("GITHUB_REF") == "refs/heads/main"
         and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
         and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and env.get("COFFEE_B_REVIEW_AUTH") == "yes"
         and re.fullmatch(r"[0-9a-f]{40}",env.get("GITHUB_SHA",""))
         and re.fullmatch(r"[1-9][0-9]{0,19}",env.get("GITHUB_RUN_ID","")),
         "MANUAL_FIRST_ATTEMPT_MAIN_REQUIRED")
    need(not any(env.get(k) for k in (*dm.NO_R2,"OPEN_ROUTER_API_KEY")),
         "PROVIDER_OR_PRIVATE_SECRET_IN_READONLY_ADMISSION")
    return env["GITHUB_SHA"],int(env["GITHUB_RUN_ID"])

def history(api, current):
    """No paid second attempt; unknown/uncertain dispatches fail closed."""
    data=api.repo("GET",
        "/actions/workflows/coffee-buffalo-review.yml/runs?event=workflow_dispatch&per_page=100")
    count,runs=data.get("total_count"),data.get("workflow_runs")
    need(type(count) is int and count<=100 and
         isinstance(runs,list) and len(runs)==count,"RUN_HISTORY_INCOMPLETE")
    need(not [r for r in runs if r.get("id")!=current],
         "PRIOR_REVIEW_DISPATCH_REQUIRES_MANUAL_RECONCILIATION")
    return {"other_dispatches":0,"max_provider_posts":MAX_POSTS}

def validate_sources(archive, parent, bridge=None):
    """Require exact B feedback recorded by ATMS, original model, and R0."""
    need(set(archive)=={
        "summary.json", "B-own-review-packet.json",
        "B-ledger.sqlite","D-ledger.sqlite","M-ledger.sqlite"},
         "FEEDBACK_ARTIFACT_UNEXPECTED_MEMBERS")
    summary=json.loads(archive["summary.json"])
    packet=json.loads(archive["B-own-review-packet.json"])
    native,receipt,parent_hash,translation,notes=feedback._verify_b(parent)
    need(summary.get("schema")=="arena.coffee-peak.own-ledger-atms-consumption/2"
         and summary.get("status")==
             "OWN_FEEDBACK_RETRIEVED_DM_POLICIES_INVOKED_B_PACKET_NOT_SENT"
         and summary.get("case_sha256")==dm.CASE_SHA256
         and summary.get("as_of_replay_from_final_sqlite") is True
         and summary.get("reserved_truth_access") is False
         and summary.get("provider_posts")==0
         and summary.get("new_omc")==0
         and summary.get("scientific_lock_created") is False
         and summary.get("arms",{}).get("B",{}).get("candidate_count")==1
         and summary["arms"]["B"]["original_engine_revision_status"]==
             "NOT_INVOKED_REQUIRES_SEPARATE_PROVIDER_AUTH"
         and summary["arms"]["B"]["as_of_replay_verified_after_packet"] is True
         and summary["arms"]["B"]["parent_hash"]==parent_hash
         and summary["arms"]["B"]["ledger_sqlite_sha256"]==
             sha_bytes(archive["B-ledger.sqlite"])
         and summary["arms"]["B"]["revision_packet_sha256"]==
             sha_bytes(archive["B-own-review-packet.json"]),
         "B_LEDGER_SUMMARY_PROVENANCE_INVALID")
    need(packet.get("schema")=="arena.coffee-peak.buffalo-review-envelope/1"
         and packet.get("status")=="OWN_G1_FEEDBACK_RETRIEVED_PACKET_PREPARED_NOT_SENT"
         and packet.get("original_engine_review_invoked") is False
         and packet.get("revision_budget_authorized") is False
         and packet.get("new_native_model") is None
         and packet.get("never_reuse_Engine_generate_without_currentModel") is True
         and packet.get("truth_access") is False
         and packet.get("provider_posts_this_phase")==0
         and packet.get("parent_native_file_sha256")==parent_hash
         and packet.get("parent_provider_receipt_sha256")==
             sha_bytes(parent["provider/receipt.json"])
         and packet.get("currentModel")==native["model"]
         and packet.get("diagnostic_sha256")==
             summary["arms"]["B"]["diagnostic_sha256"]
         and packet.get("retrieved_before_any_possible_review")==
             summary["arms"]["B"]["retrieved_before_review"],
         "REVIEW_PACKET_NOT_BOUND_TO_ACTUAL_PARENT")
    cuts=summary.get("logical_temporal_cuts",{})
    asof=packet["retrieved_before_any_possible_review"]
    need(cuts.get("feedback_recorded_at","") < asof["as_known_at"] <
         cuts.get("disposition_recorded_at","")
         and cuts["retrieval_as_known_at"]==asof["as_known_at"]
         and summary["arms"]["B"]["final_sqlite_as_of_replay"]["projection_hash"]==
             asof["projection_hash"],
         "B_ASOF_ORDER_INVALID")
    own=packet.get("own_feedback",{})
    need(own.get("arm")=="B" and own.get("condition")=="B0"
         and own.get("evidence")=="G1"
         and own.get("parent_hash")==parent_hash
         and own.get("original_native_file_sha256")==parent_hash
         and own.get("source_hash")==dm.CASE_SHA256
         and own.get("no_silent_model_repair") is True
         and own.get("observations")==[]
         and own.get("no_future_truth") is True
         and own.get("own_evidence_only") is True
         and digest(own)==packet["diagnostic_sha256"],
         "B_FEEDBACK_NOT_OWN_DIAGNOSTIC")
    # Actual original Ledger, ATMS and memory retrieval, from final SQLite.
    bridge=bridge or feedback._original_bridge()
    ctx=bridge.make_context(experiment="Coffee",world="Peak",round_id="R0",
                            arm="B",condition="B0",source_hash=dm.CASE_SHA256)
    with TemporaryDirectory() as tmp:
        db=Path(tmp)/"B-ledger.sqlite"
        db.write_bytes(archive["B-ledger.sqlite"])
        replay=feedback.replay_final_ledger_at_cut(
            bridge,db,ctx,parent_hash,asof)
    need(replay["predecision_revision_count"]==4 and
         replay["final_revision_count"]==4 and
         replay["projection_hash"]==asof["projection_hash"],
         "B_FINAL_SQLITE_ATMS_REPLAY_FAILED")
    first=json.loads(parent["input.json"])
    need(first.get("schema")=="arena.coffee-peak.buffalo-public-input/1"
         and first.get("case_sha256")==dm.CASE_SHA256
         and first.get("public_sha256")==dm.PUBLIC_SHA256
         and first.get("execution_run_id")==feedback.B_RUN_ID
         and first.get("source_artifact_id")==dm.ARTIFACT_ID
         and first.get("truth_access") is False
         and first.get("new_omc")==0
         and first.get("provider_posts")==0,
         "ORIGINAL_INPUT_NOT_SAME_PUBLIC_B0")
    return native,first,packet,replay

def admission(output, *,env=None,api=None):
    env=os.environ if env is None else env
    sha,run=identity(env)
    output=Path(output)
    need(not output.exists(),"REFUSE_OVERWRITE")
    if api is None:
        need(bool(env.get("GH_TOKEN")),"GITHUB_READ_TOKEN_REQUIRED")
        api=GitHub(REPO,Secret(env["GH_TOKEN"],"GITHUB_TOKEN"))
    history(api,run)
    verify(include_history=False)
    pub=feedback._fetch(api,
        run_id=SOURCE_RUN,sha=SOURCE_SHA,artifact_id=SOURCE_ARTIFACT,
        archive_sha=SOURCE_ZIP,workflow=feedback.WORKFLOW,
        artifact_name=f"coffee-b0-own-feedback-{SOURCE_RUN}",event="push")
    parent=feedback._fetch(api,
        run_id=feedback.B_RUN_ID,sha=feedback.B_SHA,
        artifact_id=feedback.B_ARTIFACT_ID,archive_sha=feedback.B_ARCHIVE_SHA,
        workflow=feedback.B_WORKFLOW,
        artifact_name=f"coffee-b-live-{feedback.B_RUN_ID}",
        event="workflow_dispatch")
    native,first,packet,replay=validate_sources(pub,parent)
    diagnostic=packet["own_feedback"]
    # No cross-arm data (D/M graphs, CSVs, scores) is placed in the request.
    # Pass on the exact original public prompt with this original B diagnosis.
    instruction=(
      "\n\nReview YOUR earlier native stock-flow model supplied as currentModel "
      "by the original Engine.generate call. Only use your OWN recorded G1 "
      "diagnostic (below), the same public construction and its existing "
      "hypotheses. Do not invent measured pickups, hidden truth, rival models, "
      "parameter fitting, or business-policy outcomes. Reconsider physical "
      "flow types and stock ports, explicit causal relationships and the "
      "native Euler timestep equal to horizon/64. Preserve the public "
      "103.237-minute horizon. Treat correction as a candidate, not a "
      "validated simulation. Do not assert you ran a solver.\n"
      +json.dumps(diagnostic,sort_keys=True,separators=(",",":")))
    payload={
        "schema":"arena.coffee-peak.buffalo-own-review-input/1",
        "run_id":run,"run_sha":sha,"round_kind":"revision",
        "case_sha256":dm.CASE_SHA256,"public_sha256":dm.PUBLIC_SHA256,
        "parent_live_run_id":feedback.B_RUN_ID,
        "parent_native_file_sha256":packet["parent_native_file_sha256"],
        "parent_receipt_file_sha256":packet["parent_provider_receipt_sha256"],
        "feedback_run_id":SOURCE_RUN,
        "feedback_artifact_id":SOURCE_ARTIFACT,
        "feedback_zip_sha256":SOURCE_ZIP,
        "feedback_diagnostic_sha256":packet["diagnostic_sha256"],
        "feedback_asof_receipt":packet["retrieved_before_any_possible_review"],
        "original_public_prompt_sha256":"sha256:"+__import__("hashlib").sha256(
            first["prompt"].encode()).hexdigest(),
        "prompt":first["prompt"]+instruction,
        "problemStatement":first["problemStatement"],
        "backgroundKnowledge":first["backgroundKnowledge"],
        "currentModel":native["model"],
        "source_model_sha256":packet["parent_native_file_sha256"],
        "max_provider_posts":1,"new_omc":0,"truth_access":False,
        "r2_access":False,"scientific_lock_created":False,
    }
    output.mkdir(parents=True,mode=0o700)
    write_json(output/"input.json",payload,exclusive=True)
    write_json(output/"admission.json",{
        "schema":"arena.coffee-peak.buffalo-review-admission/1",
        "execution_run":run,"execution_sha":sha,
        "case_sha256":dm.CASE_SHA256,
        "parent_live_run":feedback.B_RUN_ID,
        "feedback_run":SOURCE_RUN,"feedback_artifact":SOURCE_ARTIFACT,
        "feedback_zip_sha256":SOURCE_ZIP,
        "parent_sha256":payload["source_model_sha256"],
        "feedback_diagnostic_sha256":packet["diagnostic_sha256"],
        "as_of_replayed":True,"provider_posts":0,"new_omc":0,
        "truth_access":False,"scientific_lock_created":False,
        "input_sha256":digest(payload),
    },exclusive=True)
    return {"status":"REVISION_READY_NO_PROVIDER_POST",
            "feedback_asof_replayed":True,"parent_original":True,"provider_posts":0}

def invoke(output, *,env=None,runner=None):
    env=dict(os.environ if env is None else env)
    sha,run=identity({k:v for k,v in env.items() if k not in
                    ("CLOUDFLARE_API_TOKEN","CLOUDFLARE_ACCOUNT_ID")})
    need(not any(env.get(k) for k in dm.NO_R2
                 if k != "CLOUDFLARE_API_TOKEN"),
         "PRIVATE_SECRETS_FORBIDDEN")
    account=public_config()["cloudflare"]["account_id"]
    need(env.get("CLOUDFLARE_ACCOUNT_ID") in (None,"",account)
         and bool(env.get("CLOUDFLARE_API_TOKEN"))
         and re.fullmatch(r"[0-9a-fA-F]{32}",account),
         "PROVIDER_ACCOUNT_OR_TOKEN_UNAVAILABLE")
    output=Path(output).resolve()
    admission_=read_json(output/"admission.json")
    inp=read_json(output/"input.json")
    need(admission_["execution_run"]==run and
         admission_["execution_sha"]==sha and
         admission_["input_sha256"]==digest(inp) and
         inp["run_id"]==run and inp["run_sha"]==sha and
         inp["source_model_sha256"]==admission_["parent_sha256"] and
         not (output/"attempt.json").exists() and
         not (output/"provider").exists(),
         "REVIEW_PRE_ATTEMPT_CONTRACT_FAILED")
    write_json(output/"attempt.json",{
        "schema":"arena.coffee-peak.buffalo-review-attempt/1",
        "state":"RESERVED_BEFORE_HTTP","run_id":run,"sha":sha,
        "max_posts":1,"no_retry":True,
        "uncertain_consumption_is_not_zero":True},exclusive=True)
    child={**env,"CLOUDFLARE_ACCOUNT_ID":account,
           "COFFEE_B_REVIEW_OUT":str(output/"provider"),
           "COFFEE_B_REVIEW_INPUT":str(output/"input.json"),
           "COFFEE_B_REVIEW_ADMISSION":str(output/"admission.json"),
           "COFFEE_B_REVIEW_ATTEMPT":str(output/"attempt.json"),
           "SDAI_ROOT":str(Path(env["RUNNER_TEMP"])/"arena-native/upstream/sd-ai"),
           "BUFFALO_SCRIPTS_ROOT":str(Path(env["RUNNER_TEMP"])/"arena-native/scripts")}
    child.pop("GH_TOKEN",None)
    child.pop("GITHUB_TOKEN",None)
    with (output/"node.log").open("xb") as log:
        process=(runner or subprocess.run)(
            ["node",str(RUNNER)],env=child,cwd=Path.cwd(),
            stdout=log,stderr=subprocess.STDOUT,check=False,timeout=480)
    write_json(output/"process.json",{
        "exit_code":process.returncode,"node_invocations":1,
        "retry":False},exclusive=True)
    receipt_path=output/"provider/receipt.json"
    need(process.returncode==0 and receipt_path.is_file(),
         "PROVIDER_FAILED_OR_CONSUMPTION_UNCERTAIN_NO_RETRY")
    receipt=read_json(receipt_path)
    need(receipt.get("provider_posts")==1 and
         receipt.get("sdk_interceptions")==1 and
         receipt.get("original_current_model_in_sdk_request") is True and
         receipt.get("model_returned") is True and
         receipt.get("case_sha256")==dm.CASE_SHA256 and
         receipt.get("parent_native_file_sha256")==inp["source_model_sha256"],
         "ORIGINAL_ENGINE_REVIEW_NOT_RETURNED")
    # Re-review the original native *without repairing it manually*.
    native=read_json(output/"provider/native-engine-result.json")
    report=diagnose(native)
    try:
        name,modelica,translation=translate(native)
        translation_status="TRANSLATABLE_G1_ONLY_NOT_SIMULATED"
        (output/"provider/translated.mo").write_text(modelica,encoding="utf-8")
        write_json(output/"provider/translation-report.json",translation,exclusive=True)
    except TranslationBlocked as exc:
        translation_status="BLOCKED_G1_OR_SCOPE"
        name=None
        write_json(output/"provider/translation-report.json",{
            "status":"BLOCKED_G1_OR_SCOPE","reason":str(exc),
            "native_original_unchanged":True},exclusive=True)
    write_json(output/"review-analysis.json",{
        "schema":"arena.coffee-peak.buffalo-review-analysis/1",
        "original_model_revised_by_original_Engine_generate":True,
        "parent_native_file_sha256":inp["source_model_sha256"],
        "revised_native_file_sha256":sha_bytes(
            (output/"provider/native-engine-result.json").read_bytes()),
        "native_semantic_admissible":report["admissible"],
        "native_semantic_diagnostics":report["diagnostics"],
        "translation_status":translation_status,
        "translated_model":name,
        "scientific_gate":"G1_ONLY_NOT_G2_NOT_G3",
        "provider_posts":1,"new_omc":0,"truth_access":False,
        "scientific_lock_created":False
    },exclusive=True)
    return {"status":"ORIGINAL_BUFFALO_OWN_REVIEW_COMPLETED_G1_ONLY",
            "provider_posts":1,"translation_status":translation_status,
            "native_semantic_admissible":report["admissible"],"new_omc":0}

def finalize(output):
    output=Path(output)
    if not output.is_dir():
        return {"status":"NO_ADMISSION"}
    reserved=(output/"attempt.json").exists()
    receipt_path=output/"provider/receipt.json"
    rec=read_json(receipt_path) if receipt_path.exists() else None
    result={
        "schema":"arena.coffee-peak.buffalo-review-final/1",
        "status":"REVIEW_NATIVE_RETURNED_NOT_G2"
          if rec and rec.get("model_returned") is True
          else "ATTEMPT_OR_CONSUMPTION_UNCERTAIN"
          if reserved else "NO_PROVIDER_ATTEMPT",
        "attempt_reserved":reserved,
        "provider_posts_observed":
          rec.get("provider_posts") if rec else None if reserved else 0,
        "may_have_consumed":reserved,"raw_provider_saved":
          bool(rec and rec.get("raw_provider_saved")),
        "original_current_model_in_sdk_request":
          rec.get("original_current_model_in_sdk_request") if rec else False,
        "new_omc":0,"r2_access":False,"truth_access":False,
        "scientific_lock_created":False,"retries":0}
    write_json(output/"final.json",result,exclusive=True)
    return result

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("admit","invoke","finalize"))
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        result=(admission(args.out) if args.action=="admit"
           else invoke(args.out) if args.action=="invoke"
           else finalize(args.out))
        print(json.dumps(result,sort_keys=True))
    except (ArenaError,OSError,ValueError,TypeError,KeyError,
            ImportError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status":"STOPPED_NO_RETRY",
                          "reason":str(exc) if isinstance(exc,ArenaError)
                          else "INTERNAL_ERROR"}),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
