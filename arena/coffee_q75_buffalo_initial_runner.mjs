/** Q75 one original Buffalo initial generation. Explicit manual authorization.
 * EXACT one SDK interception / at most one Cloudflare POST; no R2, OMC or retry.
 * Not adapted from CT03 B0 prompt; it reads the authenticated Q75 new prompt.
 */
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const env=process.env;
const need=(v,id)=>{if(!v)throw Error('Q75_B_INITIAL_'+id);};
const hash=x=>'sha256:'+createHash('sha256').update(x).digest('hex');
const save=(p,o)=>writeFile(join(out,p),JSON.stringify(o,null,2)+'\n',{flag:'wx'});
need(env.COFFEE_Q75_B_INITIAL_AUTH==='yes' &&
     env.GITHUB_REPOSITORY==='yudocyudoc/igc-modular' &&
     env.GITHUB_REF==='refs/heads/main' &&
     env.GITHUB_EVENT_NAME==='workflow_dispatch' &&
     env.GITHUB_RUN_ATTEMPT==='1' &&
     /^\d+$/.test(env.GITHUB_RUN_ID??'') &&
     /^[0-9a-f]{40}$/.test(env.GITHUB_SHA??'') &&
     env.GITHUB_WORKFLOW_REF?.endsWith(
       '/.github/workflows/coffee-q75-buffalo-initial-manual.yml@refs/heads/main') &&
     env.CLOUDFLARE_API_TOKEN &&
     /^[0-9a-fA-F]{32}$/.test(env.CLOUDFLARE_ACCOUNT_ID??''),
     'EXPLICIT_MANUAL_AUTH_AND_PROVIDER_REQUIRED');
need(!['CT03_R2_ACCESS_KEY_ID','CT03_R2_SECRET_ACCESS_KEY',
       'COFFEE_R2_ACCESS_KEY_ID','COFFEE_R2_SECRET_ACCESS_KEY',
       'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','GH_TOKEN','GITHUB_TOKEN',
       'OPEN_ROUTER_API_KEY'].some(k=>Boolean(env[k])),
     'PRIVATE_OR_UNAUTHORIZED_CREDENTIALS');
const inputBytes=await readFile(env.COFFEE_Q75_B_INPUT);
const input=JSON.parse(inputBytes.toString('utf8'));
const attempt=JSON.parse(await readFile(env.COFFEE_Q75_B_ATTEMPT,'utf8'));
const caseView=JSON.parse(input.backgroundKnowledge).construction;
const profile=input.original_engine_effective_option_profile;
need(attempt.request_file_sha256===hash(inputBytes) &&
     caseView.aggregate_beverage_mix_from_public_Q75.milk_required_beverages===33 &&
     caseView.aggregate_beverage_mix_from_public_Q75.no_milk_required_beverages===20 &&
     caseView.aggregate_clean_tasks_completed_in_archived_Q75===0 &&
     caseView.physical.clean_after_every_beverage_assumed===false &&
     caseView.physical.cleaning_stage_resource_requirement_from_hydra.join(',')==='barista,espresso_group' &&
     input.prompt.includes('33 require milk on W01') &&
     input.prompt.includes('DOES NOT clean the espresso group') &&
     profile.supportsArrays===false && profile.supportsModules===false &&
     profile.supportsSubTypes===false && profile.mentorMode===false &&
     profile.maxTokens===16000 &&
     profile.scope==='ORIGINAL_BUFFALO_HISTORICAL_SCALAR_NO_NATIVE_QUEUE_SUBTYPES',
     'REQUEST_BYTES_OR_Q75_MIX_OR_ENGINE_PROFILE_DRIFT');
need(input.schema==='arena.coffee.q75-buffalo-original-initial/1' &&
     input.round_kind==='initial' && input.parent_model===null &&
     input.original_B0_R1_reused===false &&
     input.max_provider_posts===1 && input.max_completion_tokens===16000 &&
     input.model==='@cf/zai-org/glm-5.3-flash' &&
     input.new_omc===0 && input.new_private_R2_gets===0 &&
     input.rival_model_or_Hydra_result_sent===false &&
     input.provider_status==='NOT_SENT' &&
     attempt.status==='RESERVED_BEFORE_HTTP' &&
     attempt.run_id===Number(env.GITHUB_RUN_ID) &&
     attempt.run_sha===env.GITHUB_SHA &&
     attempt.original_request_sha256===input.request_sha256 &&
     attempt.posts_max===1 && attempt.no_retry===true,
     'PARENT_SOURCE_OR_SPEND_CONTRACT_MISMATCH');
const scripts=resolve(env.BUFFALO_SCRIPTS_ROOT);
const sdai=resolve(env.SDAI_ROOT);
const out=resolve(env.COFFEE_Q75_B_OUT);
const {OR_SLUG,CF_MODEL,CF_MODE,EV01_CAP,EV01_TIMEOUT_MS,
       EV01_BUDGET_AUTH,requestToCloudflareEV01,
       responseToOpenRouter,cloudflareUrl}=
 await import(pathToFileURL(join(scripts,'arena_b_ev01_cf_adapter.mjs')).href);
need(CF_MODEL===input.model && EV01_CAP===16000,'VERSIONED_PROVIDER_CAP_DRIFT');
const originalFetch=globalThis.fetch;
await mkdir(out,{recursive:false});
const receipt={
  schema:'arena.coffee.q75-buffalo-original-initial-receipt/1',
  run_id:Number(env.GITHUB_RUN_ID),run_sha:env.GITHUB_SHA,
  original_request_sha256:input.request_sha256,
  original_engine:'UB-IAD/sd-ai::Engine.generate',round_kind:'initial',
  currentModel_supplied:false,
  original_engine_effective_option_profile:profile,
  native_queue_subtypes_enabled:false,
  only_historical_scalar_profile_tested:true,
  request_file_sha256:hash(inputBytes),
  provider_model:CF_MODEL,transport:CF_MODE,
  sdk_interceptions:0,provider_posts:0,
  raw_provider_saved:false,model_returned:false,
  provider_usage:null,status:'STARTED',retries:0,
  new_omc:0,private_R2_access:false,
  no_rival_answers:true,not_real_shop_validation:true,
};
let success=false;
try {
  globalThis.fetch=async(request,init={})=>{
    receipt.sdk_interceptions++;
    need(receipt.sdk_interceptions===1,'SECOND_SDK_REQUEST_BLOCKED');
    const url=new URL(typeof request==='string'?request:request.url);
    const method=init.method??(request instanceof Request?request.method:'GET');
    need(url.origin==='https://openrouter.ai' &&
         url.pathname.endsWith('/chat/completions') &&
         method.toUpperCase()==='POST','UNAUTHORIZED_SDK_ENDPOINT');
    let body=init.body??(request instanceof Request?await request.text():null);
    if(Buffer.isBuffer(body))body=body.toString('utf8');
    need(typeof body==='string','SDK_BODY_NOT_TEXT');
    const sdk=JSON.parse(body);
    need(sdk.model===OR_SLUG &&
         sdk.response_format?.type==='json_schema' &&
         sdk.response_format?.json_schema?.schema?.properties?.variables &&
         sdk.response_format?.json_schema?.schema?.properties?.relationships &&
         Array.isArray(sdk.messages) &&
         sdk.messages.some(m=>typeof m.content==='string' &&
                             m.content.includes(input.problemStatement)) &&
         sdk.messages.at(-1)?.role==='user' &&
         sdk.messages.at(-1)?.content.endsWith(input.prompt),
         'ORIGINAL_SDK_PROMPT_NOT_Q75_OR_SCHEMA_MISSING');
    // The old B0 parent is not a valid initial currentModel. Empty start only.
    const assistant=sdk.messages.filter(m=>m.role==='assistant');
    need(assistant.length<=1 &&
         assistant.every(m=>m.content==='{}' ||
                         m.content===JSON.stringify({variables:[],relationships:[]},null,2)),
         'NONEMPTY_CURRENTMODEL_FOR_INITIAL_GENERATION');
    receipt.sdk_request_sha256=hash(JSON.stringify(sdk));
    const cfBody=requestToCloudflareEV01(sdk,{authorization:EV01_BUDGET_AUTH});
    need(cfBody.max_completion_tokens===EV01_CAP &&
         cfBody.stream===false && cfBody.reasoning_effort==='low',
         'PROVIDER_CEILING_BYPASS');
    receipt.effective_request_sha256=hash(JSON.stringify(cfBody));
    await save('sdk-request.json',sdk);
    await save('cloudflare-effective-request.json',{
      model:CF_MODEL,body:cfBody,credentials_excluded:true});
    // One reservation is definitive even if the request times out or fails.
    receipt.provider_posts=1;
    await save('cf-call-started.json',{
      status:'REQUEST_MAY_HAVE_CONSUMED',run_id:receipt.run_id,
      effective_request_sha256:receipt.effective_request_sha256,
      no_retry:true,max_posts:1});
    const response=await originalFetch(cloudflareUrl(env.CLOUDFLARE_ACCOUNT_ID),{
      method:'POST',headers:{authorization:'Bearer '+env.CLOUDFLARE_API_TOKEN,
                             'content-type':'application/json'},
      body:JSON.stringify(cfBody),signal:AbortSignal.timeout(EV01_TIMEOUT_MS)});
    receipt.http_status=response.status;
    const rawText=await response.text();
    let raw;
    try {raw=JSON.parse(rawText);}catch {
      await save('provider-nonjson.json',{
        http_status:response.status,bytes:rawText.length,sha256:hash(rawText)});
      need(false,'NONJSON_PROVIDER_REPLY');
    }
    await save('provider-raw.json',raw);
    receipt.raw_provider_saved=true;
    receipt.provider_usage=raw?.result?.usage??raw?.usage??null;
    need(response.ok,'NON_200_PROVIDER_RESPONSE');
    const envelope=responseToOpenRouter(raw,receipt.sdk_request_sha256);
    await save('openrouter-compat-envelope.json',envelope);
    return new Response(JSON.stringify(envelope),{
      status:200,headers:{'content-type':'application/json'}});
  };
  env.OPEN_ROUTER_API_KEY='VIRTUAL_ORIGINAL_SDK_NO_OPENROUTER_POST';
  const {default:Engine}=await import(
    pathToFileURL(join(sdai,'engines/quantitative/engine.js')).href);
  const initial={variables:[],relationships:[]};
  const native=await new Engine().generate(input.prompt,initial,{
    underlyingModel:OR_SLUG,supportsArrays:false,supportsModules:false,
    supportsSubTypes:false,mentorMode:false,
    problemStatement:input.problemStatement,
    backgroundKnowledge:input.backgroundKnowledge,
    maxTokens:EV01_CAP,timeoutMinutes:7,
  });
  await save('native-engine-result.json',native);
  receipt.native_sha256=hash(JSON.stringify(native));
  receipt.model_returned=Boolean(!native?.err &&
      Array.isArray(native?.model?.variables) &&
      Array.isArray(native?.model?.relationships));
  receipt.status=receipt.model_returned?
     'ORIGINAL_ENGINE_INITIAL_G1_ONLY_NOT_POLICY_P90':
     'ORIGINAL_ENGINE_NO_NATIVE_MODEL';
  success=receipt.model_returned;
} catch(_err) {
  receipt.status='FAILURE_OR_CONSUMPTION_UNCERTAIN';
  receipt.reason='REDACTED_NO_RETRY';
} finally {
  globalThis.fetch=originalFetch;
  delete env.OPEN_ROUTER_API_KEY;
  await save('receipt.json',receipt);
  console.log(JSON.stringify({status:receipt.status,
    provider_posts:receipt.provider_posts,model_returned:receipt.model_returned,
    new_omc:0,no_retry:true}));
  if(!success)process.exitCode=1;
}
