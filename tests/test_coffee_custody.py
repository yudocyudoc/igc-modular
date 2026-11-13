"""No-network custody tests. R2 is a strict in-memory object store fixture."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, digest, read_json, write_json
from arena.coffee_custody import (
    PREFIX, admit, producer_boundary, require_real_lock_before_reveal,
    run_prefix, selection_key, source_key, stage_source,
)
from test_coffee_peak import make_zip


class FakeR2:
    def __init__(self, *, fail_on=None):
        self.objects = {}
        self.fail_on = fail_on

    def put_once(self, key, file):
        assert key.startswith(PREFIX)
        if self.fail_on and self.fail_on in key:
            raise ArenaError("MOCK_R2_PRIVATE_WRITE_FAILED")
        if key in self.objects:
            raise ArenaError("MOCK_R2_ALREADY_RESERVED")
        self.objects[key] = Path(file).read_bytes()

    def get(self, key, dest):
        if key not in self.objects:
            raise ArenaError("MOCK_R2_STAGE_MISSING")
        p = Path(dest)
        if p.exists():
            raise ArenaError("MOCK_R2_GET_ALREADY_EXISTS")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.objects[key])


class CoffeeCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.zip = self.root / "source.zip"
        sha = make_zip(self.zip)
        self.cfg = {
            "id": "coffee", "protocol": "coffee_peak_capacity_v1", "backend": "fixture",
            "budget": {"omc": 0, "provider_posts": 0, "workflow": 0},
            "source": {"sha256": sha, "path": str(self.zip)},
            "selection": {"scenario_id": "case-a", "replication": 1, "day_of_week": 1},
            "construction_end_min": 60.0, "window_end_min": 103.237,
        }
        self.storage = FakeR2()
        stage_source(self.cfg, self.storage)
        self.sha = "a" * 40

    def _admit(self, *, storage=None, folder="custody"):
        return admit(self.cfg, storage or self.storage, self.root / folder,
                     run_id="123", frozen_sha=self.sha)

    def test_r2_stage_and_private_linkage_not_in_public_artifact(self):
        release = self._admit()
        self.assertEqual(release["condition"], "B0")
        public_dir = self.root / "custody" / "producer-public"
        self.assertEqual({x.name for x in public_dir.iterdir()},
                         {"producer-public-b0.json", "release.json"})
        public = read_json(public_dir / "producer-public-b0.json")
        self.assertEqual(digest(public), release["public_sha256"])
        serialized = json.dumps(public)
        self.assertNotIn("P10", serialized)
        self.assertNotIn("P80", serialized)
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("order_ids", serialized)
        self.assertNotIn("private_linkage_sha256", serialized)
        self.assertNotIn("source.zip", serialized)
        self.assertEqual(len(public["pos_records"]), 1)
        private = self.root / "custody" / "private"
        original = read_json(private / "linkage.json")
        self.assertEqual(original["public_sha256"], release["public_sha256"])
        original_pos = original["pos_record_ids"][public["pos_records"][0]["pos_record_id"]]
        self.assertEqual(original_pos, "P10")
        self.assertEqual(len(original["order_ids"]), 1)
        base = run_prefix("123", self.sha)
        self.assertIn(base + "private/linkage.json", self.storage.objects)
        self.assertIn(base + "private/receipt.json", self.storage.objects)
        self.assertIn(base + "private/ready.json", self.storage.objects)
        self.assertIn(base + "public/producer-public-b0.json", self.storage.objects)
        self.assertIn(base + "public/release.json", self.storage.objects)
        self.assertIn(selection_key(self.cfg), self.storage.objects)
        self.assertTrue(all(k.startswith("coffee-peak/v1/") for k in self.storage.objects))
        self.assertTrue(all(not k.startswith("ct03/") for k in self.storage.objects))

    def test_producer_sees_only_one_public_input_and_no_credentials(self):
        self._admit()
        public_dir = self.root / "custody" / "producer-public"
        out = self.root / "boundary.json"
        receipt = producer_boundary(public_dir, out, environment={})
        self.assertEqual(receipt["arms"], {a: "NOT_EXECUTED" for a in "DBM"})
        self.assertFalse(receipt["truth_available"])
        self.assertFalse(receipt["scientific_lock_created"])
        self.assertEqual(receipt["provider_posts"], 0)
        with self.assertRaisesRegex(ArenaError, "PUBLIC_RUN_ID_MISMATCH"):
            producer_boundary(public_dir, self.root / "wrong-run.json",
                              environment={"GITHUB_RUN_ID": "555"})
        with self.assertRaisesRegex(ArenaError, "WRONG_CONFIGURED_PUBLIC_INSTANCE"):
            wrong = dict(self.cfg)
            wrong["source"] = {"sha256": "a" * 64}
            producer_boundary(public_dir, self.root / "wrong-instance.json",
                              environment={}, expected_config=wrong)
        with self.assertRaisesRegex(ArenaError, "PRODUCER_HAS_PRIVATE_CREDENTIAL"):
            producer_boundary(public_dir, self.root / "denied.json",
                              environment={"CT03_R2_ACCESS_KEY_ID": "LEAK"})
        (public_dir / "reserved.zip").write_bytes(b"secret")
        with self.assertRaisesRegex(ArenaError, "PUBLIC_ARTIFACT_CONTENTS"):
            producer_boundary(public_dir, self.root / "denied2.json", environment={})
        (public_dir / "reserved.zip").unlink()
        tampered = read_json(public_dir / "producer-public-b0.json")
        tampered["pos_records"][0]["amount_mxn"] = "0"
        write_json(public_dir / "producer-public-b0.json", tampered)
        with self.assertRaisesRegex(ArenaError, "PUBLIC_RELEASE_COMMITMENT_INVALID"):
            producer_boundary(public_dir, self.root / "denied3.json", environment={})

    def test_custody_never_repeats_the_same_selection_on_another_run(self):
        self._admit()
        with self.assertRaisesRegex(ArenaError, "ALREADY_RESERVED"):
            admit(self.cfg, self.storage, self.root / "second", run_id="124", frozen_sha=self.sha)
        self.assertFalse((self.root / "second" / "producer-public").exists())

    def test_missing_staged_zip_fails_without_public_release(self):
        storage = FakeR2()
        with self.assertRaisesRegex(ArenaError, "STAGE_MISSING"):
            self._admit(storage=storage)
        self.assertFalse((self.root / "custody" / "producer-public").exists())

    def test_private_write_failure_never_releases_public(self):
        storage = FakeR2(fail_on="private/linkage")
        stage_source(self.cfg, storage)
        with self.assertRaisesRegex(ArenaError, "PRIVATE_WRITE_FAILED"):
            self._admit(storage=storage)
        self.assertFalse((self.root / "custody" / "producer-public").exists())
        self.assertIn(selection_key(self.cfg), storage.objects)

    def test_source_is_immutable_on_second_stage(self):
        with self.assertRaisesRegex(ArenaError, "ALREADY_RESERVED"):
            stage_source(self.cfg, self.storage)

    def test_fail_closed_on_fake_or_unverified_scientific_lock(self):
        with self.assertRaisesRegex(ArenaError, "SCIENTIFIC_LOCK_MISSING"):
            require_real_lock_before_reveal({"mode": "BOUNDARY_FIXTURE"}, {})
        lock = {"schema": "arena.coffee-peak.prediction-lock/1", "mode": "SCIENTIFIC",
                "arms": {arm: {"status": "NO_NATIVE"} for arm in "DBM"}}
        archive = {"github_artifact_id": 51, "verified_by_github_api": False,
                   "immutable_archive_read_before_reveal": True,
                   "producer_write_disabled": True, "lock_sha256": digest(lock)}
        with self.assertRaisesRegex(ArenaError, "ARCHIVE_NOT_VERIFIED"):
            require_real_lock_before_reveal(lock, archive)
        archive["verified_by_github_api"] = True
        self.assertTrue(require_real_lock_before_reveal(lock, archive))

    def test_no_external_compute_can_be_requested(self):
        self.cfg["budget"]["provider_posts"] = 1
        with self.assertRaisesRegex(ArenaError, "EXTERNAL_COMPUTE_NOT_AUTHORIZED"):
            self._admit()

    def test_real_zip_b0_still_preserves_opaque_linkage(self):
        zip_path = Path("/mnt/data/piloto_cafeteria_documentacion_y_datos_completosACTUALIZADO.zip")
        if not zip_path.exists():
            self.skipTest("No real ZIP is committed to GitHub CI")
        import hashlib
        cfg = dict(self.cfg)
        cfg["source"] = {"path": str(zip_path),
                         "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()}
        cfg["selection"] = {"scenario_id": "demanda_bajo__dias6_7_bajo__paciencia_sensible",
                            "replication": 1, "day_of_week": 1}
        obj = FakeR2()
        stage_source(cfg, obj)
        release = admit(cfg, obj, self.root / "real", run_id="125", frozen_sha=self.sha)
        public = read_json(self.root / "real" / "producer-public" / "producer-public-b0.json")
        self.assertEqual((len(public["pos_records"]), len(public["pos_line_items"]),
                          len(public["video_proxy"])), (10, 13, 60))
        self.assertEqual(release["public_sha256"], digest(public))
        receipt = producer_boundary(self.root / "real" / "producer-public",
                                    self.root / "real-boundary.json", environment={})
        self.assertEqual(receipt["status"], "PUBLIC_ONLY_BOUNDARY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
