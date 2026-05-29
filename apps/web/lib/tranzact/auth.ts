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

/**
 * Pull a token out of a login/refresh response without assuming one envelope
 * shape. TranzAct's platform mixes `{ success, data }` (reporting) and
 * `{ status, data }` (login) styles, and the token may sit at the top level
 * or under `data` / `tokens`. We try every known location rather than hard-
 * failing on a single `status === 1` check (the original bug: a successful
 * `{ success: true, data: {...} }` login was rejected as an error).
 */
function pick(obj: unknown, keys: string[]): string | null {
  if (!obj || typeof obj !== "object") return null;
  const rec = obj as Record<string, unknown>;
  for (const k of keys) {
    const v = rec[k];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

const ACCESS_KEYS  = ["access_token", "access", "token", "accessToken"];
const REFRESH_KEYS = ["refresh_token", "refresh", "refreshToken"];

function extractTokens(body: Record<string, unknown>): {
  access: string | null;
  refresh: string | null;
} {
  const data   = (body.data ?? {}) as Record<string, unknown>;
  const tokens = (data.tokens ?? body.tokens ?? {}) as Record<string, unknown>;
  return {
    access:
      pick(data, ACCESS_KEYS) ?? pick(tokens, ACCESS_KEYS) ?? pick(body, ACCESS_KEYS),
    refresh:
      pick(data, REFRESH_KEYS) ?? pick(tokens, REFRESH_KEYS) ?? pick(body, REFRESH_KEYS),
  };
}

async function doLogin(): Promise<void> {
  if (!EMAIL || !PASSWORD) {
    throw new Error(
      "TranzAct credentials missing — set TRANZACT_EMAIL and TRANZACT_PASSWORD in the environment",
    );
  }

  const url = `${BASE_URL}/main/login/password-login/`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });

  const rawText = await res.text();
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawText);
  } catch {
    throw new Error(
      `TranzAct login: non-JSON response (HTTP ${res.status}) from ${url} — ${rawText.slice(0, 300)}`,
    );
  }

  if (!res.ok) {
    throw new Error(
      `TranzAct login failed: HTTP ${res.status} — ${JSON.stringify(body).slice(0, 400)}`,
    );
  }

  const { access, refresh } = extractTokens(body);
  if (!access) {
    // 2xx but no recognised token — surface the whole body so the real
    // envelope shape is visible instead of a generic "login error".
    throw new Error(
      `TranzAct login: no access token in response — ${JSON.stringify(body).slice(0, 400)}`,
    );
  }

  cache.accessToken  = access;
  cache.refreshToken = refresh;
  cache.accessExp    = decodeExp(access);
  cache.refreshExp   = refresh ? decodeExp(refresh) : 0;

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

    const body = (await res.json()) as Record<string, unknown>;
    const { access } = extractTokens(body);

    if (!access) return false;

    cache.accessToken = access;
    cache.accessExp   = decodeExp(access);
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

