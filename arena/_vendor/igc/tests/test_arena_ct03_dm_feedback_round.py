"""Synthetic offline D/M-to-own-feedback-to-policy join. Never physical proof."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import digest
from scripts.arena_cafe.ct03_public import OBS_SCHEMA
from scripts.arena_cafe.ct03_reuse_ct02 import verify_native_dir
from scripts.arena_cafe.ct03_dm_initial_batch import prepare,verify_one
from scripts.arena_cafe.ct03_dm_feedback_round import build
from scripts.arena_cafe.ct_feedback_bridge import make_context,recover_feedback
from test_arena_ct03_reuse_ct02 import synthetic_fixture

T="2026-11-07T12:00:00+00:00"
SRC="sha256:"+"a"*64


def input_construction(*,late_observed=False):
    return {
        "schema":OBS_SCHEMA,
        "world_public_id":"CT03_TEST_W1","condition_id":"C0",
        "source_snapshot_hash":SRC,"time_unit":"hours",
        "observable":"cumulative_delivered",
        "observations":[{"time":t,"delivered":0 if late_observed else .1*t}
                        for t in (0,1,2,4)],
    }


def make_all_twelve(root):
    source,fresh,d,m=synthetic_fixture(root)
    reused=verify_native_dir(source,d,m,fresh_root=fresh)
    planned=root/"producer-ten"
    plan=prepare(planned,reused)
    for row in plan["rows"]:
        arm,index=row["arm"],row["index"]
        manifest=(d if arm=="D" else m)
        candidate=manifest["candidates"][index]
        n=len(candidate["structure"]["stocks"]) if arm=="D" else 0
        m_stocks=([x["id"]+".waiting" for x in
                  candidate["original_ast"]["instances"]
                  if x["role"] in ("preparation","dispatch","transit")]
                  if arm=="M" else [])
        with Path(row["csv_file"]).open("w",newline="",encoding="utf-8") as stream:
            writer=csv.writer(stream)
            writer.writerow(["time","delivered","lost"]+
                            ["s"+str(i+1) for i in range(n)] if arm=="D"
                            else ["time","deliveredTotal",*m_stocks])
            for i in range(65):
                t=i/8
                mass=1.7*min(t,2)
                delivered=.1*t
                writer.writerow([t,delivered,0,mass-delivered]+[0]*(n-1)
                                if arm=="D" else
                                [t,delivered,mass-delivered]+[0]*(len(m_stocks)-1))
        Path(row["solver_log_file"]).write_text(
            "OpenModelica 1.26.5\n"+
            "Check of "+row["model_name"]+" completed successfully.\n"+
            "LOG_SUCCESS SYNTHETIC FIXTURE NOT OMC\n"+
            row["csv_file"]+"\n")
        verify_one(planned,arm=arm,index=index,
                   run_id="87654321",git_sha="b"*40)
    (planned/"attempts.log").write_text(
        "".join(r["arm"]+str(r["index"])+
                " attempted; GitHub run 87654321; code "+"b"*40+"\n"
                for r in plan["rows"]))
    return source,planned,reused


class DMOwnFeedbackRoundTests(unittest.TestCase):
    def test_all_twelve_own_feedbacks_policy_dispositions_without_solver(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            report=build(ten_root=planned,ct02_root=source,reuse=reused,
                construction=input_construction(),
                recorded_at=T,out=root/"compiled")
            self.assertEqual(report["D_fixed_count"],6)
            self.assertEqual(len(report["rows"]),12)
            self.assertEqual(report["new_omc_executed_by_this_module"],0)
            self.assertEqual(report["new_provider_calls"],0)
            self.assertFalse(report["own_feedback_reused_from_ct02"])
            self.assertFalse(report["reserved_truth_read"])
            self.assertEqual(report["origin_ct02_run"],42409210062)
            self.assertEqual([x["index"] for x in report["rows"] if x["arm"]=="D"],
                             list(range(6)))
            self.assertEqual([x["index"] for x in report["rows"] if x["arm"]=="M"],
                             list(range(6)))
            for row in report["rows"]:
                self.assertEqual(row["initial"]["status"],"PREDICTED")
                self.assertEqual([p["time"] for p in row["initial"]["forecast"]],[6,8])
                self.assertEqual([x["time"] for x in
                                  row["own_construction_diagnostic"]["observations"]],
                                  [0,1,2,4])
                self.assertEqual(row["retrieved_before_policy"]["item_id"],
                    "ct-CT03-CT03_TEST_W1-R0-"+row["arm"]+"-C0-parent-"+
                    row["parent_hash"][7:]+":FEEDBACK")
                self.assertFalse(row["world_private_read"])
                ctx=make_context(experiment="CT03",world="CT03_TEST_W1",
                                 round_id="R0",arm=row["arm"],
                                 condition="C0",source_hash=SRC)
                from datetime import datetime,timedelta
                recent=recover_feedback(root/"compiled/producer-12/own-feedback-ledger.sqlite",
                                        ctx,parent_hash=row["parent_hash"],
                                        as_known_at="2026-11-07T12:00:03+00:00")
                self.assertEqual(recent["diagnostic_hash"],
                                 row["own_diagnostic_sha256"])
            self.assertFalse((root/"compiled/producer-12/entries.json").exists())

    def test_missing_one_real_initial_blocks_all_feedback_without_fabrication(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            (planned/"M/m04-result.json").unlink()
            with self.assertRaisesRegex(ValueError,"MISSING_REAL_INITIAL_RUN"):
                build(ten_root=planned,ct02_root=source,reuse=reused,
                      construction=input_construction(),
                      recorded_at=T,out=root/"compile-invalid")
            self.assertFalse((root/"compile-invalid").exists())

    def test_one_failed_M_keeps_its_slot_without_feedback_or_fake_zero(self):
        from scripts.arena_cafe.ct03_dm_initial_batch import record_failure
        from scripts.arena_cafe.ct03_dm_lock_projection import project
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            # A physical attempt in the synthetic fixture reported a G2 error.
            # It has no scientific prediction and may not be silently retried.
            (planned/"M/m04-result.json").unlink()
            exact="M4 attempted; GitHub run 87654321; code "+"b"*40
            self.assertEqual((planned/"attempts.log").read_text().count(exact),1)
            failure=record_failure(planned,arm="M",index=4,
                run_id="87654321",git_sha="b"*40,
                failure_class="G2_CHECK_FAILED",omc_exit_code=0)
            self.assertEqual(failure["forecast"],None)
            self.assertTrue(failure["not_a_synthetic_zero"])
            report=build(ten_root=planned,ct02_root=source,reuse=reused,
                         construction=input_construction(),
                         recorded_at=T,out=root/"dm")
            self.assertEqual(report["failed_initial_count"],1)
            self.assertEqual(len(report["rows"]),12)
            row=next(x for x in report["rows"]
                     if x["arm"]=="M" and x["index"]==4)
            self.assertEqual(row["initial"]["status"],"G2_FAILED")
            self.assertIsNone(row["initial"]["forecast"])
            self.assertIsNone(row["own_construction_diagnostic"])
            self.assertIsNone(row["retrieved_before_policy"])
            self.assertEqual(row["decision"]["status"],"NOT_EXECUTED")
            d=json.loads((planned/"D/manifest.json").read_text())
            m=json.loads((planned/"M/manifest.json").read_text())
            projected=project(report,d,m,{})
            blocked=next(x for x in projected["rows"]
                         if x["arm"]=="M" and x["candidate_id"]==row["candidate_id"])
            self.assertEqual(blocked["initial"],blocked["final"])
            self.assertEqual(blocked["initial"]["status"],"G2_FAILED")
            self.assertEqual(projected["candidate_count"],12)

    def test_failure_without_logged_attempt_is_not_promoted_to_G2_failure(self):
        from scripts.arena_cafe.ct03_dm_initial_batch import record_failure
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            (planned/"M/m04-result.json").unlink()
            (planned/"attempts.log").write_text("")
            with self.assertRaisesRegex(ValueError,"ONE_ATTEMPT_LOGGED_REQUIRED"):
                record_failure(planned,arm="M",index=4,
                    run_id="87654321",git_sha="b"*40,
                    failure_class="G2_CHECK_FAILED",omc_exit_code=0)
            self.assertFalse((planned/"M/m04-result.json").exists())

    def test_no_reserved_construction_cut_allowed(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            c=input_construction()
            c["observations"].append({"time":6,"delivered":.6})
            with self.assertRaisesRegex(ValueError,"FOUR_CONSTRUCTION"):
                build(ten_root=planned,ct02_root=source,reuse=reused,
                      construction=c,recorded_at=T,out=root/"bad-world")
            self.assertFalse((root/"bad-world").exists())


if __name__=="__main__":
    unittest.main()
