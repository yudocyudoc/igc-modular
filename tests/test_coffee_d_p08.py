"""GitHub-only P08 D grammar extension contract; no local OMC."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError, read_json
from arena import coffee_d_p08 as d
from test_coffee_m_p08 import stage


class P08DNativeTests(unittest.TestCase):
    def test_original_d_topology_and_all_differential_equations_preserved(self):
        src=d.d.original()
        g=src.topology(3,False)
        key=src.digest(g)
        base=src.modelica({
            "structure":g,"structure_hash":key,
            "nominal_parameters":{
                "capacity":12.0,"response_time":0.1,"loss_time":1000000.0,
            },
        },{"kind":"pulse","rate":20.0,"duration":1.75})
        altered,_=d.versioned_model(
            src,{"kind":"pulse","rate":20.0,"duration":1.75},
            name="DP08_CHECK_PREP_CAPACITY_X2",caps=d.capacities("PREP_CAPACITY_X2"))
        derivatives=lambda s:[x for x in s.splitlines() if x.lstrip().startswith("der(")]
        self.assertEqual(derivatives(base),derivatives(altered))
        self.assertEqual(len(derivatives(altered)),5)
        self.assertEqual(altered.count("  f1 = min(stageCap1"),1)
        self.assertEqual(altered.count("  f2 = min(stageCap2"),1)
        self.assertEqual(altered.count("  f3 = min(stageCap3"),1)
        self.assertIn("parameter Real stageCap1 = 24;",altered)
        self.assertIn("parameter Real stageCap2 = 15;",altered)
        self.assertIn("parameter Real stageCap3 = 100;",altered)
        self.assertEqual(src.topology(3,False),g)

    def test_all_six_stage_only_variants_prepared_from_verified_source(self):
        with TemporaryDirectory() as tmp:
            inp=stage(tmp)
            manifest=d.prepare(inp,Path(tmp)/"D")
            self.assertEqual(len(manifest["models"]),6)
            self.assertEqual(manifest["max_new_omc"],6)
            self.assertEqual(manifest["translation"],
                             "ONLY_SHARED_CAPACITY_TO_STAGE_CAP1_2_3")
            for label in d.LOADS:
                subset=[r for r in manifest["models"] if r["load_label"]==label]
                self.assertEqual({r["variant"] for r in subset},set(d.VARIANTS))
                self.assertEqual(
                    len({r["rectangular_rate_per_hour"] for r in subset}),1)
                for row in subset:
                    self.assertEqual(row["stage_caps_per_hour"],
                                     list(d.capacities(row["variant"])))
                    script=(Path(tmp)/"D"/row["script_file"]).read_text()
                    self.assertEqual(script.count("simulate("),1)
                    self.assertEqual(script.count("checkModel("),1)
                    self.assertNotIn("Cloudflare",script)
                    self.assertNotIn("POST",script)
            self.assertFalse(manifest["original_source_edited"])
            self.assertFalse(manifest["truth_read"])

    def test_rejects_forged_artifact_and_unknown_capacity(self):
        with TemporaryDirectory() as tmp:
            inp=stage(tmp)
            inp.write_text(inp.read_text()+"\n")
            with self.assertRaisesRegex(ArenaError,"SOURCE_MEMBER_HASH_CHANGED"):
                d.prepare(inp,Path(tmp)/"D")
        with self.assertRaisesRegex(ArenaError,"UNDECLARED_CAPACITY_VARIANT"):
            d.capacities("INSERT_FUTURE_POLICY")
        with self.assertRaisesRegex(ArenaError,"CAPACITY_VECTOR_OUT_OF_SCOPE"):
            d.versioned_model(d.d.original(),
                {"kind":"pulse","rate":20,"duration":1.75},
                name="DP08_FORGED",caps=(0,15,100))

    def test_synthetic_trace_only_tests_csv_audit_not_solver(self):
        with TemporaryDirectory() as tmp:
            f=Path(tmp)/"D.csv"
            with f.open("w",newline="") as out:
                writer=csv.writer(out)
                writer.writerow(["time","delivered","lost","s1","s2","s3"])
                for i in range(d.INTERVALS+1):
                    t=i*d.STOP_HOURS/d.INTERVALS
                    y=19*min(t/d.HORIZON_HOURS,1.0)
                    writer.writerow([t,y,0,max(0,19-y),0,0])
            rec={"input_paid_orders":19,"rectangular_rate_per_hour":
                 19/d.HORIZON_HOURS}
            result=d.verify_csv(f,rec)
            self.assertEqual(result["modeled_delivered_after_drain"],19.0)
            wrong=dict(rec,input_paid_orders=46)
            with self.assertRaisesRegex(ArenaError,
                                        "DRAIN_OR_ORDER_CONSERVATION_FAILED"):
                d.verify_csv(f,wrong)

    def test_omc_cannot_run_as_pr_or_locally(self):
        with patch.dict("os.environ",{
            "GITHUB_REPOSITORY":"yudocyudoc/igc-modular",
            "GITHUB_REF":"refs/pull/37/merge",
            "GITHUB_EVENT_NAME":"pull_request",
            "GITHUB_RUN_ATTEMPT":"1"}):
            with self.assertRaisesRegex(ArenaError,
                                        "NATIVE_OMC_ONLY_MAIN_FIRST_ATTEMPT"):
                d.run("/must-not-open")


if __name__=="__main__":
    unittest.main()
