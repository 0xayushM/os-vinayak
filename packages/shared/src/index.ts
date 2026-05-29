/**
 * @vinayak/shared
 * ───────────────
 * Types shared across the monorepo. The FastAPI backend returns every
 * dashboard panel in a consistent envelope; mirror that shape here so the
 * Next.js BFF and panels stay in sync with the API.
 */

/** Standard envelope returned by every FastAPI dashboard endpoint. */
export interface ApiEnvelope<T> {
  data: T;
  meta: {
    report_id: number;
    /** ISO 8601 timestamp of the last successful sync, or null if never synced. */
    last_synced_at: string | null;
    /** True if the cached data is older than the staleness threshold. */
    stale: boolean;
  };
}

/** Result of POST /api/tranzact/login (the test-connection endpoint). */
export interface TranzactLoginResult {
  ok: boolean;
  base_url: string;
  token_preview?: string;
  expires_at?: string;
  error?: string;
}
