"""CT-03 Buffalo native G1 -> unambiguous cumulative-delivery OMC plan.

This is NOT a converter change: it calls the preexisting strict original
Buffalo native-to-Modelica translator. The observable must already be an
explicit, zero-initial, terminal material stock denominated in items, with a
delivery-name in the native original. No selection by fitting against public
or withheld observations, no repairs, no solver or provider calls.

Ambiguity, absence, or a G1 translation failure blocks this candidate.
Only a later independent OMC run/receipt may convert a plan to a prediction.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_b_native_to_modelica import generate,TranslationBlocked,ident
from scripts.arena_cafe.ct03_b_own_feedback import validate as validate_initial
from scripts.arena_cafe.e02_b_feedback import _model_sha
from scripts.arena_cafe.ct_feedback_bridge import require
from scripts.arena_cafe.ct03_m_construction_diagnostic import sha_bytes

SCHEMA="igc-ct03-b-original-unambiguous-delivery-port-physical-plan/1.0"
NAMES=re.compile(r"(?:^|[\s_-])(delivered|deliveries|delivery)(?:$|[\s_-])",re.I)

def operator(native:dict):
    """Only the original Buffalo native semantics may establish this port."""
    model=native["model"]
    variables=model["variables"]
    stocks=[v for v in variables if v.get("type")=="stock"]
    flows={v["name"] for v in variables if v.get("type")=="flow"}
    candidates=[]
    for v in stocks:
        if not NAMES.search(v["name"]):
            continue
        require(v.get("equation") in ("0","0.0",0,0.0) and
                v.get("units","").strip().lower() in
                ("items","item","work items") and
                isinstance(v.get("inflows"),list) and
                len(v["inflows"])==1 and v["inflows"][0] in flows and
                v.get("outflows")==[],
                "CT03_B_DELIVERY_CANNOT_BE_GROUNDED_IN_TERMINAL_STOCK")
        candidates.append(v)
    require(len(candidates)==1,
            "CT03_B_MISSING_OR_AMBIGUOUS_CUMULATIVE_DELIVERY_STOCK")
    chosen=candidates[0]
    # Other terminal sinks could mean there is unaccounted material,
    # e.g. dropped work; fail closed rather than attributing it to delivery.
    for v in stocks:
        if v is chosen:
            continue
        if v.get("inflows") and not v.get("outflows"):
            require(False,"CT03_B_ALTERNATIVE_TERMINAL_STOCK_UNRESOLVED")
    return {
        "quantity":"cumulative_delivered",
        "native_stock_name":chosen["name"],
        "modelica_csv_column":ident(chosen["name"]),
        "material_inflow_name":chosen["inflows"][0],
        "initial_value":0,"quantity_unit":"items",
        "operator":"DIRECT_UNMODIFIED_NATIVE_TERMINAL_STOCK",
        "no_hidden_truth_or_fit":True
    }

def validate_revision_live(native,receipt,construction,b_feedback,provenance):
    """Require the *original* Buffalo currentModel plus its own recovered G1.

    No provider call is performed. The revision receipt must come from the
    original native runner's second round, not a forged initial receipt.
    """
    require(type(provenance) is dict and
            set(provenance)=={"parent_native","parent_receipt","packet"},
            "CT03_B_REVISION_PROVENANCE_REQUIRED")
    parent,origin,packet=(provenance[k] for k in
                          ("parent_native","parent_receipt","packet"))
    validate_initial(parent,origin,construction)
    require(type(packet) is dict and
            packet.get("schema")=="igc-ct03-b-own-feedback/1.0" and
            packet.get("arm")=="B" and
            packet.get("world_public_id")==construction["world_public_id"] and
            packet.get("condition_id")=="C0" and
            packet.get("source_snapshot_hash")==construction["source_snapshot_hash"] and
            packet.get("parent_result_sha256")==origin["result_sha256"] and
            packet.get("own_diagnostic_sha256")==
                b_feedback.get("own_diagnostic_sha256") and
            packet.get("own_diagnostic_sha256")==
                digest(packet.get("own_diagnostic")) and
            packet.get("retrieved_before_policy")==
                b_feedback.get("retrieved_before_policy") and
            b_feedback.get("parent_native_sha256")==origin["result_sha256"] and
            b_feedback.get("revision_packet_sha256")==digest(packet) and
            b_feedback.get("provider_calls_by_this_adapter")==0 and
            type(receipt) is dict and
            receipt.get("case_id")=="CT-03" and
            receipt.get("world_public_id")==construction["world_public_id"] and
            receipt.get("condition_id")=="C0" and
            receipt.get("source_snapshot_hash")==construction["source_snapshot_hash"] and
            receipt.get("round_kind")=="revision" and
            receipt.get("mode")=="live" and
            receipt.get("status")=="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED" and
            receipt.get("provider_calls")==1 and
            receipt.get("proxy_requests")==1 and
            receipt.get("model_returned") is True and
            receipt.get("upstream_sha")==origin["upstream_sha"] and
            receipt.get("upstream_source_modified") is False and
            receipt.get("transport")==origin["transport"] and
            receipt.get("parent_native_sha256")==origin["result_sha256"] and
            receipt.get("own_feedback_sha256")==digest(packet) and
            receipt.get("horizon_matches_case") is True and
            receipt.get("output_horizon_hours")==8 and
            receipt.get("result_sha256")==_model_sha(native),
            "CT03_B_REVISION_NOT_ORIGINAL_ENGINE_CURRENTMODEL_OWN_FEEDBACK")
    return digest(packet)


def prepare(native:dict,receipt:dict,construction:dict,b_feedback:dict,out:Path,
            *,revision_provenance=None):
    out=Path(out)
    require(not out.exists(),"CT03_B_PHYSICAL_NO_OVERWRITE")
    if revision_provenance is None:
        validate_initial(native,receipt,construction)
        effective_g1=b_feedback.get("G1_status") if type(b_feedback) is dict else None
    else:
        validate_revision_live(native,receipt,construction,b_feedback,
                               revision_provenance)
        # G1 of the new native is checked freshly, not inherited from
        # the original currentModel's G1 status.
        effective_g1="NATIVE_TRANSLATION_CONDITIONAL_NEEDS_G2_AND_OBSERVABLE"
    require(type(b_feedback) is dict and
            b_feedback.get("schema")==
              "igc-ct03-b-original-own-g1-ledger-and-revision-packet/1.0" and
            b_feedback.get("world_public_id")==construction["world_public_id"] and
            b_feedback.get("source_snapshot_hash")==construction["source_snapshot_hash"] and
            b_feedback.get("parent_native_sha256")==(
                receipt["result_sha256"] if revision_provenance is None
                else revision_provenance["parent_receipt"]["result_sha256"]) and
            b_feedback.get("new_omc_by_this_adapter")==0 and
            b_feedback.get("provider_calls_by_this_adapter")==0 and
            b_feedback.get("G1_status") in (
              "G1_TRANSLATION_BLOCKED_ORIGINAL_UNCHANGED",
              "NATIVE_TRANSLATION_CONDITIONAL_NEEDS_G2_AND_OBSERVABLE"),
            "CT03_B_PHYSICAL_G1_OWN_FEEDBACK_MISSING")
    model=None
    translated=None
    port=None
    block=None
    if effective_g1=="G1_TRANSLATION_BLOCKED_ORIGINAL_UNCHANGED":
        block=b_feedback["G1_block_reason"]
        require(type(block) is str and block,
                "CT03_B_PHYSICAL_G1_FAILURE_REASON_MISSING")
    else:
        # Re-run original translator: cannot trust copied provisional Modelica.
        try:
            model,translated,_=generate(native)
            port=operator(native)
        except (TranslationBlocked,ValueError) as exc:
            block=str(exc)
            # The translated Modelica may be valid yet the native delivery
            # observable remains unresolved. Never stage an executable MOS
            # without the separately grounded observation operator.
            model,translated,port=None,None,None
        require((block is not None)==(translated is None),
                "CT03_B_PHYSICAL_NO_UNCONTROLLED_NATIVE_FALLBACK")
    result={
        "schema":SCHEMA,
        "status":(
            "B_NATIVE_G1_TRANSLATION_BLOCKED_NO_OMC"
            if effective_g1=="G1_TRANSLATION_BLOCKED_ORIGINAL_UNCHANGED"
            else "B_OBSERVABLE_UNRESOLVED_NO_OMC"
            if block else "B_NATIVE_PHYSICAL_PLANNED_NO_OMC"),
        "world_public_id":construction["world_public_id"],
        "source_snapshot_hash":construction["source_snapshot_hash"],
        "native_result_sha256":receipt["result_sha256"],
        "native_result_bytes_bound":_model_sha(native)==receipt["result_sha256"],
        "original_G1_status":effective_g1,
        "round_kind":"revision" if revision_provenance else "initial",
        "revision_parent_native_sha256":(
            revision_provenance["parent_receipt"]["result_sha256"]
            if revision_provenance else None),
        "original_G1_feedback_sha256":digest(b_feedback),
        "observation_operator":port,
        "blocked_reason":block,
        "translated_model_name":model,
        "translated_modelica_sha256":sha_bytes(translated.encode()) if translated else None,
        "script_sha256":None,
        "provider_calls_by_this_step":0,
        "new_omc_by_this_step":0,
        "reserved_truth_read":False,
        "model_repair_performed":False,
        "observable_scope":"Conservative native terminal stock recognition only; "
                           "an unresolved port is NOT proof that the native lacks "
                           "valid delivery semantics. No scoring or fit based selection."
    }
    out.mkdir(parents=True,exist_ok=False)
    if translated:
        # No extra state, equations or reporting variables added to the native.
        (out/(model+".mo")).write_text(translated,encoding="utf-8",newline="\n")
        script="\n".join([
            "getVersion();",
            'loadFile("/repo/'+(out/(model+".mo")).as_posix()+'");',
            "checkModel("+model+");",
            "print(getErrorString());",
            "simulate("+model+",startTime=0,stopTime=8,numberOfIntervals=64,"
            'method="euler",outputFormat="csv",fileNamePrefix="'+
              (out/"b-original").as_posix()+'");',
            "print(getErrorString());",""
        ])
        require(script.count("simulate(")==1,
                "CT03_B_PHYSICAL_ONE_SIMULATION_PER_NATIVE")
        (out/"initial.mos").write_text(script,encoding="utf-8",newline="\n")
        result["script_sha256"]=sha_bytes(script.encode())
    (out/"plan.json").write_bytes(canonical(result)+b"\n")
    return result

def main():
    p=argparse.ArgumentParser()
    for arg in ("native","receipt","construction","b-feedback","out"):
        p.add_argument("--"+arg,type=Path,required=True)
    for arg in ("revision-parent-native","revision-parent-receipt","revision-packet"):
        p.add_argument("--"+arg,type=Path)
    a=p.parse_args()
    def load(f):return json.loads(f.read_text(encoding="utf-8"))
    extras=(a.revision_parent_native,a.revision_parent_receipt,a.revision_packet)
    require(all(x is None for x in extras) or all(x is not None for x in extras),
            "CT03_B_REVISION_ALL_PARENT_INPUTS_REQUIRED")
    revision=({
        "parent_native":load(a.revision_parent_native),
        "parent_receipt":load(a.revision_parent_receipt),
        "packet":load(a.revision_packet),
    } if all(x is not None for x in extras) else None)
    result=prepare(load(a.native),load(a.receipt),load(a.construction),
                   load(a.b_feedback),a.out,revision_provenance=revision)
    print(json.dumps({"status":result["status"],"new_omc":0,"provider":0}))

if __name__=="__main__":
    main()
