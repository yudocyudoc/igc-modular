"""CT-03 minimal evaluator: consume a procedural archived lock BEFORE private t6/t8.

Only the custodian (never producers) runs this after the GitHub lock artifact is
verified by a human and producer jobs are complete. No RSA/archive service.
This is procedural custody, NOT cryptographic certification of independent
operator control or native G2. No solver, model fit or provider.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from statistics import median

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_cafe.ct03_public import validate_construction
from scripts.arena_cafe.ct03_world_custody import SCHEMA as PRIVATE_SCHEMA
from scripts.arena_cafe.ct03_prospective_lock import verify_locked
from scripts.arena_cafe.ct03_minimal_custody import distinct
from scripts.arena_cafe.ct02_minimal_batch import _full_end
from scripts.arena_cafe.ct_feedback_bridge import require

SCHEMA = "igc-ct03-paired-prospective-evaluation/1.0"
FREEZE_SCHEMA = "igc-ct03-procedural-archive-ack/1.0"


def _ack(archive, lock):
    """Human attestation, NOT a self-authenticating timestamp or GitHub API."""
    require(type(archive) is dict and set(archive) == {
        "schema","lock_sha256","github_run_id","github_artifact_id",
        "frozen_code_sha","verified_by_custodian","archived_before_reveal",
        "producer_write_disabled","custody_scope",
    }, "CT03_SCORE_ARCHIVE_ACK_FIELDS")
    require(archive["schema"] == FREEZE_SCHEMA and
            archive["lock_sha256"] == lock["lock_sha256"] and
            type(archive["github_run_id"]) is int and archive["github_run_id"] > 0 and
            type(archive["github_artifact_id"]) is int and archive["github_artifact_id"] > 0 and
            type(archive["frozen_code_sha"]) is str and
            re.fullmatch("[0-9a-f]{40}", archive["frozen_code_sha"]) and
            type(archive["verified_by_custodian"]) is str and
            3 <= len(archive["verified_by_custodian"]) <= 120 and
            archive["archived_before_reveal"] is True and
            archive["producer_write_disabled"] is True and
            archive["custody_scope"] == "PROCEDURAL_HUMAN_NO_EXTERNAL_SIGNER",
            "CT03_SCORE_LOCK_NOT_PROSPECTIVELY_ARCHIVED")
    return archive


def _reserved(csv_file):
    """Read withheld samples only after the lock and archive ACK are checked."""
    _full_end(csv_file, "deliveredTotal")
    sampled = {}
    with Path(csv_file).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames.count("deliveredTotal") == 1 and
                reader.fieldnames.count("time") == 1,
                "CT03_SCORE_UNRECOGNIZED_PRIVATE_CSV")
        for row in reader:
            t=float(row["time"])
            v=float(row["deliveredTotal"])
            require(math.isfinite(t) and math.isfinite(v) and
                    -1e-8 <= v <= 3.4 + 1e-8,
                    "CT03_SCORE_INVALID_WORLD_CONSERVATION")
            for point in (6,8):
                if abs(t-point) <= 1e-8:
                    if point in sampled:
                        require(abs(sampled[point]-v)<1e-8,
                                "CT03_SCORE_CONFLICTING_RESERVED_SAMPLE")
                    sampled[point]=v
    require(set(sampled)=={6,8} and sampled[8]>=sampled[6]-1e-8,
            "CT03_SCORE_RESERVED_TIMES_MISSING_OR_DECREASING")
    return sampled


def _mae(points, truth):
    if type(points) is not list or len(points) != 2:
        return None
    if any(type(p) is not dict or set(p)!={"time","delivered"} for p in points):
        return None
    if [p["time"] for p in points] != [6,8]:
        return None
    errors=[abs(p["delivered"]-truth[t]) for t,p in zip((6,8),points)]
    return {"t6":errors[0],"t8":errors[1],"mae":sum(errors)/2}


def _group_summary(rows, arm):
    groups={}
    for row in rows:
        if row["arm"]!=arm:
            continue
        groups.setdefault(row["material_group"],[]).append(row["delta_mae"])
    summary=[]
    for ident, values in sorted(groups.items()):
        eligible=[x for x in values if x is not None]
        summary.append({"group":ident,"slots":len(values),
                        "paired_available":len(eligible),
                        "median_delta":median(eligible) if eligible else None})
    expected={"D":6,"M":3,"B":1}[arm]
    require(len(summary)==expected,"CT03_SCORE_MISSING_MATERIAL_GROUP")
    per_group=[g["median_delta"] for g in summary if g["median_delta"] is not None]
    return {"total_groups":expected,"groups_with_paired_predictions":len(per_group),
            "median_of_group_medians":median(per_group) if per_group else None,
            "complete":len(per_group)==expected,"groups":summary}


def evaluate(*, lock, archive, construction, commitment, producer_root,
             private_dir, out: Path):
    # No access to the private workspace until all public preconditions pass.
    verify_locked(lock)
    _ack(archive, lock)
    require(lock["status"] == "BYTE_LOCK_ONLY_NOT_INDEPENDENT_EXECUTION_PROOF" and
            lock["candidate_count"] == 13 and len(lock["rows"]) == 13 and
            lock["construction_sha256"] == digest(construction) and
            lock["world_commitment_sha256"] == commitment["private_commitment_sha256"] and
            lock["world_public_id"] == construction["world_public_id"] ==
                  commitment["world_public_id"],
            "CT03_SCORE_LOCK_PUBLIC_SCOPE_MISMATCH")
    context={"source_hash":construction["source_snapshot_hash"],
             "world":construction["world_public_id"],"condition":"C0"}
    validate_construction(context,construction)
    require(any(x["initial"]["status"]=="PREDICTED" or
                x["final"]["status"]=="PREDICTED" for x in lock["rows"]),
            "CT03_SCORE_ZERO_ADMISSIBLE_PREDICTIONS_STOP")
    # Fail before any private truth read when a result already exists.
    require(not Path(out).exists(),"CT03_SCORE_REFUSE_OVERWRITE")
    private=distinct(producer_root,private_dir,out)
    manifest=json.loads((private/"private-manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema")==PRIVATE_SCHEMA and
            digest(manifest)==lock["world_commitment_sha256"],
            "CT03_SCORE_PRIVATE_WORLD_DIFFERENT_FROM_LOCK")
    truth=_reserved(private/"sealed_world_res.csv")
    obs={o["time"]:o["delivered"] for o in construction["observations"]}
    y2,y4=obs[2],obs[4]
    slope=max(0,(y4-y2)/2)
    baselines = {
        "persist_y4": {t: y4 for t in (6,8)},
        "linear_y4_slope_clamped_mass": {
            t: min(3.4,max(y4,y4+slope*(t-4))) for t in (6,8)},
    }
    rows=[]
    for item in lock["rows"]:
        initial=_mae(item["initial"].get("forecast"),truth) if item["initial"]["status"]=="PREDICTED" else None
        final=_mae(item["final"].get("forecast"),truth) if item["final"]["status"]=="PREDICTED" else None
        delta=final["mae"]-initial["mae"] if initial is not None and final is not None else None
        rows.append({"arm":item["arm"],"candidate_id":item["candidate_id"],
                     "material_group":item["material_group"],
                     "initial_status":item["initial"]["status"],
                     "final_status":item["final"]["status"],
                     "decision":item["decision"]["status"],
                     "initial_error":initial,"final_error":final,
                     "delta_mae":delta,
                     "pair_comparable":delta is not None})
    result={
        "schema":SCHEMA,
        "status":"PROCEDURAL_PAIRED_EVALUATION_NO_INDEPENDENT_RUNNER_ATTESTATION",
        "world_public_id":lock["world_public_id"],
        "lock_sha256":lock["lock_sha256"],
        "archive_record_sha256":digest(archive),
        "custody_limit":"HUMAN_ACK_AND_SEPARATE_WORKSPACE_NOT_OS_ACL_PROOF",
        "true_reserved":[{"time":t,"delivered":truth[t]} for t in (6,8)],
        "baselines":{name:_mae([{"time":t,"delivered":pred[t]} for t in (6,8)],truth)
                     for name,pred in baselines.items()},
        "candidate_denominator":13,
        "paired_available":sum(r["pair_comparable"] for r in rows),
        "failures_kept_in_denominator":sum(not r["pair_comparable"] for r in rows),
        "rows":rows,
        "material_groups":{arm:_group_summary(rows,arm) for arm in ("D","M","B")},
        "scientific_scope":"SYNTHETIC_INTRAFAMILY_SINGLE_WORLD",
        "provider_posts_by_evaluator":0,"new_omc_by_evaluator":0,
    }
    require(not Path(out).exists(),"CT03_SCORE_REFUSE_OVERWRITE")
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    with Path(out).open("x", encoding="utf-8") as stream:
        stream.write(canonical(result).decode("utf-8")+"\n")
    return result


def main():
    p=argparse.ArgumentParser()
    for name in ("lock","archive-record","construction","commitment",
                 "producer-root","private-dir","out"):
        p.add_argument("--"+name,required=True,type=Path)
    a=p.parse_args()
    def read(path):return json.loads(path.read_text(encoding="utf-8"))
    result=evaluate(lock=read(a.lock),archive=read(a.archive_record),
                    construction=read(a.construction),commitment=read(a.commitment),
                    producer_root=a.producer_root,private_dir=a.private_dir,out=a.out)
    print(json.dumps({"status":result["status"],
                      "denominator":result["candidate_denominator"],
                      "paired":result["paired_available"],"new_omc":0,
                      "provider_posts":0}))


if __name__=="__main__":
    main()
