"""F172-09: B solver/CSV failures retain a native and occupy slot 13.

All artifacts are synthetic. No provider, OMC, private world or heldout score.
"""
import copy
import csv
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_b_physical_outcome import collect,STATUS
from scripts.arena_cafe.ct03_b_lock_projection import project
from scripts.arena_cafe.ct03_b_physical_prepare import prepare
from scripts.arena_cafe.ct03_assemble_entries import assemble
from scripts.arena_cafe.ct03_prospective_lock import validate_row
from test_arena_ct03_b_lock_projection import (
    prepare_fixture,review_receipt,provenance
)
from test_arena_ct03_b_own_feedback import public
from test_arena_ct03_assemble_entries import fixture as twelve_and_b_fixture

RUN="98765"
SHA="a"*40

def attempt(root,round_kind="initial",code=0):
    meta={"arm":"B","round_kind":round_kind,"run_id":RUN,"git_sha":SHA,
          "exit_code":code,"attempted":True}
    (root/"omc-exit.json").write_text(json.dumps(meta,sort_keys=True)+"\n",
                                     encoding="utf-8")

def break_mass(path):
    with path.open(encoding="utf-8",newline="") as f:
        reader=csv.DictReader(f)
        fields=reader.fieldnames
        rows=list(reader)
    for row in rows:
        if float(row["time"])==3.0:
            row["pending_work"]="0"
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def b_args(native,receipt,plan,feedback,packet,initial_physical=None):
    return dict(original_native=native,initial_receipt=receipt,
                construction=public(),b_feedback=feedback,packet=packet,
                initial_plan=plan,initial_physical=initial_physical)

def check_thirteen(root,b13):
    root.mkdir(exist_ok=True)
    dm,b_original,d,m=twelve_and_b_fixture(root)
    rows=assemble(dm,b13,public(),d,m)["rows"]
    assert len(rows)==13
    b=next(x for x in rows if x["arm"]=="B")
    validate_row(b,{("B","B-original"):
                     {"parent_hash":None,"group":"B-original"}},
                 public()["world_public_id"])
    return b

class BPhysicalFailureReceiptTests(unittest.TestCase):
    def test_initial_physical_mass_failure_projects_G2_and_assembles_13(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,fb,packet,_=prepare_fixture(root)
            attempt(root/"physical")
            break_mass(root/"physical/b-original_res.csv")
            physical=collect(native=native,receipt=receipt,plan=plan,
                             root=root/"physical",
                             github_sha=SHA,github_run_id=RUN)
            self.assertEqual(physical["status"],STATUS)
            self.assertEqual(physical["failure_reason"],
                             "CT03_B_PHYS_MATERIAL_MASS_BALANCE_FAILED")
            self.assertEqual(physical["omc_exit_code"],0)
            self.assertTrue(physical["attempted"])
            self.assertIsNone(physical["forecast"])
            result=project(**b_args(native,receipt,plan,fb,packet,physical),
                           stop_reason="B_BATCH_STOP_RULE_OR_BUDGET_EXHAUSTED")
            b=result["row"]
            self.assertEqual(b["initial"]["status"],"G2_FAILED")
            self.assertEqual(b["initial"],b["final"])
            self.assertEqual(b["decision"]["status"],"NOT_EXECUTED")
            self.assertEqual(b["initial"]["native_sha256"],receipt["result_sha256"])
            self.assertIsNone(b["initial"]["trace_sha256"])
            self.assertIsNone(b["initial"]["forecast"])
            self.assertIsNotNone(b["initial"]["receipt_sha256"])
            self.assertEqual(check_thirteen(root/"twelve",result)["initial"]["status"],
                             "G2_FAILED")

    def test_changed_native_revision_physical_failure_stays_revised_not_scored(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,fb,packet,initial=prepare_fixture(root)
            revised=copy.deepcopy(native)
            revised["model"]["variables"][0]["documentation"]="New own version"
            second=review_receipt(receipt,revised,packet)
            revision_plan=prepare(revised,second,public(),fb,root/"revision",
                                  revision_provenance=provenance(native,receipt,packet))
            shutil.copyfile(root/"physical/b-original_res.csv",
                            root/"revision/b-original_res.csv")
            (root/"revision/b-original-omc.log").write_text(
                "OpenModelica 1.26.5 SYNTHETIC\nCheck of "+
                revision_plan["translated_model_name"]+
                " completed successfully.\nLOG_SUCCESS MOCK ONLY\n"
                "b-original_res.csv\n",encoding="utf-8")
            attempt(root/"revision",round_kind="revision")
            break_mass(root/"revision/b-original_res.csv")
            failed=collect(native=revised,receipt=second,plan=revision_plan,
                           root=root/"revision",github_sha=SHA,github_run_id=RUN)
            result=project(**b_args(native,receipt,plan,fb,packet,initial),
                           revision_native=revised,revision_receipt=second,
                           revision_plan=revision_plan,revision_physical=failed)
            row=result["row"]
            self.assertEqual(row["decision"]["status"],"REVISED")
            self.assertEqual(row["initial"]["status"],"PREDICTED")
            self.assertEqual(row["final"]["status"],"G2_FAILED")
            self.assertEqual(row["final"]["native_sha256"],second["result_sha256"])
            self.assertIsNone(row["final"]["forecast"])
            self.assertTrue(result["second_B_provider_post_observed"])
            self.assertEqual(check_thirteen(root/"twelve",result)["final"]["status"],
                             "G2_FAILED")

    def test_missing_attempt_rejected_even_if_csv_fails(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,fb,packet,_=prepare_fixture(root)
            break_mass(root/"physical/b-original_res.csv")
            with self.assertRaisesRegex(ValueError,
                                        "CONSUMED_ATTEMPT_AND_LOG_REQUIRED"):
                collect(native=native,receipt=receipt,plan=plan,
                        root=root/"physical",github_sha=SHA,github_run_id=RUN)
            with self.assertRaisesRegex(ValueError,
                                        "NATIVE_PHYSICAL_CSV_NOT_CONFORMING"):
                project(**b_args(native,receipt,plan,fb,packet),
                        stop_reason="B_BATCH_STOP_RULE_OR_BUDGET_EXHAUSTED")

    def test_metadata_run_or_phase_mismatch_stops_not_failure(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,fb,packet,_=prepare_fixture(root)
            attempt(root/"physical",round_kind="revision")
            with self.assertRaisesRegex(ValueError,"ATTEMPT_METADATA_MISMATCH"):
                collect(native=native,receipt=receipt,plan=plan,
                        root=root/"physical",github_sha=SHA,github_run_id=RUN)
            attempt(root/"physical")
            broken=copy.deepcopy(plan)
            broken["script_sha256"]="sha256:"+"f"*64
            with self.assertRaisesRegex(ValueError,"SCRIPT_INTEGRITY_STOP"):
                collect(native=native,receipt=receipt,plan=broken,
                        root=root/"physical",github_sha=SHA,github_run_id=RUN)

    def test_failed_solver_exit_with_log_and_no_csv(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,fb,packet,_=prepare_fixture(root)
            attempt(root/"physical",code=1)
            (root/"physical/b-original_res.csv").unlink()
            physical=collect(native=native,receipt=receipt,plan=plan,
                             root=root/"physical",github_sha=SHA,github_run_id=RUN)
            self.assertEqual(physical["failure_reason"],"OMC_EXIT_NONZERO:1")
            self.assertIsNone(physical["csv_sha256"])
            result=project(**b_args(native,receipt,plan,fb,packet,physical),
                           stop_reason="B_BATCH_STOP_RULE_OR_BUDGET_EXHAUSTED")
            self.assertEqual(result["row"]["final"]["status"],"G2_FAILED")

    def test_success_with_record_keeps_original_success_route(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            native,receipt,plan,fb,packet,_=prepare_fixture(root)
            attempt(root/"physical")
            physical=collect(native=native,receipt=receipt,plan=plan,
                             root=root/"physical",github_sha=SHA,github_run_id=RUN)
            self.assertEqual(physical["status"],
                             "B_ORIGINAL_NATIVE_PHYSICAL_CSV_CONFORMING_NOT_HELDOUT")
            result=project(**b_args(native,receipt,plan,fb,packet,physical),
                           stop_reason="B_BATCH_STOP_RULE_OR_BUDGET_EXHAUSTED")
            self.assertEqual(result["row"]["initial"]["status"],"PREDICTED")

if __name__=="__main__":
    unittest.main()
