import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import urllib.request

from arena import config, orchestrator
from arena.common import ArenaError, read_json, write_json
from arena.connections import Connections, Secret, SystemVault
from arena.data import ingest, ct03_public
from arena.engines import Engines
from arena.fixture import FixtureBackend
from arena.github import ApiError, GitHub, SafeRedirect
from arena.legacy import load, verify
from arena.remote import GitHubBackend
from arena.store import RunStore

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT/"examples/smoke.toml"
LIVE = ROOT/"examples/ct03.toml"


class MemoryVault:
    def __init__(self):
        self.values = {}
        self.reads = []

    def get(self, name):
        self.reads.append(name)
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"buffalo": {"api_token": ["env:CLOUDFLARE_API_TOKEN", "vault:buffalo/api_token"]}}

    def test_existing_environment_is_reused_without_vault_or_new_names(self):
        vault = MemoryVault()
        con = Connections(self.profile, environ={"CLOUDFLARE_API_TOKEN": "test-sensitive"}, vault=vault)
        secret = con.resolve("buffalo", "api_token")
        self.assertEqual(secret.value, "test-sensitive")
        self.assertEqual(vault.reads, [])
        self.assertNotIn("test-sensitive", repr(secret)+str(secret)+json.dumps(con.check()))

    def test_one_vault_entry_can_be_reused_by_independent_runs(self):
        vault = MemoryVault()
        Connections(self.profile, environ={}, vault=vault).store("buffalo", "api_token", "test-sensitive")
        for _ in range(3):
            con = Connections(self.profile, environ={}, vault=vault)
            self.assertEqual(con.resolve("buffalo", "api_token").value, "test-sensitive")
        self.assertEqual(list(vault.values), ["buffalo/api_token"])

    def test_literal_credentials_are_rejected(self):
        con = Connections({"bad": {"token": ["literal-secret"]}}, environ={})
        with self.assertRaisesRegex(ArenaError, "references only"):
            con.resolve("bad", "token")

    def test_vault_error_does_not_disclose_backend_exception(self):
        vault = SystemVault()
        backend = Mock()
        backend.get_password.side_effect = RuntimeError("test-sensitive")
        with patch.object(vault, "_backend", return_value=backend):
            with self.assertRaises(ArenaError) as error:
                vault.get("x")
        self.assertNotIn("test-sensitive", str(error.exception))

    def test_missing_vault_does_not_block_existing_gh_session(self):
        vault = Mock()
        vault.get.side_effect = ArenaError("Vault unavailable")
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "test-sensitive\n", ""))
        con = Connections({"github": {"token": ["env:GH_TOKEN", "vault:github/token", "gh:github.com"]}},
                          environ={}, vault=vault, gh_runner=runner)
        self.assertEqual(con.resolve("github", "token").value, "test-sensitive")
        status = con.check()
        self.assertFalse(status["github"]["token"]["authentication_validated"])
        self.assertNotIn("test-sensitive", json.dumps(status))

    def test_artifact_redirect_strips_authentication_off_host(self):
        request = urllib.request.Request("https://api.github.com/something", headers={"Authorization": "Bearer test-sensitive"})
        redirected = SafeRedirect().redirect_request(request, None, 302, "Found", {}, "https://objects.example/artifact")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(ArenaError):
            SafeRedirect().redirect_request(request, None, 302, "Found", {}, "http://objects.example/artifact")


class DataTests(unittest.TestCase):
    def test_partial_data_are_admitted_without_inventing_identity_or_cycles(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/"partial.json"
            original = [{"interval_start": 299, "interval_end": 302, "censored": True, "note": "two receptions"}]
            write_json(source, original)
            dataset = ingest(source)
            self.assertEqual(dataset["record_count"], 1)
            self.assertFalse(dataset["identity_validated"])
            self.assertFalse(dataset["continuity_certified"])
            self.assertEqual(dataset["observations"][0]["fields"], original[0])
            with self.assertRaisesRegex(ArenaError, "source remains admitted"):
                ct03_public(dataset, world="W", source_hash="sha256:"+"a"*64)

    def test_explicit_mapping_and_no_reserved_truth_in_public_input(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/"mapped.csv"
            source.write_text("hora,entregado\n0,0\n1,.3\n2,.6\n4,1.2\n", encoding="utf-8")
            dataset = ingest(source, time_column="hora", value_column="entregado")
            result = ct03_public(dataset, world="W", source_hash="sha256:"+"a"*64)
            self.assertEqual([r["time"] for r in result["observations"]], [0,1,2,4])
            source.write_text(source.read_text()+"6,1.8\n", encoding="utf-8")
            with self.assertRaisesRegex(ArenaError, "reserved truth"):
                ct03_public(ingest(source, time_column="hora", value_column="entregado"), world="W", source_hash="sha256:"+"a"*64)

    def test_non_numeric_measurement_is_kept_as_partial_without_becoming_a_number(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/"bad.csv"
            for value in ("nan", "infinity", "perhaps"):
                source.write_text("time,delivered\n0,"+value+"\n", encoding="utf-8")
                dataset = ingest(source)
                self.assertNotIn("timed_numeric_observations", dataset["capabilities"])
                self.assertNotIn("value", dataset["observations"][0])
                self.assertEqual(dataset["observations"][0]["fields"]["delivered"], value)
                self.assertTrue(dataset["issues"])

    def test_duplicate_columns_keep_original_positions_without_selecting_one(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/"ambiguous.csv"
            source.write_text("time,time,delivered\n0,1,.3\n", encoding="utf-8")
            dataset = ingest(source)
            self.assertEqual(dataset["issues"][0]["code"], "AMBIGUOUS_COLUMNS")
            self.assertNotIn("timed_numeric_observations", dataset["capabilities"])
            self.assertEqual([x["value"] for x in dataset["observations"][0]["fields"]["columns"]], ["0","1",".3"])


class BudgetTests(unittest.TestCase):
    def test_failed_attempt_is_spent_and_remains_spent_after_restart(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/"run"
            settings = {"id": "budget", "backend": "fixture", "budget": {"omc": 1}}
            store = RunStore(path, config=settings)
            store.attempt("D0", "omc")
            store.finish_attempt("D0", successful=False)
            store.close()
            store = RunStore(path)
            try:
                self.assertEqual(store.report()["consumption"]["omc"]["observed_attempts"], 1)
                self.assertEqual(store.report()["consumption"]["omc"]["failed_local_attempts"], 1)
                with self.assertRaisesRegex(ArenaError, "retry refused"):
                    store.attempt("D0", "omc")
                with self.assertRaisesRegex(ArenaError, "Budget exhausted"):
                    store.attempt("M0", "omc")
            finally:
                store.close()

    def test_unknown_remote_consumption_is_never_reported_as_zero_spend(self):
        with TemporaryDirectory() as temp:
            store = RunStore(Path(temp)/"run", config=config.load(LIVE))
            try:
                omc = store.report()["consumption"]["omc"]
                self.assertFalse(omc["complete"])
                self.assertIsNone(omc["remaining"])
                store.measure("world", "omc", 1, complete=False)
                store.measure("world", "omc", 1, complete=False)
                self.assertEqual(store.report()["consumption"]["omc"]["observed_attempts"], 1)
            finally:
                store.close()


class IntegrationTests(unittest.TestCase):
    def test_complete_cli_fixture_uses_original_contracts_and_no_credentials(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)/"run"
            completed = subprocess.run([sys.executable, "-m", "arena", "run", str(SMOKE), "--out", str(out)],
                                       cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "INTEGRATION_COMPLETED")
            result = read_json(out/"result.json")
            self.assertEqual(result["evidence_kind"], "INTEGRATION_FIXTURE")
            self.assertFalse(result["physical_experiment_executed"])
            score = result["fixture_score"]
            self.assertEqual(score["candidate_denominator"], 13)
            self.assertEqual(score["paired_available"], 2)
            self.assertEqual(score["failures_kept_in_denominator"], 11)
            self.assertEqual([x["name"] for x in result["run"]["stages"]], list(FixtureBackend.stages))
            self.assertTrue(all(x["observed_attempts"] == 0 for x in summary["consumption"].values()))
            public = read_json(out/"producers/public/construction.json")
            self.assertEqual([x["time"] for x in public["observations"]], [0,1,2,4])
            again = orchestrator.resume(out, Connections({}))
            self.assertEqual(result, again)

    def test_tampered_lock_stops_before_reserved_fixture_is_read(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)/"run"
            orchestrator.run(SMOKE, out, Connections({}))
            lock = read_json(out/"archive/lock.json")
            lock["rows"][0]["candidate_id"] = "changed"
            write_json(out/"archive/lock.json", lock)
            store = RunStore(out)
            scorer = load("ct03_minimal_score")
            try:
                with patch.object(scorer, "_reserved") as reserve:
                    with self.assertRaises(ValueError):
                        FixtureBackend()._evaluate(store)
                    reserve.assert_not_called()
            finally:
                store.close()

    def test_original_generators_are_preserved_and_registry_is_replaceable(self):
        self.assertTrue(verify()["unchanged"])
        engines = Engines()
        fake = Mock()
        fake.prepare.return_value = {"test": True}
        engines.register("NEW", fake)
        self.assertEqual(engines.prepare("NEW", Path("unused")), {"test": True})
        with self.assertRaises(ArenaError):
            engines.register("D", fake)

    def test_live_requires_one_authorization_before_creating_run(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)/"run"
            with self.assertRaisesRegex(ArenaError, "Authorize"):
                orchestrator.run(LIVE, out, Connections({}))
            self.assertFalse(out.exists())


class FakeGitHub:
    """Transport fixture only. No actual GitHub/provider/solver operation."""
    repository="yudocyudoc/igc-modular"
    def __init__(self):
        self.settings=config.load(LIVE)["github"]
        self.sha="b"*40
        self.calls=[]
        self.failed=False
        self.network_uncertain=False
        self.in_progress=False
        self.inspections=0
        self.unavailable_usage=False
        self.wrong_provenance=False

    def inspect(self,settings,*,configure=False):
        self.inspections+=1
        assert configure is False
        return {"frozen_code_sha":self.sha,"admin_writes_required_to_run":False}

    def variable(self,*args):
        raise AssertionError("Running an experiment must not write administrative variables")

    def dispatch(self,workflow,ref,inputs):
        self.calls.append((workflow,ref,copy.deepcopy(inputs)))
        if self.network_uncertain: raise ArenaError("Disconnected after dispatch")
        return 10

    def run(self,run_id):
        return {"id":run_id,"head_sha":self.sha,"head_branch":"main","event":"workflow_dispatch",
                "run_attempt":1,"path":".github/workflows/arena-run.yml",
                "status":"in_progress" if self.in_progress else "completed",
                "conclusion":"failure" if self.failed else "success",
                "html_url":"https://github.com/test/run/"+str(run_id)}

    def artifact(self,run_id,name):
        if "diagnostic" in name: raise ArenaError("Diagnostic unavailable in this transport fixture")
        assert name=="arena-native-result-"+str(run_id)
        usage={
            "omc":{"limit":19,"observed_attempts":11 if self.unavailable_usage else 19,
                   "complete":not self.unavailable_usage,"remaining":None if self.unavailable_usage else 0,"failed_local_attempts":0},
            "provider_posts":{"limit":2,"observed_attempts":0 if self.unavailable_usage else 2,
                              "complete":not self.unavailable_usage,"remaining":None if self.unavailable_usage else 0,"failed_local_attempts":0},
            "workflow":{"limit":1,"observed_attempts":1,"complete":True,"remaining":0,"failed_local_attempts":0}}
        score={"schema":"igc-ct03-paired-prospective-evaluation/1.0","candidate_denominator":13,
               "lock_sha256":"sha256:"+"a"*64,"scientific_scope":"SYNTHETIC_INTRAFAMILY_SINGLE_WORLD"}
        ack={"github_run_id":run_id,"frozen_code_sha":self.sha,"lock_sha256":score["lock_sha256"]}
        result={"schema":"arena.result/1","evidence_kind":"PHYSICAL_NATIVE_WORKFLOW","score":score,
                "provenance":{"repository":self.repository,"run_id":str(run_id),
                              "frozen_code_sha":"c"*40 if self.wrong_provenance else self.sha},
                "run":{"experiment":"native-test","status":"COMPLETED","backend":"github",
                       "consumption":usage,"stages":[],
                       "cost":{"estimated":None,"billed":None,"currency":None}}}
        return {name:json.dumps(value).encode() for name,value in {
            "result.json":result,"consumption.json":usage,"score-post-lock.json":score,
            "archive-record.json":ack}.items()}|{"report.md":b"TRANSPORT FIXTURE ONLY"}


class RemoteCoordinatorTests(unittest.TestCase):
    def test_single_approval_dispatches_one_native_workflow_without_admin_writes(self):
        with TemporaryDirectory() as temp:
            api=FakeGitHub()
            result=orchestrator.run(LIVE,Path(temp)/"run",Connections({}),authorize=True,adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls),1)
            self.assertEqual(api.calls[0][0],"arena-run.yml")
            self.assertEqual(api.calls[0][2]["freeze_sha"],api.sha)
            self.assertEqual(api.calls[0][2]["mode"],"live")
            self.assertEqual(result["controller"]["consumption"]["omc"]["observed_attempts"],19)
            self.assertEqual(result["controller"]["consumption"]["provider_posts"]["observed_attempts"],2)
            self.assertEqual(result["controller"]["consumption"]["workflow"]["observed_attempts"],1)
            self.assertIsNone(result["run"]["cost"]["billed"])

    def test_resume_only_monitors_existing_run_without_new_authorization(self):
        with TemporaryDirectory() as temp:
            out,api=Path(temp)/"run",FakeGitHub()
            api.in_progress=True
            with self.assertRaisesRegex(ArenaError,"Resume"):
                orchestrator.run(LIVE,out,Connections({}),authorize=True,adapter=GitHubBackend(api,timeout_seconds=0))
            self.assertEqual(len(api.calls),1)
            api.in_progress=False
            result=orchestrator.resume(out,Connections({}),adapter=GitHubBackend(api))
            self.assertEqual(result["run"]["status"],"COMPLETED")
            self.assertEqual(len(api.calls),1)
            self.assertEqual(api.inspections,1)

    def test_failed_workflow_never_dispatches_another_paid_execution(self):
        with TemporaryDirectory() as temp:
            out,api=Path(temp)/"run",FakeGitHub()
            api.failed=True
            with self.assertRaisesRegex(ArenaError,"Native workflow failed"):
                orchestrator.run(LIVE,out,Connections({}),authorize=True,adapter=GitHubBackend(api))
            with self.assertRaisesRegex(ArenaError,"retry refused"):
                orchestrator.resume(out,Connections({}),adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls),1)
            self.assertIsNone(orchestrator.status(out)["consumption"]["omc"]["remaining"])

    def test_ambiguous_dispatch_cannot_be_reissued(self):
        with TemporaryDirectory() as temp:
            out,api=Path(temp)/"run",FakeGitHub()
            api.network_uncertain=True
            with self.assertRaises(ArenaError):
                orchestrator.run(LIVE,out,Connections({}),authorize=True,adapter=GitHubBackend(api))
            self.assertEqual(orchestrator.status(out)["status"],"NEEDS_RECONCILIATION")
            with self.assertRaisesRegex(ArenaError,"retry refused"):
                orchestrator.resume(out,Connections({}),adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls),1)

    def test_unconfirmed_usage_stays_unknown_in_controller_and_public_result(self):
        with TemporaryDirectory() as temp:
            api=FakeGitHub()
            api.unavailable_usage=True
            result=orchestrator.run(LIVE,Path(temp)/"run",Connections({}),authorize=True,adapter=GitHubBackend(api))
            self.assertFalse(result["controller"]["consumption"]["omc"]["complete"])
            self.assertIsNone(result["controller"]["consumption"]["provider_posts"]["remaining"])
            self.assertEqual(result["controller"]["consumption"]["omc"]["observed_attempts"],11)

    def test_result_from_another_frozen_source_is_rejected(self):
        with TemporaryDirectory() as temp:
            api=FakeGitHub()
            api.wrong_provenance=True
            with self.assertRaisesRegex(ArenaError,"does not match"):
                orchestrator.run(LIVE,Path(temp)/"run",Connections({}),authorize=True,adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls),1)


if __name__=="__main__":
    unittest.main()
