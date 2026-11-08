"""CT03 public-only intake: accepts the custodian's released 4 cuts, never truth.

This validates provenance *claims and content*, not operator separation.
The private world/CSV must be produced under external credentials, and only
its three already-public JSON files may be supplied to this workflow.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT,validate_construction
from scripts.arena_cafe.ct03_world_custody import PUBLIC_SCHEMA
from scripts.arena_cafe.ct03_prospective_lock import PROTOCOL,sha,only
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA="igc-ct03-public-four-cuts-release/1.0"
FILES={"construction.json","world-commitment.json","release-status.json"}

def validate(construction,commitment,status):
    only(commitment,("schema","world_public_id","source_definition_sha256",
        "private_commitment_sha256","protocol_sha256","status",
        "evaluator_boundary","omc_executed","provider_calls"),
        "CT03_INTAKE_PUBLIC_COMMITMENT_FIELDS")
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    require(commitment["schema"]==PUBLIC_SCHEMA and
            commitment["source_definition_sha256"]==digest(PUBLIC_INPUT) and
            sha(commitment["private_commitment_sha256"]) and
            commitment["protocol_sha256"]==digest(protocol) and
            commitment["status"]==
                "WORLD_COMMITTED_NOT_EXECUTED_NO_PUBLIC_CONSTRUCTION_YET" and
            commitment["evaluator_boundary"]==
                "PROCEDURAL_JOB_ISOLATION_NOT_OS_ACL_PROOF" and
            commitment["omc_executed"]==0 and commitment["provider_calls"]==0,
            "CT03_INTAKE_WRONG_CUSTODIAN_COMMITMENT")
    ctx={
        "world":commitment["world_public_id"],
        "source_hash":construction.get("source_snapshot_hash"),
        "condition":"C0"
    }
    validate_construction(ctx,construction)
    expected_source=digest({
        "world_public_id":commitment["world_public_id"],
        "world_commitment_sha256":commitment["private_commitment_sha256"],
        "source_definition_sha256":commitment["source_definition_sha256"],
        "role":"PUBLIC_ONLY_CONSTRUCTION_CUTS"
    })
    require(construction["source_snapshot_hash"]==expected_source,
            "CT03_INTAKE_SOURCE_NOT_DERIVED_FROM_COMMITMENT")
    only(status,("schema","status","construction_sha256",
        "public_world_commitment_sha256","source_snapshot_hash",
        "released_times","reserved_times_released","private_solver_csv_exported",
        "private_source_exported","operator_independence_verified",
        "new_omc_by_release","provider_posts"),
        "CT03_INTAKE_RELEASE_STATUS_FIELDS")
    require(status["schema"]==SCHEMA and
            status["status"]=="PROCEDURAL_CUSTODY_FOUR_CONSTRUCTION_ONLY" and
            status["construction_sha256"]==digest(construction) and
            status["public_world_commitment_sha256"]==digest(commitment) and
            status["source_snapshot_hash"]==expected_source and
            status["released_times"]==[0,1,2,4] and
            status["reserved_times_released"]==[] and
            status["private_solver_csv_exported"] is False and
            status["private_source_exported"] is False and
            status["operator_independence_verified"] is False and
            status["new_omc_by_release"]==0 and
            status["provider_posts"]==0,
            "CT03_INTAKE_NONPUBLIC_RELEASE_OR_MISMATCH")
    return expected_source

def from_b64_environment(out):
    require(not Path(out).exists(),"CT03_INTAKE_REFUSE_OVERWRITE")
    values={}
    for name,key in (
        ("construction.json","CT03_PUBLIC_CONSTRUCTION_B64"),
        ("world-commitment.json","CT03_PUBLIC_COMMITMENT_B64"),
        ("release-status.json","CT03_PUBLIC_RELEASE_STATUS_B64")
    ):
        raw=os.environ.get(key,"")
        require(len(raw)>0 and len(raw)<=16000,
                "CT03_INTAKE_PUBLIC_JSON_MISSING_OR_OVERSIZE")
        try:
            data=base64.b64decode(raw,validate=True)
            require(base64.b64encode(data).decode("ascii")==raw and
                    len(data)<=12000,"CT03_INTAKE_NONCANONICAL_OR_OVERSIZE_BASE64")
            values[name]=json.loads(data.decode("utf-8"))
        except (ValueError,UnicodeError,TypeError) as exc:
            raise ValueError("CT03_INTAKE_PUBLIC_JSON_NOT_VALID") from exc
    source=validate(values["construction.json"],values["world-commitment.json"],
                    values["release-status.json"])
    p=Path(out);p.mkdir(parents=True,exist_ok=False)
    for name,value in values.items():
        (p/name).write_bytes(canonical(value)+b"\n")
    return source

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    source=from_b64_environment(a.out)
    print(json.dumps({"status":"CT03_FOUR_CUTS_PUBLIC_ONLY_ACCEPTED",
                      "source_snapshot_hash":source,
                      "files":sorted(FILES),
                      "custodian_independence_verified":False,
                      "provider_calls":0,"omc":0}))
if __name__=="__main__":
    main()
