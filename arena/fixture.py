"""Executable integration fixture, explicitly not a prospective physical experiment.

Original D/M preparation, public projection, lock and scorer run unchanged.
Solver/provider outputs are labeled fixtures, not substituted scientific evidence.
"""
import copy
import csv
import hashlib
import shutil

from .common import ArenaError, digest, read_json, write_json
from .data import ingest
from .engines import Engines
from .legacy import load, verify


class FixtureBackend:
    stages = ("source", "prepare", "producer-fixtures", "lock", "evaluate")

    def __init__(self, *, engines=None):
        self.engines = engines or Engines()

    def execute(self, store, *, authorize=False):
        root, config = store.root, store.config
        store.status("RUNNING")
        for stage in self.stages:
            previous = store.stage(stage)
            if previous and previous["state"] == "COMPLETED":
                continue
            if previous:
                raise ArenaError("Interrupted fixture stage; create a fresh zero-consumption fixture run.")
            store.transition(stage, "RUNNING")
            try:
                getattr(self, "_" + stage.replace("-", "_"))(store)
                store.transition(stage, "COMPLETED")
            except Exception:
                store.transition(stage, "FAILED")
                store.status("FAILED")
                raise
        store.status("INTEGRATION_COMPLETED")
        result = {"schema": "arena.result/1", "evidence_kind": "INTEGRATION_FIXTURE",
                  "physical_experiment_executed": False, "scientific_conclusion": None,
                  "upstream": verify(), "fixture_score": read_json(root/"results/fixture-score.json"),
                  "run": store.report()}
        write_json(root/"result.json", result)
        return result

    def _source(self, store):
        verify()
        root, source = store.root, store.config["source"]
        data = ingest(source["path"], time_column=source.get("time_column", "time"),
                      value_column=source.get("value_column", "delivered"),
                      time_unit=source.get("time_unit", "hours"))
        observed = [(x.get("time"), x.get("value")) for x in data["observations"]]
        if observed != [(0, 0), (1, .3), (2, .6), (4, 1.2)]:
            raise ArenaError("This integration fixture uses its fixed public cuts; use ingest to admit other sources.")
        write_json(root/"inputs/dataset.json", data)
        shutil.copyfile(source["path"], root/"inputs/original-source.csv")
        producer = root/"producers"
        producer.mkdir()
        private = root/"fixture-private"
        protocol = load("ct03_prospective_lock")
        commitment = load("ct03_world_custody").prepare_private({
            "world_public_id": "FIXTURE_CT03_NOT_REAL", "stage_count": 2,
            "capacity": 2.1, "response_time": .8,
            "custody_nonce": "FIXTURE_NONCE_NOT_SECRET_12345",
            "protocol_sha256": digest(read_json(protocol.PROTOCOL)),
        }, private)
        with (private/"sealed_world_res.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time", "deliveredTotal"])
            writer.writerows((i/8, .3*(i/8)) for i in range(65))
        (private/"world-omc.log").write_text("INTEGRATION FIXTURE ONLY; no solver. OpenModelica v1.26.5\n", encoding="utf-8")
        load("ct03_minimal_custody").release(producer_root=producer, private_dir=private,
                public_out=producer/"public", commitment=commitment)

    def _prepare(self, store):
        root = store.root/"producers"
        self.engines.prepare("D", root/"D")
        self.engines.prepare("M", root/"M")

    def _producer_fixtures(self, store):
        root = store.root/"producers"
        public = read_json(root/"public/construction.json")
        d, m = read_json(root/"D/manifest.json"), read_json(root/"M/manifest.json")
        protocol = load("ct03_prospective_lock")
        rows, fixture_assigned = [], set()
        policies = {"D": "D-CT03-EXPLICIT-FIXED-SET/1.0", "M": "M-E1-OWN-FEEDBACK-SET/1.0",
                    "B": "UB-IAD/sd-ai::Engine.generate"}
        for (arm, ident), meta in protocol.registry(d, m).items():
            state = {"status": "NO_NATIVE" if arm == "B" else "NOT_EXECUTED",
                     "native_sha256": None, "trace_sha256": None, "receipt_sha256": None, "forecast": None}
            if arm in ("D", "M") and arm not in fixture_assigned:
                fixture_assigned.add(arm)
                forecast = [{"time": 6, "delivered": 2.0}, {"time": 8, "delivered": 2.5}]
                receipt = {"evidence_kind": "INTEGRATION_FIXTURE", "solver_executed": False,
                           "arm": arm, "candidate_id": ident, "forecast": forecast}
                write_json(root/arm/"fixture-receipt.json", receipt)
                state = {"status": "PREDICTED", "native_sha256": digest({"fixture": ident}),
                         "trace_sha256": digest(forecast), "receipt_sha256": digest(receipt), "forecast": forecast}
            rows.append({"arm": arm, "candidate_id": ident, "parent_hash": meta["parent_hash"],
                         "material_group": meta["group"], "initial": state,
                         "decision": {"status": "NOT_EXECUTED", "policy": policies[arm],
                                      "feedback_hash": None, "retrieved_item_id": None, "new_model_sha256": None},
                         "final": copy.deepcopy(state)})
        entries = {"schema": protocol.INPUT_SCHEMA, "world_public_id": public["world_public_id"],
                   "source_snapshot_hash": public["source_snapshot_hash"], "condition_id": "C0", "rows": rows}
        write_json(root/"entries.json", entries)

    def _lock(self, store):
        root = store.root/"producers"
        lock = load("ct03_prospective_lock").seal(
            read_json(root/"public/construction.json"), read_json(root/"public/world-commitment.json"),
            read_json(root/"D/manifest.json"), read_json(root/"M/manifest.json"), read_json(root/"entries.json"))
        write_json(store.root/"archive/lock.json", lock, exclusive=True)
        write_json(store.root/"archive/metadata.json", {"evidence_kind": "INTEGRATION_FIXTURE",
                   "lock_sha256": lock["lock_sha256"], "read_private_world": False}, exclusive=True)

    def _evaluate(self, store):
        root = store.root/"producers"
        lock = read_json(store.root/"archive/lock.json")
        metadata = read_json(store.root/"archive/metadata.json")
        if metadata["lock_sha256"] != lock["lock_sha256"] or metadata["read_private_world"] is not False:
            raise ArenaError("Fixture lock/archive mismatch; private fixture not opened.")
        scorer = load("ct03_minimal_score")
        ack = {"schema": scorer.FREEZE_SCHEMA, "lock_sha256": lock["lock_sha256"],
               "github_run_id": 1, "github_artifact_id": 1, "frozen_code_sha": "f"*40,
               "verified_by_custodian": "INTEGRATION_FIXTURE_NOT_GITHUB_EXECUTION",
               "archived_before_reveal": True, "producer_write_disabled": True,
               "custody_scope": "PROCEDURAL_HUMAN_NO_EXTERNAL_SIGNER"}
        scorer.evaluate(lock=lock, archive=ack, construction=read_json(root/"public/construction.json"),
                        commitment=read_json(root/"public/world-commitment.json"), producer_root=root,
                        private_dir=store.root/"fixture-private", out=store.root/"results/fixture-score.json")

