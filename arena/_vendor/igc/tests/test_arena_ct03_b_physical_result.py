"""B physical result on synthetic CSV/log only, never OMC or provider."""
import csv
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_b_own_feedback import build
from scripts.arena_cafe.ct03_b_physical_prepare import prepare
from scripts.arena_cafe.ct03_b_physical_result import check
from test_arena_ct03_b_own_feedback import fixture,public,TIME

def setup(root,broken_mass=False):
    native,receipt=fixture()
    fb=build(original=native,receipt=receipt,construction=public(),
             recorded_at=TIME,out=root/"feedback")
    plan=prepare(native,receipt,public(),fb,root/"physical")
    with (root/"physical/b-original_res.csv").open(
            "w",encoding="utf-8",newline="") as stream:
        w=csv.writer(stream)
        w.writerow(["time","delivered_work","pending_work"])
        for i in range(65):
            t=i/8
            delivered=.1*t
            remain=0 if broken_mass else 1.7*min(t,2)-delivered
            w.writerow([t,delivered,remain])
    (root/"physical/b-original-omc.log").write_text(
        "OpenModelica 1.26.5\nCheck of "+
        plan["translated_model_name"]+
        " completed successfully.\nLOG_SUCCESS FAKE_TEST_NOT_OMC\n"
        "b-original_res.csv\n")
    return native,receipt,plan


def _rewrite_csv_with_change(root,change):
    # Preserve the native model, receipt, script, fake solver log and mass.
    path=root/"physical/b-original_res.csv"
    with path.open(newline="",encoding="utf-8") as stream:
        reader=csv.DictReader(stream)
        headers=reader.fieldnames
        rows=list(reader)
    change(rows)
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class BPhysicalResultTests(unittest.TestCase):
    def test_one_original_B_success_shape_not_a_live_result(self):
        with TemporaryDirectory(dir=".") as t:
            root=Path(t).relative_to(Path.cwd())
            native,receipt,plan=setup(root)
            result=check(native=native,receipt=receipt,plan=plan,
                         root=root/"physical",
                         github_run_id="12345",github_sha="a"*40)
            self.assertEqual(result["forecast"][0]["time"],6)
            self.assertAlmostEqual(result["forecast"][0]["delivered"],.6)
            self.assertEqual(result["forecast"][1]["time"],8)
            self.assertAlmostEqual(result["forecast"][1]["delivered"],.8)
            self.assertLess(result["max_abs_material_residual"],1e-10)
            self.assertEqual(result["parent_native_sha256"],receipt["result_sha256"])
            self.assertTrue(result["not_a_scientific_G3_score"])

    def test_bad_mass_or_wrong_operator_must_fail(self):
        with TemporaryDirectory(dir=".") as t:
            root=Path(t).relative_to(Path.cwd())
            native,receipt,plan=setup(root,broken_mass=True)
            with self.assertRaisesRegex(ValueError,"MATERIAL_MASS_BALANCE_FAILED"):
                check(native=native,receipt=receipt,plan=plan,
                      root=root/"physical",
                      github_run_id="12345",github_sha="a"*40)
            plan["observation_operator"]["modelica_csv_column"]="pending_work"
            with self.assertRaisesRegex(ValueError,"NATIVE_PORT_OR_PARENT_DRIFT"):
                check(native=native,receipt=receipt,plan=plan,
                      root=root/"physical",
                      github_run_id="12345",github_sha="a"*40)

    def test_F172_08_mass_conserving_midtrace_delivery_drop_is_rejected(self):
        # Exact reviewer counterexample: t=2.875 .2875 -> t=3 .25 ->
        # t=3.125 .3125; leave y6=.6 and y8=.8 unchanged, conserve mass.
        with TemporaryDirectory(dir=".") as t:
            root=Path(t).relative_to(Path.cwd())
            native,receipt,plan=setup(root)
            def dip(rows):
                p=next(x for x in rows if float(x["time"])==3)
                self.assertAlmostEqual(float(p["delivered_work"]),.3)
                p["delivered_work"]="0.25"
                p["pending_work"]=repr(3.4-.25)
            _rewrite_csv_with_change(root,dip)
            with self.assertRaisesRegex(
                    ValueError,"CT03_B_PHYS_CUMULATIVE_DELIVERED_DECREASED"):
                check(native=native,receipt=receipt,plan=plan,
                      root=root/"physical",
                      github_run_id="12345",github_sha="a"*40)
            # The positive baseline in test_one_original_B_success_shape
            # still passes. This is synthetic fixture evidence, not OMC.

    def test_F172_08_event_duplicate_consistent_with_roundoff_is_accepted(self):
        with TemporaryDirectory(dir=".") as t:
            root=Path(t).relative_to(Path.cwd())
            native,receipt,plan=setup(root)
            def add_consistent_duplicate(rows):
                idx=next(i for i,x in enumerate(rows)
                         if float(x["time"])==2)
                row=dict(rows[idx])
                row["delivered_work"]=repr(float(row["delivered_work"])-5e-9)
                row["pending_work"]=repr(3.4-float(row["delivered_work"]))
                rows.insert(idx+1,row)
            _rewrite_csv_with_change(root,add_consistent_duplicate)
            result=check(native=native,receipt=receipt,plan=plan,
                         root=root/"physical",
                         github_run_id="12345",github_sha="a"*40)
            self.assertEqual(result["csv_rows"],66)
            self.assertEqual(result["cumulative_monotonicity_tolerance_items"],1e-8)
            self.assertAlmostEqual(result["forecast"][0]["delivered"],.6)

    def test_F172_08_duplicate_time_inconsistent_increase_rejected(self):
        with TemporaryDirectory(dir=".") as t:
            root=Path(t).relative_to(Path.cwd())
            native,receipt,plan=setup(root)
            def add_inconsistent_duplicate(rows):
                idx=next(i for i,x in enumerate(rows)
                         if float(x["time"])==2)
                row=dict(rows[idx])
                row["delivered_work"]=repr(float(row["delivered_work"])+2e-8)
                row["pending_work"]=repr(3.4-float(row["delivered_work"]))
                rows.insert(idx+1,row)
            _rewrite_csv_with_change(root,add_inconsistent_duplicate)
            with self.assertRaisesRegex(
                    ValueError,"CT03_B_PHYS_DUPLICATE_TIME_INCONSISTENT_DELIVERIES"):
                check(native=native,receipt=receipt,plan=plan,
                      root=root/"physical",
                      github_run_id="12345",github_sha="a"*40)

if __name__=="__main__":
    unittest.main()
