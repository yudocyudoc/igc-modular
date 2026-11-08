import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {digest} from "../scripts/arena_b_cf_protocol_adapter.mjs";
import {validateCt03Visible,validateCt03Revision,classifyCt03NativeResult,
        CT03_SCHEMA,CT03_INPUT,CT03_OWN_FEEDBACK_SCHEMA}
  from "../scripts/arena_b_ct03_contract.mjs";

const SHA="sha256:"+"a".repeat(64);
const fixtureDiagnostic=parent=>({
  arm:"B",condition:"C0",source_hash:SHA,parent_hash:parent,
  evidence:"G3",trace_sha256:"sha256:"+"d".repeat(64),
  own_evidence_only:true,no_future_truth:true,
  observations:[{time:2,residual:0.3},{time:4,residual:0.4}]
});
const canonical=x=>JSON.stringify(Object.fromEntries(
  Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([key,value])=>
    [key,Array.isArray(value)?value.map(v=>typeof v==="object"?
      Object.fromEntries(Object.entries(v).sort()):v):value])));
const fixtureFeedback=(parent)=>{
  const diag=fixtureDiagnostic(parent);
  // Sorted-key fixture matches Python json.dumps(...,sort_keys=True,separators).
  const bytes=Buffer.from(canonical(diag),"utf8");
  return {schema:CT03_OWN_FEEDBACK_SCHEMA,arm:"B",
    world_public_id:"W1",condition_id:"C0",source_snapshot_hash:SHA,
    parent_result_sha256:parent,
    own_diagnostic_sha256:"sha256:"+createHash("sha256").update(bytes).digest("hex"),
    own_diagnostic_canonical_base64:bytes.toString("base64"),
    retrieved_before_policy:{item_id:"ct-CT03-W1-R0-B-C0-parent-"+parent.slice(7)+":FEEDBACK",
      projection_hash:"sha256:"+"c".repeat(64),
      as_known_at:"2026-11-07T12:00:00.000000+00:00"},
    own_diagnostic:diag};
};
const visible=(round="initial")=>({
  schema:CT03_SCHEMA,case_id:"CT-03",arm:"B",round_id:"ct03-b-"+round,
  source_snapshot_hash:SHA,world_public_id:"W1",condition_id:"C0",
  question:"Build a quantitative aggregate stock-flow model for conserved items.",
  construction:{input:CT03_INPUT,observations:[
    {time:0,delivered:0},{time:1,delivered:.1},
    {time:2,delivered:.2},{time:4,delivered:.4}],
    observation_times_hours:[0,1,2,4]},
  observability:{quantity_unit:"items",time_unit:"hours",
    observable:"cumulative_delivered",construction_times_hours:[0,1,2,4],
    horizon_hours:8}
});

test("CT03 B sees same fixed pulse and only four construction observations",()=>{
  assert.equal(validateCt03Visible(visible(),"initial").condition,"C0");
  assert.equal(validateCt03Visible(visible("revision"),"revision").world,"W1");
});

test("CT03 B rejects reserved truth, extra fields, wrong cuts, wrong pulse",()=>{
  const v=visible();v.heldout_t6=3;
  assert.throws(()=>validateCt03Visible(v,"initial"),/SCOPE_OR_KEYS/);
  const w=visible();w.construction.observations.push({time:6,delivered:2.1});
  assert.throws(()=>validateCt03Visible(w,"initial"),/FOUR_CONSTRUCTION/);
  const x=visible();x.construction.input={...CT03_INPUT,pulse_rate:2};
  assert.throws(()=>validateCt03Visible(x,"initial"),/PULSE_OR_CUTS/);
  const y=visible();y.question+=" EVALUATOR_PRIVATE_TRUTH";
  assert.throws(()=>validateCt03Visible(y,"initial"),/EVALUATOR_OR_RIVAL/);
});


test("F172-05 B rejects initial +/-0.5 and cumulative > arrived mass at t1",()=>{
  for(const initial of [-.5,.5]){
    const v=visible();
    v.construction.observations[0].delivered=initial;
    if(initial<0)for(const p of v.construction.observations.slice(1))p.delivered=.6;
    assert.throws(()=>validateCt03Visible(v,"initial"),/INVALID_CONSTRUCTION_POINT/);
  }
  const x=visible();
  [0,3,3.1,3.2].forEach((n,i)=>x.construction.observations[i].delivered=n);
  assert.throws(()=>validateCt03Visible(x,"initial"),/INVALID_CONSTRUCTION_POINT/);
  assert.equal(validateCt03Visible(visible(),"initial").condition,"C0");
});

test("CT03 B validates own currentModel parent exactly, never accepts other world",()=>{
  const native={model:{specs:{stopTime:8},variables:[],relationships:[]}};
  const receipt={case_id:"CT-03",world_public_id:"W1",condition_id:"C0",
    round_kind:"initial",source_snapshot_hash:SHA,model_returned:true,
    mode:"mock",provider_calls:0,result_sha256:digest(native)};
  const feedback=fixtureFeedback(receipt.result_sha256);
  const v=visible("revision");
  assert.equal(validateCt03Revision({native,receipt,feedback,visible:v,mode:"mock"}).model,
               native.model);
  assert.throws(()=>validateCt03Revision({native,receipt:{...receipt,world_public_id:"W2"},
    feedback,visible:v,mode:"mock"}),/PARENT_RECEIPT_MISMATCH/);
  assert.throws(()=>validateCt03Revision({native,receipt,feedback:{...feedback,arm:"M"},
    visible:v,mode:"mock"}),/FEEDBACK_NOT_OWN/);
  assert.throws(()=>validateCt03Revision({native,receipt,feedback,
    visible:v,mode:"live"}),/PARENT_RECEIPT_MISMATCH/);
});


test("F172-02 rejects edited bytes, t6, empty retrieval and forged inner provenance",()=>{
  const native={model:{specs:{stopTime:8},variables:[],relationships:[]}};
  const receipt={case_id:"CT-03",world_public_id:"W1",condition_id:"C0",
    round_kind:"initial",source_snapshot_hash:SHA,model_returned:true,
    mode:"mock",provider_calls:0,result_sha256:digest(native)};
  const original=fixtureFeedback(receipt.result_sha256);
  const v=visible("revision");
  const verify=f=>validateCt03Revision({native,receipt,feedback:f,visible:v,mode:"mock"});
  assert.equal(verify(original).feedback.own_diagnostic.observations[0].residual,.3);
  // Original ATMS project() returns 64 hex without the sha256: prefix.
  assert.equal(verify({...original,retrieved_before_policy:{
    ...original.retrieved_before_policy,
    projection_hash:"c".repeat(64)}}).feedback.own_diagnostic.arm,"B");
  assert.throws(()=>verify({...original,retrieved_before_policy:{
    ...original.retrieved_before_policy,
    item_id:"ct-CT03-W2-R0-B-C0-parent-"+receipt.result_sha256.slice(7)+":FEEDBACK"
  }}),/LEDGER_RETRIEVAL_METADATA_INVALID/);
  assert.throws(()=>verify({...original,own_diagnostic:{
    ...original.own_diagnostic,observations:[{time:2,residual:999},{time:4,residual:.4}]
  }}),/BODY_NOT_EXPORTED/);
  const tamper=x=>({...original,own_diagnostic:x});
  assert.throws(()=>verify(tamper({...original.own_diagnostic,
    observations:[...original.own_diagnostic.observations,{time:6,residual:.1}]})),
    /BODY_NOT_EXPORTED/);
  assert.throws(()=>verify({...original,retrieved_before_policy:{}}),/LEDGER_RETRIEVAL_METADATA_INVALID/);
  assert.throws(()=>verify(tamper({...original.own_diagnostic,source_hash:"sha256:"+"f".repeat(64),
    own_evidence_only:false,no_future_truth:false})),/BODY_NOT_EXPORTED/);
  const recanonical=x=>{
    const raw=Buffer.from(canonical(x));
    return {...original,own_diagnostic:x,
      own_diagnostic_canonical_base64:raw.toString("base64"),
      own_diagnostic_sha256:"sha256:"+createHash("sha256").update(raw).digest("hex")};
  };
  assert.throws(()=>verify(recanonical({...original.own_diagnostic,
    observations:[...original.own_diagnostic.observations,{time:6,residual:.1}]})),
    /OUTSIDE_CONSTRUCTION/);
  assert.throws(()=>verify(recanonical({...original.own_diagnostic,
    source_hash:"sha256:"+"f".repeat(64),own_evidence_only:false,no_future_truth:false})),
    /OWN_SCOPE_OR_PROVENANCE/);
});

test("CT03 B has separate NONE vs malformed horizon statuses",()=>{
  assert.equal(classifyCt03NativeResult({provider_calls:0,model_returned:false}).status,
               "CT03_PREPROVIDER_NO_NATIVE");
  assert.equal(classifyCt03NativeResult({provider_calls:1,model_returned:false}).status,
               "CT03_PROVIDER_ATTEMPT_NO_NATIVE");
  assert.equal(classifyCt03NativeResult({mode:"mock",model_returned:true,
    horizon_matches_case:false}).status,"CT03_NATIVE_HORIZON_MISMATCH");
});

test("CT03 B accepts only receipt-backed no-trajectory G2 as own revision feedback",()=>{
  const native={model:{specs:{stopTime:8},variables:[],relationships:[]}};
  const receipt={case_id:"CT-03",world_public_id:"W1",condition_id:"C0",
    round_kind:"initial",source_snapshot_hash:SHA,model_returned:true,
    mode:"mock",provider_calls:0,result_sha256:digest(native)};
  const basic=fixtureFeedback(receipt.result_sha256);
  const d={...basic.own_diagnostic,
    evidence:"G2",trace_sha256:null,observations:[],
    own_physical_outcome_sha256:"sha256:"+"b".repeat(64),
    attempt_record_sha256:"sha256:"+"c".repeat(64),
    no_valid_trajectory_or_forecast:true,
    physical_failure_class:"G2_PHYSICAL_CHECK_FAILED",
    physical_failure_reason:"CT03_B_PHYS_MATERIAL_MASS_BALANCE_FAILED"};
  const packet=(diag)=>{
    const bytes=Buffer.from(canonical(diag),"utf8");
    return {...basic,own_diagnostic:diag,
      own_diagnostic_canonical_base64:bytes.toString("base64"),
      own_diagnostic_sha256:"sha256:"+createHash("sha256").update(bytes).digest("hex")};
  };
  const verify=fb=>validateCt03Revision({
    native,receipt,feedback:fb,visible:visible("revision"),mode:"mock"});
  assert.equal(verify(packet(d)).feedback.own_diagnostic.evidence,"G2");
  assert.throws(()=>verify(packet({...d,attempt_record_sha256:null})),
    /OWN_SCOPE_OR_PROVENANCE/);
  assert.throws(()=>verify(packet({...d,no_valid_trajectory_or_forecast:false})),
    /OWN_SCOPE_OR_PROVENANCE/);
  assert.throws(()=>verify(packet({...d,physical_failure_reason:""})),
    /OWN_SCOPE_OR_PROVENANCE/);
  assert.throws(()=>verify(packet({...d,observations:[{time:6,residual:0}]})),
    /OWN_SCOPE_OR_PROVENANCE|OUTSIDE_CONSTRUCTION/);
});
