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
    def test_historical_artifact_digest_preserves_required_sha256_prefix(self):
        with patch.object(e2e.feedback,"_fetch",return_value={}) as fetch:
            e2e.fetch_historical(Mock(),4)
        self.assertEqual(fetch.call_args.kwargs["archive_sha"],
                         "sha256:"+e2e.history.HISTORY[4][6])

    def test_cli_reports_preflight_failure_without_hiding_original_error(self):
        from contextlib import redirect_stderr
        capture = io.StringIO()
        with patch.object(e2e,"stage_native",side_effect=ArenaError("known failure")), redirect_stderr(capture):
            self.assertEqual(e2e.main(["native-preflight","--out","unused"]),2)
        self.assertEqual(json.loads(capture.getvalue())["reason"],"known failure")

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
        api.repo.side_effect = [{"sha":"a"*40},{"total_count":0,"workflow_runs":[]},
                               {"total_count":0,"workflow_runs":[]}]
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

    def test_runtime_log_cannot_overwrite_omc_console_evidence(self):
        native = {"model":{"variables":[
            {"name":"Waiting Paid Orders","type":"stock","equation":"0",
             "inflows":["Paid"],"outflows":["Pickup","Loss"]},
            {"name":"Picked Up Cumulative","type":"stock","equation":"0",
             "inflows":["Pickup"],"outflows":[]}]}}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"B.mo").write_text("fictional model",encoding="utf-8")
            (root/"B.mos").write_text("fictional commands",encoding="utf-8")
            e2e.write_json(root/"B-native.json",native)
            stage = {"run_id":12345,"code_sha":"a"*40,"B_class":"FixtureNative"}
            for name,key in (("B.mo","B_model_sha256"),("B.mos","B_script_sha256"),
                             ("B-native.json","B_native_file_sha256")):
                stage[key] = "sha256:"+corpus.sha_file(root/name)
            e2e.write_json(root/"stage.json",stage)
            e2e.write_json(root/"B-attempt.json",{"run_id":12345,"code_sha":"a"*40,"max_new_omc":1})
            def fake_cli(args, **kwargs):
                kwargs["stdout"].write(b"Check of FixtureNative completed successfully\nLOG_SUCCESS\n")
                # Reproduce exactly OMC's independent <prefix>.log creation.
                (root/"B.log").write_text("LOG_SUCCESS runtime only\n",encoding="utf-8")
                with (root/"B_res.csv").open("w",encoding="utf-8",newline="") as stream:
                    writer=csv.writer(stream)
                    writer.writerow(["time","Waiting_Paid_Orders","Picked_Up_Cumulative","Loss"])
                    for i in range(65):
                        t=i*e2e.solver.HORIZON/64
                        writer.writerow([t,0,10*t,0])
                return Mock(returncode=0)
            with patch.dict(os.environ,ENV,clear=True), patch.object(
                    os,"getuid",return_value=1001,create=True), patch.object(
                    os,"getgid",return_value=1001,create=True):
                result=e2e.run_b(root,cli=fake_cli)
            self.assertEqual(result["status"],"PREDICTED")
            self.assertIn("Check of FixtureNative",(root/"B-omc.log").read_text())
            self.assertNotIn("Check of",(root/"B.log").read_text())

    def test_correction_keeps_original_failed_lock_and_uses_sealed_forecast_only(self):
        lock=lock_fixture()
        lock.update(run_id=e2e.SEALED_B_RECOVERY["run_id"],code_sha=e2e.SEALED_B_RECOVERY["code_sha"])
        lock["candidates"][-1].update(status="FAILED_G2",predictions=None)
        oracle={"metrics":{str(t):{"orders_picked_up_cumulative":1} for t in e2e.CUTS}}
        original={"lock_sha256":e2e.digest(lock),
                  "archive_verification":{"artifact_id":e2e.SEALED_B_RECOVERY["lock"][0]},
                  "truth_read_after_archived_lock":True,"scores":e2e.score_pickups(lock,oracle),
                  "actual_synthetic_pickups":{str(t):1 for t in e2e.CUTS}}
        model=b"unchanged original equation bytes"
        commands=b"one original simulate command"
        stage={"run_id":lock["run_id"],"code_sha":lock["code_sha"],
               "B_model_sha256":"sha256:"+hashlib.sha256(model).hexdigest(),
               "B_script_sha256":"sha256:"+hashlib.sha256(commands).hexdigest()}
        entries={"lock.json":json.dumps(lock).encode(),"B-native.json":b"{}",
                 "B-result.json":json.dumps({"status":"FAILED_G2", "failure":"COFFEE_E2E_B_OMC_NOT_SUCCESSFUL"}).encode(),
                 "B-attempt.json":json.dumps({"run_id":lock["run_id"],"code_sha":lock["code_sha"],
                                               "max_new_omc":1,"attempt_reserved":True}).encode(),
                 "stage.json":json.dumps(stage).encode(),"B.mo":model,"B.mos":commands,
                 "B.log":b"LOG_SUCCESS The simulation finished successfully",
                 "B_res.csv":b"fictional already sealed trace"}
        original_lock=entries["lock.json"]
        checked={"predictions":{str(t):{"orders_picked_up_cumulative":2.0} for t in e2e.CUTS}}
        with patch.object(e2e,"translate_b",return_value=("Fixture",model.decode(),{})), patch.object(
                e2e,"verify_b_csv",return_value=checked):
            corrected=e2e.reclassify_sealed_b(entries,original)
        self.assertEqual(entries["lock.json"],original_lock)
        self.assertEqual(json.loads(entries["lock.json"])["candidates"][-1]["status"],"FAILED_G2")
        self.assertEqual(corrected["scores"][-1]["mae_pickups_orders"],1.0)
        self.assertEqual(corrected["new_omc_attempts"],0)
        self.assertTrue(corrected["technical_reclassification"]["original_lock_and_failure_preserved"])

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
