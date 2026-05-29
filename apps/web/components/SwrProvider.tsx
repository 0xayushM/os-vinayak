"use client";

import { SWRConfig } from "swr";

export function SwrProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        // Global error handler — log to console; individual panels show their own errors
        onError: (err, key) => {
          console.error(`[SWR] ${key}:`, err.message);
        },
        // Keep stale data visible while revalidating (no blank flash on refresh)
        revalidateOnMount: true,
        revalidateOnFocus: false,
        dedupingInterval: 30_000,
      }}
    >
      {children}
    </SWRConfig>
  );
}
