"""Coffee workflow adapter for the existing registry, CLI, RunStore and connections."""
import json
import re
import time

from .common import ArenaError, write_json
from . import runtime

WORKFLOW = "coffee-end-to-end.yml"
RECONCILE_WORKFLOW = "coffee-end-to-end-reconcile.yml"
REPO = "yudocyudoc/igc-modular"


class CoffeeEndToEnd:
    def validate(self, config, path):
        if set(config) != {"id", "protocol", "backend", "budget", "github"}:
            raise ArenaError("Coffee end-to-end requires its explicit GitHub contract.")
        if config["backend"] != "github" or config["budget"] != {
                "omc":1, "provider_posts":0, "workflow":1}:
            raise ArenaError("Coffee lot: GitHub, at most one new OMC, zero provider, one dispatch.")
        gh = config["github"]
        if (set(gh) != {"repository", "ref", "freeze_sha", "poll_seconds"}
                or gh["repository"] != REPO or gh["ref"] != "main"
                or not (gh["freeze_sha"] == "HEAD" or re.fullmatch(r"[0-9a-f]{40}", gh["freeze_sha"]))
                or type(gh["poll_seconds"]) is not int or not 1 <= gh["poll_seconds"] <= 60):
            raise ArenaError("Invalid frozen coffee workflow selection.")

    def verify(self):
        return runtime.verify()

    def backend(self, config, connections):
        from .github import GitHub
        return CoffeeGitHubBackend(GitHub(REPO, connections.resolve("github", "token")))

    def check(self, config, connections):
        api = self.backend(config, connections).api
        sha = api.repo("GET", "/commits/main")["sha"]
        expected = config["github"]["freeze_sha"]
        if expected != "HEAD" and sha != expected:
            raise ArenaError("Main differs from the declared coffee code SHA.")
        workflow = api.repo("GET", "/actions/workflows/"+WORKFLOW)
        if workflow.get("state") != "active":
            raise ArenaError("Coffee end-to-end workflow is not active.")
        return {"status":"CHECKED", "backend":"github", "frozen_code_sha":sha,
                "budget":config["budget"], "upstream":self.verify(),
                "external_compute_started":False}


class CoffeeGitHubBackend:
    def __init__(self, api, *, sleep=time.sleep, timeout_seconds=3600):
        self.api, self.sleep, self.timeout_seconds = api, sleep, timeout_seconds

    def execute(self, store, *, authorize=False):
        if authorize:
            store.authorize()
        stage = store.stage("coffee")
        if stage is None:
            if not store.authorized:
                raise ArenaError("Authorize this complete coffee lot once.")
            sha = self.api.repo("GET", "/commits/main")["sha"]
            expected = store.config["github"]["freeze_sha"]
            if expected != "HEAD" and expected != sha:
                raise ArenaError("Frozen coffee code changed before dispatch.")
            # Reuse the one bootstrap on the exact code commit. Never pick 'latest'.
            workflow = WORKFLOW
            data = self.api.repo("GET", f"/actions/workflows/{WORKFLOW}/runs?head_sha={sha}&per_page=100")
            matches = [r for r in data.get("workflow_runs", []) if r.get("head_sha") == sha
                       and r.get("head_branch") == "main" and r.get("run_attempt") == 1
                       and r.get("event") in ("push", "workflow_dispatch")]
            if data.get("total_count", 101) > 100 or len(matches) > 1:
                raise ArenaError("Coffee run identity is ambiguous; do not dispatch again.")
            if not matches:
                correction = self.api.repo("GET", f"/actions/workflows/{RECONCILE_WORKFLOW}/runs?head_sha={sha}&per_page=100")
                recovered_runs = [r for r in correction.get("workflow_runs", [])
                                  if r.get("head_sha") == sha and r.get("head_branch") == "main"
                                  and r.get("run_attempt") == 1 and r.get("event") in ("push","workflow_dispatch")]
                if correction.get("total_count",101) > 100 or len(recovered_runs) > 1:
                    raise ArenaError("Coffee reconciliation run identity is ambiguous.")
                if recovered_runs:
                    matches, workflow = recovered_runs, RECONCILE_WORKFLOW
            detail = {"frozen_code_sha":sha, "reused_bootstrap":bool(matches), "workflow":workflow}
            if matches:
                run_id = matches[0]["id"]
            else:
                store.attempt("coffee:dispatch", "workflow")
                store.transition("coffee", "DISPATCHING", detail=detail)
                try:
                    run_id = self.api.dispatch(WORKFLOW, "main", {"authorized":"yes"})
                except Exception:
                    store.finish_attempt("coffee:dispatch", successful=False)
                    store.transition("coffee", "DISPATCH_UNCERTAIN", detail=detail)
                    store.status("NEEDS_RECONCILIATION")
                    raise
                store.finish_attempt("coffee:dispatch", successful=True)
            detail["url"] = f"https://github.com/{REPO}/actions/runs/{run_id}"
            store.transition("coffee", "RUNNING", run_id=run_id, detail=detail)
            stage = store.stage("coffee")
        if stage["state"] in ("DISPATCHING", "DISPATCH_UNCERTAIN", "FAILED"):
            raise ArenaError("Existing uncertain or failed coffee run: inspect it; automatic retry refused.")
        detail = json.loads(stage["detail"])
        store.status("RUNNING")
        started = time.monotonic()
        while True:
            run = self.api.run(stage["run_id"])
            if (run.get("head_sha") != detail["frozen_code_sha"] or run.get("head_branch") != "main"
                    or run.get("path") != ".github/workflows/"+detail.get("workflow", WORKFLOW) or run.get("run_attempt") != 1):
                raise ArenaError("Remote coffee run identity changed.")
            if run["status"] == "completed":
                break
            if time.monotonic()-started >= self.timeout_seconds:
                raise ArenaError("Coffee is still running. Resume this ID; do not dispatch again.")
            self.sleep(store.config["github"]["poll_seconds"])
        if run["conclusion"] != "success":
            store.transition("coffee", "FAILED", detail=detail)
            store.status("FAILED")
            raise ArenaError("Coffee run did not complete; preserve its attempts and diagnostics.")
        files = self.api.artifact(stage["run_id"], f"coffee-e2e-result-{stage['run_id']}")
        result = json.loads(files["result.json"])
        execution = result.get("execution", result["native_evaluation"])
        if (result.get("status") != "END_TO_END_COMPLETED_WITH_DECLARED_LIMITS"
                or execution["run_id"] != stage["run_id"]
                or execution["code_sha"] != detail["frozen_code_sha"]):
            raise ArenaError("Coffee result does not match this run.")
        for name, raw in files.items():
            if "/" in name or "\\" in name or name not in {
                    "result.json", "REPORT.md", "ATMS_DECISION.json", "native-scores.csv", "paired-sensitivity.csv", "economics-conditional.csv"}:
                raise ArenaError("Unexpected coffee result artifact member.")
            target = "COFFEE_REPORT.md" if name == "REPORT.md" else name
            (store.root/target).write_bytes(raw)
        store.measure("coffee:omc", "omc", result["new_omc_attempts"], complete=True)
        store.measure("coffee:provider", "provider_posts", result["provider_posts"], complete=True)
        store.transition("coffee", "COMPLETED", detail=detail)
        store.status("COMPLETED")
        result.update(evidence_kind="COFFEE_SYNTHETIC_NATIVE_CONTRAST_AND_CONDITIONAL_DECISION",
                      run=store.report(), score={"candidate_denominator":13})
        write_json(store.root/"result.json", result)
        return result
