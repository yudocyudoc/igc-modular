/** Q75: no-credential probe through the ORIGINAL Buffalo Engine.generate SDK.
 * Intercepts the OpenRouter SDK request; converts it using the PINNED EV01
 * Cloudflare adapter, and aborts before ALL HTTP. No native model is claimed.
 */
import {readFile,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {Q75_PROVIDER_MODEL,HISTORICAL_ADAPTER_MODEL,providerEndpoint}
  from '../arena/coffee_q75_buffalo_provider_target.mjs';
const env=process.env;
const need=(v,reason)=>{if(!v)throw new Error('Q75_OFFLINE_SDK_'+reason);};
need(env.COFFEE_Q75_B_INPUT && env.SDAI_ROOT && env.BUFFALO_SCRIPTS_ROOT &&
     env.COFFEE_Q75_B_PROBE_OUT, 'REQUIRED_PATHS_ABSENT');
need(!['CLOUDFLARE_API_TOKEN','OPEN_ROUTER_API_KEY','GH_TOKEN','GITHUB_TOKEN',
        'CT03_R2_ACCESS_KEY_ID','CT03_R2_SECRET_ACCESS_KEY',
        'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY']
     .some(key=>Boolean(env[key])), 'NO_PRIVATE_OR_PROVIDER_CREDENTIALS_ALLOWED');
const input=JSON.parse(await readFile(env.COFFEE_Q75_B_INPUT,'utf8'));
const {OR_SLUG,CF_MODEL:historicalModel,EV01_CAP,EV01_BUDGET_AUTH,requestToCloudflareEV01}=
  await import(pathToFileURL(join(resolve(env.BUFFALO_SCRIPTS_ROOT),
                              'arena_b_ev01_cf_adapter.mjs')).href);
need(input.model===Q75_PROVIDER_MODEL &&
     historicalModel===HISTORICAL_ADAPTER_MODEL &&
     providerEndpoint('a'.repeat(32)).endsWith('/ai/run/'+Q75_PROVIDER_MODEL),
     'TARGET_PROVIDER_MODEL_OR_ENDPOINT_DRIFT');
let intercepted=0, effective=null;
const fetchBefore=globalThis.fetch;
globalThis.fetch=async(request,opts={})=>{
  ++intercepted;
  need(intercepted===1,'SECOND_SDK_INTERCEPTION');
  const url=new URL(typeof request==='string'?request:request.url);
  need(url.origin==='https://openrouter.ai' &&
       url.pathname.endsWith('/chat/completions'),'ORIGINAL_SDK_ENDPOINT_DRIFT');
  let raw=opts.body??(request instanceof Request?await request.text():null);
  if(Buffer.isBuffer(raw))raw=raw.toString('utf8');
  const sdk=JSON.parse(raw);
  need(sdk.model===OR_SLUG && sdk.response_format?.type==='json_schema' &&
       sdk.response_format.json_schema.schema.properties.variables &&
       sdk.response_format.json_schema.schema.properties.relationships &&
       sdk.messages.at(-1)?.content.endsWith(input.prompt),
       'ORIGINAL_ENGINE_DID_NOT_DELIVER_Q75_PROMPT');
  effective=requestToCloudflareEV01(sdk,{authorization:EV01_BUDGET_AUTH});
  need(effective.max_completion_tokens===EV01_CAP &&
       effective.stream===false && effective.reasoning_effort==='low',
       'EFFECTIVE_PROVIDER_REQUEST_BUDGET_DRIFT');
  // HTTP 400 constructed IN MEMORY, never network, so the pinned SDK does
  // not automatically retry a simulated transient fetch/connection failure.
  return new Response(JSON.stringify({error:{
    message:'Q75_OFFLINE_PROBE_EXPECTED_STOP_BEFORE_NETWORK',
    type:'invalid_request_error'}}),{
    status:400,headers:{'content-type':'application/json'}});
};
try {
  env.OPEN_ROUTER_API_KEY='VIRTUAL_OFFLINE_SDK_PROBE_NOT_A_PROVIDER_KEY';
  const {default:Engine}=await import(
    pathToFileURL(join(resolve(env.SDAI_ROOT),'engines/quantitative/engine.js')).href);
  const native=await new Engine().generate(input.prompt,{variables:[],relationships:[]},{
    underlyingModel:OR_SLUG,supportsArrays:false,supportsModules:false,
    supportsSubTypes:false,mentorMode:false,
    problemStatement:input.problemStatement,
    backgroundKnowledge:input.backgroundKnowledge,
    maxTokens:EV01_CAP,timeoutMinutes:7
  });
  void native; // fake failure expected; NO native model or prediction was obtained
} catch (_expected) {
  // The original method may propagate or catch the deliberately aborted HTTP.
} finally {
  globalThis.fetch=fetchBefore;
  delete env.OPEN_ROUTER_API_KEY;
}
need(intercepted===1 && effective!==null, 'ORIGINAL_ENGINE_NEVER_REACHED_EFFECTIVE_SDK');
const result={status:'ORIGINAL_ENGINE_SDK_EFFECTIVE_CLOUDFLARE_REQUEST_VERIFIED_OFFLINE',
  source_request_sha256:input.request_sha256,
  sdk_interceptions:intercepted,actual_provider_posts:0,
  model_native_generated:false,new_omc:0,private_R2_reads:0,
  supportsArrays:false,supportsModules:false,supportsSubTypes:false,
  effective_max_completion_tokens:effective.max_completion_tokens,
  provider_model:Q75_PROVIDER_MODEL,
  historical_sdk_virtual_provider:HISTORICAL_ADAPTER_MODEL,
  cloudflare_effective_request_sha256:'sha256:'+createHash('sha256')
    .update(JSON.stringify(effective)).digest('hex'),
  explicit_transport_abort:true};
await writeFile(env.COFFEE_Q75_B_PROBE_OUT,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(result));
