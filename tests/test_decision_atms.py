"""ATMS decision contracts. All cases fictitious; tests execute in GitHub."""
from datetime import datetime, timedelta, timezone
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError, digest, read_json, write_json
from arena import decision_atms as atms
from arena import decision_atms_gate as execution_gate
from arena import coffee_e2e as e2e
from test_coffee_v2_reference import dossier
from test_coffee_v2_p11 import contract

BASE = datetime(2026, 11, 15, tzinfo=timezone.utc)
SRC = digest({"source":"fictional fixture not business evidence"})


def t(n):
    return (BASE + timedelta(microseconds=n)).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def add(j, op, eventid, i, **kwargs):
    j.append(atms.event(op, eventid, t(i), SRC, **kwargs))


def simple_pre():
    return atms.scenario_predecision(
        dossier(), contract(), recorded_at=t(100))


def nominal_policy(pre, low=0, high=1):
    return {
        "schema": "arena.coffee-v2.p11-conditional-policy/1",
        "status": "P11_CONDITIONAL_CONSEQUENCES_NOT_BUSINESS_RECOMMENDATION",
        "dossier_sha256": pre["dossier_sha256"],
        "protocol_sha256": pre["protocol_sha256"],
        "atms_predecision_snapshot_sha256": pre["snapshot"]["snapshot_sha256"],
        "summary": {
            "nominal_delta_by_load": {"LOWER":low, "HIGHER":high},
            "physical_reference_simulations":52,
            "paired_counterfactual_model_runs":26,
            "min_delta_peak_handoffs":0,
            "max_delta_peak_handoffs":2,
            "economic_grid_sign_counts":{"TIE_IF_ASSUMPTIONS":234},
        },
    }


def sealed_native():
    return {
        "truth_read_after_archived_lock": True,
        "policy_support_by_original_arms": {
            "D":"S5_NOT_REPRESENTABLE",
            "M":"S5_NOT_REPRESENTABLE",
            "B":"S5_NOT_REPRESENTABLE"},
        "lock_sha256": digest({"fixture":"pre-reveal prediction archive"}),
        "scores": [], "new_omc_attempts": 0,
    }


class DecisionAtmsTests(unittest.TestCase):
    def test_minimal_and_or_nogood_retract_restore_as_of(self):
        j=atms.Journal()
        add(j,"assumption","A",0,node="A_NODE",status="ASSUMED")
        add(j,"assumption","B",1,node="B_NODE",status="ASSUMED")
        add(j,"assumption","C",2,node="C_NODE",status="ASSUMED")
        add(j,"justification","J_A",3,conclusion="X",premises=["A_NODE"])
        add(j,"justification","J_B",4,conclusion="X",premises=["B_NODE"])
        add(j,"justification","J_Y",5,conclusion="Y",premises=["X","C_NODE"])
        first=j.snapshot(as_known_at=t(6),valid_at=t(6))
        self.assertEqual(first["labels"]["X"],[["A"],["B"]])
        self.assertEqual(first["labels"]["Y"],[["A","C"],["B","C"]])
        add(j,"nogood","NG_BC",7,assumptions=["B","C"])
        blocked=j.snapshot(as_known_at=t(8),valid_at=t(8))
        self.assertEqual(blocked["labels"]["X"],[["A"],["B"]])
        self.assertEqual(blocked["labels"]["Y"],[["A","C"]])
        add(j,"retract","R_A",9,target="A")
        after=j.snapshot(as_known_at=t(10),valid_at=t(10))
        self.assertNotIn("Y",after["labels"])
        self.assertEqual(after["labels"]["X"],[["B"]])
        self.assertEqual(j.snapshot(as_known_at=t(6),valid_at=t(6)),first)
        add(j,"restore","RESTORE_A",11,target="A")
        restored=j.snapshot(as_known_at=t(12),valid_at=t(12))
        self.assertEqual(restored["labels"]["Y"],[["A","C"]])
        self.assertNotEqual(first["journal_sha256"],
                            restored["journal_sha256"])
        self.assertNotEqual(first["snapshot_sha256"],
                            restored["snapshot_sha256"])
        explanation=j.explain("Y",as_known_at=t(12),valid_at=t(12))
        self.assertEqual(explanation["logical_support_environments"],
                         [["A","C"]])

    def test_ephemeral_what_if_reports_impacts_without_changing_canon(self):
        j=atms.Journal()
        add(j,"assumption","A",0,node="A_NODE",status="ASSUMED")
        add(j,"assumption","B",1,node="B_NODE",status="ASSUMED")
        add(j,"justification","JOIN",2,conclusion="HYPOTHESIS",
            premises=["A_NODE","B_NODE"])
        canonical=j.snapshot(as_known_at=t(3),valid_at=t(3))
        hypothetical=j.what_if(
            as_known_at=t(3),valid_at=t(3),
            candidate_events=[
                atms.event("retract","HYPOTHETICAL_RETIRE",t(4),SRC,
                           target="A")])
        self.assertTrue(hypothetical["hypothetical_only"])
        self.assertEqual(hypothetical["changed_labels"]["HYPOTHESIS"],{
            "before":[["A","B"]],"after":[]})
        self.assertEqual(
            j.snapshot(as_known_at=t(3),valid_at=t(3)), canonical)
        self.assertEqual(len(j.events),3)
        self.assertEqual(hypothetical["canonical_journal_sha256_unchanged"],
                         digest(j.events))

    def test_contextual_unsupported_cycles_future_and_provenance(self):
        j=atms.Journal()
        add(j,"justification","CY1",0,conclusion="CYCLE_X",
            premises=["CYCLE_Y"])
        add(j,"justification","CY2",1,conclusion="CYCLE_Y",
            premises=["CYCLE_X"])
        no_roots=j.snapshot(as_known_at=t(2),valid_at=t(2))
        self.assertNotIn("CYCLE_X",no_roots["labels"])
        add(j,"assumption","ROOT",3,node="CYCLE_X",status="ASSUMED")
        self.assertEqual(j.snapshot(as_known_at=t(4),valid_at=t(4))[
            "labels"]["CYCLE_Y"], [["ROOT"]])
        self.assertNotIn("CYCLE_X",no_roots["labels"])
        future=j.snapshot(as_known_at=t(2),valid_at=t(2))
        self.assertNotIn("ROOT",future["active_event_ids"])
        with self.assertRaisesRegex(ArenaError,"SCOPE_NOT_AUTHORIZED"):
            j.append(dict(atms.event("assumption","FOREIGN",t(5),SRC,
                                     node="SECRET",status="ASSUMED"),
                          scope="EVALUATION"))
        with self.assertRaisesRegex(ArenaError,"MISSING_PROVENANCE_SHA"):
            j.append(atms.event("assumption","BADHASH",t(5),"no-hash",
                                node="N",status="ASSUMED"))
        with self.assertRaisesRegex(ArenaError,"FUTURE_VALIDITY_QUERY"):
            j.snapshot(as_known_at=t(2),valid_at=t(4))
        with self.assertRaisesRegex(ArenaError,"RETRACTION_UNKNOWN_TARGET"):
            add(j,"retract","BAD_TARGET",6,target="MISSING")

    def test_event_record_immutable_and_retraction_must_not_modify_history(self):
        j=atms.Journal()
        e=atms.event("assumption","A",t(0),SRC,
                     node="SOME_NODE",status="ASSUMED")
        j.append(e)
        e["node"]="TAMPERED"
        self.assertIn("SOME_NODE", j.snapshot(
            as_known_at=t(1),valid_at=t(1))["labels"])
        with self.assertRaisesRegex(ArenaError,"DUPLICATE_EVENT_ID"):
            j.append(atms.event("assumption","A",t(2),SRC,
                                node="NEW",status="ASSUMED"))

    def test_predecision_is_only_synthetic_conditional_not_real(self):
        pre=simple_pre()
        self.assertTrue(pre["snapshot"]["labels"].get(
            "S5_CONDITIONAL_SIMULATABLE"))
        self.assertNotIn("S5_REAL_FEASIBLE",pre["snapshot"]["labels"])
        self.assertNotIn("S5_REAL_ECONOMIC_BENEFIT",
                         pre["snapshot"]["labels"])
        missing=pre["real_business_claim"][
            "missing_nodes_by_justification"]["J_S5_PROFIT"]
        self.assertIn("REAL_OPPORTUNITY_COST_VALIDATED",missing)
        self.assertTrue(pre["no_truth_access"])
        modified=dossier()
        modified["resources"]["existing_support"]["units"]=0
        with self.assertRaisesRegex(ArenaError,
                                    "NO_DECLARED_SUPPORT_FOR_S5"):
            atms.scenario_predecision(modified,contract(),recorded_at=t(100))

    def test_postseal_gain_is_simulated_not_business_evidence(self):
        pre=simple_pre()
        policy=nominal_policy(pre)
        native=sealed_native()
        post=atms.postevaluation(pre,policy,native,recorded_at=t(200))
        self.assertEqual(
            post["status"],"POST_SEAL_ATMS_UPDATED_NO_BUSINESS_RECOMMENDATION")
        self.assertTrue(post["conditionally_model_beneficial"])
        self.assertIn("S5_CONDITIONAL_MODEL_GAIN",post["changed_support_nodes"])
        self.assertFalse(post["real_business_benefit"][
            "logical_support_environments"])
        self.assertTrue(post["prior_snapshot_remains_reproducible"])
        self.assertEqual(
            atms.Journal(pre["journal"]).snapshot(
                as_known_at=pre["snapshot"]["as_known_at"],
                valid_at=pre["snapshot"]["valid_at"]), pre["snapshot"])
        policy0=nominal_policy(pre,0,0)
        post0=atms.postevaluation(pre,policy0,native,recorded_at=t(200))
        self.assertFalse(post0["conditionally_model_beneficial"])
        self.assertNotIn("S5_CONDITIONAL_MODEL_GAIN",
                         post0["post_snapshot"]["labels"])
        self.assertIn("NATIVE_DMB_DO_NOT_REPRESENT_S5",
                      post0["post_snapshot"]["labels"])

    def test_postseal_requires_parent_and_native_lock(self):
        pre=simple_pre()
        policy=nominal_policy(pre)
        native=sealed_native()
        invalid=copy.deepcopy(policy)
        invalid["dossier_sha256"]=SRC
        with self.assertRaisesRegex(ArenaError,"P11_RESULT_PARENT_MISMATCH"):
            atms.postevaluation(pre,invalid,native,recorded_at=t(200))
        invalid=copy.deepcopy(native)
        invalid["truth_read_after_archived_lock"]=False
        with self.assertRaisesRegex(ArenaError,"POST_LOCK_NATIVE_POLICY_BOUNDARY"):
            atms.postevaluation(pre,policy,invalid,recorded_at=t(200))
        invalid=copy.deepcopy(native)
        invalid["policy_support_by_original_arms"]["D"]="S5_SUPPORTED"
        with self.assertRaisesRegex(ArenaError,"POST_LOCK_NATIVE_POLICY_BOUNDARY"):
            atms.postevaluation(pre,policy,invalid,recorded_at=t(200))
        with self.assertRaisesRegex(ArenaError,"POST_NOT_AFTER_PREDECISION"):
            atms.postevaluation(pre,policy,native,recorded_at=t(101))

    def test_report_postseal_emits_linked_atms_and_preserves_legacy(self):
        pre=simple_pre()
        policy=nominal_policy(pre)
        native=sealed_native()
        with TemporaryDirectory() as d:
            root=Path(d)
            for part in ("admission","decision","evaluation"):
                (root/part).mkdir()
            write_json(root/"admission"/"admission-summary.json",
                       {"weekly_cases":54,"pos_rows":100})
            write_json(root/"decision"/"p11-conditional-summary.json",policy)
            write_json(root/"decision"/"atms-predecision.json",pre)
            admission=execution_gate.gate(pre,dossier(),contract())
            policy["atms_execution_gate_sha256"]=admission["gate_sha256"]
            write_json(root/"decision"/"p11-conditional-summary.json",policy)
            write_json(root/"decision"/"atms-execution-gate.json",
                       admission)
            write_json(root/"evaluation"/"evaluation.json",native)
            with patch.object(e2e.knowledge,"utc_now",return_value=t(200)):
                reported=e2e.final_report(
                    root/"evaluation",root/"decision",
                    root/"admission",root/"new-report")
            self.assertEqual(reported["status"],
                             "END_TO_END_COMPLETED_WITH_DECLARED_LIMITS")
            self.assertEqual(
                read_json(root/"new-report"/"result.json")["decision_atms_status"],
                "POST_SEAL_ATMS_UPDATED_NO_BUSINESS_RECOMMENDATION")
            receipt=read_json(root/"new-report"/"ATMS_DECISION.json")
            self.assertEqual(receipt["predecision_snapshot_sha256"],
                             pre["snapshot"]["snapshot_sha256"])
            self.assertIn("ATMS", (root/"new-report"/"REPORT.md").read_text(
                encoding="utf-8"))
            (root/"decision"/"atms-predecision.json").unlink()
            with self.assertRaisesRegex(ArenaError,
                                        "MISSING_MANDATORY_ATMS_PREDECISION"):
                e2e.final_report(root/"evaluation",root/"decision",
                                 root/"admission",root/"failed-report")
            old=copy.deepcopy(policy)
            old.pop("atms_predecision_snapshot_sha256")
            old.pop("atms_execution_gate_sha256")
            (root/"decision"/"atms-execution-gate.json").unlink()
            write_json(root/"decision"/"p11-conditional-summary.json",old)
            legacy=e2e.final_report(root/"evaluation",root/"decision",
                                    root/"admission",root/"legacy-report")
            self.assertEqual(legacy["status"],
                             "END_TO_END_COMPLETED_WITH_DECLARED_LIMITS")
            self.assertEqual(
                read_json(root/"legacy-report"/"result.json")["decision_atms_status"],
                "LEGACY_RUN_NO_PREDECISION_ATMS_NOT_RETROACTIVELY_CLAIMED")

    def test_run_decision_calls_admission_before_simulator(self):
        with TemporaryDirectory() as d:
            out=Path(d)/"decision"
            claimed={"status":"P11_CONDITIONAL_CONSEQUENCES_NOT_BUSINESS_RECOMMENDATION",
                     "summary":{"physical_reference_simulations":0}}
            invoked=[]
            def fake_compare(view,dossier_data,protocol_data):
                # The ATMS predecision has to run *before* the comparator.
                invoked.append("comparator")
                return copy.deepcopy(claimed)
            def fake_export(result,target):
                Path(target).mkdir(parents=True)
                write_json(Path(target)/"p11-conditional-summary.json",result)
            with patch.object(e2e,"execution_identity",return_value=(7,"f"*40)), \
                 patch.object(e2e.knowledge,"utc_now",return_value=t(300)), \
                 patch.object(e2e.decision,"compare",side_effect=fake_compare), \
                 patch.object(e2e.decision,"export",side_effect=fake_export):
                response=e2e.run_decision("fictional-producer",out)
            self.assertEqual(invoked,["comparator"])
            self.assertIn("atms_snapshot_sha256",response)
            self.assertEqual(read_json(out/"atms-predecision.json")["status"],
                "S5_ONLY_CONDITIONAL_SYNTHETIC_COMPARISON_ADMITTED")
            self.assertEqual(
                read_json(out/"p11-conditional-summary.json")[
                    "atms_predecision_snapshot_sha256"],
                response["atms_snapshot_sha256"])


if __name__ == "__main__":
    unittest.main()
