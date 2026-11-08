"""13th B slot tests are synthetic, NOT Buffalo provider or OMC executions."""
import copy
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import digest
from scripts.arena_cafe.ct03_b_physical_prepare import prepare
from scripts.arena_cafe.ct03_b_physical_result import check
from scripts.arena_cafe.ct03_b_lock_projection import project,project_no_native
from scripts.arena_cafe.ct03_prospective_lock import validate_row
from scripts.arena_cafe.e02_b_feedback import _model_sha
from test_arena_ct03_b_physical_result import setup
from test_arena_ct03_b_own_feedback import public

def prepare_fixture(root):
    native,receipt,plan=setup(root)
    feedback=json.loads((root/"feedback/status.json").read_text())
    packet=json.loads((root/"feedback/own-revision-packet.json").read_text())
    physically_checked=check(
        native=native,receipt=receipt,plan=plan,root=root/"physical",
        github_sha="a"*40,github_run_id="98765")
    return native,receipt,plan,feedback,packet,physically_checked

def review_receipt(original_receipt,native,packet):
    return {
        **original_receipt,
        "round_kind":"revision",
        "parent_native_sha256":original_receipt["result_sha256"],
        "own_feedback_sha256":digest(packet),
        "result_sha256":_model_sha(native)
    }

def provenance(native,receipt,packet):
    return {"parent_native":native,"parent_receipt":receipt,"packet":packet}

def check_row(result):
    validate_row(result["row"],{("B","B-original"):
                 {"parent_hash":None,"group":"B-original"}},
                 public()["world_public_id"])

class BuffaloSlotTests(unittest.TestCase):
    def test_one_actual_second_round_shape_ratif_no_repeat_omc(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,feedback,packet,physical=prepare_fixture(root)
            second=review_receipt(receipt,native,packet)
            rev_plan=prepare(native,second,public(),feedback,root/"revision",
                             revision_provenance=provenance(native,receipt,packet))
            result=project(original_native=native,initial_receipt=receipt,
                           construction=public(),b_feedback=feedback,
                           packet=packet,initial_plan=plan,
                           initial_physical=physical,
                           revision_native=native,revision_receipt=second,
                           revision_plan=rev_plan)
            check_row(result)
            row=result["row"]
            self.assertEqual(row["decision"]["status"],"RATIFIED")
            self.assertEqual(row["initial"],row["final"])
            self.assertEqual(row["initial"]["status"],"PREDICTED")
            self.assertTrue(result["second_B_provider_post_observed"])
            self.assertEqual(result["new_provider_calls"],0)
            self.assertFalse(result["reserved_truth_read"])
            self.assertFalse((root/"revision/b-original_res.csv").exists())

    def test_changed_native_with_real_shaped_second_omc_trace(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,feedback,packet,physical=prepare_fixture(root)
            revised=copy.deepcopy(native)
            revised["model"]["variables"][0]["documentation"]="Revised own-rate model"
            second=review_receipt(receipt,revised,packet)
            rev_plan=prepare(revised,second,public(),feedback,root/"revision",
                             revision_provenance=provenance(native,receipt,packet))
            self.assertEqual(rev_plan["status"],"B_NATIVE_PHYSICAL_PLANNED_NO_OMC")
            csv_file=root/"revision/b-original_res.csv"
            with csv_file.open("w",newline="",encoding="utf-8") as f:
                w=csv.writer(f);w.writerow(["time","delivered_work","pending_work"])
                for n in range(65):
                    t=n/8
                    delivery=.1*t
                    w.writerow([t,delivery,1.7*min(t,2)-delivery])
            (root/"revision/b-original-omc.log").write_text(
                "OpenModelica 1.26.5 SYNTHETIC\n"
                "Check of "+rev_plan["translated_model_name"]+
                " completed successfully.\nLOG_SUCCESS MOCK ONLY\n"
                "b-original_res.csv\n")
            rev_physical=check(native=revised,receipt=second,plan=rev_plan,
                               root=root/"revision",
                               github_sha="a"*40,github_run_id="98765")
            result=project(original_native=native,initial_receipt=receipt,
                           construction=public(),b_feedback=feedback,
                           packet=packet,initial_plan=plan,
                           initial_physical=physical,
                           revision_native=revised,revision_receipt=second,
                           revision_plan=rev_plan,revision_physical=rev_physical)
            check_row(result)
            row=result["row"]
            self.assertEqual(row["decision"]["status"],"REVISED")
            self.assertEqual(row["final"]["status"],"PREDICTED")
            self.assertNotEqual(row["final"]["native_sha256"],row["initial"]["native_sha256"])
            self.assertEqual(result["new_omc_by_projection"],0)

    def test_no_real_second_provider_cannot_be_silently_ratif(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,feedback,packet,physical=prepare_fixture(root)
            kwargs=dict(original_native=native,initial_receipt=receipt,
                        construction=public(),b_feedback=feedback,
                        packet=packet,initial_plan=plan,initial_physical=physical)
            with self.assertRaisesRegex(ValueError,"REVIEW_MISSING_NEEDS_EXPLICIT_STOP"):
                project(**kwargs)
            stopped=project(**kwargs,stop_reason="B_BATCH_STOP_RULE_OR_BUDGET_EXHAUSTED")
            check_row(stopped)
            self.assertEqual(stopped["row"]["decision"]["status"],"NOT_EXECUTED")
            self.assertFalse(stopped["second_B_provider_post_observed"])

    def test_changed_native_review_missing_physical_is_not_scored(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,feedback,packet,physical=prepare_fixture(root)
            revised=copy.deepcopy(native)
            revised["model"]["variables"][0]["documentation"]="Model changed"
            second=review_receipt(receipt,revised,packet)
            rev_plan=prepare(revised,second,public(),feedback,root/"revision",
                             revision_provenance=provenance(native,receipt,packet))
            with self.assertRaisesRegex(ValueError,
                                        "NATIVE_PHYSICAL_CSV_NOT_CONFORMING"):
                project(original_native=native,initial_receipt=receipt,
                        construction=public(),b_feedback=feedback,packet=packet,
                        initial_plan=plan,initial_physical=physical,
                        revision_native=revised,revision_receipt=second,
                        revision_plan=rev_plan)

    def test_failed_live_original_B_occupies_slot_without_fake_zero(self):
        receipt={
            "case_id":"CT-03","world_public_id":public()["world_public_id"],
            "condition_id":"C0",
            "source_snapshot_hash":public()["source_snapshot_hash"],
            "round_kind":"initial","mode":"live","model_returned":False,
            "status":"CT03_PROVIDER_ATTEMPT_NO_NATIVE",
            "upstream_source_modified":False,
            "upstream_sha":"5199f7b45f3a7ae4a773cb0dd8542940aabe9edc",
            "transport":"CLOUDFLARE_WORKERS_AI_DIRECT_REST_JSON_SCHEMA",
            "provider_calls":1
        }
        result=project_no_native(receipt,public())
        check_row(result)
        self.assertEqual(result["row"]["initial"]["status"],"NO_NATIVE")
        self.assertIsNone(result["row"]["initial"]["forecast"])
        self.assertEqual(result["row"]["initial"],result["row"]["final"])
        self.assertEqual(result["row"]["decision"]["status"],"NOT_EXECUTED")
        tampered={**receipt,"world_public_id":"OTHER_WORLD"}
        with self.assertRaisesRegex(ValueError,"NO_NATIVE_NEEDS_REAL_ORIGINAL"):
            project_no_native(tampered,public())

    def test_review_parent_or_own_diagnostic_mismatch_rejected(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,feedback,packet,physical=prepare_fixture(root)
            bad=review_receipt(receipt,native,packet)
            bad["own_feedback_sha256"]="sha256:"+"f"*64
            with self.assertRaisesRegex(ValueError,"REVISION_NOT_ORIGINAL_ENGINE"):
                prepare(native,bad,public(),feedback,root/"forbidden",
                        revision_provenance=provenance(native,receipt,packet))
            self.assertFalse((root/"forbidden").exists())

if __name__=="__main__":
    unittest.main()
