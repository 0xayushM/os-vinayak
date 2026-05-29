"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import ConnectTranzact from "./ConnectTranzact";

interface Connection {
  tool_name: string;
  is_active: boolean;
  last_verified_at: string | null;
}

/**
 * Gates the dashboard behind a verified TranzAct connection.
 *
 *   not connected  → show the Connect TranzAct onboarding flow
 *   connected       → render the dashboard (children)
 *
 * This replaces the old dismissible banner: connecting TranzAct is now the
 * first thing a freshly-logged-in user does.
 */
export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"loading" | "connected" | "disconnected">("loading");

  const check = useCallback(async () => {
    try {
      const res = await fetch("/api/connections/", { credentials: "include" });
      if (!res.ok) {
        setState("disconnected");
        return;
      }
      const data = await res.json();
      const conns: Connection[] = data.connections ?? [];
      const tz = conns.find((c) => c.tool_name === "tranzact");
      setState(tz && tz.is_active && tz.last_verified_at ? "connected" : "disconnected");
    } catch {
      setState("disconnected");
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (state === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[60vh] text-zinc-500 text-sm gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Checking your connection…
      </div>
    );
  }

  if (state === "disconnected") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] px-6 gap-6">
        <div className="text-center">
          <h1 className="text-lg font-semibold text-zinc-100">Welcome to Vinayak Brain OS</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Connect TranzAct to bring your business data into the dashboard.
          </p>
        </div>
        <ConnectTranzact onConnected={check} />
      </div>
    );
  }

  return <>{children}</>;
}
