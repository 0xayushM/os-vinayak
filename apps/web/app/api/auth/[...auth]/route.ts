/**
 * app/api/auth/[...auth]/route.ts
 * BFF proxy for platform auth endpoints.
 *   POST /api/auth/login   → FastAPI /auth/login
 *   POST /api/auth/logout  → FastAPI /auth/logout
 *   GET  /api/auth/me      → FastAPI /auth/me
 */
import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL  = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";
const INTERNAL_KEY = process.env.INTERNAL_API_KEY     ?? "";

async function proxy(request: NextRequest, segments: string[]) {
  const path     = segments.join("/");
  const upstream = `${FASTAPI_URL}/auth/${path}`;
  const isGet    = request.method === "GET";
  const body     = isGet ? undefined : await request.text();

  const res = await fetch(upstream, {
    method: request.method,
    headers: {
      "Content-Type":   "application/json",
      "X-Internal-Key": INTERNAL_KEY,
      Cookie: request.headers.get("cookie") ?? "",
    },
    body: body || undefined,
    cache: "no-store",
  });

  const data     = await res.json();
  const response = NextResponse.json(data, { status: res.status });

  const setCookie = res.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);

  return response;
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ auth: string[] }> },
) {
  return proxy(req, (await params).auth);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ auth: string[] }> },
) {
  return proxy(req, (await params).auth);
}
