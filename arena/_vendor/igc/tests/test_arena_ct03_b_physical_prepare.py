"""Synthetic B live-shaped native; no provider, Docker, solver or hidden world."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_b_own_feedback import build
from scripts.arena_cafe.ct03_b_physical_prepare import prepare,operator
from test_arena_ct03_b_own_feedback import fixture,public,TIME as T
from scripts.arena_cafe.e02_b_feedback import _model_sha


class BPhysicsPreparationTests(unittest.TestCase):
    def test_unique_original_delivered_terminal_stock_generates_no_solver(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            native,receipt=fixture()
            feedback=build(original=native,receipt=receipt,construction=public(),
                           recorded_at=T,out=root/"G1")
            report=prepare(native,receipt,public(),feedback,root/"B-physical")
            self.assertEqual(report["status"],"B_NATIVE_PHYSICAL_PLANNED_NO_OMC")
            self.assertEqual(report["observation_operator"]["native_stock_name"],
                             "delivered work")
            self.assertEqual(report["observation_operator"]["modelica_csv_column"],
                             "delivered_work")
            self.assertIsNone(report["blocked_reason"])
            self.assertEqual(report["new_omc_by_this_step"],0)
            self.assertEqual(report["provider_calls_by_this_step"],0)
            script=(root/"B-physical/initial.mos").read_text()
            self.assertEqual(script.count("simulate("),1)
            self.assertIn('numberOfIntervals=64,method="euler"',script)
            self.assertIn("getVersion();",script)
            self.assertFalse((root/"B-physical/b-original_res.csv").exists())
            with self.assertRaisesRegex(ValueError,"NO_OVERWRITE"):
                prepare(native,receipt,public(),feedback,root/"B-physical")

    def test_native_conveyor_g1_blocks_without_fake_modelica(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            native,receipt=fixture()
            native["model"]["variables"][0]["subType"]="conveyor"
            receipt["result_sha256"]=_model_sha(native)
            feedback=build(original=native,receipt=receipt,construction=public(),
                           recorded_at=T,out=root/"G1")
            r=prepare(native,receipt,public(),feedback,root/"B-physical")
            self.assertEqual(r["status"],"B_NATIVE_G1_TRANSLATION_BLOCKED_NO_OMC")
            self.assertIn("UNSUPPORTED_NATIVE_VARIABLE_FIELD",r["blocked_reason"])
            self.assertIsNone(r["observation_operator"])
            self.assertFalse((root/"B-physical/initial.mos").exists())

    def test_no_delivery_or_ambiguous_sink_rejected_without_repair(self):
        native,receipt=fixture()
        no=copy.deepcopy(native)
        var=next(x for x in no["model"]["variables"]
                 if x["name"]=="delivered work")
        var["name"]="unlabeled stock"
        with self.assertRaisesRegex(ValueError,"MISSING_OR_AMBIGUOUS"):
            operator(no)
        alt=copy.deepcopy(native)
        alt["model"]["variables"].append({
            "name":"discarded work","type":"stock","equation":"0",
            "units":"items","inflows":["arrivals"],"outflows":[]
        })
        with self.assertRaisesRegex(ValueError,"ALTERNATIVE_TERMINAL_STOCK"):
            operator(alt)
        extra=copy.deepcopy(native)
        extra["model"]["variables"].append({
            "name":"delivery alternate","type":"stock","equation":"0",
            "units":"items","inflows":["arrivals"],"outflows":[]
        })
        with self.assertRaisesRegex(ValueError,"MISSING_OR_AMBIGUOUS"):
            operator(extra)

    def test_semantically_unresolved_port_is_not_native_G1_failure(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            native,receipt=fixture()
            sink=next(v for v in native["model"]["variables"]
                      if v["name"]=="delivered work")
            sink["name"]="completed output"
            for edge in native["model"]["relationships"]:
                if edge["to"]=="delivered work":
                    edge["to"]="completed output"
            receipt["result_sha256"]=_model_sha(native)
            feedback=build(original=native,receipt=receipt,construction=public(),
                           recorded_at=T,out=root/"G1")
            self.assertEqual(feedback["G1_status"],
                             "NATIVE_TRANSLATION_CONDITIONAL_NEEDS_G2_AND_OBSERVABLE")
            report=prepare(native,receipt,public(),feedback,root/"B-physical")
            self.assertEqual(report["status"],"B_OBSERVABLE_UNRESOLVED_NO_OMC")
            self.assertIsNone(report["observation_operator"])
            self.assertFalse((root/"B-physical/initial.mos").exists())
            self.assertIn("NOT proof",report["observable_scope"])

    def test_receipt_and_world_tamper_fails_before_output(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            native,receipt=fixture()
            feedback=build(original=native,receipt=receipt,construction=public(),
                           recorded_at=T,out=root/"G1")
            forged=copy.deepcopy(receipt)
            forged["result_sha256"]="sha256:"+"e"*64
            with self.assertRaisesRegex(ValueError,"RECEIPT_UNVERIFIED"):
                prepare(native,forged,public(),feedback,root/"B-physical")
            self.assertFalse((root/"B-physical").exists())

if __name__=="__main__":
    unittest.main()
