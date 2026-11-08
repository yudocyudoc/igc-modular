"""CT03 B G1 -> own physical G2/G3 -> ledger/ATMS -> real-review packet.

Only synthetic solver/provider fixtures are used; no private t6/t8 truth.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import digest
from scripts.arena_cafe.ct03_b_physical_feedback import build
from scripts.arena_cafe.ct03_b_physical_outcome import collect
from scripts.arena_cafe.ct03_b_physical_prepare import prepare
from scripts.arena_cafe.ct03_b_lock_projection import project
from scripts.arena_cafe.ct_feedback_bridge import make_context,recover_feedback
from scripts.arena_cafe.e02_b_feedback import _model_sha
from test_arena_ct03_b_lock_projection import prepare_fixture,review_receipt,provenance
from test_arena_ct03_b_physical_outcome import attempt,break_mass,RUN,SHA
from test_arena_ct03_b_own_feedback import public

LATER="2026-11-07T12:00:10+00:00"
def ctx():
    c=public()
    return make_context(experiment="CT03",world=c["world_public_id"],
        round_id="R0",arm="B",condition="C0",
        source_hash=c["source_snapshot_hash"])

def prepare_own_physical(root,failed=False):
    native,receipt,plan,g1,packet,_=prepare_fixture(root)
    attempt(root/"physical")
    if failed:
        break_mass(root/"physical/b-original_res.csv")
    physical=collect(native=native,receipt=receipt,plan=plan,
                     root=root/"physical",github_sha=SHA,github_run_id=RUN)
    status=build(original=native,receipt=receipt,construction=public(),
                 g1_dir=root/"feedback",initial_plan=plan,physical=physical,
                 physical_root=root/"physical",recorded_at=LATER,
                 out=root/"physical-feedback")
    r=root/"physical-feedback"
    return native,receipt,plan,g1,packet,physical,status,(
        json.loads((r/"status.json").read_text()),
        json.loads((r/"own-revision-packet.json").read_text()),
        json.loads((r/"own-physical-diagnostic.json").read_text()))

class BPhysicalOwnFeedbackTests(unittest.TestCase):
    def test_success_delivers_only_four_residuals_and_preserves_g1_cut(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,g1,packet,physical,meta,items=prepare_own_physical(root)
            updated,new_packet,diag=items
            self.assertEqual(meta["own_gate"],"G3")
            self.assertEqual(meta["construction_residual_count"],4)
            self.assertEqual([p["time"] for p in diag["observations"]],[0,1,2,4])
            self.assertEqual([p["time"] for p in diag["own_construction_predicted"]],
                             [0,1,2,4])
            self.assertEqual(diag["evidence"],"G3")
            self.assertEqual(diag["trace_sha256"],physical["csv_sha256"])
            self.assertNotIn("forecast",diag)
            self.assertNotIn("t6",json.dumps(diag))
            self.assertNotIn("t8",json.dumps(diag))
            self.assertEqual(new_packet["own_diagnostic_sha256"],digest(diag))
            self.assertEqual(new_packet["own_diagnostic"],diag)
            prev=recover_feedback(root/"physical-feedback/b-own-feedback-ledger.sqlite",
                ctx(),parent_hash=receipt["result_sha256"],
                as_known_at="2026-11-07T12:00:02+00:00")
            later=recover_feedback(root/"physical-feedback/b-own-feedback-ledger.sqlite",
                ctx(),parent_hash=receipt["result_sha256"],
                as_known_at="2026-11-07T12:00:11+00:00")
            self.assertEqual(prev["diagnostic_hash"],g1["own_diagnostic_sha256"])
            self.assertEqual(later["diagnostic_hash"],digest(diag))
            self.assertEqual(prev["retrieval"]["item_id"],later["retrieval"]["item_id"])
            self.assertNotEqual(prev["diagnostic_hash"],later["diagnostic_hash"])

    def test_second_buffalo_revision_uses_numerical_retrieval_not_prephysical_g1(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,g1,packet,physical,meta,items=prepare_own_physical(root)
            updated,new_packet,diag=items
            second=review_receipt(receipt,native,new_packet)
            rev_plan=prepare(native,second,public(),updated,root/"revision",
                             revision_provenance=provenance(native,receipt,new_packet))
            result=project(
                original_native=native,initial_receipt=receipt,
                construction=public(),b_feedback=g1,packet=packet,
                initial_plan=plan,initial_physical=physical,
                revision_native=native,revision_receipt=second,
                revision_plan=rev_plan,
                review_feedback=updated,review_packet=new_packet)
            row=result["row"]
            self.assertEqual(row["decision"]["status"],"RATIFIED")
            self.assertEqual(row["decision"]["feedback_hash"],digest(diag))
            self.assertEqual(row["initial"]["status"],"PREDICTED")
            self.assertEqual(row["final"],row["initial"])
            with self.assertRaisesRegex(ValueError,
                                        "PHYSICAL_FEEDBACK_NOT_OWN_INITIAL_ATTEMPT"):
                project(original_native=native,initial_receipt=receipt,
                        construction=public(),b_feedback=g1,packet=packet,
                        initial_plan=plan,initial_physical=physical,
                        review_feedback={**updated,
                            "physical_outcome_sha256":"sha256:"+"f"*64},
                        review_packet=new_packet,
                        stop_reason="B_BATCH_STOP_RULE_OR_BUDGET_EXHAUSTED")

    def test_failed_real_shaped_g2_attempt_has_no_fake_trace_or_residuals(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,g1,packet,physical,meta,items=prepare_own_physical(
                root,failed=True)
            updated,new_packet,diag=items
            self.assertEqual(meta["own_gate"],"G2")
            self.assertEqual(meta["construction_residual_count"],0)
            self.assertEqual(diag["observations"],[])
            self.assertIsNone(diag["trace_sha256"])
            self.assertTrue(diag["no_valid_trajectory_or_forecast"])
            self.assertEqual(diag["physical_failure_class"],"G2_PHYSICAL_CHECK_FAILED")
            self.assertEqual(new_packet["own_diagnostic"],diag)
            self.assertIsNone(new_packet["own_diagnostic"]["trace_sha256"])
            self.assertFalse(meta["reserved_truth_read"])

    def test_forged_physical_or_wrong_world_fails_before_ledger_creation(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,g1,packet,_=prepare_fixture(root)
            attempt(root/"physical")
            physical=collect(native=native,receipt=receipt,plan=plan,
                             root=root/"physical",github_sha=SHA,github_run_id=RUN)
            forged={**physical,"csv_sha256":"sha256:"+"f"*64}
            out=root/"blocked"
            with self.assertRaisesRegex(ValueError,
                                        "OUTCOME_BYTES_OR_STATUS_CHANGED"):
                build(original=native,receipt=receipt,construction=public(),
                      g1_dir=root/"feedback",initial_plan=plan,physical=forged,
                      physical_root=root/"physical",recorded_at=LATER,out=out)
            self.assertFalse(out.exists())
            wrong=copy.deepcopy(receipt)
            wrong["world_public_id"]="OTHER_WORLD"
            with self.assertRaisesRegex(ValueError,
                                        "ORIGINAL_LIVE_NATIVE_OR_RECEIPT_UNVERIFIED"):
                build(original=native,receipt=wrong,construction=public(),
                      g1_dir=root/"feedback",initial_plan=plan,physical=physical,
                      physical_root=root/"physical",recorded_at=LATER,out=out)
            self.assertFalse(out.exists())

if __name__=="__main__":
    unittest.main()
