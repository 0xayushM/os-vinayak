import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // BFF routes proxy to FastAPI over a private, server-only network address.
  // FASTAPI_INTERNAL_URL and INTERNAL_API_KEY are server-only env vars.
  // They are read directly from process.env in route handlers (server code only).
  // Only vars prefixed NEXT_PUBLIC_* ever reach the client bundle.
};

export default nextConfig;
