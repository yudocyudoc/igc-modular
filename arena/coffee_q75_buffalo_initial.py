"""Q75 initial Buffalo: exact Q75 common input → ORIGINAL Engine.generate.

Dry-run is source-authenticated and costs zero. A live invoke is only possible
with separate manual first-attempt, main-branch, one-POST authorization.
Never turn B0/R1 into a fake Q75 currentModel. No OMC or private R2 use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .common import ArenaError, digest, read_json, write_json
from .coffee_q75_milk_cycle import prepare as q75_prepare, FIXED_QUESTION
from .coffee_q75_own_policy_cycle import gate
from .connections import public_config
from .runtime import verify
from .buffalo.validation import diagnose
from .coffee_adapters.b_translation import generate as translate, TranslationBlocked

SCHEMA = "arena.coffee.q75-buffalo-original-initial/1"
WORKFLOW = ".github/workflows/coffee-q75-buffalo-initial-manual.yml"
RUNNER = Path(__file__).with_name("coffee_q75_buffalo_initial_runner.mjs")
REPOSITORY = "yudocyudoc/igc-modular"
MODEL = "@cf/zai-org/glm-5.3"  # Nov 20, 2026 replacement; deprecated -flash returned HTTP 410
MAX_POSTS = 1
MAX_TOKENS = 16000


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_Q75_B_INITIAL_" + code)


def make_request(prepared):
    """Create an executable *new initial prompt*, never a prior-model review."""
    common, packets = gate(prepared)
    packet = packets["B"]
    need(packet["status"] == "PREPARED_NOT_DELIVERED_TO_PRODUCER"
         and packet["producer_response"] == "NOT_EXECUTED"
         and packet["operation_known"] == common
         and packet["input_sha256"] == digest({k:v for k,v in packet.items()
                                              if k != "input_sha256"}),
         "B_PACKET_NOT_PREPARED_OR_CHANGED")
    physics = common["physical"]
    need(physics["resource_units_from_hydra"] == {
            "barista": 2, "prep_space": 2, "espresso_group": 3,
            "steam_wand": 1, "pickup_pass": 1}
         and physics["resource_ids_from_dossier"]["steam_wand"] == ["W01"]
         and common["alternatives"] == ["FCFS_READY_ASSUMED",
                                         "PRIORITIZE_MILK_READY"]
         and common["aggregate_beverage_mix_from_public_Q75"]
             ["milk_required_beverages"] == 33
         and common["aggregate_beverage_mix_from_public_Q75"]
             ["no_milk_required_beverages"] == 20
         and common["aggregate_clean_tasks_completed_in_archived_Q75"] == 0
         and physics["clean_after_every_beverage_assumed"] is False,

         "SINGLE_W01_OR_POLICY_NOT_TRANSMITTED")
    common_json = json.dumps(common, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False)
    prompt = ("Generate YOUR FIRST quantitative stock-flow model of the known "
              "coffee process. Compare only FCFS_READY_ASSUMED versus "
              "PRIORITIZE_MILK_READY under the same Q75 construction. "
              "Both policies are explicitly defined below. This is a NEW "
              "initial generation, not a revision of the old B0/R1 models. "
              "Preserve the explicit single steam wand W01, two shared "
              "baristas, two preparation stations, three espresso groups, "
              "one pickup pass, operator windows, stage precedence and "
              "nonpreemptive runnable-task fallback. Of the 53 synthetic "
              "beverages, 33 require milk on W01 and 20 do not. "
              "The base Q75 scenario DOES NOT clean the espresso group "
              "after every beverage; if cleaning were enabled, each clean "
              "would occupy one barista AND the espresso group before release. "
              "A milk stage starts only "
              "with a free qualified barista AND a free steam wand. If W01 is "
              "busy, another executable task may start on the second barista. "
              "Do not invent a second wand or idle the barista solely because "
              "milk is blocked. Do not invent individual paid arrival times, "
              "recipes, interventions or empirical service measurements. "
              "Q75 aggregate totals alone cannot determine per-order P90. "
              "If the original stock-flow language cannot encode the task "
              "selector or per-order latency, explicitly expose that limitation; "
              "never return a numerical P90 or a zero policy effect without "
              "a representable comparison. Do not claim to run OpenModelica. "
              "Do not use any other model's answer or the Hydra policy effect.\n"
              "KNOWN CASE AND EXACT POLICY SEMANTICS:\n" + common_json)
    need("-3.837" not in prompt and "44234407455" not in prompt
         and "currentModel" not in prompt
         and "shared barista/espresso coupling" not in prompt,
         "RIVAL_DELTA_OR_HISTORICAL_B0_PROMPT_LEAK")
    background = {"construction": common,
                  "observability": {
                      "allowed": "visible synthetic construction and resources",
                      "individual_q75_payments": "NOT_PUBLIC_IN_AGGREGATE",
                      "per_order_handoff_times": "NOT_PROVIDED",
                      "real_shop_policy": "NOT_OBSERVED",
                      "90s_extraction": "ASSUMED_NOT_CALIBRATED"},
                  "method": "original Buffalo quantitative Engine.generate",
                  "own_feedback": None}
    request = {
        "schema": SCHEMA,
        "method": "UB-IAD/sd-ai::Engine.generate",
        "round_kind": "initial",
        "parent_model": None,
        "original_B0_R1_currentModel_compatible": False,
        "original_B0_R1_reused": False,
        "case": "Q75_CONSTRUCTION_SYNTHETIC_ONLY",
        "case_source_sha256": common["case_day_sha256"],
        "common_evidence_sha256": digest(common),
        "original_B_prepared_input_sha256": packet["input_sha256"],
        "question": FIXED_QUESTION,
        "prompt": prompt,
        "problemStatement": FIXED_QUESTION,
        "backgroundKnowledge": json.dumps(background, sort_keys=True,
                                          ensure_ascii=False, allow_nan=False),
        "max_provider_posts": 1,
        "max_completion_tokens": MAX_TOKENS,
        "original_engine_effective_option_profile": {
            "supportsArrays":False,"supportsModules":False,
            "supportsSubTypes":False,"mentorMode":False,
            "maxTokens":MAX_TOKENS,
            "scope":"ORIGINAL_BUFFALO_HISTORICAL_SCALAR_NO_NATIVE_QUEUE_SUBTYPES",
            "not_entire_buffalo_representational_capability":True,
        },
        "model": MODEL,
        "new_omc": 0,
        "new_private_R2_gets": 0,
        "holdout_access": False,
        "rival_model_or_Hydra_result_sent": False,
        "not_a_Q75_P90_prediction": True,
        "provider_status": "NOT_SENT",
        "no_automatic_retry": True,
    }
    request["request_sha256"] = digest(request)
    return request


def dry_run(zip_dir, dossier, out):
    out = Path(out)
    need(not out.exists(), "NO_OVERWRITE")
    original = verify(include_history=False)
    need(original["unchanged"] is True, "ORIGINAL_ENGINE_MANIFEST_CHANGED")
    prepared = q75_prepare(zip_dir, dossier)
    request = make_request(prepared)
    out.mkdir(parents=True)
    write_json(out/"request.json", request, exclusive=True)
    write_json(out/"dry-run.json", {
        "schema": "arena.coffee.q75-buffalo-initial-dry-run/1",
        "status": "READY_BUT_NOT_AUTHORIZED_OR_SENT",
        "Q75_request_sha256": request["request_sha256"],
        "source_verified": True,
        "engine_original": "UB-IAD/sd-ai::Engine.generate",
        "B0_parent_not_reused": True,
        "only_existing_public_aggregates": True,
        "outbound_provider_posts": 0,
        "new_omc": 0,
        "new_private_R2_gets": 0,
        "separate_approval_needed": True,
        "cost_ceiling": {"posts": 1, "completion_tokens_per_request": MAX_TOKENS,
                         "monetary_price": "UNKNOWN_PROVIDER_BILLING_NOT_A_FIXED_MXN_QUOTE"},
    }, exclusive=True)
    return request


def provider_ai_only_preflight(env=None, opener=None):
    """Check Workers AI reachability without any R2 operation.

    This workflow requires zero R2 access but cannot certify the R2 *scope*
    of a pre-existing broad token. The old 403-only R2 GET assertion blocked
    a proved no-POST run; no token is silently represented as least-privilege.
    """
    import urllib.error
    import urllib.request
    env = dict(os.environ if env is None else env)
    account = public_config()["cloudflare"]["account_id"]
    supplied = env.get("CLOUDFLARE_ACCOUNT_ID")
    token = env.get("CLOUDFLARE_API_TOKEN", "")
    need(not supplied or supplied == account, "PREFLIGHT_WRONG_ACCOUNT")
    need(bool(token), "PREFLIGHT_TOKEN_MISSING")
    # One exact-name catalog lookup. A generic "some AI model is available"
    # preflight missed the provider model's scheduled 2026-11-20 removal.
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/" + account +
        "/ai/models/search?search=glm-5.3&include_deprecated=false&per_page=25",
        headers={"Authorization": "Bearer " + token},
        method="GET")
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(req, timeout=30) as response:
            status = response.status
            raw = response.read(150_001)
        need(len(raw) <= 150_000, "PREFLIGHT_RESPONSE_TOO_LARGE")
        payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ArenaError("COFFEE_Q75_B_INITIAL_WORKERS_AI_METADATA_HTTP_" +
                         str(exc.code)) from None
    except (OSError, ValueError):
        raise ArenaError("COFFEE_Q75_B_INITIAL_WORKERS_AI_METADATA_UNAVAILABLE") from None
    need(status == 200 and payload.get("success") is True
         and type(payload.get("result")) is list,
         "PREFLIGHT_WORKERS_AI_METADATA_NOT_AVAILABLE")
    exact = [m for m in payload["result"] if
             isinstance(m, dict) and m.get("name") == MODEL]
    need(len(exact) == 1,
         "PREFLIGHT_TARGET_MODEL_NOT_IN_LIVE_CATALOG")
    return {
        "workers_ai_metadata": "AVAILABLE",
        "provider_model": MODEL,
        "target_present_in_catalog": True,
        "workers_ai_metadata_requests": 1,
        "r2_requests": 0,
        "private_R2_reads": 0,
        "token_r2_permission_scope": "NOT_VERIFIED_DO_NOT_CLAIM_LEAST_PRIVILEGE",
        "provider_posts": 0,
        "inference_write_permission": "NOT_TESTED_UNTIL_AUTHORIZED_POST",
    }


def manual_identity(env):
    need(env.get("GITHUB_REPOSITORY") == REPOSITORY
         and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
         and env.get("GITHUB_REF") == "refs/heads/main"
         and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and env.get("COFFEE_Q75_B_INITIAL_AUTH") == "yes"
         and env.get("GITHUB_WORKFLOW_REF", "").endswith(
             WORKFLOW + "@refs/heads/main")
         and re.fullmatch(r"[a-f0-9]{40}", env.get("GITHUB_SHA", ""))
         and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")),
         "EXPLICIT_FIRST_MAIN_MANUAL_AUTHORIZATION_REQUIRED")
    for key in ("CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GH_TOKEN"):
        need(not env.get(key), "UNEXPECTED_PRIVATE_CUSTODY_OR_GITHUB_TOKEN")
    return env["GITHUB_SHA"], int(env["GITHUB_RUN_ID"])


def request_file_sha256(path):
    """Hash exactly the persisted input bytes, independently of the JSON digest."""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reserve(out, env=None):
    """Reserve a single attempt before any Node call; never retry."""
    env = dict(os.environ if env is None else env)
    sha, run = manual_identity(env)
    out = Path(out)
    request = read_json(out/"request.json")
    need(request["schema"] == SCHEMA
         and request["round_kind"] == "initial"
         and request["parent_model"] is None
         and request["request_sha256"] == digest({k:v for k,v in request.items()
                                                if k != "request_sha256"})
         and read_json(out/"dry-run.json")["Q75_request_sha256"]
             == request["request_sha256"]
         and not (out/"attempt.json").exists(), "MISSING_OR_TAMPERED_DRY_RUN")
    write_json(out/"attempt.json", {
        "status": "RESERVED_BEFORE_HTTP",
        "run_id": run, "run_sha": sha,
        "original_request_sha256": request["request_sha256"],
        "request_file_sha256":request_file_sha256(out/"request.json"),
        "posts_max": 1, "no_retry": True,
        "provider_consumption_after_failure": "UNKNOWN_NOT_ZERO",
    }, exclusive=True)
    return {"status": "ONE_INITIAL_POST_ATTEMPT_RESERVED", "run_id": run}


def invoke(out, env=None):
    env = dict(os.environ if env is None else env)
    sha, run = manual_identity({k:v for k,v in env.items()
                               if k not in ("CLOUDFLARE_API_TOKEN",
                                            "CLOUDFLARE_ACCOUNT_ID")})
    need(env.get("CLOUDFLARE_API_TOKEN"), "CLOUDFLARE_PROVIDER_TOKEN_REQUIRED")
    account = public_config()["cloudflare"]["account_id"]
    need(env.get("CLOUDFLARE_ACCOUNT_ID") in (None, "", account),
         "WRONG_PROVIDER_ACCOUNT")
    out = Path(out)
    attempt = read_json(out/"attempt.json")
    request = read_json(out/"request.json")
    need(attempt["status"] == "RESERVED_BEFORE_HTTP"
         and attempt["run_id"] == run and attempt["run_sha"] == sha
         and attempt["original_request_sha256"] == request["request_sha256"]
         and attempt["request_file_sha256"] ==
             request_file_sha256(out/"request.json")
         and request["request_sha256"] ==
             digest({k:v for k,v in request.items() if k != "request_sha256"})
         and read_json(out/"dry-run.json")["Q75_request_sha256"] ==
             request["request_sha256"]
         and not (out/"provider").exists()
         and not (out/"process.json").exists(),
         "ATTEMPT_ALREADY_SPENT_OR_INPUT_BYTES_CHANGED")
    child = dict(env)
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "CT03_R2_ACCESS_KEY_ID",
                "CT03_R2_SECRET_ACCESS_KEY"):
        child.pop(key, None)
    child.update({
        "CLOUDFLARE_ACCOUNT_ID": account,
        "COFFEE_Q75_B_INPUT": str((out/"request.json").resolve()),
        "COFFEE_Q75_B_ATTEMPT": str((out/"attempt.json").resolve()),
        "COFFEE_Q75_B_OUT": str((out/"provider").resolve()),
        "SDAI_ROOT": str(Path(env["RUNNER_TEMP"])/"arena-native/upstream/sd-ai"),
        "BUFFALO_SCRIPTS_ROOT":str(Path(env["RUNNER_TEMP"])/"arena-native/scripts"),
    })
    with (out/"runner.log").open("xb") as log:
        p = subprocess.run(["node",str(RUNNER)], cwd=Path.cwd(), env=child,
                           stdout=log, stderr=subprocess.STDOUT, timeout=480,
                           check=False)
    write_json(out/"process.json", {
        "returncode": p.returncode,"node_invocations": 1,"retry": False},
        exclusive=True)
    need(p.returncode == 0, "PROVIDER_RESULT_INVALID_OR_CONSUMPTION_UNKNOWN")
    return {"status":"INITIAL_ORIGINAL_ENGINE_CALL_FINISHED", "run_id":run}


def finalize(out):
    out = Path(out)
    if not out.exists():
        return {"status":"NO_REQUEST_DIRECTORY"}
    attempt = (out/"attempt.json").exists()
    receipt_path = out/"provider/receipt.json"
    receipt = read_json(receipt_path) if receipt_path.exists() else None
    analysis={
        "schema":"arena.coffee.q75-buffalo-original-initial-analysis/1",
        "attempt_reserved": attempt,
        "actual_or_possible_provider_post": bool(attempt),
        "provider_posts_reported": receipt.get("provider_posts") if receipt else None,
        "raw_provider_archived": (out/"provider/provider-raw.json").is_file(),
        "provider_usage": receipt.get("provider_usage") if receipt else None,
        "new_omc":0,"new_private_R2_gets":0,"no_retry":True,
        "G1_report": None,
        "policy_effect_P90_status":"NOT_EVALUATED_NO_ORDER_LEVEL_EXECUTION",
    }
    native_path=out/"provider/native-engine-result.json"
    if native_path.is_file() and receipt and receipt.get("model_returned"):
        native=read_json(native_path)
        g1=diagnose(native)
        analysis["G1_report"]={"admissible":g1["admissible"],
                               "diagnostics":g1["diagnostics"]}
        try:
            _,modelica,translator=translate(native)
            (out/"provider/BuffaloQ75Initial.mo").write_text(modelica, encoding="utf8")
            analysis["translation"]={"status":"G1_TRANSLATED_NOT_SIMULATED",
                                      "translation_report":translator}
        except TranslationBlocked as exc:
            analysis["translation"]={"status":"BLOCKED_G1_OR_NATIVE_SCHEMA",
                                      "reason":str(exc)}
    write_json(out/"analysis.json", analysis)
    return analysis


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("mode", choices=("dry-run", "reserve", "invoke", "finalize"))
    ap.add_argument("--public-zips",type=Path)
    ap.add_argument("--dossier",type=Path)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    if args.mode == "dry-run":
        need(args.public_zips and args.dossier, "AUTHENTIC_PUBLIC_SOURCES_REQUIRED")
        result=dry_run(args.public_zips,args.dossier,args.out)
        print("Q75_BUFFALO_INITIAL_READY_NOT_SENT",result["request_sha256"])
    elif args.mode == "reserve":
        print(json.dumps(reserve(args.out)))
    elif args.mode == "invoke":
        print(json.dumps(invoke(args.out)))
    else:
        print(json.dumps(finalize(args.out)))

if __name__ == "__main__":
    main()
