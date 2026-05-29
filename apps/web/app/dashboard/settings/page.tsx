"use client";

import { Unplug } from "lucide-react";
import ConnectTranzact from "@/components/dashboard/ConnectTranzact";

export default function SettingsPage() {
  return (
    <div className="p-6 space-y-8 max-w-xl">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Settings & Connections</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          Connect your ERP tools or re-sync data on demand.
        </p>
      </div>

      {/* TranzAct connection — save, test, and run a fresh sync */}
      <ConnectTranzact compact />

      {/* Future ERP placeholders */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-zinc-600 uppercase tracking-wider">
          Coming in Phase 3
        </h3>
        {["Tally Prime (Local Agent)", "Busy Accounting"].map((name) => (
          <div
            key={name}
            className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 flex items-center gap-3 opacity-50"
          >
            <div className="w-9 h-9 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center">
              <Unplug className="w-4 h-4 text-zinc-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-400">{name}</p>
              <p className="text-xs text-zinc-600">Not yet available</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
