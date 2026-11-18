"""P46 D software acceptance: single dispatch priority, paired conservation.

All input rows are invented toy payments. No new synthetic corpus, R2,
private producer views, solver, science campaign, or model calibration.
"""
from __future__ import annotations

import copy
import csv
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from arena.common import ArenaError, read_json
from arena import coffee_v2_hydra_physical_b as b
from arena import coffee_v2_hydra_causes_c as c
from arena import coffee_v2_hydra_policies_d as d
from test_coffee_v2_reference import paid,item,make_view

ROOT=Path(__file__).resolve().parents[1]
DOSSIER=ROOT/"experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json"
TOY=ROOT/"experiments/coffee_v2/C_FIXED_TOY_PAID_INPUT.json"


def dossier():
    return read_json(DOSSIER)


def fixture():
    return read_json(TOY)


def compare_toy(x=None,conf=None):
    x=x or fixture()
    return d.compare(x["positions"],x["lines"],conf or dossier(),
                     x["horizon_min"])


class DPolicies(unittest.TestCase):
    def test_astra_manual_workflow_uses_custodian_environment_but_not_in_compute(self):
        # No R2 call or secrets needed: static YAML contract matches P39.
        manual=(ROOT/".github/workflows/coffee-hydra-p46-d-manual.yml"
                ).read_text(encoding="utf-8")
        precedent=(ROOT/".github/workflows/coffee-hydra-p39.yml"
                   ).read_text(encoding="utf-8")
        self.assertIn("    environment: arena-custodian\n",manual)
        self.assertIn("    environment: arena-custodian\n",precedent)
        self.assertIn("  manual-eight-policy-comparisons:\n"
                      "    runs-on: ubuntu-24.04\n"
                      "    environment: arena-custodian\n",manual)
        fetch=manual.split("      - name: Fetch only existing private "
                           "CONSTRUCTION views from pinned source run\n")[1]
        fetch,compute=fetch.split(
            "      - name: Compare 2 verified construction loads x "
            "4 policies without R2 credentials\n",1)
        compute=compute.split(
            "      - name: Publish only aggregate Q25/Q75 policy artifact",1)[0]
        for key in ("CT03_R2_ACCESS_KEY_ID",
                    "CT03_R2_SECRET_ACCESS_KEY"):
            self.assertIn(key,fetch)
            self.assertNotIn(key,compute)
        self.assertIn("--mode construction",compute)
        self.assertNotIn("s3api",compute)

    def test_astra_one_paid_order_three_drinks_one_delayed_preparation(self):
        # Astra's specific counterexample: operator rows must not each
        # repeat the ONE globally late preparation.
        x={"positions":[paid("triple",drinks=3)],
           "lines":[item("triple",quantity=3)],
           "horizon_min":10}
        result=compare_toy(x)
        arm=next(a for a in result["policies"] if
                 a["policy"]=="PRIORITIZE_LOAD_READY_WITH_FREE_GROUP")
        self.assertEqual(arm["paid_orders"],1)
        self.assertEqual(arm["synthetic_beverages"],3)
        prep=arm["start_shift_by_stage"]["prepare"]
        self.assertEqual(prep["later_tasks"],1)
        rows=d._global_stage_shift_rows("SOFTWARE_TOY_FIXED",arm)
        preparation=[r for r in rows if r["stage"]=="prepare"]
        self.assertEqual(len(preparation),1)
        self.assertEqual(preparation[0]["later_task_starts"],1)
        self.assertEqual(sum(r["later_task_starts"] for r in
                             preparation),1)
        manual=sum(work["stage_counts"]["prepare"] for work in
                   arm["work_assigned_by_actor"].values())
        self.assertEqual(manual,3)
        self.assertEqual(sum(
            work["stage_busy_manual_min"]["prepare"] for work in
            arm["work_assigned_by_actor"].values()),
            round(3*dossier()["durations_min"][
                "prepare_off_group_min"]["value"],9))

    def test_astra_q25_q75_make_view_adaptor_exports_exact_eight_aggregates(self):
        with TemporaryDirectory() as tmp:
            view,_=make_view(tmp)
            comparison=d.compare_existing_construction_q25_q75(
                view,dossier(),dispatch_authorized=True)
            self.assertEqual(comparison["schema"],d.CASE_SET_SCHEMA)
            self.assertEqual(comparison["scenario_count"],8)
            self.assertEqual([r["load_label"] for r in comparison["results"]],
                             list(d.ALLOWED_CONSTRUCTION))
            target=Path(tmp)/"eight-public"
            aggregate=d.export(comparison,target)
            self.assertEqual(aggregate["scenario_count"],8)
            self.assertEqual(len(aggregate["paired_interpretation"]),4)
            self.assertEqual(aggregate["execution_and_consumption"][
                "status"],"LOCAL_FIXTURE_NOT_GITHUB_RUN")
            self.assertIsNone(aggregate["execution_and_consumption"][
                "github_run_id"])
            self.assertEqual(aggregate["source_view_run_id"],None)
            self.assertEqual({p.name for p in target.iterdir()},{
                "D_Q25_Q75_AGGREGATE.json","D_Q25_Q75_PAIRED.csv",
                "D_Q25_Q75_OPERATOR_STAGE.csv",
                "D_Q25_Q75_STAGE_SHIFTS.csv",
                "D_Q25_Q75_DECISION.md"})
            with (target/"D_Q25_Q75_PAIRED.csv").open(
                    encoding="utf-8",newline="") as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),8)
            with (target/"D_Q25_Q75_OPERATOR_STAGE.csv").open(
                    encoding="utf-8",newline="") as stream:
                by_stage=list(csv.DictReader(stream))
            self.assertEqual(len(by_stage),8*2*6)
            self.assertTrue(all(item["stage"] and
                                item["busy_manual_min"] for item in by_stage))
            self.assertTrue(all("earlier_task_starts" not in item and
                                "later_task_starts" not in item
                                for item in by_stage))
            with (target/"D_Q25_Q75_STAGE_SHIFTS.csv").open(
                    encoding="utf-8",newline="") as stream:
                shifted=list(csv.DictReader(stream))
            self.assertEqual(len(shifted),8*len(b.STAGES))
            for load in aggregate["results"]:
                self.assertEqual(load["paid_orders"],
                                 load["arms"][0]["paid_orders"])
                self.assertEqual(load["synthetic_beverages"],
                                 load["arms"][0]["synthetic_beverages"])
                self.assertGreater(load["paid_orders"],0)
                self.assertGreater(load["synthetic_beverages"],0)
                for arm in load["arms"]:
                    self.assertEqual(arm["paid_orders"],load["paid_orders"])
                    self.assertEqual(arm["synthetic_beverages"],
                                     load["synthetic_beverages"])
                    stage_rows=[x for x in shifted
                                if x["load_label"]==load["load_label"] and
                                x["policy"]==arm["policy"]]
                    self.assertEqual(len(stage_rows),len(b.STAGES))
                    self.assertEqual(sum(int(x["earlier_task_starts"])
                                         for x in stage_rows),
                                     arm["task_changes_earlier"])
                    self.assertEqual(sum(int(x["later_task_starts"])
                                         for x in stage_rows),
                                     arm["task_changes_later"])
            for row in rows:
                self.assertGreater(int(row["paid_orders"]),0)
                self.assertGreater(int(row["synthetic_beverages"]),0)
            public_json=(target/"D_Q25_Q75_AGGREGATE.json").read_text()
            for forbidden in (
                    "per_order_pseudonymous","override_events_pseudonymous",
                    "task_start_or_assignment_changes",
                    '"order_id"','"pos_event_id"',"producer-pos-observations"):
                self.assertNotIn(forbidden,public_json)
            self.assertIn("Q25",target.joinpath(
                "D_Q25_Q75_DECISION.md").read_text())
            self.assertIn("Q75",target.joinpath(
                "D_Q25_Q75_DECISION.md").read_text())
            with self.assertRaisesRegex(ArenaError,"OUTPUT_ALREADY_EXISTS"):
                d.export(comparison,target)

    def test_astra_manual_cli_selection_to_export_and_run_receipt_offline(self):
        # Exercise the *manual construction CLI* with P11-validated fake
        # views, using simulated Actions metadata; NEVER connect to R2.
        with TemporaryDirectory() as tmp:
            view,_=make_view(tmp)
            out=Path(tmp)/"manual-eight"
            receipt=Path(tmp)/"fake-source-receipt.json"
            sha="a"*40
            receipt.write_text(json.dumps({
                "status":"EXISTING_CONSTRUCTION_VIEWS_VERIFIED_NO_NEW_CORPUS",
                "read_only_source_run_id":d.SOURCE_RUN_ID,
                "github_run_id":777333,
                "github_commit_sha":sha,
                "R2_read_attempts":8,
                "R2_views_successfully_retrieved":8,
                "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
            }))
            env={
                "GITHUB_REPOSITORY":"yudocyudoc/igc-modular",
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_RUN_ID":"777333",
                "GITHUB_SHA":sha,
                "GITHUB_EVENT_NAME":"workflow_dispatch",
                "GITHUB_WORKFLOW_REF":
                    "yudocyudoc/igc-modular/.github/workflows/"
                    "coffee-hydra-p46-d-manual.yml@refs/heads/main",
            }
            command=[
                "--mode","construction",
                "--source-run-id",str(d.SOURCE_RUN_ID),
                "--authorize-eight-scenarios",
                "--source-receipt",str(receipt),
                "--construction-views",str(view),
                "--dossier",str(DOSSIER),
                "--out",str(out),
            ]
            # Keep simulated GitHub identity out of actual CI logs.
            captured=io.StringIO()
            with patch.dict("os.environ",env,clear=False):
                with redirect_stdout(captured):
                    d.main(command)
            self.assertIn("GITHUB_RUN_ID 777333",captured.getvalue())
            public=read_json(out/"D_Q25_Q75_AGGREGATE.json")
            self.assertEqual(public["scenario_count"],8)
            self.assertEqual(public["execution_and_consumption"][
                "github_run_id"],777333)
            self.assertEqual(public["execution_and_consumption"][
                "github_commit_sha"],sha)
            self.assertEqual(public["execution_and_consumption"][
                "source_view_run_id"],d.SOURCE_RUN_ID)
            self.assertEqual(public["execution_and_consumption"][
                "R2_billing_cost"],"UNKNOWN_NO_PROVIDER_RECEIPT")
            self.assertEqual(len(list(csv.DictReader(
                (out/"D_Q25_Q75_PAIRED.csv").open(
                    encoding="utf-8",newline="")))),8)
            with patch.dict("os.environ",dict(env,GITHUB_REF=
                                "refs/heads/feat/unsafe"),clear=False):
                with self.assertRaisesRegex(ArenaError,
                                           "MAIN_FIRST_ATTEMPT_REQUIRED"):
                    d.main([*command[:-2],"--out",str(
                        Path(tmp)/"blocked")])

    def test_astra_construction_label_requires_p11_verified_selection(self):
        x=fixture()
        with self.assertRaisesRegex(ArenaError,
                "CONSTRUCTION_REQUIRES_VERIFIED_SELECTION"):
            d.compare(x["positions"],x["lines"],dossier(),
                      x["horizon_min"],
                      source_label="CONSTRUCTION_SYNTHETIC_Q25",
                      load_label="LOWER_PAID_INPUT_Q25")
        result,trace,_=b._engine(
            x["positions"],x["lines"],dossier(),x["horizon_min"])
        with self.assertRaisesRegex(ArenaError,
                "CONSTRUCTION_REQUIRES_VERIFIED_ADAPTER"):
            c.diagnose_trace(
                result,trace,dossier(),
                fixture_label="CONSTRUCTION_SYNTHETIC_Q25")
        self.assertEqual(compare_toy()["source"],
                         "SOFTWARE_TOY_ONLY_NOT_REAL_CAFE")

    def test_astra_c_diagnostic_policy_must_match_executed_engine_trace(self):
        x=fixture()
        policy="PRIORITIZE_LOAD_READY_WITH_FREE_GROUP"
        result,trace,_=b._engine(
            x["positions"],x["lines"],dossier(),x["horizon_min"],
            dispatch_policy=policy)
        self.assertTrue(any(v["event"]=="dispatch_policy_identity"
                            for v in trace))
        with self.assertRaisesRegex(ArenaError,
                "DIAGNOSIS_POLICY_NOT_EXECUTED_ENGINE_POLICY"):
            c.diagnose_trace(
                result,trace,dossier(),fixture_label="SOFTWARE_TOY_D_FIXED",
                dispatch_policy="PRIORITIZE_MILK_READY")
        with self.assertRaisesRegex(ArenaError,
                "DIAGNOSIS_POLICY_NOT_EXECUTED_ENGINE_POLICY"):
            c.diagnose_trace(
                result,trace,dossier(),fixture_label="SOFTWARE_TOY_D_FIXED",
                dispatch_policy="FCFS_READY_ASSUMED")
        accepted=c.diagnose_trace(
            result,trace,dossier(),fixture_label="SOFTWARE_TOY_D_FIXED",
            dispatch_policy=policy)
        self.assertEqual(accepted["dispatch_policy"],policy)
        self.assertEqual(accepted["dispatch_policy_identity_source"],
                         "ENGINE_TRACE_VARIANT_IDENTITY")

    def test_astra_cannot_cross_result_and_trace_of_two_priorities(self):
        x=fixture()
        params=(x["positions"],x["lines"],dossier(),x["horizon_min"])
        result_load,trace_load,_=b._engine(
            *params,dispatch_policy="PRIORITIZE_LOAD_READY_WITH_FREE_GROUP")
        result_milk,trace_milk,_=b._engine(
            *params,dispatch_policy="PRIORITIZE_MILK_READY")
        with self.assertRaisesRegex(
                ArenaError,"ENGINE_RESULT_TRACE_POLICY_IDENTITY_MISMATCH"):
            c.diagnose_trace(result_load,trace_milk,dossier(),
                             fixture_label="SOFTWARE_TOY_D_FIXED")
        with self.assertRaisesRegex(
                ArenaError,"ENGINE_RESULT_TRACE_POLICY_IDENTITY_MISMATCH"):
            c.diagnose_trace(result_milk,trace_load,dossier(),
                             fixture_label="SOFTWARE_TOY_D_FIXED")
        self.assertEqual(result_load["executed_dispatch_policy"],
                         "PRIORITIZE_LOAD_READY_WITH_FREE_GROUP")
        self.assertEqual(result_milk["executed_dispatch_policy"],
                         "PRIORITIZE_MILK_READY")

    def test_astra_no_intervention_variant_still_bound_to_actual_policy(self):
        x={"positions":[paid("solo")],
           "lines":[item("solo")],"horizon_min":10}
        result,trace,_=b._engine(
            x["positions"],x["lines"],dossier(),x["horizon_min"],
            dispatch_policy="PRIORITIZE_MILK_READY")
        self.assertFalse(any(r["event"]=="dispatch_override" for r in trace))
        self.assertEqual(c.diagnose_trace(
            result,trace,dossier(),fixture_label="SOFTWARE_TOY_D_FIXED")[
                "dispatch_policy"],"PRIORITIZE_MILK_READY")
        with self.assertRaisesRegex(ArenaError,
                "DIAGNOSIS_POLICY_NOT_EXECUTED_ENGINE_POLICY"):
            c.diagnose_trace(
                result,trace,dossier(),fixture_label="SOFTWARE_TOY_D_FIXED",
                dispatch_policy="PRIORITIZE_HANDOFF_READY")

    def test_astra_direction_classifies_regressions_losses_and_costly_gains(self):
        report=compare_toy()
        load=next(p for p in report["policies"] if p["policy"]==
                  "PRIORITIZE_LOAD_READY_WITH_FREE_GROUP")
        self.assertEqual(load["classification"],
                         "MODEL_P90_WORSE_NO_ORDER_ADVANCED")
        self.assertEqual(load["orders_handoff_earlier"],0)
        self.assertGreater(load["orders_handoff_later"],0)
        self.assertIn("worsens",load["decision_note"])
        milk=self._competition_at_group_release("con_leche")
        result=compare_toy(milk)
        milk_arm=next(p for p in result["policies"] if
                      p["policy"]=="PRIORITIZE_MILK_READY")
        self.assertEqual(milk_arm["classification"],
                         "MODEL_P90_BETTER_WITH_LATE_ORDERS")
        self.assertGreater(milk_arm["orders_handoff_earlier"],0)
        self.assertGreater(milk_arm["orders_handoff_later"],0)
        self.assertIn("later",milk_arm["decision_note"])

    def test_astra_operator_stage_minutes_and_start_shift_sums(self):
        report=compare_toy()
        for arm in report["policies"]:
            for actor,work in arm["work_assigned_by_actor"].items():
                self.assertAlmostEqual(
                    work["busy_manual_minutes"],
                    sum(work["stage_busy_manual_min"].values()))
                self.assertEqual(sum(work["stage_counts"].values()),
                                 work["completed_manual_tasks"])
                delta=arm["work_assignment_delta_from_base"][actor]
                self.assertAlmostEqual(delta["busy_manual_min_change"],
                                       sum(delta[
                                           "stage_busy_manual_min_change"].values()))
            self.assertEqual(sum(row["earlier_tasks"] for row in
                                 arm["start_shift_by_stage"].values()),
                             arm["task_changes_earlier"])
            self.assertEqual(sum(row["later_tasks"] for row in
                                 arm["start_shift_by_stage"].values()),
                             arm["task_changes_later"])
        with TemporaryDirectory() as tmp:
            output=Path(tmp)/"toy-report"
            d.export(report,output)
            md=(output/"D_PAIRED_POLICY_COMPARISON.md").read_text()
            self.assertIn("microfixture de software ficticio",md)
            self.assertIn("Minutos por operador y etapa",md)
            self.assertIn("Lectura direccional",md)

    def test_baseline_reproduces_accepted_B_exact_result_trace_and_orders(self):
        x=fixture()
        inputs=(x["positions"],x["lines"],dossier(),x["horizon_min"])
        accepted=b._engine(*inputs)
        selected=b._engine(*inputs,dispatch_policy="FCFS_READY_ASSUMED")
        self.assertEqual(accepted,selected)
        r=compare_toy()
        p=r["policies"][0]
        self.assertEqual(p["policy"],"FCFS_READY_ASSUMED")
        self.assertEqual(p["rule_changed_assignment_count"],0)
        self.assertEqual(p["task_start_or_assignment_changes"],[])
        self.assertEqual(p["orders_handoff_unchanged"],3)
        self.assertEqual(p["p90_paid_to_handoff_full_drain_min"],
                         accepted[0]["modeled_paid_to_handoff_p90_full_drain_min"])
        self.assertEqual(p["handoffs_before_source_cut"],
                         accepted[0]["modeled_handoffs_before_cut"])

    def test_four_arms_use_identical_physics_while_one_rule_changes(self):
        x=fixture()
        before=copy.deepcopy(x)
        conf=dossier()
        backup=copy.deepcopy(conf)
        r=compare_toy(x,conf)
        self.assertEqual(r["schema"],d.SCHEMA)
        self.assertEqual(tuple(x["policy"] for x in r["policies"]),
                         tuple(b.D_DISPATCH_STAGE))
        self.assertEqual(len(r["policies"]),4)
        self.assertEqual(len(r["per_order_pseudonymous"]),12)
        self.assertEqual(x,before)
        self.assertEqual(conf,backup)
        for arm in r["policies"]:
            self.assertEqual(arm["paid_orders"],3)
            self.assertEqual(arm["synthetic_beverages"],3)
            self.assertEqual(arm["handoffs_before_source_cut"]+
                             arm["orders_pending_at_source_cut"],3)
            self.assertEqual(set(arm["work_assigned_by_actor"]),
                             {"B01","B02"})
            self.assertTrue(arm["not_a_real_intervention"])
        self.assertTrue(r["same_inputs_dossier_durations_windows_and_precedence"])
        self.assertTrue(r["limits"]["no_new_staff_or_historical_S5_support_assignment"])

    def test_load_priority_intervenes_with_free_group_at_half_minute(self):
        report=compare_toy()
        row=next(x for x in report["policies"] if x["policy"]==
                 "PRIORITIZE_LOAD_READY_WITH_FREE_GROUP")
        self.assertGreaterEqual(row["rule_changed_assignment_count"],1)
        self.assertTrue(any(
            abs(e["minute"]-0.5)<1e-8 and
            e["first_runnable_under_fcfs"]["stage"]=="prepare" and
            e["selected_instead"]["stage"]=="load"
            for e in row["override_events_pseudonymous"]))
        self.assertTrue(any(x["direction"]=="LATER" for x in
                            row["task_start_or_assignment_changes"]))
        self.assertEqual(row["rule_changed_assignment_count"],
                         len(row["override_events_pseudonymous"]))
        self.assertAlmostEqual(row["p90_paid_to_handoff_full_drain_min"]-
                               report["policies"][0][
                                   "p90_paid_to_handoff_full_drain_min"],
                               row["delta_p90_min_positive_is_worse"])

    def test_policy_overrides_are_atomic_resource_feasible_and_nonpreemptive(self):
        x=fixture()
        conf=dossier()
        reference,_,_=b._engine(x["positions"],x["lines"],conf,
                               x["horizon_min"])
        for policy in d.POLICIES[1:]:
            res,trace,completed=b._engine(
                x["positions"],x["lines"],conf,x["horizon_min"],
                dispatch_policy=policy)
            self.assertEqual(res["stage_counts"],reference["stage_counts"])
            self.assertEqual(res["max_simultaneous_group_reservations"]<=3,
                             True)
            self.assertEqual(set(completed),
                             {"Ctoy0","Ctoy1","Ctoy2"})
            alloc=[x for x in trace if x["event"]=="dispatch_override"]
            self.assertTrue(all(x["selected_stage"]==
                                b.D_DISPATCH_STAGE[policy] for x in alloc))
            self.assertFalse(any(x["selected_actor"] not in
                                 {"B01","B02"} for x in alloc))
            self.assertTrue(all(x["work_displaced_is_not_cancelled"]
                                for x in alloc))
            self.assertTrue(res["group_release_follows_remove_or_optional_clean"])

    def test_no_priority_needed_reports_no_intervention_not_improvement(self):
        x={"positions":[paid("solo")],
           "lines":[item("solo")],"horizon_min":10}
        report=compare_toy(x)
        for arm in report["policies"][1:]:
            self.assertEqual(arm["rule_changed_assignment_count"],0)
            self.assertEqual(arm["classification"],"NO_RULE_INTERVENTION")
            self.assertEqual(arm["orders_handoff_earlier"],0)
            self.assertEqual(arm["orders_handoff_later"],0)
            self.assertEqual(arm["delta_p90_min_positive_is_worse"],0)

    def _competition_at_group_release(self,first_archetype):
        # Prior paid beverage reaches release at t=2.25; three fictional
        # payments at 2.24 leave older preparation waiting while B01 removes
        # a portafilter and B02 starts a new preparation. Neither a new
        # operator nor a video order association is introduced.
        arrivals=[("first",0,first_archetype),
                  ("late1",2.24,"solo_extraccion"),
                  ("late2",2.24,"solo_extraccion"),
                  ("late3",2.24,"solo_extraccion")]
        return {
            "positions":[paid(oid,time=time) for oid,time,_ in arrivals],
            "lines":[item(oid,typ,time=time) for oid,time,typ in arrivals],
            "horizon_min":10,
        }

    def test_milk_priority_actually_displaces_earlier_runnable_preparation(self):
        x=self._competition_at_group_release("con_leche")
        report=compare_toy(x)
        arm=next(a for a in report["policies"] if
                 a["policy"]=="PRIORITIZE_MILK_READY")
        self.assertGreater(arm["rule_changed_assignment_count"],0)
        self.assertTrue(any(
            event["first_runnable_under_fcfs"]["stage"]=="prepare" and
            event["selected_instead"]["stage"]=="milk"
            for event in arm["override_events_pseudonymous"]))
        self.assertTrue(any(task["stage"]=="prepare" and
                            task["direction"]=="LATER" for task in
                            arm["task_start_or_assignment_changes"]))
        self.assertTrue(all(event["selected_actor"] in ("B01","B02") for
                            event in arm["override_events_pseudonymous"]))

    def test_handoff_priority_displaces_preparation_using_existing_barista(self):
        x=self._competition_at_group_release("solo_extraccion")
        report=compare_toy(x)
        arm=next(a for a in report["policies"] if
                 a["policy"]=="PRIORITIZE_HANDOFF_READY")
        self.assertGreater(arm["rule_changed_assignment_count"],0)
        self.assertTrue(any(
            event["first_runnable_under_fcfs"]["stage"]=="prepare" and
            event["selected_instead"]["stage"]=="handoff"
            for event in arm["override_events_pseudonymous"]))
        self.assertTrue(any(task["stage"]=="prepare" and
                            task["direction"]=="LATER" for task in
                            arm["task_start_or_assignment_changes"]))
        self.assertTrue(all(event["selected_actor"] in ("B01","B02") for
                            event in arm["override_events_pseudonymous"]))

    def test_milk_and_handoff_use_existing_staff_not_historical_s5_support(self):
        x=fixture()
        conf=dossier()
        for policy in ("PRIORITIZE_MILK_READY",
                       "PRIORITIZE_HANDOFF_READY"):
            result,trace,_=b._engine(
                x["positions"],x["lines"],conf,x["horizon_min"],
                dispatch_policy=policy)
            starts=[row for row in trace if row["event"]=="start" and
                    row["stage"] in ("milk","handoff")]
            self.assertTrue(starts)
            self.assertTrue(all(row["actor"] in ("B01","B02") for row in starts))
            self.assertFalse(any("existing_support" in json.dumps(row)
                                 for row in starts))
            self.assertTrue(result["operator_exclusive_across_all_manual_stages"])

    def test_per_order_tradeoffs_and_shifted_task_starts_are_visible(self):
        r=compare_toy()
        for arm in r["policies"]:
            rows=[x for x in r["per_order_pseudonymous"]
                  if x["policy"]==arm["policy"]]
            self.assertEqual(len(rows),3)
            self.assertEqual(arm["orders_handoff_earlier"]+
                             arm["orders_handoff_later"]+
                             arm["orders_handoff_unchanged"],3)
            for row in rows:
                self.assertAlmostEqual(
                    row["policy_handoff_min"]-row["baseline_handoff_min"],
                    row["handoff_delta_min_positive_is_later"])
                self.assertTrue(row["paid_case_label"].startswith("P"))
            self.assertTrue(all("stage" in task for task in
                                arm["task_start_or_assignment_changes"]))
            self.assertEqual(set(arm["work_assignment_delta_from_base"]),
                             {"B01","B02"})

    def test_export_reports_hashes_pseudonyms_and_no_raw_order_ids(self):
        report=compare_toy()
        serialized=json.dumps(report)
        for secret in ("Ctoy0","Ctoy1","Ctoy2","payCtoy","order_id"):
            self.assertNotIn(secret,serialized)
        self.assertNotIn("operadores.jpg",serialized)
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"d"
            d.export(report,path)
            self.assertEqual(
                set(x.name for x in path.iterdir()),{
                    "D_PAIRED_POLICY_COMPARISON.json",
                    "D_PAIRED_POLICY_COMPARISON.md",
                    "D_ORDER_OUTCOMES_PSEUDONYMOUS.csv"})
            md=(path/"D_PAIRED_POLICY_COMPARISON.md").read_text()
            self.assertIn("PRIORITIZE_LOAD_READY_WITH_FREE_GROUP",md)
            self.assertIn("P90",md)
            self.assertIn("Trabajo reasignado",md)
            with (path/"D_ORDER_OUTCOMES_PSEUDONYMOUS.csv").open(
                    encoding="utf-8",newline="") as inp:
                rows=list(csv.DictReader(inp))
            self.assertEqual(len(rows),12)
            with self.assertRaisesRegex(ArenaError,"OUTPUT_ALREADY_EXISTS"):
                d.export(report,path)

    def test_private_q25_q75_adapter_requires_authorization_before_any_reads(self):
        with self.assertRaisesRegex(ArenaError,
               "Q25_Q75_REQUIRES_EXPLICIT_EXPERIMENTAL_AUTHORIZATION"):
            d.compare_existing_construction_q25_q75(
                "/nonexistent/private/views",dossier())

    def test_q25_q75_are_only_admitted_with_matching_source_labels(self):
        x=fixture()
        for scope,load in (
                ("CONSTRUCTION_SYNTHETIC_Q25","HIGHER_PAID_INPUT_Q75"),
                ("CONSTRUCTION_SYNTHETIC_Q75","LOWER_PAID_INPUT_Q25")):
            with self.assertRaisesRegex(ArenaError,"LABEL_MISMATCH"):
                d.compare(x["positions"],x["lines"],dossier(),
                          x["horizon_min"],source_label=scope,
                          load_label=load)

    def test_no_invalid_policy_or_silent_dossier_policy_mutation(self):
        x=fixture()
        conf=dossier()
        with self.assertRaisesRegex(ArenaError,"UNDECLARED_D_DISPATCH_POLICY"):
            b._engine(x["positions"],x["lines"],conf,x["horizon_min"],
                      dispatch_policy="HIRE_SUPPORT")
        conf["dispatch_policy"]="PRIORITIZE_MILK_READY"
        with self.assertRaisesRegex(ArenaError,
               "UNDECLARED_POLICY_OR_ASSUMED_STATE"):
            d.compare(x["positions"],x["lines"],conf,x["horizon_min"])

    def test_c_diagnostic_labels_each_actual_policy_and_retains_toy_guard(self):
        x=fixture()
        conf=dossier()
        policy="PRIORITIZE_LOAD_READY_WITH_FREE_GROUP"
        result,trace,_=b._engine(
            x["positions"],x["lines"],conf,x["horizon_min"],
            dispatch_policy=policy)
        diag=c.diagnose_trace(result,trace,conf,
                              fixture_label="SOFTWARE_TOY_D_FIXED",
                              dispatch_policy=policy)
        self.assertEqual(diag["dispatch_policy"],policy)
        self.assertTrue(diag["limits"]["not_an_empirical_bottleneck_measure"])
        with self.assertRaisesRegex(ArenaError,"REQUIRES_EXPLICIT_TOY_SCOPE"):
            c.diagnose_trace(result,trace,conf,
                             fixture_label="PRODUCTION_SHOP_DATA",
                             dispatch_policy=policy)


if __name__=="__main__":
    unittest.main()
