/** Offline integration of genuine vendored Engine.generate for coffee.
 * Strictly NO network and NO live provider mode. Never eligible for scientific lock.
 * The actual original OpenRouter SDK request is intercepted and protocol-checked;
 * a local Cloudflare-shaped fixture supplies only a simulated provider response.
 */
import {readFile, mkdir, writeFile} from "node:fs/promises";
import {resolve, join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";

const sha = data => "sha256:" + createHash("sha256").update(JSON.stringify(data)).digest("hex");
const need = (ok, reason) => { if (!ok) throw Error("COFFEE_B_" + reason); };
const root = resolve(process.env.SDAI_ROOT ?? "upstream/sd-ai");
const scripts = resolve(process.env.BUFFALO_SCRIPTS_ROOT ?? "scripts");
const output = resolve(process.env.COFFEE_B_OUT ?? "coffee-b-offline-out");
const source = resolve(process.env.COFFEE_B_INPUT ?? "coffee-b-public-input.json");
const fixturePath = resolve(process.env.COFFEE_B_FIXTURE ?? "coffee-b-fixture.json");
need(process.env.COFFEE_B_OFFLINE === "yes", "OFFLINE_ONLY");
need(!["CLOUDFLARE_API_TOKEN", "OPEN_ROUTER_API_KEY",
       "CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
       "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
       "COFFEE_R2_ACCESS_KEY_ID", "COFFEE_R2_SECRET_ACCESS_KEY"]
       .some(k => process.env[k]), "SECRETS_FORBIDDEN_IN_OFFLINE_RUNNER");
const payload = JSON.parse(await readFile(source, "utf8"));
need(payload?.schema === "arena.coffee-peak.buffalo-public-input/1" &&
     payload.mode === "OFFLINE_FIXTURE_CONTRACT_ONLY" &&
     payload.protocol === "coffee_peak_capacity_v1" &&
     payload.arm === "B" && payload.condition === "B0" &&
     Number.isFinite(payload.horizon_hours) &&
     Math.abs(payload.horizon_hours - 103.237 / 60) < 1e-10 &&
     Number.isFinite(payload.input_rate_orders_per_hour) &&
     payload.input_rate_orders_per_hour > 0 &&
     payload.truth_access === false &&
     payload.scientific_lock_created === false &&
     payload.provider_posts === 0 &&
     payload.new_omc === 0, "INVALID_PUBLIC_COFFEE_PAYLOAD");
const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const {OR_SLUG, CF_MODEL, CF_MODE, EV01_CAP, EV01_BUDGET_AUTH,
       requestToCloudflareEV01, responseToOpenRouter} =
      await import(pathToFileURL(join(scripts, "arena_b_ev01_cf_adapter.mjs")).href);
const save = (name, data) => writeFile(join(output, name), JSON.stringify(data, null, 2) + "\n");
await mkdir(output, {recursive: false});
const receipt = {
  schema: "arena.coffee-peak.b-offline-receipt/1",
  mode: "OFFLINE_FIXTURE_CONTRACT_ONLY", case_sha256: payload.case_sha256,
  public_sha256: payload.public_sha256, source_package_sha256: payload.source_package_sha256,
  run_id: payload.run_id, frozen_sha: payload.frozen_sha, selection: payload.selection,
  horizon_hours: payload.horizon_hours, engine: "ORIGINAL_UB_IAD_SDAI_ENGINE_GENERATE",
  engine_source_modified: false, transport: CF_MODE, model: CF_MODEL,
  sdk_interceptions: 0, provider_posts: 0, new_omc: 0,
  real_network_calls: 0, model_returned: false, native_sha256: null,
  status: "STARTED", stop_reason: null, scientific_lock_created: false,
};
const previousFetch = globalThis.fetch;
let failed = false;
try {
  globalThis.fetch = async (request, init={}) => {
    receipt.sdk_interceptions += 1;
    need(receipt.sdk_interceptions === 1, "SECOND_SDK_REQUEST_REFUSED");
    const url = new URL(typeof request === "string" ? request : request.url);
    const method = init.method ?? (request instanceof Request ? request.method : "GET");
    need(url.origin === "https://openrouter.ai" &&
         url.pathname.endsWith("/chat/completions") &&
         method.toUpperCase() === "POST", "NETWORK_DESTINATION_FORBIDDEN");
    let bodyText = init.body ?? (request instanceof Request ? await request.text() : null);
    if (Buffer.isBuffer(bodyText)) bodyText = bodyText.toString("utf8");
    need(typeof bodyText === "string", "SDK_BODY_NOT_TEXT");
    const body = JSON.parse(bodyText);
    need(body.model === OR_SLUG &&
         body.response_format?.type === "json_schema" &&
         body.response_format.json_schema?.schema?.properties?.variables &&
         body.response_format.json_schema?.schema?.properties?.relationships,
         "ORIGINAL_ENGINE_SCHEMA_NOT_PRESENT");
    need(Array.isArray(body.messages) &&
         !body.messages.some(m => m.role === "assistant") &&
         body.messages.at(-1)?.role === "user" &&
         body.messages.at(-1)?.content.endsWith(payload.prompt),
         "ORIGINAL_ENGINE_PROMPT_OR_PARENT_INVALID");
    need(body.messages.some(m => typeof m.content === "string" &&
         m.content.includes(payload.problemStatement)) &&
         body.messages.some(m => typeof m.content === "string" &&
         m.content.includes(payload.backgroundKnowledge)),
         "PUBLIC_CONTEXT_NOT_IN_ORIGINAL_REQUEST");
    const effective = requestToCloudflareEV01(body, {authorization: EV01_BUDGET_AUTH});
    need(effective.max_completion_tokens === EV01_CAP &&
         effective.response_format?.type === "json_schema" &&
         effective.stream === false, "PROTOCOL_ADAPTER_DRIFT");
    await save("sdk-request.json", body);
    await save("cloudflare-effective-request.json",
               {model: CF_MODEL, body: effective, no_credentials: true});
    await save("provider-fixture-response.json", fixture);
    const envelope = responseToOpenRouter(fixture, sha(body));
    return new Response(JSON.stringify(envelope),
                        {status: 200, headers: {"content-type": "application/json"}});
  };
  process.env.OPEN_ROUTER_API_KEY = "LOCAL_ONLY_NO_REAL_OPENROUTER_KEY";
  const {default: Engine} =
      await import(pathToFileURL(join(root, "engines/quantitative/engine.js")).href);
  const parameters = {
    underlyingModel: OR_SLUG, supportsArrays: false, supportsModules: false,
    supportsSubTypes: false, mentorMode: false,
    problemStatement: payload.problemStatement,
    backgroundKnowledge: payload.backgroundKnowledge,
    maxTokens: EV01_CAP, timeoutMinutes: 7,
  };
  const native = await new Engine().generate(
      payload.prompt, {variables: [], relationships: []}, parameters);
  await save("native-engine-result.json", native);
  receipt.native_sha256 = sha(native);
  receipt.native_file_sha256 = "sha256:" + createHash("sha256")
    .update(JSON.stringify(native, null, 2) + "\n").digest("hex");
  receipt.model_returned = Boolean(!native?.err &&
      Array.isArray(native?.model?.variables) &&
      Array.isArray(native?.model?.relationships));
  if (!receipt.model_returned) {
    receipt.status = "ORIGINAL_ENGINE_RETURNED_NO_NATIVE";
    receipt.stop_reason = "NO_VALID_NATIVE_ENVELOPE";
    failed = true;
  } else if (native.model?.specs?.startTime !== 0 ||
             Math.abs(native.model?.specs?.stopTime - payload.horizon_hours) > 1e-9 ||
             !["hour", "hours"].includes(native.model?.specs?.timeUnits)) {
    receipt.status = "NATIVE_BLOCKED";
    receipt.stop_reason = "COFFEE_HORIZON_OR_TIME_UNIT_MISMATCH";
    failed = true;
  } else {
    receipt.status = "ORIGINAL_ENGINE_OUTPUT_ON_OFFLINE_FIXTURE";
    receipt.stop_reason = "FIXTURE_NOT_SCIENTIFIC_AND_TRANSLATOR_UNVALIDATED";
  }
} catch (error) {
  failed = true;
  receipt.status = "OFFLINE_RUNNER_STOPPED";
  receipt.stop_reason = String(error?.message ?? error).slice(0, 250);
} finally {
  globalThis.fetch = previousFetch;
  delete process.env.OPEN_ROUTER_API_KEY;
  await save("receipt.json", receipt);
  console.log(JSON.stringify({status: receipt.status,
    stop_reason: receipt.stop_reason, sdk_interceptions: receipt.sdk_interceptions,
    provider_posts: 0, new_omc: 0, real_network_calls: 0,
    scientific_lock_created: false}));
  if (failed || !receipt.model_returned) process.exitCode = 1;
}
