"""Native migration invariants. All provider/storage/solver operations are mocked or absent."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
import urllib.error

from arena import cloud,orchestrator
from arena.common import ArenaError,read_json,write_json
from arena.connections import Connections
from arena.engines import Engines
from arena.runtime import prepare,verify
from arena.custody import R2

ROOT=Path(__file__).resolve().parents[1]


def environment(attempt="1"):
    return {"GITHUB_SHA":"a"*40,"GITHUB_RUN_ID":"123","GITHUB_REPOSITORY":"yudocyudoc/igc-modular",
            "GITHUB_EVENT_NAME":"workflow_dispatch","GITHUB_RUN_ATTEMPT":attempt,"GITHUB_REF":"refs/heads/main"}


class NativeRuntimeTests(unittest.TestCase):
    def test_all_original_sources_and_historical_consequences_are_preserved(self):
        result=verify()
        self.assertTrue(result["unchanged"])
        self.assertEqual(result["files"],103)
        self.assertEqual(result["new_omc"],0)

    def test_b_runtime_excludes_other_arms_historical_traces_and_relocates_only_guards(self):
        with TemporaryDirectory() as temp:
            target=Path(temp)/"runtime"
            info=prepare(target,role="b")
            self.assertFalse((target/"artifacts/ct03-reuse/original").exists())
            self.assertTrue((target/"upstream/sd-ai/engines/quantitative/engine.js").exists())
            text=(target/"scripts/arena_b_ct03_native_runner.mjs").read_text(encoding="utf-8")
            self.assertIn("refs/heads/main",text)
            self.assertNotIn("refs/heads/experiment/arena-ct00-ct02-20261107",text)
            self.assertFalse(info["scientific_sources_modified"])
            with self.assertRaisesRegex(ArenaError,"overwrite"):
                prepare(target,role="b")

    def test_buffalo_is_registered_but_preparation_does_not_make_an_inference(self):
        with TemporaryDirectory() as temp:
            prepared=Engines().prepare("B",Path(temp)/"B")
            self.assertEqual(prepared["status"],"ORIGINAL_SOURCE_READY_NOT_GENERATED")
            self.assertEqual(prepared["provider_posts"],0)


class NativeSafetyTests(unittest.TestCase):
    def test_live_admission_denies_missing_approval_before_any_engine_or_world(self):
        with patch.dict(os.environ,environment(),clear=True),patch("arena.cloud.verify") as verify_sources:
            with self.assertRaises(ArenaError):
                cloud.admit("live","no","",19,2)
            verify_sources.assert_not_called()
            with self.assertRaises(ArenaError):
                cloud.admit("live","yes","",20,2)
            verify_sources.assert_not_called()

    def test_storage_credentials_are_never_allowed_in_a_producer_environment(self):
        with patch.dict(os.environ,{"CT03_R2_SECRET_ACCESS_KEY":"TEST_ONLY"},clear=True):
            with self.assertRaisesRegex(ArenaError,"Storage credentials"):
                cloud.assert_producer_environment(buffalo=True)
        with patch.dict(os.environ,{"CLOUDFLARE_API_TOKEN":"TEST_ONLY"},clear=True):
            with self.assertRaises(ArenaError):
                cloud.assert_producer_environment()
            cloud.assert_producer_environment(buffalo=True)

    def test_provider_preflight_uses_only_get_and_rejects_storage_access(self):
        response=Mock()
        response.status=200
        response.read.return_value=b'{"success":true,"result":[]}'
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        forbidden=urllib.error.HTTPError("https://api.cloudflare.com",403,"Forbidden",{},None)
        variables={"CLOUDFLARE_ACCOUNT_ID":"a"*32,"CLOUDFLARE_API_TOKEN":"TEST_ONLY"}
        with patch.dict(os.environ,variables,clear=True),patch("urllib.request.urlopen",side_effect=[response,forbidden]) as opened:
            report=cloud.provider_preflight()
            self.assertTrue(report["r2_bucket_listing_denied"])
            self.assertEqual(report["provider_posts"],0)
            self.assertTrue(all(call.args[0].get_method()=="GET" for call in opened.call_args_list))
        with patch.dict(os.environ,variables,clear=True),patch("urllib.request.urlopen",return_value=response):
            with self.assertRaisesRegex(ArenaError,"R2 bucket listing is not denied"):
                cloud.provider_preflight()

    def test_archive_rejection_occurs_before_constructing_storage_client(self):
        with patch("arena.cloud.verify_archive",side_effect=ArenaError("Lock rejected")),patch("arena.custody.R2") as storage:
            with self.assertRaisesRegex(ArenaError,"Lock rejected"):
                cloud.evaluate(Path("not-present"),"42")
            storage.assert_not_called()

    def test_world_claim_is_atomic_create_once_and_not_a_plain_overwrite(self):
        with TemporaryDirectory() as temp:
            client=R2.__new__(R2)
            client.bucket="private-test"
            client.preflight=Mock(return_value={})
            client.call=Mock(return_value={})
            with patch.dict(os.environ,environment(),clear=True):
                client.reserve(Path(temp),"123","a"*40)
            call=client.call.call_args.args
            self.assertIn("--if-none-match",call)
            self.assertEqual(call[call.index("--if-none-match")+1],"*")

    def test_evaluator_can_retry_without_reexecuting_first_attempt_producers(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            fixture=root/"fixture"
            orchestrator.run(ROOT/"examples/smoke.toml",fixture,Connections({}))
            target=root/"runtime"
            prepare(target,role="evaluator")
            shutil.copytree(fixture/"producers/public",target/"artifacts/ct03-public")
            archive=target/"artifacts/native-lock"
            archive.mkdir()
            sealed=read_json(fixture/"archive/lock.json")
            write_json(archive/"lock.json",sealed)
            write_json(archive/"archive-metadata.json",{
                "schema":cloud.LOCK_SCHEMA,"repository":"yudocyudoc/igc-modular","github_run_id":"123",
                "frozen_code_sha":"a"*40,"lock_sha256":sealed["lock_sha256"],"candidate_count":13,
                "producer_execution_attempt":1,"reserved_truth_opened":False,
                "producer_jobs_closed_before_archive":True})
            api=Mock()
            api.run.return_value={"head_sha":"a"*40,"head_branch":"main","event":"workflow_dispatch","run_attempt":2,
                                  "path":".github/workflows/arena-run.yml"}
            def repo(method,path):
                if "/artifacts/" in path:
                    return {"expired":False,"workflow_run":{"id":123,"head_sha":"a"*40},"name":"native-lock-123"}
                self.assertIn("/attempts/1/jobs",path)
                return {"jobs":[{"name":name,"status":"completed","conclusion":"success"} for name in (
                    "Select and simulate one private world","D and M originals","Buffalo original and own feedback","Lock producer predictions")]}
            api.repo.side_effect=repo
            with patch.dict(os.environ,environment("2"),clear=True):
                verified,_=cloud.verify_archive(target,"42",api=api)
            self.assertEqual(verified["lock_sha256"],sealed["lock_sha256"])


if __name__=="__main__":
    unittest.main()
