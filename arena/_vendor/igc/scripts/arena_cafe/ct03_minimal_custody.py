"""CT-03 procedural custody: release ONLY t0,t1,t2,t4 from a private OMC trace.

Run this under a distinct custodian account/workspace, outside producer CI.
The producer receives ONLY the new public-construction JSON and commitment;
world configuration, native source, original trace and reserved t6/t8 remain
in custodian storage. This code cannot establish OS/account independence.
No OMC or provider is executed by this CLI. No hidden scores are computed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT, OBS_SCHEMA, validate_construction
from scripts.arena_cafe.ct03_world_custody import PUBLIC_SCHEMA, SCHEMA as PRIVATE_SCHEMA
from scripts.arena_cafe.ct03_prospective_lock import PROTOCOL
from scripts.arena_cafe.ct03_m_construction_diagnostic import _sample, sha_bytes
from scripts.arena_cafe.ct02_minimal_batch import _full_end
from scripts.arena_cafe.ct_feedback_bridge import require


def distinct(producer_root: Path, private_dir: Path, public_out: Path):
    p = Path(producer_root).resolve(strict=True)
    private = Path(private_dir).resolve(strict=True)
    published = Path(public_out).resolve(strict=False)
    require(p.is_dir() and private.is_dir() and
            p != private and p not in private.parents and
            private not in p.parents and
            private != published and private not in published.parents and
            published not in private.parents,
            "CT03_PRIVATE_WORLD_INSIDE_PRODUCER_OR_PUBLIC_DIR")
    return private


def release(*, producer_root: Path, private_dir: Path, public_out: Path,
            commitment: dict):
    """No private values, solver CSV or logs ever written to the public output."""
    private = distinct(producer_root, private_dir, public_out)
    require(not Path(public_out).exists(), "CT03_PUBLIC_RELEASE_REFUSE_OVERWRITE")
    manifest = json.loads((private/"private-manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    require(type(commitment) is dict and
            commitment.get("schema") == PUBLIC_SCHEMA and
            type(manifest) is dict and manifest.get("schema") == PRIVATE_SCHEMA and
            commitment.get("private_commitment_sha256") == digest(manifest) and
            commitment.get("protocol_sha256") ==
                manifest["world_private_config"]["protocol_sha256"] == digest(protocol) and
            commitment.get("world_public_id") ==
                manifest["world_private_config"]["world_public_id"] and
            commitment.get("source_definition_sha256") ==
                manifest.get("source_definition_sha256") == digest(PUBLIC_INPUT) and
            manifest["modelica_sha256"] ==
                sha_bytes((private/"private_world.mo").read_bytes()) and
            manifest["script_sha256"] ==
                sha_bytes((private/"simulate.mos").read_bytes()),
            "CT03_CUSTODIAN_PRIVATE_MANIFEST_OR_COMMITMENT_MISMATCH")
    trace = private/"sealed_world_res.csv"
    log = private/"world-omc.log"
    require(trace.is_file() and log.is_file() and
            ("1.26.5" in log.read_text(encoding="utf-8",errors="replace")),
            "CT03_PRIVATE_OMC_OUTPUT_OR_VERSION_MISSING")
    _full_end(trace, "deliveredTotal")
    samples,count = _sample(trace.read_bytes(), "deliveredTotal")
    require(len(samples) == 4 and count >= 5,
            "CT03_PRIVATE_FOUR_CONSTRUCTION_POINTS_REQUIRED")
    source = digest({
        "world_public_id": commitment["world_public_id"],
        "world_commitment_sha256": commitment["private_commitment_sha256"],
        "source_definition_sha256": commitment["source_definition_sha256"],
        "role": "PUBLIC_ONLY_CONSTRUCTION_CUTS",
    })
    construction = {
        "schema": OBS_SCHEMA,
        "source_snapshot_hash": source,
        "world_public_id": commitment["world_public_id"],
        "condition_id": "C0", "time_unit": "hours",
        "observable": "cumulative_delivered",
        "observations": [{"time": t, "delivered": samples[float(t)]}
                         for t in (0, 1, 2, 4)],
    }
    context = {"source_hash": source, "world": commitment["world_public_id"],
               "condition": "C0"}
    validate_construction(context, construction)
    # Public output is created ONLY after all private checks succeed.
    dest = Path(public_out)
    dest.mkdir(parents=True, exist_ok=False)
    (dest/"construction.json").write_bytes(canonical(construction)+b"\n")
    (dest/"world-commitment.json").write_bytes(canonical(commitment)+b"\n")
    (dest/"release-status.json").write_bytes(canonical({
        "schema": "igc-ct03-public-four-cuts-release/1.0",
        "status": "PROCEDURAL_CUSTODY_FOUR_CONSTRUCTION_ONLY",
        "construction_sha256": digest(construction),
        "public_world_commitment_sha256": digest(commitment),
        "source_snapshot_hash": source,
        "released_times": [0,1,2,4],
        "reserved_times_released": [],
        "private_solver_csv_exported": False,
        "private_source_exported": False,
        "operator_independence_verified": False,
        "new_omc_by_release": 0, "provider_posts": 0,
    })+b"\n")
    return construction


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--producer-root", required=True, type=Path)
    p.add_argument("--private-dir", required=True, type=Path)
    p.add_argument("--public-out", required=True, type=Path)
    p.add_argument("--commitment", required=True, type=Path)
    args = p.parse_args()
    result = release(
        producer_root=args.producer_root, private_dir=args.private_dir,
        public_out=args.public_out,
        commitment=json.loads(args.commitment.read_text(encoding="utf-8")))
    print(json.dumps({"status":"PUBLIC_FOUR_CUTS_ONLY", "source":result["source_snapshot_hash"],
                      "released_times":[0,1,2,4], "reserved_released":False,
                      "new_omc":0,"provider_posts":0}))


if __name__=="__main__":
    main()
