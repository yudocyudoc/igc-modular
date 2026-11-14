"""Offline coffee feedback contracts: original Ledger/ATMS/policies, no provider.

All fake diagnostics in these tests are *test fixtures*. The live feedback job
separately authenticates the real Modelica/Buffalo artifact bytes and CSVs.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from arena.common import ArenaError, digest
from arena import coffee_feedback as cf
from arena.coffee_domain import build_case
from arena.coffee_adapters import m as adapter_m
import test_coffee_domain


class CoffeeFeedbackTests(unittest.TestCase):
    setUp = test_coffee_domain.CoffeeDomainTests.setUp

    def env(self):
        return {"GITHUB_REPOSITORY":cf.REPO,
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_EVENT_NAME":"push",
                "GITHUB_RUN_ID":"999"}

    def test_only_main_first_attempt_with_no_provider_and_r2_secrets(self):
        self.assertEqual(cf.identity(self.env()),999)
        for key,value in (("GITHUB_REF","refs/heads/feature"),
                          ("GITHUB_RUN_ATTEMPT","2"),
                          ("GITHUB_REPOSITORY","any/other"),
                          ("GITHUB_EVENT_NAME","pull_request"),
                          ("CLOUDFLARE_API_TOKEN","test"),
                          ("CT03_R2_ACCESS_KEY_ID","test")):
            env=self.env();env[key]=value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ArenaError,
                                            "MAIN_FIRST|CREDENTIAL"):
                    cf.identity(env)

    def test_bound_and_hash_pinned_source_zip_and_no_member_escape(self):
        def pack(files):
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
                for k,v in files:
                    z.writestr(k,v)
            return buf.getvalue()
        safe=pack([("result.json",b"{}"),("receipt.json",b"{}")])
        self.assertEqual(set(cf._safe_archive(safe,
                             expected_digest="sha256:"+hashlib.sha256(safe).hexdigest())),
                         {"result.json","receipt.json"})
        with self.assertRaisesRegex(ArenaError,"GITHUB_ZIP_SHA256_MISMATCH"):
            cf._safe_archive(safe+b"change",
                expected_digest="sha256:"+hashlib.sha256(safe).hexdigest())
        for entries in (
            [("../truth.json",b"secret")],
            [("result.json",b"ok"),("result.json",b"tamper")]
        ):
            raw=pack(entries)
            with self.assertRaisesRegex(ArenaError,"UNSAFE_OR_DUPLICATE"):
                cf._safe_archive(raw,
                    expected_digest="sha256:"+hashlib.sha256(raw).hexdigest())

    def test_source_run_and_artifact_identity_fail_closed(self):
        class FakeAPI:
            def __init__(self,sha):
                self.sha=sha
                self.requested=[]
            def run(self,id):
                self.requested.append(("run",id))
                return {"id":78,"head_sha":self.sha,"head_branch":"main",
                        "path":cf.G2_WORKFLOW,"event":"workflow_dispatch",
                        "run_attempt":1,"status":"completed",
                        "conclusion":"success"}
            def repo(self,method,path,**kwargs):
                self.requested.append((method,path))
                raise AssertionError("must fail before artifact download")
        with self.assertRaisesRegex(ArenaError,"SOURCE_RUN_IDENTITY_FAILED"):
            cf._fetch(FakeAPI("a"*40),run_id=cf.G2_RUN_ID,
                      sha=cf.G2_SHA,artifact_id=cf.G2_ARTIFACT_ID,
                      archive_sha=cf.G2_ARCHIVE_SHA,
                      workflow=cf.G2_WORKFLOW,artifact_name="ignored",
                      event="workflow_dispatch")

    def test_D_original_fixed_decision_and_M_original_abstention_are_real_retrievals(self):
        bridge=cf._original_bridge()
        clock="2026-11-14T04:00:00+00:00"
        source="sha256:"+"a"*64
        for arm in ("D","M"):
            with self.subTest(arm=arm):
                db=self.root/(arm+"-own.sqlite")
                ctx=bridge.make_context(experiment="Coffee",world="Peak",
                    round_id="R0",arm=arm,condition="B0",source_hash=source)
                if arm=="D":
                    parent="sha256:"+"c"*64
                else:
                    case=build_case(self.public,test_coffee_domain.ASSUMPTIONS,environment={})
                    _,manifest=adapter_m.generate(case)
                    graph=manifest["candidates"][0]["full_ast"]
                    parent=digest(graph)
                diag={
                    "arm":arm,"condition":"B0","source_hash":source,
                    "parent_hash":parent,"evidence":"G2",
                    "trace_sha256":"sha256:"+"d"*64,
                    "own_evidence_only":True,"no_future_truth":True,
                    "observations":[],
                }
                saved=bridge.record_feedback(
                    db,ctx,parent_hash=parent,diagnostic=diag,recorded_at=clock)
                memory=bridge.recover_feedback(
                    db,ctx,parent_hash=parent,as_known_at=clock)
                self.assertEqual(saved["diagnostic_hash"],memory["diagnostic_hash"])
                self.assertTrue(memory["retrieval"]["projection_hash"])
                if arm=="D":
                    decision=bridge.d_fixed_decision(
                        db,ctx,parent_hash=parent,as_known_at=clock)
                    self.assertEqual(decision["status"],"RATIFIED")
                    self.assertFalse(decision["model_revision"])
                else:
                    composer,_,_=adapter_m.original()
                    _,classes,_=composer.load_registry(adapter_m.REGISTRY)
                    decision=bridge.own_m_decision(
                        db,ctx,parent_graph=graph,as_known_at=clock,classes=classes)
                    self.assertEqual(decision["status"],"ABSTAINED")
                    self.assertEqual(decision["reason"],
                                     "NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS")
                    self.assertIsNone(decision["new_model"])
                self.assertEqual(decision["feedback_hash"],saved["diagnostic_hash"])
                self.assertEqual(decision["retrieved_before_policy"],memory["retrieval"])
                disposed=bridge.persist_disposition(
                    db,ctx,decision=decision,recorded_at=clock)
                self.assertEqual(disposed["status"],
                                 "DISPOSITION_RECORDED_WITH_OWN_FEEDBACK_SUPPORT")
        # M's SQLite does not contain D's case, even if the query claims a
        # different arm. Retrieval cannot expose a rival's evidence.
        d_ctx=bridge.make_context(experiment="Coffee",world="Peak",
                    round_id="R0",arm="D",condition="B0",source_hash=source)
        with self.assertRaisesRegex(ValueError,"NO_CURRENT_FEEDBACK"):
            bridge.recover_feedback(self.root/"M-own.sqlite",d_ctx,
                      parent_hash="sha256:"+"c"*64,as_known_at=clock)

    def test_g1_native_cannot_be_misrepresented_as_G2(self):
        with self.assertRaises((ArenaError, KeyError)):
            cf._verify_b({})
        with self.assertRaises((ArenaError, KeyError)):
            cf._verify_g2({})
