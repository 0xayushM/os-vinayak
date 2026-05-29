/**
 * POST /api/tranzact/login
 * ------------------------
 * Test endpoint — forces a fresh TranzAct login and returns token metadata.
 * Useful for verifying credentials and checking the base URL is reachable.
 */
import { NextResponse } from "next/server";
import { clearTokenCache, getAccessToken, BASE } from "@/lib/tranzact/auth";

export async function POST() {
  try {
    clearTokenCache(); // force fresh login
    const token = await getAccessToken();

    // Decode exp without importing jose
    const payload = token.split(".")[1];
    const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString());

    return NextResponse.json({
      ok: true,
      base_url: BASE,
      token_preview: token.substring(0, 40) + "...",
      expires_at: new Date(exp * 1000).toISOString(),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, base_url: BASE, error: message }, { status: 502 });
  }
}

// Allow GET so the connection can be tested straight from a browser.
export const GET = POST;
