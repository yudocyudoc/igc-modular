/** Coffee Buffalo R1: one original Engine.generate(prompt,currentModel,...).
 * One SDK interception -> <=1 Cloudflare Workers AI POST. The parent/feedback
 * were attested through Python against the archived final B-only Ledger.
 * No local native repair, rivals, heldout, OMC or automatic retry.
 */
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
const env=process.env;
const fail=reason=>{throw Error("COFFEE_B_REVIEW_"+reason);};
const need=(ok,code)=>{if(!ok)fail(code);};
const hash=x=>"sha256:"+createHash("sha256").update(x).digest("hex");
const digest=x=>hash(JSON.stringify(x));
need(env.COFFEE_B_REVIEW_AUTH==="yes" &&
     env.GITHUB_REPOSITORY==="yudocyudoc/igc-modular" &&
     env.GITHUB_REF==="refs/heads/main" &&
     env.GITHUB_EVENT_NAME==="workflow_dispatch" &&
     env.GITHUB_RUN_ATTEMPT==="1" &&
     /^[0-9a-f]{40}$/.test(env.GITHUB_SHA??"") &&
     /^[1-9][0-9]*$/.test(env.GITHUB_RUN_ID??"") &&
     env.CLOUDFLARE_API_TOKEN &&
     /^[0-9a-fA-F]{32}$/.test(env.CLOUDFLARE_ACCOUNT_ID??""),
     "FIRST_AUTHORIZED_MAIN_DISPATCH_REQUIRED");
need(!["CT03_R2_ACCESS_KEY_ID","CT03_R2_SECRET_ACCESS_KEY",
 "COFFEE_R2_ACCESS_KEY_ID","COFFEE_R2_SECRET_ACCESS_KEY",
 "AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN",
 "GH_TOKEN","GITHUB_TOKEN","OPEN_ROUTER_API_KEY"].some(k=>env[k]),
 "UNAUTHORIZED_PRIVATE_CREDENTIALS");
const payload=JSON.parse(await readFile(env.COFFEE_B_REVIEW_INPUT,"utf8"));
const admission=JSON.parse(await readFile(env.COFFEE_B_REVIEW_ADMISSION,"utf8"));
const attempt=JSON.parse(await readFile(env.COFFEE_B_REVIEW_ATTEMPT,"utf8"));
need(payload.schema==="arena.coffee-peak.buffalo-own-review-input/1" &&
     payload.round_kind==="revision" &&
     payload.case_sha256===admission.case_sha256 &&
     payload.case_sha256==="sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f" &&
     payload.run_id===Number(env.GITHUB_RUN_ID) &&
     payload.run_sha===env.GITHUB_SHA &&
     payload.source_model_sha256===admission.parent_sha256 &&
     admission.execution_run===payload.run_id &&
     admission.execution_sha===payload.run_sha &&
     admission.as_of_replayed===true &&
     payload.feedback_diagnostic_sha256===admission.feedback_diagnostic_sha256 &&
     payload.feedback_run_id===43561168032 &&
     payload.parent_live_run_id===43537333254 &&
     payload.max_provider_posts===1 &&
     payload.provider_posts===undefined &&
     payload.truth_access===false && payload.r2_access===false &&
     payload.scientific_lock_created===false && payload.new_omc===0 &&
     Array.isArray(payload.currentModel.variables) &&
     Array.isArray(payload.currentModel.relationships) &&
     attempt.state==="RESERVED_BEFORE_HTTP" &&
     attempt.run_id===payload.run_id &&
     attempt.sha===env.GITHUB_SHA &&
     attempt.no_retry===true && attempt.max_posts===1,
     "ATTESTED_CURRENTMODEL_OR_REQUEST_CONTRACT_MISMATCH");
const scripts=resolve(env.BUFFALO_SCRIPTS_ROOT);
const sdai=resolve(env.SDAI_ROOT);
const out=resolve(env.COFFEE_B_REVIEW_OUT);
const {OR_SLUG,CF_MODEL,CF_MODE,EV01_BUDGET_AUTH,
       EV01_CAP,EV01_TIMEOUT_MS,requestToCloudflareEV01,
       responseToOpenRouter,cloudflareUrl}=
   await import(pathToFileURL(join(scripts,"arena_b_ev01_cf_adapter.mjs")).href);
const originalFetch=globalThis.fetch;
const save=(name,obj)=>writeFile(join(out,name),
    JSON.stringify(obj,null,2)+"\n",{flag:"wx"});
await mkdir(out,{recursive:false});
const receipt={
  schema:"arena.coffee-peak.buffalo-review-receipt/1",
  run_id:payload.run_id,run_sha:payload.run_sha,
  case_sha256:payload.case_sha256,
  original_engine:"Engine.generate",
  review_round:"R1",
  model:CF_MODEL,transport:CF_MODE,
  source_feedback_run:payload.feedback_run_id,
  source_parent_live_run:payload.parent_live_run_id,
  parent_native_file_sha256:payload.source_model_sha256,
  feedback_diagnostic_sha256:payload.feedback_diagnostic_sha256,
  original_current_model_in_sdk_request:false,
  sdk_interceptions:0,provider_posts:0,raw_provider_saved:false,
  model_returned:false,provider_usage:null,status:"STARTED",
  no_rival_inputs:true,new_omc:0,r2_access:false,
  truth_access:false,scientific_lock_created:false,retry:false
};
let finished=false;
try{
  globalThis.fetch=async (request,init={})=>{
    receipt.sdk_interceptions+=1;
    need(receipt.sdk_interceptions===1,"SECOND_SDK_REQUEST_BLOCKED");
    const url=new URL(typeof request==="string"?request:request.url);
    const method=init.method??(request instanceof Request?request.method:"GET");
    need(url.origin==="https://openrouter.ai" &&
      url.pathname.endsWith("/chat/completions") &&
      method.toUpperCase()==="POST","UNEXPECTED_SDK_REQUEST");
    let textBody=init.body??(request instanceof Request?await request.text():null);
    if(Buffer.isBuffer(textBody))textBody=textBody.toString("utf8");
    need(typeof textBody==="string","SDK_BODY_NOT_TEXT");
    const sdk=JSON.parse(textBody);
    const prior=JSON.stringify(payload.currentModel,null,2);
    const assistants=sdk.messages?.filter(x=>x.role==="assistant")??[];
    need(sdk.model===OR_SLUG &&
      sdk.response_format?.type==="json_schema" &&
      sdk.response_format.json_schema?.schema?.properties?.variables &&
      sdk.response_format.json_schema?.schema?.properties?.relationships &&
      Array.isArray(sdk.messages) &&
      assistants.length===1 && assistants[0].content===prior &&
      sdk.messages.at(-1)?.role==="user" &&
      sdk.messages.at(-1).content.endsWith(payload.prompt) &&
      sdk.messages.some(x=>typeof x.content==="string"&&
                           x.content.includes(payload.problemStatement)) &&
      sdk.messages.some(x=>typeof x.content==="string"&&
                           x.content.includes(payload.backgroundKnowledge)),
      "ORIGINAL_SDK_CURRENTMODEL_NOT_AUTHENTIC_REVIEW");
    receipt.original_current_model_in_sdk_request=true;
    receipt.sdk_request_sha256=digest(sdk);
    const effective=requestToCloudflareEV01(sdk,{authorization:EV01_BUDGET_AUTH});
    need(effective.max_completion_tokens===EV01_CAP &&
      effective.stream===false && effective.reasoning_effort==="low",
      "PROVIDER_BUDGET_DRIFT");
    receipt.effective_request_sha256=digest(effective);
    await save("sdk-request.json",sdk);
    await save("cloudflare-effective-request.json",{
      model:CF_MODEL,body:effective,no_credentials:true});
    // Reserve before network call, including errors and timeout uncertainty.
    receipt.provider_posts=1;
    await save("cf-call-started.json",{
      status:"REQUEST_MAY_HAVE_CONSUMED",run_id:payload.run_id,
      max_posts:1,effective_request_sha256:receipt.effective_request_sha256});
    const response=await originalFetch(cloudflareUrl(env.CLOUDFLARE_ACCOUNT_ID),{
      method:"POST",headers:{"Authorization":"Bearer "+env.CLOUDFLARE_API_TOKEN,
                            "Content-Type":"application/json"},
      body:JSON.stringify(effective),signal:AbortSignal.timeout(EV01_TIMEOUT_MS)});
    receipt.http_status=response.status;
    const rawText=await response.text();
    let raw;
    try{raw=JSON.parse(rawText)}catch{
      await save("provider-nonjson.json",{
        http_status:response.status,bytes:rawText.length,sha256:hash(rawText)});
      fail("NONJSON_PROVIDER_REPLY");
    }
    await save("provider-raw.json",raw);
    receipt.raw_provider_saved=true;
    receipt.provider_usage=raw?.result?.usage??raw?.usage??null;
    receipt.finish_reason=raw?.result?.choices?.[0]?.finish_reason??null;
    need(response.ok,"PROVIDER_HTTP_NON_200");
    const compatibility=responseToOpenRouter(raw,receipt.sdk_request_sha256);
    await save("openrouter-compat-envelope.json",compatibility);
    return new Response(JSON.stringify(compatibility),{
      status:200,headers:{"content-type":"application/json"}});
  };
  env.OPEN_ROUTER_API_KEY="VIRTUAL_ORIGINAL_SDK_BRIDGE_NO_OPENROUTER_POST";
  const {default:Engine}=await import(
    pathToFileURL(join(sdai,"engines/quantitative/engine.js")).href);
  const native=await new Engine().generate(
    payload.prompt,payload.currentModel,{
      underlyingModel:OR_SLUG,supportsArrays:false,supportsModules:false,
      supportsSubTypes:false,mentorMode:false,
      problemStatement:payload.problemStatement,
      backgroundKnowledge:payload.backgroundKnowledge,
      maxTokens:EV01_CAP,timeoutMinutes:7
    });
  await save("native-engine-result.json",native);
  receipt.native_sha256=digest(native);
  receipt.native_file_sha256=hash(JSON.stringify(native,null,2)+"\n");
  receipt.model_returned=Boolean(!native?.err &&
    Array.isArray(native?.model?.variables) &&
    Array.isArray(native?.model?.relationships));
  const scoped=receipt.model_returned &&
    native.model.specs?.startTime===0 &&
    Math.abs(native.model.specs?.stopTime-103.237/60)<1e-9 &&
    native.model.specs?.timeUnits==="hour";
  receipt.status=scoped?"ORIGINAL_ENGINE_OWN_REVIEW_RETURNED_G1_ONLY":
                        "REVISED_NATIVE_SCOPE_BLOCKED_G1";
  receipt.stop_reason=scoped?"NO_OMC_NO_G3_NO_SCIENTIFIC_LOCK":
                             "MODEL_OR_COFFEE_HORIZON_INVALID";
  finished=scoped;
}catch(_err){
  // No credentials, provider raw messages or response content in console.
  receipt.status="FAILURE_OR_CONSUMPTION_UNCERTAIN";
  receipt.stop_reason="REDACTED_ERROR_NO_RETRY";
}finally{
  globalThis.fetch=originalFetch;
  delete env.OPEN_ROUTER_API_KEY;
  await save("receipt.json",receipt);
  console.log(JSON.stringify({
    status:receipt.status,provider_posts:receipt.provider_posts,
    sdk_current_model_verified:receipt.original_current_model_in_sdk_request,
    native_returned:receipt.model_returned,new_omc:0,retry:false}));
  if(!finished) process.exitCode=1;
}
