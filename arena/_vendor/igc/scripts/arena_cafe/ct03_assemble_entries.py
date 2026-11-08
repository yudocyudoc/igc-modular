"""Join twelve own D/M and one own Buffalo native into 13 prospective slots.

This is ONLY an entries assembler, not a lock, physical-run authenticator or
custodian. The existing separate GitHub Actions freeze workflow must archive
the final byte-lock before any evaluator can access held-out t6/t8. All rows
are checked by the unchanged ct03_prospective_lock registry and validator.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_prospective_lock import (
    INPUT_SCHEMA,registry,validate_row
)
from scripts.arena_cafe.ct03_dm_lock_projection import SCHEMA as DM_SCHEMA
from scripts.arena_cafe.ct03_b_lock_projection import SCHEMA as B_SCHEMA
from scripts.arena_cafe.ct03_public import validate_construction
from scripts.arena_cafe.ct_feedback_bridge import require

def assemble(dm_projection,b_projection,construction,d_manifest,m_manifest):
    world=construction["world_public_id"]
    source=construction["source_snapshot_hash"]
    validate_construction({
        "world":world,"source_hash":source,"condition":"C0"
    },construction)
    require(type(dm_projection) is dict and
            dm_projection.get("schema")==DM_SCHEMA and
            dm_projection.get("status")==
                "TWELVE_D_M_LOCK_ROWS_VALID_B_NOT_INCLUDED_NOT_SEALED" and
            dm_projection.get("candidate_count")==12 and
            len(dm_projection.get("rows",[]))==12 and
            dm_projection.get("world_public_id")==world and
            dm_projection.get("source_snapshot_hash")==source and
            dm_projection.get("reserved_world_truth_read") is False and
            dm_projection.get("new_provider_calls")==0 and
            type(b_projection) is dict and
            b_projection.get("schema")==B_SCHEMA and
            b_projection.get("status")==
                "B_THIRTEENTH_SLOT_VALID_NOT_ARCHIVED_OR_SCORED" and
            b_projection.get("world_public_id")==world and
            b_projection.get("source_snapshot_hash")==source and
            b_projection.get("reserved_truth_read") is False and
            b_projection.get("new_provider_calls")==0,
            "CT03_ASSEMBLY_D_M_B_PUBLIC_SCOPE_OR_STATUS_INCOMPATIBLE")
    expected=registry(d_manifest,m_manifest)
    rows=[*dm_projection["rows"],b_projection["row"]]
    seen=set()
    for row in rows:
        key=validate_row(row,expected,world)
        require(key not in seen,"CT03_ASSEMBLY_DUPLICATE_SLOT")
        seen.add(key)
    require(len(rows)==13 and seen==set(expected) and
            sum(r["arm"]=="D" for r in rows)==6 and
            sum(r["arm"]=="M" for r in rows)==6 and
            sum(r["arm"]=="B" for r in rows)==1,
            "CT03_ASSEMBLY_EXACT_THIRTEEN_ORIGINALS_REQUIRED")
    return {
        "schema":INPUT_SCHEMA,
        "world_public_id":world,"source_snapshot_hash":source,
        "condition_id":"C0",
        "rows":sorted(rows,key=lambda r:(r["arm"],r["candidate_id"]))
    }

def main():
    p=argparse.ArgumentParser()
    for name in ("dm-projection","b-projection","construction",
                 "d-manifest","m-manifest","out"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    require(not args.out.exists(),"CT03_ASSEMBLY_ENTRIES_REFUSE_OVERWRITE")
    def load(path):return json.loads(path.read_text(encoding="utf-8"))
    entries=assemble(load(args.dm_projection),load(args.b_projection),
                     load(args.construction),load(args.d_manifest),
                     load(args.m_manifest))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(entries)+b"\n")
    print(json.dumps({
        "status":"THIRTEEN_ENTRIES_READY_NOT_SEALED_OR_ARCHIVED",
        "candidate_count":len(entries["rows"]),
        "entries_sha256":digest(entries),
        "new_omc":0,"provider_posts":0,
        "truth_revealed":False
    }))

if __name__=="__main__":
    main()
