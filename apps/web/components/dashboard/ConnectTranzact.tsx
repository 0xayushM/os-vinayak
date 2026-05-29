"use client";

import { useState } from "react";
import { CheckCircle, AlertTriangle, Loader2, Plug, Circle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils/cn";

type Step = "idle" | "saving" | "testing" | "syncing" | "done" | "error";

type PipelineStatus = "pending" | "running" | "success" | "failed";

interface PipelineProgress {
  key: string;
  label: string;
  status: PipelineStatus;
  rows: number | null;
  error: string | null;
}

interface SyncState {
  running: boolean;
  total: number;
  completed: number;
  current: string | null;
  error: string | null;
  pipelines: PipelineProgress[];
}

interface Props {
  /** Called once the connection is verified AND the initial sync has finished. */
  onConnected?: () => void;
  /** Compact mode for the settings page (no big hero copy). */
  compact?: boolean;
}

/**
 * Full connect-TranzAct flow:
 *   1. Save encrypted credentials   → POST /api/connections/tranzact
 *   2. Test connection              → POST /api/connections/tranzact/test
 *   3. Trigger initial full sync    → POST /api/connections/tranzact/sync
 *   4. Poll sync health until data has landed, then onConnected().
 */
export default function ConnectTranzact({ onConnected, compact = false }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<Step>("idle");
  const [message, setMessage] = useState("");
  const [sync, setSync] = useState<SyncState | null>(null);

  const busy = step === "saving" || step === "testing" || step === "syncing";

  async function pollSyncUntilDone(maxSeconds = 600) {
    const start = Date.now();
    while (Date.now() - start < maxSeconds * 1000) {
      try {
        const res = await fetch("/api/connections/tranzact/sync", { credentials: "include" });
        if (res.ok) {
          const state: SyncState = await res.json();
          setSync(state);
          // Finished when the worker stops running and has processed everything.
          if (!state.running && state.total > 0 && state.completed >= state.total) {
            return true;
          }
        }
      } catch {
        /* keep polling */
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    return true; // give up waiting but let the user into the dashboard
  }

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setStep("saving");
    setMessage("Saving credentials…");

    try {
      // 1. Save
      const saveRes = await fetch("/api/connections/tranzact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      if (!saveRes.ok) {
        const d = await saveRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "Failed to save credentials");
      }

      // 2. Test
      setStep("testing");
      setMessage("Testing TranzAct authentication…");
      const testRes = await fetch("/api/connections/tranzact/test", {
        method: "POST",
        credentials: "include",
      });
      if (!testRes.ok) {
        const d = await testRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "Connection test failed");
      }

      // 3. Trigger full sync
      setStep("syncing");
      setMessage("Connection verified. Pulling your data from TranzAct…");
      await fetch("/api/connections/tranzact/sync", {
        method: "POST",
        credentials: "include",
      });

      // 4. Poll until all reports finish
      await pollSyncUntilDone();

      setStep("done");
      setMessage("All set — loading your dashboard.");
      onConnected?.();
    } catch (err) {
      setStep("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div
      className={cn(
        "bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-5",
        compact ? "max-w-xl" : "max-w-md w-full",
      )}
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-blue-600/20 border border-blue-500/20 flex items-center justify-center">
          <Plug className="w-5 h-5 text-blue-400" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Connect TranzAct</h2>
          <p className="text-xs text-zinc-500">Cloud ERP · letstranzact.com</p>
        </div>
      </div>

      {!compact && (
        <p className="text-sm text-zinc-400">
          Enter your TranzAct login to start syncing your business data. We test
          the connection, then pull all reports into your dashboard automatically.
        </p>
      )}

      <form onSubmit={handleConnect} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">TranzAct Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
            disabled={busy || step === "done"}
            className="w-full bg-zinc-800 text-zinc-200 text-sm rounded-lg px-3 py-2 border border-zinc-700 focus:border-blue-500 focus:outline-none placeholder-zinc-600 disabled:opacity-60"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">TranzAct Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            disabled={busy || step === "done"}
            className="w-full bg-zinc-800 text-zinc-200 text-sm rounded-lg px-3 py-2 border border-zinc-700 focus:border-blue-500 focus:outline-none placeholder-zinc-600 disabled:opacity-60"
          />
        </div>

        <button
          type="submit"
          disabled={busy || step === "done"}
          className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-50"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          {step === "saving" && "Saving…"}
          {step === "testing" && "Testing…"}
          {step === "syncing" && "Syncing data…"}
          {step === "done" && "Connected"}
          {(step === "idle" || step === "error") && "Connect & Sync"}
        </button>
      </form>

      {message && (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs",
            step === "done"
              ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
              : step === "error"
              ? "bg-red-500/10 border border-red-500/20 text-red-400"
              : "bg-zinc-800 text-zinc-400",
          )}
        >
          {step === "done" && <CheckCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
          {step === "error" && <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
          {busy && <Loader2 className="w-3.5 h-3.5 mt-0.5 shrink-0 animate-spin" />}
          {message}
        </div>
      )}

      {/* ── Sync progress tracker ──────────────────────────────────────────── */}
      {(step === "syncing" || step === "done") && sync && sync.total > 0 && (
        <div className="space-y-3">
          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span>Pulling reports from TranzAct</span>
              <span className="tabular-nums">
                {sync.completed}/{sync.total}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
              <div
                className="h-full rounded-full bg-blue-500 transition-all duration-500"
                style={{ width: `${Math.round((sync.completed / sync.total) * 100)}%` }}
              />
            </div>
          </div>

          {/* Per-report checklist */}
          <ul className="space-y-1.5">
            {sync.pipelines.map((p) => (
              <li key={p.key} className="flex items-center gap-2 text-xs">
                {p.status === "success" && (
                  <CheckCircle className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                )}
                {p.status === "running" && (
                  <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-blue-400" />
                )}
                {p.status === "failed" && (
                  <XCircle className="w-3.5 h-3.5 shrink-0 text-red-400" />
                )}
                {p.status === "pending" && (
                  <Circle className="w-3.5 h-3.5 shrink-0 text-zinc-600" />
                )}
                <span
                  className={cn(
                    "flex-1",
                    p.status === "success" && "text-zinc-300",
                    p.status === "running" && "text-zinc-200",
                    p.status === "failed" && "text-red-400",
                    p.status === "pending" && "text-zinc-600",
                  )}
                >
                  {p.label}
                </span>
                {p.status === "success" && p.rows != null && (
                  <span className="tabular-nums text-zinc-600">{p.rows} rows</span>
                )}
                {p.status === "failed" && (
                  <span className="text-zinc-600">failed</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11px] text-zinc-600">
        Your credentials are encrypted (AES-256) before storage. Bearer tokens are
        never persisted — they are obtained on demand and held in memory only.
      </p>
    </div>
  );
}
