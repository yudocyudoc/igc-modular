"""All B outputs are SYNTHETIC live-shaped fixtures, not a provider POST."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_b_own_feedback import build,TRANSPORT,PIN
from scripts.arena_cafe.ct03_public import OBS_SCHEMA
from scripts.arena_cafe.e02_b_feedback import _model_sha
from test_arena_b_native_to_modelica import BuffaloNativeTranslatorTests

SRC="sha256:"+"a"*64
TIME="2026-11-07T12:00:00+00:00"

def public():
    return {
        "schema":OBS_SCHEMA,"world_public_id":"CT03_SYNTH_W1",
        "condition_id":"C0","source_snapshot_hash":SRC,
        "time_unit":"hours","observable":"cumulative_delivered",
        "observations":[{"time":t,"delivered":.1*t} for t in (0,1,2,4)]
    }

def fixture():
    native=BuffaloNativeTranslatorTests().model()
    receipt={
        "case_id":"CT-03","world_public_id":"CT03_SYNTH_W1",
        "condition_id":"C0","source_snapshot_hash":SRC,
        "round_kind":"initial","mode":"live",
        "provider_calls":1,"proxy_requests":1,"model_returned":True,
        "status":"ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED",
        "upstream_sha":PIN,"upstream_source_modified":False,
        "transport":TRANSPORT,"horizon_matches_case":True,
        "output_horizon_hours":8,
        "result_sha256":_model_sha(native),
    }
    return native,receipt

class BOriginalFeedbackTests(unittest.TestCase):
    def test_original_live_shape_translated_G1_then_own_ledger_packet_no_calls(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);native,receipt=fixture()
            result=build(original=native,receipt=receipt,construction=public(),
                         recorded_at=TIME,out=root/"B")
            self.assertTrue((root/"B/own-g1-diagnostic.json").exists())
            self.assertTrue((root/"B/own-revision-packet.json").exists())
            self.assertTrue((root/"B/b-own-feedback-ledger.sqlite").exists())
            self.assertTrue((root/"B/conditional-translated.mo").exists())
            self.assertEqual(result["G1_status"],
                             "NATIVE_TRANSLATION_CONDITIONAL_NEEDS_G2_AND_OBSERVABLE")
            self.assertTrue(result["modelica_translation_provisional"])
            self.assertFalse(result["native_delivery_observation_operator_verified"])
            self.assertEqual(result["provider_calls_by_this_adapter"],0)
            self.assertEqual(result["new_omc_by_this_adapter"],0)
            self.assertEqual(result["physical_B_G2_or_G3"],"NOT_EXECUTED")
            self.assertFalse(result["heldout_observations_read"])
            self.assertFalse(result["cross_arm_feedback_read"])
            self.assertFalse(result["source_model_rewritten"])
            from scripts.arena_cafe.ct_feedback_bridge import recover_feedback,make_context
            ctx=make_context(experiment="CT03",world="CT03_SYNTH_W1",round_id="R0",
                             arm="B",condition="C0",source_hash=SRC)
            recovered=recover_feedback(root/"B/b-own-feedback-ledger.sqlite",
                ctx,parent_hash=receipt["result_sha256"],
                as_known_at="2026-11-07T12:00:02+00:00")
            self.assertEqual(recovered["diagnostic_hash"],
                             result["own_diagnostic_sha256"])

    def test_nonrepresentable_native_becomes_B_G1_blocked_not_repaired(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);native,receipt=fixture()
            native["model"]["variables"][0]["subType"]="conveyor"
            receipt["result_sha256"]=_model_sha(native)
            result=build(original=native,receipt=receipt,construction=public(),
                         recorded_at=TIME,out=root/"B")
            self.assertEqual(result["G1_status"],
                             "G1_TRANSLATION_BLOCKED_ORIGINAL_UNCHANGED")
            self.assertIn("UNSUPPORTED_NATIVE_VARIABLE_FIELD",
                          result["G1_block_reason"])
            self.assertFalse(result["modelica_translation_provisional"])
            self.assertFalse((root/"B/conditional-translated.mo").exists())
            self.assertTrue((root/"B/own-revision-packet.json").exists())

    def test_wrong_world_or_provenance_blocks_before_ledger_creation(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);native,receipt=fixture()
            receipt["world_public_id"]="OTHER_WORLD"
            with self.assertRaisesRegex(ValueError,"ORIGINAL_LIVE_NATIVE_OR_RECEIPT_UNVERIFIED"):
                build(original=native,receipt=receipt,construction=public(),
                      recorded_at=TIME,out=root/"blocked")
            self.assertFalse((root/"blocked").exists())
            receipt["world_public_id"]="CT03_SYNTH_W1"
            receipt["result_sha256"]="sha256:"+"f"*64
            with self.assertRaisesRegex(ValueError,"ORIGINAL_LIVE_NATIVE_OR_RECEIPT_UNVERIFIED"):
                build(original=native,receipt=receipt,construction=public(),
                      recorded_at=TIME,out=root/"blocked")

if __name__=="__main__":
    unittest.main()
