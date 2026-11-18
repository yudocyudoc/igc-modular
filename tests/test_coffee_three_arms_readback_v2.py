"""PR1 V2: offline+public-artifact regressions; no OMC, provider or R2.

The acceptance workflow supplies previously published authentic ZIPs. The
negative tests synthesize tampered ZIPs under temporary directories only.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from arena import coffee_three_arms_readback_v2 as r


class ReadbackV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get("ARENA_PUBLIC_ZIP_DIR")
        if not value:
            # Generic offline CI has no historical ZIPs and must not access
            # GitHub/provider on its own. Dedicated PR48 CI explicitly
            # asserts that all eight ZIPs exist before running these tests.
            raise unittest.SkipTest("AUTHENTIC_PUBLIC_ARTIFACTS_NOT_MOUNTED_IN_GENERIC_OFFLINE_CI")
        cls.directory=Path(value)
        cls.report=r.readback(cls.directory)

    def modify(self, source, key, transform):
        """Make a verified-looking forged ZIP to test INNER source contract."""
        with tempfile.TemporaryDirectory() as path:
            p=Path(path)
            for _, (_,artifact,_,_) in r.SOURCES.items():
                src=self.directory / ("artifact-"+str(artifact)+".zip")
                (p/src.name).write_bytes(src.read_bytes())
            _,artifact,_,_=r.SOURCES[source]
            src=p/("artifact-"+str(artifact)+".zip")
            with zipfile.ZipFile(src) as z:
                members={k:z.read(k) for k in z.namelist()}
            obj=json.loads(members[key]);transform(obj)
            members[key]=json.dumps(obj,ensure_ascii=False).encode()
            with zipfile.ZipFile(src,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for name,value in members.items():z.writestr(name,value)
            pinned=r.SOURCES[source]
            with patch.dict(r.SOURCES,{source:(*pinned[:3],r.sha_bytes(src.read_bytes())[7:])}):
                yield r.readback(p)

    def test_real_sources_exactly_8_pinned_and_crosslink_12_original_models(self):
        x=self.report
        self.assertEqual(x["schema"],r.SCHEMA)
        self.assertEqual(len(x["source_registry"]),8)
        self.assertEqual(x["original_B0"]["G2_authenticated"],12)
        rows=x["original_B0"]["candidate_receipts"]
        self.assertEqual(len(rows),12)
        self.assertEqual([i["arm"] for i in rows].count("D"),6)
        self.assertEqual([i["arm"] for i in rows].count("M"),6)
        self.assertEqual({i["policy_status"] for i in rows if i["arm"]=="D"},{"RATIFIED"})
        self.assertEqual({i["policy_status"] for i in rows if i["arm"]=="M"},{"ABSTAINED"})
        self.assertEqual({i["policy_reason"] for i in rows if i["arm"]=="M"},
                         {"NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS"})
        self.assertTrue(all(i["feedback_projection_hash"] for i in rows))

    def test_real_buffalo_parent_r1_not_replaced_by_hydra_or_first_packet(self):
        x=self.report["buffalo_R1"]
        self.assertEqual(x["original_variables"],10)
        self.assertEqual(x["revised_variables"],11)
        self.assertEqual(x["original_relationships"],0)
        self.assertEqual(x["revised_relationships"],12)
        self.assertFalse(x["own_feedback_packet_sent_in_first_feedback_run"])
        self.assertTrue(x["later_original_currentModel_review_invoked"])
        self.assertEqual(x["r1_scientific_gate"],"G1_ONLY_NOT_G2_NOT_G3")
        self.assertAlmostEqual(x["sealed_b0_pickups_mae_orders"],0.8948896795738998)
        self.assertEqual(self.report["b0_sealed_scores"]["score_scope"],
                         "SYNTHETIC_B0_ONLY_NOT_FIELD_OPERATIONS")

    def test_real_p08_twice_same_numbers_not_two_independent_confirmations(self):
        rows=self.report["p08"]["same_values_rows"]
        self.assertEqual(len(rows),6)
        high={x["action"]:x for x in rows if x["load"]=="HIGHER_PAID_INPUT_Q75"}
        self.assertAlmostEqual(high["BASE"]["M_continuous_deliveries"],18.248947)
        self.assertAlmostEqual(high["PREP_CAPACITY_X2"]["D_continuous_deliveries"],23.134332)
        self.assertAlmostEqual(high["ESPRESSO_CAPACITY_X2"]["M_continuous_deliveries"],18.248947)
        self.assertTrue(self.report["p08"]["same_model_not_two_independent_confirmations"])
        self.assertFalse(self.report["shared_premises_example"]["two_independent_empirical_confirmations"])

    def test_real_hydra_load_worse_milk_better_and_h3_unobserved(self):
        q=self.report["hydra_q75"]
        self.assertEqual((q["paid_orders"],q["synthetic_beverages"]),(46,53))
        self.assertAlmostEqual(q["load_priority_P90_delta_s"],2.163)
        self.assertAlmostEqual(q["milk_priority_P90_delta_s"],-3.837)
        self.assertEqual((q["load_earlier"],q["load_later"]),(9,9))
        self.assertEqual((q["milk_earlier"],q["milk_later"]),(5,4))
        self.assertTrue(q["H3_group_retained_in_B_state_machine_but_no_real_episode_attributed"])

    def test_real_decision_is_retrospective_and_does_not_claim_value(self):
        x=self.report
        self.assertEqual(x["decision_with_Hydra_only"]["action"],
                         x["decision_with_Hydra_plus_DMB"]["action"])
        self.assertFalse(x["decision_with_Hydra_plus_DMB"]["incremental_operational_observation_demonstrated"])
        self.assertEqual(x["contribution_assessment"]["decisional"],
                         "PENDING_INDEPENDENT_PROSPECTIVE_CONTRAST")
        self.assertFalse(x["shared_premises_example"]["cross_arm_ATMS_what_if_executed_in_PR1"])
        self.assertTrue(x["limits"]["no_model_rerun_or_provider_calls_or_R2"])
        text=r.markdown(x)
        self.assertIn("RETROSPECTIVA, NO CIEGA",text)
        self.assertIn("NO se permite restar cuantías",text)
        self.assertIn("PENDIENTE DE CONTRASTE",text)

    def test_refuse_hydra_artifact_misrepresented_as_buffalo(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _,(_,aid,_,_) in r.SOURCES.items():
                original=self.directory/("artifact-"+str(aid)+".zip")
                (Path(tmp)/original.name).write_bytes(original.read_bytes())
            b_id=r.SOURCES["buffalo_r1"][1];h_id=r.SOURCES["hydra"][1]
            (Path(tmp)/(f"artifact-{b_id}.zip")).write_bytes(
                (Path(tmp)/(f"artifact-{h_id}.zip")).read_bytes())
            with self.assertRaisesRegex(r.SourceError,"PUBLIC_ZIP_DIGEST_MISMATCH_buffalo_r1"):
                r.readback(tmp)

    def test_refuse_p08_m_version_spoof_even_if_zip_rehashed(self):
        gen=self.modify("m_p08","manifest.json",lambda j:j.__setitem__(
            "method","short-e1-original-typed-graph-enumeration"))
        with self.assertRaisesRegex(r.SourceError,"M_P08_WRONG_VERSION_OR_UNAUTHENTIC_SIMULATION"):
            next(gen)

    def test_refuse_modified_parent_feedback_before_conclusion(self):
        def tamper(j):
            j["arms"]["D"]["candidates"][0]["parent_hash"]="sha256:"+"0"*64
        gen=self.modify("feedback","summary.json",tamper)
        with self.assertRaisesRegex(r.SourceError,"ORIGINAL_EVIDENCE_MISMATCH_D"):
            next(gen)

    def test_refuse_mismatched_buffalo_parent(self):
        proof=self.report["buffalo_R1"]
        with self.assertRaisesRegex(r.SourceError,"BUFFALO_REVIEW_PARENT_IDENTITY_MISMATCH"):
            r.validate_r1_parent(b"altered",{
                "parent_native_file_sha256":proof["parent_sha256"],
                "revised_native_file_sha256":proof["child_sha256"],
                "original_model_revised_by_original_Engine_generate":True},b"child")

    def test_refuse_numeric_p08_vs_hydra_or_same_order_count_wrong_pulse(self):
        good={"case":"P08_Q75","input_profile":"RECTANGULAR_105_MIN",
              "material_unit":"continuous_orders","horizon_min":105,
              "cut_min":105,"intervention":"PREP_CAPACITY_X2",
              "observable":"delivered_at_cut","observable_unit":"orders"}
        other=copy.deepcopy(good)
        other["input_profile"]="SAME_TOTAL_DIFFERENT_PAID_EVENTS"
        self.assertEqual(r.validate_comparable(good,other)["allowed"],"MECHANISM_ONLY")
        with self.assertRaisesRegex(r.SourceError,"NUMERIC_COMPARISON_FORBIDDEN_input_profile"):
            r.validate_comparable(good,other,numeric=True)
        bad=copy.deepcopy(good);bad["observable"]="p90"
        with self.assertRaisesRegex(r.SourceError,"NUMERIC_COMPARISON_FORBIDDEN_observable"):
            r.validate_comparable(good,bad,numeric=True)

    def test_no_false_h3_claim_from_timer_end_without_removal(self):
        h3=next(x for x in self.report["H1_H2_H3_method_matrix"]
                if x["method"]=="referencia Hydra")
        self.assertIn("NO_OBSERVED",h3["H3"])
        self.assertTrue(self.report["limits"]["H3_timer_stopping_not_proof_of_group_release"])
        self.assertEqual(self.report["contribution_assessment"]["decisional"],
                         "PENDING_INDEPENDENT_PROSPECTIVE_CONTRAST")


if __name__=="__main__":unittest.main()
