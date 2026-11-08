"""CT03 shared OMC budget, with a D/M-only artifact for the B job.

One custodian world attempt + exactly ten D/M originals + up to six M
revisions + at most two B physical attempts = 19. The B runner never reads
D/M model or feedback: only this narrow outcome/attempt count receipt.
This is a procedural GitHub Actions boundary, not proof of OS isolation.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct_feedback_bridge import require
from scripts.arena_cafe.ct03_dm_feedback_round import SCHEMA as DM_SCHEMA
from scripts.arena_cafe.ct03_m_revision_physical import SCHEMA as REV_SCHEMA

SCHEMA="igc-ct03-same-lot-dm-count-only-budget/1.0"
SHA40=re.compile(r"[0-9a-f]{40}\Z")
ATTEMPTS=re.compile(r"([DM])([1-5]) attempted; GitHub run ([1-9][0-9]*); code ([0-9a-f]{40})\Z")
REV_ATTEMPTS=re.compile(r"M([0-5]) attempted; GitHub run ([1-9][0-9]*); code ([0-9a-f]{40})\Z")
FIELDS={"schema","world_public_id","source_snapshot_hash","github_run_id",
        "github_sha","world_omc_attempts","dm_initial_omc_attempts",
        "m_revision_omc_attempts","b_physical_omc_max","global_omc_max",
        "dm_feedback_sha256","m_revision_outcomes_sha256","new_provider_posts",
        "reserved_truth_read","digest_sha256"}

def verify_receipt(receipt,*,run_id,git_sha,construction=None):
    require(type(receipt) is dict and set(receipt)==FIELDS and
            receipt.get("schema")==SCHEMA and
            type(run_id) is str and run_id.isdigit() and
            type(git_sha) is str and SHA40.fullmatch(git_sha) is not None and
            receipt.get("github_run_id")==run_id and
            receipt.get("github_sha")==git_sha and
            receipt.get("world_omc_attempts")==1 and
            type(receipt.get("dm_initial_omc_attempts")) is int and
            receipt["dm_initial_omc_attempts"]==10 and
            type(receipt.get("m_revision_omc_attempts")) is int and
            0<=receipt["m_revision_omc_attempts"]<=6 and
            receipt.get("b_physical_omc_max")==2 and
            receipt.get("global_omc_max")==19 and
            receipt.get("new_provider_posts")==0 and
            receipt.get("reserved_truth_read") is False and
            type(receipt.get("world_public_id")) is str and
            type(receipt.get("source_snapshot_hash")) is str and
            receipt["source_snapshot_hash"].startswith("sha256:") and
            1+10+receipt["m_revision_omc_attempts"]+2<=19 and
            digest({k:v for k,v in receipt.items()
                    if k!="digest_sha256"})==receipt["digest_sha256"],
            "CT03_LOT_DM_COUNT_ONLY_BUDGET_INVALID_OR_CROSS_RUN")
    if construction is not None:
        require(type(construction) is dict and
                construction.get("world_public_id")==receipt["world_public_id"] and
                construction.get("source_snapshot_hash")==receipt["source_snapshot_hash"] and
                construction.get("condition_id")=="C0" and
                type(construction.get("observations")) is list and
                len(construction["observations"])==4 and
                all(type(x) is dict and x.get("time")==t
                    for x,t in zip(construction["observations"],(0,1,2,4))),
                "CT03_LOT_B_OTHER_WORLD_OR_PUBLIC_SOURCE_MISMATCH")
    return 11+receipt["m_revision_omc_attempts"]

def issue(*,dm_report,revisions,initial_attempt_log,m_revision_attempt_log,
          run_id,git_sha):
    require(type(run_id) is str and re.fullmatch(r"[1-9][0-9]*",run_id) and
            type(git_sha) is str and SHA40.fullmatch(git_sha),
            "CT03_LOT_RUN_ID_SHA_INVALID")
    require(type(dm_report) is dict and dm_report.get("schema")==DM_SCHEMA and
            len(dm_report.get("rows",[]))==12 and
            dm_report.get("reserved_truth_read") is False and
            type(revisions) is dict and revisions.get("schema")==REV_SCHEMA and
            revisions.get("world_public_id")==dm_report.get("world_public_id") and
            revisions.get("source_snapshot_hash")==dm_report.get("source_snapshot_hash") and
            revisions.get("dm_feedback_sha256")==digest(dm_report) and
            revisions.get("run_id")==run_id and
            revisions.get("git_sha")==git_sha and
            revisions.get("reserved_truth_read") is False and
            revisions.get("provider_posts")==0 and
            revisions.get("revised_count")==len(revisions.get("outcomes",{})) and
            revisions.get("revised_count")==len(revisions.get("receipts",{})) and
            revisions["revised_count"]==
              sum(r["arm"]=="M" and r["decision"]["status"]=="REVISED"
                  for r in dm_report["rows"]),
            "CT03_LOT_DM_OR_M_REVISED_REPORT_MISMATCH")
    rows=Path(initial_attempt_log).read_text(encoding="utf-8").splitlines()
    expected=[(arm,str(i)) for arm in "DM" for i in range(1,6)]
    parsed=[ATTEMPTS.fullmatch(line) for line in rows]
    require(len(parsed)==10 and all(parsed) and
            [(x[1],x[2]) for x in parsed]==expected and
            all(x[3]==run_id and x[4]==git_sha for x in parsed),
            "CT03_LOT_TEN_INITIALS_ONE_SAME_RUN_REQUIRED")
    p=Path(m_revision_attempt_log)
    observed=p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    checked=[REV_ATTEMPTS.fullmatch(line) for line in observed]
    selected=[str(r["index"]) for r in dm_report["rows"]
              if r["arm"]=="M" and r["decision"]["status"]=="REVISED"]
    require(len(checked)==len(selected)<=6 and all(checked) and
            [x[1] for x in checked]==selected and
            all(x[2]==run_id and x[3]==git_sha for x in checked),
            "CT03_LOT_M_REVISED_ATTEMPTS_NOT_EXACT")
    body={
        "schema":SCHEMA,"world_public_id":dm_report["world_public_id"],
        "source_snapshot_hash":dm_report["source_snapshot_hash"],
        "github_run_id":run_id,"github_sha":git_sha,
        "world_omc_attempts":1,"dm_initial_omc_attempts":10,
        "m_revision_omc_attempts":len(selected),
        "b_physical_omc_max":2,"global_omc_max":19,
        "dm_feedback_sha256":digest(dm_report),
        "m_revision_outcomes_sha256":digest(revisions),
        "new_provider_posts":0,"reserved_truth_read":False
    }
    receipt={**body,"digest_sha256":digest(body)}
    verify_receipt(receipt,run_id=run_id,git_sha=git_sha)
    return receipt

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="mode",required=True)
    gen=sub.add_parser("issue")
    for n in ("dm-report","m-revision-report","initial-attempt-log",
              "m-revision-attempt-log","out"):
        gen.add_argument("--"+n,required=True,type=Path)
    val=sub.add_parser("verify")
    val.add_argument("--receipt",required=True,type=Path)
    val.add_argument("--construction",required=True,type=Path)
    for x in (gen,val):
        x.add_argument("--run-id",required=True)
        x.add_argument("--git-sha",required=True)
    a=p.parse_args()
    if a.mode=="verify":
        r=json.loads(a.receipt.read_text(encoding="utf-8"))
        construction=json.loads(a.construction.read_text(encoding="utf-8"))
        before=verify_receipt(r,run_id=a.run_id,git_sha=a.git_sha,
                              construction=construction)
        print(json.dumps({"status":"CT03_DM_COUNT_ONLY_BUDGET_VERIFIED",
                          "omc_before_B":before,"max_new_omc":19}))
        return
    require(not a.out.exists(),"CT03_LOT_DM_BUDGET_REFUSE_OVERWRITE")
    def load(p):return json.loads(p.read_text(encoding="utf-8"))
    r=issue(dm_report=load(a.dm_report),revisions=load(a.m_revision_report),
            initial_attempt_log=a.initial_attempt_log,
            m_revision_attempt_log=a.m_revision_attempt_log,
            run_id=a.run_id,git_sha=a.git_sha)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes(canonical(r)+b"\n")
    print(json.dumps({"status":"CT03_DM_COUNT_ONLY_BUDGET_READY",
                      "m_revisions":r["m_revision_omc_attempts"],
                      "max_new_omc":19,"provider_calls":0}))

if __name__=="__main__":
    main()
