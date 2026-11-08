"""CT03 initial D/M and M-revision budget crosses to B as counts only.

No private world, Docker or provider calls; synthetic same-run receipts.
"""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import digest
from scripts.arena_cafe.ct03_lot_budget import issue,verify_receipt,SCHEMA
from scripts.arena_cafe.ct03_dm_feedback_round import SCHEMA as DM
from scripts.arena_cafe.ct03_m_revision_physical import SCHEMA as REV

RUN="23456"
SHA="a"*40
SRC="sha256:"+"b"*64

def fake(n):
    rows=[{"arm":"M","index":i,"decision":{"status":"REVISED"}} for i in range(n)]
    rows+= [{"arm":"D","index":i,"decision":{"status":"RATIFIED"}} for i in range(6)]
    rows+= [{"arm":"M","index":i,"decision":{"status":"RATIFIED"}} for i in range(n,6)]
    dm={"schema":DM,"rows":rows,"world_public_id":"W1",
        "source_snapshot_hash":SRC,"reserved_truth_read":False}
    revisions={"schema":REV,"world_public_id":"W1",
        "source_snapshot_hash":SRC,"dm_feedback_sha256":digest(dm),
        "run_id":RUN,"git_sha":SHA,"reserved_truth_read":False,
        "provider_posts":0,"revised_count":n,
        "outcomes":{str(i):{} for i in range(n)},
        "receipts":{str(i):{} for i in range(n)}}
    return dm,revisions

def logs(root,n):
    orig=root/"initial.log"
    rev=root/"m-revised.log"
    orig.write_text("".join(
        f"{arm}{i} attempted; GitHub run {RUN}; code {SHA}\n"
        for arm in "DM" for i in range(1,6)))
    if n:
        rev.write_text("".join(
            f"M{i} attempted; GitHub run {RUN}; code {SHA}\n"
            for i in range(n)))
    return orig,rev

class LotBudgetTests(unittest.TestCase):
    def test_six_M_revisions_leaves_exactly_two_B_physical_attempts(self):
        with TemporaryDirectory() as t:
            root=Path(t)
            dm,rev=fake(6);orig,mrev=logs(root,6)
            budget=issue(dm_report=dm,revisions=rev,
                         initial_attempt_log=orig,m_revision_attempt_log=mrev,
                         run_id=RUN,git_sha=SHA)
            self.assertEqual(budget["schema"],SCHEMA)
            self.assertEqual(verify_receipt(budget,run_id=RUN,git_sha=SHA),17)
            construction={"world_public_id":"W1","source_snapshot_hash":SRC,
                          "condition_id":"C0",
                          "observations":[{"time":t} for t in (0,1,2,4)]}
            self.assertEqual(verify_receipt(budget,run_id=RUN,git_sha=SHA,
                                            construction=construction),17)
            for change in ({"world_public_id":"W2"},
                           {"source_snapshot_hash":"sha256:"+"f"*64},
                           {"observations":[{"time":t} for t in (0,1,2,6)]}):
                with self.assertRaisesRegex(ValueError,"B_OTHER_WORLD_OR_PUBLIC_SOURCE"):
                    verify_receipt(budget,run_id=RUN,git_sha=SHA,
                                   construction={**construction,**change})
            self.assertEqual(17+budget["b_physical_omc_max"],19)
            self.assertEqual(set(budget),{
                "schema","world_public_id","source_snapshot_hash",
                "github_run_id","github_sha","world_omc_attempts",
                "dm_initial_omc_attempts","m_revision_omc_attempts",
                "b_physical_omc_max","global_omc_max","dm_feedback_sha256",
                "m_revision_outcomes_sha256","new_provider_posts",
                "reserved_truth_read","digest_sha256"
            })
            for key,value in [("github_sha","f"*40),
                              ("world_omc_attempts",0),
                              ("dm_initial_omc_attempts",9),
                              ("m_revision_omc_attempts",7)]:
                bad={**budget,key:value}
                with self.assertRaisesRegex(ValueError,"INVALID_OR_CROSS_RUN"):
                    verify_receipt(bad,run_id=RUN,git_sha=SHA)

    def test_zero_M_revisions_is_valid_and_no_fake_attempt_log(self):
        with TemporaryDirectory() as t:
            root=Path(t)
            dm,rev=fake(0);orig,mrev=logs(root,0)
            self.assertFalse(mrev.exists())
            receipt=issue(dm_report=dm,revisions=rev,
                          initial_attempt_log=orig,m_revision_attempt_log=mrev,
                          run_id=RUN,git_sha=SHA)
            self.assertEqual(verify_receipt(receipt,run_id=RUN,git_sha=SHA),11)

    def test_other_run_missing_attempt_or_unsanctioned_m_revision_stops(self):
        with TemporaryDirectory() as t:
            root=Path(t);dm,rev=fake(1);orig,mrev=logs(root,1)
            with self.assertRaisesRegex(ValueError,"DM_OR_M_REVISED_REPORT_MISMATCH"):
                issue(dm_report=dm,revisions=rev,initial_attempt_log=orig,
                      m_revision_attempt_log=mrev,run_id="9999",git_sha=SHA)
            mrev.write_text("M4 attempted; GitHub run "+RUN+"; code "+SHA+"\n")
            with self.assertRaisesRegex(ValueError,"M_REVISED_ATTEMPTS_NOT_EXACT"):
                issue(dm_report=dm,revisions=rev,initial_attempt_log=orig,
                      m_revision_attempt_log=mrev,run_id=RUN,git_sha=SHA)
            orig.write_text("")
            with self.assertRaisesRegex(ValueError,"TEN_INITIALS_ONE_SAME_RUN"):
                issue(dm_report=dm,revisions=rev,initial_attempt_log=orig,
                      m_revision_attempt_log=mrev,run_id=RUN,git_sha=SHA)

if __name__=="__main__":
    unittest.main()
