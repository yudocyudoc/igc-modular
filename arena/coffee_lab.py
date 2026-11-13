"""Coffee P3: honest original-arm readiness, immutable pre-reveal lock and API proof.

D and M prepare CT03-native candidates, not coffee-native models. Buffalo has not
executed a coffee model. This is an executable *no-inference* bridge, NOT a
scientific prediction or an authorization to open hidden synthetic truth.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import zipfile
from urllib.parse import urlsplit
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

from .common import ArenaError, digest, read_json, write_json
from .coffee_custody import ARMS, producer_boundary, require_real_lock_before_reveal

ARM_SCHEMA = "arena.coffee-peak.arm-submission/1"
LOCK_SCHEMA = "arena.coffee-peak.prediction-lock/1"
PUBLIC_NAME = "producer-public-b0.json"
RELEASE_NAME = "release.json"
RUN_RE = re.compile(r"[1-9][0-9]{0,19}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
REPO = "yudocyudoc/igc-modular"
WORKFLOW = ".github/workflows/coffee-peak-custody.yml"


def _need(condition, reason):
    if not condition:
        raise ArenaError("COFFEE_LAB_" + reason)


def _verified_public(folder, *, environment=None):
    """Validate the only admitted construction artifact, never open the ZIP."""
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        proof = producer_boundary(folder, Path(temp) / "boundary.json",
                                  environment=environment)
    release = read_json(Path(folder) / RELEASE_NAME)
    return proof, release


def probe(public_dir, arm, out, *, environment=None, source_verifier=None):
    """One arm per independent job. Verify source identity; DO NOT run CT03 as coffee.

    `source_verifier` is a test-only dependency injection; the real CLI calls
    the verified upstream manifest, without provider, solver or credentials.
    """
    _need(arm in ARMS, "UNKNOWN_ARM")
    boundary, release = _verified_public(public_dir, environment=environment)
    if source_verifier is None:
        from .runtime import verify
        origin = verify(include_history=False)
    else:
        origin = source_verifier()
    _need(origin.get("unchanged") is True and origin.get("files", 0) > 0,
          "UPSTREAM_IDENTITY_NOT_VERIFIED")
    known = {
        "D": "OriginalD / conservative-chain generator (CT03 domain)",
        "M": "OriginalM / Short E1 composition (CT03 domain)",
        "B": "OriginalB / UB-IAD sd-ai Engine.generate (not invoked)",
    }
    submission = {
        "schema": ARM_SCHEMA, "arm": arm, "status": "NO_NATIVE",
        "evidence_kind": "ORIGINAL_ENGINE_READINESS_ONLY",
        "protocol": "coffee_peak_capacity_v1", "condition": "B0",
        "source_package_sha256": release["source_package_sha256"],
        "public_sha256": boundary["public_sha256"],
        "run_id": release["run_id"], "frozen_sha": release["frozen_sha"],
        "original_engine": known[arm],
        "original_sources_verified": True,
        "upstream": {"igc_commit": origin.get("igc_commit"),
                     "buffalo_commit": origin.get("buffalo_commit"),
                     "manifest_files_verified": origin["files"]},
        "representability": {k: "no_demostrado" for k in
            ("cashier", "shared_prep", "abandonment", "stock_balance",
             "S1_staff", "S2_machine", "S3_both", "S4_batch", "S5_reallocation")},
        "coffee_domain_adapter_validated": False,
        "native_model_sha256": None, "native_receipt_sha256": None,
        "predictions": None, "holdout_read": False,
        "provider_posts": 0, "new_omc": 0,
        "stop_reason": "COFFEE_NATIVE_ADAPTER_NOT_VALIDATED",
    }
    write_json(out, submission, exclusive=True)
    return submission


def validate_submission(row, release):
    _need(isinstance(row, dict) and row.get("schema") == ARM_SCHEMA,
          "SUBMISSION_SCHEMA_INVALID")
    arm = row.get("arm")
    _need(arm in ARMS, "SUBMISSION_ARM_INVALID")
    _need(row.get("status") == "NO_NATIVE"
          and row.get("evidence_kind") == "ORIGINAL_ENGINE_READINESS_ONLY"
          and row.get("native_model_sha256") is None
          and row.get("native_receipt_sha256") is None
          and row.get("predictions") is None,
          "PREDICTION_NOT_AUTHORIZED_BY_P3")
    _need(row.get("source_package_sha256") == release["source_package_sha256"]
          and row.get("public_sha256") == release["public_sha256"]
          and row.get("run_id") == release["run_id"]
          and row.get("frozen_sha") == release["frozen_sha"]
          and row.get("condition") == "B0"
          and row.get("protocol") == "coffee_peak_capacity_v1",
          "SUBMISSION_PROVENANCE_MISMATCH")
    _need(row.get("original_sources_verified") is True
          and row.get("coffee_domain_adapter_validated") is False
          and row.get("holdout_read") is False
          and row.get("provider_posts") == 0
          and row.get("new_omc") == 0,
          "SUBMISSION_FALSE_EXECUTION_OR_LEAK")
    capabilities = row.get("representability")
    _need(isinstance(capabilities, dict)
          and set(capabilities) == {"cashier", "shared_prep", "abandonment",
                                    "stock_balance", "S1_staff", "S2_machine",
                                    "S3_both", "S4_batch", "S5_reallocation"}
          and set(capabilities.values()) == {"no_demostrado"},
          "CAPABILITY_NOT_DEMONSTRATED")
    return arm


def freeze(public_dir, submissions_dir, out, *, environment=None):
    """Freeze three verifiable NO_NATIVE outcomes; this lock cannot reveal truth."""
    proof, release = _verified_public(public_dir, environment=environment)
    folder = Path(submissions_dir)
    expected = {f"submission-{a}.json" for a in ARMS}
    _need(folder.is_dir() and {x.name for x in folder.iterdir()} == expected
          and all(x.is_file() and not x.is_symlink() for x in folder.iterdir()),
          "INCOMPLETE_OR_CONTAMINATED_PRODUCER_ARTIFACTS")
    rows = {}
    for arm in ARMS:
        submission = read_json(folder / f"submission-{arm}.json")
        _need(validate_submission(submission, release) == arm, "ARM_SUBMISSION_MISMATCH")
        rows[arm] = {"status": submission["status"],
                     "submission_sha256": digest(submission),
                     "model_sha256": None, "predictions": None,
                     "representability": submission["representability"]}
    public = read_json(Path(public_dir) / PUBLIC_NAME)
    _need(public.get("selection") and isinstance(public.get("selection"), dict)
          and set(public["selection"]) == {"scenario_id", "replication", "day_of_week"}
          and public.get("time", {}).get("construction_end_exclusive")
              == release["construction_end_exclusive"]
          and public.get("time", {}).get("window_end") == 103.237
          and 0 < release["construction_end_exclusive"] < 80.0
          and proof["public_sha256"] == release["public_sha256"],
          "PUBLIC_CASE_NOT_VERIFIED")
    lock = {
        "schema": LOCK_SCHEMA, "mode": "READINESS_ONLY", "protocol": "coffee_peak_capacity_v1",
        "condition": "B0", "run_id": release["run_id"],
        "frozen_sha": release["frozen_sha"],
        "source_package_sha256": release["source_package_sha256"],
        "selection": dict(public["selection"]),
        "window_end_min": public["time"]["window_end"],
        "public_sha256": proof["public_sha256"],
        "construction_end_exclusive": release["construction_end_exclusive"],
        "arms": rows,
        "reserved_observables": ["paid_sales_cumulative", "refund_amount_mxn_cumulative",
                                 "completed_orders", "waiting_time_min", "abandonment_count"],
        "score": None, "truth_opened": False, "scientific_conclusion": None,
        "provider_posts": 0, "new_omc": 0,
    }
    target = Path(out)
    _need(not target.exists(), "LOCK_DIRECTORY_ALREADY_EXISTS")
    target.mkdir(parents=True)
    write_json(target / "lock.json", lock, exclusive=True)
    checksum = "sha256:" + hashlib.sha256((target / "lock.json").read_bytes()).hexdigest()
    (target / "lock-sha256.txt").write_text(checksum + "\n", encoding="ascii")
    return lock


def inspect_lock_files(folder):
    folder = Path(folder)
    _need(folder.is_dir() and {p.name for p in folder.iterdir()} ==
          {"lock.json", "lock-sha256.txt"}, "LOCK_ARTIFACT_CONTENTS_INVALID")
    files = [folder / "lock.json", folder / "lock-sha256.txt"]
    _need(all(p.is_file() and not p.is_symlink() for p in files),
          "LOCK_ARTIFACT_UNSAFE_FILES")
    lock = read_json(files[0]); expected = files[1].read_text(encoding="ascii")
    _need(HASH_RE.fullmatch(expected.strip()) is not None
          and expected == "sha256:" + hashlib.sha256(files[0].read_bytes()).hexdigest() + "\n",
          "LOCK_BYTES_MISMATCH")
    _need(lock.get("schema") == LOCK_SCHEMA and lock.get("mode") == "READINESS_ONLY"
          and lock.get("truth_opened") is False
          and lock.get("score") is None and lock.get("scientific_conclusion") is None
          and isinstance(lock.get("selection"), dict)
          and set(lock["selection"]) == {"scenario_id", "replication", "day_of_week"}
          and isinstance(lock["selection"].get("scenario_id"), str)
          and type(lock["selection"].get("replication")) is int
          and type(lock["selection"].get("day_of_week")) is int
          and lock.get("window_end_min") == 103.237
          and type(lock.get("construction_end_exclusive")) in (int, float)
          and float(lock["construction_end_exclusive"]).is_integer()
          and 0 < lock["construction_end_exclusive"] < 80.0
          and HASH_RE.fullmatch(str(lock.get("public_sha256", ""))) is not None
          and set(lock.get("arms", {})) == set(ARMS)
          and all(lock["arms"][a].get("status") == "NO_NATIVE" for a in ARMS),
          "LOCK_READINESS_ONLY_NOT_WELL_FORMED")
    return lock


def _api_json(path, token):
    _need(bool(token), "GITHUB_TOKEN_REQUIRED")
    req = urllib.request.Request("https://api.github.com" + path,
             headers={"Authorization": "Bearer " + token,
                      "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28",
                      "User-Agent": "IGC-Coffee-Lab-Archive-Verify"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(response.read(1024 * 1024))
    except (ValueError, OSError, urllib.error.HTTPError):
        raise ArenaError("COFFEE_LAB_GITHUB_API_VERIFICATION_FAILED") from None


MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024


class _SafeArchiveRedirect(urllib.request.HTTPRedirectHandler):
    """Follow the official GitHub signed ZIP URL without forwarding our token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _need(urlsplit(newurl).scheme == "https", "ARCHIVE_REDIRECT_NOT_HTTPS")
        target = super().redirect_request(req, fp, code, msg, headers, newurl)
        if target is not None and urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            # GitHub redirects archive ZIPs to temporary signed object-storage URLs.
            # Only the initial api.github.com request may carry GH_TOKEN.
            target = urllib.request.Request(newurl, headers={
                "User-Agent": "IGC-Coffee-Lab-Archive-Verify",
                "Accept": "application/octet-stream"})
        return target


def _github_archive_zip(repo, artifact_id, token):
    """Download ZIP bytes by the exact immutable artifact ID; fail without a token."""
    _need(bool(token), "GITHUB_TOKEN_REQUIRED")
    url = f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "IGC-Coffee-Lab-Archive-Verify"})
    try:
        with urllib.request.build_opener(_SafeArchiveRedirect()).open(request, timeout=25) as response:
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
    except (ValueError, OSError, urllib.error.HTTPError):
        raise ArenaError("COFFEE_LAB_GITHUB_ARCHIVE_DOWNLOAD_FAILED") from None
    _need(0 < len(payload) <= MAX_ARCHIVE_BYTES, "ARCHIVE_ZIP_SIZE_INVALID")
    return payload


def _match_archive_to_local(folder, archive_data):
    """Compare exact archive member bytes to local verifier input, not metadata."""
    _need(isinstance(archive_data, bytes) and 0 < len(archive_data) <= MAX_ARCHIVE_BYTES,
          "ARCHIVE_ZIP_SIZE_INVALID")
    expected = {"lock.json", "lock-sha256.txt"}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            entries = archive.infolist()
            _need(len(entries) == len(expected)
                  and {info.filename for info in entries} == expected
                  and all(not info.is_dir() and info.file_size <= MAX_MEMBER_BYTES
                          and ((info.external_attr >> 16) & 0o170000) != 0o120000
                          for info in entries), "ARCHIVE_ZIP_MEMBERS_INVALID")
            for name in expected:
                _need(archive.read(name) == (Path(folder) / name).read_bytes(),
                      "ARCHIVED_LOCK_BYTES_DIFFER_FROM_LOCAL")
    except (zipfile.BadZipFile, RuntimeError, OSError, ValueError, EOFError):
        raise ArenaError("COFFEE_LAB_ARCHIVE_ZIP_INVALID") from None
    return hashlib.sha256(archive_data).hexdigest()


def verify_archived_lock(folder, *, artifact_id, run_id, frozen_sha, repo=REPO,
                         api_get=None, archive_fetch=None, environment=None):
    """Verify metadata AND exact ZIP bytes downloaded by artifact ID.

    `api_get` and `archive_fetch` are injected only in offline tests. The CLI
    fetches the real GitHub archive by ID. No metadata-only approval is possible.
    The readiness archive still cannot authorize R2 truth release.
    """
    env = os.environ if environment is None else environment
    _need(repo == REPO and RUN_RE.fullmatch(str(run_id)) is not None
          and COMMIT_RE.fullmatch(frozen_sha) is not None
          and type(artifact_id) is int and artifact_id > 0,
          "INVALID_ARCHIVE_IDENTITY")
    _need(env.get("GITHUB_RUN_ID") in (None, str(run_id))
          and env.get("GITHUB_SHA") in (None, frozen_sha), "RUN_ENV_MISMATCH")
    _need(not any(env.get(k) for k in ("CT03_R2_ACCESS_KEY_ID",
          "CT03_R2_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")),
          "ARCHIVE_VERIFIER_HAS_CUSTODY_SECRETS")
    lock = inspect_lock_files(folder)
    _need(lock["run_id"] == str(run_id) and lock["frozen_sha"] == frozen_sha,
          "LOCK_RUN_SHA_MISMATCH")
    if api_get is None:
        token = env.get("GH_TOKEN", "")
        api_get = lambda path: _api_json(path, token)
    run = api_get(f"/repos/{repo}/actions/runs/{run_id}")
    artifact = api_get(f"/repos/{repo}/actions/artifacts/{artifact_id}")
    path = run.get("path", "")
    _need(run.get("id") == int(run_id) and run.get("head_sha") == frozen_sha
          and run.get("head_branch") == "main" and run.get("event") == "workflow_dispatch"
          and run.get("run_attempt") == 1
          and path.split("@", 1)[0] == WORKFLOW,
          "GITHUB_RUN_NOT_ORIGINAL_ONE_DISPATCH")
    _need(artifact.get("id") == artifact_id and artifact.get("name") == f"coffee-lock-{run_id}"
          and artifact.get("expired") is False
          and artifact.get("workflow_run", {}).get("id") == int(run_id)
          and artifact.get("size_in_bytes", 0) > 0,
          "GITHUB_ARTIFACT_NOT_IMMUTABLE_RUN_ARCHIVE")
    if archive_fetch is None:
        payload = _github_archive_zip(repo, artifact_id, env.get("GH_TOKEN", ""))
    else:
        payload = archive_fetch(repo, artifact_id)
    archive_zip_sha = _match_archive_to_local(folder, payload)
    archive = {
        "schema": "arena.coffee-peak.github-lock-verified/1",
        "status": "READINESS_ARCHIVE_VERIFIED_NO_REVEAL",
        "github_run_id": int(run_id), "github_artifact_id": artifact_id,
        "frozen_sha": frozen_sha, "lock_sha256": digest(lock),
        "file_sha256": hashlib.sha256((Path(folder)/"lock.json").read_bytes()).hexdigest(),
        "artifact_zip_sha256": archive_zip_sha,
        "artifact_content_verified": True,
        "verified_by_github_api": True, "immutable_archive_read_before_reveal": True,
        "producer_write_disabled": True, "scientific_lock": False,
        "holdout_opened": False, "provider_posts": 0, "new_omc": 0,
    }
    # Even a valid readiness lock can NEVER be used to open the reserve.
    try:
        require_real_lock_before_reveal(lock, archive)
    except ArenaError:
        pass
    else:
        raise ArenaError("COFFEE_LAB_READINESS_LOCK_UNEXPECTEDLY_REVEALABLE")
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description="Coffee P3, public-only readiness + immutable lock")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe"); p.add_argument("--public-dir", required=True)
    p.add_argument("--arm", choices=ARMS, required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("freeze"); p.add_argument("--public-dir", required=True)
    p.add_argument("--submissions-dir", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("verify-archive"); p.add_argument("--lock-dir", required=True)
    p.add_argument("--artifact-id", type=int, required=True)
    p.add_argument("--run-id", required=True); p.add_argument("--sha", required=True)
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "probe":
            result = probe(args.public_dir, args.arm, args.out)
        elif args.command == "freeze":
            result = freeze(args.public_dir, args.submissions_dir, args.out)
        else:
            result = verify_archived_lock(args.lock_dir,
                         artifact_id=args.artifact_id, run_id=args.run_id,
                         frozen_sha=args.sha)
            write_json(args.out, result, exclusive=True)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ArenaError, ValueError, OSError, KeyError, TypeError) as e:
        print(json.dumps({"status": "STOPPED", "reason": str(e)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
