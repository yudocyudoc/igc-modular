/** Buffalo-adjust-v1: one invocation of the ORIGINAL Engine.generate.
 * This is a versioned operational adapter, not a fork of the scientific SDK.
 * The caller reserves the paid attempt BEFORE launching this script.
 * 1 original OpenRouter SDK request -> 1 Workers AI POST maximum.
 */
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
const root=resolve(process.env.SDAI_ROOT??"upstream/sd-ai");
const scripts=resolve(process.env.BUFFALO_SCRIPTS_ROOT??"scripts");
const out=resolve(process.env.BUFFALO_ADJUST_OUTPUT??"artifacts/buffalo-adjust-v1/unknown");
const round=process.env.BUFFALO_ADJUST_ROUND;
const pin="5199f7b45f3a7ae4a773cb0dd8542940aabe9edc";
const {OR_SLUG,CF_MODEL,CF_MODE,digest,responseToOpenRouter,
       requestToCloudflareEV01,cloudflareUrl,EV01_BUDGET_AUTH,
       EV01_CAP,EV01_TIMEOUT_MS,EV01_ADAPTER_VERSION} =
       await import(pathToFileURL(join(scripts,"arena_b_ev01_cf_adapter.mjs")).href);
const {validateCt03Visible} =
       await import(pathToFileURL(join(scripts,"arena_b_ct03_contract.mjs")).href);
const sha=x=>digest(x);
const originals={fetch:globalThis.fetch};
const receipt={
  schema:"buffalo-adjust-v1/original-engine-attempt/1",batch_id:"buffalo-adjust-v1",
  round_kind:round,upstream_sha:pin,upstream_source_modified:false,
  provider_model:CF_MODEL,backend_alias:OR_SLUG,transport:CF_MODE,
  adapter_version:EV01_ADAPTER_VERSION,original_engine_max_tokens:EV01_CAP,
  configured_http_timeout_ms:EV01_TIMEOUT_MS,provider_calls:0,proxy_requests:0,
  model_returned:false,raw_provider_saved:false,status:"STARTED",
  no_other_arm_inputs:true,new_omc:0,new_worlds:0,
  generation_profile_sha256:null,runner_error:null
};
const save=(name,data)=>writeFile(join(out,name),JSON.stringify(data,null,2)+"\n");
const fail=code=>{throw Error(code)};
await mkdir(out,{recursive:false});
try{
  if(process.env.GITHUB_EVENT_NAME!=="workflow_dispatch"||
     process.env.GITHUB_RUN_ATTEMPT!=="1"||
     process.env.GITHUB_REF!=="refs/heads/main"||
     process.env.BUFFALO_ADJUST_AUTH!=="yes"||
     !/^[0-9a-f]{40}$/.test(process.env.GITHUB_SHA??"")||
     !/^[1-9][0-9]*$/.test(process.env.GITHUB_RUN_ID??"")||
     !["bf03","bf04"].includes(round))
    fail("BUFFALO_ADJUST_MANUAL_FIRST_ATTEMPT_ON_MAIN_REQUIRED");
  if(!process.env.CLOUDFLARE_API_TOKEN)fail("CLOUDFLARE_TOKEN_MISSING");
  if(["CT03_R2_ACCESS_KEY_ID","CT03_R2_SECRET_ACCESS_KEY",
      "AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY"].some(x=>process.env[x]))
    fail("CUSTODIAN_SECRETS_FORBIDDEN");
  const visible=JSON.parse(await readFile(resolve(process.env.BUFFALO_VISIBLE_INPUT),"utf8"));
  const validated=validateCt03Visible(visible,round==="bf03"?"revision":"initial");
  const profile=JSON.parse(await readFile(resolve(process.env.BUFFALO_PROFILE_INPUT),"utf8"));
  if(profile.id!=="buffalo-adjust-v1"||!profile.text||
     profile.utf8_sha256!=="sha256:"+createHash("sha256").update(profile.text).digest("hex"))
    fail("PROFILE_SHA_INVALID");
  receipt.generation_profile_sha256=profile.utf8_sha256;
  receipt.source_snapshot_hash=visible.source_snapshot_hash;
  receipt.world_public_id=visible.world_public_id;
  receipt.condition_id=visible.condition_id;
  const feedback=round==="bf03"
    ?JSON.parse(await readFile(resolve(process.env.BUFFALO_OWN_FEEDBACK),"utf8"))
    :null;
  const parent=round==="bf03"
    ?JSON.parse(await readFile(resolve(process.env.BUFFALO_PARENT_NATIVE),"utf8"))
    :null;
  if(round==="bf03" && (feedback?.profile_sha256!==profile.utf8_sha256||
      !parent?.model?.variables||!parent?.model?.relationships||
      feedback?.world_public_id!==visible.world_public_id||
      feedback?.source_snapshot_hash!==visible.source_snapshot_hash))
    fail("ORIGINAL_PARENT_FEEDBACK_PROVENANCE_MISMATCH");
  if(round==="bf03")receipt.parent_native_sha256=feedback.parent_native_sha256;
  const userPrompt=visible.question+"\n\n"+profile.text+
    (round==="bf03"?
       "\n\nReconsider YOUR previous native model (currentModel) using ONLY "+
       "your own semantic diagnostic and the public construction. Do not "+
       "inherit the model unchanged if defects remain. Do not add hidden "+
       "observations, other arms or true parameters.\n"+
       JSON.stringify(feedback.own_semantic_diagnostics):"");
  const parentModel=round==="bf03"?parent.model:{variables:[],relationships:[]};
  globalThis.fetch=async (request,init={})=>{
    receipt.proxy_requests+=1;
    if(receipt.proxy_requests!==1)fail("SECOND_SDK_REQUEST_REFUSED");
    const url=new URL(typeof request==="string"?request:request.url);
    const method=init.method??(request instanceof Request?request.method:"GET");
    if(url.origin!=="https://openrouter.ai"||
       !url.pathname.endsWith("/chat/completions")||
       method.toUpperCase()!=="POST")
      fail("UNEXPECTED_OUTBOUND_REQUEST");
    let bodyText=init.body??(request instanceof Request?await request.text():null);
    if(Buffer.isBuffer(bodyText))bodyText=bodyText.toString("utf8");
    if(typeof bodyText!=="string")fail("SDK_REQUEST_NOT_JSON_TEXT");
    const body=JSON.parse(bodyText);
    if(body.model!==OR_SLUG||body.response_format?.type!=="json_schema"||
       !body.response_format.json_schema?.schema?.properties?.variables||
       !body.response_format.json_schema?.schema?.properties?.relationships)
      fail("ORIGINAL_QUANTITATIVE_SDK_SCHEMA_MISMATCH");
    const serialized=JSON.stringify(parentModel,null,2);
    if(round==="bf03" && !body.messages.some(m=>m.role==="assistant"&&m.content===serialized))
      fail("ORIGINAL_CURRENTMODEL_MISSING_FROM_SDK_REQUEST");
    if(round==="bf04" && body.messages.some(m=>m.role==="assistant"&&m.content===serialized))
      fail("BF04_CURRENTMODEL_NOT_ALLOWED");
    if(body.messages.at(-1)?.role!=="user"||
       !body.messages.at(-1)?.content.endsWith(userPrompt))
      fail("SDK_PROMPT_PROFILE_NOT_PRESENT");
    receipt.request_sha256=sha(body);
    receipt.schema_sha256=sha(body.response_format.json_schema.schema);
    const effective=requestToCloudflareEV01(body,{authorization:EV01_BUDGET_AUTH});
    if(effective.max_completion_tokens!==16000||
       effective.reasoning_effort!=="low"||effective.stream!==false)
      fail("CLOUDFLARE_ADAPTER_CHANGED");
    receipt.effective_request_sha256=sha(effective);
    await save("sdk-request.json",body);
    await save("cf-effective-request.json",{model:CF_MODEL,body:effective,
      body_sha256:receipt.effective_request_sha256,no_credentials:true});
    receipt.provider_calls=1; // Mark BEFORE the network call; timeout still counts.
    await save("cf-call-started.json",{provider_calls:1,
      effective_request_sha256:receipt.effective_request_sha256,
      run_id:process.env.GITHUB_RUN_ID,round});
    const response=await originals.fetch(cloudflareUrl(process.env.CLOUDFLARE_ACCOUNT_ID),{
      method:"POST",headers:{"Authorization":"Bearer "+process.env.CLOUDFLARE_API_TOKEN,
                             "Content-Type":"application/json"},
      body:JSON.stringify(effective),signal:AbortSignal.timeout(EV01_TIMEOUT_MS)
    });
    receipt.http_status=response.status;
    const rawText=await response.text();
    let raw;
    try{raw=JSON.parse(rawText)}catch{
      await save("nonjson-response.json",{http_status:response.status,
        text_sha256:"sha256:"+createHash("sha256").update(rawText).digest("hex"),
        length:rawText.length});
      fail("PROVIDER_NON_JSON");
    }
    await save("provider-raw.json",raw);
    receipt.raw_provider_saved=true;
    receipt.provider_usage=raw?.result?.usage??raw?.usage??null;
    receipt.provider_finish_reason=raw?.result?.choices?.[0]?.finish_reason??null;
    if(!response.ok)fail("CLOUDFLARE_HTTP_"+response.status);
    const envelope=responseToOpenRouter(raw,receipt.request_sha256);
    await save("openrouter-compat-envelope.json",envelope);
    return new Response(JSON.stringify(envelope),{
      status:200,headers:{"content-type":"application/json"}});
  };
  process.env.OPEN_ROUTER_API_KEY="IGC_LOCAL_ONLY_NOT_REAL_OPENROUTER_KEY";
  const {default:Engine}=await import(pathToFileURL(join(root,"engines/quantitative/engine.js")).href);
  const parameters={underlyingModel:OR_SLUG,supportsArrays:false,
    supportsModules:false,supportsSubTypes:false,mentorMode:false,
    problemStatement:visible.question,backgroundKnowledge:JSON.stringify({
      construction:visible.construction,observability:visible.observability,
      buffalo_adjust_profile_sha256:profile.utf8_sha256,
      own_feedback:round==="bf03"?feedback.own_semantic_diagnostics:null
    }),maxTokens:EV01_CAP,timeoutMinutes:7};
  const output=await new Engine().generate(userPrompt,parentModel,parameters);
  await save("native-engine-result.json",output);
  receipt.result_sha256=sha(output);
  receipt.model_returned=Boolean(!output?.err&&Array.isArray(output?.model?.variables)&&
                                 Array.isArray(output?.model?.relationships));
  receipt.native_error=output?.err??null;
  receipt.status=receipt.model_returned?"ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED":"ORIGINAL_ENGINE_NO_NATIVE_MODEL";
  receipt.native_variable_count=output?.model?.variables?.length??null;
  receipt.output_horizon_hours=output?.model?.specs?.stopTime??null;
  if(receipt.output_horizon_hours!==8)fail("OUTPUT_HORIZON_MISMATCH");
}catch(error){
  receipt.runner_error=String(error?.message??error).slice(0,450);
  if(receipt.status==="STARTED")receipt.status="RUNNER_FAILURE";
}finally{
  globalThis.fetch=originals.fetch;
  await save("receipt.json",receipt);
  console.log(JSON.stringify({batch:receipt.batch_id,round:receipt.round_kind,
    status:receipt.status,provider_calls:receipt.provider_calls,
    model_returned:receipt.model_returned,
    http_status:receipt.http_status??null,runner_error:receipt.runner_error}));
  if(!receipt.model_returned||receipt.runner_error)process.exitCode=1;
}
