"""CT03 ten native initial D/M plans; all CSV tests use fake fixtures, no OMC."""
import csv
import json
import shutil
import sys
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_dm_initial_batch import prepare,verify_one
from scripts.arena_cafe.ct03_d_prepare import original_six
from scripts.arena_cafe.ct03_m_prepare import generated
from scripts.arena_cafe.ct03_reuse_ct02 import SCHEMA as REUSE,RUN_ID
from scripts.arena_v0_contract import digest

def reuse_fixture():
    d,_=original_six()
    m,_,_,_=generated()
    return {
        "schema":REUSE,
        "status":"TWO_ORIGINAL_INITIAL_CONSEQUENCES_ELIGIBLE_FOR_REUSE",
        "source_github_run_id":RUN_ID,"new_omc":0,
        "own_feedback_or_decision_reused":False,
        "items":[
            {"arm":"D","candidate_id":d[0]["id"],
             "model_sha256":d[0]["native_modelica_sha256"]},
            {"arm":"M","candidate_id":m[0]["canonical_sha256"],
             "model_sha256":"PENDING_M_SHA"}
        ],
    }

def local_setup(root):
    # TemporaryDirectory must yield a repo-relative folder for native /repo mounts.
    root=Path(root)
    out=root/"planned"
    x=reuse_fixture()
    from scripts.arena_cafe.ct03_m_prepare import prepare as p_m
    temporary=root/"m_for_expected_sha"
    m=p_m(temporary)
    x["items"][1]["model_sha256"]=m["native_modelica_sha256"]
    return out,prepare(out,x)

class TenInitialCT03(unittest.TestCase):
    def test_ten_exact_original_scripts_after_reusing_D0_and_M0(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            out,plan=local_setup(root)
            self.assertEqual(plan["status"],
                             "TEN_ORIGINAL_NATIVE_PLANNED_ZERO_NEW_OMC")
            self.assertEqual(plan["new_omc_max_this_step"],10)
            self.assertEqual(plan["new_omc_executed_by_this_module"],0)
            self.assertEqual(plan["buffalo_calls"],0)
            self.assertFalse(plan["reserved_truth_read"])
            self.assertEqual([x["arm"] for x in plan["rows"]],["D"]*5+["M"]*5)
            self.assertEqual([x["index"] for x in plan["rows"]],[1,2,3,4,5]*2)
            for item in plan["rows"]:
                script=Path(item["script_file"]).read_text()
                self.assertEqual(script.count("simulate("),1)
                self.assertEqual(script.count("checkModel("),1)
                self.assertIn("method=\"euler\"",script)
                self.assertIn("numberOfIntervals=64",script)
                self.assertEqual(len(item["parent_hash"]),71)
            self.assertEqual(len((out/"D/manifest.json").read_bytes())>100,True)
            self.assertEqual(len((out/"M/manifest.json").read_bytes())>100,True)
            self.assertFalse((out/"D/d01_res.csv").exists())
            self.assertFalse((out/"M/m01_res.csv").exists())
            self.assertFalse((out/"B").exists())
            with self.assertRaisesRegex(ValueError,"NO_OVERWRITE"):
                prepare(out,reuse_fixture())

    def test_no_real_csv_or_solver_log_means_no_prediction(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            out,_=local_setup(root)
            for arm in ("D","M"):
                with self.assertRaisesRegex(ValueError,"REAL_SOLVER_CSV_AND_LOG_REQUIRED"):
                    verify_one(out,arm=arm,index=1,run_id="12345",git_sha="a"*40)
                self.assertFalse((out/arm/(arm.lower()+"01-result.json")).exists())
            with self.assertRaisesRegex(ValueError,"NOT_A_NONREUSED_INITIAL"):
                verify_one(out,arm="M",index=0,run_id="12345",git_sha="a"*40)

    def test_synthetic_m_one_result_only_and_no_secret_or_policy(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            out,plan=local_setup(root)
            item=next(x for x in plan["rows"] if x["arm"]=="M" and x["index"]==1)
            from scripts.arena_cafe.ct03_dm_initial_batch import _m_material_conservation
            import json
            parent=json.loads((out/"M/manifest.json").read_text())["candidates"][1]
            stock_ids=[x["id"]+".waiting" for x in parent["original_ast"]["instances"]
                       if x["role"] in ("preparation","dispatch","transit")]
            with Path(item["csv_file"]).open("w",encoding="utf-8",newline="") as f:
                writer=csv.writer(f)
                writer.writerow(["time","deliveredTotal",*stock_ids])
                for i in range(65):
                    t=i/8
                    delivered=.2*t
                    remaining=1.7*min(t,2)-delivered
                    writer.writerow([t,delivered,remaining,*([0.]*(len(stock_ids)-1))])
            Path(item["solver_log_file"]).write_text(
                "OpenModelica 1.26.5\nCheck of "+item["model_name"]+
                " completed successfully.\nLOG_SUCCESS SYNTHETIC ONLY\n"+
                item["csv_file"]+"\n")
            result=verify_one(out,arm="M",index=1,
                              run_id="12345",git_sha="a"*40)
            self.assertEqual(result["status"],
                "ONE_REAL_ORIGINAL_INITIAL_NATIVE_CHECKED_NOT_SCORED")
            # This result says source receipts checked, NOT independent physical proof.
            self.assertEqual([p["time"] for p in result["forecast"]],[6,8])
            self.assertAlmostEqual(result["forecast"][0]["delivered"],1.2)
            self.assertAlmostEqual(result["forecast"][1]["delivered"],1.6)
            self.assertEqual(result["G2_material_conservation_status"],
                             "ORIGINAL_E1_MASS_BALANCE_PASS_NOT_HELDOUT_G3")
            self.assertTrue(result["construction_residuals_not_yet_built"])
            self.assertFalse(result["feedback_or_revision_executed"])
            with self.assertRaisesRegex(ValueError,"RESULT_REFUSE_OVERWRITE"):
                verify_one(out,arm="M",index=1,run_id="12345",git_sha="a"*40)

    def test_changed_native_or_command_stops_before_receipt(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            out,plan=local_setup(root)
            item=next(x for x in plan["rows"] if x["arm"]=="M" and x["index"]==1)
            with Path(item["script_file"]).open("a") as f:f.write("\nsimulate(FAKE);\n")
            with self.assertRaisesRegex(ValueError,"SCRIPT_OR_MODEL_TAMPERED"):
                verify_one(out,arm="M",index=1,run_id="12345",git_sha="a"*40)
            self.assertFalse((out/"M/m01-result.json").exists())

if __name__=="__main__":
    unittest.main()
