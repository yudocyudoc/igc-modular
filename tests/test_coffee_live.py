"""Offline admission and no-retry regressions for coffee live Buffalo."""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock

from arena.buffalo import coffee_live
from arena.common import ArenaError, read_json
import test_coffee_domain


class FakeGitHub:
    def __init__(self, bad_source=False, bad_artifact=False, older=None):
        self.bad_source=bad_source
        self.bad_artifact=bad_artifact
        self.older=older or {}

    def run(self, id):
        if id == 123:
            return {"id":123,"path":"wrong" if self.bad_source else coffee_live.SOURCE_WORKFLOW,
                    "event":"workflow_dispatch","head_branch":"main",
                    "run_attempt":1,"status":"completed","conclusion":"success",
                    "head_sha":"a"*40}
        return self.older[id]["run"]

    def repo(self, method, path):
        assert method == "GET"
        if path == "/actions/artifacts/77":
            return {"id":77,"name":"wrong" if self.bad_artifact else "coffee-public-123",
                    "expired":False,"workflow_run":{"id":123}}
        if path == "/actions/runs/123/jobs?per_page=100":
            return {"total_count":1,"jobs":[{
                "name":"Admit one staged B0 source under private R2 prefix",
                "status":"completed","conclusion":"success"}]}
        if path.startswith("/actions/workflows/coffee-buffalo-live.yml/runs?"):
            return {"total_count":len(self.older),
                    "workflow_runs":[{"id":id} for id in self.older]}
        for id,item in self.older.items():
            if path == f"/actions/runs/{id}/jobs?per_page=100":
                return item["jobs"]
        raise AssertionError(path)


class CoffeeLiveTests(TestCase):
    setUp=test_coffee_domain.CoffeeDomainTests.setUp

    def env(self):
        return {"GITHUB_EVENT_NAME":"workflow_dispatch",
                "GITHUB_REPOSITORY":coffee_live.REPO,
                "GITHUB_REF":"refs/heads/main","GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_SHA":"b"*40,"GITHUB_RUN_ID":"456",
                "COFFEE_B_LIVE_AUTH":"yes","GH_TOKEN":"FAKE_READ_ONLY",
                "RUNNER_TEMP":"/tmp"}

    def admit(self, path, api=None, env=None):
        public=read_json(self.public/"producer-public-b0.json")
        cfg={"source":{"sha256":public["source_package_sha256"]},
             "selection":public["selection"],"construction_end_min":60,
             "window_end_min":103.237}
        with patch.object(coffee_live.tomllib,"load",return_value=cfg), \
             patch.object(coffee_live,"verify",return_value={}):
            return coffee_live.admit(self.public,123,77,path,
                api=api or FakeGitHub(),env=env or self.env())

    def test_identity_rejects_wrong_branch_or_retry(self):
        for key,value in (("GITHUB_REF","refs/heads/dev"),
                          ("GITHUB_RUN_ATTEMPT","2"),("COFFEE_B_LIVE_AUTH","no")):
            env=self.env();env[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ArenaError,"MANUAL_FIRST"):
                coffee_live.identity(env)

    def test_admission_public_only_and_single_use(self):
        path=self.root/"live"
        result=self.admit(path)
        inp=read_json(path/"input.json")
        self.assertEqual(result["provider_posts"],0)
        self.assertEqual(inp["mode"],coffee_live.LIVE_MODE)
        self.assertEqual(inp["source_artifact_id"],77)
        self.assertEqual(inp["execution_run_id"],456)
        self.assertFalse(inp["truth_access"])
        self.assertNotIn("SECRET-FUTURE-TRUTH",json.dumps(inp))
        with self.assertRaisesRegex(ArenaError,"REFUSE_OVERWRITE"):
            self.admit(path)

    def test_bad_custody_artifact_and_private_credentials_fail_closed(self):
        for api,env in ((FakeGitHub(bad_source=True),self.env()),
                        (FakeGitHub(bad_artifact=True),self.env()),
                        (FakeGitHub(),{**self.env(),"CT03_R2_ACCESS_KEY_ID":"private"})):
            path=self.root/"live"
            with self.assertRaises(ArenaError):
                self.admit(path,api=api,env=env)
            self.assertFalse(path.exists())

    def test_prior_paid_attempt_blocks_future_dispatch(self):
        run={"id":300,"path":coffee_live.WORKFLOW,"event":"workflow_dispatch",
             "run_attempt":1,"status":"completed","conclusion":"failure"}
        steps=[{"name":"npm","number":3,"status":"completed","conclusion":"failure"},
               {"name":coffee_live.PAID_STEP,"number":4,"status":"completed",
                "conclusion":"skipped"}]
        older={300:{"run":run,"jobs":{"total_count":1,"jobs":[{
            "name":coffee_live.PAID_JOB,"status":"completed",
            "conclusion":"failure","steps":steps}]}}}
        self.assertEqual(coffee_live.check_history(FakeGitHub(older=older),456),[300])
        steps[-1]["conclusion"]="failure"
        with self.assertRaisesRegex(ArenaError,"PREVIOUS_POST_POSSIBLE"):
            coffee_live.check_history(FakeGitHub(older=older),456)
        run["status"]="in_progress"
        with self.assertRaisesRegex(ArenaError,"PREVIOUS_RUN_UNCERTAIN"):
            coffee_live.check_history(FakeGitHub(older=older),456)

    def test_attempt_reserved_before_failed_runner_and_never_repeated(self):
        path=self.root/"live"
        self.admit(path)
        env={**self.env(),"CLOUDFLARE_API_TOKEN":"FAKE",
             "CLOUDFLARE_ACCOUNT_ID":"a"*32}
        with self.assertRaisesRegex(ArenaError,"PROVIDER_FAILED_OR_UNKNOWN"):
            coffee_live.generate(path,env=env,runner=lambda *a,**k:Mock(returncode=1))
        self.assertTrue((path/"attempt.json").is_file())
        with self.assertRaisesRegex(ArenaError,"ATTEMPT_ALREADY_RESERVED"):
            coffee_live.generate(path,env=env,runner=lambda *a,**k:Mock(returncode=0))
        final=coffee_live.finalize(path)
        self.assertTrue(final["provider_may_have_consumed"])
        self.assertIsNone(final["provider_posts_observed"])
        self.assertEqual(final["retries"],0)

    def test_workflow_has_single_paid_step_and_no_r2_secrets(self):
        y=(Path(__file__).resolve().parents[1] /
           ".github/workflows/coffee-buffalo-live.yml").read_text()
        self.assertIn("environment: arena-provider",y)
        self.assertIn("github.run_attempt == 1",y)
        self.assertEqual(y.count("- name: "+coffee_live.PAID_STEP),1)
        self.assertIn("merge-multiple: true",y)
        self.assertIn("cancel-in-progress: false",y)
        self.assertNotIn("CT03_R2_ACCESS_KEY_ID:",y)
        self.assertNotIn("COFFEE_R2_ACCESS_KEY_ID:",y)
