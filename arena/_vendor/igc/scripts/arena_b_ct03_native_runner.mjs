/** CT-03 Buffalo original quantitative engine -> original OpenRouter SDK ->
 * proven Cloudflare /ai/run transport. New case contract; EV-01 runner untouched.
 * No provider call is authorized by preparing or testing this module.
 */
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {validateCt03Visible,validateCt03Revision,classifyCt03NativeResult}
  from "./arena_b_ct03_contract.mjs";
import {OR_SLUG,CF_MODEL,CF_MODE,digest,responseToOpenRouter,
        requestToCloudflareEV01,cloudflareUrl,EV01_BUDGET_AUTH,
        EV01_CAP,EV01_TIMEOUT_MS,EV01_ADAPTER_VERSION}
  from "./arena_b_ev01_cf_adapter.mjs";

const PIN="5199f7b45f3a7ae4a773cb0dd8542940aabe9edc";
const ORIGIN="UB-IAD/sd-ai";
const mode=process.env.BUFFALO_MODE??"mock";
const round=process.env.BUFFALO_ROUND_KIND??"initial";
const root=resolve(process.env.SDAI_ROOT??"upstream/sd-ai");
const out=resolve(process.env.BUFFALO_OUTPUT??"artifacts/buffalo-ct03");
const input=resolve(process.env.BUFFALO_VISIBLE_INPUT??"artifacts/ct03/b-visible.json");
const sha=x=>digest(x);
const recorded={
  schema:"igc-ct03-b-original-engine-proof/1.0",
  origin:ORIGIN,upstream_sha:PIN,engine:"quantitative",
  mode,provider_model:mode==="live"?CF_MODEL:"OFFLINE_SCHEMA_STUB",
  transport:CF_MODE,adapter_version:EV01_ADAPTER_VERSION,
  original_engine_max_tokens:EV01_CAP,configured_http_timeout_ms:EV01_TIMEOUT_MS,
  backend_alias:OR_SLUG,backend:"OPEN_ROUTER",
  provider_calls:0,proxy_requests:0,
  status:"STARTED",native_error:null,raw_provider_saved:false,
  model_returned:false,quant_schema_seen:false,no_d_or_m_candidate_inputs:true,
  b_real_original_method:"UB-IAD_QUANTITATIVE_ENGINE_UNMODIFIED",
};
const save=(name,obj)=>writeFile(join(out,name),JSON.stringify(obj,null,2)+"\n");
const fail=code=>{throw Error(code);};
const originals={fetch:globalThis.fetch};
let visible,userPrompt,parentModel={variables:[],relationships:[]};
let ownFeedback;
await mkdir(out,{recursive:false});
try{
  if(!["mock","live"].includes(mode))fail("INVALID_MODE");
  if(!["initial","revision"].includes(round))fail("INVALID_ROUND_KIND");
  if(mode==="live" &&
       (process.env.BUFFALO_LIVE_AUTH!=="ONE_UPSTREAM_CALL" ||
        process.env.BUFFALO_CT03_LIVE_AUTH!=="CT03_ONE_ROUND_EXPRESS_AUTH" ||
        process.env.GITHUB_RUN_ATTEMPT!=="1" ||
        process.env.GITHUB_REF!=="refs/heads/experiment/arena-ct00-ct02-20261107"))
    fail("CT03_LIVE_ONE_ROUND_AUTH_REQUIRED");
  visible=JSON.parse(await readFile(input,"utf8"));
  const valid=validateCt03Visible(visible,round);
  const cond=valid.condition;
  recorded.case_id="CT-03";
  recorded.world_public_id=valid.world;
  recorded.condition_id=cond;
  recorded.round_kind=round;
  recorded.source_snapshot_hash=valid.source_hash;
  recorded.input_definition=visible.construction.input;
  recorded.expected_horizon_hours=8;
  userPrompt=visible.question;
  if(round==="revision"){
    const nativeFile=process.env.BUFFALO_PARENT_NATIVE;
    const receiptFile=process.env.BUFFALO_PARENT_RECEIPT;
    const feedbackFile=process.env.BUFFALO_OWN_FEEDBACK;
    if(!nativeFile || !receiptFile || !feedbackFile)
      fail("CT03_B_REVISION_PARENT_AND_OWN_FEEDBACK_REQUIRED");
    const parent=JSON.parse(await readFile(resolve(nativeFile),"utf8"));
    const receipt=JSON.parse(await readFile(resolve(receiptFile),"utf8"));
    const feedbackRaw=await readFile(resolve(feedbackFile),"utf8");
    // Python exported canonical UTF-8 JSON plus exactly one LF. Hash those
    // exact bytes, not JS JSON.stringify (different key order/float spelling).
    if(!feedbackRaw.endsWith("\n") || feedbackRaw.endsWith("\n\n") ||
       feedbackRaw.includes("\r"))
      fail("CT03_B_FEEDBACK_PACKET_CANONICAL_LF_REQUIRED");
    const feedback=JSON.parse(feedbackRaw);
    const feedbackByteSha="sha256:"+createHash("sha256")
      .update(Buffer.from(feedbackRaw.slice(0,-1),"utf8")).digest("hex");
    const checked=validateCt03Revision({
      native:parent,receipt,feedback,visible,mode
    });
    parentModel=checked.model;
    ownFeedback=checked.feedback;
    recorded.parent_native_sha256=receipt.result_sha256;
    recorded.own_feedback_sha256=feedbackByteSha;
    userPrompt=visible.question+"\\n\\nReconsider YOUR own previous Buffalo model "+
      "(provided as currentModel), using ONLY the following observed "+
      "construction diagnostic:\\n"+JSON.stringify(ownFeedback.own_diagnostic)+
      "\\nDecide whether to revise or explicitly retain. Do not use "+
      "hidden evaluation times, true model parameters, other arms or "+
      "undocumented functions. Do not assume finite buffers or FIFO servers.";
    await save("own-feedback-sent.json",ownFeedback);
  }
  // Intercept the ORIGINAL upstream OpenRouter SDK, as in R2 16K.
  globalThis.fetch=async function intercept(request,init={}){
    recorded.proxy_requests++;
    const url=new URL(typeof request==="string"?request:request.url);
    const method=init.method??(request instanceof Request?request.method:"GET");
    if(url.origin!=="https://openrouter.ai"||
       !url.pathname.endsWith("/chat/completions")||
       method.toUpperCase()!=="POST")
      fail("CT03_UNEXPECTED_OUTBOUND_HTTP:"+url.origin+url.pathname);
    if(recorded.proxy_requests!==1)fail("CT03_ONE_PROVIDER_CALL_PER_ROUND_GATE");
    let bodyText=init.body??(request instanceof Request?await request.text():null);
    if(typeof bodyText!=="string")
      bodyText=Buffer.isBuffer(bodyText)?bodyText.toString("utf8"):String(bodyText??"");
    const body=JSON.parse(bodyText);
    if(body.model!==OR_SLUG)fail("CT03_WRONG_OPENROUTER_SDK_BACKEND");
    if(body.response_format?.type!=="json_schema")
      fail("CT03_NATIVE_SCHEMA_MISSING");
    const schema=body.response_format.json_schema?.schema;
    if(!schema?.properties?.variables||!schema?.properties?.relationships)
      fail("CT03_NATIVE_QUANTITATIVE_SCHEMA_MISSING");
    if(round==="revision"){
      const serialized=JSON.stringify(parentModel,null,2);
      if(!body.messages.some(m=>m.role==="assistant"&&m.content===serialized))
        fail("CT03_OWN_CURRENTMODEL_NOT_PRESENT_IN_SDK");
      if(body.messages.at(-1)?.role!=="user"||
         !body.messages.at(-1)?.content.endsWith(userPrompt))
        fail("CT03_OWN_FEEDBACK_NOT_IN_SDK_MESSAGES");
      recorded.parent_as_original_currentModel=true;
    }
    recorded.quant_schema_seen=true;
    recorded.request_sha256=sha(body);
    recorded.schema_sha256=sha(schema);
    recorded.message_roles=body.messages.map(m=>m.role);
    const cfBody=requestToCloudflareEV01(body,{authorization:EV01_BUDGET_AUTH});
    if(cfBody.max_completion_tokens!==16000||
       cfBody.reasoning_effort!=="low"||
       cfBody.stream!==false)
      fail("CT03_CF_ADAPTER_BUDGET_OR_REASONING_MISMATCH");
    recorded.translated_body_sha256=sha(cfBody);
    recorded.cloudflare_schema_sha256=sha(cfBody.response_format.json_schema);
    recorded.actual_endpoint="Workers AI /ai/run/{model}";
    await save("request-metadata.json",{
      source:"UNMODIFIED_UPSTREAM_OPENROUTER_SDK",
      original_alias_model:OR_SLUG,request_sha256:recorded.request_sha256,
      schema_sha256:recorded.schema_sha256,
      prompt_hashes:body.messages.map(m=>({role:m.role,sha256:sha(m.content)})),
      original_upstream_modified:false,
      round_kind:round,
      backend:"OPEN_ROUTER"
    });
    await save("cf-effective-request.json",{
      target_endpoint:recorded.actual_endpoint,actual_model:CF_MODEL,
      body:cfBody,body_sha256:recorded.translated_body_sha256,
      source_request_sha256:recorded.request_sha256,
      no_credentials_serialized:true
    });
    let raw;
    if(mode==="mock"){
      raw={success:true,result:{response:{
        specs:{startTime:0,stopTime:8,dt:0.125,timeUnits:"Hour",integrationMethod:"Euler"},
        variables:[
          {name:"Arrivals",type:"flow",units:"items/hour",inflows:[],outflows:[],
           equation:"if TIME < 2 then 1.7 else 0",uniflow:true,graphicalFunction:{points:[]},documentation:"Offline input."},
          {name:"Completions",type:"flow",units:"items/hour",inflows:[],outflows:[],
           equation:"MIN(2, Backlog / 1)",uniflow:true,graphicalFunction:{points:[]},documentation:"Offline completion."},
          {name:"Backlog",type:"stock",units:"items",inflows:[],outflows:[],
           equation:"0",uniflow:false,graphicalFunction:{points:[]},documentation:"Offline outstanding."},
          {name:"Completed",type:"stock",units:"items",inflows:["Completions"],outflows:[],
           equation:"0",uniflow:false,graphicalFunction:{points:[]},documentation:"Offline total."}
        ],
        relationships:[
          {from:"Arrivals",to:"Backlog",reasoning:"Material inflow",polarity:"+",polarityReasoning:"Adds."},
          {from:"Completions",to:"Backlog",reasoning:"Material outflow",polarity:"-",polarityReasoning:"Subtracts."},
          {from:"Completions",to:"Completed",reasoning:"Material inflow",polarity:"+",polarityReasoning:"Adds."}
        ],
        explanation:"OFFLINE FIXTURE NOT BUFFALO INFERENCE",title:"Offline stub"
      },usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0}}};
      recorded.inference_source="OFFLINE_WORKERS_AI_PROTOCOL_FIXTURE";
    }else{
      const account=process.env.CLOUDFLARE_ACCOUNT_ID;
      const token=process.env.CLOUDFLARE_API_TOKEN;
      if(!token)fail("CT03_MISSING_CLOUDFLARE_SECRETS");
      const endpoint=cloudflareUrl(account);
      recorded.provider_calls++;
      recorded.inference_source="REAL_CLOUDFLARE_WORKERS_AI";
      await save("cf-call-started.json",{model:CF_MODEL,
        calls_started:recorded.provider_calls,
        effective_body_sha256:recorded.translated_body_sha256,
        timestamp:new Date().toISOString()});
      const response=await originals.fetch(endpoint,{
        method:"POST",headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},
        body:JSON.stringify(cfBody),signal:AbortSignal.timeout(EV01_TIMEOUT_MS)
      });
      recorded.http_status=response.status;
      const rawText=await response.text();
      try{raw=JSON.parse(rawText)}catch{
        await save("cf-nonjson-error.json",{http_status:response.status,
          body_sha256:sha(rawText),size:rawText.length});
        fail("CT03_CLOUDFLARE_NON_JSON");
      }
      await save("provider-raw.json",raw);
      recorded.raw_provider_saved=true;
      if(!response.ok)fail("CT03_CLOUDFLARE_HTTP_"+response.status);
    }
    recorded.provider_usage=raw?.result?.usage??raw?.usage??null;
    recorded.provider_finish_reason=raw?.result?.choices?.[0]?.finish_reason??null;
    const envelope=responseToOpenRouter(raw,recorded.request_sha256);
    recorded.compatibility_envelope_synthesized=true;
    recorded.generated_content_sha256=sha(envelope.choices[0].message.content);
    await save("openrouter-compat-envelope.json",envelope);
    return new Response(JSON.stringify(envelope),{status:200,
      headers:{"content-type":"application/json"}});
  };
  process.env.OPEN_ROUTER_API_KEY="IGC_LOCAL_ONLY_NOT_REAL_OPENROUTER_KEY";
  const {default:Engine}=await import(pathToFileURL(join(root,"engines/quantitative/engine.js")).href);
  const engine=new Engine();
  const parameters={
    underlyingModel:OR_SLUG,
    supportsArrays:false,supportsModules:false,supportsSubTypes:false,mentorMode:false,
    problemStatement:visible.question,
    backgroundKnowledge:JSON.stringify({construction:visible.construction,
      observability:visible.observability,
      own_feedback:ownFeedback?.diagnostic??null}),
    maxTokens:EV01_CAP,timeoutMinutes:7
  };
  const output=await engine.generate(userPrompt,parentModel,parameters);
  await save("native-engine-result.json",output);
  recorded.result_sha256=sha(output);
  recorded.model_returned=output?.success===undefined &&
    Array.isArray(output?.model?.variables)&&
    Array.isArray(output?.model?.relationships);
  recorded.native_error=output?.err??null;
  if(recorded.model_returned){
    recorded.variable_count=output.model.variables.length;
    recorded.relationship_count=output.model.relationships.length;
    recorded.inferred_inflow_by_buffalo=output.model.variables.find(
      v=>v.name==="Backlog")?.inflows??null;
    recorded.status=mode==="mock"?
       "ORIGINAL_ENGINE_OFFLINE_PATH_PASS":
       "ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED";
  }else{
    recorded.status="ORIGINAL_ENGINE_NO_NATIVE_MODEL";
  }
  recorded.llm_wrapper_schema_was_sent=recorded.quant_schema_seen;
  recorded.output_horizon_hours=output?.model?.specs?.stopTime??null;
  recorded.horizon_matches_case=recorded.model_returned?
    Math.abs(recorded.output_horizon_hours-8)<1e-8:false;
  if(recorded.model_returned&&!recorded.horizon_matches_case)
    recorded.status="CT03_NATIVE_HORIZON_NOT_COMPARABLE";
  recorded.upstream_source_modified=false;
  if(mode==="mock" &&
     !recorded.inferred_inflow_by_buffalo?.includes("Arrivals"))
    fail("CT03_ORIGINAL_UPSTREAM_POSTPROCESS_NOT_EXERCISED");
}catch(err){
  recorded.runner_error=String(err?.message??err).slice(0,450);
  if(recorded.status==="STARTED")recorded.status="RUNNER_FAILURE";
}finally{
  globalThis.fetch=originals.fetch;
  Object.assign(recorded,classifyCt03NativeResult(recorded));
  await save("receipt.json",recorded);
  console.log(JSON.stringify({status:recorded.status,mode:recorded.mode,
    transport:recorded.transport,backend:recorded.backend,
    provider_calls:recorded.provider_calls,model_returned:recorded.model_returned,
    runner_error:recorded.runner_error,http_status:recorded.http_status??null}));
  if(!recorded.model_returned||recorded.runner_error||
     recorded.status==="CT03_NATIVE_HORIZON_MISMATCH")process.exitCode=1;
}
