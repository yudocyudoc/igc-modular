"""Coffee B0: isolated R2 admission and public-only producer boundary.

The custody job is the ONLY role allowed to read the original ZIP and private
linkage. No D/B/M execution or holdout scoring is authorized by this module.
The scientific lock/reveal gate is deliberately fail-closed until implemented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from .common import ArenaError, digest, read_json, write_json
from .coffee_peak import (
    ALLOWED_LINES, ALLOWED_POS, ALLOWED_PROFILE, _build_public, _load_package
)

PREFIX = "coffee-peak/v1/"
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
RUN = re.compile(r"[1-9][0-9]{0,19}\Z")
ARMS = ("D", "B", "M")
RESTRICTED_ENV = (
    "CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "COFFEE_R2_ACCESS_KEY_ID",
    "COFFEE_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_API_TOKEN", "GH_TOKEN",
)


def _require(ok, code):
    if not ok:
        raise ArenaError("COFFEE_CUSTODY_" + code)


def _sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def _require_pinned_config(cfg):
    _require(cfg["protocol"] == "coffee_peak_capacity_v1" and cfg["backend"] == "fixture",
             "UNSUPPORTED_PROTOCOL_OR_BACKEND")
    _require(cfg["budget"] == {"omc": 0, "provider_posts": 0, "workflow": 0},
             "EXTERNAL_COMPUTE_NOT_AUTHORIZED")
    _require(bool(SHA.fullmatch(cfg["source"]["sha256"])), "UNPINNED_SOURCE")


def source_key(package_sha):
    _require(bool(SHA.fullmatch(package_sha)), "INVALID_SOURCE_SHA")
    return PREFIX + "source/" + package_sha + ".zip"


def selection_key(cfg):
    """Stable reservation across GitHub runs, preventing multiple openings."""
    _require_pinned_config(cfg)
    fingerprint = digest({
        "source": cfg["source"]["sha256"],
        "selection": cfg["selection"],
        "construction_end_min": cfg["construction_end_min"],
        "window_end_min": cfg["window_end_min"],
    }).split(":", 1)[1]
    return PREFIX + "reservations/" + fingerprint + ".json"


def run_prefix(run_id, frozen_sha):
    run_id = str(run_id)
    _require(bool(RUN.fullmatch(run_id)) and bool(COMMIT.fullmatch(frozen_sha)),
             "INVALID_GITHUB_RUN_IDENTITY")
    return PREFIX + "runs/" + run_id + "-" + frozen_sha[:12] + "/"


class R2Storage:
    """Use CT03's proven S3 transport, not its ct03/ preflight or reservation.

    No new secrets or buckets are introduced. The same private bucket is
    namespace-separated with coffee-peak/v1/, never with ct03/.
    """
    def __init__(self):
        from .custody import R2
        self.client = R2()
        self.client.call("s3api", "head-bucket", "--bucket", self.client.bucket)

    @staticmethod
    def _key(key):
        _require(isinstance(key, str) and key.startswith(PREFIX)
                 and ".." not in key and "//" not in key and "\\" not in key,
                 "INVALID_R2_KEY")
        return key

    def put_once(self, key, path):
        self.client.call("s3api", "put-object", "--bucket", self.client.bucket,
                         "--key", self._key(key), "--body", str(Path(path)),
                         "--if-none-match", "*")

    def get(self, key, destination):
        destination = Path(destination)
        _require(not destination.exists(), "REFUSE_OVERWRITE_PRIVATE_FILE")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.call("s3api", "get-object", "--bucket", self.client.bucket,
                         "--key", self._key(key), str(destination))
        _require(destination.is_file(), "R2_GET_DID_NOT_CREATE_FILE")


def stage_source(config, storage):
    """One-time trusted source bootstrap, without a GitHub artifact containing truth."""
    _require_pinned_config(config)
    path = Path(config["source"]["path"])
    zf, _ = _load_package(path, config["source"]["sha256"])
    zf.close()
    storage.put_once(source_key(config["source"]["sha256"]), path)
    return {"schema": "arena.coffee-source-staged/1", "source_sha256": config["source"]["sha256"],
            "r2_source_key": source_key(config["source"]["sha256"]),
            "source_publicly_uploaded": False, "scientific_experiment_executed": False}


def admit(config, storage, out, *, run_id, frozen_sha):
    """Private custodian role: R2 stage -> one B0 view -> private linkage -> public release.

    Reserve BEFORE storing the linkage, and publish public files only AFTER all
    private writes have succeeded. Never expose the ZIP or private mapping in
    public GitHub artifacts. Any uncertain write is terminal, not retried.
    """
    _require_pinned_config(config)
    prefix = run_prefix(run_id, frozen_sha)
    output = Path(out)
    _require(not output.exists(), "REFUSE_REUSE_CUSTODY_DIRECTORY")
    output.mkdir(parents=True, mode=0o700)
    private = output / "private"
    private.mkdir(mode=0o700)
    package = private / "source.zip"
    storage.get(source_key(config["source"]["sha256"]), package)
    zf, _ = _load_package(package, config["source"]["sha256"])
    with zf:
        public, linkage = _build_public(zf, config, config["source"]["sha256"], include_private=True)
    public_sha = digest(public)
    _require(linkage["public_sha256"] == public_sha, "LINKAGE_PUBLIC_MISMATCH")
    private_file = private / "linkage.json"
    write_json(private_file, linkage, exclusive=True)
    linkage_sha = digest(linkage)
    receipt = {
        "schema": "arena.coffee-peak.custody-receipt/1",
        "repository": "yudocyudoc/igc-modular", "run_id": str(run_id),
        "frozen_sha": frozen_sha, "protocol": "coffee_peak_capacity_v1",
        "source_package_sha256": config["source"]["sha256"],
        "source_key": source_key(config["source"]["sha256"]),
        "selection": dict(config["selection"]),
        "construction_end_min": config["construction_end_min"],
        "public_sha256": public_sha, "private_linkage_sha256": linkage_sha,
        "model_execution": "NOT_EXECUTED", "holdout_opened": False,
    }
    receipt_file = private / "receipt.json"
    write_json(receipt_file, receipt, exclusive=True)
    # Stable across retries/runs for the same source/selection/cut, create-once.
    storage.put_once(selection_key(config), receipt_file)
    storage.put_once(prefix + "private/linkage.json", private_file)
    storage.put_once(prefix + "private/receipt.json", receipt_file)
    # Ready marker confirms all private objects are durably stored.
    ready = private / "ready.json"
    write_json(ready, {"schema": "arena.coffee-peak.private-ready/1",
                       "receipt_sha256": digest(receipt), "linkage_sha256": linkage_sha}, exclusive=True)
    storage.put_once(prefix + "private/ready.json", ready)
    public_dir = output / "producer-public"
    public_dir.mkdir(mode=0o755)
    write_json(public_dir / "producer-public-b0.json", public, exclusive=True)
    release = {
        "schema": "arena.coffee-peak.public-release/1", "protocol": "coffee_peak_capacity_v1",
        "run_id": str(run_id), "frozen_sha": frozen_sha,
        "source_package_sha256": config["source"]["sha256"],
        "public_sha256": public_sha, "condition": "B0",
        "construction_end_exclusive": config["construction_end_min"],
        "private_custody_completed": True, "truth_released": False,
        "producer_models_generated": 0, "evidence_kind": "PRE_SCIENTIFIC_CUSTODY_ADMISSION",
    }
    write_json(public_dir / "release.json", release, exclusive=True)
    # Durable public mirror for later replay even after GitHub artifact expiry.
    # Still under the private bucket: producer jobs only get their Actions copy.
    storage.put_once(prefix + "public/producer-public-b0.json",
                     public_dir / "producer-public-b0.json")
    storage.put_once(prefix + "public/release.json", public_dir / "release.json")
    # The runner private dir must never be an upload-artifact path.
    return release


def producer_boundary(public_dir, out, *, environment=None, expected_config=None):
    """Run exclusively in a separate producer job without custodial secrets."""
    environment = os.environ if environment is None else environment
    _require(not any(environment.get(name) for name in RESTRICTED_ENV), "PRODUCER_HAS_PRIVATE_CREDENTIAL")
    public_dir = Path(public_dir)
    _require(public_dir.is_dir() and {p.name for p in public_dir.iterdir()}
             == {"producer-public-b0.json", "release.json"}, "PUBLIC_ARTIFACT_CONTENTS")
    for file in public_dir.iterdir():
        _require(file.is_file() and not file.is_symlink(), "PUBLIC_ARTIFACT_NOT_REGULAR")
    public = read_json(public_dir / "producer-public-b0.json")
    release = read_json(public_dir / "release.json")
    _require(public.get("schema") == "arena.coffee-peak.public-b0/1"
             and release.get("schema") == "arena.coffee-peak.public-release/1",
             "PUBLIC_SCHEMA_INVALID")
    _require(digest(public) == release.get("public_sha256")
             and public.get("source_package_sha256") == release.get("source_package_sha256")
             and public.get("condition") == "B0" and release.get("condition") == "B0"
             and release.get("truth_released") is False
             and release.get("private_custody_completed") is True,
             "PUBLIC_RELEASE_COMMITMENT_INVALID")
    _require(release.get("producer_models_generated") == 0
             and public.get("time", {}).get("construction_end_exclusive")
                 == release.get("construction_end_exclusive"),
             "PUBLIC_RELEASE_METADATA_INVALID")
    if environment.get("GITHUB_RUN_ID") and environment["GITHUB_RUN_ID"] != release.get("run_id"):
        raise ArenaError("COFFEE_CUSTODY_PUBLIC_RUN_ID_MISMATCH")
    if environment.get("GITHUB_SHA") and environment["GITHUB_SHA"] != release.get("frozen_sha"):
        raise ArenaError("COFFEE_CUSTODY_PUBLIC_COMMIT_MISMATCH")
    if expected_config is not None:
        _require(release["source_package_sha256"] == expected_config["source"]["sha256"]
                 and public["selection"] == expected_config["selection"]
                 and release["construction_end_exclusive"] == expected_config["construction_end_min"],
                 "WRONG_CONFIGURED_PUBLIC_INSTANCE")
    _require(set(public) == {"schema", "evidence_kind", "condition", "source_package_sha256",
                             "selection", "time", "semantics", "pos_records", "pos_line_items",
                             "video_proxy"}, "PUBLIC_TOP_LEVEL_FIELDS_INVALID")
    _require(isinstance(public["pos_records"], list)
             and isinstance(public["pos_line_items"], list)
             and isinstance(public["video_proxy"], list), "PUBLIC_ROWS_INVALID")
    for row in public["pos_records"]:
        _require(isinstance(row, dict) and set(row) == set(ALLOWED_POS), "PUBLIC_POS_FIELDS_INVALID")
    for row in public["pos_line_items"]:
        _require(isinstance(row, dict) and set(row) == set(ALLOWED_LINES), "PUBLIC_LINE_FIELDS_INVALID")
    for row in public["video_proxy"]:
        _require(isinstance(row, dict) and set(row) == set(ALLOWED_PROFILE),
                 "PUBLIC_VIDEO_FIELDS_INVALID")
    for row in public.get("pos_records", []):
        _require(all(re.fullmatch(r"(?:ord|pos)-[0-9a-f]{32}", row[k])
                     for k in ("order_id", "pos_record_id")), "NON_OPAQUE_PUBLIC_ID")
    for row in public.get("pos_line_items", []):
        _require(all(re.fullmatch(r"(?:ord|pos|line)-[0-9a-f]{32}", row[k])
                     for k in ("order_id", "pos_record_id", "pos_line_id")), "NON_OPAQUE_PUBLIC_ID")
    # Plain semantic check complements exact-whitelist data export in coffee_peak.py.
    _require(not any("truth" in key or "linkage" in key for key in public),
             "PRIVATE_FIELD_IN_PUBLIC")
    result = {"schema": "arena.coffee-peak.producer-boundary/1",
              "status": "PUBLIC_ONLY_BOUNDARY_VERIFIED", "public_sha256": release["public_sha256"],
              "run_id": release["run_id"], "frozen_sha": release["frozen_sha"],
              "arms": {a: "NOT_EXECUTED" for a in ARMS},
              "r2_credentials_available": False, "truth_available": False,
              "scientific_lock_created": False, "provider_posts": 0, "new_omc": 0}
    write_json(out, result, exclusive=True)
    return result


def require_real_lock_before_reveal(lock, archive):
    """Fail-closed future evaluator gate. No release without genuine predictions.

    An externally verified, archived lock artifact is required; a mere local
    JSON claiming success is insufficient. The scientific evaluator is NOT
    enabled by the current custody workflow.
    """
    _require(lock.get("schema") == "arena.coffee-peak.prediction-lock/1"
             and lock.get("mode") == "SCIENTIFIC"
             and set(lock.get("arms", {})) == set(ARMS), "SCIENTIFIC_LOCK_MISSING")
    _require(all(lock["arms"][arm].get("status") in ("PREDICTED", "FAILED_NATIVE", "NO_NATIVE")
                 for arm in ARMS), "LOCK_ARM_STATUS_INVALID")
    _require(type(archive.get("github_artifact_id")) is int
             and archive["github_artifact_id"] > 0
             and archive.get("verified_by_github_api") is True
             and archive.get("immutable_archive_read_before_reveal") is True
             and archive.get("producer_write_disabled") is True,
             "ARCHIVE_NOT_VERIFIED")
    _require(archive.get("lock_sha256") == digest(lock), "LOCK_ARCHIVE_HASH_MISMATCH")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Coffee custodian role; no CT03 effects")
    p = parser.add_subparsers(dest="command", required=True)
    stage = p.add_parser("stage-source")
    stage.add_argument("--config", required=True)
    adm = p.add_parser("admit")
    adm.add_argument("--config", required=True)
    adm.add_argument("--out", required=True)
    adm.add_argument("--run-id", required=True)
    adm.add_argument("--sha", required=True)
    boundary = p.add_parser("producer-boundary")
    boundary.add_argument("--public-dir", required=True)
    boundary.add_argument("--out", required=True)
    boundary.add_argument("--config", required=False)
    args = parser.parse_args(argv)
    try:
        if args.command == "producer-boundary":
            if args.config:
                from .config import load
                expected = load(args.config)
            else:
                expected = None
            result = producer_boundary(args.public_dir, args.out, expected_config=expected)
        else:
            from .config import load
            cfg = load(args.config)
            if args.command == "stage-source":
                result = stage_source(cfg, R2Storage())
            else:
                _require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
                         and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                         and os.environ.get("GITHUB_REF") == "refs/heads/main"
                         and os.environ.get("GITHUB_RUN_ID") == str(args.run_id)
                         and os.environ.get("GITHUB_SHA") == args.sha,
                         "LIVE_CUSTODY_REQUIRES_MAIN_FIRST_MANUAL_DISPATCH")
                result = admit(cfg, R2Storage(), args.out, run_id=args.run_id, frozen_sha=args.sha)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ArenaError, ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "STOPPED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
