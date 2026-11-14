"""Offline admission and no-retry regressions for coffee live Buffalo."""
import hashlib
import io
import json
import zipfile
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
                config_path=Path(__file__).resolve().parents[1] / "examples/coffee_peak.toml",
                assumptions_path=test_coffee_domain.ASSUMPTIONS,
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

    def test_dispatch_ids_remain_literal_shell_data(self):
        """Execute the exact workflow block with an inert Python argument recorder."""
        import os
        import shutil
        import subprocess
        from tempfile import TemporaryDirectory
        yaml = (Path(__file__).resolve().parents[1] /
                ".github/workflows/coffee-buffalo-live.yml").read_text()
        block = yaml.split(
            "      - name: Verify source run, artifact, B0 public identity and prior attempts\n", 1
        )[1].split("      - name: Verify Cloudflare AI permission", 1)[0]
        self.assertIn("COFFEE_PUBLIC_RUN_ID: ${{ inputs.public_run_id }}", block)
        self.assertIn("COFFEE_PUBLIC_ARTIFACT_ID: ${{ inputs.public_artifact_id }}", block)
        self.assertNotIn("--source-run-id '${{ inputs.public_run_id }}'", block)
        self.assertNotIn("--artifact-id '${{ inputs.public_artifact_id }}'", block)
        if os.name == "nt":
            # Git Bash interprets Windows drive paths differently from the Ubuntu
            # runner used by this workflow. Keep static checks on Windows;
            # execute the precise payload reproduction on Linux.
            return
        if not shutil.which("bash"):
            self.skipTest("Bash unavailable")
        body = block.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] if line.startswith("          ") else line
                           for line in body.splitlines())
        with TemporaryDirectory() as temp:
            marker = Path(temp) / "marker-must-not-exist"
            captured = Path(temp) / "shell-argv.txt"
            run_id = "123'$(touch " + str(marker) + ")'"
            artifact_id = "77'$(touch " + str(marker) + ")'"
            env = {**os.environ, "RUNNER_TEMP": temp, "GITHUB_WORKSPACE": temp,
                   "COFFEE_PUBLIC_RUN_ID": run_id,
                   "COFFEE_PUBLIC_ARTIFACT_ID": artifact_id, "CAPTURE": str(captured)}
            inert = 'python() { printf "%s\\n" "$@" > "$CAPTURE"; }\n'
            result = subprocess.run(["bash", "-e", "-c", inert + script],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = captured.read_text().splitlines()
            self.assertIn(run_id, args)
            self.assertIn(artifact_id, args)
            self.assertFalse(marker.exists(), "unexpected command execution")


    def test_account_id_falls_back_to_repository_pinned_value_before_attempt(self):
        from arena.connections import public_config
        output = self.root/"live"
        self.admit(output)
        env = {**self.env(), "CLOUDFLARE_ACCOUNT_ID": "",
               "CLOUDFLARE_API_TOKEN": "FAKE_SCOPED_TOKEN"}
        received = []

        def offline_runner(argv, **kwargs):
            received.append(kwargs["env"]["CLOUDFLARE_ACCOUNT_ID"])
            return Mock(returncode=1)

        with self.assertRaisesRegex(ArenaError,"PROVIDER_FAILED_OR_UNKNOWN"):
            coffee_live.generate(output,env=env,runner=offline_runner)
        self.assertEqual(received,[public_config()["cloudflare"]["account_id"]])
        self.assertTrue((output/"attempt.json").exists())
        bad=self.root/"bad-account"
        self.admit(bad)
        with self.assertRaisesRegex(ArenaError,"PROVIDER_CREDENTIALS_REQUIRED"):
            coffee_live.generate(bad,env={**env,
                "CLOUDFLARE_ACCOUNT_ID":"f"*32},runner=offline_runner)
        self.assertFalse((bad/"attempt.json").exists())
        self.assertEqual(len(received),1)

    def test_only_digest_pinned_historical_no_post_receipt_allows_new_admission(self):
        record = dict(coffee_live.NO_POST_RECOVERY)
        final = {
            "schema":"arena.coffee-b-live-final/1",
            "status":"NO_PROVIDER_ATTEMPT", "attempt_reserved":False,
            "provider_posts_observed":0, "provider_may_have_consumed":False,
            "provider_usage":None, "raw_provider_saved":False,
            "new_omc":0, "r2_access":False, "scientific_lock_created":False,
            "retries":0}
        admission = {
            "run_id":record["run_id"],"sha":record["head_sha"],
            "source_run_id":record["source_run_id"],
            "artifact_id":record["source_artifact_id"],
            "case_sha256":record["case_sha256"],
            "max_provider_posts":1, "scientific_lock_created":False}
        payload = {
            "execution_run_id":record["run_id"],"execution_sha":record["head_sha"],
            "case_sha256":record["case_sha256"],
            "provider_posts":0,"scientific_lock_created":False}

        def pack(*, include_attempt=False, modified_final=None):
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as archive:
                for name,obj in (("admission.json",admission),("final.json",
                                 final if modified_final is None else modified_final),
                                 ("input.json",payload)):
                    archive.writestr(name,json.dumps(obj).encode())
                if include_attempt:
                    archive.writestr("attempt.json",b"{}")
            return buffer.getvalue()

        steps=[]
        names=[
            "Verify source run, artifact, B0 public identity and prior attempts",
            "Verify Cloudflare AI permission and R2 denial (GET only)",
            "Install pinned Buffalo SDK before the paid request",
            coffee_live.PAID_STEP,
            "Finalize actual or uncertain provider usage with no retry",
            "Archive request, original native, raw response and usage receipts"]
        for number,name in enumerate(names,1):
            steps.append({"number":number,"name":name,"status":"completed",
                          "conclusion":"failure" if name==coffee_live.PAID_STEP else "success"})
        earlier={record["run_id"]:{"run":{
            "id":record["run_id"],"path":coffee_live.WORKFLOW,
            "event":"workflow_dispatch","head_sha":record["head_sha"],
            "run_attempt":1,"status":"completed","conclusion":"failure"},
            "jobs":{"total_count":1,"jobs":[{
                "id":record["job_id"],"name":coffee_live.PAID_JOB,
                "status":"completed","conclusion":"failure","steps":steps}]}}}

        class HistoricalAPI(FakeGitHub):
            def __init__(self, raw):
                super().__init__(older=earlier)
                self.raw=raw

            def repo(self, method, path, **kwargs):
                assert method=="GET"
                if path==f'/actions/artifacts/{record["artifact_id"]}':
                    return {"id":record["artifact_id"],
                            "name":f'coffee-b-live-{record["run_id"]}',
                            "expired":False,"digest":record["artifact_digest"],
                            "workflow_run":{"id":record["run_id"]}}
                if path==f'/actions/artifacts/{record["artifact_id"]}/zip':
                    assert kwargs.get("binary") is True
                    return self.raw
                return super().repo(method,path)

        def exercise(raw):
            record["artifact_digest"]="sha256:"+hashlib.sha256(raw).hexdigest()
            with patch.object(coffee_live,"NO_POST_RECOVERY",dict(record)):
                return coffee_live.check_history(HistoricalAPI(raw),456)

        intact=pack()
        self.assertEqual(exercise(intact),[record["run_id"]])
        bad=pack(include_attempt=True)
        with self.assertRaisesRegex(ArenaError,"ARCHIVE_FILES_INVALID"):
            exercise(bad)
        bad_final=dict(final)
        bad_final["provider_may_have_consumed"]=True
        with self.assertRaisesRegex(ArenaError,"RECEIPT_NOT_ZERO_ATTEMPT"):
            exercise(pack(modified_final=bad_final))
        raw=pack()
        record["artifact_digest"]="sha256:"+hashlib.sha256(raw).hexdigest()
        with patch.object(coffee_live,"NO_POST_RECOVERY",dict(record)):
            with self.assertRaisesRegex(ArenaError,"ARCHIVE_HASH_MISMATCH"):
                coffee_live.check_history(HistoricalAPI(raw[:-1]+b"x"),456)
        earlier[record["run_id"]]["jobs"]["jobs"][0]["steps"][3]["conclusion"]="success"
        with patch.object(coffee_live,"NO_POST_RECOVERY",dict(record)):
            with self.assertRaisesRegex(ArenaError,"STEP_ATTESTATION_FAILED"):
                coffee_live.check_history(HistoricalAPI(raw),456)

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
