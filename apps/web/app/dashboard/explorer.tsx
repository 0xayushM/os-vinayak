"use client";

import { useState, useCallback } from "react";

// ── Report registry ───────────────────────────────────────────────────────────
const REPORTS = [
  { id: "29",  name: "Sales Invoices",       cadence: "daily",  table: "tz_sales_invoices",       panel: "Revenue" },
  { id: "102", name: "AR Aging",             cadence: "hourly", table: "tz_ar_aging",             panel: "Receivables" },
  { id: "2",   name: "Sales Orders",         cadence: "hourly", table: "tz_sales_orders",         panel: "Order Book" },
  { id: "77",  name: "Purchase Invoices",    cadence: "daily",  table: "tz_purchase_invoices",    panel: "Purchases" },
  { id: "3",   name: "Purchase Orders",      cadence: "hourly", table: "tz_purchase_orders",      panel: "POs" },
  { id: "34",  name: "GRN / QIR",           cadence: "daily",  table: "tz_grn_qir",             panel: "Goods Received" },
  { id: "8",   name: "Sales Quotations",     cadence: "daily",  table: "tz_sales_quotations",    panel: "Quotes" },
  { id: "9",   name: "Inventory Valuation",  cadence: "hourly", table: "tz_inventory_valuation", panel: "Inventory" },
  { id: "86",  name: "Process Routing",      cadence: "daily",  table: "tz_process_routing",     panel: "BOM / Routing" },
  { id: "25",  name: "Process Details",      cadence: "hourly", table: "tz_process_details",     panel: "Production" },
] as const;

type ReportId = (typeof REPORTS)[number]["id"];

// ── TranzAct response shape ───────────────────────────────────────────────────
interface TranzActResponse {
  success: boolean;
  report_generated_at?: string;
  data?: {
    results?: Record<string, unknown>[];
    total_items?: number;
    master_columns?: unknown[];
    sum_column_dict?: Record<string, unknown>;
  };
}

interface FetchResult {
  ok: boolean;
  status?: number;
  reportId?: string;
  page?: number;
  payload?: unknown;
  response?: TranzActResponse | unknown;
  error?: string;
  preview?: string;
  fetchedAt: string;
  durationMs: number;
}

interface AuthResult {
  ok: boolean;
  base_url?: string;
  token_preview?: string;
  expires_at?: string;
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function getDefaultFilters(_reportId: ReportId) {
  // TranzAct returns data without filters — leaving empty by default
  return "{}";
}

function getResponseData(result: FetchResult | null) {
  if (!result?.response) return null;
  const r = result.response as TranzActResponse;
  return r?.data ?? null;
}

function getTotalItems(result: FetchResult | null): number {
  return getResponseData(result)?.total_items ?? 0;
}

function getRows(result: FetchResult | null): Record<string, unknown>[] {
  return getResponseData(result)?.results ?? [];
}

function getTotalPages(result: FetchResult | null, perPage: number): number {
  const total = getTotalItems(result);
  return total > 0 ? Math.ceil(total / perPage) : 0;
}

// ── Sub-components ────────────────────────────────────────────────────────────
function Badge({ cadence }: { cadence: string }) {
  const hourly = cadence === "hourly";
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
      hourly ? "bg-blue-500/20 text-blue-400" : "bg-zinc-700 text-zinc-400"
    }`}>
      {cadence}
    </span>
  );
}

function JsonViewer({ data }: { data: unknown }) {
  const json = JSON.stringify(data, null, 2);
  const lines = json.split("\n");

  function colorizeLine(line: string, i: number) {
    const colored = line
      .replace(/"([^"]+)"(?=\s*:)/g, '<span class="text-sky-400">"$1"</span>')
      .replace(/:\s*"([^"]*)"/g,     ': <span class="text-emerald-400">"$1"</span>')
      .replace(/:\s*(\d+\.?\d*)/g,   ': <span class="text-amber-400">$1</span>')
      .replace(/:\s*(true|false)/g,  ': <span class="text-purple-400">$1</span>')
      .replace(/:\s*(null)/g,        ': <span class="text-red-400">$1</span>');
    return (
      <div key={i} className="flex">
        <span className="select-none text-zinc-700 w-10 text-right pr-4 shrink-0">{i + 1}</span>
        <span dangerouslySetInnerHTML={{ __html: colored }} />
      </div>
    );
  }

  return (
    <pre className="text-xs font-mono leading-5 overflow-auto">
      {lines.map(colorizeLine)}
    </pre>
  );
}

/** Shows the data rows in a horizontal-scroll table */
function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const columns = Object.keys(rows[0]);
  // Show most useful columns first, limit to 15 for readability
  const priorityCols = ["document_no_text", "customer_name", "document_date", "grand_total",
    "item_name", "quantity", "status", "payment_status", "document_status",
    "counter_party_company_name", "item_price", "tax", "created_date"];
  const sorted = [
    ...priorityCols.filter(c => columns.includes(c)),
    ...columns.filter(c => !priorityCols.includes(c)),
  ].slice(0, 15);

  return (
    <div className="overflow-auto">
      <table className="text-[11px] font-mono border-collapse min-w-full">
        <thead>
          <tr>
            <th className="text-left px-3 py-1.5 text-zinc-600 font-semibold border-b border-zinc-800 sticky top-0 bg-zinc-950">#</th>
            {sorted.map(col => (
              <th key={col} className="text-left px-3 py-1.5 text-zinc-500 font-semibold border-b border-zinc-800 sticky top-0 bg-zinc-950 whitespace-nowrap">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="hover:bg-zinc-900 border-b border-zinc-900">
              <td className="px-3 py-1 text-zinc-700">{i + 1}</td>
              {sorted.map(col => {
                const val = row[col];
                const display = val === null ? <span className="text-red-900">null</span>
                  : val === "" ? <span className="text-zinc-800">—</span>
                  : typeof val === "number" ? <span className="text-amber-400">{val.toLocaleString()}</span>
                  : typeof val === "boolean" ? <span className="text-purple-400">{String(val)}</span>
                  : <span className="text-zinc-300">{String(val).slice(0, 40)}</span>;
                return <td key={col} className="px-3 py-1 whitespace-nowrap">{display}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
const PER_PAGE = 50;

export default function DashboardPage() {
  const [selectedReport, setSelectedReport] = useState<ReportId>("29");
  const [page, setPage]                     = useState(1);
  const [filters, setFilters]               = useState("{}");
  const [result, setResult]                 = useState<FetchResult | null>(null);
  const [loading, setLoading]               = useState(false);
  const [authResult, setAuthResult]         = useState<AuthResult | null>(null);
  const [authLoading, setAuthLoading]       = useState(false);
  const [activeTab, setActiveTab]           = useState<"table" | "json" | "payload">("table");

  const selectReport = useCallback((id: ReportId) => {
    setSelectedReport(id);
    setFilters(getDefaultFilters(id));
    setResult(null);
    setPage(1);
    setActiveTab("table");
  }, []);

  const testAuth = useCallback(async () => {
    setAuthLoading(true);
    setAuthResult(null);
    try {
      const res = await fetch("/api/tranzact/login", { method: "POST" });
      const data: AuthResult = await res.json();
      setAuthResult(data);
    } catch (e) {
      setAuthResult({ ok: false, error: String(e) });
    } finally {
      setAuthLoading(false);
    }
  }, []);

  const fetchReport = useCallback(async (overridePage?: number) => {
    const targetPage = overridePage ?? page;
    setLoading(true);
    setResult(null);
    setActiveTab("table");
    const start = Date.now();

    let parsedFilters: Record<string, unknown> = {};
    try {
      parsedFilters = JSON.parse(filters);
    } catch { /* ignore */ }

    try {
      const res = await fetch("/api/tranzact/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reportId: selectedReport,
          page: targetPage,
          perPage: PER_PAGE,
          ...parsedFilters,
        }),
      });
      const data = await res.json();
      setResult({ ...data, fetchedAt: new Date().toISOString(), durationMs: Date.now() - start });
    } catch (e) {
      setResult({
        ok: false,
        error: String(e),
        fetchedAt: new Date().toISOString(),
        durationMs: Date.now() - start,
      });
    } finally {
      setLoading(false);
    }
  }, [selectedReport, page, filters]);

  const goToPage = useCallback((newPage: number) => {
    setPage(newPage);
    fetchReport(newPage);
  }, [fetchReport]);

  const currentReport  = REPORTS.find(r => r.id === selectedReport)!;
  const rows           = getRows(result);
  const totalItems     = getTotalItems(result);
  const totalPages     = getTotalPages(result, PER_PAGE);
  const reportedAt     = (result?.response as TranzActResponse)?.report_generated_at;

  return (
    <div className="flex h-screen overflow-hidden">

      {/* ── Sidebar ──────────────────────────────────────────────────────────── */}
      <aside className="w-64 shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col overflow-hidden">
        <div className="px-4 py-4 border-b border-zinc-800">
          <div className="text-sm font-bold text-white">🪣 Vinayak Brain OS</div>
          <div className="text-[11px] text-zinc-500 mt-0.5">KBrushes · TranzAct Explorer</div>
        </div>

        {/* Auth test */}
        <div className="px-3 py-3 border-b border-zinc-800">
          <button
            onClick={testAuth}
            disabled={authLoading}
            className="w-full text-xs font-medium px-3 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            {authLoading ? <span className="animate-spin">↻</span> : "🔑"}
            {authLoading ? "Testing auth…" : "Test Authentication"}
          </button>
          {authResult && (
            <div className={`mt-2 text-[10px] rounded p-2 font-mono ${
              authResult.ok
                ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                : "bg-red-950 text-red-400 border border-red-900"
            }`}>
              {authResult.ok ? (
                <>
                  <div>✅ Auth OK · be.letstranzact.com</div>
                  <div className="text-zinc-500 mt-1">{authResult.token_preview}</div>
                  <div className="text-zinc-400 mt-0.5">
                    Expires: {authResult.expires_at
                      ? new Date(authResult.expires_at).toLocaleTimeString()
                      : "—"}
                  </div>
                </>
              ) : (
                <>
                  <div>❌ Auth failed</div>
                  <div className="mt-1 text-red-400 break-all">{authResult.error}</div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Report list */}
        <div className="flex-1 overflow-y-auto py-2">
          <div className="px-3 pb-1 text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
            TranzAct Reports
          </div>
          {REPORTS.map(r => (
            <button
              key={r.id}
              onClick={() => selectReport(r.id)}
              className={`w-full text-left px-3 py-2.5 flex flex-col gap-0.5 transition-colors ${
                selectedReport === r.id
                  ? "bg-blue-600/20 border-r-2 border-blue-500"
                  : "hover:bg-zinc-800"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium ${selectedReport === r.id ? "text-white" : "text-zinc-300"}`}>
                  {r.name}
                </span>
                <Badge cadence={r.cadence} />
              </div>
              <div className="text-[10px] text-zinc-600">
                #{r.id} · {r.panel}
              </div>
            </button>
          ))}
        </div>

        <div className="px-3 py-2 border-t border-zinc-800 text-[10px] text-zinc-600">
          reporting.letstranzact.com/generate_report
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col overflow-hidden">

        {/* Header */}
        <header className="shrink-0 bg-zinc-900 border-b border-zinc-800 px-5 py-3 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-sm font-bold text-white">{currentReport.name}</h1>
            <div className="text-[11px] text-zinc-500">
              Report #{currentReport.id} · {currentReport.table}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <Badge cadence={currentReport.cadence} />
            {result && (
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                result.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
              }`}>
                {result.ok ? `HTTP ${result.status}` : "Error"} · {result.durationMs}ms
              </span>
            )}
            {totalItems > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 font-medium">
                {totalItems.toLocaleString()} total rows
              </span>
            )}
            {reportedAt && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500">
                as of {reportedAt}
              </span>
            )}
          </div>
        </header>

        {/* Controls */}
        <div className="shrink-0 bg-zinc-900/50 border-b border-zinc-800 px-5 py-3 flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1">
              Filters JSON (optional)
            </label>
            <textarea
              value={filters}
              onChange={e => setFilters(e.target.value)}
              rows={1}
              spellCheck={false}
              className="w-full bg-zinc-800 text-zinc-200 text-xs font-mono rounded-md px-3 py-2 border border-zinc-700 focus:border-blue-500 focus:outline-none resize-none"
            />
          </div>
          <button
            onClick={() => { setPage(1); fetchReport(1); }}
            disabled={loading}
            className="px-5 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap"
          >
            {loading && <span className="animate-spin">↻</span>}
            {loading ? "Fetching…" : "Fetch Report"}
          </button>
        </div>

        {/* Result area */}
        <div className="flex-1 overflow-hidden flex flex-col">

          {/* Empty / loading states */}
          {!result && !loading && (
            <div className="flex-1 flex flex-col items-center justify-center text-zinc-600">
              <div className="text-4xl mb-3">📊</div>
              <div className="text-sm font-medium">Click Fetch Report to load data</div>
              <div className="text-xs mt-1 text-zinc-700">Report #{currentReport.id} · {currentReport.name}</div>
            </div>
          )}

          {loading && (
            <div className="flex-1 flex flex-col items-center justify-center text-zinc-500">
              <div className="text-2xl mb-3 animate-spin">↻</div>
              <div className="text-sm">Fetching from reporting.letstranzact.com…</div>
            </div>
          )}

          {result && !loading && (
            <div className="flex-1 flex flex-col overflow-hidden">

              {/* Tabs + pagination */}
              <div className="shrink-0 flex items-center border-b border-zinc-800 px-5 bg-zinc-900/30">
                {(["table", "json", "payload"] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`text-xs font-medium px-4 py-2.5 border-b-2 transition-colors ${
                      activeTab === tab
                        ? "border-blue-500 text-white"
                        : "border-transparent text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {tab === "table" ? `Table (${rows.length} rows)` : tab === "json" ? "Raw JSON" : "Payload"}
                  </button>
                ))}

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="ml-auto flex items-center gap-1.5 py-1.5">
                    <span className="text-[10px] text-zinc-600">
                      Page {page} / {totalPages}
                    </span>
                    <button
                      disabled={page <= 1}
                      onClick={() => goToPage(page - 1)}
                      className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      ← prev
                    </button>
                    <button
                      disabled={page >= totalPages}
                      onClick={() => goToPage(page + 1)}
                      className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      next →
                    </button>
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 overflow-auto p-5 bg-zinc-950">
                {result.error ? (
                  <div className="bg-red-950 border border-red-900 rounded-lg p-4">
                    <div className="text-xs font-bold text-red-400 mb-1">❌ {result.error}</div>
                    {result.preview && (
                      <pre className="text-[10px] font-mono text-red-900 mt-2 whitespace-pre-wrap">{result.preview}</pre>
                    )}
                  </div>
                ) : activeTab === "table" ? (
                  rows.length > 0
                    ? <RowsTable rows={rows} />
                    : <div className="text-zinc-600 text-sm text-center py-16">No rows returned</div>
                ) : activeTab === "json" ? (
                  <JsonViewer data={result.response} />
                ) : (
                  <JsonViewer data={result.payload} />
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
