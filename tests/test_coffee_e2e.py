"""Fictional unit contracts; authentic corpus execution happens only in GitHub."""
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock
import zipfile

from arena.common import ArenaError
from arena import coffee_e2e as e2e
from arena import coffee_v2_synthetic_corpus as corpus
from arena.coffee_v2_p11 import strict_preference_reversal
from test_coffee_v2_synthetic_corpus import synthetic_archive
from arena.coffee_e2e_protocol import CoffeeGitHubBackend
from arena.store import RunStore

ENV = {"GITHUB_REPOSITORY":e2e.REPO, "GITHUB_REF":"refs/heads/main",
       "GITHUB_EVENT_NAME":"push", "GITHUB_RUN_ATTEMPT":"1",
       "GITHUB_RUN_ID":"12345", "GITHUB_SHA":"a"*40}


def lock_fixture():
    candidates = []
    for arm, count in (("D",6),("M",6),("B",1)):
        for i in range(count):
            candidates.append({"arm":arm,"candidate_id":f"{arm}{i}","status":"PREDICTED",
                               "predictions":{str(t):{"orders_picked_up_cumulative":2.0} for t in e2e.CUTS}})
    return {"schema":e2e.LOCK_SCHEMA,"mode":"SCIENTIFIC","case_sha256":e2e.dm.CASE_SHA256,
            "public_sha256":e2e.dm.PUBLIC_SHA256,"source_sha256":e2e.SOURCE_SHA,
            "selection":e2e.dm.SELECTION,"truth_access":False,
            "prediction_cuts_min":list(e2e.CUTS),"candidates":candidates}


class CoffeeEndToEndTests(unittest.TestCase):
    def config(self):
        return {"id":"coffee-test", "protocol":"coffee_end_to_end_v1", "backend":"github",
                "budget":{"omc":1,"provider_posts":0,"workflow":1},
                "github":{"repository":e2e.REPO,"ref":"main","freeze_sha":"HEAD","poll_seconds":1}}

    def test_existing_exact_commit_run_is_followed_without_another_dispatch(self):
        api = Mock()
        api.repo.side_effect = [{"sha":"a"*40}, {"total_count":1,"workflow_runs":[{
            "id":12345,"head_sha":"a"*40,"head_branch":"main","run_attempt":1,"event":"push"}]}]
        api.run.return_value = {"head_sha":"a"*40,"head_branch":"main","run_attempt":1,
                                "path":".github/workflows/coffee-end-to-end.yml",
                                "status":"completed","conclusion":"success"}
        payload = {"status":"END_TO_END_COMPLETED_WITH_DECLARED_LIMITS",
                   "native_evaluation":{"run_id":12345,"code_sha":"a"*40},
                   "new_omc_attempts":1,"provider_posts":0}
        api.artifact.return_value = {"result.json":json.dumps(payload).encode(),"REPORT.md":b"Detailed result"}
        with TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp)/"run", config=self.config())
            try:
                result = CoffeeGitHubBackend(api).execute(store, authorize=True)
                self.assertEqual(result["run"]["status"],"COMPLETED")
                self.assertEqual(result["run"]["consumption"]["workflow"]["observed_attempts"],0)
                self.assertEqual(result["run"]["consumption"]["omc"]["observed_attempts"],1)
                self.assertTrue((store.root/"COFFEE_REPORT.md").is_file())
                api.dispatch.assert_not_called()
            finally:
                store.close()

    def test_uncertain_dispatch_is_recorded_and_never_automatically_repeated(self):
        api = Mock()
        api.repo.side_effect = [{"sha":"a"*40},{"total_count":0,"workflow_runs":[]}]
        api.dispatch.side_effect = ArenaError("uncertain network reply")
        with TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp)/"run", config=self.config())
            try:
                backend = CoffeeGitHubBackend(api)
                with self.assertRaisesRegex(ArenaError,"uncertain network"):
                    backend.execute(store,authorize=True)
                with self.assertRaisesRegex(ArenaError,"automatic retry refused"):
                    backend.execute(store)
                self.assertEqual(api.dispatch.call_count,1)
                self.assertEqual(store.report()["status"],"NEEDS_RECONCILIATION")
                self.assertEqual(store.report()["consumption"]["workflow"]["observed_attempts"],1)
            finally:
                store.close()

    def test_reversal_requires_both_strict_preferences_not_ties(self):
        for counts, expected in (({"B0_IF_ASSUMPTIONS":1,"TIE_IF_ASSUMPTIONS":1},False),
                                 ({"S5_IF_ASSUMPTIONS":1,"TIE_IF_ASSUMPTIONS":1},False),
                                 ({"B0_IF_ASSUMPTIONS":1,"S5_IF_ASSUMPTIONS":1},True),
                                 ({"TIE_IF_ASSUMPTIONS":1},False)):
            self.assertEqual(strict_preference_reversal(counts), expected)

    def test_existing_container_keeps_hash_and_reads_only_canonical_corpus(self):
        raw = synthetic_archive()
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as outer:
            for name in original.namelist():
                outer.writestr("video2/"+name, original.read(name))
            outer.writestr("video2/irrelevant-secret.txt", "NEVER_PARSE_OTHER_SOURCE")
        archive = buf.getvalue()
        checksum = hashlib.sha256(archive).hexdigest()
        with TemporaryDirectory() as tmp, patch.object(corpus,"PINNED_CONTAINER_SHA256",checksum):
            path = Path(tmp)/"container.zip"; path.write_bytes(archive)
            result = corpus.audit(path, key=b"FictionalKeyOnly"*3)
        self.assertEqual(result["public"]["source_zip_sha256"],"sha256:"+checksum)
        self.assertEqual(result["public"]["synthetic_weekly_runs"],54)
        self.assertTrue(result["public"]["truth_bytes_hashed_but_truth_rows_not_interpreted"])
        self.assertNotIn("NEVER_PARSE_OTHER_SOURCE",json.dumps(result))

    def test_no_private_storage_before_external_archive_and_native_attestation(self):
        storage = Mock()
        with patch.dict(os.environ, ENV, clear=True), patch.object(
                e2e,"verify_archived_lock",side_effect=ArenaError("archive not verified")):
            with self.assertRaisesRegex(ArenaError,"archive not verified"):
                e2e.evaluate("not-created", api=Mock(), storage_factory=storage)
        storage.assert_not_called()

    def test_readiness_wrong_population_and_nonmonotone_forecast_fail_closed(self):
        base = lock_fixture()
        self.assertTrue(e2e.validate_lock(base))
        for mutate in (lambda d:d.update(mode="READINESS_ONLY"),
                       lambda d:d.update(source_sha256="0"*64),
                       lambda d:d["candidates"].pop(),
                       lambda d:d["candidates"][0]["predictions"]["100.0"].update(
                           orders_picked_up_cumulative=1)):
            bad = copy.deepcopy(base); mutate(bad)
            with self.assertRaises(ArenaError):e2e.validate_lock(bad)

    def test_pickup_scoring_does_not_compare_against_pos_payments(self):
        lock = lock_fixture()
        actual = {"metrics":{str(t):{"orders_picked_up_cumulative":1,
                                    "paid_sales_cumulative":999} for t in e2e.CUTS}}
        scores = e2e.score_pickups(lock, actual)
        self.assertEqual(len(scores),13)
        self.assertTrue(all(r["mae_pickups_orders"]==1 for r in scores))
        lock["candidates"][-1].update(status="FAILED_G2",predictions=None)
        scores = e2e.score_pickups(lock,actual)
        self.assertIsNone(scores[-1]["mae_pickups_orders"])

    def test_main_first_attempt_only(self):
        self.assertEqual(e2e.execution_identity(ENV),(12345,"a"*40))
        for value in ({"GITHUB_RUN_ATTEMPT":"2"},{"GITHUB_REF":"refs/heads/other"},
                      {"GITHUB_EVENT_NAME":"pull_request"}):
            with self.assertRaises(ArenaError):e2e.execution_identity({**ENV,**value})

    def test_workflow_uses_existing_custody_and_does_not_publish_private_inputs(self):
        workflow = (Path(__file__).resolve().parents[1]/".github/workflows/coffee-end-to-end.yml").read_text()
        self.assertIn("environment: arena-custodian",workflow)
        self.assertIn("CT03_R2_ACCESS_KEY_ID",workflow)
        self.assertNotIn("P11_CUSTODY_HMAC_KEY_B64",workflow)
        self.assertNotIn("source_release_tag",workflow)
        self.assertNotIn("coffee-corpus/\n",workflow)
        self.assertIn("needs: native",workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}",workflow)
        self.assertIn("coffee-e2e-result-",workflow)


if __name__ == "__main__":
    unittest.main()
