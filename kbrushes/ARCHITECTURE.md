# KBrushes — Vinayak Brain OS
## Full Architecture Document
**Phase 1: TranzAct → Dashboard**
*BrewMyAgent · May 2026*

---

## 0. Tech Stack (Recommended)

| Layer | Technology | Why |
|---|---|---|
| HTTP Client (Layer A) | **httpx** (async) | Async-native, connection pooling, same API as requests but non-blocking. Essential for FastAPI's event loop. |
| Scheduler (Layer B) | **APScheduler** | Runs inside the FastAPI process — no separate Celery worker. AsyncIOScheduler shares the event loop. Cron expressions for exact IST timing. |
| Database | **PostgreSQL on Railway** | Railway hosts both Postgres and the Python service in one platform. Use Supabase if you want a visual SQL editor. |
| DB Driver | **asyncpg** | Faster than psycopg2 for async workloads. Used for all pipeline upserts and dashboard queries. |
| API (Layer C) | **FastAPI** | Auto-generates Swagger docs, native async, Pydantic response models. Phase 2 AI endpoints slot straight in. |
| Data Validation | **Pydantic v2** | Row validation in every pipeline before upsert. Type coercion, required field checks, date parsing. |
| Frontend | **Vanilla JS + Chart.js** | No build step, no npm. Same pattern as the KBrushes diagnostic report. Works offline. Migrate to React in Phase 2 if needed. |
| AI Layer (Phase 2) | **Anthropic SDK** | Direct tool_use calls against pre-aggregated query functions. No LangChain — simpler, faster, fewer failure modes. |
| JWT Decoding | **python-jose** | Extracts `exp` claim from TranzAct JWTs to know exactly when tokens expire. |

**Single-process deployment:** FastAPI (uvicorn) + APScheduler run in the same Python process. No Redis, no message queue, no separate worker in Phase 1. Token cache is in-memory. Add Redis only if you scale to multiple workers.

---

## 1. Why This Architecture Exists

TranzAct is a data-entry tool. It holds the truth about KBrushes' invoices, inventory, production, and orders — but it surfaces none of the intelligence. Vinayak Brain OS sits on top of it and does three things TranzAct never will:

1. **Consolidate** — pull all relevant data from TranzAct on a schedule and hold it in a clean Postgres database that we own and control.
2. **Visualise** — serve a live dashboard that Sandeep opens on his phone every morning; every panel shows data freshness so he always knows how recent it is.
3. **Reason** — in Phase 2, an AI layer answers natural-language questions by running pre-aggregated queries against our Postgres cache. It never speaks directly to TranzAct. This is the anti-context-rot guarantee.

Phase 1 delivers points 1 and 2. Phase 2 adds point 3. The database schema and query layer designed here are built with Phase 2 in mind — the AI layer will slot in without any migration.

---

## 2. End-to-End Data Flow

```
TranzAct ERP (source of truth)
  │  Invoices, Inventory, Orders, Production, AR
  │
  ▼  POST /main/login/password-login/  ←── one-time login, token cached
  │
  ▼  POST /generate_report             ←── only extraction endpoint
  │  Authorization: Bearer <token>
  │  Body: { report: {id: "29"}, pagination: {...}, filters: {...} }
  │
  ▼  auth.py + client.py (Layer A)
  │  • Token checked before every call
  │  • Pagination loop until all rows fetched
  │  • Exponential backoff on 429/5xx
  │
  ▼  Pipeline module (Layer B)
  │  • Rows validated by Pydantic schema
  │  • UPSERT into tz_* table (never full replace — safe on failure)
  │  • tz_sync_runs updated: rows_fetched, rows_upserted, status
  │
  ▼  PostgreSQL (The Cache)
  │  • Dashboard NEVER calls TranzAct directly
  │  • Old data stays during a failed sync (stale > empty)
  │  • Every panel loads in <2s from cache
  │
  ▼  queries.py (Layer C)
  │  • Pre-aggregated business functions, never raw rows
  │  • Top-N caps enforced (Phase 2 AI reads only from here)
  │
  ▼  FastAPI — 17 endpoints
  │  • JSON envelope: { data, meta.last_synced_at, meta.stale }
  │  • GET /dashboard/sync/health always live
  │
  ▼  dashboard/index.html
     • 12 strategic panels (daily) + 5 operational panels (hourly)
     • Every panel: "last synced X min ago"
     • "Refresh Now" triggers cache invalidation
     • Phase 2: AI chat layer slots in here
```

---

## 3. The One Critical Fact About TranzAct's API

TranzAct has 104 documented endpoints. Approximately 70 are CREATE/POST endpoints for pushing data **into** TranzAct. The data **extraction** surface is effectively a single endpoint:

```
POST /generate_report
Body: { "report": {"id": "<report_id>"}, "pagination": {...}, <filters> }
```

Every report type is called through this one endpoint with a different `report.id`. The auth endpoint:

```
POST /main/login/password-login/
Body: { "email": "...", "password": "..." }
Returns: { "data": { "access_token": "<JWT>", "refresh_token": "<JWT>" } }
Throttle: 10 requests / minute / machine
```

**Architecture consequence:** we do not mirror TranzAct's database. We run the relevant reports on a schedule, cache their output in Postgres, and expose that cache to the dashboard and (later) the AI. For ad-hoc queries, the AI gets one sandboxed tool that calls `/generate_report` live against the 11 whitelisted report IDs only.

---

## 3. Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER A — TranzAct Adapters                                    │
│  adapters/tranzact/                                             │
│  ┌────────────┐  ┌────────────────────────────────────────┐    │
│  │  auth.py   │  │  client.py                             │    │
│  │            │  │  fetch_report(report_id, filters, ...) │    │
│  │  login()   │  │  • POST /generate_report               │    │
│  │  refresh() │  │  • exponential backoff                 │    │
│  │  cache     │  │  • pagination handling                 │    │
│  │  throttle  │  │  • 8 req/min rate limit                │    │
│  └────────────┘  └────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ typed Python dicts
┌──────────────────────────────▼──────────────────────────────────┐
│  LAYER B — Data Pipelines                                       │
│  pipelines/                                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  base.py — BasePipeline                                    │ │
│  │  • run(): fetch → validate → upsert → update tz_sync_runs │ │
│  │  • backfill(from_date): same, multiple date windows        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  10 concrete pipelines (one per report):                        │
│  sales_invoices.py (report 29, daily)                           │
│  ar_aging.py       (report 102, hourly)    ← operational        │
│  sales_orders.py   (report 2, hourly)      ← operational        │
│  purchase_invoices.py (report 77, daily)                        │
│  purchase_orders.py   (report 3, hourly)   ← operational        │
│  grn_qir.py           (report 34, daily)                        │
│  sales_quotations.py  (report 8, daily)                         │
│  inventory_valuation.py (report 9, hourly) ← operational        │
│  process_routing.py   (report 86, daily)                        │
│  process_details.py   (report 25, hourly)  ← operational        │
│                                                                 │
│  scheduler.py — APScheduler orchestrates daily + hourly jobs    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ SQL (psycopg2 / asyncpg)
┌──────────────────────────────▼──────────────────────────────────┐
│  POSTGRES DATABASE — The Cache                                  │
│  schema/init.sql                                                │
│                                                                 │
│  10 cached tables  +  tz_sync_runs                              │
│  (see Section 5 for full schema)                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │ pre-aggregated queries
┌──────────────────────────────▼──────────────────────────────────┐
│  LAYER C — Business Logic + API                                 │
│  schema/queries.py — pre-aggregated query functions             │
│  api/main.py       — FastAPI app                                │
│  api/routes/dashboard.py — 17 panel endpoints                   │
│  api/routes/ai_tool.py   — Phase 2 AI query endpoint            │
│                                                                 │
│  dashboard/index.html — Single-page live dashboard              │
└─────────────────────────────────────────────────────────────────┘
```

**Strict separation of concerns:**
- Layer A knows nothing about Postgres. It speaks only to TranzAct.
- Layer B knows nothing about the dashboard. It fetches and stores.
- Layer C knows nothing about TranzAct. It reads only from Postgres.

---

## 4. Bearer Token Management (Complete Lifecycle)

TranzAct requires a Bearer token on every `POST /generate_report` call. Here is exactly how we manage it:

### Step 1 — Initial login
On first request (or when no token exists in memory), `auth.py` calls the login endpoint:
```
POST /main/login/password-login/
Body: { "email": "...", "password": "..." }
Response: { "data": { "access_token": "eyJ...", "refresh_token": "eyJ..." } }
```
Both tokens are JWT strings. The `exp` claim inside each token tells us exactly when it expires. We decode this with `python-jose` — no guesswork about token lifetime.

### Step 2 — In-memory cache
Both tokens are stored in a module-level `_TokenCache` singleton (thread-safe). The cache holds:
- `access_token` + its Unix expiry timestamp
- `refresh_token` + its Unix expiry timestamp

### Step 3 — Check before every API call
`get_access_token()` is called before every `POST /generate_report`. Three outcomes:

| Token state | Action | Cost |
|---|---|---|
| Access token valid (>2 min remaining) | Return cached token immediately | 0 network calls |
| Access token expiring soon (<2 min) | POST to `/token/refresh/` with refresh_token → get new access_token | 1 API call (does NOT count against 10/min data limit significantly) |
| Both tokens expired | Full re-login with email+password | 1 API call (counts as 1 of 10/min) |

### Step 4 — Attach to every request
```python
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}
httpx.post("https://app.tranzact.in/generate_report", headers=headers, json={...})
```

### Step 5 — Handle mid-pipeline 401
If TranzAct invalidates a token server-side before our cached expiry (e.g. they rotate secrets), the response is `HTTP 401`. We handle this with one forced re-login + retry:
```python
if response.status_code == 401:
    token = get_access_token(force_refresh=True)   # bypasses cache
    response = retry_request(headers={"Authorization": f"Bearer {token}"})
```

### Rate limit reality
- TranzAct enforces **10 requests/minute/machine**
- Login = 1 request. Each page of a report = 1 request.
- A report with 500 rows at 50 rows/page = 10 requests alone
- We run at **8 req/min max** (configurable via `TRANZACT_REQUESTS_PER_MINUTE=8`)
- Hourly pipelines are **staggered** (not all starting at :00:00) to prevent bursting

### Multi-worker note
The in-memory cache works only for single-worker deployments. If you ever run 2+ uvicorn workers, each worker gets its own token and doubles the login calls. At that point, move the token cache to Redis with a 28-minute TTL. Do not do this prematurely — single worker is fine for Phase 1.

---

## 5. File Structure

```
kbrushes/
├── config.py                          # Env vars (credentials never hardcoded)
├── requirements.txt
├── .env.example
├── ARCHITECTURE.md                    # This document
│
├── adapters/
│   └── tranzact/
│       ├── __init__.py
│       ├── auth.py                    # JWT login, refresh, in-memory cache
│       ├── client.py                  # fetch_report() with backoff + pagination
│       └── reports.py                 # Report ID constants + field schemas
│
├── pipelines/
│   ├── __init__.py
│   ├── base.py                        # BasePipeline (run, backfill, sync logging)
│   ├── sales_invoices.py              # report_id=29  → tz_sales_invoices
│   ├── ar_aging.py                    # report_id=102 → tz_ar_aging
│   ├── sales_orders.py                # report_id=2   → tz_sales_orders
│   ├── purchase_invoices.py           # report_id=77  → tz_purchase_invoices
│   ├── purchase_orders.py             # report_id=3   → tz_purchase_orders
│   ├── grn_qir.py                     # report_id=34  → tz_grn_qir
│   ├── sales_quotations.py            # report_id=8   → tz_sales_quotations
│   ├── inventory_valuation.py         # report_id=9   → tz_inventory_valuation
│   ├── process_routing.py             # report_id=86  → tz_process_routing
│   ├── process_details.py             # report_id=25  → tz_process_details
│   └── scheduler.py                   # APScheduler — daily + hourly jobs
│
├── schema/
│   ├── init.sql                       # DDL for all tables
│   └── queries.py                     # Pre-aggregated business query functions
│
├── api/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app entry point
│   └── routes/
│       ├── __init__.py
│       ├── dashboard.py               # GET /dashboard/* panel endpoints
│       └── ai_tool.py                 # POST /ai/query — Phase 2 prep
│
└── dashboard/
    └── index.html                     # Live single-page dashboard
```

---

## 6. Pipeline Execution Flow

Every pipeline follows this exact sequence on every run:

```
APScheduler fires run()
  │
  ├─▶ INSERT tz_sync_runs (status='running', started_at=NOW())
  │
  ├─▶ get_access_token()           ← checks cache, refreshes if needed
  │
  ├─▶ fetch_report(report_id, filters, page=1)
  │     └─ POST /generate_report   ← with Bearer token
  │     └─ if has_next_page: fetch page=2, page=3 … until done
  │
  ├─▶ Validate rows (Pydantic)     ← bad rows logged + skipped, never crash
  │
  ├─▶ UPSERT into tz_* table
  │     └─ ON CONFLICT (raw_id) DO UPDATE
  │     └─ Atomic — never leaves partial data
  │
  ├─▶ UPDATE tz_sync_runs (status='success', rows_fetched=N, completed_at=NOW())
  │
  └─▶ on any exception:
        UPDATE tz_sync_runs (status='failed', error_message=str(exc))
        ← old data stays in DB — stale is always better than empty
```

### Backfill (run once on Day 1)
`backfill(from_date="2025-11-01")` splits 6 months into 30-day windows:
- Window 1: Nov 1–30 → fetch → upsert
- Window 2: Dec 1–31 → fetch → upsert
- … continues to today
- 1-second sleep between windows to stay under rate limit
- Each window logs `is_backfill=TRUE` in tz_sync_runs

### Scheduler cadences

| Pipeline | Cadence | Fetch window | Why |
|---|---|---|---|
| ar_aging | Every hour | Last 2 days | Sandeep's most urgent data |
| sales_orders | Every hour | Last 7 days | Order book changes constantly |
| purchase_orders | Every hour | Last 7 days | Overdue PO alerts |
| inventory_valuation | Every hour | Current | Negative stock flags |
| process_details | Every hour | Last 7 days | WIP status |
| sales_invoices | Daily 3 AM IST | Last 30 days | Revenue analysis |
| purchase_invoices | Daily 3 AM IST | Last 30 days | Vendor spend |
| grn_qir | Daily 3 AM IST | Last 30 days | Goods received |
| sales_quotations | Daily 3 AM IST | Last 30 days | Quote conversion |
| process_routing | Daily 3 AM IST | Last 30 days | BOM / routing |

---

## 7. Database Schema

### 5.1 Mandatory columns on every cached table

Every table follows this contract. This is the **schema lock** — no deviations without a joint decision.

```sql
-- Every tz_* table has these columns:
fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- when we pulled from TranzAct
source_report   INTEGER NOT NULL                    -- report_id (traceability)
raw_id          TEXT NOT NULL                       -- TranzAct's own doc identifier
```

Upsert key is always `(raw_id)` — on conflict, we update all columns and refresh `fetched_at`.

### 5.2 Cached tables

| Table | Source report_id | Sync cadence | Purpose |
|---|---|---|---|
| `tz_sales_invoices` | 29 | Daily | Revenue, AR, customer analysis |
| `tz_ar_aging` | 102 | **Hourly** | Cash collection dashboard |
| `tz_sales_orders` | 2 | **Hourly** | Open order book |
| `tz_purchase_invoices` | 77 | Daily | Vendor spend analysis |
| `tz_purchase_orders` | 3 | **Hourly** | Overdue PO tracking |
| `tz_grn_qir` | 34 | Daily | Goods received vs ordered |
| `tz_sales_quotations` | 8 | Daily | Quotation conversion rate |
| `tz_inventory_valuation` | 9 | **Hourly** | Stock levels, negative stock alerts |
| `tz_process_routing` | 86 | Daily | Production BOM and routing |
| `tz_process_details` | 25 | **Hourly** | WIP, reject rate, production output |

**Hourly** = time-sensitive operational data (cash, orders, inventory, production). **Daily** = strategic/analytical data.

### 5.3 Sync metadata table

```sql
CREATE TABLE tz_sync_runs (
    id              SERIAL PRIMARY KEY,
    pipeline_name   TEXT NOT NULL,
    report_id       INTEGER NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running','success','failed')),
    rows_fetched    INTEGER,
    rows_upserted   INTEGER,
    error_message   TEXT,
    is_backfill     BOOLEAN DEFAULT FALSE
);

CREATE INDEX ON tz_sync_runs (pipeline_name, completed_at DESC);
```

**Data freshness rule:** if `MAX(completed_at)` for any pipeline is older than 25 hours, alert fires to engineering channel. Every dashboard panel shows its `last_synced_at` timestamp.

---

## 6. API Design

### 6.1 Dashboard endpoints (Layer C)

All endpoints return JSON with a consistent envelope:

```json
{
  "data": { ... },
  "meta": {
    "last_synced_at": "2026-05-21T07:43:00Z",
    "report_id": 29,
    "stale": false
  }
}
```

| Endpoint | Panel | Cadence |
|---|---|---|
| `GET /dashboard/revenue/summary` | Revenue KPIs (period total, monthly trend, annualised run-rate) | Daily |
| `GET /dashboard/revenue/customers` | Top customers by revenue + concentration | Daily |
| `GET /dashboard/revenue/skus` | Top SKUs by revenue | Daily |
| `GET /dashboard/ar/aging` | AR aging buckets + overdue subtotal | **Hourly** |
| `GET /dashboard/ar/customers` | AR exposure per customer | **Hourly** |
| `GET /dashboard/ar/overdue-invoices` | Overdue invoice list (sorted by days overdue) | **Hourly** |
| `GET /dashboard/inventory/summary` | Total stock value, SKU counts, negative stock flags | **Hourly** |
| `GET /dashboard/inventory/categories` | Stock value by category | **Hourly** |
| `GET /dashboard/inventory/top-holdings` | Highest-value SKUs in stock | **Hourly** |
| `GET /dashboard/inventory/negative-stock` | SKUs with negative qty + likely cause | **Hourly** |
| `GET /dashboard/purchases/summary` | Period spend, vendor count, overdue PO count | Daily |
| `GET /dashboard/purchases/vendors` | Top vendors by spend | Daily |
| `GET /dashboard/purchases/overdue-pos` | Overdue PO list | **Hourly** |
| `GET /dashboard/production/summary` | FG produced, reject rate, WIP count | **Hourly** |
| `GET /dashboard/production/process-status` | WIP / Pending / Planned / Completed breakdown | **Hourly** |
| `GET /dashboard/orders/summary` | Open OC count + value, dispatched % | **Hourly** |
| `GET /dashboard/orders/overdue` | Overdue order confirmations | **Hourly** |
| `GET /dashboard/sync/health` | Freshness of all pipelines | Always live |

### 6.2 AI tool endpoint (Phase 2 prep, built in Week 4)

```
POST /ai/query
Body: {
  "report_id": 29,          ← must be in WHITELIST (11 IDs only)
  "filters": { ... },       ← passed through to /generate_report
  "aggregate": true         ← always true; raw rows never returned
}
```

**Whitelist:** `[29, 102, 2, 77, 3, 34, 8, 9, 86, 25, 5]`. Any other `report_id` returns 403. No CREATE endpoints are ever callable. This sandbox ensures the AI cannot write to TranzAct.

---

## 7. Anti-Context-Rot Design (Phase 2 Guarantee)

Context rot happens when a language model receives more data than it can reason over — thousands of raw invoice rows, full inventory tables, unstructured CSVs. It produces hallucination or omission. Here is how we prevent it architecturally:

### 7.1 Pre-aggregation layer (queries.py)

Every function in `schema/queries.py` returns a typed dict, never raw rows. The contract:

```python
def get_ar_summary(conn) -> dict:
    """
    Returns:
      total_outstanding: float
      overdue_count: int
      overdue_value: float
      aging_buckets: list[{bucket, count, value}]   # max 4 buckets
      top_exposures: list[{customer, outstanding, oldest_days}]  # max 10
      last_synced_at: str  (ISO 8601)
    """
```

The AI never sees `SELECT * FROM tz_ar_aging`. It calls `get_ar_summary()` and gets a ~15-key dict. This is the **pre-aggregation rule**: the function does the heavy lifting; the model does the reasoning.

### 7.2 Top-N caps

Every query function caps list results:

| Data type | Max rows returned to AI |
|---|---|
| Customer lists | 15 |
| SKU lists | 20 |
| Invoice/PO detail lists | 25 |
| Vendor lists | 10 |
| Production process lists | 30 |

These caps are defined as constants in `schema/queries.py` and are the **only** place they live.

### 7.3 Semantic table naming

Every table name mirrors its source report ID: `tz_sales_invoices` (report 29), `tz_ar_aging` (report 102). The AI system prompt can reference tables by name and the mapping is always unambiguous.

### 7.4 Source citations

Every AI response must include a `citations` field:

```json
{
  "answer": "...",
  "citations": [
    { "table": "tz_ar_aging", "report_id": 102, "fetched_at": "2026-05-21T06:00Z" },
    { "table": "tz_sales_invoices", "report_id": 29, "fetched_at": "2026-05-21T03:00Z" }
  ]
}
```

The AI cannot produce an answer without knowing which tables it read from. This makes every claim auditable.

### 7.5 Schema stability

The schema is locked at end of Week 1. After that, changes require both builders to agree in a 30-minute meeting. No silent migrations. The schema is the contract between Layer B (pipelines) and Layer C (queries + AI). Stable schema = the AI's mental model of the data never breaks.

---

## 8. The 17 Dashboard Panels

### Strategic panels (daily cache, 12 total)

| # | Panel | Key metric | Source table |
|---|---|---|---|
| S1 | Revenue KPIs | ₹ period total, run-rate vs target | tz_sales_invoices |
| S2 | Monthly revenue trend | Bar chart, 6 months | tz_sales_invoices |
| S3 | Customer concentration | Top 5 / Others doughnut | tz_sales_invoices |
| S4 | Top 10 customers by revenue | Horizontal bar | tz_sales_invoices |
| S5 | Top 10 SKUs by revenue | Horizontal bar | tz_sales_invoices |
| S6 | Inventory KPIs | Total value, SKU counts, negative flags | tz_inventory_valuation |
| S7 | Inventory by category | Top 10 categories by ₹ | tz_inventory_valuation |
| S8 | Top stock holdings | Highest-value SKUs sitting idle | tz_inventory_valuation |
| S9 | Purchases summary | Period spend, vendor count | tz_purchase_invoices |
| S10 | Top 10 vendors by spend | Horizontal bar | tz_purchase_invoices |
| S11 | Production summary | FG produced, reject rate | tz_process_details |
| S12 | Order book KPIs | Open value, dispatched %, OC count | tz_sales_orders |

### Operational panels (hourly cache, 5 total — Sandeep's morning alerts)

| # | Panel | Key metric | Source table |
|---|---|---|---|
| O1 | AR aging + overdue invoices | Aging buckets + overdue list | tz_ar_aging |
| O2 | Customer AR exposure | Outstanding per customer, oldest invoice | tz_ar_aging |
| O3 | Overdue POs | POs past delivery date, ₹ at risk | tz_purchase_orders |
| O4 | WIP + production status | WIP / Pending / Planned / Completed | tz_process_details |
| O5 | Overdue order confirmations | OCs past delivery date | tz_sales_orders |

---

## 9. Build Sequence

### Week 1 — Foundation (Do not skip steps in order)

**Day 1 (CRITICAL TEST — do not proceed without completing this)**

Call `POST /generate_report` with `report.id = 29` (Sales Invoice Register) for the last 6 months. Document: response shape, record count, pagination behaviour, field names. This is the biggest unknown. If pagination is broken, all pipelines break.

**Days 2–3 (Engineering)**
1. Postgres on Railway or Supabase — run `schema/init.sql`
2. `adapters/tranzact/auth.py` — login, token cache, auto-refresh
3. `adapters/tranzact/client.py` — `fetch_report()` with backoff + pagination
4. Unit tests for auth and client against the Day 1 test responses

**Days 4–5 (Both builders)**
- Pipeline for `report.id = 29` → `tz_sales_invoices` (daily)
- Pipeline for `report.id = 102` → `tz_ar_aging` (hourly)
- Manual sync trigger — verify rows land in Postgres
- Both builders spot-check 10 records against TranzAct UI

**End of Week 1 checklist:**
- [ ] Auth module working, token refresh verified
- [ ] `tz_sales_invoices` and `tz_ar_aging` flowing into Postgres
- [ ] Backfill decision documented (full history or forward-only)
- [ ] Schema locked — committed to git, no changes without a meeting
- [ ] `tz_sync_runs` updating correctly

### Week 2 — All 10 pipelines

Run remaining 8 pipelines. Define business logic with KBrushes team:
- Product category mapping (which SKUs are Automotive / Home / Industrial / Export)
- SKU classification (Sell vs raw material)
- Stockout thresholds
- Credit period per customer tier

**End of Week 2 checklist:**
- [ ] All 10 tables populated
- [ ] 6 months backfilled (if Day 1 confirmed this is possible)
- [ ] Sync health visible in a monitoring view
- [ ] Business logic decisions documented in `schema/queries.py` comments

### Week 3 — Dashboard (17 panels)

Build all 17 panels. Non-negotiable UI rule: every panel shows a `last synced X minutes ago` timestamp. Sandeep must always know how recent his numbers are.

Week 3 ends with a mandatory demo with Sandeep. Do not proceed to Week 4 without his sign-off.

### Week 4 — AI layer + polish

- Build the 5 operational panels (hourly sync)
- Build `/ai/query` endpoint with the 11-item whitelist
- Test 20 real questions; iterate on system prompt
- Cache invalidation / "Refresh Now" button
- Every strategic panel loads under 2 seconds

---

## 10. Configuration & Credentials

**Never hardcode credentials.** All values come from environment variables.

```bash
# .env (never committed to git)
TRANZACT_EMAIL=your@email.com
TRANZACT_PASSWORD=your_password
TRANZACT_BASE_URL=https://app.tranzact.in
DATABASE_URL=postgresql://user:pass@host:5432/vinayak_brain
KBRUSHES_COMPANY_ID=your_company_id
TRANZACT_REQUESTS_PER_MINUTE=8   # stay under 10/min throttle
SYNC_STALENESS_HOURS=25
```

---

## 11. The Context-Rot Test (Phase 2 Gate)

Before the AI layer goes live, run this test:

1. Ask the AI: *"What is KBrushes' AR situation?"*
2. Inspect the context sent to the model. It must contain:
   - Fewer than 500 tokens of data
   - Named fields (not raw columns)
   - A `citations` block
3. The answer must cite specific tables and `fetched_at` timestamps
4. The answer must NOT be based on stale data (>25 hours old)

If the test fails, fix `schema/queries.py` before deploying the AI layer. The query layer is the **only** defence against context rot.

---

*BrewMyAgent · Vinayak Brain OS · KBrushes v1.0 · May 2026*
