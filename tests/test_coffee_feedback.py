"""Offline coffee feedback contracts: original Ledger/ATMS/policies, no provider.

All fake diagnostics in these tests are *test fixtures*. The live feedback job
separately authenticates the real Modelica/Buffalo artifact bytes and CSVs.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import io
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from arena.common import ArenaError, digest
from arena import coffee_feedback as cf
from arena.coffee_domain import build_case
from arena.coffee_adapters import d as adapter_d, m as adapter_m
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

    def test_all_thirteen_original_parent_cuts_replay_from_final_closed_sqlites(self):
        """Reproduce *after* storing all decisions in the same D/M SQLite."""
        bridge=cf._original_bridge()
        cuts=cf.logical_feedback_cuts(datetime(2026,11,14,4,0,tzinfo=timezone.utc))
        self.assertLess(cuts["feedback_recorded_at"],cuts["retrieval_as_known_at"])
        self.assertLess(cuts["retrieval_as_known_at"],cuts["disposition_recorded_at"])
        source="sha256:"+"a"*64
        case=build_case(self.public,test_coffee_domain.ASSUMPTIONS,environment={})
        _, d_manifest=adapter_d.generate(case)
        _, m_manifest=adapter_m.generate(case)
        composer,_,_=adapter_m.original()
        _,classes,_=composer.load_registry(adapter_m.REGISTRY)
        cases={"D":d_manifest["candidates"], "M":m_manifest["candidates"]}
        for arm in ("D","M"):
            with self.subTest(arm=arm):
                db=self.root/(arm+"-own.sqlite")
                ctx=bridge.make_context(experiment="Coffee",world="Peak",
                    round_id="R0",arm=arm,condition="B0",source_hash=source)
                receipts=[]
                for index,candidate in enumerate(cases[arm]):
                    if arm=="D":
                        parent=candidate["structure_hash"]
                    else:
                        graph=candidate["full_ast"]
                        parent=digest(graph)
                        self.assertEqual(parent,candidate["full_ast_sha256"])
                    diag={
                        "arm":arm,"condition":"B0","source_hash":source,
                        "parent_hash":parent,"evidence":"G2",
                        "trace_sha256":"sha256:"+f"{index+1:064x}",
                        "own_evidence_only":True,"no_future_truth":True,
                        "observations":[],
                    }
                    stored=bridge.record_feedback(
                        db,ctx,parent_hash=parent,diagnostic=diag,
                        recorded_at=cuts["feedback_recorded_at"])
                    if arm=="D":
                        decision=bridge.d_fixed_decision(
                            db,ctx,parent_hash=parent,
                            as_known_at=cuts["retrieval_as_known_at"])
                        self.assertEqual(decision["status"],"RATIFIED")
                        self.assertFalse(decision["model_revision"])
                    else:
                        decision=bridge.own_m_decision(
                            db,ctx,parent_graph=graph,
                            as_known_at=cuts["retrieval_as_known_at"],classes=classes)
                        self.assertEqual(decision["status"],"ABSTAINED")
                        self.assertEqual(decision["reason"],
                                         "NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS")
                        self.assertIsNone(decision["new_model"])
                    self.assertEqual(decision["feedback_hash"],
                                     stored["diagnostic_hash"])
                    self.assertEqual(decision["retrieved_before_policy"]["as_known_at"],
                                     cuts["retrieval_as_known_at"])
                    disposed=bridge.persist_disposition(
                        db,ctx,decision=decision,
                        recorded_at=cuts["disposition_recorded_at"])
                    self.assertEqual(disposed["status"],
                                     "DISPOSITION_RECORDED_WITH_OWN_FEEDBACK_SUPPORT")
                    receipts.append((parent,decision["retrieved_before_policy"]))
                # All source and decision revisions have been flushed; this
                # readonly connection sees the final on-disk DB, not a
                # temporary in-memory ATMS snapshot.
                with sqlite3.connect(db.resolve().as_uri()+"?mode=ro&immutable=1",
                                     uri=True) as closed_db:
                    self.assertEqual(closed_db.execute(
                        "PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(len(receipts),6)
                for parent,expected in receipts:
                    replay=cf.replay_final_ledger_at_cut(
                        bridge,db,ctx,parent,expected,
                        decision_recorded_at=cuts["disposition_recorded_at"])
                    self.assertEqual(replay["status"],
                                     "ASOF_REPLAYED_FROM_CLOSED_FINAL_SQLITE")
                    self.assertEqual(replay["projection_hash"],
                                     expected["projection_hash"])
                    self.assertEqual(replay["predecision_revision_count"],4)
                    self.assertEqual(replay["final_revision_count"],6)
                    self.assertTrue(replay["separate_disposition_time"])
        # Independent B ledger is still replayable as a G1 packet.
        db=self.root/"B-own.sqlite"
        ctx=bridge.make_context(experiment="Coffee",world="Peak",round_id="R0",
                                arm="B",condition="B0",source_hash=source)
        parent="sha256:"+"c"*64
        diag={"arm":"B","condition":"B0","source_hash":source,
              "parent_hash":parent,"evidence":"G1",
              "own_evidence_only":True,"no_future_truth":True,
              "observations":[]}
        bridge.record_feedback(db,ctx,parent_hash=parent,diagnostic=diag,
                               recorded_at=cuts["feedback_recorded_at"])
        before=bridge.recover_feedback(db,ctx,parent_hash=parent,
                                       as_known_at=cuts["retrieval_as_known_at"])
        with sqlite3.connect(db.resolve().as_uri()+"?mode=ro&immutable=1",
                             uri=True) as closed_db:
            self.assertEqual(closed_db.execute(
                "PRAGMA integrity_check").fetchone()[0],"ok")
        replay=cf.replay_final_ledger_at_cut(
            bridge,db,ctx,parent,before["retrieval"])
        self.assertEqual(replay["predecision_revision_count"],4)
        self.assertEqual(replay["final_revision_count"],4)
        # Lane and parent isolation survive the new timestamp scheme.
        d_ctx=bridge.make_context(experiment="Coffee",world="Peak",
                    round_id="R0",arm="D",condition="B0",source_hash=source)
        with self.assertRaisesRegex(ValueError,"NO_CURRENT_FEEDBACK"):
            bridge.recover_feedback(self.root/"M-own.sqlite",d_ctx,
                      parent_hash=cases["D"][0]["structure_hash"],
                      as_known_at=cuts["retrieval_as_known_at"])

    def test_old_colliding_timestamp_is_rejected_by_final_sqlite_replay(self):
        """Catch precisely the 12 mismatches in Astra's independent audit."""
        bridge=cf._original_bridge()
        db=self.root/"legacy_same_time.sqlite"
        timestamp="2026-11-14T04:44:02.597904+00:00"
        source="sha256:"+"a"*64
        parent="sha256:"+"c"*64
        ctx=bridge.make_context(experiment="Coffee",world="Peak",round_id="R0",
                arm="D",condition="B0",source_hash=source)
        diag={"arm":"D","condition":"B0","source_hash":source,
              "parent_hash":parent,"evidence":"G2",
              "trace_sha256":"sha256:"+"d"*64,
              "own_evidence_only":True,"no_future_truth":True,
              "observations":[]}
        bridge.record_feedback(db,ctx,parent_hash=parent,diagnostic=diag,
                               recorded_at=timestamp)
        prior=bridge.d_fixed_decision(db,ctx,parent_hash=parent,
                                      as_known_at=timestamp)
        bridge.persist_disposition(db,ctx,decision=prior,recorded_at=timestamp)
        # A completed final DB at the same as-of cut has SIX revisions, not
        # four, and its ATMS projection is not the pre-policy projection.
        later=cf.logical_feedback_cuts(
            datetime.fromisoformat(timestamp))["disposition_recorded_at"]
        with self.assertRaisesRegex(
            ArenaError,"ASOF_PREDECISION_SNAPSHOT_NOT_FOUR_VERIFIED_REVISIONS"):
            cf.replay_final_ledger_at_cut(
                bridge,db,ctx,parent,prior["retrieved_before_policy"],
                decision_recorded_at=later)

    def test_g1_native_cannot_be_misrepresented_as_G2(self):
        with self.assertRaises((ArenaError, KeyError)):
            cf._verify_b({})
        with self.assertRaises((ArenaError, KeyError)):
            cf._verify_g2({})
