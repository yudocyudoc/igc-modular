/** EV-01-only budget extension over the proven R2 OpenRouter -> Workers AI adapter.
 * Historical source scripts/arena_b_cf_protocol_adapter.mjs is byte-identical.
 * Only caller with its own EV-01 authorization may request 16000 output tokens.
 */
import {CF_MODEL,OR_SLUG,CF_MODE,digest,requestToCloudflare,responseToOpenRouter}
  from "./arena_b_cf_protocol_adapter.mjs";
export {CF_MODEL,OR_SLUG,CF_MODE,digest,responseToOpenRouter};
export const EV01_ADAPTER_VERSION="igc-b-ev01-workers-rest/0.1";
export const EV01_CAP=16000;
export const EV01_TIMEOUT_MS=360000;
export const CF_ENDPOINT_ROUTE="/client/v4/accounts/{account}/ai/run/"+CF_MODEL;
export const EV01_BUDGET_AUTH="EV01_16K_OPENROUTER_NATIVE_ONE_CALL";

export function requestToCloudflareEV01(openRouterRequest,{authorization}={}){
  if(authorization!==EV01_BUDGET_AUTH)throw Error("EV01_BUDGET_NOT_AUTHORIZED");
  // The historical adapter owns schema, role and OpenRouter wire validation.
  // Do NOT reuse the old 3500/7000 max output budget.
  const established=requestToCloudflare(openRouterRequest);
  const requested=openRouterRequest.max_completion_tokens;
  if(requested!==undefined &&
      (!Number.isInteger(requested)||requested<=0))
      throw Error("EV01_INVALID_NATIVE_TOKEN_BUDGET");
  if(requested!==undefined && requested>EV01_CAP)
      throw Error("EV01_NATIVE_TOKENS_EXCEED_CAP");
  return {...established,
    max_completion_tokens:EV01_CAP,
    reasoning_effort:"low",
    stream:false};
}
export function cloudflareUrl(account){
  if(!/^[a-fA-F0-9]{32}$/.test(account??""))
    throw Error("EV01_INVALID_CLOUDFLARE_ACCOUNT");
  return "https://api.cloudflare.com/client/v4/accounts/"+account+
         "/ai/run/"+CF_MODEL;
}
