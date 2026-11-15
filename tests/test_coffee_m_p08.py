"""P08 method-native engineering fixtures, exclusively in GitHub Actions."""
import copy
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError, read_json, write_json
from arena.coffee_adapters.shared import sha_bytes
from arena import coffee_m_p08 as p08


def source_data():
    cases=[(p08.INPUT_LABELS[0],19),(p08.INPUT_LABELS[1],46)]
    return {
        "schema":p08.SOURCE_SCHEMA,
        "status":"TWO_MECHANISMS_COMPARED_WITH_FIXED_B0",
        "real_profit_or_new_sales_inferred":False,
        "baseline":[{"load_label":name,"paid_orders":count,
                     "B0_peak_handoffs":count}
                    for name,count in cases],
        "rows":[{"load_label":name,
                 "paid_orders_same_both_cases":count,
                 "mechanism":kind}
                for name,count in cases
                for kind in ("MANUAL_PREPARATION_TO_DECLARED_LOWER_BOUND",
                             "ONE_ADDITIONAL_ESPRESSO_GROUP")],
    }


def stage(folder,source=None):
    path=Path(folder)/"NEXT_ACTION.json"
    write_json(path,source or source_data(),exclusive=True)
    write_json(Path(folder)/"receipt.json",{
        "source_run_id":p08.PRODUCER_VIEWS_RUN,
        "no_reserved_truth":True,
        "outputs":{"NEXT_ACTION.json":sha_bytes(path.read_bytes())},
    },exclusive=True)
    return path


class P08MNativeTests(unittest.TestCase):
    def test_versioned_role_is_native_composed_and_e1_original_unchanged(self):
        composer,backend,swap,cfg,classes,key,graph=p08.typed_version()
        self.assertEqual(len(cfg["new_classes"]),1)
        self.assertEqual(classes["espresso-typed-bounded-queue-p08"]["modelica"],
                         "IGCMolecules.BoundedQueue")
        self.assertEqual([x["role"] for x in graph["instances"]],
            ["source","preparation","espresso","dispatch","receipt"])
        self.assertEqual(cfg["roles"]["report"]["max_instances"],0)
        self.assertEqual(cfg["roles"]["transit"]["max_instances"],0)
        self.assertEqual(
            cfg["roles"]["espresso"]["parameters"]["maxThroughput"],15)
        self.assertEqual(
            cfg["roles"]["dispatch"]["parameters"]["maxThroughput"],100)
        self.assertEqual(len(key),64)
        composer.check_graph(graph,cfg,classes)

    def test_six_models_from_two_construction_loads_and_three_variants(self):
        with TemporaryDirectory() as tmp:
            input=stage(tmp)
            prepared=p08.prepare(input,Path(tmp)/"out")
            self.assertEqual(len(prepared["models"]),6)
            self.assertEqual(prepared["maximum_new_omc_attempts"],6)
            self.assertTrue(prepared["original_sources_modified"] is False)
            self.assertEqual(
                prepared["representability"]["M"],
                "VERSIONED_AGGREGATE_PREPARATION_ESPRESSO_STAGES_NOT_PHYSICAL_EQUIVALENCE")
            for label in p08.INPUT_LABELS:
                rows=[r for r in prepared["models"] if r["load_label"]==label]
                self.assertEqual({r["variant"] for r in rows},set(p08.VARIANTS))
                self.assertEqual(len(set(r["rectangular_rate_orders_per_hour"]
                                         for r in rows)),1)
                b0=next(r for r in rows if r["variant"]=="BASE")
                faster=next(r for r in rows
                            if r["variant"]=="PREP_CAPACITY_X2")
                machine=next(r for r in rows
                             if r["variant"]=="ESPRESSO_CAPACITY_X2")
                self.assertEqual(b0["model_parameter_changes"][
                    "preparation_max_throughput_orders_per_hour"],12)
                self.assertEqual(faster["model_parameter_changes"][
                    "preparation_max_throughput_orders_per_hour"],24)
                self.assertEqual(machine["model_parameter_changes"][
                    "espresso_stage_max_throughput_orders_per_hour"],30)
            self.assertEqual(
                (Path(tmp)/"out/native.mo").read_text().count("    deliveredTotal="),6)
            for item in prepared["models"]:
                content=(Path(tmp)/"out"/item["script"]).read_text()
                self.assertEqual(content.count("simulate("),1)
                self.assertEqual(content.count("checkModel("),1)
                self.assertNotIn("POST",content)
                self.assertNotIn("truth",content.lower())
            self.assertEqual(prepared["truth_read"],False)

    def test_source_tamper_and_private_input_cannot_activate_m(self):
        with TemporaryDirectory() as tmp:
            input=stage(tmp)
            data=read_json(input)
            data["baseline"][0]["paid_orders"]+=1
            write_json(input,data)
            with self.assertRaisesRegex(ArenaError,"DOWNLOADED_SOURCE_HASH_CHANGED"):
                p08.prepare(input,Path(tmp)/"bad")
        with TemporaryDirectory() as tmp:
            data=source_data()
            data["baseline"][1]["paid_orders"]=0
            input=stage(tmp,data)
            with self.assertRaisesRegex(ArenaError,
                                        "INPUT_NOT_TWO_DISTINCT_PAID_LOADS"):
                p08.prepare(input,Path(tmp)/"bad")
        with TemporaryDirectory() as tmp:
            data=source_data()
            data["rows"][0]["paid_orders_same_both_cases"]+=1
            input=stage(tmp,data)
            with self.assertRaisesRegex(ArenaError,"REFERENCE_ROWS_NOT_PAIRED"):
                p08.prepare(input,Path(tmp)/"bad")

    def test_no_omc_outside_github_main_first_attempt(self):
        with patch.dict("os.environ",{"GITHUB_REPOSITORY":"elsewhere",
                                       "GITHUB_REF":"refs/heads/main",
                                       "GITHUB_RUN_ATTEMPT":"1",
                                       "GITHUB_EVENT_NAME":"push"}):
            with self.assertRaisesRegex(ArenaError,
                                        "REAL_OMC_GITHUB_MAIN_FIRST_ATTEMPT_ONLY"):
                p08.run("/not/opened")

    def test_csv_mass_checks_not_fake_native_simulation(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"fixture.csv"
            with path.open("w",newline="") as fp:
                writer=csv.writer(fp)
                writer.writerow(["time","deliveredTotal","preparation0.waiting",
                                 "espresso0.waiting","dispatch0.waiting"])
                # Synthetic linear trace solely to test parsing, not authentic
                # queue dynamics or a scientific result.
                for k in range(p08.INTERVALS+1):
                    t=k*p08.STOP/p08.INTERVALS
                    delivered=19*min(t/p08.INPUT_HORIZON_MIN*60,1)
                    open_work=19-delivered if t<p08.INPUT_HORIZON_MIN/60 else 0
                    writer.writerow([t,delivered,open_work,0,0])
            record={"input_paid_orders":19}
            checked=p08.audit_csv(path,record)
            self.assertAlmostEqual(
                checked["modeled_delivered_after_drain"],19)
            record["input_paid_orders"]=46
            with self.assertRaisesRegex(ArenaError,"MATERIAL_BALANCE_OR_DRAIN_FAILURE"):
                p08.audit_csv(path,record)


if __name__=="__main__":
    unittest.main()
