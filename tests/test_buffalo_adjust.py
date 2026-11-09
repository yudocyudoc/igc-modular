"""Focused BF-00/BF-01/BF-02 regressions; never call provider or OMC."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.buffalo.validation import diagnose, classify_provider, linear_lookup
from arena.buffalo.capabilities import exact_public_pulse,normalize_units_only,capability_report
from arena.buffalo.feedback import freeze_profile,own_feedback
from arena.buffalo.adjust import MAX_POSTS, MAX_OMC, SOURCE,offline_bundle
from arena.common import ArenaError


def neutral():
    def v(name,kind,eq,units,inc=None,out=None):
        return {"name":name,"type":kind,"equation":eq,"units":units,
                "inflows":inc or [],"outflows":out or [],
                "graphicalFunction":{"points":[]}, "uniflow":kind=="flow"}
    return {"model":{"specs":{"startTime":0,"stopTime":8,"dt":0.125,
                              "timeUnits":"hour","integrationMethod":"Euler"},
                     "variables":[
                       v("Arrivals","flow","1.7","items/hour"),
                       v("Completions","flow","Work / Mean_time","items/hour"),
                       v("Work","stock","0","items",["Arrivals"],["Completions"]),
                       v("Delivered","stock","0","items",["Completions"]),
                       v("Mean time","variable","2.8","hour")],
                     "relationships":[]},
            "supportingInfo":{"explanation":"Hypothetical software fixture only."}}


class BuffaloAdjustTests(unittest.TestCase):
    def test_genuine_neutral_fixture_is_semantically_admitted(self):
        doc=neutral()
        doc["model"]["variables"][1]["equation"]="Work / Mean_time"
        self.assertTrue(diagnose(doc)["admissible"])
        self.assertFalse(diagnose(doc)["diagnostics"])

    def test_normalized_buffalo_underscores_are_valid_references(self):
        self.assertTrue(diagnose(neutral())["admissible"])

    def test_stock_feedback_is_not_mistaken_for_algebraic_cycle(self):
        doc=neutral()
        # Completions depends on Work, but Work is integrated over time.
        self.assertNotIn("ALGEBRAIC_CYCLE",
                         [x["code"] for x in diagnose(doc)["diagnostics"]])

    def test_self_reference_is_identified_and_rejected(self):
        doc=neutral()
        doc["model"]["variables"][-1]["equation"]="Mean_time"
        report=diagnose(doc)
        cycles=[x for x in report["diagnostics"] if x["code"]=="ALGEBRAIC_CYCLE"]
        self.assertEqual(len(cycles),1)
        self.assertEqual(cycles[0]["evidence"]["path"],["Mean_time","Mean_time"])

    def test_stock_flow_table_is_error_and_not_removed(self):
        doc=neutral()
        points=[{"x":0,"y":1.7},{"x":2,"y":0}]
        doc["model"]["variables"][0]["graphicalFunction"]["points"]=points
        report=diagnose(doc)
        self.assertIn("LOOKUP_UNSUPPORTED_FOR_MATERIAL_TYPE",
                      [x["code"] for x in report["diagnostics"]])
        self.assertEqual(doc["model"]["variables"][0]["graphicalFunction"]["points"],points)

    def test_scalar_auxiliary_lookup_has_effect_not_decoration(self):
        doc=neutral()
        t=doc["model"]["variables"][-1]
        t["equation"]="2.8"
        t["graphicalFunction"]["points"]=[
            {"x":0,"y":1.7},{"x":1.9,"y":1.7},{"x":2,"y":0},{"x":8,"y":0}]
        d=[x for x in diagnose(doc)["diagnostics"]
           if x["code"]=="LOOKUP_APPLIED_TO_CONSTANT"]
        self.assertEqual(len(d),1)
        self.assertEqual(d[0]["evidence"]["effective_value"],0)

    def test_trapezoid_3315_differs_from_exact_mass_34(self):
        doc=neutral()
        v=doc["model"]["variables"][-1]
        v["name"]="input rate profile"
        v["equation"]="TIME"
        v["graphicalFunction"]["points"]=[
            {"x":0,"y":1.7},{"x":1.9,"y":1.7},{"x":2,"y":0},{"x":8,"y":0}]
        report=diagnose(doc)
        row=next(x for x in report["diagnostics"]
                 if x["code"]=="LINEAR_TABLE_NOT_EXACT_PUBLIC_PULSE")
        self.assertEqual(row["evidence"]["piecewise_linear_mass"],3.315)
        self.assertEqual(row["evidence"]["public_exact_mass"],3.4)

    def test_length_and_empty_content_are_jointly_required(self):
        def raw(finish,content,tokens):
            return {"result":{"choices":[{"finish_reason":finish,
                                            "message":{"content":content}}],
                              "usage":{"completion_tokens":tokens}}}
        self.assertEqual(classify_provider(raw("length","",16000))[0]["code"],
                         "OUTPUT_BUDGET_EXHAUSTED_NO_FINAL_CONTENT")
        self.assertNotIn("OUTPUT_BUDGET_EXHAUSTED_NO_FINAL_CONTENT",
                         [r["code"] for r in classify_provider(raw("length","not empty",16000))])
        self.assertNotIn("OUTPUT_BUDGET_EXHAUSTED_NO_FINAL_CONTENT",
                         [r["code"] for r in classify_provider(raw("stop","",16000))])

    def test_unit_alias_is_view_only_and_exact(self):
        original=neutral()
        original["model"]["specs"]["timeUnits"]="hours"
        original["model"]["variables"][-1]["units"]="hours"
        copy_before=copy.deepcopy(original)
        manifest,view=normalize_units_only(original)
        self.assertEqual(original,copy_before)
        self.assertEqual(view["model"]["specs"]["timeUnits"],"hour")
        self.assertEqual(view["model"]["variables"][-1]["units"],"hour")
        self.assertEqual(len(manifest["transformations"]),2)
        self.assertEqual(view["model"]["variables"][-1]["equation"],"2.8")
        self.assertEqual(manifest["scale_factor"],1)

    def test_exact_discontinuous_input_and_backend_gap(self):
        self.assertEqual(exact_public_pulse(-1),0)
        self.assertEqual(exact_public_pulse(0),1.7)
        self.assertEqual(exact_public_pulse(1.999999),1.7)
        self.assertEqual(exact_public_pulse(2),0)
        self.assertEqual(exact_public_pulse(8),0)
        c=capability_report()
        self.assertEqual(c["physical_compatibility"],"INPUT_CAPABILITY_GAP")
        self.assertTrue(c["original_system_prohibits_conditionals"])
        self.assertEqual(c["max_completion_tokens"],16000)

    def test_profile_is_frozen_and_parent_feedback_is_not_a_repair(self):
        profile=freeze_profile()
        self.assertEqual(profile["utf8_sha256"],freeze_profile()["utf8_sha256"])
        parent=neutral()
        receipt={"model_returned":True,"provider_calls":1,
                 "round_kind":"initial","status":"ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED",
                 "source_snapshot_hash":"sha256:abc","world_public_id":"public-world",
                 "result_sha256":"sha256:parent"}
        public={"source_snapshot_hash":"sha256:abc",
                "world_public_id":"public-world","observations":[0,1,2,4]}
        packet=own_feedback(parent,receipt,public,profile)
        self.assertTrue(packet["not_a_repaired_native"])
        self.assertFalse("model" in packet)
        self.assertTrue(packet["not_physical_measurement"])
        self.assertEqual(packet["public_construction"],public)

    def test_budget_and_live_gate_are_not_a_post_authorization(self):
        self.assertEqual((MAX_POSTS,MAX_OMC),(2,1))
        w=(Path(__file__).resolve().parents[1]/
           ".github/workflows/buffalo-only.yml").read_text()
        self.assertIn("adjust-check",w)
        self.assertIn("adjust-live",w)
        self.assertIn("authorize-live",w)
        self.assertNotIn("arena-custodian",w)
        self.assertNotIn("python -m arena.cloud world",w)
        self.assertNotIn("python -m arena.cloud dm",w)


if __name__=="__main__":
    unittest.main()
