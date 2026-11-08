"""No-spend regressions for the isolated one-post Buffalo diagnostic."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena import buffalo_only
from arena.common import ArenaError, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


class StubGitHub:
    def __init__(self, *, previous=None, details=None, prior_jobs=None, count=None):
        self.previous = previous or []
        self.details = details or {}
        self.prior_jobs = prior_jobs or {}
        self.count = count

    def run(self, run_id):
        if run_id == buffalo_only.SOURCE_RUN:
            return {"conclusion": "success", "event": "workflow_dispatch",
                    "run_attempt": 1, "head_sha": buffalo_only.SOURCE_SHA,
                    "path": ".github/workflows/arena-run.yml"}
        return self.details[run_id]

    def repo(self, method, path):
        assert method == "GET"
        if path == f"/actions/artifacts/{buffalo_only.SOURCE_ARTIFACT_ID}":
            return {"name": buffalo_only.SOURCE_ARTIFACT, "expired": False,
                    "workflow_run": {"id": buffalo_only.SOURCE_RUN}}
        if path.startswith(f"/actions/runs/{buffalo_only.SOURCE_RUN}/jobs?"):
            return {"jobs": [{"name": name, "conclusion": "success", "status": "completed"}
                             for name in ("Select and simulate one private world",
                                          "D and M originals", "Buffalo original and own feedback",
                                          "Lock producer predictions", "Evaluate after immutable lock")]}
        if path.startswith("/actions/workflows/buffalo-only.yml/runs?"):
            return {"total_count": self.count if self.count is not None else len(self.previous),
                    "workflow_runs": [{"id": run} for run in self.previous]}
        for run_id, value in self.prior_jobs.items():
            if path == f"/actions/runs/{run_id}/jobs?per_page=100":
                return value
        raise AssertionError(path)


def prior_run(*, id=123, conclusion="success", status="completed",
              run_attempt=1, path=buffalo_only.WORKFLOW):
    return {"id": id, "status": status, "conclusion": conclusion,
            "run_attempt": run_attempt, "event": "workflow_dispatch", "path": path}


def prior_job(*, conclusion="success", paid_conclusion="success",
              paid_status="completed", paid_started="2026-11-08T00:00:00Z",
              preceding_failure=False, steps_present=True):
    steps = [
        {"name": "Install pinned original quantitative engine dependencies",
         "number": 5, "status": "completed",
         "conclusion": "failure" if preceding_failure else "success"},
        {"name": buffalo_only.PROVIDER_STEP, "number": 6,
         "status": paid_status, "conclusion": paid_conclusion,
         "started_at": paid_started},
    ]
    result = {"name": buffalo_only.PROVIDER_JOB,
              "status": "completed", "conclusion": conclusion, "run_attempt": 1}
    if steps_present:
        result["steps"] = steps
    return {"total_count": 1, "jobs": [result]}




class BuffaloOnlyTests(unittest.TestCase):
    def identity(self):
        return {"GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_REPOSITORY": buffalo_only.REPOSITORY,
                "GITHUB_SHA": "f" * 40,
                "GITHUB_RUN_ID": "99999889",
                "BUFFALO_ONLY_AUTH": "yes"}

    def test_admission_only_accepts_archived_public_closed_ct03(self):
        with TemporaryDirectory() as d:
            with (patch.dict(os.environ, self.identity()),
                  patch.object(buffalo_only, "verify"),
                  patch.object(buffalo_only, "public_input", return_value={})):
                outcome = buffalo_only.admission(d, api=StubGitHub())
                self.assertEqual(outcome["new_omc"], 0)
                self.assertEqual(outcome["provider_posts"], 0)
                proof = read_json(Path(d) / "artifacts/buffalo-only/admission.json")
                self.assertEqual(proof["source_artifact_id"], 13607441674)
                self.assertEqual(proof["scientific_scope"],
                                 "SEPARATE_DIAGNOSTIC_NOT_CT03_REEVALUATION")
                with self.assertRaises(FileExistsError):
                    buffalo_only.admission(d, api=StubGitHub())

    def check_prior(self, run, job, *, permitted):
        with TemporaryDirectory() as d:
            api = StubGitHub(previous=[123], details={123: run},
                             prior_jobs={123: job})
            with (patch.dict(os.environ, self.identity()),
                  patch.object(buffalo_only, "verify"),
                  patch.object(buffalo_only, "public_input", return_value={})):
                if permitted:
                    result = buffalo_only.admission(d, api=api)
                    self.assertEqual(result["provider_posts"], 0)
                    record = read_json(Path(d) / "artifacts/buffalo-only/admission.json")
                    self.assertEqual(record["earlier_verified_no_post_runs"], [123])
                else:
                    with self.assertRaisesRegex(ArenaError, "possible or uncertain"):
                        buffalo_only.admission(d, api=api)
                    self.assertFalse((Path(d) / "artifacts/buffalo-only").exists())

    def test_authorized_no_job_skipped_does_not_spend_right_to_execute(self):
        self.check_prior(prior_run(conclusion="success"),
                         prior_job(conclusion="skipped", steps_present=False),
                         permitted=True)

    def test_failed_npm_before_node_does_not_spend_right_to_execute(self):
        self.check_prior(prior_run(conclusion="failure"),
                         prior_job(conclusion="failure", preceding_failure=True,
                                   paid_conclusion="skipped", paid_started=None),
                         permitted=True)

    def test_cancelled_unequivocally_before_node_does_not_spend(self):
        self.check_prior(prior_run(conclusion="cancelled"),
                         prior_job(conclusion="cancelled", preceding_failure=True,
                                   paid_conclusion=None, paid_status="pending",
                                   paid_started=None),
                         permitted=True)

    def test_provider_step_started_or_completed_never_allows_another_post(self):
        for paid_conclusion, status, started in (
                ("success", "completed", "2026-11-08T00:00:00Z"),
                ("failure", "completed", "2026-11-08T00:00:00Z"),
                (None, "in_progress", "2026-11-08T00:00:00Z")):
            with self.subTest(paid=paid_conclusion):
                self.check_prior(prior_run(conclusion="failure"),
                                 prior_job(conclusion="failure", preceding_failure=True,
                                           paid_conclusion=paid_conclusion,
                                           paid_status=status, paid_started=started),
                                 permitted=False)

    def test_run_failure_is_not_itself_proof_of_no_provider_post(self):
        self.check_prior(prior_run(conclusion="failure"),
                         prior_job(conclusion="failure", preceding_failure=False,
                                   paid_conclusion="skipped", paid_started=None),
                         permitted=False)

    def test_unknown_in_progress_or_retried_history_fails_closed(self):
        for history in (prior_run(status="in_progress", conclusion=None),
                        prior_run(run_attempt=2),
                        prior_run(conclusion="failure", path=".github/workflows/other.yml")):
            with self.subTest(history=history):
                self.check_prior(history, prior_job(conclusion="skipped"),
                                 permitted=False)

    def test_missing_job_steps_is_not_proof_of_no_attempt(self):
        self.check_prior(prior_run(conclusion="failure"),
                         prior_job(conclusion="failure", steps_present=False),
                         permitted=False)

    def test_incomplete_paginated_history_fails_closed(self):
        with TemporaryDirectory() as d:
            api = StubGitHub(previous=[], count=101)
            with (patch.dict(os.environ, self.identity()),
                  patch.object(buffalo_only, "verify"),
                  patch.object(buffalo_only, "public_input", return_value={})):
                with self.assertRaisesRegex(ArenaError, "reconcile all prior"):
                    buffalo_only.admission(d, api=api)

    def test_rerun_or_wrong_branch_is_refused(self):
        for key, value in (("GITHUB_RUN_ATTEMPT", "2"),
                           ("GITHUB_REF", "refs/heads/feature")):
            env = self.identity()
            env[key] = value
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(ArenaError, "first-attempt"):
                    buffalo_only.identity()

    def test_execute_invokes_unmodified_runner_once_and_no_omc(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "artifacts/buffalo-only"
            out.mkdir(parents=True)
            write_json(out / "admission.json",
                       {"execution_run_id": 99999889, "execution_commit_sha": "f" * 40})
            with (patch.dict(os.environ, {**self.identity(),
                                          "CLOUDFLARE_API_TOKEN": "mock-sensitive-token"}),
                  patch.object(buffalo_only, "public_input",
                               return_value={"world_public_id": "PUBLIC_WORLD"}),
                  patch.object(buffalo_only, "module"),
                  patch.object(buffalo_only.subprocess, "run") as subprocess_run):
                subprocess_run.return_value.returncode = 1
                outcome = buffalo_only.execute_once(d)
                self.assertEqual(outcome["returncode"], 1)
                self.assertEqual(subprocess_run.call_count, 1)
                args, kwargs = subprocess_run.call_args
                self.assertEqual(args[0],
                                 ["node", "scripts/arena_b_ct03_native_runner.mjs"])
                self.assertEqual(kwargs["env"]["BUFFALO_ROUND_KIND"], "initial")
                self.assertEqual(kwargs["env"]["BUFFALO_MODE"], "live")
                self.assertEqual(kwargs["env"]["CLOUDFLARE_ACCOUNT_ID"],
                                 buffalo_only.public_config()["cloudflare"]["account_id"])
                self.assertNotIn("omc", args[0])
                self.assertEqual(read_json(out / "attempt.json")["max_provider_posts"], 1)
                with self.assertRaisesRegex(ArenaError, "retry refused"):
                    buffalo_only.execute_once(d)

    def test_finalize_unanswered_post_reports_unknown_consumption(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "artifacts/buffalo-only"
            out.mkdir(parents=True)
            write_json(out / "admission.json", {"schema": "test"})
            write_json(out / "attempt.json", {"state": "ATTEMPT_RESERVED"})
            result = buffalo_only.finalize(d)
            self.assertTrue(result["provider_attempt_reserved"])
            self.assertIsNone(result["provider_posts_reported"])
            self.assertFalse(result["provider_consumption_complete"])
            self.assertFalse(result["raw_provider_response_archived"])

    def test_original_adapter_and_separate_manual_workflow_contract(self):
        workflow = (ROOT / ".github/workflows/buffalo-only.yml").read_text()
        adapter = (ROOT / "arena/_vendor/igc/scripts/arena_b_ev01_cf_adapter.mjs").read_text()
        runner = (ROOT / "arena/_vendor/igc/scripts/arena_b_ct03_native_runner.mjs").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertNotIn("  pull_request:", workflow)
        self.assertIn("environment: arena-provider", workflow)
        self.assertNotIn("environment: arena-custodian", workflow)
        self.assertNotIn("native-runtime/action.yml", workflow)
        self.assertIn("role: b", workflow)
        self.assertIn("run-id: 42455527897", workflow)
        self.assertIn("artifact-ids: 13607441674", workflow)
        self.assertNotIn("python -m arena.cloud b ", workflow)
        self.assertNotIn("python -m arena.cloud world", workflow)
        self.assertNotIn("python -m arena.cloud dm", workflow)
        self.assertNotIn("python -m arena.cloud evaluate", workflow)
        self.assertIn("EV01_CAP=16000", adapter)
        self.assertIn("const response=await originals.fetch", runner)
        self.assertIn("recorded.proxy_requests!==1", runner)


if __name__ == "__main__":
    unittest.main()
