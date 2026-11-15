"""P06/P07/P10 narrow physical reference: toy scenes and producer-view contract.

Synthetic toy durations are NOT calibrated to the real coffee shop.
No original source ZIP or G3 is mounted by CI.
"""
from contextlib import closing
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import copy

from arena.common import ArenaError
from arena import coffee_v2_reference as reference
from arena import coffee_v2_reference_inputs as reader
from arena import coffee_v2_producer_views as views
from test_coffee_v2_producer_views import prepare, build_fixture


def dossier(policy="B0", support=1):
    values = {
        "manual_setup_min": 1,
        "espresso_auto_min": 4,
        "milk_finish_min": 1,
        "handoff_min": 1,
    }
    return {
        "schema": reference.DOSSIER,
        "frontier": reference.FRONTIER,
        "policy": policy,
        "resources": {
            name: {"units": support if name == "existing_support" else 1,
                   "status": "ASSUMED",
                   "evidence": "FICTIONAL_TEST_SCENARIO"}
            for name in reference.RESOURCES
        },
        "durations": {
            name: {"value": value, "bounds": [value*.5, value*1.5],
                   "status": "ASSUMED",
                   "evidence": "FICTIONAL_TEST_SCENARIO"}
            for name, value in values.items()
        },
        "initial_open_orders": {
            "value": 0, "status": "ASSUMED",
            "evidence": "FICTIONAL_ZERO_BACKLOG_NOT_OBSERVED"
        },
        "scope_limits": dict(reference.SCOPES),
    }


def paid(oid, time=0, drinks=1):
    return {"pos_event_id": "pay"+oid, "order_id": oid, "time_min": time,
            "kind": "sale", "beverage_count": drinks}


def item(oid, archetype="solo_extraccion", quantity=1, time=0):
    return {"line_id": "line"+oid, "pos_event_id": "pay"+oid,
            "order_id": oid, "time_min": time,
            "archetype": archetype, "quantity": quantity}


def make_view(tmp):
    src, private, _, audited = prepare(tmp)
    packet = build_fixture(src, private)
    # Extend deliberately minimal fictional source with explicit item recipes
    # so the physical reference can admit it, without touching source truth.
    for n, row in enumerate(packet["tables"]["producer-pos-observations.csv"]):
        r = list(row)
        r[9] = 1  # beverage count
        packet["tables"]["producer-pos-observations.csv"][n] = tuple(r)
    for n, row in enumerate(packet["tables"]["producer-line-items.csv"]):
        r = list(row)
        r[8] = "solo_extraccion"
        packet["tables"]["producer-line-items.csv"][n] = tuple(r)
    path = Path(tmp)/"producer-safe"
    views.export(packet, path)
    return path, audited


class PhysicalReferenceTests(TestCase):
    def test_parallel_machine_and_manual_without_resource_overbooking(self):
        positions = [paid("A"), paid("B")]
        lines = [item("A"), item("B")]
        result, intervals, finished = reference._engine(
            positions, lines, dossier(), 9)
        self.assertEqual((finished["A"], finished["B"]), (6.0, 10.0))
        self.assertTrue(any(
            stage == "manual_setup" and start == 1 and end == 2
            for stage, start, end, _ in intervals))
        self.assertTrue(any(
            stage == "espresso_auto" and start == 1 and end == 5
            for stage, start, end, _ in intervals))
        self.assertEqual(result["modeled_handoffs_during_halfopen_peak"], 1)
        self.assertEqual(result["modeled_orders_open_at_peak_cut"], 1)
        self.assertEqual(result["modeled_handoffs_after_peak_in_drain"], 1)
        self.assertEqual(result["synthetic_beverage_units"], 2)
        self.assertEqual(result["resources"]["espresso_group"][
            "max_simultaneous_occupied"], 1)
        self.assertEqual(result["resources"]["barista"][
            "max_simultaneous_occupied"], 1)
        self.assertEqual(result["resources"]["espresso_group"][
            "busy_unit_minutes_full_drain"], 8.0)
        public = reference.simulate(positions, lines, dossier(), 9)
        self.assertNotIn("payA", json.dumps(public))
        self.assertNotIn("payB", json.dumps(public))
        self.assertNotIn("order_id", json.dumps(public))
        self.assertTrue(public["no_observed_pickup_wait_or_real_utilization"])

    def test_one_order_two_drinks_handoff_after_last_unit_and_milk_resource(self):
        result, trace, completion = reference._engine(
            [paid("ONE", drinks=2)],
            [item("ONE", "con_leche", quantity=2)], dossier(), 10.5)
        self.assertEqual(result["synthetic_paid_orders"], 1)
        self.assertEqual(result["synthetic_beverage_units"], 2)
        self.assertEqual(result["stage_operation_counts"], {
            "manual_setup": 2, "espresso_auto": 2,
            "milk_finish": 2, "handoff": 1})
        self.assertEqual(result["modeled_handoffs_during_halfopen_peak"], 0)
        self.assertEqual(result["modeled_orders_open_at_peak_cut"], 1)
        self.assertGreater(completion["ONE"], 10.5)
        handoff = next(v for v in trace if v[0] == "handoff")
        self.assertTrue(all(v[2] <= handoff[1] for v in trace
                            if v[0] == "milk_finish"))
        self.assertEqual(result["resources"]["steam_wand"][
            "max_simultaneous_occupied"], 1)
        self.assertEqual(result["modeled_final_open_orders"], 0)

    def test_s5_only_reassigns_existing_handoff_worker(self):
        pos = [paid("A"), paid("B"), paid("C")]
        items = [item("A"), item("B"), item("C")]
        base = reference.simulate(pos, items, dossier(), 13)
        s5 = reference.simulate(pos, items, dossier(reference.S5), 13)
        self.assertEqual(s5["synthetic_paid_orders"],
                         base["synthetic_paid_orders"])
        self.assertEqual(s5["synthetic_beverage_units"],
                         base["synthetic_beverage_units"])
        self.assertEqual(s5["resources"]["existing_support"][
            "max_simultaneous_occupied"], 1)
        self.assertEqual(base["resources"]["existing_support"][
            "max_simultaneous_occupied"], 0)
        self.assertEqual(s5["resources"]["barista"]["units_assumed"],
                         base["resources"]["barista"]["units_assumed"])
        with self.assertRaisesRegex(ArenaError,
                                    "S5_NEEDS_EXISTING_SUPPORT"):
            reference.simulate(pos, items,
                               dossier(reference.S5, support=0), 13)

    def test_no_invented_measurement_no_wrong_units_and_mass_gates(self):
        bad = dossier()
        bad["durations"]["manual_setup_min"]["status"] = "MEASURED"
        with self.assertRaisesRegex(ArenaError,
                                    "DURATION_NOT_EXPLICIT_SCENARIO"):
            reference.simulate([paid("A")], [item("A")], bad, 20)
        bad = dossier()
        bad["durations"]["espresso_auto_min"]["bounds"] = [5, 6]
        with self.assertRaisesRegex(ArenaError, "DURATION_OUT_OF_BOUNDS"):
            reference.config_gate(bad)
        bad = dossier()
        bad["initial_open_orders"]["value"] = 2
        with self.assertRaisesRegex(ArenaError, "UNKNOWN_INITIAL_STOCK"):
            reference.config_gate(bad)
        bad = dossier()
        bad["resources"]["steam_wand"]["units"] = 0
        with self.assertRaisesRegex(ArenaError, "MILK_REQUIRES_STEAM"):
            reference.simulate([paid("A")], [item("A", "con_leche")], bad, 20)
        with self.assertRaisesRegex(ArenaError, "ORDER_TO_BEVERAGE_MASS"):
            reference.simulate([paid("A", drinks=2)], [item("A")],
                               dossier(), 20)
        with self.assertRaisesRegex(ArenaError, "ORPHAN_OR_REFUND_LINE"):
            reference.simulate([paid("A")], [item("B")], dossier(), 20)
        with self.assertRaisesRegex(ArenaError, "PAID_AFTER_PEAK_CUT"):
            reference.simulate([paid("A", time=20)],
                               [item("A", time=20)], dossier(), 20)

    def test_frozen_producer_manifest_and_partition_integrated_fixture(self):
        with TemporaryDirectory() as tmp:
            folder, audited = make_view(tmp)
            index = reader.read_rows(folder/"producer-case-index.csv",
                                     views.CSV_COLUMNS["producer-case-index.csv"])
            selected = next(row for row in index
                            if row["partition"] == "CONSTRUCTION")
            case_id = selected["case_id"]
            loaded = reader.select_case_day(folder, case_id, 1)
            self.assertEqual(loaded["partition"], "CONSTRUCTION")
            self.assertEqual(len(loaded["positions"]), 1)
            self.assertEqual(len(loaded["items"]), 1)
            result = reference.run(folder, case_id, 1, dossier())
            self.assertEqual(result["synthetic_paid_orders"], 1)
            self.assertEqual(result["synthetic_beverage_units"], 1)
            self.assertFalse(result["fitted_to_private_truth"])
            self.assertIn("real_resource_occupation",
                          result["identifiability_register"])
            out = Path(tmp)/"reference-output"
            reference.export(result, out)
            data = "\n".join(p.read_text("utf-8")
                             for p in out.iterdir() if p.is_file())
            self.assertNotIn("PRIVATE_regime_", data)
            self.assertNotIn("PRIVATE_RECORD_", data)
            self.assertNotIn("SUPER_PRIVATE_TRUTH_CANARY", data)
            self.assertNotIn("CUSTOMER", data)
            reserved_id = next(
                c["opaque_case_id"] for c in audited["cases"]
                if c["partition"] == "EVALUATION")
            with self.assertRaisesRegex(ArenaError, "CASE_NOT_AUTHORIZED"):
                reader.select_case_day(folder, reserved_id, 1)
            with self.assertRaisesRegex(ArenaError,
                                        "OUTPUT_ALREADY_EXISTS"):
                reference.export(result, out)
            # A changed observation must be detected before it is parsed.
            with (folder/"producer-pos-observations.csv").open("a") as f:
                f.write("TAMPERED_PRIVATE_TRUTH\n")
            with self.assertRaisesRegex(ArenaError, "VIEW_CHECKSUM"):
                reader.select_case_day(folder, case_id, 1)

    def test_synthetic_refunds_do_not_create_negative_deliveries(self):
        positions = [paid("A"), {
            "pos_event_id": "REFUND", "order_id": "OUTSIDE",
            "time_min": 2, "kind": "refund", "beverage_count": None}]
        result = reference.simulate(positions, [item("A")], dossier(), 20)
        self.assertEqual(result["synthetic_paid_orders"], 1)
        self.assertEqual(result["synthetic_refunds_not_negative_handoffs"], 1)
        self.assertEqual(result["stage_operation_counts"]["handoff"], 1)
        self.assertIsNone(
            reference.simulate([], [], dossier(), 20)[
                "modeled_paid_to_handoff_p90_full_drain_min"])


if __name__ == "__main__":
    import unittest
    unittest.main()
