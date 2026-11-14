"""Strict zero-network contracts for coffee G2; synthetic CSVs are TEST fixtures."""
from contextlib import ExitStack
import os
import csv
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import test_coffee_domain
from arena.common import ArenaError, digest, write_json
from arena.coffee_domain import build_case
from arena.coffee_native_dm import prepare
from arena import coffee_dm_solver as g2
from arena import coffee_dm_campaign as dm


class CoffeeDMModelicaTests(TestCase):
    setUp=test_coffee_domain.CoffeeDomainTests.setUp

    def env(self):
        return {"GITHUB_EVENT_NAME":"workflow_dispatch",
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_REPOSITORY":g2.REPO,
                "GITHUB_RUN_ATTEMPT":"1", "GITHUB_RUN_ID":"999",
                "GITHUB_SHA":"b"*40,
                "COFFEE_DM_OMC_AUTH":"yes",
                "COFFEE_DM_OMC_MAX":"12",
                "RUNNER_TEMP":str(self.root)}

    def test_identity_enforces_authorization_budgets_and_no_private_provider(self):
        self.assertEqual(g2.identity(self.env()),999)
        for key,value in (("GITHUB_EVENT_NAME","push"),
                          ("GITHUB_REF","refs/heads/branch"),
                          ("GITHUB_RUN_ATTEMPT","2"),
                          ("COFFEE_DM_OMC_AUTH","no"),
                          ("COFFEE_DM_OMC_MAX","13"),
                          ("CT03_R2_ACCESS_KEY_ID","SECRET"),
                          ("CLOUDFLARE_API_TOKEN","SECRET")):
            env=self.env();env[key]=value
            with self.subTest(key=key),self.assertRaises(ArenaError):
                g2.identity(env)

    def test_source_zip_denies_unknown_bytes(self):
        with self.assertRaisesRegex(ArenaError,"ORIGINAL_NATIVE_ARTIFACT_HASH_MISMATCH"):
            g2.zip_bytes(b"not a native result")

    def test_no_second_workflow_run_without_independent_reconciliation(self):
        class API:
            def __init__(self, prior):
                self.prior=prior
            def repo(self, verb, endpoint):
                self.verb=verb
                return {"total_count":len(self.prior),
                        "workflow_runs":[{"id":v} for v in self.prior]}
        self.assertTrue(g2.history(API([999]),999)["first_g2_batch"])
        with self.assertRaisesRegex(ArenaError,"PRIOR_RUN_REQUIRES"):
            g2.history(API([999,888]),999)
        with patch.object(g2, "reconcile_no_simulation",return_value={}):
            reconciled = g2.history(API([999,g2.NO_SIMULATION_RECOVERY["run_id"]]),999)
        self.assertTrue(reconciled["one_verified_execution_bug_recovery"])
        self.assertEqual(reconciled["previous_omc_invocations_spent"],12)
        with self.assertRaisesRegex(ArenaError,"PRIOR_RUN_REQUIRES"):
            g2.history(API([999,g2.NO_SIMULATION_RECOVERY["run_id"],777]),999)

    def fixture_plan(self):
        source=build_case(self.public,test_coffee_domain.ASSUMPTIONS,environment={})
        case_sha=digest(source)
        stack=ExitStack()
        for k,value in (
            ("CASE_SHA256",case_sha),
            ("PUBLIC_SHA256",source["public_sha256"]),
            ("SOURCE_RUN_ID",123),
            ("SOURCE_PACKAGE_SHA256",source["source_package_sha256"]),
            ("SELECTION",source["selection"]),
            ("ARTIFACT_ID",77),
        ):
            stack.enter_context(patch.object(dm,k,value))
        stack.enter_context(patch.object(g2,"ARTIFACT_ID",77))
        root=self.root/"g2"
        input_=root/"input"
        input_.mkdir(parents=True)
        import shutil
        shutil.copytree(self.public,input_/"public")
        prepare(input_/"public",test_coffee_domain.ASSUMPTIONS,
                input_/"native",environment={},verify_original=False)
        write_json(input_/"attestation.json",{
            "status":"EXACT_GITHUB_PUBLIC_SOURCE_VERIFIED",
            "source_artifact_id":77,"case_sha256":case_sha},exclusive=True)
        dm.audit(input_)
        return stack, root

    def test_original_twelve_mos_plans_are_own_arm_once_and_no_omc(self):
        stack,root=self.fixture_plan()
        with stack:
            plan=g2.plan(root)
            self.assertEqual(len(plan["candidates"]),12)
            self.assertEqual(plan["max_new_omc_attempts"],12)
            self.assertEqual(plan["max_simulations"],12)
            self.assertEqual(plan["modelica_image"],g2.IMAGE)
            self.assertEqual(sum(item["arm"]=="D" for item in plan["candidates"]),6)
            self.assertEqual(sum(item["arm"]=="M" for item in plan["candidates"]),6)
            for item in plan["candidates"]:
                text=(root/item["script"]).read_text()
                self.assertEqual(text.count("simulate("),1)
                self.assertEqual(text.count("checkModel("),1)
                self.assertIn(f'fileNamePrefix="results/{item["arm"]}/{item["prefix"]}"',text)
                self.assertNotIn('fileNamePrefix="/work/',text)
                self.assertNotIn("ct03",text.lower())
                self.assertNotIn("R2",text)
            self.assertFalse((root/"attempts.jsonl").exists())
            with self.assertRaisesRegex(ArenaError,"REFUSE_COMMAND_OVERWRITE"):
                g2.plan(root)

    def test_csv_validation_balance_monotonicity_and_counter(self):
        p=self.root/"test.csv"
        item={"arm":"D","counter":"delivered","stocks":["s1"],
              "loss_counter":"lost"}
        def emit(bad=None):
            with p.open("w",newline="",encoding="utf-8") as fd:
                writer=csv.DictWriter(fd,fieldnames=["time","delivered","s1","lost"])
                writer.writeheader()
                for n in range(g2.INTERVALS+1):
                    t=g2.HORIZON*n/g2.INTERVALS
                    mass=10.0*t
                    if bad=="negative" and n==30: mass=-3
                    if bad=="balance" and n==30: mass+=2
                    writer.writerow({"time":repr(t),"delivered":0,
                                     "s1":repr(mass),"lost":0})
        emit()
        res=g2.verify_csv(p,item)
        self.assertEqual(res["samples"],g2.INTERVALS+1)
        self.assertAlmostEqual(res["max_abs_balance_orders"],0,places=9)
        self.assertEqual(res["status"],"G2_NATIVE_CSV_FINITE_NONNEGATIVE_BALANCED_NOT_G3")
        emit("negative")
        with self.assertRaisesRegex(ArenaError,"NEGATIVE_MATERIAL"):
            g2.verify_csv(p,item)
        emit("balance")
        with self.assertRaisesRegex(ArenaError,"MATERIAL_BALANCE_FAILURE"):
            g2.verify_csv(p,item)

    def test_exact_prior_no_simulation_archive_reconciled_or_rejected(self):
        import hashlib
        import io
        import json
        import zipfile
        prior=dict(g2.NO_SIMULATION_RECOVERY)
        rows=[]
        outputs=[]
        attempts=[]
        members={}
        for i in range(12):
            arm="D" if i < 6 else "M"
            label=arm.lower()+f"{i%6:02d}"
            cls=f"TestModel{i}"
            ident=f"{arm}-TEST{i}"
            model="sha256:"+"a"*64
            script="sha256:"+"b"*64
            logpath=f"logs/{arm}/{label}.log"
            scriptpath=f"commands/{label}.mos"
            log=(f"Check of {cls} completed successfully\n"
                 'resultFile = ""\n'
                 f"Simulation execution failed for model: {cls}\n"
                 f"/bin/sh: 1: /work//work/results/{arm}/{label}: not found\n").encode()
            members[logpath]=log
            members[scriptpath]=(f'checkModel({cls});\n'
                f'simulate({cls},fileNamePrefix="/work/results/{arm}/{label}");\n').encode()
            rows.append({"arm":arm,"prefix":label,"id":ident,
                         "modelica_class":cls,"log":logpath,
                         "script":scriptpath,"model_sha256":model,
                         "script_sha256":script})
            attempts.append({"candidate_id":ident,"attempt_number":i+1,
                             "run_id":prior["run_id"],"reserved_before_omc":True,
                             "model_sha256":model,"script_sha256":script})
            outputs.append({"arm":arm,"candidate_id":ident,
                            "attempt_reserved":True,"attempt_number":i+1,
                            "omc_exit_code":0,"check_model_completed":True,
                            "status":"G2_CSV_NOT_PRODUCED",
                            "solver_simulation_authenticated":False,
                            "solver_log_sha256":g2.sha_bytes(log)})
        report={
            "status":"ONE_INITIAL_BATCH_EXECUTED_NO_SCIENTIFIC_LOCK",
            "run_id":prior["run_id"],"head_sha":prior["sha"],
            "case_sha256":dm.CASE_SHA256,
            "attempts_reserved":12, "simulations_authenticated":0,
            "maximum_allowed_attempts":12,"truth_access":False,
            "provider_posts":0,"scientific_lock_created":False,
            "no_retries":True,"results":outputs}
        plan={"case_sha256":dm.CASE_SHA256,
              "source_native_artifact_id":g2.ARTIFACT_ID,
              "candidates":rows}
        def archive(*, simulated=False, extra_csv=False):
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as z:
                for name, content in members.items():
                    if simulated and name==rows[0]["log"]:
                        content += b"LOG_SUCCESS\n"
                    z.writestr(name,content)
                z.writestr("plan.json",json.dumps(plan))
                z.writestr("result.json",json.dumps(report))
                z.writestr("attempts.jsonl",
                           "\n".join(json.dumps(a) for a in attempts)+"\n")
                if extra_csv:
                    z.writestr("results/D/d00_res.csv","time,delivered\n0,0\n")
            return buffer.getvalue()
        class API:
            def __init__(self,raw):
                self.raw=raw
            def run(self,id):
                assert id==prior["run_id"]
                return {"id":id,"head_sha":prior["sha"],
                        "path":g2.WORKFLOW,"event":"workflow_dispatch",
                        "head_branch":"main","run_attempt":1,
                        "status":"completed","conclusion":"success"}
            def repo(self,verb,path,**kwargs):
                assert verb=="GET"
                if path.endswith("/jobs?per_page=100"):
                    return {"total_count":1,"jobs":[{
                        "id":prior["job_id"],"status":"completed",
                        "conclusion":"success"}]}
                if path.endswith("/zip"):
                    assert kwargs.get("binary") is True
                    return self.raw
                return {"id":prior["artifact_id"],
                        "name":f'coffee-dm-g2-{prior["run_id"]}',
                        "expired":False,"digest":prior["artifact_digest"],
                        "workflow_run":{"id":prior["run_id"]}}
        def review(raw):
            active={**prior,
                    "artifact_digest":"sha256:"+hashlib.sha256(raw).hexdigest()}
            with patch.object(g2,"NO_SIMULATION_RECOVERY",active):
                return g2.reconcile_no_simulation(API(raw))
        good=archive()
        self.assertEqual(review(good)["historical_simulations_completed"],0)
        with self.assertRaisesRegex(ArenaError,"REAL_CSV_PRESENT"):
            review(archive(extra_csv=True))
        with self.assertRaisesRegex(ArenaError,"SIMULATION_POSSIBLY_RAN"):
            review(archive(simulated=True))
        active={**prior,"artifact_digest":"sha256:"+hashlib.sha256(good).hexdigest()}
        with patch.object(g2,"NO_SIMULATION_RECOVERY",active):
            with self.assertRaisesRegex(ArenaError,"ARCHIVE_BYTES_DIFFER"):
                g2.reconcile_no_simulation(API(good+b"tamper"))

    def test_zero_provider_failed_omc_is_counted_once_for_every_candidate(self):
        if os.name == "nt":
            self.skipTest("Docker execution is Linux-only; static plan tests run on Windows")
        stack,root=self.fixture_plan()
        with stack:
            g2.plan(root)
            write_json(root/"stage-receipt.json",{
                "execution_run_id":999,
                "status":"TWELVE_ORIGINALS_ADMITTED_FOR_ONE_G2_BATCH_NOT_YET_RUN"},
                exclusive=True)
            write_json(root/"history-receipt.json",{
                "one_verified_execution_bug_recovery":False},exclusive=True)
            for path in ("e1-home","e1-libs/msl","e1-libs/systemdynamics"):
                (self.root/path).mkdir(parents=True,exist_ok=True)
            calls=[]
            def fake(argv, **kwargs):
                self.assertEqual(argv[0:3],["docker","run","--rm"])
                self.assertIn("--network",argv)
                self.assertIn("none",argv)
                self.assertEqual(argv[-2],"omc")
                calls.append(argv[-1])
                return SimpleNamespace(returncode=1)
            report=g2.run_batch(root,env=self.env(),cli=fake)
            self.assertEqual(report["attempts_reserved"],12)
            self.assertEqual(report["simulations_authenticated"],0)
            self.assertEqual(len(calls),12)
            self.assertEqual(len((root/"attempts.jsonl").read_text().splitlines()),12)
            self.assertEqual({r["status"] for r in report["results"]},
                             {"OMC_EXIT_NONZERO"})
            with self.assertRaisesRegex(ArenaError,"REFUSE_RERUN"):
                g2.run_batch(root,env=self.env(),cli=fake)
            self.assertEqual(len(calls),12)
