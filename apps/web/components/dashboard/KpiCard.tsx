"use client";

import { cn } from "@/lib/utils/cn";

interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  accent?: "blue" | "emerald" | "amber" | "red" | "violet";
}

const ACCENT_CLASSES = {
  blue:    "text-blue-400",
  emerald: "text-emerald-400",
  amber:   "text-amber-400",
  red:     "text-red-400",
  violet:  "text-violet-400",
};

const TREND_CLASSES = {
  up:      "text-emerald-400",
  down:    "text-red-400",
  neutral: "text-zinc-500",
};

const TREND_ARROWS = { up: "↑", down: "↓", neutral: "—" };

export function KpiCard({
  label,
  value,
  sub,
  trend,
  trendLabel,
  accent = "blue",
}: KpiCardProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wide">
        {label}
      </span>
      <span className={cn("text-2xl font-bold tabular-nums", ACCENT_CLASSES[accent])}>
        {value}
      </span>
      {(sub || trendLabel) && (
        <div className="flex items-center gap-1.5 mt-0.5">
          {trend && trendLabel && (
            <span className={cn("text-xs font-medium", TREND_CLASSES[trend])}>
              {TREND_ARROWS[trend]} {trendLabel}
            </span>
          )}
          {sub && <span className="text-xs text-zinc-600">{sub}</span>}
        </div>
      )}
    </div>
  );
}
