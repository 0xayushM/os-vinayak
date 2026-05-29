/**
 * middleware.ts
 * ─────────────
 * Runs on every request that matches the `matcher` pattern below.
 *
 * Rules:
 *   1. If the user has a `vb_access_token` cookie → let them through.
 *   2. If not → redirect to /login.
 *   3. If the user is on /login and already has a valid cookie → redirect to /dashboard.
 *
 * We do NOT verify the JWT signature here (that would require importing crypto
 * in the Edge runtime). Signature verification happens inside FastAPI on every
 * API call. The middleware only checks cookie presence to avoid a flash of the
 * dashboard before the first API call.
 */
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME   = "vb_access_token";
const LOGIN_PATH    = "/login";
const DASHBOARD_PATH = "/dashboard";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(COOKIE_NAME)?.value;

  // Already logged in and trying to visit /login → go to dashboard
  if (pathname === LOGIN_PATH && token) {
    return NextResponse.redirect(new URL(DASHBOARD_PATH, request.url));
  }

  // Not logged in and trying to visit a protected route → go to login
  if (pathname.startsWith(DASHBOARD_PATH) && !token) {
    const loginUrl = new URL(LOGIN_PATH, request.url);
    // Preserve the intended destination so we can redirect back after login
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Protect all dashboard pages
    "/dashboard/:path*",
    // Redirect /login if already authenticated
    "/login",
  ],
};
