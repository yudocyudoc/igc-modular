"""CT03: emit ONLY the five public files accepted by the archival freeze job.

This is an assembly/handoff, not a lock, attestation, custodian, physical run,
provider call or release of t6/t8 evaluator truth. Source bundles with any
extra field fail closed through the original registry/lock validators.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_assemble_entries import assemble
from scripts.arena_cafe.ct03_prospective_lock import only,PROTOCOL
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT
from scripts.arena_cafe.ct03_world_custody import PUBLIC_SCHEMA
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA="igc-ct03-producer-five-file-freeze-handoff/1.0"
FILES=("construction.json","world-commitment.json",
       "D/manifest.json","M/manifest.json","entries.json")

def pack(*,dm_projection,b_projection,construction,commitment,
         d_manifest,m_manifest,out):
    out=Path(out)
    require(not out.exists(),"CT03_HANDOFF_REFUSE_OVERWRITE")
    only(commitment,("schema","world_public_id","source_definition_sha256",
        "private_commitment_sha256","protocol_sha256","status",
        "evaluator_boundary","omc_executed","provider_calls"),
        "CT03_HANDOFF_CUSTODY_FIELDS")
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    require(commitment["schema"]==PUBLIC_SCHEMA and
            commitment["world_public_id"]==construction["world_public_id"] and
            commitment["source_definition_sha256"]==digest(PUBLIC_INPUT) and
            commitment["protocol_sha256"]==digest(protocol) and
            type(commitment["private_commitment_sha256"]) is str and
            commitment["private_commitment_sha256"].startswith("sha256:") and
            len(commitment["private_commitment_sha256"])==71 and
            type(commitment["evaluator_boundary"]) is str and
            commitment["provider_calls"]==0 and
            commitment["omc_executed"]==0,
            "CT03_HANDOFF_PRIVATE_COMMITMENT_OR_PROTOCOL_MISMATCH")
    entries=assemble(dm_projection,b_projection,construction,
                     d_manifest,m_manifest)
    payload={
        "construction.json":construction,
        "world-commitment.json":commitment,
        "D/manifest.json":d_manifest,
        "M/manifest.json":m_manifest,
        "entries.json":entries
    }
    require(set(payload)==set(FILES),"CT03_HANDOFF_EXACT_FIVE_FILES")
    # The output tree has no private manifest, world Modelica, CSV, or G1
    # SQLite; public data plus 13 original slot rows are the ONLY contents.
    out.mkdir(parents=True,exist_ok=False)
    for name,value in payload.items():
        path=out/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(canonical(value)+b"\n")
    return {
        "schema":SCHEMA,
        "status":"FIVE_PUBLIC_PRODUCER_FILES_READY_NOT_LOCKED_NOT_ARCHIVED",
        "world_public_id":construction["world_public_id"],
        "source_snapshot_hash":construction["source_snapshot_hash"],
        "entries_sha256":digest(entries),
        "candidate_count":len(entries["rows"]),
        "file_names":list(FILES),
        "reserved_truth_read":False,"new_omc":0,"provider_calls":0
    }

def main():
    p=argparse.ArgumentParser()
    for flag in ("dm-projection","b-projection","construction","commitment",
                 "d-manifest","m-manifest","out"):
        p.add_argument("--"+flag,required=True,type=Path)
    a=p.parse_args()
    def read(path):return json.loads(path.read_text(encoding="utf-8"))
    result=pack(dm_projection=read(a.dm_projection),
                b_projection=read(a.b_projection),
                construction=read(a.construction),
                commitment=read(a.commitment),
                d_manifest=read(a.d_manifest),
                m_manifest=read(a.m_manifest),out=a.out)
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
