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
    """Transport fixture only. No actual GitHub/provider/solver operations."""
    repository = "yudocyudoc/IGC"

    def __init__(self):
        self.settings = config.load(LIVE)["github"]
        self.calls, self.variables = [], []
        self.failed = None
        self.network_uncertain = False
        self.in_progress = False
        self.inspections = 0
        self.unavailable_usage = False

    def inspect(self, settings, *, configure=False):
        self.inspections += 1
        if settings != self.settings:
            raise AssertionError("Different protocol")

    def variable(self, environment, name, value):
        self.variables.append((environment, name, value))

    def dispatch(self, workflow, ref, inputs):
        self.calls.append((workflow, ref, copy.deepcopy(inputs)))
        if self.network_uncertain:
            raise ArenaError("Network disconnected after dispatch")
        return len(self.calls)*10

    def run(self, run_id):
        workflow = self.calls[run_id//10-1][0]
        failure = self.failed and self.failed in workflow
        return {"id": run_id, "head_sha": self.settings["freeze_sha"], "head_branch": self.settings["ref"],
                "event": "workflow_dispatch", "run_attempt": 1, "path": ".github/workflows/"+workflow,
                "status": "in_progress" if self.in_progress else "completed",
                "conclusion": "failure" if failure else "success", "html_url": "https://github.com/test/run/"+str(run_id)}

    def artifact(self, run_id, name):
        if "postlock-score" in name:
            return {"score-post-lock.json": json.dumps({"schema": "igc-ct03-paired-prospective-evaluation/1.0",
                    "candidate_denominator": 13, "lock_sha256": "sha256:"+"a"*64,
                    "scientific_scope": "SYNTHETIC_INTRAFAMILY_SINGLE_WORLD"}).encode(),
                    "archive-record.json": json.dumps({"github_run_id": 30, "frozen_code_sha": self.settings["freeze_sha"],
                    "lock_sha256": "sha256:"+"a"*64}).encode()}
        if self.unavailable_usage:
            raise ArenaError("Artifact missing")
        suffix = f" attempted; GitHub run {run_id}; code {self.settings['freeze_sha']}\n"
        if "dm-raw" in name:
            return {"dm-ten/attempts.log": "".join(arm+str(i)+suffix for arm in "DM" for i in range(1,6)).encode(),
                    "producer-12/m-revision-attempts.log": "".join("M"+str(i)+suffix for i in range(6)).encode()}
        return {"b-provider-attempts.log": "".join("B-"+mode+suffix for mode in ("initial","revision")).encode(),
                "b-physical-attempts.log": "".join("B-"+mode+suffix for mode in ("initial","revision")).encode()}


class RemoteCoordinatorTests(unittest.TestCase):
    def test_single_approval_chains_four_original_workflows_with_automatic_ids_and_budget(self):
        with TemporaryDirectory() as temp:
            api = FakeGitHub()
            result = orchestrator.run(LIVE, Path(temp)/"run", Connections({}), authorize=True, adapter=GitHubBackend(api))
            self.assertEqual(result["run"]["status"], "COMPLETED")
            self.assertEqual(len(api.calls), 4)
            self.assertEqual(api.calls[1][2]["public_release_run_id"], "10")
            self.assertEqual(api.calls[2][2]["producer_run_id"], "20")
            self.assertEqual(api.calls[3][2]["lock_run_id"], "30")
            self.assertIn(("arena-ct03-producer", "CT03_APPROVED_RELEASE_RUN_ID", "10"), api.variables)
            self.assertIn(("arena-ct03-producer", "CT03_EXTERNAL_CUSTODIAN_ACK", "external_private_world_attempted_once"), api.variables)
            self.assertEqual(result["run"]["consumption"]["omc"]["observed_attempts"], 19)
            self.assertEqual(result["run"]["consumption"]["provider_posts"]["observed_attempts"], 2)
            self.assertIsNone(result["run"]["cost"]["billed"])

    def test_resume_only_monitors_existing_run_and_does_not_ask_approval_again(self):
        with TemporaryDirectory() as temp:
            out, api = Path(temp)/"run", FakeGitHub()
            api.in_progress = True
            with self.assertRaisesRegex(ArenaError, "Resume"):
                orchestrator.run(LIVE, out, Connections({}), authorize=True,
                                 adapter=GitHubBackend(api, timeout_seconds=0))
            self.assertEqual(len(api.calls), 1)
            api.in_progress = False
            result = orchestrator.resume(out, Connections({}), adapter=GitHubBackend(api))
            self.assertEqual(result["run"]["status"], "COMPLETED")
            self.assertEqual(len(api.calls), 4)
            self.assertEqual(api.inspections, 1)

    def test_provider_or_solver_stage_failure_never_opens_reserve_or_retries(self):
        with TemporaryDirectory() as temp:
            out, api = Path(temp)/"run", FakeGitHub()
            api.failed = "producer"
            with self.assertRaisesRegex(ArenaError, "Remote stage failed"):
                orchestrator.run(LIVE, out, Connections({}), authorize=True, adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls), 2)
            with self.assertRaisesRegex(ArenaError, "retry refused"):
                orchestrator.resume(out, Connections({}), adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls), 2)
            self.assertIsNone(orchestrator.status(out)["consumption"]["omc"]["remaining"])

    def test_ambiguous_dispatch_cannot_be_reissued(self):
        with TemporaryDirectory() as temp:
            out, api = Path(temp)/"run", FakeGitHub()
            api.network_uncertain = True
            with self.assertRaises(ArenaError):
                orchestrator.run(LIVE, out, Connections({}), authorize=True, adapter=GitHubBackend(api))
            self.assertEqual(orchestrator.status(out)["status"], "NEEDS_RECONCILIATION")
            with self.assertRaisesRegex(ArenaError, "retry refused"):
                orchestrator.resume(out, Connections({}), adapter=GitHubBackend(api))
            self.assertEqual(len(api.calls), 1)

    def test_missing_usage_is_reported_unknown_while_preserving_successful_result(self):
        with TemporaryDirectory() as temp:
            api = FakeGitHub()
            api.unavailable_usage = True
            result = orchestrator.run(LIVE, Path(temp)/"run", Connections({}), authorize=True, adapter=GitHubBackend(api))
            self.assertFalse(result["run"]["consumption"]["omc"]["complete"])
            self.assertIsNone(result["run"]["consumption"]["provider_posts"]["remaining"])
            self.assertEqual(result["run"]["consumption"]["omc"]["observed_attempts"], 1)

    def test_absent_optional_attempt_log_does_not_become_confirmed_zero(self):
        with TemporaryDirectory() as temp:
            api = FakeGitHub()
            original = api.artifact

            def artifact(run_id, name):
                files = original(run_id, name)
                return {key:value for key,value in files.items() if not key.endswith("m-revision-attempts.log")}

            api.artifact = artifact
            result = orchestrator.run(LIVE, Path(temp)/"run", Connections({}), authorize=True, adapter=GitHubBackend(api))
            self.assertFalse(result["run"]["consumption"]["omc"]["complete"])
            self.assertIsNone(result["run"]["consumption"]["omc"]["remaining"])
            self.assertTrue(result["run"]["consumption"]["provider_posts"]["complete"])



class DispatchResponseTests(unittest.TestCase):
    def test_dispatch_requests_confirmed_run_id_on_2026_api(self):
        api = GitHub("yudocyudoc/IGC", Secret("fixture-token", "env:GH_TOKEN"))
        received = []

        def reply(method, path, payload=None):
            received.append((method, path, payload))
            return {"workflow_run_id": 314, "run_url": "https://api.github.com/run/314",
                    "html_url": "https://github.com/run/314"}

        api.repo = reply
        run = api.dispatch("arena-ct03-public-intake.yml", "some-branch", {"authorized": "yes"})
        self.assertEqual(run, 314)
        self.assertEqual(received, [("POST",
            "/actions/workflows/arena-ct03-public-intake.yml/dispatches",
            {"ref": "some-branch", "inputs": {"authorized": "yes"}, "return_run_details": True})])

    def test_empty_legacy_dispatch_reply_is_not_treated_as_a_safe_retry(self):
        api = GitHub("yudocyudoc/IGC", Secret("fixture-token", "env:GH_TOKEN"))
        api.repo = lambda *args, **kwargs: None
        with self.assertRaisesRegex(ArenaError, "no confirmed run ID"):
            api.dispatch("arena-ct03-public-intake.yml", "some-branch", {"authorized": "yes"})



if __name__ == "__main__":
    unittest.main()
