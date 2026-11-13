"""D/M native source-equivalence and safety tests. Only offline generation.

Fixtures are engineering evidence only, not solver results or observations.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from arena.common import ArenaError, digest
from arena.coffee_domain import build_case
from arena.coffee_adapters import d, m
from arena.coffee_adapters.shared import VENDOR_ROOT, case_guard
from arena.coffee_native_dm import prepare
import test_coffee_domain

ASSUMPTIONS = test_coffee_domain.ASSUMPTIONS


# Reuse the official public fixture setup without inheriting its many test cases.
class CoffeeNativeContracts(unittest.TestCase):
    setUp = test_coffee_domain.CoffeeDomainTests.setUp

    def _case(self):
        return build_case(self.public, ASSUMPTIONS, environment={})

    def test_case_rejects_privileged_or_faked_output(self):
        c = self._case()
        self.assertIs(case_guard(c), c)
        forged = copy.deepcopy(c)
        forged["input"]["rate_orders_per_hour"] = 1 / 60
        with self.assertRaisesRegex(ArenaError, "CASE_INPUT"):
            case_guard(forged)
        forged = copy.deepcopy(c)
        forged["hypotheses"]["parameters"]["service_capacity"]["value"] = 9
        with self.assertRaisesRegex(ArenaError, "CASE_PRIORS_HASH"):
            case_guard(forged)
        forged = copy.deepcopy(c)
        forged["restrictions"]["truth_access"] = True
        with self.assertRaisesRegex(ArenaError, "CASE_HAS_PRIVATE_EVIDENCE"):
            case_guard(forged)

    def test_never_overwrite_native_dir(self):
        case = self._case()
        with self.assertRaisesRegex(ArenaError, "REFUSE_OVERWRITE"):
            d.prepare(case, self.root)

    def test_generation_d_requires_real_original_module(self):
        if not (VENDOR_ROOT / "scripts" / "arena_d_v01.py").exists():
            self.skipTest("Vendored originals only in complete GitHub checkout")
        case = self._case()
        original = d.original()
        files, receipt = d.generate(case)
        self.assertEqual(receipt["candidate_count"], 6)
        self.assertEqual(len(files), 6)
        self.assertEqual([r["structure"]["loss"] for r in receipt["candidates"]],
                         [False, True] * 3)
        for row in receipt["candidates"]:
            g = row["structure"]
            self.assertEqual(g, original.topology(len(g["stocks"]), g["loss"]))
            self.assertEqual(row["structure_hash"], original.digest(g))
            self.assertEqual(row["lint"], original.lint_structure(g))
            self.assertEqual(files[row["modelica_file"]], original.modelica(
                {"structure": g, "structure_hash": row["structure_hash"],
                 "nominal_parameters": row["nominal_parameters"]},
                receipt["input_profile"]))
            text = files[row["modelica_file"]]
            self.assertIn("der(delivered)", text)
            self.assertNotIn("if time < 2 then 1.7", text)
            self.assertEqual(row["nominal_parameters"]["capacity"], 12)
            self.assertEqual(row["nominal_parameters"]["response_time"], 0.1)
            self.assertEqual(row["nominal_parameters"]["loss_time"], 20)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "D"
            manifest = d.prepare(case, output)
            self.assertEqual(manifest["candidate_count"], 6)
            self.assertFalse(manifest["truth_access"])
            self.assertEqual(manifest["new_omc"], 0)
            for name, meta in manifest["files"].items():
                self.assertEqual("sha256:" + hashlib.sha256((output/name).read_bytes()).hexdigest(),
                                 meta["sha256"])
            self.assertNotIn("order_id", json.dumps(manifest))
            self.assertNotIn("SECRET-FUTURE-TRUTH", json.dumps(manifest))

    def test_m_compositor_registry_and_exact_external_stimulus(self):
        if not (VENDOR_ROOT / "experiments" / "e1" / "composer.py").exists():
            self.skipTest("Vendored originals only in complete GitHub checkout")
        case = self._case()
        composer, backend, swap = m.original()
        cfg, classes, _ = composer.load_registry(m.REGISTRY)
        expected = composer.enumerate_graphs(cfg, classes)
        self.assertEqual(len(expected), 6)
        files, manifest = m.generate(case)
        self.assertEqual(manifest["candidate_count"], 6)
        self.assertEqual(len(manifest["material_groups"]), 3)
        self.assertEqual(sorted(len(g["candidate_ids"]) for g in manifest["material_groups"]),
                         [2, 2, 2])
        self.assertEqual(len(manifest["candidates"]), 6)
        for row, (key, graph) in zip(manifest["candidates"], expected):
            self.assertEqual(row["canonical_graph_sha256"], "sha256:" + key)
            self.assertEqual(row["full_ast"], graph)
            self.assertEqual(row["full_ast_sha256"], digest(graph))
            model_name = row["modelica_class"].split(".")[-1]
            original = backend.render_model(model_name, graph, cfg, classes)
            changed = swap(original, case["input"]["rate_orders_per_hour"],
                           case["time"]["horizon_hours"])
            self.assertIn(changed, files["native.mo"])
            self.assertNotIn("    Modelica.Blocks.Sources.Pulse pulse(", changed)
            self.assertNotIn("der(", changed)
            self.assertEqual(row["physical_counter"], "deliveredTotal")
            self.assertNotEqual(row["informational_signal_not_counter"], "deliveredTotal")
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"M"
            result=m.prepare(case,output)
            self.assertEqual(result["new_omc"],0)
            self.assertEqual(result["registry_sha256"],
                             "sha256:"+hashlib.sha256(m.REGISTRY.read_bytes()).hexdigest())
            self.assertEqual(result["model_validation"],
                             "GENERATED_NOT_COMPILED_OR_SIMULATED")

    def test_m_does_not_silently_relax_six_minute_catalog_limit(self):
        if not (VENDOR_ROOT / "experiments" / "e1" / "composer.py").exists():
            self.skipTest("Vendored originals only in complete GitHub checkout")
        case=self._case()
        case["hypotheses"]["parameters"]["response_time"]["value"] = 0.05
        case["hypotheses"]["parameters"]["response_time"]["admissible_range"] = [0.05, 5]
        case["hypotheses_sha256"] = digest(case["hypotheses"])
        with self.assertRaisesRegex(ArenaError, "M_PUBLIC_PRIOR_DIFFERS|M_MIN_RESPONSE"):
            m.generate(case)

    def test_prepare_cannot_access_custody_secrets(self):
        with self.assertRaisesRegex(ArenaError, "PRODUCER_HAS_PRIVATE_CREDENTIAL"):
            build_case(self.public, ASSUMPTIONS,
                       environment={"CT03_R2_ACCESS_KEY_ID": "forbidden"})

    def test_full_prepare_public_only_is_not_scientific_lock(self):
        if not (VENDOR_ROOT / "scripts" / "arena_d_v01.py").exists():
            self.skipTest("Vendored originals only in complete GitHub checkout")
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"native"
            report=prepare(self.public,ASSUMPTIONS,out,verify_original=False,environment={})
            self.assertEqual(report["arms"],{"D":6,"M":6})
            self.assertFalse(report["scientific_lock_created"])
            self.assertFalse(report["truth_access"])
            self.assertEqual(report["new_omc"],0)
            self.assertEqual(report["provider_posts"],0)
            self.assertEqual(len(list((out/"D").glob("*.mo"))),6)
            self.assertEqual(len(list((out/"M").glob("*.mo"))),1)
            self.assertFalse((out/"truth").exists())
            case=json.loads((out/"public-case.json").read_text())
            self.assertEqual(case["input"]["public_paid_order_count_before_cut"],1)
            self.assertEqual(case["input"]["rate_orders_per_hour"],1)


if __name__ == "__main__":
    unittest.main()
