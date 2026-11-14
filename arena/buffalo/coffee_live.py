"""One authorized Buffalo coffee POST; only verified public custody evidence."""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

from arena.common import ArenaError, digest, read_json, write_json
from arena.connections import Secret, public_config
from arena.github import GitHub
from arena.runtime import verify
from arena.coffee_domain import build_case
from arena.coffee_adapters.b import make_payload

REPO = "yudocyudoc/igc-modular"
WORKFLOW = ".github/workflows/coffee-buffalo-live.yml"
SOURCE_WORKFLOW = ".github/workflows/coffee-peak-custody.yml"
PAID_JOB = "Coffee Buffalo one-post live (no OMC/R2)"
PAID_STEP = "One original coffee Engine.generate Cloudflare POST"
LIVE_MODE = "CLOUDFLARE_WORKERS_AI_LIVE_ONE_POST"
R2 = ("CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
      "COFFEE_R2_ACCESS_KEY_ID", "COFFEE_R2_SECRET_ACCESS_KEY",
      "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_B_LIVE_" + code)


def identity(env=None):
    env = os.environ if env is None else env
    need(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
         and env.get("GITHUB_REPOSITORY") == REPO
         and env.get("GITHUB_REF") == "refs/heads/main"
         and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and env.get("COFFEE_B_LIVE_AUTH") == "yes", "MANUAL_FIRST_ATTEMPT_MAIN_REQUIRED")
    sha, run = env.get("GITHUB_SHA", ""), env.get("GITHUB_RUN_ID", "")
    need(re.fullmatch(r"[0-9a-f]{40}", sha) and
         re.fullmatch(r"[1-9][0-9]{0,19}", run), "RUN_SHA_INVALID")
    return sha, int(run)



# Exactly one independently inspected pre-HTTP failure, not a general retry
# exemption. SHA-256 is the *GitHub ZIP artifact bytes* downloaded and audited
# following the 2026-11-14 run. No provider/attempt files were present.
NO_POST_RECOVERY = {
    "run_id": 43533784491,
    "head_sha": "4dd62c8b323096abfa3aca8675a311738cdce34e",
    "job_id": 132257699365,
    "artifact_id": 14088099211,
    "artifact_digest": "sha256:c15251e8a129a93dced1997f9aa29a29e5c6554450e1d24042de34655f643789",
    "source_run_id": 43532737911,
    "source_artifact_id": 14088545399,
    "case_sha256": "sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f",
}


def verify_one_historical_no_post(api, previous, job):
    """Allow only the independently verified pre-attempt credential failure.

    Verify both GitHub job states and the exact archived receipt *bytes* before
    accepting any further authorized workflow dispatch. Never infer zero
    consumption merely from a failed paid step or an absent provider response.
    """
    r = NO_POST_RECOVERY
    need(previous.get("id") == r["run_id"] and
         previous.get("head_sha") == r["head_sha"] and
         previous.get("path") == WORKFLOW and
         previous.get("run_attempt") == 1 and
         previous.get("status") == "completed" and
         previous.get("conclusion") == "failure", "PREVIOUS_NO_POST_RUN_IDENTITY_MISMATCH")
    need(job.get("id") == r["job_id"] and
         job.get("status") == "completed" and
         job.get("conclusion") == "failure", "PREVIOUS_NO_POST_JOB_IDENTITY_MISMATCH")
    steps = job.get("steps")
    need(isinstance(steps, list), "PREVIOUS_NO_POST_STEPS_MISSING")
    expected = {
        "Verify source run, artifact, B0 public identity and prior attempts": "success",
        "Verify Cloudflare AI permission and R2 denial (GET only)": "success",
        "Install pinned Buffalo SDK before the paid request": "success",
        PAID_STEP: "failure",
        "Finalize actual or uncertain provider usage with no retry": "success",
        "Archive request, original native, raw response and usage receipts": "success",
    }
    for name, result in expected.items():
        matches = [step for step in steps if step.get("name") == name]
        need(len(matches) == 1 and matches[0].get("status") == "completed" and
             matches[0].get("conclusion") == result,
             "PREVIOUS_NO_POST_STEP_ATTESTATION_FAILED")
    meta = api.repo("GET", f'/actions/artifacts/{r["artifact_id"]}')
    need(meta.get("id") == r["artifact_id"]
         and meta.get("name") == f'coffee-b-live-{r["run_id"]}'
         and meta.get("expired") is False
         and meta.get("digest") == r["artifact_digest"]
         and meta.get("workflow_run", {}).get("id") == r["run_id"],
         "PREVIOUS_NO_POST_ARTIFACT_ATTESTATION_FAILED")
    archive = api.repo("GET", f'/actions/artifacts/{r["artifact_id"]}/zip',
                       binary=True)
    need(type(archive) is bytes and len(archive) <= 20_000 and
         "sha256:" + hashlib.sha256(archive).hexdigest() == r["artifact_digest"],
         "PREVIOUS_NO_POST_ARCHIVE_HASH_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            need(sorted(bundle.namelist()) == ["admission.json", "final.json", "input.json"],
                 "PREVIOUS_NO_POST_ARCHIVE_FILES_INVALID")
            need(all(not item.is_dir() and item.file_size <= 12_000
                     for item in bundle.infolist()),
                 "PREVIOUS_NO_POST_ARCHIVE_MEMBERS_INVALID")
            admission = json.loads(bundle.read("admission.json"))
            inputs = json.loads(bundle.read("input.json"))
            final = json.loads(bundle.read("final.json"))
    except (ValueError, KeyError, zipfile.BadZipFile, UnicodeError):
        raise ArenaError("COFFEE_B_LIVE_PREVIOUS_NO_POST_ARCHIVE_UNREADABLE") from None
    need(final == {
        "schema": "arena.coffee-b-live-final/1",
        "status": "NO_PROVIDER_ATTEMPT", "attempt_reserved": False,
        "provider_posts_observed": 0, "provider_may_have_consumed": False,
        "provider_usage": None, "raw_provider_saved": False,
        "new_omc": 0, "r2_access": False, "scientific_lock_created": False,
        "retries": 0,
    }, "PREVIOUS_NO_POST_RECEIPT_NOT_ZERO_ATTEMPT")
    need(admission.get("run_id") == r["run_id"] and
         admission.get("sha") == r["head_sha"] and
         admission.get("source_run_id") == r["source_run_id"] and
         admission.get("artifact_id") == r["source_artifact_id"] and
         admission.get("case_sha256") == r["case_sha256"] and
         admission.get("max_provider_posts") == 1 and
         admission.get("scientific_lock_created") is False and
         inputs.get("execution_run_id") == r["run_id"] and
         inputs.get("execution_sha") == r["head_sha"] and
         inputs.get("case_sha256") == admission["case_sha256"] and
         inputs.get("provider_posts") == 0 and
         inputs.get("scientific_lock_created") is False,
         "PREVIOUS_NO_POST_PUBLIC_IDENTITY_MISMATCH")
    return True

def check_history(api, current):
    data = api.repo("GET", "/actions/workflows/coffee-buffalo-live.yml/runs?event=workflow_dispatch&per_page=100")
    count, rows = data.get("total_count"), data.get("workflow_runs")
    need(type(count) is int and 0 <= count <= 100 and
         isinstance(rows, list) and len(rows) == count, "HISTORY_INCOMPLETE")
    cleared = []
    for row in rows:
        rid = row.get("id")
        need(type(rid) is int and rid > 0, "HISTORY_INVALID")
        if rid == current:
            continue
        prev = api.run(rid)
        need(prev.get("id") == rid and prev.get("path") == WORKFLOW
             and prev.get("event") == "workflow_dispatch"
             and prev.get("run_attempt") == 1
             and prev.get("status") == "completed", "PREVIOUS_RUN_UNCERTAIN")
        jobs = api.repo("GET", f"/actions/runs/{rid}/jobs?per_page=100")
        items = jobs.get("jobs")
        need(isinstance(items, list) and len(items) == jobs.get("total_count")
             and len(items) <= 100, "PREVIOUS_JOBS_INCOMPLETE")
        matches = [j for j in items if j.get("name") == PAID_JOB]
        need(len(matches) == 1, "PREVIOUS_PAID_JOB_UNKNOWN")
        job = matches[0]
        if job.get("status") == "completed" and job.get("conclusion") == "skipped":
            cleared.append(rid)
            continue
        if rid == NO_POST_RECOVERY["run_id"]:
            verify_one_historical_no_post(api, prev, job)
            cleared.append(rid)
            continue
        steps = job.get("steps")
        need(job.get("status") == "completed"
             and job.get("conclusion") in ("failure", "cancelled")
             and isinstance(steps, list), "PREVIOUS_PAID_JOB_UNCERTAIN")
        paid = [s for s in steps if s.get("name") == PAID_STEP]
        need(len(paid) == 1 and paid[0].get("status") == "completed"
             and paid[0].get("conclusion") == "skipped", "PREVIOUS_POST_POSSIBLE")
        paid_number = paid[0].get("number")
        need(type(paid_number) is int and any(
            type(s.get("number")) is int and s["number"] < paid_number
            and s.get("status") == "completed"
            and s.get("conclusion") in ("failure", "cancelled")
            for s in steps), "PREVIOUS_PREPAID_FAILURE_NOT_PROVEN")
        cleared.append(rid)
    return cleared


def confirm_source(api, source_id, artifact_id, public_dir, cfg):
    run = api.run(source_id)
    need(run.get("id") == source_id and run.get("path") == SOURCE_WORKFLOW
         and run.get("event") == "workflow_dispatch"
         and run.get("head_branch") == "main"
         and run.get("run_attempt") == 1
         and run.get("status") == "completed"
         and run.get("conclusion") == "success"
         and re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha") or ""),
         "SOURCE_RUN_UNVERIFIED")
    artifact = api.repo("GET", f"/actions/artifacts/{artifact_id}")
    need(artifact.get("id") == artifact_id
         and artifact.get("name") == f"coffee-public-{source_id}"
         and artifact.get("expired") is False
         and artifact.get("workflow_run", {}).get("id") == source_id,
         "SOURCE_ARTIFACT_UNVERIFIED")
    jobs = api.repo("GET", f"/actions/runs/{source_id}/jobs?per_page=100")
    items = jobs.get("jobs")
    need(isinstance(items, list) and len(items) == jobs.get("total_count")
         and any(j.get("name") == "Admit one staged B0 source under private R2 prefix"
                 and j.get("status") == "completed" and j.get("conclusion") == "success"
                 for j in items), "SOURCE_CUSTODY_JOB_UNVERIFIED")
    release = read_json(Path(public_dir) / "release.json")
    need(release.get("run_id") == str(source_id)
         and release.get("frozen_sha") == run["head_sha"]
         and release.get("source_package_sha256") == cfg["source"]["sha256"]
         and release.get("construction_end_exclusive") == cfg["construction_end_min"],
         "SOURCE_RELEASE_MISMATCH")
    return run


def admit(public_dir, source_id, artifact_id, output, *, config_path, assumptions_path, api=None, env=None):
    env = os.environ if env is None else env
    sha, run_id = identity(env)
    need(not any(env.get(k) for k in (*R2, "CLOUDFLARE_API_TOKEN")),
         "CUSTODY_OR_PROVIDER_SECRET_IN_ADMISSION")
    need(type(source_id) is int and source_id > 0 and
         type(artifact_id) is int and artifact_id > 0, "SOURCE_IDS_INVALID")
    output = Path(output)
    need(not output.exists(), "REFUSE_OVERWRITE")
    # Explicit resources: no assumption that site-packages has a checkout's examples/.
    with Path(config_path).open("rb") as f:
        cfg = tomllib.load(f)
    if api is None:
        need(bool(env.get("GH_TOKEN")), "GITHUB_READ_TOKEN_REQUIRED")
        api = GitHub(REPO, Secret(env["GH_TOKEN"], "GITHUB_TOKEN"))
    source = confirm_source(api, source_id, artifact_id, public_dir, cfg)
    cleared = check_history(api, run_id)
    verify(include_history=False)
    # Source release identity has already been validated, so the producer
    # boundary must not compare its historical run ID with this new dispatch.
    case = build_case(public_dir, Path(assumptions_path), environment={})
    need(case["selection"] == cfg["selection"]
         and case["source_package_sha256"] == cfg["source"]["sha256"]
         and case["time"]["construction_end_min"] == cfg["construction_end_min"]
         and case["time"]["window_end_min"] == cfg["window_end_min"],
         "SOURCE_CASE_NOT_PINNED_B0")
    payload = make_payload(case)
    need(payload["mode"] == "OFFLINE_FIXTURE_CONTRACT_ONLY", "UNEXPECTED_BASE_MODE")
    payload = {**payload, "mode": LIVE_MODE, "execution_run_id": run_id,
               "execution_sha": sha, "source_run_id": source_id,
               "source_artifact_id": artifact_id, "max_provider_posts": 1}
    output.mkdir(parents=True, mode=0o700)
    write_json(output / "input.json", payload, exclusive=True)
    write_json(output / "admission.json", {
        "schema": "arena.coffee-b-live-admission/1",
        "run_id": run_id, "sha": sha, "source_run_id": source_id,
        "source_sha": source["head_sha"], "artifact_id": artifact_id,
        "case_sha256": digest(case), "payload_sha256": digest(payload),
        "prior_proven_no_post_runs": cleared, "max_provider_posts": 1,
        "new_omc": 0, "r2_access": False, "scientific_lock_created": False,
    }, exclusive=True)
    return {"status": "PUBLIC_ONLY_ADMITTED_NO_POST", "provider_posts": 0, "new_omc": 0}


def generate(output, *, env=None, runner=None):
    env = dict(os.environ if env is None else env)
    sha, run_id = identity(env)
    need(not any(env.get(k) for k in R2), "CUSTODY_CREDENTIALS_FORBIDDEN")
    # Match the already-proven preflight fallback. The GitHub environment
    # supplies the scoped token but its account variable can be absent.
    # Only the repository-pinned *public* account ID is accepted.
    pinned = public_config()["cloudflare"]["account_id"]
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or pinned
    need(bool(env.get("CLOUDFLARE_API_TOKEN"))
         and re.fullmatch(r"[0-9a-fA-F]{32}", account)
         and account == pinned, "PROVIDER_CREDENTIALS_REQUIRED")
    env["CLOUDFLARE_ACCOUNT_ID"] = account
    output = Path(output).resolve()
    admission, payload = (read_json(output / name)
                          for name in ("admission.json", "input.json"))
    need(admission.get("run_id") == run_id and admission.get("sha") == sha
         and admission.get("payload_sha256") == digest(payload)
         and payload.get("mode") == LIVE_MODE
         and payload.get("execution_run_id") == run_id
         and payload.get("execution_sha") == sha
         and payload.get("case_sha256") == admission.get("case_sha256"),
         "LIVE_ADMISSION_MISMATCH")
    need(not (output / "attempt.json").exists()
         and not (output / "provider").exists(), "ATTEMPT_ALREADY_RESERVED")
    write_json(output / "attempt.json", {
        "schema": "arena.coffee-b-live-attempt/1",
        "state": "RESERVED_BEFORE_HTTP", "run_id": run_id, "sha": sha,
        "case_sha256": payload["case_sha256"], "max_posts": 1,
        "no_retry": True, "uncertain_consumption_is_not_zero": True,
    }, exclusive=True)
    environment = {**env, "COFFEE_B_LIVE_INPUT": str(output / "input.json"),
                   "COFFEE_B_LIVE_OUT": str(output / "provider"),
                   "SDAI_ROOT": str(Path(env["RUNNER_TEMP"]) / "arena-native/upstream/sd-ai"),
                   "BUFFALO_SCRIPTS_ROOT": str(Path(env["RUNNER_TEMP"]) / "arena-native/scripts")}
    environment.pop("GH_TOKEN", None)
    environment.pop("GITHUB_TOKEN", None)
    with (output / "node.log").open("xb") as log:
        process = (runner or subprocess.run)(
            ["node", str(Path(__file__).with_name("coffee_live_runner.mjs"))],
            env=environment, cwd=Path.cwd(), stdout=log, stderr=subprocess.STDOUT,
            check=False, timeout=480)
    write_json(output / "process.json", {"exit_code": process.returncode,
                                         "node_invocations": 1, "retry": False}, exclusive=True)
    path = output / "provider/receipt.json"
    need(process.returncode == 0 and path.is_file(),
         "PROVIDER_FAILED_OR_UNKNOWN_CONSUMPTION_NO_RETRY")
    receipt = read_json(path)
    need(receipt.get("provider_posts") == 1
         and receipt.get("sdk_interceptions") == 1
         and receipt.get("model_returned") is True
         and receipt.get("case_sha256") == admission["case_sha256"],
         "PROVIDER_NATIVE_NOT_ADMISSIBLE_NO_RETRY")
    return {"status": "BUFFALO_NATIVE_RETURNED_NOT_SCIENTIFICALLY_VALIDATED",
            "provider_posts_observed": 1, "new_omc": 0,
            "scientific_lock_created": False}


def finalize(output):
    output = Path(output)
    if not output.is_dir():
        return {"status": "NO_ADMISSION", "provider_posts_observed": 0}
    attempt = (output / "attempt.json").is_file()
    path = output / "provider/receipt.json"
    receipt = read_json(path) if path.is_file() else None
    count = receipt.get("provider_posts") if receipt else None
    result = {
        "schema": "arena.coffee-b-live-final/1",
        "status": "NATIVE_NOT_VALIDATED" if receipt and receipt.get("model_returned") else
                  "ATTEMPT_OR_CONSUMPTION_UNKNOWN" if attempt else "NO_PROVIDER_ATTEMPT",
        "attempt_reserved": attempt,
        "provider_posts_observed": count if type(count) is int else (None if attempt else 0),
        "provider_may_have_consumed": attempt,
        "provider_usage": receipt.get("provider_usage") if receipt else None,
        "raw_provider_saved": bool(receipt and receipt.get("raw_provider_saved")),
        "new_omc": 0, "r2_access": False,
        "scientific_lock_created": False, "retries": 0,
    }
    write_json(output / "final.json", result, exclusive=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("admit", "generate", "finalize"))
    ap.add_argument("--public-dir", type=Path)
    ap.add_argument("--source-run-id", type=int)
    ap.add_argument("--artifact-id", type=int)
    ap.add_argument("--config", type=Path)
    ap.add_argument("--assumptions", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        if args.action == "admit":
            need(args.public_dir and args.source_run_id and args.artifact_id
                 and args.config and args.assumptions, "SOURCE_OR_CONFIG_REQUIRED")
            result = admit(args.public_dir, args.source_run_id, args.artifact_id,
                           args.out, config_path=args.config,
                           assumptions_path=args.assumptions)
        elif args.action == "generate":
            result = generate(args.out)
        else:
            result = finalize(args.out)
        print(json.dumps(result, sort_keys=True))
    except (ArenaError, OSError, KeyError, ValueError, TypeError, subprocess.TimeoutExpired) as err:
        print(json.dumps({"status": "STOPPED_NO_RETRY",
                          "reason": str(err) if isinstance(err, ArenaError) else "INTERNAL_ERROR"}),
              file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
