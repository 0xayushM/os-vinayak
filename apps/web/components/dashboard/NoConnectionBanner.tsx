"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { Plug, X } from "lucide-react";

/**
 * Shown on the dashboard when no TranzAct connection exists yet.
 * Fetches /api/connections to check — only renders if connections list is empty.
 */
export function NoConnectionBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    fetch("/api/connections/", { credentials: "include" })
      .then((r) => r.json())
      .then((d) => {
        const active = (d.connections ?? []).filter(
          (c: { is_active: boolean }) => c.is_active,
        );
        setShow(active.length === 0);
      })
      .catch(() => {
        // Backend not reachable — don't show the banner, just let panels fail gracefully
      });
  }, []);

  if (!show) return null;

  return (
    <div className="mx-6 mt-6 bg-blue-600/10 border border-blue-500/20 rounded-xl px-4 py-3 flex items-center gap-3">
      <Plug className="w-4 h-4 text-blue-400 shrink-0" />
      <div className="flex-1">
        <p className="text-sm font-medium text-blue-300">
          No ERP connected yet
        </p>
        <p className="text-xs text-blue-400/70 mt-0.5">
          Connect your TranzAct account to start syncing data and seeing live panels.
        </p>
      </div>
      <Link
        href="/dashboard/settings"
        className="shrink-0 text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg transition-colors"
      >
        Connect now
      </Link>
      <button
        onClick={() => setShow(false)}
        className="shrink-0 text-blue-400/50 hover:text-blue-400 transition-colors"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
