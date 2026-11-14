/** Offline proof that coffee R1 sends its EXACT currentModel to ORIGINAL SDK.
 * Mocked Cloudflare transport, zero real provider requests. Same runner
 * module as the paid workflow; no alternative implementation of Engine.
 */
import {mkdtemp,mkdir,writeFile,readFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import assert from "node:assert/strict";

const ws=resolve(process.argv[2]??"");
const root=await mkdtemp(join(process.env.RUNNER_TEMP??tmpdir(),"coffee-b-review-test-"));
const out=join(root,"provider");
const sha="a".repeat(40);
const run=991234;
const caseSha="sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f";
const dt=(103.237/60)/64;
const variable=(name,type,equation,units,ins=[],outs=[])=>({
  name,type,equation,units,inflows:ins,outflows:outs,
  graphicalFunction:{points:[]},uniflow:type==="flow",documentation:"Offline test"});
const response={
  specs:{startTime:0,stopTime:103.237/60,dt,timeUnits:"hour",integrationMethod:"Euler"},
  variables:[
    variable("Paid Rate","flow","10","orders/hour"),
    variable("Pickup Rate","flow","MIN(10, Backlog / 0.1)","orders/hour"),
    variable("Backlog","stock","0","orders",["Paid Rate"],["Pickup Rate"]),
    variable("Delivered","stock","0","orders",["Pickup Rate"])
  ],
  relationships:[
    {from:"Paid Rate",to:"Backlog",reasoning:"inflow",polarity:"+",polarityReasoning:"adds"},
    {from:"Pickup Rate",to:"Backlog",reasoning:"outflow",polarity:"-",polarityReasoning:"drains"},
    {from:"Pickup Rate",to:"Delivered",reasoning:"inflow",polarity:"+",polarityReasoning:"adds"}
  ],
  explanation:"OFFLINE fixture only",title:"Coffee R1 offline test"
};
const currentModel=JSON.parse(JSON.stringify(response));
currentModel.variables[0].name="Old Paid Rate";
currentModel.variables[0].type="variable";
const originalPrompt="Public coffee orders, review own parent.";
const problem="Unknown pickups per paid order.";
const background="Public only, no observed future pickups.";
const input={
  schema:"arena.coffee-peak.buffalo-own-review-input/1",
  round_kind:"revision",run_id:run,run_sha:sha,
  case_sha256:caseSha,source_model_sha256:"sha256:"+"b".repeat(64),
  feedback_diagnostic_sha256:"sha256:"+"c".repeat(64),
  feedback_run_id:43561168032,
  parent_live_run_id:43537333254,
  max_provider_posts:1,
  prompt:originalPrompt,problemStatement:problem,
  backgroundKnowledge:background,currentModel,
  new_omc:0,truth_access:false,r2_access:false,
  scientific_lock_created:false
};
const admission={
  execution_run:run,execution_sha:sha,case_sha256:caseSha,
  parent_sha256:input.source_model_sha256,
  feedback_diagnostic_sha256:input.feedback_diagnostic_sha256,
  as_of_replayed:true
};
const attempt={
  state:"RESERVED_BEFORE_HTTP",run_id:run,sha,
  no_retry:true,max_posts:1
};
for(const [name,contents] of [
  ["input.json",input],["admission.json",admission],["attempt.json",attempt]
]) await writeFile(join(root,name),JSON.stringify(contents));
const env=process.env;
Object.assign(env,{
  COFFEE_B_REVIEW_AUTH:"yes",GITHUB_REPOSITORY:"yudocyudoc/igc-modular",
  GITHUB_REF:"refs/heads/main",GITHUB_EVENT_NAME:"workflow_dispatch",
  GITHUB_RUN_ATTEMPT:"1",GITHUB_SHA:sha,GITHUB_RUN_ID:String(run),
  CLOUDFLARE_ACCOUNT_ID:"a".repeat(32),
  CLOUDFLARE_API_TOKEN:"FAKE_LOCAL_ONLY_DO_NOT_SEND",
  COFFEE_B_REVIEW_OUT:out,
  COFFEE_B_REVIEW_INPUT:join(root,"input.json"),
  COFFEE_B_REVIEW_ADMISSION:join(root,"admission.json"),
  COFFEE_B_REVIEW_ATTEMPT:join(root,"attempt.json"),
  SDAI_ROOT:join(ws,"upstream/sd-ai"),
  BUFFALO_SCRIPTS_ROOT:join(ws,"scripts")
});
for(const k of ["GH_TOKEN","GITHUB_TOKEN","OPEN_ROUTER_API_KEY",
    "CT03_R2_ACCESS_KEY_ID","CT03_R2_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY"])delete env[k];
let sent=0;
globalThis.fetch=async (url,init)=>{
  sent++;
  assert.equal(sent,1);
  assert.equal(new URL(url).hostname,"api.cloudflare.com");
  assert.equal(init.method,"POST");
  assert.equal(init.headers.Authorization,"Bearer FAKE_LOCAL_ONLY_DO_NOT_SEND");
  const actual=JSON.parse(init.body);
  assert(actual.messages?.filter(m=>m.role==="assistant").length===1);
  assert(actual.messages.some(m=>m.role==="assistant" &&
     m.content===JSON.stringify(currentModel,null,2)));
  assert(actual.messages.at(-1)?.content.endsWith(originalPrompt));
  assert(actual.messages.some(m=>m.content.includes(background)));
  assert.equal(actual.max_completion_tokens,16000);
  assert.equal(actual.reasoning_effort,"low");
  assert.equal(actual.stream,false);
  return new Response(JSON.stringify({
    success:true,
    result:{response,usage:{prompt_tokens:88,completion_tokens:77,total_tokens:165},
      choices:[{message:{content:JSON.stringify(response)},finish_reason:"stop"}]}
  }),{status:200,headers:{"content-type":"application/json"}});
};
await import(pathToFileURL(resolve("arena/buffalo/coffee_review_runner.mjs")).href);
const receipt=JSON.parse(await readFile(join(out,"receipt.json"),"utf8"));
assert.equal(receipt.sdk_interceptions,1);
assert.equal(receipt.provider_posts,1);
assert.equal(receipt.original_current_model_in_sdk_request,true);
assert.equal(receipt.model_returned,true);
assert.equal(receipt.status,"ORIGINAL_ENGINE_OWN_REVIEW_RETURNED_G1_ONLY");
const native=JSON.parse(await readFile(join(out,"native-engine-result.json"),"utf8"));
assert.equal(native.model.specs.stopTime,103.237/60);
assert.equal(native.model.variables[0].type,"flow");
console.log(JSON.stringify({mocked_original_review:true,
  sdk_currentModel_is_exact_parent:true,simulated_cloudflare_posts:sent,
  real_provider_posts:0,omc:0,truth_access:false}));
