"""Chain existing CT03 workflows automatically without merging their data roles."""
import json
import re
import time

from .common import ArenaError, write_json


class GitHubBackend:
    stages = ("intake", "producer", "lock", "evaluate")
    workflows = {"intake": "arena-ct03-public-intake.yml", "producer": "arena-ct03-producer.yml",
                 "lock": "arena-ct03-freeze-predictions.yml", "evaluate": "arena-ct03-evaluate-postlock.yml"}

    def __init__(self, api, *, sleep=None, timeout_seconds=4*60*60):
        self.api = api
        self.sleep = sleep or time.sleep
        self.timeout_seconds = timeout_seconds

    def _inputs(self, stage, store):
        sha = store.config["github"]["freeze_sha"]
        inputs = {"freeze_sha": sha}
        run_id = lambda name: str(store.stage(name)["run_id"])
        if stage == "intake":
            inputs.update(authorized="yes", mode="managed")
        elif stage == "producer":
            inputs.update(authorized="yes", public_release_run_id=run_id("intake"),
                          max_new_omc="19", max_provider_posts="2")
        elif stage == "lock":
            inputs["producer_run_id"] = run_id("producer")
        else:
            inputs.update(authorized="yes", public_release_run_id=run_id("intake"),
                          producer_run_id=run_id("producer"), lock_run_id=run_id("lock"))
        return inputs

    def _verify_run(self, run, stage, store):
        settings = store.config["github"]
        if (run.get("head_sha") != settings["freeze_sha"] or run.get("head_branch") != settings["ref"]
            or run.get("event") != "workflow_dispatch" or run.get("run_attempt") != 1
            or run.get("path") != ".github/workflows/" + self.workflows[stage]):
            raise ArenaError("Remote run identity differs from the approved stage: " + stage)

    def execute(self, store, *, authorize=False):
        if authorize:
            store.authorize()
        previous = [store.stage(stage) for stage in self.stages]
        if not any(previous):
            if not store.authorized:
                raise ArenaError("Live lot not authorized. Check is free; run requires one --authorize.")
            # All read checks and administrative variable writes happen before OMC.
            self.api.inspect(store.config["github"], configure=True)
        elif any(stage and stage["state"] in ("DISPATCHING", "DISPATCH_UNCERTAIN", "FAILED") for stage in previous):
            raise ArenaError("An uncertain or failed remote stage is recorded; automatic retry refused. Inspect its run URL.")
        started = time.monotonic()
        store.status("RUNNING")
        for stage in self.stages:
            current = store.stage(stage)
            if current and current["state"] == "COMPLETED":
                if stage == "producer" and any(not item["complete"] for key,item in store.report()["consumption"].items() if key in ("omc", "provider_posts")):
                    self._usage(store, successful=True)
                continue
            if current is None:
                if stage == "producer":
                    # Replace the manual copy/paste of an intermediate release ID.
                    self.api.variable("arena-ct03-producer", "CT03_APPROVED_RELEASE_RUN_ID",
                                      str(store.stage("intake")["run_id"]))
                    self.api.variable("arena-ct03-producer", "CT03_EXTERNAL_CUSTODIAN_ACK",
                                      "external_private_world_attempted_once")
                store.attempt("dispatch:" + stage, "workflow")
                store.transition(stage, "DISPATCHING")
                try:
                    run_id = self.api.dispatch(self.workflows[stage], store.config["github"]["ref"], self._inputs(stage, store))
                except Exception:
                    store.finish_attempt("dispatch:" + stage, successful=False)
                    store.transition(stage, "DISPATCH_UNCERTAIN")
                    store.status("NEEDS_RECONCILIATION")
                    raise
                store.finish_attempt("dispatch:" + stage, successful=True)
                store.transition(stage, "RUNNING", run_id=run_id,
                                 detail={"url": f"https://github.com/{self.api.repository}/actions/runs/{run_id}"})
                current = store.stage(stage)
            while True:
                record = self.api.run(current["run_id"])
                self._verify_run(record, stage, store)
                if record["status"] == "completed":
                    success = record["conclusion"] == "success"
                    store.transition(stage, "COMPLETED" if success else "FAILED", run_id=current["run_id"],
                                     detail={"url": record.get("html_url"), "conclusion": record["conclusion"]})
                    if stage == "intake" and success:
                        store.measure("world-confirmed", "omc", 1, complete=False)
                    if stage == "producer":
                        self._usage(store, successful=success)
                    if not success:
                        store.status("FAILED")
                        raise ArenaError("Remote stage failed; no automatic re-execution: " + stage)
                    break
                if time.monotonic() - started >= self.timeout_seconds:
                    store.status("WAITING_REMOTE")
                    raise ArenaError("Local wait limit reached. Resume this run to continue monitoring; do not start another lot.")
                self.sleep(store.config["github"]["poll_seconds"])
        return self._result(store)

    def _usage(self, store, *, successful):
        """Count retained attempts, including failed ones; missing evidence stays unknown."""
        run_id = store.stage("producer")["run_id"]
        sha = store.config["github"]["freeze_sha"]
        try:
            dm = self.api.artifact(run_id, f"arena-ct03-dm-raw-one-lot-{run_id}")
            b = self.api.artifact(run_id, f"arena-ct03-b-raw-one-lot-{run_id}")
            suffix = rf" attempted; GitHub run {run_id}; code {sha}"
            def lines(files, basename, pattern, *, required=False):
                selected = [value for name,value in files.items() if name.split("/")[-1] == basename]
                if len(selected) > 1 or (required and len(selected) != 1):
                    raise ArenaError("Ambiguous or missing attempt evidence.")
                if not selected:
                    return 0
                rows = selected[0].decode("utf-8").splitlines()
                if len(rows) != len(set(rows)) or any(not re.fullmatch(pattern + suffix, row) for row in rows):
                    raise ArenaError("Attempt evidence differs from the frozen lot.")
                return len(rows)
            initial = lines(dm, "attempts.log", r"[DM][1-5]", required=True)
            revisions = lines(dm, "m-revision-attempts.log", r"M[0-5]")
            physical = lines(b, "b-physical-attempts.log", r"B-(initial|revision)")
            posts = lines(b, "b-provider-attempts.log", r"B-(initial|revision)", required=successful)
            if initial > 10 or revisions > 6 or physical > 2 or posts > 2:
                raise ArenaError("Observed consumption exceeds the protocol.")
            has = lambda files,name: any(path.split("/")[-1] == name for path in files)
            # An absent log may mean zero attempts OR missing evidence. Without
            # a zero-attempt receipt we retain the distinction rather than infer zero.
            omc_complete = successful and initial == 10 and has(dm, "m-revision-attempts.log") and has(b, "b-physical-attempts.log")
            posts_complete = successful and has(b, "b-provider-attempts.log")
            store.measure("world-confirmed", "omc", 1, complete=omc_complete)
            store.measure("dm-initial", "omc", initial, complete=omc_complete)
            store.measure("m-revisions", "omc", revisions, complete=omc_complete)
            store.measure("b-physical", "omc", physical, complete=omc_complete)
            store.measure("b-provider", "provider_posts", posts, complete=posts_complete)
            if not omc_complete:
                write_json(store.root/"usage-note.json", {"status": "OPTIONAL_ATTEMPT_EVIDENCE_ABSENT",
                           "note": "Absent revision/physical logs do not prove zero attempts. Known attempts are retained; remaining budget is not confirmed."})
        except ArenaError:
            # Do not turn unavailable evidence into zero consumption or erase a failure.
            write_json(store.root/"usage-note.json", {"status": "REMOTE_USAGE_NOT_FULLY_VERIFIED",
                        "action": "Inspect the retained producer attempt artifacts; no retry authorized."})

    def _result(self, store):
        evaluate_id = store.stage("evaluate")["run_id"]
        files = self.api.artifact(evaluate_id, f"arena-ct03-postlock-score-{evaluate_id}")
        if set(files) != {"score-post-lock.json", "archive-record.json"}:
            raise ArenaError("Unexpected files in public post-lock score artifact.")
        score = json.loads(files["score-post-lock.json"])
        ack = json.loads(files["archive-record.json"])
        if (score.get("schema") != "igc-ct03-paired-prospective-evaluation/1.0"
            or score.get("candidate_denominator") != 13 or ack.get("github_run_id") != store.stage("lock")["run_id"]
            or ack.get("frozen_code_sha") != store.config["github"]["freeze_sha"]
            or ack.get("lock_sha256") != score.get("lock_sha256")):
            raise ArenaError("Public score/archive does not match the closed original experiment.")
        write_json(store.root/"results/score-post-lock.json", score)
        write_json(store.root/"results/archive-record.json", ack)
        store.status("COMPLETED")
        result = {"schema": "arena.result/1", "evidence_kind": "REMOTE_ORIGINAL_WORKFLOWS",
                  "scientific_scope": score.get("scientific_scope"), "score": score, "run": store.report()}
        write_json(store.root/"result.json", result)
        return result
