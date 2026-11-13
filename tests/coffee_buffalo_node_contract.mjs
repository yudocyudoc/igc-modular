/** Original Engine.generate under a local Cloudflare fixture, NO live network. */
import {mkdtemp, readFile, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {spawnSync} from "node:child_process";
import assert from "node:assert/strict";

const workspace = resolve(process.argv[2] ?? "");
const repo = resolve(".");
const tmp = await mkdtemp(join(process.env.RUNNER_TEMP ?? tmpdir(), "coffee-b-test-"));
const input = join(tmp, "input.json");
const fixture = join(tmp, "mock.json");
const horizon = 103.237 / 60;
const sha = "sha256:" + "a".repeat(64);
const context = {frontier: "PAID_ORDER_TO_PICKUP",
                 input_rate_orders_per_hour: 10, horizon_hours: horizon,
                 future_input: "ASSUMED_NOT_OBSERVED"};
const prompt = "A cafeteria must model accepted paid orders, not observed pickup. " +
               "Generate original stock/flow model for " + horizon + " hours.";
const problem = "Unknown paid-to-pickup dynamics, no measured pickups.";
const background = JSON.stringify(context);
const payload = {
  schema: "arena.coffee-peak.buffalo-public-input/1",
  mode: "OFFLINE_FIXTURE_CONTRACT_ONLY", protocol: "coffee_peak_capacity_v1",
  arm: "B", condition: "B0", case_sha256: sha, public_sha256: sha,
  source_package_sha256: "b".repeat(64), run_id: "123",
  frozen_sha: "c".repeat(40), selection: {scenario_id: "case-a",
  replication: 1, day_of_week: 1},
  horizon_hours: horizon, input_rate_orders_per_hour: 10,
  truth_access: false, scientific_lock_created: false,
  provider_posts: 0, new_omc: 0,
  prompt, problemStatement: problem, backgroundKnowledge: background,
};
await writeFile(input, JSON.stringify(payload));
function variable(name, type, equation, unit, inflows=[], outflows=[]) {
  return {name, type, equation, units: unit, inflows, outflows,
          uniflow: type === "flow", graphicalFunction: {points: []},
          documentation: "OFFLINE FIXTURE ONLY; no actual model generation."};
}
const response = {
  specs: {startTime: 0, stopTime: horizon, dt: horizon / 64,
          timeUnits: "hour", integrationMethod: "Euler"},
  variables: [
    variable("Paid Orders", "flow", "10", "orders/hour"),
    variable("Pickup Rate", "flow", "MIN(10, Backlog / 0.1)", "orders/hour"),
    variable("Backlog", "stock", "0", "orders", ["Paid Orders"], ["Pickup Rate"]),
    variable("Picked Up", "stock", "0", "orders", ["Pickup Rate"], []),
  ],
  relationships: [
    {from: "Paid Orders", to: "Backlog", reasoning: "Fixture", polarity: "+", polarityReasoning: "Fixture"},
    {from: "Pickup Rate", to: "Backlog", reasoning: "Fixture", polarity: "-", polarityReasoning: "Fixture"},
    {from: "Pickup Rate", to: "Picked Up", reasoning: "Fixture", polarity: "+", polarityReasoning: "Fixture"},
  ],
  explanation: "OFFLINE FIXTURE ONLY", title: "Offline coffee fixture",
};
async function run(end, suffix) {
  const out = join(tmp, "out-" + suffix);
  response.specs.stopTime = end;
  await writeFile(fixture, JSON.stringify({success: true, result: {
    response, usage: {prompt_tokens: 5, completion_tokens: 5},
    choices: [{message: {content: JSON.stringify(response)}, finish_reason: "stop"}]
  }}));
  const env = {...process.env, SDAI_ROOT: join(workspace, "upstream/sd-ai"),
      BUFFALO_SCRIPTS_ROOT: join(workspace, "scripts"), COFFEE_B_INPUT: input,
      COFFEE_B_FIXTURE: fixture, COFFEE_B_OUT: out, COFFEE_B_OFFLINE: "yes"};
  for (const key of ["CLOUDFLARE_API_TOKEN", "OPEN_ROUTER_API_KEY",
      "CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
      "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
    delete env[key];
  // Node process launched after the transport fixture is on disk. The runner
  // intercepts global fetch; no real outgoing request can be made.
  const result = spawnSync(process.execPath, [join(repo, "arena/buffalo/coffee_runner.mjs")],
      {cwd: repo, env, encoding: "utf8", timeout: 120000});
  const receipt = JSON.parse(await readFile(join(out, "receipt.json"), "utf8"));
  const native = JSON.parse(await readFile(join(out, "native-engine-result.json"), "utf8"));
  assert.equal(receipt.sdk_interceptions, 1);
  assert.equal(receipt.provider_posts, 0);
  assert.equal(receipt.real_network_calls, 0);
  assert.equal(receipt.engine_source_modified, false);
  assert.equal(receipt.native_file_sha256,
      "sha256:" + (await import("node:crypto")).createHash("sha256")
        .update(await readFile(join(out, "native-engine-result.json"))).digest("hex"));
  assert.equal(receipt.native_sha256,
      "sha256:" + (await import("node:crypto")).createHash("sha256")
        .update(JSON.stringify(native)).digest("hex"));
  const req = JSON.parse(await readFile(join(out, "sdk-request.json"), "utf8"));
  assert.equal(req.response_format.type, "json_schema");
  assert(req.messages.at(-1).content.endsWith(prompt), "Original SDK wraps the user prompt with public background");
  assert(!req.messages.some(m => m.role === "assistant"));
  assert(req.messages.some(m => m.content.includes(problem)));
  const effective = JSON.parse(await readFile(join(out, "cloudflare-effective-request.json"), "utf8"));
  assert.equal(effective.body.max_completion_tokens, 16000);
  assert.equal(effective.body.stream, false);
  assert.equal(effective.no_credentials, true);
  return {result, receipt, native};
}
let ok = await run(horizon, "correct");
assert.equal(ok.result.status, 0, ok.result.stderr + "\n" + ok.result.stdout);
assert.equal(ok.receipt.status, "ORIGINAL_ENGINE_OUTPUT_ON_OFFLINE_FIXTURE");
assert.equal(ok.receipt.model_returned, true);
assert.equal(ok.native.model.specs.stopTime, horizon);
let bad = await run(8, "wrong-horizon");
assert.notEqual(bad.result.status, 0);
assert.equal(bad.receipt.status, "NATIVE_BLOCKED");
assert.equal(bad.receipt.stop_reason, "COFFEE_HORIZON_OR_TIME_UNIT_MISMATCH");
console.log(JSON.stringify({original_engine_generate_called: true,
  mock_sdk_requests: 2, scientific_models: 0, real_provider_posts: 0,
  wrong_horizon_blocked: true, no_solver: true}));
