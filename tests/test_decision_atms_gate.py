"""GitHub-only fictional tests: ATMS supports actually control solver admission."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError, digest, read_json, write_json
from arena import coffee_e2e as arena
from arena import decision_atms as atms
from arena import decision_atms_gate as control
from test_decision_atms import t, SRC, simple_pre, nominal_policy, sealed_native
from test_coffee_v2_reference import dossier
from test_coffee_v2_p11 import contract


def change(op, ident, i, **fields):
    return atms.event(op, ident, t(i), SRC, **fields)


class AtmsOperationalGateTests(unittest.TestCase):
    def setUp(self):
        self.pre = simple_pre()
        self.dossier = dossier()
        self.protocol = contract()

    def gate(self, *revisions):
        return control.gate(self.pre, self.dossier, self.protocol,
                            revision_events=list(revisions))

    def test_supported_premises_admit_only_conditional_model(self):
        proof=self.gate()
        self.assertEqual(proof["status"],control.EXECUTE)
        self.assertEqual(proof["action"],"RUN_P11_CONDITIONAL_REFERENCE")
        self.assertTrue(proof["policy_support_environments"])
        self.assertEqual(proof["allowed_simulations"],52)
        self.assertEqual(control.require_executable(proof),
                         proof["atms_snapshot"]["snapshot_sha256"])
        self.assertNotIn("S5_REAL_FEASIBLE",
                         proof["atms_snapshot"]["labels"])
        self.assertNotIn("S5_REAL_ECONOMIC_BENEFIT",
                         proof["atms_snapshot"]["labels"])

    def test_retraction_blocks_model_and_restoration_recovers_admission(self):
        prior=self.gate()
        retired=change("retract","RETRACT_SUPPORT",108,target="A_SUPPORT")
        stopped=self.gate(retired)
        self.assertEqual(stopped["status"],control.ABSTAIN)
        self.assertEqual(stopped["action"],
                         "DO_NOT_RUN_P11_MEASURE_OR_REVISIT_PREMISES")
        self.assertEqual(stopped["allowed_simulations"],0)
        self.assertEqual(stopped["policy_support_environments"],[])
        self.assertIn("S5_CONDITIONAL_SIMULATABLE",
                      stopped["changed_support"])
        with self.assertRaisesRegex(ArenaError,
                                    "ABSTAIN_MEASURE_FIRST_NO_SIMULATOR"):
            control.require_executable(stopped)
        restored=change("restore","RESTORE_SUPPORT",109,target="A_SUPPORT")
        admitted=self.gate(retired,restored)
        self.assertEqual(admitted["status"],control.EXECUTE)
        control.require_executable(admitted)
        self.assertEqual(admitted["policy_support_environments"],
                         prior["policy_support_environments"])
        self.assertEqual(atms.Journal(self.pre["journal"]).snapshot(
                         as_known_at=self.pre["snapshot"]["as_known_at"],
                         valid_at=self.pre["snapshot"]["valid_at"]),
                         self.pre["snapshot"])

    def test_nogood_can_block_and_retraction_of_conflict_restores(self):
        conflict=change("nogood","INCOMPATIBLE_RESOURCES",108,
                        assumptions=["A_SUPPORT","A_HANDOFF"])
        blocked=self.gate(conflict)
        self.assertEqual(blocked["status"],control.ABSTAIN)
        cleared=change("retract","RETRACT_NOGOOD",109,
                       target="INCOMPATIBLE_RESOURCES")
        allow=self.gate(conflict,cleared)
        self.assertEqual(allow["status"],control.EXECUTE)
        self.assertNotIn("S5_REAL_ECONOMIC_BENEFIT",
                         allow["atms_snapshot"]["labels"])

    def test_retracting_non_necessary_real_business_rule_does_not_block_synthetic(self):
        # Future change to this graph should not confuse business admissibility
        # with its only allowed synthetic reference comparison.
        with self.assertRaisesRegex(ArenaError,
                                    "REVISION_OUTSIDE_P11_PREMISES"):
            self.gate(change("retract","BAD_RETRACT",108,
                             target="J_S5_PROFIT"))
        still_ok=self.gate(change("retract","RETRACT_PAIR_RULE",108,
                                  target="J_S5_SIM"),
                           change("restore","RESTORE_PAIR_RULE",109,
                                  target="J_S5_SIM"))
        self.assertEqual(still_ok["status"],control.EXECUTE)

    def test_no_fabricated_predecision_or_arbitrary_premises(self):
        corrupt=copy.deepcopy(self.pre)
        corrupt["journal"][0]["source_sha256"]=SRC
        with self.assertRaisesRegex(ArenaError,
                                    "PREDECISION_NOT_DERIVED"):
            control.gate(corrupt,self.dossier,self.protocol)
        with self.assertRaisesRegex(ArenaError,
                                    "NO_ARBITRARY_NEW_PREMISES"):
            self.gate(change("assumption","FALSIFY_SUPPORT",108,
                             node="SUPPORT_ACTUALLY_AVAILABLE",
                             status="EVIDENCED"))
        with self.assertRaisesRegex(ArenaError,
                                    "NO_ARBITRARY_NEW_PREMISES"):
            self.gate(change("justification","NEW_RULE",108,
                             conclusion="S5_REAL_FEASIBLE",
                             premises=["S5_CONDITIONAL_SIMULATABLE"]))
        with self.assertRaisesRegex(ArenaError,
                                    "REVISION_BEFORE_SEALED_PREDECISION"):
            self.gate(change("retract","PAST",103,
                             target="A_SUPPORT"))
        with self.assertRaisesRegex(ArenaError,
                                    "NO_RETROACTIVE_AUTHORING"):
            e=change("retract","RETRO",108,target="A_SUPPORT")
            e["valid_from"]=t(101)
            self.gate(e)

    def test_gate_receipt_is_verified_before_execution(self):
        valid=self.gate()
        forged=copy.deepcopy(valid)
        forged["status"]=control.ABSTAIN
        with self.assertRaisesRegex(ArenaError,"GATE_RECEIPT_MUTATED"):
            control.require_executable(forged)
        forged=copy.deepcopy(valid)
        forged["policy_support_environments"]=[]
        forged["gate_sha256"]=digest({
            k:v for k,v in forged.items() if k!="gate_sha256"})
        with self.assertRaisesRegex(ArenaError,
                                    "ABSTAIN_MEASURE_FIRST_NO_SIMULATOR"):
            control.require_executable(forged)

    def test_arena_blocks_before_p11_and_preserves_abstention_receipt(self):
        forbidden=[change("retract","RETRACT_SUPPORT",308,
                          target="A_SUPPORT")]
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            out=root/"blocked"
            with patch.object(arena,"execution_identity",
                              return_value=(7,"f"*40)), \
                 patch.object(arena.knowledge,"utc_now",
                              return_value=t(300)), \
                 patch.object(arena.decision,"compare") as compare, \
                 patch.object(arena.decision,"export") as export:
                with self.assertRaisesRegex(ArenaError,
                        "ABSTAIN_MEASURE_FIRST_NO_P11_SIMULATION"):
                    arena.run_decision("fictional-view",out,
                                      atms_revision_events=forbidden)
            compare.assert_not_called()
            export.assert_not_called()
            self.assertEqual(set(p.name for p in out.iterdir()),
                             {"atms-predecision.json",
                              "atms-execution-gate.json"})
            self.assertEqual(read_json(out/"atms-execution-gate.json")[
                             "allowed_simulations"],0)

    def test_arena_allows_only_after_restoration_and_links_gate(self):
        changes=[
            change("retract","RETRACT_SUPPORT",308,target="A_SUPPORT"),
            change("restore","RESTORE_SUPPORT",309,target="A_SUPPORT")]
        compare_calls=[]
        original={
            "status":"P11_CONDITIONAL_CONSEQUENCES_NOT_BUSINESS_RECOMMENDATION",
            "summary":{"physical_reference_simulations":0}}
        def fake_compare(*args):
            compare_calls.append(args)
            return copy.deepcopy(original)
        def fake_export(payload,path):
            Path(path).mkdir()
            write_json(Path(path)/"p11-conditional-summary.json",payload)
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/"allowed"
            with patch.object(arena,"execution_identity",
                              return_value=(7,"f"*40)), \
                 patch.object(arena.knowledge,"utc_now",
                              return_value=t(300)), \
                 patch.object(arena.decision,"compare",
                              side_effect=fake_compare), \
                 patch.object(arena.decision,"export",
                              side_effect=fake_export):
                run=arena.run_decision("fictional-view",out,
                                       atms_revision_events=changes)
            self.assertEqual(len(compare_calls),1)
            self.assertEqual(run["atms_admission"],control.EXECUTE)
            receipt=read_json(out/"atms-execution-gate.json")
            payload=read_json(out/"p11-conditional-summary.json")
            self.assertEqual(payload["atms_execution_gate_sha256"],
                             receipt["gate_sha256"])
            self.assertEqual(receipt["status"],control.EXECUTE)
            self.assertEqual(receipt["revision_events"],changes)

    def test_postseal_memory_replays_actual_restoration_and_stays_hypothetical(self):
        revisions=[
            change("retract","RETRACT_SUPPORT",108,target="A_SUPPORT"),
            change("restore","RESTORE_SUPPORT",109,target="A_SUPPORT")]
        receipt=self.gate(*revisions)
        policy=nominal_policy(self.pre)
        policy["atms_execution_gate_sha256"]=receipt["gate_sha256"]
        after=atms.postevaluation(self.pre,policy,sealed_native(),
                                  recorded_at=t(200),
                                  execution_receipt=receipt)
        self.assertEqual(after["predecision_snapshot_sha256"],
                         self.pre["snapshot"]["snapshot_sha256"])
        self.assertEqual(after["execution_snapshot_sha256"],
                         receipt["atms_snapshot"]["snapshot_sha256"])
        self.assertEqual(after["execution_gate_sha256"],
                         receipt["gate_sha256"])
        self.assertNotIn("S5_REAL_ECONOMIC_BENEFIT",
                         after["post_snapshot"]["labels"])
        self.assertTrue(after["prior_snapshot_remains_reproducible"])


if __name__=="__main__":
    unittest.main()
