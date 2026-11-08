"""CT03 original Buffalo native -> G1 translation status -> own ledger feedback.

Only AFTER the existing original Engine.generate live result has been retrieved
from an actual provider run and bound to its own receipt by the runner.
No provider call, no OMC, no evaluator-private world, no model correction.
A native G1 block is feedback, not grounds to silently remove B from 13 slots.
Any Modelica translation is conditional and its delivery observation operator
must be grounded separately before scientific G2/prediction.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timedelta
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_b_native_to_modelica import generate, TranslationBlocked
from scripts.arena_cafe.e02_b_feedback import _model_sha
from scripts.arena_cafe.ct03_b_visible import view
from scripts.arena_cafe.ct_feedback_bridge import (
    make_context,record_feedback,b_review_envelope,require
)

SCHEMA="igc-ct03-b-original-own-g1-ledger-and-revision-packet/1.0"
PIN="5199f7b45f3a7ae4a773cb0dd8542940aabe9edc"
TRANSPORT="CLOUDFLARE_WORKERS_AI_DIRECT_REST_JSON_SCHEMA"

def validate(original,receipt,construction):
    world=construction["world_public_id"]
    source=construction["source_snapshot_hash"]
    view(construction,world=world,round_kind="initial")
    ctx=make_context(experiment="CT03",world=world,round_id="R0",
                     arm="B",condition="C0",source_hash=source)
    require(type(original) is dict and type(original.get("model")) is dict and
            type(original["model"].get("variables")) is list and
            type(original["model"].get("relationships")) is list and
            type(receipt) is dict and
            receipt.get("case_id")=="CT-03" and
            receipt.get("world_public_id")==world and
            receipt.get("condition_id")=="C0" and
            receipt.get("source_snapshot_hash")==source and
            receipt.get("round_kind")=="initial" and
            receipt.get("status")=="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED" and
            receipt.get("mode")=="live" and
            receipt.get("model_returned") is True and
            receipt.get("provider_calls")==1 and
            receipt.get("proxy_requests")==1 and
            receipt.get("upstream_sha")==PIN and
            receipt.get("upstream_source_modified") is False and
            receipt.get("horizon_matches_case") is True and
            receipt.get("output_horizon_hours")==8 and
            receipt.get("transport")==TRANSPORT and
            receipt.get("result_sha256")==_model_sha(original),
            "CT03_B_ORIGINAL_LIVE_NATIVE_OR_RECEIPT_UNVERIFIED")
    return ctx

def build(*,original:dict,receipt:dict,construction:dict,
          recorded_at:str,out:Path):
    out=Path(out)
    require(not out.exists(),"CT03_B_OWN_REFUSE_OVERWRITE")
    ctx=validate(original,receipt,construction)
    stamp=datetime.fromisoformat(recorded_at.replace("Z","+00:00"))
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            "CT03_B_OWN_AWARE_TIMESTAMP_REQUIRED")
    try:
        model_name,modelica,translation=generate(original)
        g1="NATIVE_TRANSLATION_CONDITIONAL_NEEDS_G2_AND_OBSERVABLE"
        blocked_reason=None
    except TranslationBlocked as error:
        model_name,modelica,translation=None,None,None
        g1="G1_TRANSLATION_BLOCKED_ORIGINAL_UNCHANGED"
        blocked_reason=str(error)
    parent=receipt["result_sha256"]
    diagnostic={
        "arm":"B","condition":"C0",
        "source_hash":ctx["source_hash"],"parent_hash":parent,
        "evidence":"G1",
        "own_evidence_only":True,"no_future_truth":True,
        "observations":[],
        "G1_status":g1,"G1_translation_block_reason":blocked_reason,
        "native_provider_receipt_sha256":digest(receipt),
        "native_model_sha256":parent,
        "scope":"ORIGINAL_NATIVE_B_G1_ONLY_NO_MODEL_REPAIR_NO_HELDOUT",
    }
    # Do not write even a ledger entry until source/provider parent and scope
    # have been checked. An unsupported translation is a legitimate G1 result.
    out.mkdir(parents=True,exist_ok=False)
    ledger=out/"b-own-feedback-ledger.sqlite"
    record_feedback(ledger,ctx,parent_hash=parent,
                    diagnostic=diagnostic,recorded_at=stamp.isoformat())
    phase=b_review_envelope(ledger,ctx,original_native=original,
                            authenticated_receipt=receipt,
                            as_known_at=(stamp+timedelta(seconds=1)).isoformat())
    require(phase["status"]=="READY_NOT_SENT_RECEIPT_REQUIRES_EXTERNAL_BYTE_VERIFICATION"
            and phase["parent_hash"]==parent,
            "CT03_B_OWN_REVISION_NOT_READY_FOR_OWN_PARENT")
    packet=phase["revision_feedback_packet"]
    if modelica is not None:
        (out/"conditional-translated.mo").write_text(
            modelica,encoding="utf-8",newline="\n")
        (out/"conditional-translation.json").write_bytes(
            canonical(translation)+b"\n")
    # A translation does not certify a delivery stock/flow observable.
    result={
        "schema":SCHEMA,
        "status":"B_OWN_G1_RETRIEVED_AND_REVISION_PACKET_PREPARED_NO_PROVIDER_CALL",
        "world_public_id":ctx["world"],
        "source_snapshot_hash":ctx["source_hash"],
        "parent_native_sha256":parent,
        "provider_initial_calls_attested_by_receipt":1,
        "provider_calls_by_this_adapter":0,
        "new_omc_by_this_adapter":0,
        "G1_status":g1,
        "G1_block_reason":blocked_reason,
        "own_diagnostic_sha256":digest(diagnostic),
        "retrieved_before_policy":phase["retrieved_before_policy"],
        "revision_packet_sha256":digest(packet),
        "revision_packet_status":"PREPARED_NOT_SENT",
        "translated_model_name":model_name,
        "modelica_translation_provisional":modelica is not None,
        "native_delivery_observation_operator_verified":False,
        "physical_B_G2_or_G3":"NOT_EXECUTED",
        "heldout_observations_read":False,
        "cross_arm_feedback_read":False,
        "source_model_rewritten":False,
    }
    (out/"own-g1-diagnostic.json").write_bytes(canonical(diagnostic)+b"\n")
    (out/"own-revision-packet.json").write_bytes(canonical(packet)+b"\n")
    (out/"status.json").write_bytes(canonical(result)+b"\n")
    return result

def main():
    p=argparse.ArgumentParser()
    for arg in ("native","receipt","construction","out"):
        p.add_argument("--"+arg,type=Path,required=True)
    p.add_argument("--recorded-at",required=True)
    a=p.parse_args()
    def read(x):return json.loads(x.read_text(encoding="utf-8"))
    r=build(original=read(a.native),receipt=read(a.receipt),
            construction=read(a.construction),recorded_at=a.recorded_at,
            out=a.out)
    print(json.dumps({"status":r["status"],"G1":r["G1_status"],
                      "provider_calls":0,"new_omc":0}))

if __name__=="__main__":
    main()
