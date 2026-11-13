/** One real Cloudflare POST through original Engine.generate, never a fixture.
 * Requires separate Python admission and a pre-HTTP attempt reservation.
 */
import {readFile, mkdir, writeFile} from "node:fs/promises";
import {resolve, join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";

const h = x => "sha256:" + createHash("sha256")
  .update(typeof x === "string" ? x : JSON.stringify(x)).digest("hex");
const fail = reason => {throw Error("COFFEE_B_LIVE_" + reason);};
const require_ = (ok, reason) => {if (!ok) fail(reason);};
const env = process.env;
require_(env.COFFEE_B_LIVE_AUTH === "yes" &&
  env.GITHUB_EVENT_NAME === "workflow_dispatch" &&
  env.GITHUB_REPOSITORY === "yudocyudoc/igc-modular" &&
  env.GITHUB_REF === "refs/heads/main" && env.GITHUB_RUN_ATTEMPT === "1" &&
  /^[0-9a-f]{40}$/.test(env.GITHUB_SHA ?? "") &&
  /^[1-9][0-9]*$/.test(env.GITHUB_RUN_ID ?? ""),
  "MANUAL_FIRST_ATTEMPT_REQUIRED");
require_(env.CLOUDFLARE_API_TOKEN &&
  /^[0-9a-fA-F]{32}$/.test(env.CLOUDFLARE_ACCOUNT_ID ?? ""), "PROVIDER_CREDENTIALS_MISSING");
require_(!["CT03_R2_ACCESS_KEY_ID","CT03_R2_SECRET_ACCESS_KEY",
    "COFFEE_R2_ACCESS_KEY_ID","COFFEE_R2_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN",
    "GH_TOKEN","GITHUB_TOKEN"].some(name => env[name]), "FORBIDDEN_CUSTODY_CREDENTIAL");
const root = resolve(env.SDAI_ROOT);
const scripts = resolve(env.BUFFALO_SCRIPTS_ROOT);
const out = resolve(env.COFFEE_B_LIVE_OUT);
const parent = resolve(out, "..");
const payload = JSON.parse(await readFile(env.COFFEE_B_LIVE_INPUT, "utf8"));
const admission = JSON.parse(await readFile(join(parent, "admission.json"), "utf8"));
const attempt = JSON.parse(await readFile(join(parent, "attempt.json"), "utf8"));
require_(payload.schema === "arena.coffee-peak.buffalo-public-input/1" &&
  payload.mode === "CLOUDFLARE_WORKERS_AI_LIVE_ONE_POST" &&
  payload.protocol === "coffee_peak_capacity_v1" &&
  payload.arm === "B" && payload.condition === "B0" &&
  payload.execution_run_id === Number(env.GITHUB_RUN_ID) &&
  payload.execution_sha === env.GITHUB_SHA &&
  admission.run_id === payload.execution_run_id &&
  admission.artifact_id === payload.source_artifact_id &&
  payload.case_sha256 === admission.case_sha256 &&
  attempt.run_id === payload.execution_run_id &&
  attempt.state === "RESERVED_BEFORE_HTTP" &&
  attempt.case_sha256 === payload.case_sha256 &&
  payload.max_provider_posts === 1 &&
  Math.abs(payload.horizon_hours - 103.237 / 60) < 1e-10 &&
  Number.isFinite(payload.input_rate_orders_per_hour) &&
  payload.input_rate_orders_per_hour > 0 &&
  payload.provider_posts === 0 && payload.new_omc === 0 &&
  payload.truth_access === false && payload.scientific_lock_created === false,
  "LIVE_PAYLOAD_OR_ATTEMPT_MISMATCH");
const {OR_SLUG, CF_MODEL, CF_MODE, EV01_CAP, EV01_TIMEOUT_MS, EV01_BUDGET_AUTH,
       requestToCloudflareEV01, responseToOpenRouter, cloudflareUrl} =
  await import(pathToFileURL(join(scripts, "arena_b_ev01_cf_adapter.mjs")).href);
const originalFetch = globalThis.fetch;
const save = (name, value) => writeFile(join(out, name),
    JSON.stringify(value, null, 2) + "\n", {flag:"wx"});
await mkdir(out, {recursive: false});
const receipt = {
  schema:"arena.coffee-peak.b-live-receipt/1",
  mode:"CLOUDFLARE_WORKERS_AI_LIVE_ONE_POST",
  run_id:payload.execution_run_id, source_run_id:payload.source_run_id,
  source_artifact_id:payload.source_artifact_id, case_sha256:payload.case_sha256,
  public_sha256:payload.public_sha256, original_engine:"Engine.generate",
  model:CF_MODEL, transport:CF_MODE, sdk_interceptions:0, provider_posts:0,
  cloudflare_requests:0, raw_provider_saved:false, provider_usage:null,
  model_returned:false, status:"STARTED", stop_reason:null, new_omc:0,
  truth_access:false, scientific_lock_created:false, retry:false
};
let success = false;
try {
  globalThis.fetch = async (request, init={}) => {
    receipt.sdk_interceptions++;
    require_(receipt.sdk_interceptions === 1, "SECOND_SDK_REQUEST_BLOCKED");
    const url = new URL(typeof request === "string" ? request : request.url);
    const method = init.method ?? (request instanceof Request ? request.method : "GET");
    require_(url.origin === "https://openrouter.ai" &&
      url.pathname.endsWith("/chat/completions") &&
      method.toUpperCase() === "POST", "UNEXPECTED_SDK_REQUEST");
    let bodyText = init.body ?? (request instanceof Request ? await request.text() : null);
    if (Buffer.isBuffer(bodyText)) bodyText = bodyText.toString("utf8");
    require_(typeof bodyText === "string", "SDK_REQUEST_NOT_TEXT");
    const body = JSON.parse(bodyText);
    require_(body.model === OR_SLUG &&
      body.response_format?.type === "json_schema" &&
      body.response_format.json_schema?.schema?.properties?.variables &&
      body.response_format.json_schema?.schema?.properties?.relationships &&
      Array.isArray(body.messages) &&
      !body.messages.some(m => m.role === "assistant") &&
      body.messages.at(-1)?.content?.endsWith(payload.prompt) &&
      body.messages.some(m => typeof m.content === "string" &&
        m.content.includes(payload.problemStatement)) &&
      body.messages.some(m => typeof m.content === "string" &&
        m.content.includes(payload.backgroundKnowledge)), "SDK_PUBLIC_CONTRACT_MISMATCH");
    const effective = requestToCloudflareEV01(body, {authorization: EV01_BUDGET_AUTH});
    require_(effective.max_completion_tokens === EV01_CAP &&
      effective.stream === false && effective.reasoning_effort === "low",
      "PROVIDER_BUDGET_DRIFT");
    receipt.sdk_request_sha256 = h(body);
    receipt.effective_request_sha256 = h(effective);
    await save("sdk-request.json",body);
    await save("cloudflare-effective-request.json",
      {model:CF_MODEL,body:effective,no_credentials:true});
    // Write before POST. Network timeout implies possible consumption.
    receipt.provider_posts=1;
    receipt.cloudflare_requests=1;
    await save("cf-call-started.json",{
      status:"REQUEST_MAY_HAVE_CONSUMED",run_id:payload.execution_run_id,
      max_posts:1, effective_request_sha256:receipt.effective_request_sha256
    });
    const response = await originalFetch(cloudflareUrl(env.CLOUDFLARE_ACCOUNT_ID),{
      method:"POST",
      headers:{"Authorization":"Bearer "+env.CLOUDFLARE_API_TOKEN,
               "Content-Type":"application/json"},
      body:JSON.stringify(effective),
      signal:AbortSignal.timeout(EV01_TIMEOUT_MS)
    });
    receipt.http_status=response.status;
    const responseText=await response.text();
    let raw;
    try {raw=JSON.parse(responseText);}
    catch {
      await save("provider-nonjson.json",{
        status:response.status, bytes:responseText.length,
        sha256:"sha256:"+createHash("sha256").update(responseText).digest("hex")
      });
      fail("PROVIDER_NONJSON");
    }
    await save("provider-raw.json",raw);
    receipt.raw_provider_saved=true;
    receipt.provider_usage=raw?.result?.usage ?? raw?.usage ?? null;
    receipt.finish_reason=raw?.result?.choices?.[0]?.finish_reason ?? null;
    require_(response.ok, "PROVIDER_HTTP_FAILED");
    const compatibility=responseToOpenRouter(raw,receipt.sdk_request_sha256);
    await save("openrouter-compat-envelope.json",compatibility);
    return new Response(JSON.stringify(compatibility),{
      status:200,headers:{"content-type":"application/json"}});
  };
  env.OPEN_ROUTER_API_KEY="VIRTUAL_SDK_ROUTING_NO_REAL_OPENROUTER_KEY";
  const {default:Engine} =
    await import(pathToFileURL(join(root,"engines/quantitative/engine.js")).href);
  const native=await new Engine().generate(
    payload.prompt,{variables:[],relationships:[]},{
      underlyingModel:OR_SLUG,supportsArrays:false,supportsModules:false,
      supportsSubTypes:false,mentorMode:false,
      problemStatement:payload.problemStatement,
      backgroundKnowledge:payload.backgroundKnowledge,
      maxTokens:EV01_CAP,timeoutMinutes:7
    });
  await save("native-engine-result.json",native);
  receipt.native_sha256=h(native);
  receipt.native_file_sha256="sha256:"+createHash("sha256")
    .update(JSON.stringify(native,null,2)+"\n").digest("hex");
  receipt.model_returned=Boolean(!native?.err &&
    Array.isArray(native?.model?.variables) &&
    Array.isArray(native?.model?.relationships));
  receipt.native_horizon_hours=native?.model?.specs?.stopTime ?? null;
  const scope=receipt.model_returned &&
    native.model.specs?.startTime === 0 &&
    Math.abs(native.model.specs?.stopTime-payload.horizon_hours)<1e-9 &&
    native.model.specs?.timeUnits === "hour";
  receipt.status=scope?"ORIGINAL_ENGINE_LIVE_NATIVE_NOT_VALIDATED":"NATIVE_SCOPE_BLOCKED";
  receipt.stop_reason=scope?"NO_G2_G3_OR_SCIENTIFIC_LOCK":"INVALID_NATIVE_OR_COFFEE_HORIZON";
  success=scope;
} catch (_error) {
  // Neither SDK error messages nor raw HTTP bodies are printed with credentials.
  receipt.status="FAILURE_OR_CONSUMPTION_UNCERTAIN";
  receipt.stop_reason="REDACTED_FAILURE_NO_RETRY";
} finally {
  globalThis.fetch=originalFetch;
  delete env.OPEN_ROUTER_API_KEY;
  await save("receipt.json",receipt);
  console.log(JSON.stringify({status:receipt.status,provider_posts:receipt.provider_posts,
    model_returned:receipt.model_returned,new_omc:0,retry:false,
    scientific_lock_created:false}));
  if (!success) process.exitCode=1;
}
