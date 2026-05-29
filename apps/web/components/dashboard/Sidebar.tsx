"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3, TrendingUp, Users, Package, ShoppingCart,
  CreditCard, Truck, Wrench, Activity, Settings, Zap, LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useSyncHealth } from "@/hooks/useDashboard";

const NAV = [
  {
    section: "Revenue",
    items: [
      { label: "Revenue Overview",      href: "/dashboard",            icon: TrendingUp },
      { label: "Customer Insights",     href: "/dashboard/customers",  icon: Users      },
      { label: "Top SKUs",              href: "/dashboard/skus",       icon: Package    },
      { label: "Quotes & Pipeline",     href: "/dashboard/quotes",     icon: Zap        },
    ],
  },
  {
    section: "Receivables",
    items: [
      { label: "AR Aging",              href: "/dashboard/ar",         icon: CreditCard },
      { label: "Open Sales Orders",     href: "/dashboard/orders",     icon: ShoppingCart },
    ],
  },
  {
    section: "Procurement",
    items: [
      { label: "Purchases",             href: "/dashboard/purchases",  icon: Truck      },
      { label: "Open POs",              href: "/dashboard/pos",        icon: ShoppingCart },
      { label: "GRN / Goods Received",  href: "/dashboard/grn",        icon: Truck      },
    ],
  },
  {
    section: "Operations",
    items: [
      { label: "Inventory",             href: "/dashboard/inventory",  icon: BarChart3  },
      { label: "Production",            href: "/dashboard/production", icon: Wrench     },
      { label: "BOM Coverage",          href: "/dashboard/bom",        icon: Activity   },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: health } = useSyncHealth();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    window.location.href = "/login";
  }

  return (
    <aside className="w-56 shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col overflow-hidden">
      {/* Brand */}
      <div className="px-4 py-4 border-b border-zinc-800">
        <div className="text-sm font-bold text-white">🧠 Vinayak Brain OS</div>
        <div className="text-[11px] text-zinc-500 mt-0.5">KBrushes · TranzAct</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2 space-y-4">
        {NAV.map((section) => (
          <div key={section.section}>
            <div className="px-4 pb-1 text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
              {section.section}
            </div>
            {section.items.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2.5 px-4 py-2 text-xs transition-colors",
                    active
                      ? "bg-blue-600/20 text-white border-r-2 border-blue-500"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800",
                  )}
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Sync health indicator */}
      <div className="px-4 py-3 border-t border-zinc-800">
        <Link
          href="/dashboard/sync"
          className="flex items-center gap-2 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              health === undefined
                ? "bg-zinc-600"
                : health.healthy
                ? "bg-emerald-500"
                : "bg-amber-500 animate-pulse",
            )}
          />
          {health === undefined
            ? "Checking sync…"
            : health.healthy
            ? "All pipelines healthy"
            : `${health.stale_pipelines.length} stale pipeline${health.stale_pipelines.length > 1 ? "s" : ""}`}
        </Link>
      </div>

      {/* Settings + Logout */}
      <div className="px-4 py-3 border-t border-zinc-800 space-y-2">
        <Link
          href="/dashboard/settings"
          className="flex items-center gap-2 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <Settings className="w-3.5 h-3.5" />
          Settings & Connections
        </Link>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-[11px] text-zinc-600 hover:text-red-400 transition-colors w-full text-left"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
