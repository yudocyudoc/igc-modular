"""Coffee Buffalo public input: enforce common case and absence of future/truth."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, digest
from arena.coffee_domain import build_case
from arena.coffee_adapters.b import (make_payload, prepare, validate_payload,
                                     audit_fixture_result)
from arena.common import write_json
import test_coffee_domain


class CoffeeBuffaloContracts(unittest.TestCase):
    setUp = test_coffee_domain.CoffeeDomainTests.setUp

    def _case(self):
        return build_case(self.public, test_coffee_domain.ASSUMPTIONS, environment={})

    def test_buffalo_public_payload_is_nonleaking_and_only_one_arm(self):
        case = self._case()
        p = make_payload(case)
        self.assertEqual(p["horizon_hours"], 103.237 / 60)
        self.assertEqual(p["input_rate_orders_per_hour"], 1)
        self.assertEqual(p["public_sha256"], case["public_sha256"])
        self.assertTrue(validate_payload(p, case))
        self.assertNotIn('"representability"', json.dumps(p))
        self.assertNotIn('reportedDeliveryRate', json.dumps(p))
        self.assertNotIn('P10', json.dumps(p))
        self.assertNotIn('SECRET-FUTURE-TRUTH', json.dumps(p))
        self.assertNotIn('source.zip', json.dumps(p))
        self.assertIn("stopTime=1.72061666666667", p["prompt"])
        self.assertNotIn("stopTime=8", p["prompt"])
        self.assertEqual(p["provider_posts"], 0)
        self.assertFalse(p["truth_access"])

    def test_exposed_wrong_horizon_or_rate_fails(self):
        case = self._case()
        payload = make_payload(case)
        for name, val in (("horizon_hours", 8), ("input_rate_orders_per_hour", 99),
                          ("truth_access", True), ("mode", "LIVE")):
            changed = copy.deepcopy(payload)
            changed[name] = val
            with self.subTest(name=name):
                with self.assertRaisesRegex(ArenaError, "PUBLIC_CASE_PAYLOAD_MISMATCH"):
                    validate_payload(changed, case)

    def test_shared_assumptions_guard_rejects_nonunit_workload(self):
        case = self._case()
        p = case["hypotheses"]["parameters"]["workload_per_paid_order"]
        p["value"] = 2
        p["admissible_range"] = [1, 2]
        case["hypotheses_sha256"] = digest(case["hypotheses"])
        with self.assertRaisesRegex(ArenaError, "NONUNIT_WORKLOAD_UNSUPPORTED"):
            make_payload(case)

    def test_prepare_is_create_once(self):
        case = self._case()
        out = self.root / "buffalo-input.json"
        data = prepare(case, out)
        self.assertEqual(json.loads(out.read_text()), data)
        with self.assertRaises(FileExistsError):
            prepare(case, out)


    def test_versioned_coffee_modelica_translator_rejects_eight_hours(self):
        from arena.coffee_adapters import b_translation
        from arena.buffalo.capabilities import pulse_fixture
        original = pulse_fixture()
        original["model"]["specs"].update({
            "stopTime": 103.237 / 60.0,
            "dt": (103.237 / 60.0) / 64.0
        })
        name, modelica, info = b_translation.generate(original)
        self.assertTrue(name.startswith("BuffaloNative_"))
        self.assertIn("der(", modelica)
        self.assertEqual(info["native_simulation_specs"]["stopTime"], 103.237 / 60)
        self.assertEqual(info["solver_scope"],
                         "COFFEE_EULER_0_TO_103_237_MINUTES_DT_HORIZON_DIV_64")
        original["model"]["specs"]["stopTime"] = 8
        with self.assertRaisesRegex(b_translation.TranslationBlocked,
                                    "NATIVE_SPECS_OUTSIDE_COFFEE_V1_SCOPE"):
            b_translation.generate(original)
        original["model"]["specs"]["stopTime"] = 103.237 / 60.0
        original["model"]["variables"][0]["equation"] = "UNSUPPORTED(TIME)"
        with self.assertRaisesRegex(b_translation.TranslationBlocked,
                                    "UNSUPPORTED"):
            b_translation.generate(original)

    def test_readiness_does_not_accept_mock_native_as_scientific(self):
        case = self._case()
        payload = make_payload(case)
        folder = self.root / "fake"
        folder.mkdir()
        native = {"model": {"variables": [], "relationships": []}}
        write_json(folder/"native-engine-result.json", native)
        write_json(folder/"receipt.json", {
            "schema": "arena.coffee-peak.b-offline-receipt/1",
            "mode": "OFFLINE_FIXTURE_CONTRACT_ONLY",
            "case_sha256": payload["case_sha256"], "provider_posts": 0,
            "sdk_interceptions": 1, "native_sha256": digest(native),
            "native_file_sha256": "sha256:" + __import__("hashlib").sha256(
                (folder / "native-engine-result.json").read_bytes()).hexdigest(),
            "model_returned": True,
        })
        audit = audit_fixture_result(folder, payload)
        self.assertFalse(audit["scientific_lock_created"])
        self.assertEqual(audit["translation"],
                         "NOT_AUTHORIZED_UNTIL_COFFEE_HORIZON_ADAPTER")
        with self.assertRaisesRegex(ArenaError, "FIXTURE_RECEIPT_INVALID"):
            wrong = self.root/"wrong"
            wrong.mkdir()
            write_json(wrong/"native-engine-result.json", native)
            write_json(wrong/"receipt.json", {
                "schema": "arena.coffee-peak.b-offline-receipt/1",
                "mode": "OFFLINE_FIXTURE_CONTRACT_ONLY",
                "case_sha256": payload["case_sha256"], "provider_posts": 1,
                "sdk_interceptions": 1, "native_sha256": digest(native),
            })
            audit_fixture_result(wrong, payload)


if __name__ == "__main__":
    unittest.main()
