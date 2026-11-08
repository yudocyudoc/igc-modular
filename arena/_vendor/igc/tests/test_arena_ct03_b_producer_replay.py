"""Replay F172-10/11 using the ORIGINAL Bash producer and a local Node stub.

No Buffalo SDK, Cloudflare, Docker, solver, custodian, network, or reserved
truth. The Python B G1/ATMS, plan and projection adapters remain REAL code.
The stub replaces only the Node call and emits synthetic runner receipts.
Linux CI only (the Bash/relative-symlink surface is intentionally exercised).
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_lot_budget import SCHEMA as BUDGET
from test_arena_ct03_b_own_feedback import public

REPO=Path(__file__).resolve().parents[1]
RUN="98765"
SHA="a"*40
BASH=REPO/"scripts/arena_cafe/ct03_b_producer_rounds_once.sh"

NODE_STUB=r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
from scripts.arena_v0_contract import digest
from scripts.arena_cafe.e02_b_feedback import _model_sha
from test_arena_ct03_b_own_feedback import fixture

scenario=os.environ["CT03_NODE_STUB_SCENARIO"]
phase=os.environ["BUFFALO_ROUND_KIND"]
out=Path(os.environ["BUFFALO_OUTPUT"])
out.mkdir(parents=False,exist_ok=False)
native,receipt=fixture()
receipt["round_kind"]=phase
receipt["provider_calls_attempted"]=1
receipt["native_model_available"]=True
if phase=="initial":
    if scenario=="initial_invalid":
        native["model"]["specs"]["stopTime"]=10
        receipt.update({"status":"CT03_NATIVE_HORIZON_MISMATCH",
                        "horizon_matches_case":False,"output_horizon_hours":10})
    else:
        # Original native has an unsupported field: original G1 correctly blocks.
        # The producer must not call OMC or synthesize a delivery observable.
        native["model"]["variables"][0]["subType"]="conveyor"
    receipt["result_sha256"]=_model_sha(native)
    (out/"native-engine-result.json").write_text(json.dumps(native)+"\n")
else:
    parent=json.loads(Path(os.environ["BUFFALO_PARENT_NATIVE"]).read_text())
    original=json.loads(Path(os.environ["BUFFALO_PARENT_RECEIPT"]).read_text())
    own=json.loads(Path(os.environ["BUFFALO_OWN_FEEDBACK"]).read_text())
    receipt["parent_native_sha256"]=original["result_sha256"]
    receipt["own_feedback_sha256"]=digest(own)
    if scenario in ("review_failed","review_preprovider"):
        posts=0 if scenario=="review_preprovider" else 1
        receipt.update({
            "model_returned":False,"native_model_available":False,
            "provider_calls":posts,"provider_calls_attempted":posts,
            "proxy_requests":posts,
            "status":("CT03_PREPROVIDER_NO_NATIVE" if posts==0
                      else "CT03_PROVIDER_ATTEMPT_NO_NATIVE"),
            "result_sha256":None
        })
    elif scenario=="review_invalid":
        native=parent
        native["model"]["specs"]["stopTime"]=10
        receipt.update({"status":"CT03_NATIVE_HORIZON_MISMATCH",
                        "horizon_matches_case":False,"output_horizon_hours":10,
                        "result_sha256":_model_sha(native)})
        (out/"native-engine-result.json").write_text(json.dumps(native)+"\n")
    else:
        raise RuntimeError("CT03_UNDECLARED_NODE_STUB_SCENARIO")
(out/"receipt.json").write_text(json.dumps(receipt)+"\n")
sys.exit(1 if receipt["status"]!="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED" else 0)
'''

def budget(public_case):
    body={
        "schema":BUDGET,"world_public_id":public_case["world_public_id"],
        "source_snapshot_hash":public_case["source_snapshot_hash"],
        "github_run_id":RUN,"github_sha":SHA,
        "world_omc_attempts":1,"dm_initial_omc_attempts":10,
        "m_revision_omc_attempts":0,"b_physical_omc_max":2,
        "global_omc_max":19,
        "dm_feedback_sha256":"sha256:"+"d"*64,
        "m_revision_outcomes_sha256":"sha256:"+"e"*64,
        "new_provider_posts":0,"reserved_truth_read":False
    }
    return {**body,"digest_sha256":digest(body)}

@unittest.skipIf(os.name=="nt", "Actual Bash replays require Linux")
class OriginalBashFailedRunnerReplays(unittest.TestCase):
    def run_replay(self,scenario):
        with TemporaryDirectory() as tmp:
            w=Path(tmp)
            (w/"scripts").symlink_to(REPO/"scripts",target_is_directory=True)
            out=w/"artifacts/ct03-public"
            out.mkdir(parents=True)
            p=public()
            (out/"construction.json").write_bytes(canonical(p)+b"\n")
            counts=w/"artifacts/ct03-budget"
            counts.mkdir(parents=True)
            (counts/"dm-budget.json").write_bytes(canonical(budget(p))+b"\n")
            bindir=w/"bin"
            bindir.mkdir()
            stub=bindir/"node"
            stub.write_text(NODE_STUB,encoding="utf-8")
            stub.chmod(0o755)
            env={
                **os.environ,
                "PYTHONPATH":str(REPO)+os.pathsep+str(REPO/"tests"),
                "PATH":str(bindir)+os.pathsep+os.environ["PATH"],
                "CT03_NODE_STUB_SCENARIO":scenario,
                "CT03_LIVE_BATCH_AUTH":"CT03_ONE_APPROVED_LOT",
                "BUFFALO_MODE":"live",
                "BUFFALO_LIVE_AUTH":"ONE_UPSTREAM_CALL",
                "BUFFALO_CT03_LIVE_AUTH":"CT03_ONE_ROUND_EXPRESS_AUTH",
                "CT03_FROZEN_SHA":SHA,
                "GITHUB_SHA":SHA,"GITHUB_RUN_ID":RUN,
                "GITHUB_EVENT_NAME":"workflow_dispatch",
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_REF":"refs/heads/experiment/arena-ct00-ct02-20261107",
                "CT03_OMC_BUDGET_MAX":"19","CT03_OMC_WORLD_ATTEMPTS":"1",
                "CLOUDFLARE_ACCOUNT_ID":"NO_EXTERNAL_ACCOUNT_STUB",
                "CLOUDFLARE_API_TOKEN":"NO_EXTERNAL_TOKEN_STUB",
                "CT03_DM_COUNT_ONLY_BUDGET":"artifacts/ct03-budget/dm-budget.json"
            }
            run=subprocess.run(["bash",str(BASH)],cwd=w,env=env,
                               capture_output=True,text=True,timeout=50)
            self.assertEqual(run.returncode,0,
                             f"scenario={scenario}\nstdout={run.stdout}\nstderr={run.stderr}")
            root=w/"artifacts/ct03-producer"
            raw=root/"B-thirteenth-row.json"
            self.assertTrue(raw.is_file(),scenario)
            result=json.loads(raw.read_text())
            counts=(root/"b-provider-attempts.log").read_text().splitlines()
            self.assertEqual(len(counts),1 if scenario=="initial_invalid" else 2)
            self.assertFalse((root/"b-physical-attempts.log").exists())
            self.assertFalse((root/"B-physical/initial.mos").exists())
            self.assertFalse((root/"B-revision-physical/initial.mos").exists())
            self.assertEqual(result["row"]["arm"],"B")
            self.assertFalse(result["reserved_truth_read"])
            self.assertIsNone(result["row"]["initial"]["forecast"])
            if scenario=="initial_invalid":
                self.assertEqual(result["row"]["initial"]["status"],"G0_REJECTED")
                self.assertEqual(result["row"]["initial"],result["row"]["final"])
                self.assertFalse(result["second_B_provider_post_observed"])
                self.assertEqual(result["row"]["decision"]["status"],"NOT_EXECUTED")
                self.assertEqual(len(counts),1)
            elif scenario=="review_invalid":
                self.assertEqual(result["row"]["initial"]["status"],"G1_BLOCKED")
                self.assertEqual(result["row"]["final"]["status"],"G0_REJECTED")
                self.assertEqual(result["row"]["decision"]["status"],"REVISED")
                self.assertTrue(result["second_B_provider_post_observed"])
                self.assertIn("HORIZON_MISMATCH",result["revision_stop_or_disposition"])
            else:
                self.assertEqual(result["row"]["initial"]["status"],"G1_BLOCKED")
                self.assertEqual(result["row"]["final"],result["row"]["initial"])
                self.assertEqual(result["row"]["decision"]["status"],"NOT_EXECUTED")
                self.assertEqual(result["second_B_provider_post_observed"],
                                 scenario=="review_failed")
                self.assertIsNotNone(result["second_B_provider_receipt_sha256"])
                self.assertIn(("SECOND_PROVIDER_POST_NO_NATIVE" if scenario=="review_failed"
                               else "SECOND_REVIEW_RUNNER_STOP_BEFORE_PROVIDER_POST"),
                              result["revision_stop_or_disposition"])

    def test_failed_second_provider_post_preserves_receipt_and_cost(self):
        self.run_replay("review_failed")

    def test_preprovider_second_runner_stop_preserves_zero_post(self):
        self.run_replay("review_preprovider")

    def test_initial_horizon_mismatch_preserves_g0_thirteenth_slot(self):
        self.run_replay("initial_invalid")

    def test_revised_horizon_mismatch_preserves_g0_thirteenth_slot(self):
        self.run_replay("review_invalid")

if __name__=="__main__":
    unittest.main()
