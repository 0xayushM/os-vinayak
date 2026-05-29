/**
 * useDashboard.ts
 * ───────────────
 * SWR hook wrappers for every dashboard panel endpoint.
 *
 * All calls go to /api/dashboard/* (Next.js BFF routes).
 * The BFF proxies to FastAPI over a private, server-only network address.
 * The FastAPI URL is NEVER present in this file or in the browser network tab.
 */
import useSWR, { SWRConfiguration } from "swr";

// ── SWR fetcher ───────────────────────────────────────────────────────────────
async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Response envelope type ────────────────────────────────────────────────────
export interface PanelMeta {
  report_id:     number;
  last_synced_at: string | null;
  stale:          boolean;
}

export interface PanelResponse<T> {
  data: T;
  meta: PanelMeta;
}

// ── Refresh intervals ─────────────────────────────────────────────────────────
const HOURLY  = 60 * 60 * 1_000;
const DAILY   = 24 * HOURLY;

const swrHourly: SWRConfiguration = { refreshInterval: HOURLY,  revalidateOnFocus: false };
const swrDaily:  SWRConfiguration = { refreshInterval: DAILY,   revalidateOnFocus: false };

// ── Revenue panels ────────────────────────────────────────────────────────────
export interface RevenueSummary {
  period_days:    number;
  period_total:   number;
  invoice_count:  number;
  customer_count: number;
  monthly_avg:    number;
  ytd_total:      number;
}

export function useRevenueSummary(days = 30) {
  return useSWR<PanelResponse<RevenueSummary>>(
    `/api/dashboard/revenue-summary?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface RevenueTrendMonth { month: string; revenue: number; invoice_count: number; }
export interface RevenueTrend { months: RevenueTrendMonth[]; }

export function useRevenueTrend(months = 6) {
  return useSWR<PanelResponse<RevenueTrend>>(
    `/api/dashboard/revenue-trend?months=${months}`,
    fetcher,
    swrDaily,
  );
}

export interface CustomerSlice { name: string; revenue: number; pct: number; }
export interface CustomerConcentration { slices: CustomerSlice[]; }

export function useCustomerConcentration(days = 30) {
  return useSWR<PanelResponse<CustomerConcentration>>(
    `/api/dashboard/customer-concentration?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface TopSku { sku_code: string; item_name: string; qty_sold: number; revenue: number; }
export interface TopSkus { skus: TopSku[]; }

export function useTopSkus(days = 30) {
  return useSWR<PanelResponse<TopSkus>>(
    `/api/dashboard/top-skus?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface QuoteSummary {
  open_count: number; open_value: number;
  won_count: number; won_value: number;
  conversion_rate: number;
}

export function useQuoteSummary(days = 30) {
  return useSWR<PanelResponse<QuoteSummary>>(
    `/api/dashboard/quote-summary?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface PurchaseSummary {
  period_total: number; invoice_count: number; vendor_count: number; monthly_avg: number;
}

export function usePurchaseSummary(days = 30) {
  return useSWR<PanelResponse<PurchaseSummary>>(
    `/api/dashboard/purchase-summary?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface TopVendor { vendor_name: string; spend: number; invoice_count: number; }
export interface TopVendors { vendors: TopVendor[]; }

export function useTopVendors(days = 30) {
  return useSWR<PanelResponse<TopVendors>>(
    `/api/dashboard/top-vendors?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface BomCoverage {
  total_items: number; items_with_bom: number; coverage_pct: number; items_missing_bom: number;
}

export function useBomCoverage() {
  return useSWR<PanelResponse<BomCoverage>>("/api/dashboard/bom-coverage", fetcher, swrDaily);
}

// ── AR panel ──────────────────────────────────────────────────────────────────
export interface ArBucket {
  bucket: string; amount: number; invoice_count: number; overdue_days_avg: number;
}
export interface ArSummary {
  total_outstanding: number; overdue_amount: number; overdue_pct: number; buckets: ArBucket[];
}

export function useArSummary() {
  return useSWR<PanelResponse<ArSummary>>("/api/dashboard/ar-summary", fetcher, swrHourly);
}

// ── Open orders panel ─────────────────────────────────────────────────────────
export interface OpenOrderSummary {
  open_count: number; open_value: number; oldest_order_days: number;
  by_status: { status: string; count: number; value: number }[];
}

export function useOpenOrders() {
  return useSWR<PanelResponse<OpenOrderSummary>>(
    "/api/dashboard/open-orders",
    fetcher,
    swrHourly,
  );
}

// ── Purchase orders panel ─────────────────────────────────────────────────────
export interface OpenPoSummary {
  open_count: number; open_value: number; overdue_count: number;
  by_vendor: { vendor_name: string; count: number; value: number }[];
}

export function useOpenPOs() {
  return useSWR<PanelResponse<OpenPoSummary>>(
    "/api/dashboard/open-pos",
    fetcher,
    swrHourly,
  );
}

// ── Inventory panels ──────────────────────────────────────────────────────────
export interface InventorySummary {
  total_value: number; total_skus: number; low_stock_count: number; zero_stock_count: number;
}

export function useInventorySummary() {
  return useSWR<PanelResponse<InventorySummary>>(
    "/api/dashboard/inventory-summary",
    fetcher,
    swrHourly,
  );
}

export interface InventoryCategory { category: string; value: number; sku_count: number; }
export interface InventoryByCategory { categories: InventoryCategory[]; total_value: number; }

export function useInventoryByCategory() {
  return useSWR<PanelResponse<InventoryByCategory>>(
    "/api/dashboard/inventory-by-category",
    fetcher,
    swrHourly,
  );
}

// ── GRN / production panels ───────────────────────────────────────────────────
export interface GrnSummary {
  received_count: number; total_value: number; pending_qir: number; rejection_rate: number;
}

export function useGrnSummary(days = 30) {
  return useSWR<PanelResponse<GrnSummary>>(
    `/api/dashboard/grn-summary?days=${days}`,
    fetcher,
    swrDaily,
  );
}

export interface ProductionSummary {
  wip_count: number; wip_value: number; completed_count: number; avg_cycle_days: number;
}

export function useProductionSummary() {
  return useSWR<PanelResponse<ProductionSummary>>(
    "/api/dashboard/production-summary",
    fetcher,
    swrHourly,
  );
}

// ── Sync health ───────────────────────────────────────────────────────────────
export interface SyncRun {
  pipeline_name: string; status: string; started_at: string;
  completed_at: string | null; rows_upserted: number | null; error_message: string | null;
}
export interface SyncHealth { runs: SyncRun[]; stale_pipelines: string[]; healthy: boolean; }

export function useSyncHealth() {
  return useSWR<SyncHealth>("/api/dashboard/sync-health", fetcher, {
    refreshInterval: 5 * 60 * 1_000,
    revalidateOnFocus: true,
  });
}
