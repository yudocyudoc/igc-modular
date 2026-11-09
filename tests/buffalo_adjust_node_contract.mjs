/** True original Engine.generate offline integration with mocked Workers AI REST.
 * Never allows network: global fetch is replaced before importing the adapter.
 * The fixture is software-only and is NEVER submitted as Buffalo's scientific output.
 */
import {mkdtemp,mkdir,readFile,writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import assert from "node:assert/strict";

const mode=process.argv[2];
const workspace=resolve(process.argv[3]??"");
assert(["bf03","bf04"].includes(mode),"Only dry BF03 or BF04 mode.");
assert(process.env.CLOUDFLARE_API_TOKEN===undefined,
       "Offline contract must not receive any provider secret.");
const repo=resolve(".");
const tmp=await mkdtemp(join(process.env.RUNNER_TEMP??tmpdir(),"bf-adjust-test-"));
const input=join(tmp,"visible.json");
const profile=join(tmp,"profile.json");
const feedback=join(tmp,"feedback.json");
const parent=join(tmp,"parent.json");
const output=join(tmp,"output");
const hash="sha256:"+"a".repeat(64);
const world="PUBLIC_TEST";
const question="Build a quantitative aggregate stock-flow model for conserved work items, using only four public observations.";
const visible={
  schema:"igc-ct03-b-visible/1.0",case_id:"CT-03",arm:"B",
  round_id:"ct03-b-"+(mode==="bf03"?"revision":"initial"),
  source_snapshot_hash:hash,world_public_id:world,condition_id:"C0",question,
  construction:{
    input:{pulse_rate:1.7,pulse_start:0,pulse_end:2,total_mass:3.4,
      unit:"items/hour",horizon_hours:8,integration_step_hours:0.125},
    observations:[{time:0,delivered:0},{time:1,delivered:0.1},
      {time:2,delivered:0.5},{time:4,delivered:1.7}],
    observation_times_hours:[0,1,2,4]
  },
  observability:{quantity_unit:"items",time_unit:"hours",
    observable:"cumulative_delivered",construction_times_hours:[0,1,2,4],
    horizon_hours:8}
};
const text="Offline integration test profile. No scientific model generated here.";
const prof={id:"buffalo-adjust-v1",text,
  utf8_sha256:"sha256:"+createHash("sha256").update(text).digest("hex")};
const own={profile_sha256:prof.utf8_sha256,world_public_id:world,
  source_snapshot_hash:hash,own_semantic_diagnostics:{diagnostics:[]},
  parent_native_sha256:"sha256:"+"b".repeat(64)};
const response={
  specs:{startTime:0,stopTime:8,dt:0.125,timeUnits:"Hour",
         integrationMethod:"Euler"},
  variables:[
    {name:"Arrivals",type:"flow",units:"items/hour",inflows:[],outflows:[],
     equation:"1.7",uniflow:true,graphicalFunction:{points:[]},
     documentation:"Mock source input."},
    {name:"Completions",type:"flow",units:"items/hour",inflows:[],outflows:[],
     equation:"MIN(2, Backlog / 1)",uniflow:true,graphicalFunction:{points:[]},
     documentation:"Mock completion."},
    {name:"Backlog",type:"stock",units:"items",inflows:[],outflows:[],
     equation:"0",uniflow:false,graphicalFunction:{points:[]},
     documentation:"Mock work."},
    {name:"Completed",type:"stock",units:"items",inflows:["Completions"],outflows:[],
     equation:"0",uniflow:false,graphicalFunction:{points:[]},
     documentation:"Mock cumulative."}
  ],
  relationships:[
    {from:"Arrivals",to:"Backlog",reasoning:"Material inflow",polarity:"+",
     polarityReasoning:"Adds."},
    {from:"Completions",to:"Backlog",reasoning:"Material outflow",polarity:"-",
     polarityReasoning:"Subtracts."},
    {from:"Completions",to:"Completed",reasoning:"Material inflow",polarity:"+",
     polarityReasoning:"Adds."}
  ],
  explanation:"OFFLINE FIXTURE: not Buffalo inference",title:"Offline fixture"
};
await writeFile(input,JSON.stringify(visible));
await writeFile(profile,JSON.stringify(prof));
await writeFile(feedback,JSON.stringify(own));
await writeFile(parent,JSON.stringify({model:response,supportingInfo:{}}));
process.env.GITHUB_EVENT_NAME="workflow_dispatch";
process.env.GITHUB_RUN_ATTEMPT="1";
process.env.GITHUB_REF="refs/heads/main";
process.env.GITHUB_SHA="f".repeat(40);
process.env.GITHUB_RUN_ID="99999991";
process.env.BUFFALO_ADJUST_AUTH="yes";
process.env.BUFFALO_ADJUST_ROUND=mode;
process.env.SDAI_ROOT=join(workspace,"upstream/sd-ai");
process.env.BUFFALO_SCRIPTS_ROOT=join(workspace,"scripts");
process.env.BUFFALO_ADJUST_OUTPUT=output;
process.env.BUFFALO_VISIBLE_INPUT=input;
process.env.BUFFALO_PROFILE_INPUT=profile;
process.env.BUFFALO_PARENT_NATIVE=parent;
process.env.BUFFALO_OWN_FEEDBACK=feedback;
process.env.CLOUDFLARE_ACCOUNT_ID="a".repeat(32);
process.env.CLOUDFLARE_API_TOKEN="FAKE_LOCAL_ONLY_NO_NETWORK_TOKEN";
let sent=0;
const mockedProvider=async (url,init)=>{
  sent+=1;
  assert.equal(sent,1,"exactly one actual adapter fetch");
  assert.equal(new URL(url).hostname,"api.cloudflare.com");
  assert.equal(init.method,"POST");
  assert.equal(init.headers.Authorization,"Bearer FAKE_LOCAL_ONLY_NO_NETWORK_TOKEN");
  const body=JSON.parse(init.body);
  assert.equal(body.max_completion_tokens,16000);
  assert.equal(body.reasoning_effort,"low");
  assert.equal(body.stream,false);
  assert.equal(body.response_format.type,"json_schema");
  assert(body.messages.some(m=>m.content.includes(prof.text)));
  if(mode==="bf03"){
    assert(body.messages.some(m=>m.role==="assistant"));
    assert(body.messages.some(m=>m.content.includes("own semantic diagnostic")||
                             m.content.includes("semantic diagnostic")));
  }else{
    assert(!body.messages.some(m=>m.role==="assistant"),"bf04 must not inherit parent");
  }
  return new Response(JSON.stringify({
    success:true,
    result:{response,usage:{prompt_tokens:100,completion_tokens:100,total_tokens:200},
            choices:[{message:{content:JSON.stringify(response)},finish_reason:"stop"}]}
  }),{status:200,headers:{"content-type":"application/json"}});
};
// Intercept at transport boundary without modifying any vendored code.
// The production runner captures this fake as "originals.fetch".
globalThis.fetch=mockedProvider;
await import(pathToFileURL(join(repo,"arena/buffalo/original_runner.mjs")).href);
const receipt=JSON.parse(await readFile(join(output,"receipt.json"),"utf8"));
assert.equal(sent,1);
assert.equal(receipt.provider_calls,1);
assert.equal(receipt.proxy_requests,1);
assert.equal(receipt.generation_profile_sha256,prof.utf8_sha256);
assert.equal(receipt.http_status,200);
assert.equal(receipt.model_returned,true,
  "original Engine.generate should have returned native using mock JSON response");
assert.equal(receipt.status,"ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED");
assert.equal(receipt.round_kind,mode);
if(mode==="bf03")assert.equal(receipt.parent_native_sha256,own.parent_native_sha256);
else assert.equal(receipt.parent_native_sha256,undefined);
const native=JSON.parse(await readFile(join(output,"native-engine-result.json"),"utf8"));
assert(native.model.variables?.length>=1);
assert(native.model.relationships?.length>=1);
console.log(JSON.stringify({dry_original_engine:true,phase:mode,
  sdk_generated_native:true,mocked_transport_calls:sent,real_network_calls:0,
  completion_token_cap:16000}));
