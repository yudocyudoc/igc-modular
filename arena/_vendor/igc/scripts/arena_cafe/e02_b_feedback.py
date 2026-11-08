"""E02 Buffalo: create ONLY its own G0 diagnostic, never DES or rival feedback.

A genuine provider response is required. Native original still controls
whether to modify its model after this diagnostic. This is not G2/G3.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.arena_v0_contract import canonical
from scripts.arena_cafe.native_handoff import need

SCHEMA="igc-e02-b-own-feedback/0.1"
STATUS="G0_SELF_INSPECTION_ONLY_NO_NATIVE_TRAJECTORY"


def _model_sha(native):
    # Match the compact UTF-8 JSON.stringify object digest used by the
    # Node original-engine adapter. Reject instead of guessing on mismatch.
    return "sha256:"+sha256(json.dumps(native,ensure_ascii=False,
                     separators=(",",":"),allow_nan=False).encode()).hexdigest()


def build(native,receipt):
    need(type(native) is dict and type(receipt) is dict,
         "B_E02_NATIVE_AND_RECEIPT_REQUIRED")
    need(receipt.get("case_id")=="EV-01" and
         receipt.get("round_kind")=="initial" and
         receipt.get("condition_id") in ("O0","O1") and
         receipt.get("mode")=="live" and receipt.get("provider_calls")==1 and
         receipt.get("model_returned") is True and
         receipt.get("status")=="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED",
         "B_E02_REAL_OWN_PARENT_REQUIRED")
    need(receipt.get("result_sha256")==_model_sha(native),
         "B_E02_NATIVE_RECEIPT_HASH_MISMATCH")
    model=native.get("model")
    need(type(model) is dict and
         type(model.get("variables")) is list and
         type(model.get("relationships")) is list and
         type(model.get("specs")) is dict,
         "B_E02_NATIVE_SCHEMA_NOT_ADMISSIBLE")
    spec=model["specs"]
    horizon=spec.get("stopTime")
    name_types=[v.get("type") for v in model["variables"] if type(v) is dict]
    need(len(name_types)==len(model["variables"]) and
         all(isinstance(k,str) for k in name_types),
         "B_E02_NATIVE_VARIABLE_TYPE_INVALID")
    diagnostic={
        "scope":STATUS,
        "native_first_round_status":receipt["status"],
        "native_model_sha256":receipt["result_sha256"],
        "native_variable_count":len(model["variables"]),
        "native_relationship_count":len(model["relationships"]),
        "native_stock_count":name_types.count("stock"),
        "native_flow_count":name_types.count("flow"),
        "native_time_unit":spec.get("timeUnits"),
        "native_stop_hours":horizon,
        "public_cutoff_hours":1/6,
        "native_horizon_matches_public_cutoff":(
            isinstance(horizon,(int,float)) and abs(horizon-1/6)<1e-8),
        "native_equations_translated":"NOT_RUN_NO_G0_G1_EQUIVALENCE",
        "native_trajectory":"NOT_RUN",
        "H_j_delivery_operator":"NOT_AUTHENTICATED",
        "input_kernel_read_by_upstream":"PROMPT_EXPOSED_NATIVE_USE_NOT_PROVEN",
        "scientific_fit":"NOT_COMPUTABLE_NO_NATIVE_G2_TRACE",
        "no_rival_models_or_evaluator_truth":True,
        "no_repair_equation_hints":True,
        "epistemic_status":"PROVIDER_NATIVE_RETURNED_G0_ONLY",
    }
    return {
        "schema":SCHEMA,
        "arm":"B",
        "condition_id":receipt["condition_id"],
        "source_snapshot_hash":receipt["source_snapshot_hash"],
        "parent_result_sha256":receipt["result_sha256"],
        "diagnostic":diagnostic,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--native",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    need(not args.out.exists(),"B_E02_FEEDBACK_REFUSE_OVERWRITE")
    result=build(json.loads(args.native.read_text()),
                 json.loads(args.receipt.read_text()))
    args.out.write_bytes(canonical(result)+b"\n")
    print(json.dumps({"status":STATUS,
                      "condition_id":result["condition_id"],
                      "scientific_fit":"NOT_COMPUTABLE",
                      "provider_calls_in_this_step":0}))


if __name__=="__main__":
    main()
