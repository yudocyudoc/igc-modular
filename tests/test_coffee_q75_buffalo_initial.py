"""Q75 first Buffalo initial-prompt contract. No provider, Modelica or R2."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arena import coffee_q75_buffalo_initial as q
from arena.common import ArenaError, digest


class Offline(unittest.TestCase):
    def test_initial_not_revision_and_exact_w01_is_required(self):
        process={
            "case_day_sha256":"sha256:"+"a"*64,
            "alternatives":["FCFS_READY_ASSUMED","PRIORITIZE_MILK_READY"],
            "physical":{
                "resource_units_from_hydra":{"barista":2,"prep_space":2,
                     "espresso_group":3,"steam_wand":1,"pickup_pass":1},
                "resource_ids_from_dossier":{"steam_wand":["W01"]},
                "policy_selection_semantics":{
                    "PRIORITIZE_MILK_READY":"first executable milk then first executable FCFS"},
                "duration_min_assumed_not_calibrated":{"espresso_auto_min":1.5}
            },
            "question":q.FIXED_QUESTION
        }
        packet={"status":"PREPARED_NOT_DELIVERED_TO_PRODUCER",
                "producer_response":"NOT_EXECUTED",
                "operation_known":process}
        packet["input_sha256"]=digest({k:v for k,v in packet.items()})
        with patch.object(q,"gate",return_value=(process,{"B":packet})):
            req=q.make_request({})
            self.assertEqual(req["round_kind"],"initial")
            self.assertIsNone(req["parent_model"])
            self.assertNotIn("-3.837",req["prompt"])
            self.assertIn("W01",req["prompt"])
            self.assertIn("one pickup pass",req["prompt"])
            self.assertFalse(req["original_B0_R1_reused"])
            self.assertEqual(req["max_provider_posts"],1)
            self.assertEqual(req["max_completion_tokens"],16000)
            self.assertTrue(req["not_a_Q75_P90_prediction"])
            process["physical"]["resource_units_from_hydra"]["steam_wand"]=2
            with self.assertRaises(ArenaError):q.make_request({})

    def test_no_fake_permission_or_review_on_PR(self):
        with self.assertRaises(ArenaError):q.manual_identity({})
        env={"GITHUB_REPOSITORY":q.REPOSITORY,
             "GITHUB_EVENT_NAME":"pull_request","GITHUB_REF":"refs/heads/main",
             "GITHUB_RUN_ATTEMPT":"1","COFFEE_Q75_B_INITIAL_AUTH":"yes",
             "GITHUB_SHA":"a"*40,"GITHUB_RUN_ID":"123",
             "GITHUB_WORKFLOW_REF":q.REPOSITORY+"/"+q.WORKFLOW+"@refs/heads/main"}
        with self.assertRaises(ArenaError):q.manual_identity(env)
        env["GITHUB_EVENT_NAME"]="workflow_dispatch"
        self.assertEqual(q.manual_identity(env),("a"*40,123))
        env["CT03_R2_ACCESS_KEY_ID"]="secret"
        with self.assertRaises(ArenaError):q.manual_identity(env)

    def test_budget_separate_no_omc_no_r2(self):
        self.assertEqual(q.MAX_POSTS,1)
        self.assertEqual(q.MAX_TOKENS,16000)
        self.assertEqual(q.MODEL,"@cf/zai-org/glm-5.3-flash")
        self.assertEqual(q.WORKFLOW,".github/workflows/coffee-q75-buffalo-initial-manual.yml")


class AuthenticatedArchives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory=os.environ.get("ARENA_PUBLIC_ZIP_DIR")
        if not directory:
            raise unittest.SkipTest("requires eight real pinned public archives in dedicated workflow")
        cls.root=Path(directory)
        cls.dossier=Path("experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json")

    def test_real_public_q75_first_initial_prompt_has_no_delta(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)/"initial"
            inp=q.dry_run(self.root,self.dossier,d)
            self.assertEqual(inp["provider_status"],"NOT_SENT")
            self.assertIn("W01",inp["prompt"])
            self.assertIn("PRIORITIZE_MILK_READY",inp["prompt"])
            self.assertNotIn("-3.837",inp["backgroundKnowledge"])
            self.assertEqual(json.loads((d/"request.json").read_text())["request_sha256"],
                             inp["request_sha256"])
            dry=json.loads((d/"dry-run.json").read_text())
            self.assertEqual(dry["outbound_provider_posts"],0)
            self.assertTrue(dry["separate_approval_needed"])
            self.assertEqual(dry["cost_ceiling"]["posts"],1)
            self.assertEqual(dry["cost_ceiling"]["completion_tokens_per_request"],16000)
            with self.assertRaises(ArenaError):q.dry_run(self.root,self.dossier,d)

if __name__=="__main__":unittest.main()
