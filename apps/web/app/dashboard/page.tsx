"use client";

import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import {
  useRevenueSummary, useRevenueTrend, useCustomerConcentration,
  useTopSkus, useArSummary, useOpenOrders, useInventorySummary,
  useInventoryByCategory, useProductionSummary, usePurchaseSummary,
  useGrnSummary, useOpenPOs, useQuoteSummary, useBomCoverage,
} from "@/hooks/useDashboard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";

// ── Chart colour palette (dark theme) ────────────────────────────────────────
const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"];
const BLUE   = "#3b82f6";
const GREEN  = "#10b981";
const AMBER  = "#f59e0b";

const tooltipStyle = {
  contentStyle: {
    background: "#18181b",
    border: "1px solid #3f3f46",
    borderRadius: 8,
  },
  labelStyle: { color: "#a1a1aa" },
};

// Recharts ValueType is string | number | (string | number)[] — cast helper avoids
// repeating the assertion on every formatter prop.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fmt(label: string): (v: any) => [string, string] {
  return (v) => [formatCurrency(Number(v ?? 0)), label];
}

// ── S1 Revenue KPIs ───────────────────────────────────────────────────────────
function RevenueKpiPanel() {
  const { data, error, isLoading } = useRevenueSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper
      title="Revenue Overview"
      subtitle="Last 30 days"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard
          label="Period Total"
          value={formatCurrency(d?.period_total ?? 0, true)}
          accent="blue"
          sub={`${d?.invoice_count ?? 0} invoices`}
        />
        <KpiCard
          label="Monthly Avg"
          value={formatCurrency(d?.monthly_avg ?? 0, true)}
          accent="emerald"
        />
        <KpiCard
          label="YTD Total"
          value={formatCurrency(d?.ytd_total ?? 0, true)}
          accent="violet"
        />
        <KpiCard
          label="Active Customers"
          value={formatNumber(d?.customer_count ?? 0)}
          accent="amber"
        />
      </div>
    </PanelWrapper>
  );
}

// ── S2 Monthly Revenue Trend ──────────────────────────────────────────────────
function RevenueTrendPanel() {
  const { data, error, isLoading } = useRevenueTrend(6);
  const months = data?.data?.months ?? [];
  return (
    <PanelWrapper
      title="Revenue Trend"
      subtitle="6-month bar chart"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={months} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fill: "#71717a", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#71717a", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => formatCurrency(v, true)}
          />
          <Tooltip
            {...tooltipStyle}
            formatter={fmt("Revenue")}
          />
          <Bar dataKey="revenue" fill={BLUE} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </PanelWrapper>
  );
}

// ── S3 Customer Concentration ─────────────────────────────────────────────────
function CustomerConcentrationPanel() {
  const { data, error, isLoading } = useCustomerConcentration(30);
  const slices = data?.data?.slices ?? [];
  return (
    <PanelWrapper
      title="Customer Concentration"
      subtitle="Top 5 + Others"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="flex items-center gap-4">
        <ResponsiveContainer width={120} height={120}>
          <PieChart>
            <Pie
              data={slices}
              dataKey="revenue"
              cx="50%"
              cy="50%"
              innerRadius={30}
              outerRadius={52}
              paddingAngle={2}
            >
              {slices.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip
              {...tooltipStyle}
              formatter={fmt("Revenue")}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex-1 space-y-1.5">
          {slices.map((s, i) => (
            <div key={s.name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: COLORS[i % COLORS.length] }}
                />
                <span className="text-zinc-300 truncate max-w-[100px]">{s.name}</span>
              </div>
              <span className="text-zinc-500 tabular-nums">{s.pct.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

// ── S4 Top SKUs ───────────────────────────────────────────────────────────────
function TopSkusPanel() {
  const { data, error, isLoading } = useTopSkus(30);
  const skus = data?.data?.skus ?? [];
  const max  = skus[0]?.revenue ?? 1;
  return (
    <PanelWrapper
      title="Top SKUs by Revenue"
      subtitle="Last 30 days"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="space-y-2 pt-1">
        {skus.slice(0, 8).map((s) => (
          <div key={s.sku_code} className="flex items-center gap-2 text-xs">
            <span className="text-zinc-500 font-mono w-14 shrink-0 truncate">
              {s.sku_code}
            </span>
            <div className="flex-1 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full rounded-full bg-blue-500"
                style={{ width: `${(s.revenue / max) * 100}%` }}
              />
            </div>
            <span className="text-zinc-300 tabular-nums w-16 text-right shrink-0">
              {formatCurrency(s.revenue, true)}
            </span>
          </div>
        ))}
      </div>
    </PanelWrapper>
  );
}

// ── S5 Quote Pipeline ─────────────────────────────────────────────────────────
function QuotePipelinePanel() {
  const { data, error, isLoading } = useQuoteSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper
      title="Quote Pipeline"
      subtitle="Last 30 days"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard
          label="Open Quotes"
          value={formatNumber(d?.open_count ?? 0)}
          accent="blue"
          sub={formatCurrency(d?.open_value ?? 0, true)}
        />
        <KpiCard
          label="Won"
          value={formatNumber(d?.won_count ?? 0)}
          accent="emerald"
          sub={formatCurrency(d?.won_value ?? 0, true)}
        />
        <KpiCard
          label="Conversion Rate"
          value={`${((d?.conversion_rate ?? 0) * 100).toFixed(1)}%`}
          accent="violet"
        />
      </div>
    </PanelWrapper>
  );
}

// ── S6 Purchase Summary ───────────────────────────────────────────────────────
function PurchaseSummaryPanel() {
  const { data, error, isLoading } = usePurchaseSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper
      title="Purchases"
      subtitle="Last 30 days"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard
          label="Total Spend"
          value={formatCurrency(d?.period_total ?? 0, true)}
          accent="amber"
          sub={`${d?.invoice_count ?? 0} invoices`}
        />
        <KpiCard
          label="Monthly Avg"
          value={formatCurrency(d?.monthly_avg ?? 0, true)}
          accent="blue"
        />
        <KpiCard
          label="Active Vendors"
          value={formatNumber(d?.vendor_count ?? 0)}
          accent="emerald"
        />
      </div>
    </PanelWrapper>
  );
}

// ── S7 BOM Coverage ───────────────────────────────────────────────────────────
function BomCoveragePanel() {
  const { data, error, isLoading } = useBomCoverage();
  const d = data?.data;
  const pct = d?.coverage_pct ?? 0;
  return (
    <PanelWrapper
      title="BOM Coverage"
      subtitle="Items with routing"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="pt-2 space-y-3">
        <div className="flex items-end justify-between">
          <span className="text-3xl font-bold text-blue-400 tabular-nums">
            {pct.toFixed(1)}%
          </span>
          <span className="text-xs text-zinc-500">
            {d?.items_with_bom}/{d?.total_items} items
          </span>
        </div>
        <div className="w-full bg-zinc-800 rounded-full h-2 overflow-hidden">
          <div
            className="h-full rounded-full bg-blue-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        {(d?.items_missing_bom ?? 0) > 0 && (
          <p className="text-xs text-amber-400">
            {d?.items_missing_bom} items missing BOM
          </p>
        )}
      </div>
    </PanelWrapper>
  );
}

// ── O1 AR Aging ───────────────────────────────────────────────────────────────
function ArAgingPanel() {
  const { data, error, isLoading } = useArSummary();
  const d = data?.data;
  const buckets = d?.buckets ?? [];
  return (
    <PanelWrapper
      title="AR Aging"
      subtitle="Outstanding receivables"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="space-y-3 pt-1">
        <div className="flex gap-4">
          <KpiCard
            label="Total Outstanding"
            value={formatCurrency(d?.total_outstanding ?? 0, true)}
            accent="blue"
          />
          <KpiCard
            label="Overdue"
            value={formatCurrency(d?.overdue_amount ?? 0, true)}
            accent="red"
            sub={`${((d?.overdue_pct ?? 0) * 100).toFixed(1)}% of total`}
          />
        </div>
        <ResponsiveContainer width="100%" height={120}>
          <BarChart
            data={buckets}
            layout="vertical"
            margin={{ left: 0, right: 8, top: 0, bottom: 0 }}
          >
            <XAxis
              type="number"
              tick={{ fill: "#71717a", fontSize: 9 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => formatCurrency(v, true)}
            />
            <YAxis
              type="category"
              dataKey="bucket"
              tick={{ fill: "#71717a", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={60}
            />
            <Tooltip
              {...tooltipStyle}
              formatter={fmt("Amount")}
            />
            <Bar dataKey="amount" fill={AMBER} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </PanelWrapper>
  );
}

// ── O2 Open Sales Orders ──────────────────────────────────────────────────────
function OpenOrdersPanel() {
  const { data, error, isLoading } = useOpenOrders();
  const d = data?.data;
  const byStatus = d?.by_status ?? [];
  return (
    <PanelWrapper
      title="Open Sales Orders"
      subtitle="Live order book"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="space-y-3 pt-1">
        <div className="flex gap-4">
          <KpiCard
            label="Open Orders"
            value={formatNumber(d?.open_count ?? 0)}
            accent="blue"
          />
          <KpiCard
            label="Open Value"
            value={formatCurrency(d?.open_value ?? 0, true)}
            accent="emerald"
          />
          <KpiCard
            label="Oldest Order"
            value={`${d?.oldest_order_days ?? 0}d`}
            accent="amber"
          />
        </div>
        <div className="space-y-1">
          {byStatus.map((s) => (
            <div key={s.status} className="flex justify-between text-xs">
              <span className="text-zinc-400">{s.status}</span>
              <div className="flex gap-3">
                <span className="text-zinc-500">{s.count} orders</span>
                <span className="text-zinc-300 tabular-nums">
                  {formatCurrency(s.value, true)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

// ── O3 Open POs ───────────────────────────────────────────────────────────────
function OpenPosPanel() {
  const { data, error, isLoading } = useOpenPOs();
  const d = data?.data;
  return (
    <PanelWrapper
      title="Open Purchase Orders"
      subtitle="Live PO book"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="space-y-3 pt-1">
        <div className="flex gap-4">
          <KpiCard
            label="Open POs"
            value={formatNumber(d?.open_count ?? 0)}
            accent="blue"
          />
          <KpiCard
            label="Open Value"
            value={formatCurrency(d?.open_value ?? 0, true)}
            accent="amber"
          />
          <KpiCard
            label="Overdue POs"
            value={formatNumber(d?.overdue_count ?? 0)}
            accent="red"
          />
        </div>
        <div className="space-y-1">
          {(d?.by_vendor ?? []).slice(0, 5).map((v) => (
            <div key={v.vendor_name} className="flex justify-between text-xs">
              <span className="text-zinc-400 truncate max-w-[140px]">
                {v.vendor_name}
              </span>
              <span className="text-zinc-300 tabular-nums">
                {formatCurrency(v.value, true)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

// ── O4 Inventory ──────────────────────────────────────────────────────────────
function InventoryPanel() {
  const { data: sumData, error: sumError, isLoading: sumLoading } = useInventorySummary();
  const { data: catData } = useInventoryByCategory();
  const d          = sumData?.data;
  const categories = catData?.data?.categories ?? [];
  return (
    <PanelWrapper
      title="Inventory"
      subtitle="Stock valuation"
      meta={sumData?.meta}
      loading={sumLoading}
      error={sumError}
    >
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-3">
          <KpiCard
            label="Total Value"
            value={formatCurrency(d?.total_value ?? 0, true)}
            accent="blue"
          />
          <KpiCard
            label="SKUs Tracked"
            value={formatNumber(d?.total_skus ?? 0)}
            accent="emerald"
          />
          <KpiCard
            label="Low Stock"
            value={formatNumber(d?.low_stock_count ?? 0)}
            accent="amber"
          />
          <KpiCard
            label="Zero Stock"
            value={formatNumber(d?.zero_stock_count ?? 0)}
            accent="red"
          />
        </div>
        {categories.length > 0 && (
          <ResponsiveContainer width="100%" height={90}>
            <BarChart
              data={categories.slice(0, 6)}
              margin={{ top: 0, right: 4, left: -20, bottom: 0 }}
            >
              <XAxis
                dataKey="category"
                tick={{ fill: "#71717a", fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#71717a", fontSize: 9 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => formatCurrency(v, true)}
              />
              <Tooltip
                {...tooltipStyle}
                formatter={fmt("Value")}
              />
              <Bar dataKey="value" fill={GREEN} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </PanelWrapper>
  );
}

// ── O5 GRN ────────────────────────────────────────────────────────────────────
function GrnPanel() {
  const { data, error, isLoading } = useGrnSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper
      title="GRN / Goods Received"
      subtitle="Last 30 days"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard
          label="GRNs Received"
          value={formatNumber(d?.received_count ?? 0)}
          accent="blue"
          sub={formatCurrency(d?.total_value ?? 0, true)}
        />
        <KpiCard
          label="Pending QIR"
          value={formatNumber(d?.pending_qir ?? 0)}
          accent="amber"
        />
        <KpiCard
          label="Rejection Rate"
          value={`${((d?.rejection_rate ?? 0) * 100).toFixed(1)}%`}
          accent={(d?.rejection_rate ?? 0) > 0.05 ? "red" : "emerald"}
        />
      </div>
    </PanelWrapper>
  );
}

// ── O6 Production ─────────────────────────────────────────────────────────────
function ProductionPanel() {
  const { data, error, isLoading } = useProductionSummary();
  const d = data?.data;
  return (
    <PanelWrapper
      title="Production"
      subtitle="WIP & completed jobs"
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard
          label="WIP Jobs"
          value={formatNumber(d?.wip_count ?? 0)}
          accent="blue"
          sub={formatCurrency(d?.wip_value ?? 0, true)}
        />
        <KpiCard
          label="Completed"
          value={formatNumber(d?.completed_count ?? 0)}
          accent="emerald"
        />
        <KpiCard
          label="Avg Cycle Time"
          value={`${(d?.avg_cycle_days ?? 0).toFixed(1)}d`}
          accent="amber"
        />
      </div>
    </PanelWrapper>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Main — 18-panel overview grid
// ════════════════════════════════════════════════════════════════════════════
export default function DashboardOverview() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Business Overview</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          KBrushes · Powered by TranzAct · Panels refresh automatically
        </p>
      </div>

      {/* Strategic panels — daily cache */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-600 uppercase tracking-wider mb-3">
          Strategic — Daily Refresh
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <RevenueKpiPanel />
          <RevenueTrendPanel />
          <CustomerConcentrationPanel />
          <TopSkusPanel />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mt-4">
          <QuotePipelinePanel />
          <PurchaseSummaryPanel />
          <BomCoveragePanel />
          <PanelWrapper title="Top Vendors" subtitle="See Purchases page for full breakdown">
            <p className="text-xs text-zinc-600 pt-3">
              Vendor-level analysis is available on the Purchases page.
            </p>
          </PanelWrapper>
        </div>
      </section>

      {/* Operational panels — hourly cache */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-600 uppercase tracking-wider mb-3">
          Operational — Hourly Refresh
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <ArAgingPanel />
          <OpenOrdersPanel />
          <OpenPosPanel />
          <InventoryPanel />
          <GrnPanel />
          <ProductionPanel />
        </div>
      </section>
    </div>
  );
}
