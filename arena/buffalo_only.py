"""Isolated, one-shot Buffalo reproduction using the CLOSED CT03 public release.

This command must never mutate CT03, select a world, invoke OMC, or call D/M.
The original quantitative Engine.generate and Cloudflare 16K adapter are used unchanged.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .common import ArenaError, read_json, write_json
from .connections import Secret, public_config
from .github import GitHub
from .runtime import module, verify
from .cloud import public_input

SOURCE_RUN = 42455527897
SOURCE_ARTIFACT_ID = 13607441674
SOURCE_SHA = "f6cd90d2356a790f70312aa7c958953ba0b2c522"
SOURCE_ARTIFACT = f"native-public-{SOURCE_RUN}"
WORKFLOW = ".github/workflows/buffalo-only.yml"
REPOSITORY = "yudocyudoc/igc-modular"


def identity():
    if (os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
        or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("BUFFALO_ONLY_AUTH") != "yes"):
        raise ArenaError("Buffalo-only requires one explicit first-attempt dispatch on main.")
    sha = os.environ.get("GITHUB_SHA", "")
    run = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[a-f0-9]{40}", sha) or not re.fullmatch(r"[1-9][0-9]*", run):
        raise ArenaError("Actual frozen SHA and GitHub run ID required.")
    return sha, int(run)


# Only this original Engine.generate step can initiate a paid POST.
PROVIDER_STEP = "One original Engine.generate, Cloudflare adapter 16,000 tokens"
PROVIDER_JOB = "Original Buffalo - archived public CT03 input - 0 OMC"


def _proven_no_post(api, previous):
    """Require affirmative Actions evidence that the paid Node step never started."""
    run_id = previous.get("id")
    if (type(run_id) is not int or run_id <= 0
        or previous.get("status") != "completed"
        or previous.get("run_attempt") != 1
        or previous.get("event") != "workflow_dispatch"
        or previous.get("path") != WORKFLOW):
        return False
    jobs = api.repo("GET", f"/actions/runs/{run_id}/jobs?per_page=100")
    rows = jobs.get("jobs")
    if jobs.get("total_count") != 1 or not isinstance(rows, list) or len(rows) != 1:
        return False
    job = rows[0]
    if (job.get("name") != PROVIDER_JOB or job.get("status") != "completed"
        or job.get("run_attempt", 1) != 1):
        return False
    # Job-level skips run no steps at all (authorized=no, or non-main).
    if job.get("conclusion") == "skipped":
        return True
    if (previous.get("conclusion") not in ("failure", "cancelled")
        or job.get("conclusion") not in ("failure", "cancelled")):
        return False
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    paid = [step for step in steps if step.get("name") == PROVIDER_STEP]
    if len(paid) != 1:
        return False
    paid = paid[0]
    earlier = [step for step in steps if
               type(step.get("number")) is int and
               type(paid.get("number")) is int and
               step["number"] < paid["number"]]
    # A terminal failure/cancellation preceding a skipped/unstarted paid step.
    broke_before = any(step.get("status") == "completed"
                       and step.get("conclusion") in ("failure", "cancelled")
                       for step in earlier)
    if not broke_before:
        return False
    paid_skipped = paid.get("status") == "completed" and paid.get("conclusion") == "skipped"
    paid_unstarted = (paid.get("status") in ("pending", "queued", "waiting")
                      and paid.get("conclusion") is None
                      and not paid.get("started_at"))
    return paid_skipped or paid_unstarted


def eligible_history(api, listing, *, current_id):
    """Allow a new first attempt only when every older dispatch provably spent zero."""
    rows = listing.get("workflow_runs")
    count = listing.get("total_count")
    if (type(count) is not int or count < 0 or count > 100
        or not isinstance(rows, list) or len(rows) != count):
        raise ArenaError("Cannot reconcile all prior buffalo-only dispatches; provider attempt blocked.")
    verified = []
    for record in rows:
        previous_id = record.get("id")
        if type(previous_id) is not int or previous_id <= 0:
            raise ArenaError("Invalid buffalo-only workflow run history; provider attempt blocked.")
        if previous_id == current_id:
            continue
        # Fetch exact run and its jobs; a list summary alone cannot authorize POST.
        detail = api.run(previous_id)
        if detail.get("id") != previous_id or not _proven_no_post(api, detail):
            raise ArenaError("Previous buffalo-only run has a possible or uncertain provider attempt; retry refused.")
        verified.append(previous_id)
    return verified


def admission(workspace, *, api=None):
    """Read-only origin checks. No provider credential is used here."""
    sha, run_id = identity()
    verify()
    if api is None:
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise ArenaError("GitHub Actions read token unavailable.")
        api = GitHub(REPOSITORY, Secret(token, "GITHUB_TOKEN"))
    source = api.run(SOURCE_RUN)
    if (source.get("conclusion") != "success"
        or source.get("event") != "workflow_dispatch"
        or source.get("run_attempt") != 1
        or source.get("head_sha") != SOURCE_SHA
        or source.get("path") != ".github/workflows/arena-run.yml"):
        raise ArenaError("Archived public source does not belong to closed CT03.")
    archive = api.repo("GET", f"/actions/artifacts/{SOURCE_ARTIFACT_ID}")
    if (archive.get("name") != SOURCE_ARTIFACT
        or archive.get("expired") is not False
        or archive.get("workflow_run", {}).get("id") != SOURCE_RUN):
        raise ArenaError("Public release artifact ID, origin or retention has changed.")
    jobs = api.repo("GET", f"/actions/runs/{SOURCE_RUN}/jobs?per_page=100")
    complete = {j.get("name") for j in jobs.get("jobs", [])
                if j.get("status") == "completed" and j.get("conclusion") == "success"}
    if not {"Select and simulate one private world", "D and M originals",
            "Buffalo original and own feedback", "Lock producer predictions",
            "Evaluate after immutable lock"} <= complete:
        raise ArenaError("CT03 source run is not demonstrably closed.")
    previous = api.repo("GET", "/actions/workflows/buffalo-only.yml/runs?event=workflow_dispatch&per_page=100")
    earlier = eligible_history(api, previous, current_id=run_id)
    root = Path(workspace)
    public_input(root)  # validates exactly three public files and four original observations
    path = root / "artifacts/buffalo-only"
    path.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "arena.buffalo-only-admission/1",
               "source_run_id": SOURCE_RUN, "source_artifact_id": SOURCE_ARTIFACT_ID,
               "source_commit_sha": SOURCE_SHA, "execution_run_id": run_id,
               "earlier_verified_no_post_runs": earlier,
               "execution_commit_sha": sha, "provenance": "CLOSED_CT03_PUBLIC_ONLY",
               "new_worlds": 0, "max_provider_posts": 1, "max_omc": 0,
               "scientific_scope": "SEPARATE_DIAGNOSTIC_NOT_CT03_REEVALUATION"}
    write_json(path / "admission.json", receipt, exclusive=True)
    return {"status": "ADMITTED_PUBLIC_ONLY", "source_run": SOURCE_RUN,
            "new_omc": 0, "provider_posts": 0}


def execute_once(workspace):
    """One original Engine.generate, through its original 16K Cloudflare adapter."""
    sha, run_id = identity()
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        raise ArenaError("Existing arena-provider connection is missing.")
    if any(os.environ.get(k) for k in (
        "CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")):
        raise ArenaError("Custody credentials cannot be exposed to buffalo-only.")
    root = Path(workspace).resolve()
    out = root / "artifacts/buffalo-only"
    admission_record = read_json(out / "admission.json")
    if admission_record["execution_run_id"] != run_id or admission_record["execution_commit_sha"] != sha:
        raise ArenaError("Buffalo-only admission identity mismatch.")
    construction = public_input(root)
    world_id = construction["world_public_id"]
    module(root, "ct03_b_visible", "--construction", "artifacts/ct03-public/construction.json",
           "--world", world_id, "--round", "initial",
           "--out", "artifacts/buffalo-only/visible-initial.json")
    visible = out / "visible-initial.json"
    target = out / "initial"
    if target.exists() or (out / "attempt.json").exists():
        raise ArenaError("Provider attempt already reserved; automatic retry refused.")
    write_json(out / "attempt.json", {
        "schema": "arena.buffalo-only-one-post/1", "run_id": run_id,
        "source_run_id": SOURCE_RUN, "round": "initial",
        "max_provider_posts": 1, "new_omc": 0, "state": "ATTEMPT_RESERVED_BEFORE_REQUEST",
        "note": "Failure to receive a response cannot establish zero provider consumption."},
        exclusive=True)
    env = {**os.environ,
           "SDAI_ROOT": str(root / "upstream/sd-ai"),
           "BUFFALO_VISIBLE_INPUT": str(visible),
           "BUFFALO_OUTPUT": str(target),
           "BUFFALO_MODE": "live",
           "BUFFALO_ROUND_KIND": "initial",
           "BUFFALO_LIVE_AUTH": "ONE_UPSTREAM_CALL",
           "BUFFALO_CT03_LIVE_AUTH": "CT03_ONE_ROUND_EXPRESS_AUTH",
           "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID")
               or public_config()["cloudflare"]["account_id"]}
    # The original runner rejects a second outbound POST *before* sending it.
    # This wrapper never calls it twice and never invokes OMC or the CT03 batch.
    with (out / "runner.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(
            ["node", "scripts/arena_b_ct03_native_runner.mjs"],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    write_json(out / "process.json", {"returncode": process.returncode,
              "node_invocations": 1, "new_omc": 0, "retries": 0}, exclusive=True)
    return {"status": "ONE_ORIGINAL_ENGINE_INVOCATION_FINISHED",
            "returncode": process.returncode, "max_provider_posts": 1, "new_omc": 0}


def finalize(workspace):
    """Preserve evidence even if the live runner errors; never infer zero use."""
    root = Path(workspace) / "artifacts/buffalo-only"
    if not root.is_dir():
        return {"status": "NO_PROVIDER_ATTEMPT_DIRECTORY", "new_omc": 0}
    admission_record = read_json(root / "admission.json") if (root / "admission.json").is_file() else None
    attempt = (root / "attempt.json").is_file()
    native = root / "initial"
    receipt = read_json(native / "receipt.json") if (native / "receipt.json").is_file() else None
    if receipt is not None and (receipt.get("provider_calls") not in (0, 1)
                               or receipt.get("mode") != "live"
                               or receipt.get("round_kind") != "initial"):
        raise ArenaError("Unexpected Buffalo attempt scope; preserve all artifacts for review.")
    result = {
        "schema": "arena.buffalo-only-result/1",
        "kind": "INDEPENDENT_DIAGNOSTIC_NOT_CT03",
        "source_run_id": SOURCE_RUN,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "origin_verified": admission_record is not None,
        "new_worlds": 0, "omc_attempts": 0, "max_provider_posts": 1,
        "provider_attempt_reserved": attempt,
        "provider_posts_reported": receipt.get("provider_calls") if receipt else None,
        "provider_attempt_count_complete": receipt is not None,
        "provider_consumption_complete": bool(receipt is not None and (
            receipt.get("provider_calls") == 0 or receipt.get("provider_usage") is not None)),
        "raw_provider_response_archived": (native / "provider-raw.json").is_file(),
        "provider_usage": receipt.get("provider_usage") if receipt else None,
        "provider_finish_reason": receipt.get("provider_finish_reason") if receipt else None,
        "native_model_returned": receipt.get("model_returned") if receipt else None,
        "native_status": receipt.get("status") if receipt else None,
        "http_status": receipt.get("http_status") if receipt else None,
        "runner_error": receipt.get("runner_error") if receipt else None,
        "runner_process": read_json(root / "process.json") if (root / "process.json").is_file() else None,
        "no_retry": True, "ct03_original_untouched": True,
        "note": "Missing receipts/raw responses mean UNKNOWN consumption; CT03 remains closed."
    }
    write_json(root / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("admit", "run", "finalize"))
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "admit":
        result = admission(args.workspace)
    elif args.command == "run":
        result = execute_once(args.workspace)
    else:
        result = finalize(args.workspace)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except ArenaError as e:
        print(json.dumps({"status": "STOPPED", "reason": str(e)}), file=sys.stderr)
        raise SystemExit(2)
