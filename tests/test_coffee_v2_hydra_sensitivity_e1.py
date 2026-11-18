"""E1 offline tests: 30s Q75 sensitivity with *fictional* P11 producer views.

Never contacts R2, OMC, models, provider, or reads historic private views.
D historical aggregates in this suite are manufactured from make_view(), NOT
the authentic 44234407455 output. Runtime binds the real D artifact separately.
"""
from __future__ import annotations

import copy
import csv
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from arena.common import ArenaError, read_json
from arena import coffee_v2_hydra_physical_b as b
from arena import coffee_v2_hydra_policies_d as d
from arena import coffee_v2_hydra_sensitivity_e1 as e1
from test_coffee_v2_reference import make_view

ROOT=Path(__file__).resolve().parents[1]
DOSSIER=ROOT/"experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json"


def prior_toy(view,folder,dossier):
    old=d.compare_existing_construction_q25_q75(
        view,dossier,dispatch_authorized=True)
    return d.export(old,folder/"old-d-fixture")


def case_in_tmp(fn):
    with TemporaryDirectory() as temporary:
        folder=Path(temporary)
        view,_=make_view(temporary)
        original=read_json(DOSSIER)
        archive=prior_toy(view,folder,original)
        fn(folder,view,original,archive)


class E1Tests(unittest.TestCase):
    def test_exact_two_30s_engine_invocations_and_true_paired_mass_balance(self):
        def check(folder,view,old,archive):
            source_before=copy.deepcopy(old)
            old_before=copy.deepcopy(archive)
            with patch.object(b,"_engine",wraps=b._engine) as motor:
                report=e1.compare_verified_q75(
                    view,archive,old,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
                self.assertEqual(motor.call_count,2)
                self.assertEqual([x.kwargs["dispatch_policy"] for x in
                                  motor.call_args_list],
                                 [e1.BASE,e1.MILK])
                self.assertEqual([
                    x.args[2]["durations_min"]["espresso_auto_min"]["value"]
                    for x in motor.call_args_list],[0.5,0.5])
            self.assertEqual(archive,old_before)
            self.assertEqual(old,source_before)
            self.assertEqual(report["new_scenarios_executed"],2)
            self.assertEqual(report["old_scenarios_rerun"],0)
            self.assertEqual([x["auto_extraction_seconds"] for x in
                              report["historical_90s_arms"]],[90,90])
            self.assertEqual([x["auto_extraction_seconds"] for x in
                              report["new_30s_arms"]],[30,30])
            self.assertEqual(report["paid_orders"],
                             archive["results"][1]["paid_orders"])
            self.assertEqual(report["synthetic_beverages"],
                             archive["results"][1]["synthetic_beverages"])
            self.assertEqual(report["source_selection_sha256"],
                             archive["source_selection_sha256"])
            self.assertEqual(report["q75_input_digest_90s"],
                             archive["results"][1]["scenario_input_sha256"])
            self.assertNotEqual(report["q75_input_digest_90s"],
                                report["q75_input_digest_30s"])
            self.assertEqual(report["milk_vs_FCFS_at_30s"]["orders_earlier"]+
                             report["milk_vs_FCFS_at_30s"]["orders_later"]+
                             report["milk_vs_FCFS_at_30s"]["orders_unchanged"],
                             report["paid_orders"])
            self.assertEqual(report["new_30s_arms"][0][
                "handoffs_before_source_cut"]+report["new_30s_arms"][0][
                "orders_pending_at_source_cut"],report["paid_orders"])
        case_in_tmp(check)

    def test_only_extraction_parameter_changed_with_evidence_annotation(self):
        old=read_json(DOSSIER)
        original=copy.deepcopy(old)
        changed=e1.verified_30s_dossier(old)
        self.assertEqual(old,original)
        self.assertEqual(changed["durations_min"]["espresso_auto_min"]["value"],
                         0.5)
        self.assertEqual(old["durations_min"]["espresso_auto_min"]["value"],
                         1.5)
        clone=copy.deepcopy(changed)
        clone["durations_min"]["espresso_auto_min"]=copy.deepcopy(
            old["durations_min"]["espresso_auto_min"])
        self.assertEqual(clone,old)
        self.assertIn("NOT_FULL_CYCLE",changed["durations_min"][
            "espresso_auto_min"]["evidence"])
        with self.assertRaisesRegex(ArenaError,"EXPECTED_OLD_90S_DOSSIER"):
            e1.verified_30s_dossier(changed)

    def test_reject_authorization_before_private_view_read(self):
        with self.assertRaisesRegex(
                ArenaError,"REQUIRES_EXPLICIT_TWO_ARM_AUTHORIZATION"):
            e1.compare_verified_q75(
                "/nonexistent/not-read",{},read_json(DOSSIER))
        with self.assertRaisesRegex(ArenaError,
                                   "MANUAL_MAIN_FIRST_ATTEMPT_ONLY"):
            with patch.dict(os.environ,{
                "GITHUB_EVENT_NAME":"pull_request",
                "GITHUB_REF":"refs/heads/feat/unapproved",
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_WORKFLOW_REF":"non-matching"},clear=False):
                e1.main(["--mode","verify-archive",
                         "--historical","/nonexistent",
                         "--dossier",str(DOSSIER),
                         "--source-run-id",str(e1.SOURCE_RUN_ID),
                         "--authorize-two-scenarios",
                         "--out","/never-written"])
        self.assertFalse(Path("/never-written").exists())

    def test_cannot_label_fixture_as_authentic_historical_run(self):
        def check(folder,view,original,archive):
            with self.assertRaisesRegex(
                    ArenaError,"HISTORICAL_D_RUN_IDENTITY_OR_CUSTODY_MISMATCH"):
                e1.compare_verified_q75(
                    view,archive,original,dispatch_authorized=True)
            with self.assertRaisesRegex(
                    ArenaError,"FIXTURE_MUST_NOT_CLAIM_PRIVATE_SOURCE_RECEIPT"):
                e1.compare_verified_q75(
                    view,archive,original,dispatch_authorized=True,
                    allow_fixture_for_tests=True,
                    source_receipt={"read_only_source_run_id":e1.SOURCE_RUN_ID})
        case_in_tmp(check)

    def test_astra_rejects_tampered_historical_p90_even_when_metadata_claims_real_run(self):
        # The original artifact hash is pinned OUTSIDE the received JSON.
        # Fabricate valid-looking receipt metadata; no R2 is ever contacted.
        # Astra's adversarial mutation adds 0.5 min = 30 s to milk P90.
        self.assertEqual(e1.HISTORICAL_D_AGGREGATE_SHA256,
                         "sha256:197ee046eb4030371ce4049c674c701781fe7aeaeb175adc107e7b2d4b55a215")
        def check(folder,view,original,archive):
            fake=copy.deepcopy(archive)
            receipt=fake["execution_and_consumption"]
            receipt.update({
                "status":"GITHUB_MANUAL_EIGHT_ARM_DISPATCH",
                "github_run_id":e1.HISTORICAL_D_RUN,
                "github_commit_sha":e1.HISTORICAL_D_SHA,
                "source_view_run_id":e1.SOURCE_RUN_ID,
                "R2_views_successfully_retrieved":8,
            })
            fake["source_view_run_id"]=e1.SOURCE_RUN_ID
            milk=next(x for x in fake["results"][1]["arms"]
                      if x["policy"]==e1.MILK)
            baseline=next(x for x in fake["results"][1]["arms"]
                          if x["policy"]==e1.BASE)
            old_effect=60*(milk["p90_paid_to_handoff_full_drain_min"]-
                           baseline["p90_paid_to_handoff_full_drain_min"])
            milk["p90_paid_to_handoff_full_drain_min"]+=0.5
            altered_effect=60*(milk["p90_paid_to_handoff_full_drain_min"]-
                               baseline["p90_paid_to_handoff_full_drain_min"])
            self.assertAlmostEqual(altered_effect-old_effect,30.0)
            with self.assertRaisesRegex(
                    ArenaError,"HISTORICAL_AGGREGATE_SHA256_MISMATCH"):
                e1._historical_q75(fake,original)
            with self.assertRaisesRegex(
                    ArenaError,"HISTORICAL_AGGREGATE_SHA256_MISMATCH"):
                e1.compare_verified_q75(
                    view,fake,original,dispatch_authorized=True,
                    source_receipt={
                        "status":"EXISTING_CONSTRUCTION_VIEWS_VERIFIED_NO_NEW_CORPUS",
                        "read_only_source_run_id":e1.SOURCE_RUN_ID,
                        "R2_views_successfully_retrieved":8})
        case_in_tmp(check)

    def test_reject_archive_wrong_selected_case_day_and_digest(self):
        def check(folder,view,original,archive):
            corrupt=copy.deepcopy(archive)
            corrupt["results"][1]["source_provenance"][
                "selected_case_day_digest"]="sha256:wrong"
            with self.assertRaisesRegex(ArenaError,
                                       "Q75_CASE_DAY_OR_INPUT_NOT_HISTORICAL"):
                e1.compare_verified_q75(
                    view,corrupt,original,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
            corrupt=copy.deepcopy(archive)
            corrupt["source_selection_sha256"]="sha256:wrong"
            with self.assertRaisesRegex(ArenaError,
                                  "HISTORICAL_D_Q75_PROVENANCE_OR_POLICY_MISMATCH"):
                e1.compare_verified_q75(
                    view,corrupt,original,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
            corrupt=copy.deepcopy(archive)
            corrupt["results"][1]["scenario_input_sha256"]="sha256:wrong"
            with self.assertRaisesRegex(ArenaError,
                                     "NOT_SAME_Q75_INPUT_OR_ORIGINAL_PHYSICS"):
                e1.compare_verified_q75(
                    view,corrupt,original,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
        case_in_tmp(check)

    def test_reject_historical_physic_policy_identity_and_order_count_drift(self):
        def check(folder,view,original,archive):
            drift=copy.deepcopy(original)
            drift["durations_min"]["remove_min"]["value"]+=0.1
            with self.assertRaisesRegex(ArenaError,
                            "HISTORICAL_D_Q75_PROVENANCE_OR_POLICY_MISMATCH"):
                e1.compare_verified_q75(
                    view,archive,drift,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
            corrupt=copy.deepcopy(archive)
            corrupt["results"][1]["arms"][1]["policy"]="HIRE_THIRD_BARISTA"
            with self.assertRaisesRegex(ArenaError,
                            "HISTORICAL_D_Q75_PROVENANCE_OR_POLICY_MISMATCH"):
                e1.compare_verified_q75(
                    view,corrupt,original,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
            corrupt=copy.deepcopy(archive)
            corrupt["results"][1]["arms"][1]["paid_orders"]+=1
            with self.assertRaisesRegex(ArenaError,
                                         "HISTORICAL_D_LOAD_NOT_CONSERVED"):
                e1.compare_verified_q75(
                    view,corrupt,original,dispatch_authorized=True,
                    allow_fixture_for_tests=True)
        case_in_tmp(check)

    def test_four_cell_export_contains_no_private_order_row_and_consistent_units(self):
        def check(folder,view,original,archive):
            report=e1.compare_verified_q75(
                view,archive,original,dispatch_authorized=True,
                allow_fixture_for_tests=True)
            output=folder/"e1-aggregate"
            public=e1.export(report,output)
            self.assertEqual(set(p.name for p in output.iterdir()),{
                "E1_Q75_SENSITIVITY_AGGREGATE.json",
                "E1_Q75_FOUR_CELLS.csv",
                "E1_Q75_30S_STAGE_WAITS.csv",
                "E1_Q75_DECISION.md"})
            self.assertEqual(public["execution_and_consumption"]["status"],
                             "LOCAL_SOFTWARE_FIXTURE_NO_R2_OR_HISTORICAL_CUSTODY")
            self.assertIsNone(public["historical_D_run_id"])
            self.assertIsNone(public["R2_source_run_id"])
            with (output/"E1_Q75_FOUR_CELLS.csv").open(
                    newline="",encoding="utf-8") as handle:
                rows=list(csv.DictReader(handle))
            self.assertEqual(len(rows),4)
            self.assertEqual([int(x["auto_extraction_seconds"])
                              for x in rows],[90,90,30,30])
            self.assertEqual([x["policy"] for x in rows],
                             [e1.BASE,e1.MILK,e1.BASE,e1.MILK])
            self.assertEqual(
                {x["source"] for x in rows if
                 x["auto_extraction_seconds"]=="90"},
                {"SOFTWARE_FIXTURE_D_90S_INVENTED_NOT_GITHUB_RUN"})
            self.assertEqual(
                {x["source"] for x in rows if
                 x["auto_extraction_seconds"]=="30"},
                {"SOFTWARE_FIXTURE_E1_30S_INVENTED_NOT_PRIVATE_RUN"})
            markdown=(output/"E1_Q75_DECISION.md").read_text(
                encoding="utf-8")
            self.assertIn("SOFTWARE_FIXTURE_D_90S_INVENTED_NOT_GITHUB_RUN",
                          markdown)
            self.assertIn("SOFTWARE_FIXTURE_E1_30S_INVENTED_NOT_PRIVATE_RUN",
                          markdown)
            self.assertNotIn("ARCHIVED_ACCEPTED_D_RUN_44234407455_NOT_RERUN",
                             markdown)
            self.assertNotIn("ARCHIVED_ACCEPTED_D_RUN_44234407455_NOT_RERUN",
                             (output/"E1_Q75_FOUR_CELLS.csv").read_text())
            self.assertEqual(
                {x["source"] for x in public["historical_90s_arms"]},
                {"SOFTWARE_FIXTURE_D_90S_INVENTED_NOT_GITHUB_RUN"})
            self.assertEqual({int(x["paid_orders"]) for x in rows},
                             {report["paid_orders"]})
            raw=json.dumps(public)
            for private in ("per_order_pseudonymous","paid_case_label",
                            "override_events_pseudonymous",
                            '"order_id"','"pos_event_id"'):
                self.assertNotIn(private,raw)
            self.assertIn("NO calibración",(output/
                "E1_Q75_DECISION.md").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ArenaError,"OUTPUT_ALREADY_EXISTS"):
                e1.export(report,output)
        case_in_tmp(check)

    def test_delta_effect_is_difference_of_differences_not_raw_p90_change(self):
        def check(folder,view,original,archive):
            report=e1.compare_verified_q75(
                view,archive,original,dispatch_authorized=True,
                allow_fixture_for_tests=True)
            old=dict((x["policy"],x) for x in report["historical_90s_arms"])
            new=dict((x["policy"],x) for x in report["new_30s_arms"])
            before=60*(old[e1.MILK]["p90_paid_to_handoff_min"]-
                       old[e1.BASE]["p90_paid_to_handoff_min"])
            after=60*(new[e1.MILK]["p90_paid_to_handoff_min"]-
                      new[e1.BASE]["p90_paid_to_handoff_min"])
            self.assertAlmostEqual(
                report["delta_p90_milk_minus_FCFS_at_90s_seconds"],before)
            self.assertAlmostEqual(
                report["delta_p90_milk_minus_FCFS_at_30s_seconds"],after)
            self.assertAlmostEqual(
                report["difference_of_policy_effect_30s_minus_90s_seconds"],
                after-before)
        case_in_tmp(check)

    def test_manual_custody_gate_and_ci_never_touch_r2(self):
        workflow=(ROOT/".github/workflows/coffee-hydra-p47-e1-manual.yml"
                  ).read_text(encoding="utf-8")
        ci=(ROOT/".github/workflows/coffee-hydra-p47-e1.yml"
            ).read_text(encoding="utf-8")
        self.assertIn("    environment: arena-custodian",workflow)
        self.assertIn("  workflow_dispatch:",workflow)
        self.assertNotIn("  pull_request:",workflow)
        self.assertIn("github.run_attempt == 1",workflow)
        self.assertIn("authorize_two_scenarios == true",workflow)
        archive=workflow.index("Verify historical D 90s artifact identity")
        fetch=workflow.index("Custodian reads only eight existing CONSTRUCTION")
        compute=workflow.index("Execute EXACTLY two Q75 30s B scenarios")
        publish=workflow.index("Publish only E1 public aggregates")
        self.assertLess(archive,fetch)
        self.assertLess(fetch,compute)
        self.assertLess(compute,publish)
        segment=workflow[compute:publish]
        self.assertNotIn("CT03_R2_ACCESS_KEY_ID",segment)
        self.assertNotIn("CT03_R2_SECRET_ACCESS_KEY",segment)
        self.assertIn("fetch_existing_construction_views",
                      (ROOT/"arena/coffee_v2_hydra_sensitivity_e1.py"
                      ).read_text(encoding="utf-8"))
        self.assertIn("  pull_request:",ci)
        self.assertNotIn("CT03_R2_ACCESS_KEY_ID",ci)
        self.assertNotIn("workflow_dispatch:",ci)
        self.assertNotIn("fetch-private-views",ci)


if __name__=="__main__":
    unittest.main()
