/** Q75-only provider migration after Cloudflare HTTP 410 / code 5028.
 * The original IGC protocol adapter stays byte-identical and continues to
 * validate the ORIGINAL Buffalo SDK's virtual OpenRouter alias. Only the
 * Cloudflare endpoint model changes. No automatic retry or new authorization.
 */
export const Q75_PROVIDER_MODEL='@cf/zai-org/glm-5.3';
export const HISTORICAL_ADAPTER_MODEL='@cf/zai-org/glm-5.3-flash';
export function providerEndpoint(account) {
  if(!/^[0-9a-fA-F]{32}$/.test(account??''))
    throw new Error('Q75_INVALID_PROVIDER_ACCOUNT');
  return 'https://api.cloudflare.com/client/v4/accounts/'+account+
    '/ai/run/'+Q75_PROVIDER_MODEL;
}
