"""CT-02 Buffalo revision handoff: ledger -> own feedback packet -> original runner.

No call to engine or provider; this only exports the supported feedback which
the new CT-03 runner checks again against its exact own native parent receipt.
Mock, absent, different-world or unauthenticated historical parents fail closed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical
from scripts.arena_cafe.ct_feedback_bridge import (
    b_review_envelope, require,
)

SCHEMA="igc-ct03-b-own-feedback/1.0"


def prepare(db, context, native, receipt, at):
    stage=b_review_envelope(db,context,original_native=native,
                             authenticated_receipt=receipt,as_known_at=at)
    require(stage["status"]=="READY_NOT_SENT_RECEIPT_REQUIRES_EXTERNAL_BYTE_VERIFICATION",
            "CT03_B_REVIEW_NOT_READY:"+stage["status"])
    packet=stage["revision_feedback_packet"]
    require(packet["schema"]==SCHEMA and
            packet["parent_result_sha256"]==stage["parent_hash"] and
            packet["own_diagnostic_sha256"] and
            packet["retrieved_before_policy"]["item_id"] and
            packet["retrieved_before_policy"]["projection_hash"] and
            stage["provider_calls"]==0 and stage["new_omc"]==0,
            "CT03_B_LEDGER_RETRIEVAL_NOT_BINDING")
    return packet


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,required=True)
    for name in ("context","native","receipt"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--as-known-at",required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    require(not args.out.exists(),"CT03_B_FEEDBACK_PACKET_REFUSE_OVERWRITE")
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))
    packet=prepare(args.ledger,load(args.context),load(args.native),
                   load(args.receipt),args.as_known_at)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(packet)+b"\n")
    print(json.dumps({"status":"CT03_B_OWN_FEEDBACK_PACKET_READY_NOT_SENT",
                      "parent":packet["parent_result_sha256"],
                      "provider_calls":0,"new_omc":0}))


if __name__=="__main__":
    main()
