"""P3 producer read-boundary, immutable readiness lock and reserved evaluator gates."""
import hashlib
import io
import zipfile
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, digest, read_json, write_json
from arena.coffee_custody import admit, stage_source, producer_boundary
from arena.coffee_lab import (ARMS, probe, freeze, inspect_lock_files,
                              verify_archived_lock, validate_submission)
from arena.coffee_score import (reserved_measurements, score_prediction,
                                guarded_reserved_score, PREDICTION_CUTS)
from arena.coffee_peak import _load_package
from test_coffee_peak import make_zip
from test_coffee_custody import FakeR2


class CoffeeLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        package = self.root / "source.zip"
        sha = make_zip(package)
        self.cfg = {
            "id": "test", "protocol": "coffee_peak_capacity_v1", "backend": "fixture",
            "budget": {"omc": 0, "provider_posts": 0, "workflow": 0},
            "source": {"path": str(package), "sha256": sha},
            "selection": {"scenario_id": "case-a", "replication": 1, "day_of_week": 1},
            "construction_end_min": 60.0, "window_end_min": 103.237,
        }
        self.storage = FakeR2()
        stage_source(self.cfg, self.storage)
        self.sha = "a" * 40
        admit(self.cfg, self.storage, self.root / "custody",
              run_id="123", frozen_sha=self.sha)
        self.public = self.root / "custody" / "producer-public"
        self.submissions = self.root / "submissions"
        self.submissions.mkdir()
        self.origin = lambda: {"unchanged": True, "files": 147,
                               "igc_commit": "source", "buffalo_commit": "source"}

    def _probe_all(self):
        for arm in ARMS:
            probe(self.public, arm, self.submissions / f"submission-{arm}.json",
                  environment={}, source_verifier=self.origin)

    def _freeze(self):
        self._probe_all()
        return freeze(self.public, self.submissions, self.root / "lock", environment={})

    def _archive(self, folder=None):
        """Offline stand-in for GET /actions/artifacts/{id}/zip (exact bytes)."""
        folder = Path(folder) if folder is not None else self.root / "lock"
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("lock.json", "lock-sha256.txt"):
                zf.writestr(name, (folder / name).read_bytes())
        return payload.getvalue()

    def _fetch(self, repo, artifact_id):
        self.assertEqual((repo, artifact_id), ("yudocyudoc/igc-modular", 456))
        return self._archive()

    def _api(self, path):
        if path.endswith("/actions/runs/123"):
            return {"id": 123, "head_sha": self.sha, "head_branch": "main",
                    "event": "workflow_dispatch", "run_attempt": 1,
                    "path": ".github/workflows/coffee-peak-custody.yml"}
        if path.endswith("/actions/artifacts/456"):
            return {"id": 456, "name": "coffee-lock-123", "expired": False,
                    "workflow_run": {"id": 123}, "size_in_bytes": 3000}
        return {}

    def test_three_original_arms_have_no_coffee_model_or_prediction(self):
        self._probe_all()
        for arm in ARMS:
            row=read_json(self.submissions/f"submission-{arm}.json")
            self.assertEqual(row["arm"],arm)
            self.assertEqual(row["status"],"NO_NATIVE")
            self.assertFalse(row["coffee_domain_adapter_validated"])
            self.assertIsNone(row["predictions"])
            self.assertEqual(set(row["representability"].values()), {"no_demostrado"})
            self.assertNotIn("SECRET",json.dumps(row))
        self.assertEqual({p.name for p in self.public.iterdir()},
                         {"producer-public-b0.json", "release.json"})

    def test_rejects_misrepresented_prediction_and_leaky_credential(self):
        self._probe_all()
        sub=read_json(self.submissions / "submission-D.json")
        sub["status"] = "PREDICTED"
        sub["predictions"]={"80.0": {"paid_sales_cumulative": 15}}
        write_json(self.submissions/"submission-D.json",sub)
        with self.assertRaisesRegex(ArenaError,"PREDICTION_NOT_AUTHORIZED"):
            freeze(self.public,self.submissions,self.root/"bad-lock",environment={})
        with self.assertRaisesRegex(ArenaError,"PRODUCER_HAS_PRIVATE_CREDENTIAL"):
            probe(self.public,"D",self.root/"denied.json",
                  environment={"AWS_SECRET_ACCESS_KEY":"dummy"},source_verifier=self.origin)

    def test_lock_complete_and_readiness_cannot_open_truth(self):
        lock=self._freeze()
        self.assertEqual(lock["mode"],"READINESS_ONLY")
        self.assertFalse(lock["truth_opened"])
        self.assertEqual(lock,inspect_lock_files(self.root/"lock"))
        with self.assertRaisesRegex(ArenaError, "SCIENTIFIC_LOCK_MISSING"):
            from arena.coffee_custody import require_real_lock_before_reveal
            require_real_lock_before_reveal(lock,{})
        verified=verify_archived_lock(self.root/"lock",artifact_id=456,
                    run_id="123",frozen_sha=self.sha,api_get=self._api,archive_fetch=self._fetch,environment={})
        self.assertEqual(verified["status"],"READINESS_ARCHIVE_VERIFIED_NO_REVEAL")
        self.assertFalse(verified["scientific_lock"])
        self.assertEqual(verified["lock_sha256"],digest(lock))

    def test_rejects_lock_tamper_and_incomplete_arm_set(self):
        self._freeze()
        p=self.root/"lock"/"lock.json"
        p.write_bytes(p.read_bytes()+b" ")
        with self.assertRaisesRegex(ArenaError,"LOCK_BYTES_MISMATCH"):
            inspect_lock_files(self.root/"lock")
        p.write_bytes(p.read_bytes()[:-1]); self.assertTrue(p.exists())
        # Remove one arm after regenerating a properly checksummed file.
        obj=read_json(p);obj["arms"].pop("M")
        write_json(p,obj)
        (self.root/"lock"/"lock-sha256.txt").write_text(
            "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()+"\n")
        with self.assertRaisesRegex(ArenaError,"LOCK_READINESS_ONLY_NOT_WELL_FORMED"):
            inspect_lock_files(self.root/"lock")

    def test_github_metadata_blocks_wrong_artifact_wrong_run_and_rerun(self):
        self._freeze()
        def wrong_artifact(path):
            v=self._api(path)
            if "artifacts" in path:return {**v, "workflow_run":{"id": 333}}
            return v
        with self.assertRaisesRegex(ArenaError,"GITHUB_ARTIFACT_NOT_IMMUTABLE"):
            verify_archived_lock(self.root/"lock", artifact_id=456, run_id="123",
                 frozen_sha=self.sha,api_get=wrong_artifact,archive_fetch=self._fetch,environment={})
        def rerun(path):
            v=self._api(path)
            if "runs" in path:return {**v,"run_attempt": 2}
            return v
        with self.assertRaisesRegex(ArenaError,"GITHUB_RUN_NOT_ORIGINAL"):
            verify_archived_lock(self.root/"lock", artifact_id=456, run_id="123",
                 frozen_sha=self.sha,api_get=rerun,archive_fetch=self._fetch,environment={})
        with self.assertRaisesRegex(ArenaError,"ARCHIVE_VERIFIER_HAS_CUSTODY_SECRETS"):
            verify_archived_lock(self.root/"lock", artifact_id=456, run_id="123",
                 frozen_sha=self.sha,api_get=self._api,archive_fetch=self._fetch,
                 environment={"CT03_R2_ACCESS_KEY_ID":"test"})

    def test_workflow_download_by_artifact_id_unpacks_into_lock_root(self):
        # v4 only flattens a download-by-ID when merge-multiple is explicit.
        wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
              / "coffee-peak-custody.yml").read_text()
        block = wf.split("  verify-lock:", 1)[1].split("      - name: Verify run SHA", 1)[0]
        self.assertIn("artifact-ids: ${{ needs.prediction-lock.outputs.artifact_id }}", block)
        self.assertIn("merge-multiple: true", block)
        self.assertIn("path: ${{ runner.temp }}/coffee-locked", block)
        # A nested artifact-name directory is rejected as intended.
        self._freeze()
        nested = self.root / "download-nested" / "coffee-lock-123"
        nested.mkdir(parents=True)
        for name in ("lock.json", "lock-sha256.txt"):
            (nested / name).write_bytes((self.root / "lock" / name).read_bytes())
        with self.assertRaisesRegex(ArenaError, "LOCK_ARTIFACT_CONTENTS_INVALID"):
            inspect_lock_files(nested.parent)
        self.assertEqual(inspect_lock_files(nested)["mode"], "READINESS_ONLY")

    def test_archive_bytes_are_tied_to_fetched_github_artifact(self):
        self._freeze()
        original_archive = self._archive()
        path = self.root / "lock" / "lock.json"
        lock = read_json(path)
        lock["public_sha256"] = "sha256:" + "b" * 64
        write_json(path, lock)
        (self.root / "lock" / "lock-sha256.txt").write_text(
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
        # A locally self-consistent JSON+checksum is NOT the GitHub archive.
        self.assertEqual(inspect_lock_files(self.root / "lock")["public_sha256"],
                         lock["public_sha256"])
        with self.assertRaisesRegex(ArenaError, "ARCHIVED_LOCK_BYTES_DIFFER"):
            verify_archived_lock(self.root / "lock", artifact_id=456, run_id="123",
                frozen_sha=self.sha,api_get=self._api,
                archive_fetch=lambda repo, artifact: original_archive,environment={})
        # A metadata-valid archive with an extra/unexpected file must fail.
        with zipfile.ZipFile(io.BytesIO(original_archive)) as zf:
            old = {n: zf.read(n) for n in zf.namelist()}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for n, data in old.items(): zf.writestr(n, data)
            zf.writestr("evil.txt", b"BAD")
        with self.assertRaisesRegex(ArenaError,"ARCHIVE_ZIP_MEMBERS_INVALID"):
            verify_archived_lock(self.root / "lock", artifact_id=456, run_id="123",
                frozen_sha=self.sha,api_get=self._api,
                archive_fetch=lambda repo, artifact: buf.getvalue(),environment={})

    def test_lock_carries_selected_population_and_window(self):
        lock = self._freeze()
        self.assertEqual(lock["selection"], self.cfg["selection"])
        self.assertEqual(lock["window_end_min"], self.cfg["window_end_min"])
        self.assertEqual(lock["public_sha256"],
                         read_json(self.public / "release.json")["public_sha256"])

    def test_guarded_evaluator_refuses_day_swap_and_public_mismatch_pre_r2(self):
        locked = self._freeze()
        scientific = {**locked, "mode": "SCIENTIFIC"}
        archive = {"github_artifact_id":456, "verified_by_github_api":True,
                   "immutable_archive_read_before_reveal":True,
                   "producer_write_disabled":True, "lock_sha256":digest(scientific)}
        class NoReads:
            def get(self,*args,**kwargs):
                raise AssertionError("R2 was accessed before case/proof check")
        wrong_day = {**self.cfg, "selection": {**self.cfg["selection"], "day_of_week":2}}
        with self.assertRaisesRegex(ArenaError,"LOCK_CASE_IDENTITY_MISMATCH"):
            guarded_reserved_score(NoReads(), wrong_day, scientific, archive,
                archive_attestor=lambda *args:True,native_attestor=lambda *args:True,
                public_dir=self.public)
        with self.assertRaisesRegex(ArenaError,"PUBLIC_COMMITMENT_PROOF_REQUIRED"):
            guarded_reserved_score(NoReads(), self.cfg, scientific, archive,
                archive_attestor=lambda *args:True,native_attestor=lambda *args:True)
        public = read_json(self.public / "producer-public-b0.json")
        public["pos_records"][0]["amount_mxn"] = "999"
        write_json(self.public / "producer-public-b0.json", public)
        with self.assertRaisesRegex(ArenaError,"LOCK_PUBLIC_COMMITMENT_MISMATCH"):
            guarded_reserved_score(NoReads(), self.cfg, scientific, archive,
                archive_attestor=lambda *args:True,native_attestor=lambda *args:True,
                public_dir=self.public)

    def test_admission_rejects_late_cut_before_any_irreversible_r2_reservation(self):
        wrong = {**self.cfg, "construction_end_min": 90.0}
        storage = FakeR2()
        stage_source(wrong, storage)
        from arena.coffee_custody import selection_key
        with self.assertRaisesRegex(ArenaError, "CONSTRUCTION_CUT_NOT_BEFORE_P3_FORECASTS"):
            admit(wrong, storage, self.root / "late-custody",
                  run_id="125", frozen_sha=self.sha)
        self.assertNotIn(selection_key(wrong), storage.objects)

    def test_reserved_observations_cannot_start_before_construction_end(self):
        with zipfile.ZipFile(self.cfg["source"]["path"]) as zf:
            later = {**self.cfg,"construction_end_min":90.0}
            with self.assertRaisesRegex(ArenaError,"PREDICTION_CUTS_OUTSIDE_RESERVED_FUTURE"):
                reserved_measurements(zf,later)

    def test_never_reads_r2_before_real_lock_both_attestors(self):
        self._freeze()
        lock=inspect_lock_files(self.root/"lock")
        with self.assertRaisesRegex(ArenaError,"EXTERNAL_GITHUB_ARCHIVE_VERIFICATION_REQUIRED"):
            guarded_reserved_score(self.storage,self.cfg,lock,{})
        with self.assertRaisesRegex(ArenaError,"SCIENTIFIC_LOCK_MISSING"):
            guarded_reserved_score(self.storage,self.cfg,lock,{},
                  archive_attestor=lambda a,b: True,native_attestor=lambda a:True)
        with self.assertRaisesRegex(ArenaError,"SCIENTIFIC_LOCK_REQUIRED"):
            score_prediction(lock,{"metrics":{}},native_attestor=lambda l:True)

    def test_reserved_metrics_from_fixture_are_labeled_synthetic(self):
        real = Path("/mnt/data/piloto_cafeteria_documentacion_y_datos_completosACTUALIZADO.zip")
        if not real.exists():
            self.skipTest("The 17 MB synthetic truth ZIP is not included in GitHub CI")
        real_sha=hashlib.sha256(real.read_bytes()).hexdigest()
        zf,_=_load_package(real,real_sha)
        cfg={**self.cfg, "source":{"path":str(real),"sha256":real_sha},
             "selection":{"scenario_id":"demanda_bajo__dias6_7_bajo__paciencia_sensible",
                          "replication":1,"day_of_week":1}}
        with zf:
            oracle=reserved_measurements(zf,cfg)
        self.assertEqual(oracle["evidence_kind"],"SYNTHETIC_ORACLE_ONLY_NOT_REAL_CAFE")
        self.assertEqual(set(oracle["metrics"]), {str(c) for c in PREDICTION_CUTS})
        self.assertGreaterEqual(oracle["metrics"]["100.0"]["paid_sales_cumulative"],10)
        self.assertEqual(oracle["profit_mxn"],"NOT_IDENTIFIABLE_NO_FIXED_COSTS")

    def test_future_cumulative_paid_sales_must_be_monotone(self):
        lock={"schema":"arena.coffee-peak.prediction-lock/1","mode":"SCIENTIFIC",
              "arms": {a:{"status":"NO_NATIVE"} for a in ARMS}}
        lock["arms"]["D"]={"status":"PREDICTED","predictions": {
            "80.0":{"paid_sales_cumulative":12},
            "100.0":{"paid_sales_cumulative":10},
            "103.237":{"paid_sales_cumulative":14}}}
        oracle={"metrics": {t:{"paid_sales_cumulative":10} for t in
                ("80.0","100.0","103.237")}}
        with self.assertRaisesRegex(ArenaError,"PREDICTION_NON_MONOTONE"):
            score_prediction(lock,oracle,native_attestor=lambda _:True)

    def test_no_archive_secret_or_truth_in_public_future(self):
        self._freeze()
        lock_json=(self.root/"lock"/"lock.json").read_text()
        for secret in ("SECRET-FUTURE-TRUTH", "P80", "source.zip", "private/linkage"):
            self.assertNotIn(secret,lock_json)


if __name__=="__main__":unittest.main()
