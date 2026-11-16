"""PR38 native/resource diagnostics on GitHub only; fixtures aren't evidence."""
import copy
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError, digest, read_json, write_json
from arena import coffee_espresso_p38 as p38
from arena import coffee_v2_reference as physical
from arena import coffee_m_p08 as m
from test_coffee_v2_reference import dossier, paid, item
from test_coffee_m_p08 import stage


def tiny_m_artifact(folder):
    root=Path(folder)
    (root/"results").mkdir(parents=True)
    models=[]
    for load in p38.LOADS:
        for variant in m.VARIANTS:
            name="P08_"+("LOW" if load==p38.LOADS[0] else "HIGH")+"_"+variant
            rec={
                "name":name,"load_label":load,"variant":variant,
                "input_paid_orders":19 if load==p38.LOADS[0] else 46,
                "model_parameter_changes":{
                    "preparation_max_throughput_orders_per_hour":
                        24 if variant=="PREP_CAPACITY_X2" else 12,
                    "espresso_stage_max_throughput_orders_per_hour":
                        30 if variant=="ESPRESSO_CAPACITY_X2" else 15,
                    "dispatch_max_throughput_orders_per_hour":100},
                "csv":"results/"+name+"_res.csv",
            }
            models.append(rec)
            if variant=="BASE":
                # Construct a CSV parsing fixture with valid mass balance;
                # it is NOT native Modelica evidence or an observed barista.
                with (root/rec["csv"]).open("w",newline="") as f:
                    writer=csv.writer(f)
                    writer.writerow(["time","deliveredTotal",
                                     "preparation0.waiting",
                                     "espresso0.waiting","dispatch0.waiting"])
                    for i in range(m.INTERVALS+1):
                        t=i*m.STOP/m.INTERVALS
                        completed=rec["input_paid_orders"]*min(
                            t/(m.INPUT_HORIZON_MIN/60),1)
                        writer.writerow([t,completed,0,0,0])
    pairs=[{
        "load_label":load,
        "variant":"ESPRESSO_CAPACITY_X2",
        "B0_paid_orders_from_existing_artifact":paid_count,
        "native_M_B0_continuous_handoffs_at_cut":paid_count,
        "delta_continuous_handoffs_at_cut":0.0,
    } for load,paid_count in ((p38.LOADS[0],19),(p38.LOADS[1],46))]
    write_json(root/"manifest.json",{
        "schema":m.SCHEMA,"models":models},exclusive=True)
    write_json(root/"result.json",{
        "schema":m.SCHEMA,"status":"NATIVE_M_P08_SIX_SIMS_SUCCEEDED",
        "new_omc_attempted":6,"failed_models":[],
        "pairwise_comparisons":pairs},exclusive=True)


class EspressoMechanismTests(unittest.TestCase):
    def test_trace_does_not_change_scheduling_or_wait_percentile(self):
        p=[paid("A"),paid("B"),paid("C")]
        lines=[item("A"),item("B"),item("C")]
        d=dossier()
        usual=physical.simulate(p,lines,d,13)
        annotated,intervals,finished=physical._engine(
            p,lines,d,13,diagnose_stage_waits=True)
        diag=annotated.pop("mechanism_diagnostics")
        self.assertEqual(usual,annotated)
        self.assertEqual(usual["synthetic_paid_orders"],3)
        self.assertEqual(len(finished),3)
        self.assertEqual(len(intervals),usual["synthetic_beverage_units"]*2+
                         usual["synthetic_paid_orders"])
        self.assertGreater(diag["espresso_tasks_blocked_by_group_count"],0)
        self.assertGreater(diag["espresso_auto_queued_minutes_before_cut"],0)
        self.assertTrue(diag["diagnostic_does_not_modify_scheduling"])
        more=copy.deepcopy(d)
        more["resources"]["espresso_group"]["units"]=2
        changed,_,_=physical._engine(
            p,lines,more,13,diagnose_stage_waits=True)
        self.assertLess(changed["mechanism_diagnostics"][
            "espresso_auto_queued_minutes_before_cut"],
            diag["espresso_auto_queued_minutes_before_cut"])

    def test_drain_start_after_cut_has_no_negative_peak_queue(self):
        d=dossier()
        d["durations"]["espresso_auto_min"]["value"]=5
        p=[paid("A"),paid("B"),paid("C"),paid("D")]
        r,_,_=physical._engine(
            p,[item("A"),item("B"),item("C"),item("D")],
            d,5,diagnose_stage_waits=True)
        self.assertGreaterEqual(r["mechanism_diagnostics"][
            "espresso_auto_queued_minutes_before_cut"],0)

    def test_native_m_csv_stage_capacity_is_not_physical_machine(self):
        with TemporaryDirectory() as folder:
            tiny_m_artifact(folder)
            out=p38.native_m_stage_diagnostic(folder,p38.LOADS[0],19)
            self.assertTrue(out["M_espresso_stage_cap_not_hit"])
            self.assertFalse(out["no_p90_per_paid_order"] is False)
            self.assertEqual(out["M_espresso_x2_delta_continuous_at_cut"],0)
            self.assertEqual(out["M_max_uncapped_espresso_release_per_hour"],0)
            manifest=read_json(Path(folder)/"manifest.json")
            manifest["models"][0]["model_parameter_changes"][
                "espresso_stage_max_throughput_orders_per_hour"]=123
            write_json(Path(folder)/"manifest.json",manifest)
            with self.assertRaisesRegex(ArenaError,
                                        "M_NOT_SAME_INPUT_OR_STAGE_PARAMETER"):
                p38.native_m_stage_diagnostic(folder,p38.LOADS[0],19)

    def test_replay_two_representations_rejects_changed_reference(self):
        with TemporaryDirectory() as folder:
            d=dossier()
            src={
                "schema":m.SOURCE_SCHEMA,
                "status":"TWO_MECHANISMS_COMPARED_WITH_FIXED_B0",
                "real_profit_or_new_sales_inferred":False,
                "dossier_sha256":digest(d),
                "baseline":[],
                "rows":[],
            }
            scenarios={}
            choices=[]
            for label,n in ((p38.LOADS[0],19),(p38.LOADS[1],46)):
                points=[paid(str(i)+"x"+label,time=i*2.1)
                        for i in range(n)]
                items=[item(str(i)+"x"+label,time=i*2.1)
                       for i in range(n)]
                horizon=105
                b=physical.simulate(points,items,d,horizon)
                altered=p38.actions._candidate(d,p38.ACTION)
                a=physical.simulate(points,items,altered,horizon)
                src["baseline"].append({
                    "load_label":label,"paid_orders":n,
                    "B0_peak_handoffs":b["modeled_handoffs_during_halfopen_peak"],
                    "B0_p90_full_drain_min":
                        b["modeled_paid_to_handoff_p90_full_drain_min"],
                })
                src["rows"].extend([{
                    "load_label":label,"mechanism":k,
                    "paid_orders_same_both_cases":n,
                    "B0_peak_handoffs":
                        b["modeled_handoffs_during_halfopen_peak"],
                    "intervention_peak_handoffs":
                        a["modeled_handoffs_during_halfopen_peak"],
                    "intervention_p90_min":
                        a["modeled_paid_to_handoff_p90_full_drain_min"],
                } for k in p38.actions.MECHANISMS])
                scenarios[label]={
                    "partition":"CONSTRUCTION","positions":points,
                    "items":items,"horizon":horizon,
                }
                choices.append({"load_label":label,"case_id":label,"day":1})
            source_path=stage(folder,src)
            tiny_m_artifact(Path(folder)/"m")
            with patch.object(p38.p11,"_verified_load_choices",
                              return_value={"selected":choices}), \
                 patch.object(p38.views,"select_case_day",
                              side_effect=lambda path,id,day:scenarios[id]), \
                 patch.object(p38,"native_m_stage_diagnostic",
                              return_value={
                                 "M_espresso_stage_cap_not_hit":True,
                                 "M_espresso_x2_delta_continuous_at_cut":0,
                                 "M_max_uncapped_espresso_release_per_hour":0.0,
                                 "M_espresso_limit_assumed_orders_per_hour":15,
                              }):
                output=p38.compare(folder,source_path,Path(folder)/"m",d)
                self.assertEqual(len(output["cases"]),2)
                self.assertFalse(output["cases"][0]["hypotheses"][
                    "H_CROSS_MODEL_DISAGREEMENT_EXPLAINED_ENTIRELY"]["support"])
                self.assertEqual(output["new_omc"],0)
                p38.export(output,Path(folder)/"out")
                self.assertIn("Hipótesis",(
                    Path(folder)/"out/DECISION.md").read_text())
                corrupted=copy.deepcopy(d)
                corrupted["durations"]["manual_setup_min"]["value"]=0.75
                with self.assertRaisesRegex(ArenaError,
                                            "REFERENCE_ASSUMPTIONS_CHANGED"):
                    p38.compare(folder,source_path,Path(folder)/"m",corrupted)


if __name__=="__main__":
    unittest.main()
