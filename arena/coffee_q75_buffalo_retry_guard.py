"""Q75 one-shot replay gate: allow ONLY a proven pre-reservation failed run.

No R2 access, Modelica, provider POST or model response in this module.
The archived run is checked against GitHub's own job steps AND artifact
contents. Unknown prior dispatches always block rather than risk duplication.
"""
from __future__ import annotations

from io import BytesIO
import json
import os
from zipfile import ZipFile
from urllib.request import Request, urlopen

from .common import ArenaError

REPO = "yudocyudoc/igc-modular"
WORKFLOW = "coffee-q75-buffalo-initial-manual.yml"
SAFE_PRIOR_RUN = 44670461871
SAFE_PRIOR_ARTIFACT = 14600040802
SAFE_REQUEST = "sha256:127d586b5420d1ebe744a4a67e6024f0c7ef3e0552888ded4ddf7bc8cbbecc2b"
LIVE_JOB = "First original Buffalo Engine.generate on Q75, one paid POST maximum"
PREFLIGHT_STEP = "Provider API GET permission check, no POST"
RESERVE_STEP = "Reserve exactly one initial provider attempt, no credentials in shell"
INVOKE_STEP = "One real ORIGINAL Engine.generate initial — one Cloudflare POST maximum"


def need(condition, code):
    if not condition:
        raise ArenaError("COFFEE_Q75_B_RETRY_" + code)


def attest_prior_run(run, jobs, artifacts, archive):
    """A positive proof of zero POST. Never infer no-spend from failure alone."""
    need(run["id"] == SAFE_PRIOR_RUN and run["event"] == "workflow_dispatch"
         and run["head_branch"] == "main" and run["run_attempt"] == 1
         and run["status"] == "completed" and run["conclusion"] == "failure"
         and run["name"].startswith("Coffee Q75"),
         "PRIOR_RUN_IDENTITY_CHANGED")
    paid = [j for j in jobs if j["name"] == LIVE_JOB]
    offline = [j for j in jobs if j["name"] == "offline-contracts"]
    need(len(jobs) == 2 and len(paid) == 1 and len(offline) == 1
         and paid[0]["conclusion"] == "failure"
         and offline[0]["conclusion"] == "success",
         "PRIOR_RUN_JOB_SET_CHANGED")
    steps = {s["name"]: s["conclusion"] for s in paid[0]["steps"]}
    need(steps.get(PREFLIGHT_STEP) == "failure"
         and steps.get(RESERVE_STEP) == "skipped"
         and steps.get(INVOKE_STEP) == "skipped"
         and steps.get("Verify original manifests and write new Q75 initial input, NO provider yet") == "success",
         "PRIOR_RUN_COULD_HAVE_POSTED")
    expected = "coffee-q75-original-b-initial-" + str(SAFE_PRIOR_RUN)
    matches = [a for a in artifacts if a["id"] == SAFE_PRIOR_ARTIFACT
               and a["name"] == expected and not a.get("expired", False)
               and a.get("workflow_run", {}).get("id", SAFE_PRIOR_RUN) == SAFE_PRIOR_RUN]
    need(len(matches) == 1, "PRIOR_ARTIFACT_NOT_PINNED")
    try:
        with ZipFile(BytesIO(archive)) as z:
            need(set(z.namelist()) == {"analysis.json", "dry-run.json", "request.json"},
                 "PRIOR_ARTIFACT_CONTAINS_ATTEMPT")
            analysis = json.loads(z.read("analysis.json"))
            dry = json.loads(z.read("dry-run.json"))
            request = json.loads(z.read("request.json"))
    except (OSError, ValueError, KeyError) as exc:
        raise ArenaError("COFFEE_Q75_B_RETRY_ARTIFACT_INVALID") from None
    need(analysis["schema"] == "arena.coffee.q75-buffalo-original-initial-analysis/1"
         and analysis["attempt_reserved"] is False
         and analysis["actual_or_possible_provider_post"] is False
         and analysis["provider_posts_reported"] is None
         and analysis["raw_provider_archived"] is False
         and analysis["new_omc"] == 0
         and analysis["new_private_R2_gets"] == 0
         and dry["outbound_provider_posts"] == 0
         and dry["Q75_request_sha256"] == SAFE_REQUEST
         and request["request_sha256"] == SAFE_REQUEST
         and request["provider_status"] == "NOT_SENT",
         "PRIOR_NO_SPEND_PROOF_FAILED")
    return {"prior_run": SAFE_PRIOR_RUN, "prior_attempt_reserved": False,
            "prior_possible_provider_posts": 0, "prior_artifact": SAFE_PRIOR_ARTIFACT}


def verify_dispatch_history(history, current_id, get_jobs, get_artifacts, get_archive):
    rows = history.get("workflow_runs", [])
    need(history.get("total_count") == len(rows)
         and 1 <= len(rows) <= 100
         and len({r["id"] for r in rows}) == len(rows),
         "HISTORY_INCOMPLETE")
    current = [r for r in rows if r["id"] == current_id]
    need(len(current) == 1 and current[0]["event"] == "workflow_dispatch"
         and current[0]["head_branch"] == "main"
         and current[0]["run_attempt"] == 1,
         "CURRENT_RUN_MISSING_OR_WRONG")
    previous = [r for r in rows if r["id"] != current_id]
    need(len(previous) <= 1, "OTHER_POSSIBLE_PROVIDER_ATTEMPT")
    if previous:
        prior = previous[0]
        need(prior["id"] == SAFE_PRIOR_RUN, "UNRECONCILED_PREVIOUS_DISPATCH")
        proof = attest_prior_run(prior, get_jobs(SAFE_PRIOR_RUN),
                                 get_artifacts(SAFE_PRIOR_RUN),
                                 get_archive(SAFE_PRIOR_ARTIFACT))
    else:
        proof = {"prior_run": None, "prior_possible_provider_posts": 0}
    return {"status": "PRIOR_POSTS_ATTESTED_ZERO",
            "new_attempt_may_reserve_max_posts": 1, **proof}


def main():
    import subprocess
    import sys
    token = os.environ.get("GH_TOKEN")
    verify_only = sys.argv[1:] == ["--verify-historical"]
    need(bool(token) and os.environ.get("GITHUB_REPOSITORY") == REPO,
         "GH_READ_PERMISSION_REQUIRED")
    if not verify_only:
        need(not sys.argv[1:] and
             os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
             and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
             and os.environ.get("GITHUB_REF") == "refs/heads/main"
             and os.environ.get("GITHUB_RUN_ID","").isdigit(),
             "GH_MANUAL_IDENTITY_REQUIRED")
    current = int(os.environ["GITHUB_RUN_ID"]) if not verify_only else None

    def api(path):
        return json.loads(subprocess.check_output(["gh", "api", path], text=True))

    def artifact_bytes(artifact_id):
        url = ("https://api.github.com/repos/" + REPO +
               "/actions/artifacts/" + str(artifact_id) + "/zip")
        req = Request(url, headers={"Authorization": "Bearer " + token,
                                    "Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2022-11-28"})
        with urlopen(req, timeout=45) as response:
            data = response.read(2_000_001)
        need(len(data) <= 2_000_000, "ARTIFACT_TOO_LARGE")
        return data

    url = "repos/" + REPO + "/actions/workflows/" + WORKFLOW + "/runs"
    history = api(url + "?event=workflow_dispatch&per_page=100")
    def jobs(run_id):
        page = api("repos/" + REPO + "/actions/runs/" + str(run_id) +
                   "/jobs?per_page=100")
        need(page.get("total_count") == len(page.get("jobs", [])),
             "PRIOR_JOB_PAGINATION_INCOMPLETE")
        return page["jobs"]
    def artifacts(run_id):
        page = api("repos/" + REPO + "/actions/runs/" + str(run_id) +
                   "/artifacts?per_page=100")
        need(page.get("total_count") == len(page.get("artifacts", [])),
             "PRIOR_ARTIFACT_PAGINATION_INCOMPLETE")
        return page["artifacts"]
    if verify_only:
        prior = [row for row in history.get("workflow_runs", [])
                 if row.get("id") == SAFE_PRIOR_RUN]
        need(len(prior) == 1, "PINNED_HISTORICAL_RUN_NOT_IN_HISTORY")
        proof = attest_prior_run(prior[0], jobs(SAFE_PRIOR_RUN),
                                 artifacts(SAFE_PRIOR_RUN),
                                 artifact_bytes(SAFE_PRIOR_ARTIFACT))
        proof["status"] = "HISTORICAL_NO_POST_ARTIFACT_VERIFIED"
    else:
        proof = verify_dispatch_history(
            history, current, jobs, artifacts, artifact_bytes)
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
