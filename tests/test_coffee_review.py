"""Coffee B R1: currentModel review staging and no-retry contracts (offline)."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from arena import coffee_review as rev
from arena.common import ArenaError, digest, read_json, write_json
from arena import coffee_dm_campaign as dm
from arena import coffee_feedback as fb
from arena.coffee_adapters.shared import sha_bytes


class BuffaloCoffeeReviewTests(unittest.TestCase):
    def env(self):
        return {"GITHUB_REPOSITORY":rev.REPO,
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_EVENT_NAME":"workflow_dispatch",
                "GITHUB_SHA":"a"*40,
                "GITHUB_RUN_ID":"991234",
                "COFFEE_B_REVIEW_AUTH":"yes"}

    def test_manual_first_attempt_and_no_secret_in_admission(self):
        self.assertEqual(rev.identity(self.env()),("a"*40,991234))
        for key,value in (
            ("GITHUB_REF","refs/heads/fix"),
            ("GITHUB_RUN_ATTEMPT","2"),
            ("GITHUB_EVENT_NAME","push"),
            ("COFFEE_B_REVIEW_AUTH","no"),
            ("CLOUDFLARE_API_TOKEN","forbidden_preflight"),
            ("CT03_R2_ACCESS_KEY_ID","forbidden"),
        ):
            env=self.env();env[key]=value
            with self.subTest(key=key),self.assertRaises(ArenaError):
                rev.identity(env)

    def test_prior_review_dispatch_never_permits_implicit_second_post(self):
        class API:
            def __init__(self,other):
                self.other=other
            def repo(self,method,path,**kw):
                self.assert_path=path
                return {"total_count":len(self.other),
                        "workflow_runs":[{"id":x} for x in self.other]}
        self.assertEqual(rev.history(API([991234]),991234)["other_dispatches"],0)
        with self.assertRaisesRegex(ArenaError,"PRIOR_REVIEW_DISPATCH"):
            rev.history(API([991234,991233]),991234)

    def test_provenance_packet_replay_and_original_public_input_no_rivals(self):
        bridge=fb._original_bridge()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            native={"model":{"variables":[{"name":"Paid Orders","type":"flow",
                          "equation":"10","units":"orders/hour",
                          "inflows":[],"outflows":[],"uniflow":True,
                          "graphicalFunction":{"points":[]}}],
                            "relationships":[],"specs":{
                            "startTime":0,"stopTime":103.237/60,
                            "dt":(103.237/60)/64,"timeUnits":"hour",
                            "integrationMethod":"Euler"}},
                    "supportingInfo":{"title":"fixture","explanation":""}}
            from arena.common import write_json
            write_json(root/"native.json",native)
            parent_sha=sha_bytes((root/"native.json").read_bytes())
            parent_receipt=b'{"test":"parent"}\n'
            case=dm.CASE_SHA256
            ctx=bridge.make_context(experiment="Coffee",world="Peak",
                    round_id="R0",arm="B",condition="B0",source_hash=case)
            diag={"arm":"B","condition":"B0","source_hash":case,
                  "parent_hash":parent_sha,"evidence":"G1",
                  "own_evidence_only":True,"no_future_truth":True,
                  "observations":[],"original_native_file_sha256":parent_sha,
                  "no_silent_model_repair":True}
            db=root/"B-ledger.sqlite"
            t0="2026-11-14T05:22:00.385364+00:00"
            t1="2026-11-14T05:22:00.385365+00:00"
            t2="2026-11-14T05:22:00.385366+00:00"
            saved=bridge.record_feedback(db,ctx,parent_hash=parent_sha,
                diagnostic=diag,recorded_at=t0)
            recovered=bridge.recover_feedback(db,ctx,
                parent_hash=parent_sha,as_known_at=t1)
            b_summary={
                "candidate_count":1,
                "original_engine_revision_status":
                   "NOT_INVOKED_REQUIRES_SEPARATE_PROVIDER_AUTH",
                "as_of_replay_verified_after_packet":True,
                "parent_hash":parent_sha,
                "ledger_sqlite_sha256":sha_bytes(db.read_bytes()),
                "diagnostic_sha256":saved["diagnostic_hash"],
                "retrieved_before_review":recovered["retrieval"],
                "final_sqlite_as_of_replay":{
                    "projection_hash":recovered["retrieval"]["projection_hash"]}
            }
            packet={
                "schema":"arena.coffee-peak.buffalo-review-envelope/1",
                "status":"OWN_G1_FEEDBACK_RETRIEVED_PACKET_PREPARED_NOT_SENT",
                "original_engine_review_invoked":False,
                "revision_budget_authorized":False,
                "new_native_model":None,
                "never_reuse_Engine_generate_without_currentModel":True,
                "truth_access":False,"provider_posts_this_phase":0,
                "parent_native_file_sha256":parent_sha,
                "parent_provider_receipt_sha256":sha_bytes(parent_receipt),
                "currentModel":native["model"],
                "diagnostic_sha256":saved["diagnostic_hash"],
                "retrieved_before_any_possible_review":recovered["retrieval"],
                "own_feedback":diag,
            }
            packet_bytes=(json.dumps(packet)+"\n").encode()
            b_summary["revision_packet_sha256"]=sha_bytes(packet_bytes)
            summary={
                "schema":"arena.coffee-peak.own-ledger-atms-consumption/2",
                "status":"OWN_FEEDBACK_RETRIEVED_DM_POLICIES_INVOKED_B_PACKET_NOT_SENT",
                "case_sha256":case,"as_of_replay_from_final_sqlite":True,
                "reserved_truth_access":False,"provider_posts":0,"new_omc":0,
                "scientific_lock_created":False,
                "logical_temporal_cuts":{
                    "feedback_recorded_at":t0,"retrieval_as_known_at":t1,
                    "disposition_recorded_at":t2},
                "arms":{"B":b_summary}
            }
            original={
                "schema":"arena.coffee-peak.buffalo-public-input/1",
                "case_sha256":case,"public_sha256":dm.PUBLIC_SHA256,
                "execution_run_id":fb.B_RUN_ID,
                "source_artifact_id":dm.ARTIFACT_ID,
                "truth_access":False,"new_omc":0,"provider_posts":0,
                "prompt":"PUBLIC ONLY",
                "problemStatement":"Unknown paid pickups.",
                "backgroundKnowledge":"public-only",
            }
            archive={
                "summary.json":json.dumps(summary).encode(),
                "B-own-review-packet.json":packet_bytes,
                "B-ledger.sqlite":db.read_bytes(),
                "D-ledger.sqlite":b"D_NOT_SHARED","M-ledger.sqlite":b"M_NOT_SHARED",
            }
            source={
                "input.json":json.dumps(original).encode(),
                "provider/receipt.json":parent_receipt,
            }
            with patch.object(fb,"_verify_b",return_value=(native,{},parent_sha,{},{})):
                seen,orig,seen_packet,replayed=rev.validate_sources(
                    archive,source,bridge=bridge)
            self.assertEqual(seen,native)
            self.assertEqual(orig["prompt"],"PUBLIC ONLY")
            self.assertEqual(seen_packet["currentModel"],native["model"])
            self.assertEqual(replayed["predecision_revision_count"],4)
            self.assertEqual(replayed["projection_hash"],
                             recovered["retrieval"]["projection_hash"])
            altered=dict(packet);altered["currentModel"]={"variables":[],"relationships":[]}
            archive["B-own-review-packet.json"]=(json.dumps(altered)+"\n").encode()
            with patch.object(fb,"_verify_b",return_value=(native,{},parent_sha,{},{})):
                with self.assertRaises(ArenaError):
                    rev.validate_sources(archive,source,bridge=bridge)

    def test_attempt_is_reserved_before_any_subprocess_and_never_retried(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            initial={
                "run_id":991234,"run_sha":"a"*40,
                "source_model_sha256":"sha256:"+"c"*64,
                "case_sha256":dm.CASE_SHA256
            }
            write_json(root/"input.json",initial)
            write_json(root/"admission.json",{
                "execution_run":991234,"execution_sha":"a"*40,
                "input_sha256":digest(initial),
                "parent_sha256":initial["source_model_sha256"]})
            calls=[]
            def fail(argv,**kwargs):
                calls.append(argv)
                self.assert_attempt=(root/"attempt.json").is_file()
                self.assertTrue(self.assert_attempt)
                return SimpleNamespace(returncode=1)
            env={**self.env(),"CLOUDFLARE_API_TOKEN":"FAKE_SECRET",
                 "RUNNER_TEMP":tmp}
            with patch("arena.coffee_review.public_config",
                       return_value={"cloudflare":{"account_id":"a"*32}}):
                with self.assertRaisesRegex(ArenaError,"NO_RETRY"):
                    rev.invoke(root,env=env,runner=fail)
                with self.assertRaisesRegex(ArenaError,"ATTEMPT_CONTRACT_FAILED"):
                    rev.invoke(root,env=env,runner=fail)
            self.assertEqual(len(calls),1)
