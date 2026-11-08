/** CT-03 strict Buffalo visible input and own-parent gates.
 * Pure validation, no engine, no provider. The same original engine and
 * Cloudflare adapter are invoked ONLY by arena_b_ct03_native_runner.mjs.
 */
import {digest} from "./arena_b_cf_protocol_adapter.mjs";
import {createHash} from "node:crypto";

export const CT03_SCHEMA="igc-ct03-b-visible/1.0";
export const CT03_OWN_FEEDBACK_SCHEMA="igc-ct03-b-own-feedback/1.0";
export const CT03_INPUT={pulse_rate:1.7,pulse_start:0,pulse_end:2,
                         total_mass:3.4,unit:"items/hour",horizon_hours:8,
                         integration_step_hours:0.125};
const hash=/^sha256:[0-9a-f]{64}$/;
// Existing ATMS project() returns a bare 64-hex report digest, unlike arena_v0_contract.digest.
const projectionHash=/^(?:sha256:)?[0-9a-f]{64}$/;
const fail=code=>{throw Error(code);};
const keys=(obj,allowed)=>Object.keys(obj).every(k=>allowed.includes(k));
const finite=n=>typeof n==="number"&&Number.isFinite(n);
const stable=x=>Array.isArray(x)?x.map(stable):
  (x&&typeof x==="object")?Object.fromEntries(Object.entries(x).sort().map(([k,v])=>[k,stable(v)])):x;
const same=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
const unsafe=/holdout|gold|private|rival|secret|future_observation|evaluator/i;
// Legitimate diagnostics can explicitly say no_future_truth=true; forbid
// actual hidden fields, not negative assertions of the absence of truth.
const forbiddenKey=/^(heldout|gold|hidden_world|true_world|true_parameters|private_des|rival_outputs|evaluator|reserved_truth|future_observation|t6|t8)$/i;
function forbiddenFields(value){
  if(!value || typeof value!=="object")return false;
  if(Array.isArray(value))return value.some(forbiddenFields);
  return Object.entries(value).some(([k,v])=>forbiddenKey.test(k)||forbiddenFields(v));
}

export function validateCt03Visible(v,round) {
  if(!v||typeof v!=="object"||Array.isArray(v) ||
     v.schema!==CT03_SCHEMA || v.case_id!=="CT-03" || v.arm!=="B" ||
     v.round_id!=="ct03-b-"+round || !["initial","revision"].includes(round) ||
     !hash.test(v.source_snapshot_hash??"") ||
     !/^[A-Za-z0-9_-]{1,64}$/.test(v.world_public_id??"") ||
     v.condition_id!=="C0" || typeof v.question!=="string" ||
     !v.question.startsWith("Build a quantitative aggregate stock-flow model") ||
     !keys(v,["schema","case_id","arm","round_id","source_snapshot_hash",
              "world_public_id","condition_id","question","construction",
              "observability"]))
    fail("CT03_B_WRONG_VISIBLE_SCHEMA_SCOPE_OR_KEYS");
  if(!v.construction || !v.observability ||
     !keys(v.construction,["input","observations","observation_times_hours"]) ||
     !keys(v.observability,["quantity_unit","time_unit","observable",
                             "construction_times_hours","horizon_hours"]))
    fail("CT03_B_WRONG_OBSERVATION_SURFACE");
  if(!same(v.construction.input,CT03_INPUT)||
     !same(v.observability,{
       quantity_unit:"items",time_unit:"hours",observable:"cumulative_delivered",
       construction_times_hours:[0,1,2,4],horizon_hours:8
     }) ||
     !same(v.construction.observation_times_hours,[0,1,2,4]))
    fail("CT03_B_INPUT_PULSE_OR_CUTS_CHANGED");
  if(!Array.isArray(v.construction.observations) || v.construction.observations.length!==4)
    fail("CT03_B_FOUR_CONSTRUCTION_OBSERVATIONS_REQUIRED");
  // 1e-8 is numeric-comparison slack, not calibrated instrumental error.
  const eps=1e-8;
  let previous=0;
  for(let i=0;i<4;i++){
    const o=v.construction.observations[i];
    const t=[0,1,2,4][i];
    const arrived=CT03_INPUT.pulse_rate*Math.min(t,CT03_INPUT.pulse_end);
    if(!o || typeof o!=="object" || Array.isArray(o) ||
       Object.keys(o).length!==2 || !keys(o,["time","delivered"]) ||
       o.time!==t || !finite(o.delivered) ||
       (i===0 && Math.abs(o.delivered)>eps) ||
       o.delivered < -eps || o.delivered < previous-eps ||
       o.delivered>arrived+eps)
      fail("CT03_B_INVALID_CONSTRUCTION_POINT");
    previous=o.delivered;
  }
  if(unsafe.test(JSON.stringify(v)))fail("CT03_B_EVALUATOR_OR_RIVAL_LEAK");
  if(v.question.length>2000)fail("CT03_B_QUESTION_TOO_LONG");
  return {condition:"C0",world:v.world_public_id,source_hash:v.source_snapshot_hash};
}

function verifyLedgerDiagnostic(feedback, receipt, check) {
  // Python canonical() uses sorted keys, ensure_ascii=False, compact JSON.
  // Do NOT rehash JS JSON.stringify: numerical spellings may differ.
  const encoded=feedback.own_diagnostic_canonical_base64;
  if(typeof encoded!=="string" || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded) ||
     !encoded.length)fail("CT03_B_DIAGNOSTIC_CANONICAL_BYTES_MISSING");
  const raw=Buffer.from(encoded,"base64");
  const contents=raw.toString("utf8");
  if(raw.toString("base64")!==encoded || !Buffer.from(contents,"utf8").equals(raw))
    fail("CT03_B_DIAGNOSTIC_CANONICAL_BYTES_INVALID");
  const sha="sha256:"+createHash("sha256").update(raw).digest("hex");
  if(sha!==feedback.own_diagnostic_sha256)
    fail("CT03_B_DIAGNOSTIC_BYTES_HASH_MISMATCH");
  let parsed;
  try{parsed=JSON.parse(contents);}catch{fail("CT03_B_DIAGNOSTIC_CANONICAL_INVALID_JSON");}
  if(!parsed || typeof parsed!=="object" || Array.isArray(parsed) ||
     !same(parsed,feedback.own_diagnostic))
    fail("CT03_B_DIAGNOSTIC_BODY_NOT_EXPORTED_LEDGER_BYTES");
  // A consumed G2 failure has an attempt receipt but no admissible CSV.
  // Do not require a fabricated trace, and do not accept a mere null.
  const consumedG2Failure=parsed.evidence==="G2" &&
    parsed.trace_sha256===null &&
    parsed.no_valid_trajectory_or_forecast===true &&
    hash.test(parsed.attempt_record_sha256??"") &&
    hash.test(parsed.own_physical_outcome_sha256??"") &&
    typeof parsed.physical_failure_class==="string" &&
    ["OMC_EXIT_NONZERO","G2_PHYSICAL_CHECK_FAILED"].includes(
      parsed.physical_failure_class) &&
    typeof parsed.physical_failure_reason==="string" &&
    parsed.physical_failure_reason.length>0 &&
    Array.isArray(parsed.observations) &&
    parsed.observations.length===0;
  // Authenticated body is the decoded source, not an untrusted duplicate.
  if(parsed.arm!=="B" ||
     parsed.condition!==check.condition ||
     parsed.source_hash!==check.source_hash ||
     parsed.parent_hash!==receipt.result_sha256 ||
     parsed.own_evidence_only!==true || parsed.no_future_truth!==true ||
     !["G1","G2","G3"].includes(parsed.evidence) ||
     (parsed.evidence!=="G1" &&
       !hash.test(parsed.trace_sha256??"") && !consumedG2Failure) ||
     forbiddenFields(parsed))
    fail("CT03_B_DIAGNOSTIC_OWN_SCOPE_OR_PROVENANCE");
  if(!Array.isArray(parsed.observations) ||
     !parsed.observations.every(p=>p && typeof p==="object" && !Array.isArray(p) &&
       finite(p.time) && p.time>=0 && p.time<=4 && finite(p.residual)))
    fail("CT03_B_DIAGNOSTIC_OUTSIDE_CONSTRUCTION");
  const retrieval=feedback.retrieved_before_policy;
  const expectedItem="ct-CT03-"+check.world+"-R0-B-"+check.condition+
    "-parent-"+receipt.result_sha256.slice(7)+":FEEDBACK";
  if(!retrieval || typeof retrieval!=="object" || Array.isArray(retrieval) ||
     Object.keys(retrieval).length!==3 ||
     !keys(retrieval,["item_id","projection_hash","as_known_at"]) ||
     retrieval.item_id!==expectedItem ||
     !projectionHash.test(retrieval.projection_hash??"") ||
     typeof retrieval.as_known_at!=="string" ||
     !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(retrieval.as_known_at) ||
     !Number.isFinite(Date.parse(retrieval.as_known_at)))
    fail("CT03_B_LEDGER_RETRIEVAL_METADATA_INVALID");
  return parsed;
}

export function validateCt03Revision({native,receipt,feedback,visible,mode}){
  const check=validateCt03Visible(visible,"revision");
  if(!native||!native.model||!Array.isArray(native.model.variables)||
     !Array.isArray(native.model.relationships)||!native.model.specs||
     !receipt || receipt.case_id!=="CT-03" ||
     receipt.world_public_id!==check.world ||
     receipt.condition_id!==check.condition ||
     receipt.round_kind!=="initial" ||
     receipt.source_snapshot_hash!==check.source_hash ||
     receipt.model_returned!==true ||
     receipt.result_sha256!==digest(native) ||
     (mode==="live" && (receipt.mode!=="live"||receipt.provider_calls!==1)))
    fail("CT03_B_ORIGINAL_PARENT_RECEIPT_MISMATCH");
  if(!feedback || feedback.schema!==CT03_OWN_FEEDBACK_SCHEMA ||
     feedback.arm!=="B" || feedback.world_public_id!==check.world ||
     feedback.condition_id!==check.condition ||
     feedback.source_snapshot_hash!==check.source_hash ||
     feedback.parent_result_sha256!==receipt.result_sha256 ||
     !hash.test(feedback.own_diagnostic_sha256??"") ||
     !feedback.retrieved_before_policy || typeof feedback.own_diagnostic!=="object" ||
     feedback.own_diagnostic===null ||
     forbiddenFields(feedback))
    fail("CT03_B_FEEDBACK_NOT_OWN_OR_MISSING_LEDGER_RETRIEVAL");
  const authenticated=verifyLedgerDiagnostic(feedback,receipt,check);
  return {model:native.model,
          feedback:{...feedback,own_diagnostic:authenticated},source:check};
}

export function classifyCt03NativeResult(r){
  const n=Number(r?.provider_calls??0),native=r?.model_returned===true;
  const out={provider_calls_attempted:n,
             provider_response_observed:Number.isInteger(r?.http_status),
             raw_provider_response_observed:r?.raw_provider_saved===true,
             provider_billing:r?.provider_usage?"PROVIDER_USAGE_RECEIVED":"UNKNOWN",
             native_model_available:native};
  if(!native)return {...out,status:n?
    "CT03_PROVIDER_ATTEMPT_NO_NATIVE":"CT03_PREPROVIDER_NO_NATIVE",
    G0:"NOT_REACHED_NO_NATIVE"};
  if(r.horizon_matches_case!==true)return {...out,
    status:"CT03_NATIVE_HORIZON_MISMATCH",G0:"REJECTED_HORIZON"};
  return {...out,status:r.mode==="mock"?
    "ORIGINAL_ENGINE_OFFLINE_PATH_PASS":"ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED",
    G0:"NATIVE_GENERATED_NOT_YET_G1_G2"};
}
