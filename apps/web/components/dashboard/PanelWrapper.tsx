"use client";

import { relativeTime } from "@/lib/utils/cn";
import { PanelMeta } from "@/hooks/useDashboard";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface PanelWrapperProps {
  title: string;
  subtitle?: string;
  meta?: PanelMeta | null;
  loading?: boolean;
  error?: Error | null;
  children: React.ReactNode;
  className?: string;
}

export function PanelWrapper({
  title,
  subtitle,
  meta,
  loading,
  error,
  children,
  className = "",
}: PanelWrapperProps) {
  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-xl flex flex-col ${className}`}>
      {/* Header */}
      <div className="px-4 pt-4 pb-2 flex items-start justify-between gap-2 shrink-0">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
          {subtitle && (
            <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {meta?.stale && (
            <span className="flex items-center gap-1 text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded-full font-medium">
              <AlertTriangle className="w-2.5 h-2.5" />
              Stale
            </span>
          )}
          {meta?.last_synced_at && (
            <span className="text-[10px] text-zinc-600">
              {relativeTime(meta.last_synced_at)}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 px-4 pb-4 min-h-0">
        {loading ? (
          <div className="h-full flex items-center justify-center py-8">
            <RefreshCw className="w-5 h-5 text-zinc-600 animate-spin" />
          </div>
        ) : error ? (
          <div className="h-full flex items-center justify-center py-8">
            <div className="text-center">
              <AlertTriangle className="w-5 h-5 text-red-500 mx-auto mb-2" />
              <p className="text-xs text-red-400">{error.message}</p>
            </div>
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}
