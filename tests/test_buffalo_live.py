"""BF03/BF04/BF05 regressions: no network, no real provider calls or OMC."""
import csv
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arena.buffalo import execution, physical
from arena.buffalo.gates import validate_candidate, CandidateBlocked
from arena.buffalo.capabilities import pulse_fixture, native_hash
from arena.common import read_json, write_json


class FakeHistory:
    def __init__(self, jobs=None, previous=None, complete=True):
        self.jobs=jobs if jobs is not None else [
            {"name":"BF00-02 - archived real evidence, no provider or OMC",
             "status":"completed","conclusion":"success"},
            {"name":"Original Buffalo - archived public CT03 input - 0 OMC",
             "status":"completed","conclusion":"skipped"}]
        self.previous=previous if previous is not None else [987]
        self.complete=complete

    def repo(self,method,path):
        assert method=="GET"
        if path.startswith("/actions/workflows/buffalo-only.yml/runs?"):
            return {"total_count":len(self.previous),
                    "workflow_runs":[{"id":n} for n in self.previous]}
        if path.startswith("/actions/runs/"):
            return {"total_count":len(self.jobs),"jobs":self.jobs}
        raise AssertionError(path)

    def run(self,rid):
        return {"id":rid,"status":"completed" if self.complete else "in_progress",
                "run_attempt":1,"event":"workflow_dispatch",
                "path":execution.WORKFLOW}


class BuffaloLiveTests(unittest.TestCase):
    def test_reconcile_no_paid_older_original_and_offline_are_separate(self):
        self.assertEqual(execution.reconcile_history(FakeHistory(),current_id=123),[987])

    def test_prior_paid_batch_started_even_if_failed_blocks_retry(self):
        for conclusion in ("success","failure","cancelled",None):
            with self.subTest(conclusion=conclusion):
                api=FakeHistory(jobs=[{"name":execution.LIVE_JOB,
                                       "conclusion":conclusion}])
                with self.assertRaisesRegex(Exception,"ALREADY_STARTED_OR_UNCERTAIN"):
                    execution.reconcile_history(api,123)

    def test_skipped_paid_job_never_counts_as_attempt(self):
        api=FakeHistory(jobs=[{"name":execution.LIVE_JOB,
                               "conclusion":"skipped"}])
        self.assertEqual(execution.reconcile_history(api,123),[987])

    def test_unfinished_previous_and_unknown_jobs_are_blocked(self):
        with self.assertRaisesRegex(Exception,"UNKNOWN_OR_RERUN"):
            execution.reconcile_history(FakeHistory(complete=False),123)
        with self.assertRaisesRegex(Exception,"UNKNOWN_JOB"):
            execution.reconcile_history(FakeHistory(jobs=[{"name":"unknown"}]),123)

    def test_exact_public_template_only_but_buffalo_can_choose_stock_mechanism(self):
        doc=pulse_fixture()
        got=validate_candidate(doc)
        self.assertEqual(got["status"],
                        "ADMISSIBLE_IN_PINNED_MODELICA_SUBSET_NOT_YET_SIMULATED")
        self.assertEqual(got["input_mass_analytic"],3.4)
        self.assertEqual(got["observation_operator"]["modelica_csv_column"],
                         "Delivered")
        self.assertIn("der(Work)",got["translated_modelica_text"])
        altered=pulse_fixture()
        source=next(v for v in altered["model"]["variables"] if v["name"]=="Arrivals")
        source["equation"]="1.7"
        with self.assertRaisesRegex(CandidateBlocked,"PUBLIC_PULSE"):
            validate_candidate(altered)
        # The validator never mutates the candidate it receives.
        self.assertEqual(source["equation"],"1.7")

    def _mock_generation_workspace(self, root):
        from arena.buffalo.feedback import freeze_profile
        batch=root/"artifacts/buffalo-adjust-v1"
        evidence=root/"evidence"
        (evidence/"parent/initial").mkdir(parents=True)
        batch.mkdir(parents=True)
        native=pulse_fixture()
        parent=evidence/"parent/initial/native-engine-result.json"
        write_json(parent,native)
        profile=freeze_profile()
        write_json(batch/"bf02-profile.json",profile)
        write_json(batch/"bf02-own-feedback.json",{
            "profile_sha256":profile["utf8_sha256"],
            "parent_native_sha256":native_hash(native),
            "world_public_id":"PUBLIC","source_snapshot_hash":"sha256:source",
            "own_semantic_diagnostics":{"diagnostics":[]}})
        write_json(batch/"live-admission.json",{
            "run_id":123,"sha":"a"*40,
            "profile_sha256":profile["utf8_sha256"]})
        return batch,evidence,native,profile

    def _run_mock_bf03_bf04(self, *, reject_bf03=False):
        with TemporaryDirectory() as d:
            root=Path(d)
            batch,evidence,native,profile=self._mock_generation_workspace(root)
            observed=[]
            construction={"world_public_id":"PUBLIC",
                          "source_snapshot_hash":"sha256:source"}
            def visible(_root,*args):
                path=Path(args[-1])
                write_json(path,{"question":"public-construction"})
                return 0
            def called(argv,**kwargs):
                env=kwargs["env"]
                phase=env["BUFFALO_ADJUST_ROUND"]
                observed.append((phase,env.get("BUFFALO_PARENT_NATIVE"),
                                 env.get("BUFFALO_OWN_FEEDBACK")))
                output=Path(env["BUFFALO_ADJUST_OUTPUT"])
                output.mkdir()
                write_json(output/"receipt.json",{
                    "provider_calls":1,"proxy_requests":1,
                    "raw_provider_saved":True,
                    "generation_profile_sha256":profile["utf8_sha256"],
                    "round_kind":phase,"source_snapshot_hash":"sha256:source",
                    "world_public_id":"PUBLIC","runner_error":None,
                    "model_returned":True,"provider_usage":{"completion_tokens":10}})
                write_json(output/"provider-raw.json",{"success":True})
                write_json(output/"native-engine-result.json",native)
                return SimpleNamespace(returncode=0)
            def validate(_):
                if reject_bf03:
                    raise CandidateBlocked("G1_INVALID_PARENT")
                return {"status":"ADMISSIBLE_IN_PINNED_MODELICA_SUBSET_NOT_YET_SIMULATED",
                        "translated_modelica_text":"model Neutral end Neutral;",
                        "observation_operator":{"modelica_csv_column":"Delivered"},
                        "public_input_flow_name":"Arrivals"}
            with (patch.object(execution,"identity",return_value=("a"*40,123)),
                  patch.object(execution,"public_input",return_value=construction),
                  patch.object(execution,"module",side_effect=visible),
                  patch.object(execution,"validate_candidate",side_effect=validate),
                  patch.dict(os.environ,{"CLOUDFLARE_API_TOKEN":"unit-test-not-real"})):
                if reject_bf03:
                    with self.assertRaisesRegex(Exception,"G1_BLOCKED_STOP"):
                        execution.generate(root,evidence,runner=called)
                    self.assertFalse((batch/"bf04-attempt.json").exists())
                else:
                    result=execution.generate(root,evidence,runner=called)
                    self.assertEqual(result["provider_posts_reported"],2)
                    self.assertTrue((batch/"bf03-g1.json").exists())
                    self.assertTrue((batch/"bf04-g1.json").exists())
            return observed

    def test_paid_sequence_two_original_invocations_and_parent_only_in_bf03(self):
        calls=self._run_mock_bf03_bf04()
        self.assertEqual([c[0] for c in calls],["bf03","bf04"])
        self.assertTrue(calls[0][1])
        self.assertTrue(calls[0][2])
        self.assertEqual(calls[1][1],"")
        self.assertEqual(calls[1][2],"")

    def test_bf03_rejected_stops_bf04_and_omc_without_retry(self):
        calls=self._run_mock_bf03_bf04(reject_bf03=True)
        self.assertEqual([c[0] for c in calls],["bf03"])

    def test_failed_parent_is_never_accepted_for_bf04_or_omc(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/"artifacts/buffalo-adjust-v1").mkdir(parents=True)
            write_json(root/"artifacts/buffalo-adjust-v1/live-admission.json",
                       {"run_id":14,"sha":"a"*40})
            with patch.object(execution,"identity",return_value=("a"*40,14)):
                with self.assertRaisesRegex(Exception,"BF_BATCH_RETRY|BF_PROVIDER_SECRET"):
                    # No Cloudflare token => fails before creating any provider attempt.
                    with patch.dict(os.environ,{"CLOUDFLARE_API_TOKEN":""}):
                        execution.generate(root,root)
                with self.assertRaisesRegex(Exception,"BOTH_G1"):
                    execution.physical(root)
            self.assertFalse((root/"artifacts/buffalo-adjust-v1/bf05").exists())

    def test_finalize_missing_receipt_is_unknown_not_zero(self):
        with TemporaryDirectory() as d:
            batch=Path(d)/"artifacts/buffalo-adjust-v1"
            batch.mkdir(parents=True)
            write_json(batch/"bf03-attempt.json",{"reserved":True})
            report=execution.finalize(d)
            self.assertEqual(report["provider_attempts_reserved"],1)
            self.assertEqual(report["provider_posts_observed"],0)
            self.assertTrue(report["attempts"][0]["attempt_may_have_consumed_when_unobserved"])
            self.assertFalse(report["attempts"][0]["provider_consumption_complete"])
            self.assertFalse((batch/"bf04-attempt.json").exists())
            self.assertFalse((batch/"bf05").exists())

    def test_physical_csv_conservation_and_public_residual_not_recalibrated(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            batch=root/"artifacts/buffalo-adjust-v1"
            dest=batch/"bf05"
            dest.mkdir(parents=True)
            (batch/"bf04").mkdir()
            native=pulse_fixture()
            write_json(batch/"bf04/native-engine-result.json",native)
            write_json(batch/"bf04-visible.json",{
                "construction":{"observations":[
                    {"time":0,"delivered":0},{"time":1,"delivered":0.5},
                    {"time":2,"delivered":1},{"time":4,"delivered":2}]}})
            fname=dest/"physical_res.csv"
            with fname.open("w",newline="",encoding="utf-8") as stream:
                writer=csv.DictWriter(stream,fieldnames=[
                    "time","Work","Delivered","Arrivals"])
                writer.writeheader()
                work=delivered=0.0
                for i in range(65):
                    t=i/8
                    arrive=1.7 if i<16 else 0.0
                    writer.writerow({"time":t,"Work":work,
                        "Delivered":delivered,"Arrivals":arrive})
                    finish=0.5*work
                    work+=0.125*(arrive-finish)
                    delivered+=0.125*finish
            plan={"observation_operator":{"modelica_csv_column":"Delivered"},
                  "external_input_flow":"Arrivals"}
            result=physical.evaluate_csv(root,plan)
            self.assertEqual(result["status"],"G2_PHYSICAL_VALID")
            self.assertAlmostEqual(result["source_mass_integral_euler"],3.4)
            self.assertLess(result["max_material_conservation_residual"],1e-9)
            self.assertEqual(result["rmse_denominator"],4)
            self.assertFalse(result["heldout_truth_accessed"])
            self.assertFalse(result["original_buffalo_simulator_parity_proven"])

    def test_omc_failed_attempt_is_recorded_no_retry(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            lib=root/"e1-libs"
            (lib/"msl").mkdir(parents=True)
            (lib/"systemdynamics").mkdir()
            (root/"e1-home").mkdir()
            dest=root/"artifacts/buffalo-adjust-v1/bf05"
            def fake_prepare(_):
                dest.mkdir(parents=True)
                return {"schema":"fake","model_name":"Neutral"}
            def fail_once(argv,**kwargs):
                self.assertEqual(argv.count("omc"),1)
                self.assertIn("--network",argv)
                self.assertIn("none",argv)
                return SimpleNamespace(returncode=1)
            with (patch.object(physical,"prepare",side_effect=fake_prepare),
                  patch.object(physical.subprocess,"run",side_effect=fail_once) as run,
                  patch.object(physical.os,"getuid",return_value=1001,create=True),
                  patch.object(physical.os,"getgid",return_value=1001,create=True),
                  patch.dict(os.environ,{"RUNNER_TEMP":str(root),
                      "GITHUB_RUN_ATTEMPT":"1"})):
                outcome=physical.simulate(root)
            self.assertEqual(outcome["status"],"G2_FAILED_OMC")
            self.assertEqual(run.call_count,1)
            self.assertTrue((dest/"attempt.json").is_file())
            self.assertEqual(read_json(dest/"omc-exit.json")["exit_code"],1)
            self.assertEqual(read_json(dest/"physical-result.json")["omc_attempts"],1)

    def test_workflow_manual_hard_limits_and_no_private_world(self):
        y=(Path(__file__).resolve().parents[1]/
           ".github/workflows/buffalo-only.yml").read_text()
        self.assertIn("  workflow_dispatch:",y)
        self.assertNotIn("\n  push:",y)
        self.assertNotIn("\n  pull_request:",y)
        self.assertIn("environment: arena-provider",y)
        self.assertNotIn("environment: arena-custodian",y)
        self.assertIn("inputs.mode == 'adjust-live'",y)
        self.assertIn("inputs.authorized == 'yes'",y)
        self.assertIn("python -m arena.buffalo.execution admit",y)
        self.assertIn("python -m arena.buffalo.execution generate",y)
        self.assertIn("python -m arena.buffalo.execution physical",y)
        self.assertIn("python -m arena.buffalo.execution finalize",y)
        self.assertIn("if: always()",y)
        self.assertNotIn("python -m arena.cloud world",y)
        self.assertNotIn("python -m arena.cloud dm",y)


if __name__=="__main__":
    unittest.main()
