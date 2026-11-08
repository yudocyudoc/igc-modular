"""Synthetic M revision OMC fixtures: no solver, provider, or private world."""
import csv
import copy
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import canonical
from scripts.arena_cafe.ct03_dm_feedback_round import build
from scripts.arena_cafe.ct03_m_revision_physical import collect
from scripts.arena_cafe.ct03_dm_lock_projection import project,project_from_revision_report
from test_arena_ct03_dm_feedback_round import make_all_twelve,input_construction,T

SHA="b"*40
RUN="123456"


def make_case(root,*,revise):
    source,planned,reused=make_all_twelve(root)
    dm_root=root/"dm"
    dm=build(ten_root=planned,ct02_root=source,reuse=reused,
             construction=input_construction(late_observed=revise),
             recorded_at=T,out=dm_root)
    m=json.loads((planned/"M/manifest.json").read_text())
    d=json.loads((planned/"D/manifest.json").read_text())
    return dm_root,dm,d,m


def fixture_revised(dm_root,dm,m,*,failed_index=None):
    selected=[r for r in dm["rows"]
              if r["arm"]=="M" and r["decision"]["status"]=="REVISED"]
    attempts=[]
    for row in selected:
        i=row["index"]
        folder=dm_root/"producer-12/revisions"/("M"+str(i))
        manifest=row["revision_native_manifest"]
        cls=("CT03MR_"+row["candidate_id"][:12]+"_"+
             manifest["revised_full_ast_sha256"][7:15])
        model="ArenaCT03MR."+cls
        (folder/"omc-exit.json").write_bytes(canonical({
            "arm":"M","index":i,"run_id":RUN,"git_sha":SHA,
            "exit_code":0,"attempted":True
        })+b"\n")
        (folder/"mrev-omc.log").write_text(
            "OpenModelica 1.26.5 SYNTHETIC TEST\n"
            "Check of "+model+" completed successfully.\n"
            "LOG_SUCCESS SYNTHETIC NOT OMC\nmrev_res.csv\n")
        original=m["candidates"][i]
        stocks=[x["id"]+".waiting" for x in original["original_ast"]["instances"]
                if x["role"] in ("preparation","dispatch","transit")]
        with (folder/"mrev_res.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(["time","deliveredTotal",*stocks])
            for n in range(65):
                t=n/8
                delivered=.1*t
                available=1.7*min(t,2)-delivered
                if i==failed_index and t==3:available=0
                w.writerow([t,delivered,available,*([0.]*(len(stocks)-1))])
        attempts.append("M"+str(i)+" attempted; GitHub run "+RUN+
                        "; code "+SHA)
    if selected:
        (dm_root/"producer-12/m-revision-attempts.log").write_text(
            "\n".join(attempts)+"\n")
    return selected


class MRevisionPhysicalTests(unittest.TestCase):
    def test_shell_is_valid_bash_and_denies_unapproved_execution(self):
        script=Path(__file__).resolve().parents[1] / (
            "scripts/arena_cafe/ct03_m_revision_execute_once.sh")
        syntax=subprocess.run(["bash","-n",str(script)],capture_output=True,
                              text=True,timeout=10)
        self.assertEqual(syntax.returncode,0,syntax.stderr)
        denial=subprocess.run(["bash",str(script)],capture_output=True,
                              text=True,timeout=10,env={"PATH":os.environ["PATH"]})
        self.assertNotEqual(denial.returncode,0)
        self.assertIn("CT03_M_REVISION_LOT_SHA_AND_BUDGET_AUTH_REQUIRED",
                      denial.stderr)

    def test_zero_revision_uses_no_solver_and_outputs_empty_map(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            dm_root,dm,d,m=make_case(root,revise=False)
            self.assertEqual(dm["M_revised_count"],0)
            r=collect(dm,dm_root,m,run_id=RUN,git_sha=SHA)
            self.assertEqual(r["revised_count"],0)
            self.assertEqual(r["outcomes"],{})
            projection=project(dm,d,m,r["outcomes"])
            self.assertEqual(projection["candidate_count"],12)
            self.assertEqual(r["new_omc_by_verifier"],0)

    def test_revised_native_success_and_one_failed_preserved_for_lock(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            dm_root,dm,d,m=make_case(root,revise=True)
            selected=[r for r in dm["rows"] if r["arm"]=="M" and
                      r["decision"]["status"]=="REVISED"]
            self.assertTrue(selected)
            failed=selected[0]["index"]
            fixture_revised(dm_root,dm,m,failed_index=failed)
            report=collect(dm,dm_root,m,run_id=RUN,git_sha=SHA)
            self.assertEqual(report["revised_count"],len(selected))
            self.assertEqual(report["failed_count"],1)
            self.assertEqual(report["predicted_count"],len(selected)-1)
            self.assertEqual(report["new_omc_by_verifier"],0)
            self.assertEqual(report["provider_posts"],0)
            self.assertFalse(report["reserved_truth_read"])
            failed_out=report["outcomes"][selected[0]["candidate_id"]]
            self.assertEqual(failed_out["status"],"G2_FAILED")
            self.assertIsNone(failed_out["forecast"])
            self.assertIsNone(failed_out["trace_sha256"])
            projected=project_from_revision_report(dm,d,m,report)
            self.assertEqual(projected["candidate_count"],12)
            bad=copy.deepcopy(report)
            cid=next(iter(bad["receipts"]))
            bad["receipts"][cid]["failure"]="FORGED_FAILURE"
            with self.assertRaisesRegex(ValueError,"ATTEMPT_RECEIPT_MISMATCH"):
                project_from_revision_report(dm,d,m,bad)
            self.assertEqual(projected["M_physical_revised_count"],len(selected))
            for r in projected["rows"]:
                if r["arm"]=="M" and r["decision"]["status"]=="REVISED":
                    self.assertNotEqual(r["initial"]["native_sha256"],
                                        r["final"]["native_sha256"])

    def test_changed_source_is_integrity_stop_not_a_g2_failure(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            dm_root,dm,d,m=make_case(root,revise=True)
            selected=fixture_revised(dm_root,dm,m)
            target=dm_root/"producer-12/revisions"/("M"+str(selected[0]["index"]))
            with (target/"revision.mo").open("a") as f:
                f.write("\n// TAMPERED SOURCE\n")
            with self.assertRaisesRegex(ValueError,"NATIVE_SOURCE_OR_SCRIPT_TAMPERED"):
                collect(dm,dm_root,m,run_id=RUN,git_sha=SHA)
            self.assertFalse((target/"revision-validated.json").exists())

    def test_missing_attempt_not_silent_reuse(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            dm_root,dm,d,m=make_case(root,revise=True)
            selected=fixture_revised(dm_root,dm,m)
            (dm_root/"producer-12/m-revision-attempts.log").unlink()
            with self.assertRaisesRegex(ValueError,"EXACTLY_ONE_ATTEMPT"):
                collect(dm,dm_root,m,run_id=RUN,git_sha=SHA)

if __name__=="__main__":
    unittest.main()
