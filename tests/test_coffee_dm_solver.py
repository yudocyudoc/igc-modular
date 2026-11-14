"""Strict zero-network contracts for coffee G2; synthetic CSVs are TEST fixtures."""
from contextlib import ExitStack
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
                self.assertIn(f'fileNamePrefix="/work/results/{item["arm"]}/{item["prefix"]}"',text)
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

    def test_zero_provider_failed_omc_is_counted_once_for_every_candidate(self):
        stack,root=self.fixture_plan()
        with stack:
            g2.plan(root)
            write_json(root/"stage-receipt.json",{
                "execution_run_id":999,
                "status":"TWELVE_ORIGINALS_ADMITTED_FOR_ONE_G2_BATCH_NOT_YET_RUN"},
                exclusive=True)
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
