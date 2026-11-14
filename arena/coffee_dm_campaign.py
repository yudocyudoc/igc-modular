"""Coffee B0 D/M campaign: exact custody artifact -> native -> static audit.

No R2 access, cloud providers, OMC, hidden synthetic truth, scientific lock,
or competitor repair. Admission is pinned to Buffalo B-LIVE-01's public case.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import zipfile

from .common import ArenaError, digest, read_json, write_json
from .connections import Secret
from .coffee_domain import build_case
from .coffee_adapters.shared import sha_bytes, case_guard
from .github import GitHub

REPO = "yudocyudoc/igc-modular"
SOURCE_RUN_ID = 43532737911
SOURCE_SHA = "4dd62c8b323096abfa3aca8675a311738cdce34e"
ARTIFACT_ID = 14088545399
ARTIFACT_NAME = f"coffee-public-{SOURCE_RUN_ID}"
ARCHIVE_SHA256 = "872cf83210a54c88563a13130c3cec819bf1a978db93d6b08610634f282c42d2"
PUBLIC_SHA256 = "sha256:531a9d823c4d76a53711bb074d2243e1ad589e454870ed760b24ee5d70bd5762"
CASE_SHA256 = "sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f"
SOURCE_PACKAGE_SHA256 = "4ff97ae4d8fe52a5c1d1701aa713fda09b6730ef63d9cbab23e6af30dfad2a5f"
SELECTION = {"scenario_id": "demanda_bajo__dias6_7_bajo__paciencia_sensible",
             "replication": 1, "day_of_week": 1}
EXPECTED_FILES = ("producer-public-b0.json", "release.json")
MAX_ARCHIVE_SIZE = 100_000
MAX_UNCOMPRESSED_SIZE = 100_000
RUN_SOURCE = ".github/workflows/coffee-peak-custody.yml"
NO_R2 = ("CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
         "COFFEE_R2_ACCESS_KEY_ID", "COFFEE_R2_SECRET_ACCESS_KEY",
         "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
         "CLOUDFLARE_API_TOKEN")
ASSUMPTIONS = Path(__file__).resolve().parents[1] / "examples/coffee_public_assumptions_v1.json"


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_DM_CAMPAIGN_" + code)


def identity(env=None):
    env = os.environ if env is None else env
    need(not any(env.get(k) for k in NO_R2), "PRIVATE_OR_PROVIDER_CREDENTIAL_PRESENT")
    need(env.get("GITHUB_REPOSITORY") == REPO
         and env.get("GITHUB_REF") == "refs/heads/main"
         and env.get("GITHUB_EVENT_NAME") in ("workflow_dispatch", "push")
         and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and re.fullmatch(r"[1-9][0-9]{0,19}", env.get("GITHUB_RUN_ID", "")),
         "MAIN_FIRST_RUN_REQUIRED")
    return int(env["GITHUB_RUN_ID"])


def validate_public_zip(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE_SIZE,
         "ARCHIVE_SIZE_INVALID")
    need(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA256,
         "SOURCE_ARTIFACT_ZIP_SHA256_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            infos = zf.infolist()
            need(len(infos) == 2 and
                 sorted(x.filename for x in infos) == list(EXPECTED_FILES) and
                 all(not x.is_dir() and
                     not (x.external_attr >> 16 & 0o170000 == 0o120000) and
                     0 <= x.file_size <= MAX_UNCOMPRESSED_SIZE
                     for x in infos) and
                 sum(x.file_size for x in infos) <= MAX_UNCOMPRESSED_SIZE,
                 "UNEXPECTED_PUBLIC_ARTIFACT_MEMBERS")
            contents = {info.filename: zf.read(info) for info in infos}
        public = json.loads(contents["producer-public-b0.json"])
        release = json.loads(contents["release.json"])
    except (ValueError, UnicodeError, zipfile.BadZipFile, KeyError):
        raise ArenaError("COFFEE_DM_CAMPAIGN_PUBLIC_ARTIFACT_UNREADABLE") from None
    need(release.get("run_id") == str(SOURCE_RUN_ID)
         and release.get("frozen_sha") == SOURCE_SHA
         and release.get("source_package_sha256") == SOURCE_PACKAGE_SHA256
         and release.get("condition") == "B0"
         and release.get("private_custody_completed") is True
         and release.get("truth_released") is False
         and release.get("public_sha256") == PUBLIC_SHA256
         and public.get("source_package_sha256") == SOURCE_PACKAGE_SHA256
         and public.get("selection") == SELECTION
         and digest(public) == PUBLIC_SHA256,
         "PUBLIC_RELEASE_NOT_THE_ADMITTED_B0")
    return contents


def acquire(out, *, api=None, env=None, assumptions=ASSUMPTIONS):
    """Download and attest exact GitHub ZIP; no independent public re-export."""
    run_id = identity(env)
    out = Path(out)
    need(not out.exists(), "REFUSE_OUTPUT_OVERWRITE")
    env = os.environ if env is None else env
    if api is None:
        need(bool(env.get("GH_TOKEN")), "GITHUB_READ_TOKEN_REQUIRED")
        api = GitHub(REPO, Secret(env["GH_TOKEN"], "GITHUB_TOKEN"))
    source = api.run(SOURCE_RUN_ID)
    need(source.get("id") == SOURCE_RUN_ID and
         source.get("path") == RUN_SOURCE and
         source.get("head_sha") == SOURCE_SHA and
         source.get("head_branch") == "main" and
         source.get("event") == "workflow_dispatch" and
         source.get("run_attempt") == 1 and
         source.get("status") == "completed" and
         source.get("conclusion") == "success",
         "SOURCE_GITHUB_RUN_NOT_VERIFIED")
    meta = api.repo("GET", f"/actions/artifacts/{ARTIFACT_ID}")
    need(meta.get("id") == ARTIFACT_ID and
         meta.get("name") == ARTIFACT_NAME and
         meta.get("expired") is False and
         meta.get("workflow_run", {}).get("id") == SOURCE_RUN_ID and
         meta.get("digest") == "sha256:" + ARCHIVE_SHA256,
         "SOURCE_GITHUB_ARTIFACT_NOT_VERIFIED")
    # Validate the same exact bytes as the first Buffalo generation, not a
    # reconstruction of the original 17MB synthetic world.
    contents = validate_public_zip(
        api.repo("GET", f"/actions/artifacts/{ARTIFACT_ID}/zip", binary=True))
    out.mkdir(parents=True, mode=0o700)
    public = out / "public"
    public.mkdir(mode=0o700)
    for name, raw in contents.items():
        with (public / name).open("xb") as stream:
            stream.write(raw)
    # The only normal pathway to the common case validates the custody
    # public-only boundary and guards construction vs future information.
    # This is a subsequent producer run; the historical release has its own
    # verified run ID and SHA. Never compare them to this new execution run.
    case = case_guard(build_case(public, assumptions, environment={}))
    need(digest(case) == CASE_SHA256 and
         case["input"]["rate_orders_per_hour"] == 10.0 and
         case["public_sha256"] == PUBLIC_SHA256 and
         case["source_package_sha256"] == SOURCE_PACKAGE_SHA256 and
         case["selection"] == SELECTION and
         case["time"]["construction_end_min"] == 60.0 and
         case["time"]["window_end_min"] == 103.237,
         "CASE_DIFFERS_FROM_BUFFALO_B_LIVE_01")
    receipt = {
        "schema": "arena.coffee-peak.dm-source-attestation/1",
        "status": "EXACT_GITHUB_PUBLIC_SOURCE_VERIFIED",
        "execution_run_id": run_id, "source_run_id": SOURCE_RUN_ID,
        "source_sha": SOURCE_SHA, "source_artifact_id": ARTIFACT_ID,
        "source_artifact_name": ARTIFACT_NAME,
        "artifact_zip_sha256": "sha256:" + ARCHIVE_SHA256,
        "public_sha256": PUBLIC_SHA256, "case_sha256": digest(case),
        "model_generation": "NOT_YET_STARTED", "truth_access": False,
        "provider_posts": 0, "new_omc": 0, "scientific_lock_created": False,
    }
    write_json(out / "attestation.json", receipt, exclusive=True)
    return receipt


def generate(root, *, env=None):
    """Invoke existing native D/M prepare only after independently attested B0."""
    identity(env)
    root = Path(root)
    proof = read_json(root / "attestation.json")
    need(proof.get("status") == "EXACT_GITHUB_PUBLIC_SOURCE_VERIFIED"
         and proof.get("source_artifact_id") == ARTIFACT_ID
         and proof.get("public_sha256") == PUBLIC_SHA256
         and proof.get("case_sha256") == CASE_SHA256, "NATIVE_SOURCE_NOT_ATTESTED")
    case = case_guard(build_case(root / "public", ASSUMPTIONS, environment={}))
    need(digest(case) == CASE_SHA256, "NATIVE_CASE_NOT_BUFFALO_B01")
    from .coffee_native_dm import prepare
    result = prepare(root / "public", ASSUMPTIONS, root / "native",
                     verify_original=True, environment={})
    need(result.get("arms") == {"D": 6, "M": 6}
         and result.get("status") == "ORIGINAL_NATIVE_GENERATED_NOT_SIMULATED",
         "NATIVE_GENERATION_CONTRACT_FAILED")
    return result


def audit(root, *, out=None):
    """Inspect real emitted D/M originals. Static audit != OMC or causal fit."""
    root = Path(root)
    public_dir = root / "public"
    native = root / "native"
    need(public_dir.is_dir() and native.is_dir(), "MISSING_PUBLIC_OR_NATIVE")
    need({p.name for p in public_dir.iterdir()} == set(EXPECTED_FILES),
         "EXTRA_PUBLIC_FILES")
    src = read_json(root / "attestation.json")
    need(src.get("status") == "EXACT_GITHUB_PUBLIC_SOURCE_VERIFIED"
         and src.get("source_artifact_id") == ARTIFACT_ID
         and src.get("case_sha256") == CASE_SHA256, "BAD_ADMISSION_RECEIPT")
    case = case_guard(build_case(public_dir, ASSUMPTIONS, environment={}))
    need(digest(case) == CASE_SHA256 and
         read_json(native / "public-case.json") == case, "PUBLIC_CASE_CHANGED")
    summary = read_json(native / "summary.json")
    need(summary.get("arms") == {"D": 6, "M": 6}
         and summary.get("status") == "ORIGINAL_NATIVE_GENERATED_NOT_SIMULATED"
         and summary.get("new_omc") == 0
         and summary.get("provider_posts") == 0
         and summary.get("truth_access") is False
         and summary.get("scientific_lock_created") is False,
         "GENERATOR_REPORTED_UNEXPECTED_EFFECT")
    need({p.name for p in native.iterdir()} ==
         {"D", "M", "public-case.json", "summary.json"}, "NATIVE_TREE_UNEXPECTED")
    reports = {}
    for arm in ("D", "M"):
        folder = native / arm
        m = read_json(folder / "manifest.json")
        expected = {"manifest.json", *m.get("files", {})}
        need({p.name for p in folder.iterdir()} == expected and
             all(p.is_file() and not p.is_symlink() for p in folder.iterdir()),
             "NATIVE_FILES_UNEXPECTED_" + arm)
        need(m.get("arm") == arm and m.get("candidate_count") == 6
             and len(m.get("candidates", [])) == 6
             and m.get("public_case_sha256") == CASE_SHA256
             and m.get("public_sha256") == PUBLIC_SHA256
             and m.get("run_id") == str(SOURCE_RUN_ID)
             and m.get("source_package_sha256") == SOURCE_PACKAGE_SHA256
             and m.get("selection") == SELECTION
             and m.get("hypotheses_sha256") == case["hypotheses_sha256"]
             and m.get("provider_posts") == 0 and m.get("new_omc") == 0
             and m.get("solver_status") == "NOT_RUN"
             and m.get("truth_access") is False
             and m.get("model_validation") == "GENERATED_NOT_COMPILED_OR_SIMULATED",
             "NATIVE_MANIFEST_PROVENANCE_" + arm)
        for name, meta in m["files"].items():
            need(name not in ("", ".", "..") and "/" not in name and
                 "\\" not in name, "UNSAFE_NATIVE_FILE")
            data = (folder / name).read_bytes()
            need(meta == {"sha256": sha_bytes(data), "bytes": len(data)},
                 "NATIVE_FILE_BYTES_MISMATCH_" + arm)
        entries = []
        for c in m["candidates"]:
            problems = []
            if arm == "D":
                graph = c["structure"]
                stocks = graph["stocks"]
                n = len(stocks)
                txt = (folder / c["modelica_file"]).read_text(encoding="utf-8")
                from .coffee_adapters import d
                original = d.original()
                try:
                    need(original.lint_structure(graph)["status"] == "G1_STRUCTURE_ADMISSIBLE"
                         and c["structure_hash"] == original.digest(graph),
                         "D_ORIGINAL_GRAPH_NOT_ADMISSIBLE")
                    need(c["physical_counter"] == "delivered"
                         and c["modelica_class"] in txt
                         and all(f"Real s{i}(start=0, fixed=true);" in txt
                                 for i in range(1, n+1))
                         and "Real delivered(start=0, fixed=true);" in txt
                         and "Real lost(start=0, fixed=true);" in txt
                         and "der(s1) = inputRate - f1 - lossRate;" in txt
                         and all(f"der(s{i}) = f{i-1} - f{i};" in txt
                                 for i in range(2, n+1))
                         and f"der(delivered) = f{n};" in txt
                         and "der(lost) = lossRate;" in txt
                         and "min(capacity, max(0," in txt
                         and "inputRate = if time < pulseDuration then pulseRate else 0;" in txt,
                         "D_MATERIAL_BALANCE_OR_OBSERVABLE_INVALID")
                    need(c["nominal_parameters"] == {"capacity": 12, "response_time": 0.1,
                                                      "loss_time": 20.0},
                         "D_PARAMETERS_NOT_PUBLIC_PRIORS")
                except (ArenaError, ValueError) as ex:
                    problems.append(str(ex))
                facts = {"stock_count": n, "post_payment_loss": graph["loss"],
                         "initial_stocks": "ZERO_EXPLICIT",
                         "material_balance": "STRUCTURAL_EQUATIONS_CHECKED_NOT_SOLVER",
                         "negative_state_prohibition": "NOT_PROVED_WITH_SOLVER"}
            else:
                from .coffee_adapters import m as adapter
                composed, _, _ = adapter.original()
                txt = (folder / "native.mo").read_text(encoding="utf-8")
                try:
                    registry = read_json(folder / "registry-snapshot.json")
                    graph = c["full_ast"]
                    need(c["full_ast_sha256"] == digest(graph) and
                         c["material_projection_sha256"] ==
                             digest(adapter.material_projection(graph, composed)),
                         "M_AST_OR_PROJECTION_INVALID")
                    need(c["physical_counter"] == "deliveredTotal"
                         and c["informational_signal_not_counter"] ==
                             "reportedDeliveryRate"
                         and c["modelica_class"].split(".")[-1] in txt
                         and "    deliveredTotal=" in txt
                         and "    reportedDeliveryRate=" in txt
                         and "der(" not in txt,
                         "M_OUTPUT_OR_ORIGINAL_EQUATIONS_INVALID")
                    need(registry["roles"]["preparation"]["parameters"] ==
                         {"maxThroughput": 12, "responseTime": 0.1}
                         and registry["roles"]["dispatch"]["parameters"] ==
                         {"maxThroughput": 12, "responseTime": 0.1}
                         and registry["roles"]["transit"]["parameters"] ==
                         {"maxThroughput": 100, "responseTime": 1.6}
                         and registry["roles"]["report"]["parameters"] ==
                         {"reportResponseTime": 1.6},
                         "M_ROLE_PARAMS_NOT_ORIGINAL")
                except (ArenaError, ValueError, KeyError, TypeError) as ex:
                    problems.append(str(ex))
                roles = [x["role"] for x in c["full_ast"]["instances"]]
                facts = {"roles": roles, "material_roles": [r for r in roles if r != "report"],
                         "material_balance": "REQUIRES_ALL_MOLECULAR_STOCKS_AND_SOLVER",
                         "catalog_transit_response_time_hours": 1.6,
                         "information_filter_response_time_hours": 1.6,
                         "preparation_response_time_hours": 0.1,
                         "information_output_not_physical_counter": True,
                         "negative_state_prohibition": "NOT_PROVED_WITH_SOLVER",
                         "dynamic_equivalence_of_material_groups": False}
            entries.append({"candidate_id": c["id"],
                            "class": c["modelica_class"],
                            "status": "STATIC_REJECTED" if problems else
                                      "STATIC_STRUCTURE_CHECKED_NOT_COMPILED",
                            "issues": problems,
                            "facts": facts})
        reports[arm] = {
            "method": m["method"], "candidate_count": len(entries),
            "candidates": entries,
            "file_sha256": {name: meta["sha256"] for name, meta in m["files"].items()},
            "original_source_unchanged": True,
            "mechanism_identified_from_pickups": False,
            "calibration_performed": False,
        }
    result = {
        "schema": "arena.coffee-peak.dm-native-static-audit/1",
        "status": "STATIC_AUDITED_WITH_REJECTIONS" if any(
            x["status"] == "STATIC_REJECTED"
            for r in reports.values() for x in r["candidates"]
        ) else "TWELVE_NATIVE_CANDIDATES_STATIC_AUDITED_NOT_SIMULATED",
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact_id": ARTIFACT_ID,
        "source_artifact_zip_sha256": "sha256:" + ARCHIVE_SHA256,
        "case_sha256": CASE_SHA256,
        "public_sha256": PUBLIC_SHA256,
        "assumed_paid_order_rate_per_hour": case["input"]["rate_orders_per_hour"],
        "prediction_cuts_minutes": [80.0, 100.0, 103.237],
        "arms": reports,
        "solver": {"checkModel": "NOT_RUN", "simulate": "NOT_RUN",
                   "new_omc_attempts": 0},
        "ledger_atms_feedback_consumed": False,
        "scientific_lock_created": False, "reserved_truth_opened": False,
        "provider_posts": 0, "r2_access": False,
        "note": "Structural audit of original native candidates. No compiled/simulated"
                " Modelica, no scientific adequacy or business-policy inference.",
    }
    path = Path(out) if out else root / "audit.json"
    write_json(path, result, exclusive=True)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate and audit native D/M on pinned B0")
    p.add_argument("action", choices=("source", "generate", "audit"))
    p.add_argument("--root", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if args.action == "source":
            result = acquire(args.root)
        elif args.action == "generate":
            result = generate(args.root)
        else:
            result = audit(args.root)
        print(json.dumps({"status": result["status"],
                          "source_run_id": SOURCE_RUN_ID,
                          "source_artifact_id": ARTIFACT_ID,
                          "provider_posts": 0, "new_omc": 0,
                          "truth_access": False}, sort_keys=True))
        return 0
    except (ArenaError, OSError, ValueError, TypeError, KeyError, ImportError) as e:
        print(json.dumps({"status": "STOPPED_NO_EXTERNAL_CONSUMPTION",
                          "reason": str(e)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
