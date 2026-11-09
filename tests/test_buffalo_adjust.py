"""Focused BF-00/BF-01/BF-02 regressions; never call provider or OMC."""
import copy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.buffalo.validation import diagnose, classify_provider, linear_lookup
from arena.buffalo.capabilities import (exact_public_pulse, normalize_units_only,
    capability_report, exact_pulse_equation, pulse_fixture, eval_fixture_equation, native_hash)
from arena.buffalo.feedback import freeze_profile,own_feedback
from arena.buffalo import adjust
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

    def test_invalid_equation_syntax_is_an_error_not_a_missing_symbol(self):
        doc=neutral()
        doc["model"]["variables"][0]["equation"]="Pulse_rate +"
        report=diagnose(doc)
        self.assertFalse(report["admissible"])
        errors=[x for x in report["diagnostics"]
                if x["code"]=="INVALID_NATIVE_EXPRESSION"]
        self.assertEqual(len(errors),1)
        self.assertEqual(errors[0]["variable"],"Arrivals")
        self.assertEqual(errors[0]["field"],"equation")
        self.assertEqual(errors[0]["evidence"]["translator_error"],
                         "UNSUPPORTED_EXPRESSION_SYNTAX")

    def test_valid_constant_lookup_gain_is_not_globally_rejected(self):
        from arena._vendor.igc.scripts.arena_b_native_to_modelica import generate
        doc=pulse_fixture()
        doc["model"]["variables"].append({
            "name":"Gain", "type":"variable", "equation":"1", "units":"",
            "inflows":[], "outflows":[], "uniflow":False,
            "documentation":"Neutral software fixture; not Buffalo output",
            "graphicalFunction":{"points":[
                {"x":0,"y":0.5},{"x":1,"y":1},{"x":2,"y":1.5}]}})
        arrivals=next(v for v in doc["model"]["variables"] if v["name"]=="Arrivals")
        arrivals["equation"]=exact_pulse_equation()+" * Gain"
        report=diagnose(doc)
        self.assertTrue(report["admissible"],report["diagnostics"])
        warns=[x for x in report["diagnostics"]
               if x["code"]=="LOOKUP_APPLIED_TO_CONSTANT"]
        self.assertEqual(len(warns),1)
        self.assertEqual(warns[0]["severity"],"WARNING")
        self.assertEqual(warns[0]["evidence"]["effective_value"],1)
        self.assertFalse(any(x["code"]=="ZERO_LOOKUP_USED_AS_DIVISOR"
                             for x in report["diagnostics"]))
        _,modelica,_=generate(doc)
        self.assertIn("lookup_Gain",modelica)

    def test_zero_lookup_used_as_unguarded_divisor_is_error(self):
        doc=neutral()
        t=doc["model"]["variables"][-1]
        t["equation"]="2.8"
        t["graphicalFunction"]["points"]=[
            {"x":0,"y":1.7},{"x":1.9,"y":1.7},{"x":2,"y":0},{"x":8,"y":0}]
        report=diagnose(doc)
        self.assertFalse(report["admissible"])
        errors=[x for x in report["diagnostics"]
                if x["code"]=="ZERO_LOOKUP_USED_AS_DIVISOR"]
        self.assertEqual(len(errors),1)
        self.assertEqual(errors[0]["variable"],"Completions")
        self.assertEqual(errors[0]["evidence"]["denominator"],"Mean_time")
        self.assertEqual(errors[0]["evidence"]["effective_value"],0)
        # Safe // returns zero when denominator zero; record without
        # claiming it is a plain division exception.
        doc["model"]["variables"][1]["equation"]="Work // Mean_time"
        report=diagnose(doc)
        self.assertTrue(report["admissible"],report["diagnostics"])
        self.assertIn("ZERO_LOOKUP_USED_IN_SAFE_DIVISION",
                      [x["code"] for x in report["diagnostics"]])

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

    def test_exact_pulse_safe_division_compiles_in_original_modelica_translator(self):
        from fractions import Fraction
        from arena._vendor.igc.scripts.arena_b_native_to_modelica import generate
        self.assertEqual(exact_public_pulse(-1),0)
        self.assertEqual(exact_public_pulse(0),1.7)
        self.assertEqual(exact_public_pulse(1.999999),1.7)
        self.assertEqual(exact_public_pulse(2),0)
        self.assertEqual(exact_public_pulse(8),0)
        expr=exact_pulse_equation()
        self.assertIn("//",expr)
        for t in ("-1","-1/1000","0","1/2","1","39/20","1999/1000",
                  "2","2001/1000"):
            x=Fraction(t)
            self.assertEqual(eval_fixture_equation(expr,time=x),
                             Fraction("1.7") if 0<=x<2 else Fraction(0))
        self.assertTrue(diagnose(pulse_fixture())["admissible"])
        modelname,modelica,report=generate(pulse_fixture())
        self.assertTrue(modelname.startswith("BuffaloNative_"))
        self.assertIn("if (",modelica)
        self.assertIn("then 0 else",modelica)
        self.assertIn("EXACT_ZERO_SAFE_DIVISION_FOR_BUFFALO_DOUBLE_SLASH",
                      report["assumptions"])
        c=capability_report()
        self.assertEqual(c["physical_compatibility"],
                         "EXACT_PULSE_STATICALLY_TRANSLATABLE_MODELICA")
        self.assertEqual(c["exact_public_input"]["analytic_mass"],
                         "17/10 * 2 = 17/5 = 3.4")
        self.assertEqual(c["exact_public_input"]["modelica_simulation_executed"],False)
        self.assertEqual(c["exact_public_input"]["buffalo_model_generated_by_fixture"],False)
        self.assertEqual(c["exact_public_input"]["xmile_pysd_safe_division_parity"],
                         "UNPROVEN_XMILE_REPLACES_DOUBLE_SLASH")
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

    def test_offline_bundle_archives_entire_normalized_native_with_hash(self):
        """Read back both manifest and native; never substitute one for the other."""
        with TemporaryDirectory() as temp:
            root=Path(temp)/"workspace"
            evidence=Path(temp)/"evidence"
            root.mkdir()
            parent=neutral()
            parent["model"]["specs"]["timeUnits"]="hours"
            parent["model"]["variables"][-1]["units"]="hours"
            source_hash="sha256:public-test"
            world="world-test"
            receipt_base={"source_snapshot_hash":source_hash,
                          "world_public_id":world,"provider_calls":1}
            sources={
                "ct03_raw":{"result":{"choices":[{"finish_reason":"length",
                          "message":{"content":""}}],
                          "usage":{"completion_tokens":16000}}},
                "ct03_receipt":{**receipt_base,"model_returned":False},
                "parent_raw":{"result":{"choices":[{"finish_reason":"stop",
                          "message":{"content":"model"}}],
                          "usage":{"completion_tokens":100}}},
                "parent_receipt":{**receipt_base,
                    "model_returned":True,"round_kind":"initial",
                    "status":"ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED",
                    "result_sha256":"sha256:parent-test"},
                "parent_native":parent,
                "parent_visible":{"question":"test-public-only"},
            }
            source={}
            for name,data in sources.items():
                relative=SOURCE[name][0]
                path=evidence/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                blob=json.dumps(data).encode()
                path.write_bytes(blob)
                source[name]=(relative,sha256(blob).hexdigest())
            public={"world_public_id":world,"source_snapshot_hash":source_hash}
            with patch.object(adjust,"SOURCE",source),patch.object(
                    adjust,"public_input",return_value=public):
                result=offline_bundle(root,evidence)
            out=root/"artifacts/buffalo-adjust-v1"
            archived=json.loads((out/"bf01-normalized-native.json").read_text())
            manifest=json.loads((out/"bf01-unit-manifest.json").read_text())
            self.assertEqual(archived["model"]["specs"]["timeUnits"],"hour")
            self.assertEqual(archived["model"]["variables"][-1]["units"],"hour")
            self.assertEqual(parent["model"]["specs"]["timeUnits"],"hours")
            self.assertEqual(manifest["view_sha256"],native_hash(archived))
            self.assertEqual(manifest["original_sha256"],native_hash(parent))
            self.assertEqual(manifest["normalized_native_file"],
                             "bf01-normalized-native.json")
            self.assertEqual(result["bf01"]["normalized_native_sha256"],
                             native_hash(archived))
            self.assertEqual(result["gate"],
                             "BLOCKED_PAID_PHASES_NOT_IMPLEMENTED_OR_AUTHORIZED")
            self.assertEqual(result["actual_consumption"],
                             {"provider_posts":0,"new_omc":0,"new_worlds":0})

    def test_budget_and_live_gate_are_not_a_post_authorization(self):
        self.assertEqual((MAX_POSTS,MAX_OMC),(2,1))
        w=(Path(__file__).resolve().parents[1]/
           ".github/workflows/buffalo-only.yml").read_text()
        self.assertIn("adjust-check",w)
        self.assertIn("adjust-live",w)
        self.assertIn("python -m arena.buffalo.execution admit",w)
        self.assertIn("python -m arena.buffalo.execution generate",w)
        self.assertIn("python -m arena.buffalo.execution physical",w)
        self.assertIn("if: always()",w)
        self.assertNotIn("arena-custodian",w)
        self.assertNotIn("python -m arena.cloud world",w)
        self.assertNotIn("python -m arena.cloud dm",w)


if __name__=="__main__":
    unittest.main()
