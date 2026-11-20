"""P49: authentic-source pre-dispatch tests, no privileged execution."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from arena import coffee_q75_milk_cycle as q
from arena.common import ArenaError


class TestContractOffline(unittest.TestCase):
    def test_no_new_policy_or_unearned_conclusion(self):
        state=q._decision_status()
        self.assertEqual(state["Hydra_only"],q.DECISION_BASE)
        self.assertIn("PENDING",state["Hydra_plus_new_D_M_B"])
        self.assertEqual(state["scientific_incremental_value"],"UNDETERMINED_NOT_ZERO")
        self.assertEqual(q.POLICIES,("FCFS_READY_ASSUMED","PRIORITIZE_MILK_READY"))

    def test_eff_inputs_do_not_claim_authentic_invocation(self):
        process={"case":"Q75_CONSTRUCTION_SYNTHETIC_ONLY","question":q.FIXED_QUESTION}
        scope={"D":{"method":"original"},"M":{"method":"original","registry":"coffee"},
               "B":{"old_method":"Engine.generate"}}
        b={"old_parent_compatible_with_new_Q75_policy":"NOT_DEMONSTRATED"}
        x=q._effective_packets(process,scope,b)
        self.assertEqual(set(x),{"D","M","B"})
        self.assertTrue(all(v["status"]=="PREPARED_NOT_DELIVERED_TO_PRODUCER" for v in x.values()))
        self.assertTrue(all(v["producer_response"]=="NOT_EXECUTED" for v in x.values()))
        self.assertEqual(len({v["input_sha256"] for v in x.values()}),3)
        self.assertNotIn("-3.837",json.dumps(x))

    def test_budget_separate_authorization(self):
        x={a:{"status":"PREPARED_NOT_DELIVERED_TO_PRODUCER"} for a in ("D","M","B")}
        budget=q._budget({},x)
        self.assertEqual(budget["new_cloudflare_posts_executed"],0)
        self.assertEqual(budget["new_omc_executed"],0)
        self.assertEqual(budget["new_private_R2_gets_executed"],0)
        self.assertTrue(budget["any_new_calls_require_a_new_explicit_budget_and_user_approval"])
        x["M"]["status"]="EXECUTED"
        with self.assertRaises(ArenaError):q._budget({},x)

    def test_atms_conditional_retraction_keeps_historical_q75(self):
        r=q._atms_public_hydra_proof(q.ARCHIVED_SOURCE_ZIP_SHA)
        changed=r["what_if_remove_90s"]
        self.assertEqual(changed["Q75_MILK_ADVANTAGE_APPLIES_AT_90S_ONLY"]["after"],[])
        self.assertTrue(r["historical_result_survives_after"])
        self.assertFalse(r["three_method_diag_recovered_and_consumed"])

    def test_invalid_sha_rejected(self):
        with self.assertRaises(ArenaError):q._atms_public_hydra_proof("sha256:"+"0"*65)

    def test_dossier_policy_drift_rejected(self):
        # The physical gate may not silently change the reference policy.
        fake={"schema":"arena.coffee.p44.hydra-physical-b/1",
              "enabled_group_ids":["G01","G02","G03"],"operators":{"B01":{},"B02":{}},
              "durations_min":{"espresso_auto_min":{"value":1.5}},
              "dispatch_policy":"PRIORITIZE_MILK_READY", "milk_precedence":"AFTER_GROUP_RELEASE_ASSUMED"}
        from arena.common import digest
        with self.assertRaises(ArenaError):q._check_physics(fake,{"physical_dossier_sha256":digest(fake)})


class TestPinnedRealPublicArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loc=os.environ.get("ARENA_PUBLIC_ZIP_DIR")
        if not loc:
            raise unittest.SkipTest("requires eight authentic GitHub archived ZIPs; dedicated workflow runs this suite")
        cls.root=Path(loc)
        from arena.coffee_three_arms_readback_v2 import load_sources
        cls.z=load_sources(cls.root)
        cls.dossier=Path("experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json")

    def test_q75_real_provenance_and_no_new_response(self):
        out=q.prepare(self.root,self.dossier)
        self.assertEqual(out["schema"],q.SCHEMA)
        self.assertEqual(out["frozen_reference_decision"]["milk_delta_p90_sec_positive_is_worse"],-3.837)
        self.assertEqual(out["Q75_public_case"]["paid_orders"],46)
        self.assertEqual(out["Q75_public_case"]["beverages"],53)
        self.assertFalse(out["ATMS_public_reference_what_if"]["three_method_diag_recovered_and_consumed"])
        self.assertEqual(out["original_generator_scope"]["D"]["six_structures_linted"],6)
        self.assertEqual(out["original_generator_scope"]["M"]["six_real_graphs_enumerated"],6)
        self.assertTrue(out["historical_buffalo_B0_prompt_scope"]["excluded_barista_espresso_coupling"])
        self.assertEqual(out["current_decision"]["scientific_incremental_value"],"UNDETERMINED_NOT_ZERO")

    def test_q75_tampered_effect_rejected(self):
        original=json.loads(self.z["hydra"].read("D_Q25_Q75_AGGREGATE.json"))
        altered=copy.deepcopy(original)
        row=next(x for x in altered["results"] if "Q75" in x["load_label"])
        milk=next(x for x in row["arms"] if x["policy"]=="PRIORITIZE_MILK_READY")
        milk["p90_paid_to_handoff_full_drain_min"]+=0.5
        class Fake:
            def read(self,name):return json.dumps(altered).encode()
        z={**self.z,"hydra":Fake()}
        with self.assertRaises(ArenaError):q._exact_hydra_source(z)

    def test_q75_rival_exposure_not_needed_to_freeze_reference(self):
        hydra,q75,_,delta=q._exact_hydra_source(self.z)
        decision=q._historical_baseline(q75,delta)
        self.assertEqual(decision["policy_comparator"],"FCFS_READY_ASSUMED_NOT_MEASURED_LOCAL")
        self.assertIn("RETROSPECTIVELY",decision["status"])
        self.assertEqual(decision["current_operational_choice"],q.DECISION_BASE)

    def test_historical_B0_prompt_no_coupling_verified(self):
        old=q._check_b0_prompt(self.z)
        self.assertTrue(old["excluded_barista_espresso_coupling"])
        self.assertEqual(old["old_parent_compatible_with_new_Q75_policy"],"NOT_DEMONSTRATED")
        modified=json.loads(self.z["buffalo_initial"].read("input.json"))
        modified["prompt"]=modified["prompt"].replace("shared barista/espresso coupling", "")
        class Fake:
            def read(self,name):return json.dumps(modified).encode()
        with self.assertRaises(ArenaError):q._check_b0_prompt({**self.z,"buffalo_initial":Fake()})

    def test_wrong_physics_or_operator_assumption_is_rejected(self):
        _,q75,_,_=q._exact_hydra_source(self.z)
        dossier=json.loads(self.dossier.read_text())
        self.assertEqual(q._check_physics(dossier,q75)["operator_ids"],["B01","B02"])
        changed=copy.deepcopy(dossier)
        changed["durations_min"]["espresso_auto_min"]["value"]=0.5
        with self.assertRaises(ArenaError):q._check_physics(changed,q75)

    def test_astra_one_vs_two_wands_changes_all_three_unsent_packets(self):
        # Astra negative: the historical result is NOT changed, but a
        # hypothetical physical dossier with two wands must NOT map to the
        # same inputs or hashes as the authentic one-wand Q75 case.
        from arena.common import digest
        _, q75, _, _ = q._exact_hydra_source(self.z)
        original = json.loads(self.dossier.read_text())
        expanded = copy.deepcopy(original)
        expanded["steam_wands"] = ["W01", "W02"]
        altered_q75 = copy.deepcopy(q75)
        altered_q75["physical_dossier_sha256"] = digest(expanded)
        first_physics = q._check_physics(original, q75)
        second_physics = q._check_physics(expanded, altered_q75)
        self.assertEqual(first_physics["resource_units_from_hydra"], {
            "barista":2,"prep_space":2,"espresso_group":3,
            "steam_wand":1,"pickup_pass":1})
        self.assertEqual(second_physics["resource_units_from_hydra"]["steam_wand"],2)
        self.assertEqual(first_physics["resource_ids_from_dossier"]["steam_wand"],["W01"])
        self.assertEqual(second_physics["resource_ids_from_dossier"]["steam_wand"],["W01","W02"])
        self.assertEqual(first_physics["task_stage_resource_requirements_from_hydra"]["milk"],
                         ["barista","steam_wand"])
        self.assertEqual(first_physics["policy_selection_semantics"],
                         second_physics["policy_selection_semantics"])
        a=q._common_process(q75,first_physics)
        b=q._common_process(altered_q75,second_physics)
        scope={"D":{"method":"d"},"M":{"method":"m","registry":"m"},
               "B":{"old_method":"Engine.generate"}}
        buffalo={"old_parent_compatible_with_new_Q75_policy":"NOT_DEMONSTRATED"}
        packets_a=q._effective_packets(a,scope,buffalo)
        packets_b=q._effective_packets(b,scope,buffalo)
        for arm in ("D","M","B"):
            self.assertNotEqual(packets_a[arm]["input_sha256"],
                                packets_b[arm]["input_sha256"])
            self.assertNotEqual(packets_a[arm]["operation_known"]["physical"],
                                packets_b[arm]["operation_known"]["physical"])
            self.assertEqual(packets_a[arm]["operation_known"]["physical"]
                             ["resource_units_from_hydra"]["steam_wand"],1)
            self.assertEqual(packets_b[arm]["operation_known"]["physical"]
                             ["resource_units_from_hydra"]["steam_wand"],2)
        # Changed physics is NOT a valid replacement for historical Q75.
        with self.assertRaises(ArenaError):
            q._check_physics(expanded,q75)

    def test_astra_milk_mix_and_cleaning_flag_affect_all_three_packages(self):
        from arena.common import digest
        _, q75, _, _=q._exact_hydra_source(self.z)
        dossier=json.loads(self.dossier.read_text())
        physics=q._check_physics(dossier,q75)
        shared=q._common_process(q75,physics)
        self.assertEqual(shared["aggregate_beverage_mix_from_public_Q75"]
                         ["milk_required_beverages"],33)
        self.assertEqual(shared["aggregate_beverage_mix_from_public_Q75"]
                         ["no_milk_required_beverages"],20)
        self.assertEqual(shared["aggregate_clean_tasks_completed_in_archived_Q75"],0)
        self.assertIs(physics["clean_after_every_beverage_assumed"],False)
        self.assertEqual(physics["cleaning_stage_resource_requirement_from_hydra"],
                         ["barista","espresso_group"])
        scope={"D":{"method":"d"},"M":{"method":"m","registry":"m"},
               "B":{"old_method":"Engine.generate"}}
        buffalo={"old_parent_compatible_with_new_Q75_policy":"NOT_DEMONSTRATED"}
        base=q._effective_packets(shared,scope,buffalo)
        changed_dossier=copy.deepcopy(dossier)
        changed_dossier["clean_after_every_beverage_assumed"]=True
        hypothetical_q75=copy.deepcopy(q75)
        hypothetical_q75["physical_dossier_sha256"]=digest(changed_dossier)
        hypothetical_physics=q._check_physics(changed_dossier,hypothetical_q75)
        hypothetical=q._common_process(hypothetical_q75,hypothetical_physics)
        changed=q._effective_packets(hypothetical,scope,buffalo)
        for arm in ("D","M","B"):
            self.assertNotEqual(base[arm]["input_sha256"],changed[arm]["input_sha256"])
            self.assertIs(changed[arm]["operation_known"]["physical"]
                          ["clean_after_every_beverage_assumed"],True)
            self.assertEqual(changed[arm]["operation_known"]
                             ["aggregate_clean_tasks_completed_in_archived_Q75"],0)
        # A hypothetical copy cannot silently become the real Q75 case.
        with self.assertRaises(ArenaError):
            q._check_physics(changed_dossier,q75)
        # Public counts are not allowed to drift, even if aggregate result
        # includes the same effect score.
        corrupt=copy.deepcopy(q75)
        corrupt["arms"][0]["work_assigned_by_actor"]["B01"]["stage_counts"]["milk"]+=1
        with self.assertRaises(ArenaError):
            q._common_process(corrupt,physics)

    def test_astra_busy_wand_allows_other_runnable_manual_tasks(self):
        # Real Hydra engine, software-only constructed orders, no private
        # Q75, Cloudflare, R2 or Modelica. Tests behavior not just prompt text.
        from arena import coffee_v2_hydra_physical_b as physical_b
        from test_coffee_v2_reference import paid, item
        d=json.loads(self.dossier.read_text())
        positions=[paid(str(i),time=0) for i in range(10)]
        lines=[item(str(i),"con_leche" if i<6 else "solo_extraccion")
               for i in range(10)]
        _, trace, _=physical_b._engine(
            positions, lines,d,25,dispatch_policy="PRIORITIZE_MILK_READY")
        milk_starts=[x for x in trace if
                     x["event"]=="start" and x["stage"]=="milk"]
        milk_ends={(x["job"]):x["time"] for x in trace if
                   x["event"]=="finish" and x["stage"]=="milk"}
        self.assertEqual(len(milk_starts),6)
        self.assertEqual(len(milk_ends),6)
        self.assertTrue(all("W:W01" in x["tokens"] for x in milk_starts))
        for prev,nxt in zip(milk_starts,milk_starts[1:]):
            self.assertGreaterEqual(nxt["time"],milk_ends[prev["job"]])
        self.assertTrue(any(
            x["event"]=="start" and x["stage"]!="milk" and
            x["stage"]!="extract_auto" and
            any(m["time"]<=x["time"]<milk_ends[m["job"]]
                for m in milk_starts)
            for x in trace),
            "A free barista must be able to execute another runnable "
            "manual task while W01 is occupied")

    def test_authentic_reproduction_no_hidden_data_or_calls(self):
        data=q.prepare(self.root,self.dossier)
        doc=q.render_markdown(data)
        self.assertIn("NO han recibido",doc)
        self.assertIn("0 GET R2 privados",doc)
        self.assertIn("PR de preparación",doc)
        self.assertEqual(data["current_decision"]["scientific_closure"],"NOT_ALLOWED_AT_PRE_DISPATCH_STAGE")
        self.assertTrue(all(v["producer_response"]=="NOT_EXECUTED"
                            for v in data["producer_effective_inputs_NOT_SENT"].values()))

if __name__=="__main__":unittest.main()
