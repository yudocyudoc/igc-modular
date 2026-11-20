"""Q75 D/M original policy contract; only dedicated workflow opens pinned ZIPs."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena import coffee_q75_own_policy_cycle as own
from arena import coffee_q75_milk_cycle as q75
from arena.common import ArenaError, digest


class OfflineGuards(unittest.TestCase):
    def test_g1_cannot_pretend_p90_effect_is_zero(self):
        parent={"primitives":["STOCK"]}
        r=own._coverage_diagnostic("D",parent,"sha256:"+"a"*64)
        self.assertTrue(r["is_not_predicted_zero_effect"])
        self.assertEqual(r["evidence"],"G1")
        self.assertEqual(r["observations"],[])
        self.assertTrue(r["no_future_truth"] and r["own_evidence_only"])
        self.assertEqual(r["parent_hash"],digest(parent))

    def test_no_fake_Q75_authentic_status(self):
        with self.assertRaises(ArenaError):own.gate({"schema":own.SCHEMA})
        self.assertEqual(own.SCHEMA,"arena.coffee.q75-own-feedback-real-DM-no-solver/1")

    def test_own_scope_is_fixed_single_question(self):
        self.assertEqual(q75.POLICIES,("FCFS_READY_ASSUMED","PRIORITIZE_MILK_READY"))
        self.assertIn("real-DM-no-solver",own.SCHEMA)
        self.assertTrue(own.T0 < own.T1 < own.T2 < own.T3)


class ActualPinnedQ75Sources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=os.environ.get("ARENA_PUBLIC_ZIP_DIR")
        if not folder:
            raise unittest.SkipTest("dedicated workflow required: 8 original public ZIPs")
        cls.folder=Path(folder)
        cls.dossier=Path("experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json")
        cls.q75=q75.prepare(cls.folder,cls.dossier)

    def test_parent_families_are_original_and_complete(self):
        x,classes=own.parents()
        self.assertEqual({k:len(v) for k,v in x.items()},{"D":6,"M":6})
        self.assertEqual(len({digest(v) for v in x["D"]}),6)
        self.assertEqual(len({digest(v) for v in x["M"]}),6)
        self.assertIn("bounded-queue",classes)

    def test_input_keeps_w01_policy_and_no_false_invocation(self):
        common,packets=own.gate(self.q75)
        self.assertEqual(common["physical"]["resource_units_from_hydra"]["steam_wand"],1)
        self.assertIn("first executable task",common["exact_policy_selection_semantics"]["PRIORITIZE_MILK_READY"])
        self.assertEqual(set(packets),{"D","M","B"})
        self.assertTrue(all(v["producer_response"]=="NOT_EXECUTED" for v in packets.values()))

    def test_w01_loss_or_packet_tamper_is_rejected(self):
        altered=copy.deepcopy(self.q75)
        altered["Q75_public_case"]["physical"]["resource_units_from_hydra"]["steam_wand"]=2
        with self.assertRaises(ArenaError):own.gate(altered)
        altered=copy.deepcopy(self.q75)
        altered["producer_effective_inputs_NOT_SENT"]["D"]["status"]="EXECUTED"
        with self.assertRaises(ArenaError):own.gate(altered)
        altered=copy.deepcopy(self.q75)
        altered["producer_effective_inputs_NOT_SENT"]["M"]["input_sha256"]="sha256:"+"0"*64
        with self.assertRaises(ArenaError):own.gate(altered)

    def test_astra_revised_common_mix_and_cleaning_bound_to_feedback(self):
        common,packets=own.gate(self.q75)
        mix=common["aggregate_beverage_mix_from_public_Q75"]
        self.assertEqual((mix["milk_required_beverages"],
                          mix["no_milk_required_beverages"]),(33,20))
        self.assertEqual(common["aggregate_clean_tasks_completed_in_archived_Q75"],0)
        self.assertIs(common["physical"]["clean_after_every_beverage_assumed"],False)
        for arm in ("D","M","B"):
            self.assertEqual(packets[arm]["operation_known"],common)
        for mutate in (
            lambda x:x["Q75_public_case"]["aggregate_beverage_mix_from_public_Q75"]
                .__setitem__("milk_required_beverages",32),
            lambda x:x["Q75_public_case"]["physical"]
                .__setitem__("clean_after_every_beverage_assumed",True)
        ):
            altered=copy.deepcopy(self.q75)
            mutate(altered)
            with self.assertRaises(ArenaError):
                own.gate(altered)

    def test_authentic_ledger_atms_12_parent_dispositions_and_replay(self):
        with TemporaryDirectory() as d:
            result=own.execute(self.q75,Path(d)/"q75-ledger-cycle")
            self.assertEqual(result["arm_D"]["ratified"],6)
            self.assertEqual(result["arm_M"]["abstained"],6)
            self.assertEqual(result["arm_B"]["status"],
                "NOT_EXECUTED_NO_Q75_COMPATIBLE_AUTHENTIC_PARENT")
            self.assertEqual(result["budget"]["new_omc"],0)
            self.assertEqual(result["budget"]["new_cloudflare_post"],0)
            self.assertEqual(result["budget"]["new_private_R2_get"],0)
            for arm,status in (("arm_D","RATIFIED"),("arm_M","ABSTAINED")):
                rows=result[arm]["real_parent_feedback_records"]
                self.assertEqual(len(rows),6)
                self.assertEqual({x["own_method_disposition"] for x in rows},{status})
                self.assertTrue(all(x["retrievable_after_decision"] for x in rows))
                self.assertTrue(all(x["own_policy_feedback_sha256"] == x["G1_diagnostic_sha256"]
                                    for x in rows))
                self.assertTrue(all(x["G1_diagnosis"]["is_not_predicted_zero_effect"] for x in rows))
            self.assertEqual({x.name for x in (Path(d)/"q75-ledger-cycle").iterdir()}, {
                "D-q75-ledger.sqlite", "M-q75-ledger.sqlite", "Q75_DM_OWN_POLICY.json", "Q75_DM_OWN_POLICY.md"})
            self.assertIn("Buffalo no invocado",(Path(d)/"q75-ledger-cycle"/"Q75_DM_OWN_POLICY.md").read_text())
            for x in result["decision_atms"]["what_if_withdrawal"].values():
                self.assertTrue(x["business_hold_remains_supported"])
            self.assertEqual(result["incremental_decision_value"],
                "NOT_DEMONSTRATED_NOT_SCORED_ZERO_FOR_THREE_METHODS")

    def test_parent_cross_lane_swap_fails_own_feedback(self):
        parents,classes=own.parents()
        from arena import coffee_feedback
        bridge=coffee_feedback._original_bridge()
        with TemporaryDirectory() as root:
            src="sha256:"+"a"*64
            d_context=bridge.make_context(experiment="Coffee",world="Q75",
                     round_id="R0",arm="D",condition="MILK",source_hash=src)
            actual=parents["D"][0]
            target=Path(root)/"ledger.sqlite"
            bridge.record_feedback(target,d_context,parent_hash=digest(actual),
                       diagnostic=own._coverage_diagnostic("D",actual,src),
                       recorded_at=own.T0)
            with self.assertRaises(ValueError):bridge.recover_feedback(
                target,d_context,parent_hash=digest(parents["D"][1]),
                as_known_at=own.T1)
            m_context=bridge.make_context(experiment="Coffee",world="Q75",
                     round_id="R0",arm="M",condition="MILK",source_hash=src)
            with self.assertRaises(ValueError):bridge.recover_feedback(
                target,m_context,parent_hash=digest(actual),as_known_at=own.T1)


if __name__=="__main__":unittest.main()
