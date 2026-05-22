/**
 * POST /api/tranzact/report
 * -------------------------
 * Proxy endpoint — fetches a TranzAct report and returns the raw JSON.
 * Handles auth automatically (token cached server-side).
 * Tries multiple endpoint paths to find the correct one.
 *
 * Body:
 *   {
 *     reportId:  string       // e.g. "29"
 *     page?:     number       // default 1
 *     perPage?:  number       // default 50
 *     filters?:  object       // passed through to TranzAct
 *   }
 */
import { NextRequest, NextResponse } from "next/server";
import { getAccessToken, clearTokenCache, REPORTING_BASE } from "@/lib/tranzact/auth";

interface RequestBody {
  reportId: string;
  page?:    number;
  perPage?: number;
  filters?: Record<string, unknown>;
}

// Confirmed working endpoint (discovered 2026-05-22 by probing app.letstranzact.com JS)
const REPORT_ENDPOINT = `${REPORTING_BASE}/generate_report`;

async function tryFetch(url: string, payload: unknown, token: string) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type":  "application/json",
    },
    body: JSON.stringify(payload),
  });

  const text = await res.text();
  const isJson = text.trimStart().startsWith("{") || text.trimStart().startsWith("[");

  return { url, status: res.status, text, isJson };
}

export async function POST(req: NextRequest) {
  let body: RequestBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body.reportId) {
    return NextResponse.json({ error: "reportId is required" }, { status: 400 });
  }

  const payload: Record<string, unknown> = {
    report:     { id: body.reportId },
    pagination: { page: body.page ?? 1, per_page: body.perPage ?? 50 },
    ...(body.filters ?? {}),
  };

  let token: string;
  try {
    token = await getAccessToken();
  } catch (err: unknown) {
    return NextResponse.json({
      ok: false,
      error: `Auth failed: ${err instanceof Error ? err.message : String(err)}`,
    }, { status: 502 });
  }

  // Fetch the report; retry once on 401
  let result = await tryFetch(REPORT_ENDPOINT, payload, token);

  if (result.status === 401) {
    clearTokenCache();
    token = await getAccessToken();
    result = await tryFetch(REPORT_ENDPOINT, payload, token);
  }

  const isJson = result.isJson;

  if (isJson && result.status < 500) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(result.text);
    } catch {
      parsed = { raw: result.text };
    }
    return NextResponse.json({
      ok:       result.status < 400,
      status:   result.status,
      endpoint: REPORT_ENDPOINT,
      reportId: body.reportId,
      page:     body.page ?? 1,
      payload,
      response: parsed,
    });
  }

  return NextResponse.json({
    ok:      false,
    error:   `Unexpected response from TranzAct: HTTP ${result.status}`,
    preview: result.text.slice(0, 400),
    reportId: body.reportId,
    payload,
  }, { status: 502 });
}
