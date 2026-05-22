/**
 * lib/tranzact/auth.ts
 * --------------------
 * Server-side token manager for TranzAct API.
 * Module-level singleton — tokens are cached in memory for the lifetime
 * of the Next.js Node process. On hot-reload the cache resets (fine for dev).
 *
 * Public API:
 *   getAccessToken()         → valid Bearer token (refreshes automatically)
 *   clearTokenCache()        → force re-login on next call
 */

const BASE_URL      = process.env.TRANZACT_BASE_URL      ?? "https://be.letstranzact.com";
export const REPORTING_BASE = process.env.TRANZACT_REPORTING_URL ?? "https://reporting.letstranzact.com";
const EMAIL    = process.env.TRANZACT_EMAIL    ?? "";
const PASSWORD = process.env.TRANZACT_PASSWORD ?? "";

const BUFFER_MS = 2 * 60 * 1000; // treat token as expired 2 min early

interface TokenCache {
  accessToken:  string | null;
  refreshToken: string | null;
  accessExp:    number; // unix ms
  refreshExp:   number;
}

const cache: TokenCache = {
  accessToken:  null,
  refreshToken: null,
  accessExp:    0,
  refreshExp:   0,
};

/** Decode the `exp` field from a JWT without verifying the signature. */
function decodeExp(token: string): number {
  try {
    const payload = token.split(".")[1];
    const json = Buffer.from(payload, "base64url").toString("utf8");
    const { exp } = JSON.parse(json);
    return (exp as number) * 1000; // convert to ms
  } catch {
    return Date.now() + 30 * 60 * 1000; // fallback: 30 min
  }
}

async function doLogin(): Promise<void> {
  const res = await fetch(`${BASE_URL}/main/login/password-login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });

  if (!res.ok) {
    throw new Error(`TranzAct login failed: HTTP ${res.status}`);
  }

  const body = await res.json();
  if (body.status !== 1) {
    throw new Error(`TranzAct login error: ${JSON.stringify(body)}`);
  }

  const data = body.data as {
    access_token: string;
    refresh_token: string;
  };

  cache.accessToken  = data.access_token;
  cache.refreshToken = data.refresh_token;
  cache.accessExp    = decodeExp(data.access_token);
  cache.refreshExp   = decodeExp(data.refresh_token);

  console.log("[tranzact/auth] Login OK — token expires at", new Date(cache.accessExp).toISOString());
}

async function doRefresh(): Promise<boolean> {
  if (!cache.refreshToken || Date.now() >= cache.refreshExp - BUFFER_MS) {
    return false;
  }

  try {
    const res = await fetch(`${BASE_URL}/main/login/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: cache.refreshToken }),
    });

    if (!res.ok) return false;

    const body = await res.json();
    const newToken: string =
      body.access ?? body.access_token ?? body.data?.access_token;

    if (!newToken) return false;

    cache.accessToken = newToken;
    cache.accessExp   = decodeExp(newToken);
    console.log("[tranzact/auth] Token refreshed");
    return true;
  } catch {
    return false;
  }
}

/** Returns a valid Bearer token, logging in or refreshing as needed. */
export async function getAccessToken(): Promise<string> {
  const now = Date.now();

  // Fast path — cached token still valid
  if (cache.accessToken && now < cache.accessExp - BUFFER_MS) {
    return cache.accessToken;
  }

  // Try refresh
  if (await doRefresh()) {
    return cache.accessToken!;
  }

  // Full re-login
  await doLogin();
  return cache.accessToken!;
}

export function clearTokenCache(): void {
  cache.accessToken  = null;
  cache.refreshToken = null;
  cache.accessExp    = 0;
  cache.refreshExp   = 0;
}

export const BASE = BASE_URL;

