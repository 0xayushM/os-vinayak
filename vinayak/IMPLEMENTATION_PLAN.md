# Vinayak Brain OS — Implementation Plan
## TranzAct Dashboard (Phase 1)
*BrewMyAgent · May 2026*

---

## How to Read This Document

This plan translates `ARCHITECTURE.md` into daily, file-level coding tasks. Each task has:
- **Exact file(s)** to create or edit
- **Acceptance criteria** — the specific thing that must be true before you move on
- **Dependencies** — what must be done first

The four phases map to the four weeks in the architecture. Do not skip phases or reorder tasks within a phase. The critical path is:

```
Day 1 API test → auth.py → client.py → first 2 pipelines → schema lock
→ remaining 8 pipelines → 17 dashboard panels → AI layer
```

---

## Pre-work: Repository Setup (Do this before Day 1)

### P1 — Create folder structure

```
vinayak/
├── adapters/tranzact/
├── pipelines/
├── schema/
├── api/routes/
└── dashboard/
```

Run:
```bash
mkdir -p vinayak/{adapters/tranzact,pipelines,schema,api/routes,dashboard}
touch vinayak/adapters/tranzact/__init__.py
touch vinayak/pipelines/__init__.py
touch vinayak/api/__init__.py
touch vinayak/api/routes/__init__.py
```

### P2 — Create `requirements.txt`

```
httpx==0.27.*
fastapi==0.111.*
uvicorn[standard]==0.30.*
apscheduler==3.10.*
asyncpg==0.29.*
pydantic==2.*
python-jose[cryptography]==3.3.*
python-dotenv==1.0.*
anthropic==0.28.*     # Phase 2 only — include now so the install is done
```

### P3 — Create `.env.example` (commit this; never commit `.env`)

```bash
TRANZACT_EMAIL=your@email.com
TRANZACT_PASSWORD=your_password
TRANZACT_BASE_URL=https://app.tranzact.in
DATABASE_URL=postgresql://user:pass@host:5432/vinayak_brain
DEFAULT_COMPANY_ID=your_company_id
TRANZACT_REQUESTS_PER_MINUTE=8
SYNC_STALENESS_HOURS=25
```

### P4 — Create `vinayak/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

TRANZACT_EMAIL = os.environ["TRANZACT_EMAIL"]
TRANZACT_PASSWORD = os.environ["TRANZACT_PASSWORD"]
TRANZACT_BASE_URL = os.environ.get("TRANZACT_BASE_URL", "https://app.tranzact.in")
DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_COMPANY_ID = os.environ["DEFAULT_COMPANY_ID"]
REQUESTS_PER_MINUTE = int(os.environ.get("TRANZACT_REQUESTS_PER_MINUTE", "8"))
SYNC_STALENESS_HOURS = int(os.environ.get("SYNC_STALENESS_HOURS", "25"))
```

**✅ Acceptance:** `python -c "import vinayak.config"` runs without error (with a valid `.env`).

---

## Phase 1 — Foundation (Week 1, Days 1–5)

### Day 1 — CRITICAL: API Handshake Test

**This is a gate. Nothing else starts until this succeeds.**

Write a one-off test script (not production code) at `vinayak/scripts/test_api.py`:

```python
"""
Run once: python -m vinayak.scripts.test_api
Purpose: Prove the TranzAct API returns what we expect for report 29.
"""
import httpx, json

BASE = "https://app.tranzact.in"
EMAIL = "your@email.com"
PASSWORD = "your_password"

# Step 1: Login
r = httpx.post(f"{BASE}/main/login/password-login/",
               json={"email": EMAIL, "password": PASSWORD})
r.raise_for_status()
tokens = r.json()["data"]
access_token = tokens["access_token"]
refresh_token = tokens["refresh_token"]
print("✅ Login OK")
print(f"   access_token (first 40 chars): {access_token[:40]}...")

# Step 2: Pull page 1 of report 29 (Sales Invoice Register)
r = httpx.post(
    f"{BASE}/generate_report",
    headers={"Authorization": f"Bearer {access_token}"},
    json={
        "report": {"id": "29"},
        "pagination": {"page": 1, "per_page": 50},
        "filters": {"date_range": "last_6_months"}   # adjust to actual filter key
    }
)
r.raise_for_status()
data = r.json()
print(f"✅ Report 29 page 1 OK — {len(data.get('data', []))} rows")
print("   Keys on first row:", list(data["data"][0].keys()) if data.get("data") else "NO ROWS")
print("   Pagination info:", {k: data[k] for k in data if k != "data"})

# Save raw response for reference
with open("report_29_sample.json", "w") as f:
    json.dump(data, f, indent=2)
print("   Saved to report_29_sample.json")
```

**Document before Day 2:**
- Exact filter key for date range (is it `date_range`? `from_date`/`to_date`?)
- Pagination keys: what tells you there's a next page? (`total_pages`? `has_next`?)
- Column names on a sales invoice row (you'll use these to build Pydantic schemas)
- Any 401 / 403 / 400 errors and what they mean

**✅ Acceptance:** Script runs, returns >0 rows, `report_29_sample.json` saved.

---

### Day 2 — `adapters/tranzact/auth.py`

**File:** `vinayak/adapters/tranzact/auth.py`

Implement the `_TokenCache` singleton and three public functions:

```python
"""
auth.py — Bearer token lifecycle management.

Public API:
  await get_access_token(force_refresh=False) -> str
  await logout() -> None   (testing helper only)

Token state machine:
  cached + >2min remaining  →  return cached (0 network calls)
  cached + <2min remaining  →  POST /token/refresh/ (1 call)
  no token or both expired  →  POST /main/login/password-login/ (1 call)
  force_refresh=True        →  bypass cache, re-login immediately
"""
import asyncio, time
from dataclasses import dataclass, field
from typing import Optional
import httpx
from jose import jwt as jose_jwt
from vinayak.config import TRANZACT_EMAIL, TRANZACT_PASSWORD, TRANZACT_BASE_URL

TOKEN_EXPIRY_BUFFER_SECONDS = 120  # treat tokens as expired 2 min early

@dataclass
class _TokenCache:
    access_token: Optional[str] = None
    access_exp: float = 0.0
    refresh_token: Optional[str] = None
    refresh_exp: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

_cache = _TokenCache()

def _decode_exp(token: str) -> float:
    """Extract exp claim from JWT without verifying signature."""
    claims = jose_jwt.get_unverified_claims(token)
    return float(claims["exp"])

async def _do_login(client: httpx.AsyncClient) -> None:
    r = await client.post(
        f"{TRANZACT_BASE_URL}/main/login/password-login/",
        json={"email": TRANZACT_EMAIL, "password": TRANZACT_PASSWORD}
    )
    r.raise_for_status()
    data = r.json()["data"]
    _cache.access_token = data["access_token"]
    _cache.access_exp = _decode_exp(_cache.access_token)
    _cache.refresh_token = data["refresh_token"]
    _cache.refresh_exp = _decode_exp(_cache.refresh_token)

async def _do_refresh(client: httpx.AsyncClient) -> None:
    r = await client.post(
        f"{TRANZACT_BASE_URL}/token/refresh/",    # confirm exact path on Day 1
        json={"refresh": _cache.refresh_token}
    )
    if r.status_code == 401:
        await _do_login(client)
        return
    r.raise_for_status()
    data = r.json()
    _cache.access_token = data["access_token"]
    _cache.access_exp = _decode_exp(_cache.access_token)

async def get_access_token(force_refresh: bool = False) -> str:
    async with _cache._lock:
        now = time.time()
        if (not force_refresh
                and _cache.access_token
                and _cache.access_exp - now > TOKEN_EXPIRY_BUFFER_SECONDS):
            return _cache.access_token  # fast path — 0 network calls
        async with httpx.AsyncClient() as client:
            if (_cache.refresh_token
                    and _cache.refresh_exp - now > TOKEN_EXPIRY_BUFFER_SECONDS
                    and not force_refresh):
                await _do_refresh(client)
            else:
                await _do_login(client)
        return _cache.access_token

async def logout() -> None:
    """For tests only — wipes the in-memory cache."""
    async with _cache._lock:
        _cache.access_token = None
        _cache.refresh_token = None
        _cache.access_exp = 0.0
        _cache.refresh_exp = 0.0
```

**✅ Acceptance:**
- `asyncio.run(get_access_token())` returns a non-empty string
- Call it twice in 5 seconds → only 1 network request made (cache hit on second call)
- `asyncio.run(get_access_token(force_refresh=True))` forces a fresh login

---

### Day 2 — `adapters/tranzact/client.py`

**File:** `vinayak/adapters/tranzact/client.py`

```python
"""
client.py — Single function: fetch_report()

Handles:
  • Attaches Bearer token (via auth.get_access_token)
  • Pagination loop until all pages fetched
  • Exponential backoff on 429 / 5xx
  • 401 → force token refresh → one retry
  • Rate limiting: stays under REQUESTS_PER_MINUTE
"""
import asyncio, time
from typing import Any, Optional
import httpx
from vinayak.config import TRANZACT_BASE_URL, REQUESTS_PER_MINUTE
from vinayak.adapters.tranzact.auth import get_access_token

_MIN_INTERVAL = 60.0 / REQUESTS_PER_MINUTE  # seconds between requests
_last_request_at: float = 0.0

async def _throttle():
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = _MIN_INTERVAL - elapsed
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request_at = time.monotonic()

async def _post_with_retry(client: httpx.AsyncClient,
                           payload: dict,
                           retries: int = 3) -> dict:
    for attempt in range(retries):
        await _throttle()
        token = await get_access_token()
        r = await client.post(
            f"{TRANZACT_BASE_URL}/generate_report",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=30.0
        )
        if r.status_code == 401:
            token = await get_access_token(force_refresh=True)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            await asyncio.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"fetch_report failed after {retries} retries")

async def fetch_report(
    report_id: str,
    filters: Optional[dict] = None,
    per_page: int = 50,
) -> list[dict]:
    """
    Fetch ALL rows of a report across all pages.
    Returns a flat list of row dicts.
    """
    payload_base = {
        "report": {"id": report_id},
        "pagination": {"page": 1, "per_page": per_page},
        **(filters or {}),
    }
    all_rows: list[dict] = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            payload = {**payload_base, "pagination": {"page": page, "per_page": per_page}}
            data = await _post_with_retry(client, payload)
            rows = data.get("data", [])
            all_rows.extend(rows)

            # IMPORTANT: Update this after Day 1 to match actual pagination keys
            total_pages = data.get("total_pages") or data.get("meta", {}).get("total_pages", 1)
            if page >= total_pages or not rows:
                break
            page += 1

    return all_rows
```

**✅ Acceptance:** `asyncio.run(fetch_report("29", {"filters": {"date_range": "last_30_days"}}))` returns a non-empty list of dicts.

---

### Day 2 — `adapters/tranzact/reports.py`

**File:** `vinayak/adapters/tranzact/reports.py`

```python
"""
Canonical map of report IDs to human names.
Used by pipelines, sync logging, and the AI whitelist.
"""

REPORT_IDS = {
    "sales_invoices":       "29",
    "ar_aging":             "102",
    "sales_orders":         "2",
    "purchase_invoices":    "77",
    "purchase_orders":      "3",
    "grn_qir":              "34",
    "sales_quotations":     "8",
    "inventory_valuation":  "9",
    "process_routing":      "86",
    "process_details":      "25",
}

# Whitelisted for AI tool endpoint (Phase 2)
AI_WHITELIST = set(REPORT_IDS.values()) | {"5"}

# Filter configs per pipeline (update field names after Day 1 test)
PIPELINE_FILTERS = {
    "sales_invoices":       lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "ar_aging":             lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "sales_orders":         lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "purchase_invoices":    lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "purchase_orders":      lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "grn_qir":              lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "sales_quotations":     lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "inventory_valuation":  lambda from_date, to_date: {},  # usually no date filter
    "process_routing":      lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
    "process_details":      lambda from_date, to_date: {"filters": {"from_date": from_date, "to_date": to_date}},
}
```

---

### Days 3–4 — Database Schema (`schema/init.sql`)

**File:** `vinayak/schema/init.sql`

Run this on your Supabase Postgres instance. This is the **schema lock** — finalize it at end of Day 5 and treat it as immutable.

```sql
-- ============================================================
-- Vinayak Brain OS — TranzAct Cache Schema
-- Lock date: [fill in end of Week 1]
-- ============================================================

-- Sync audit log (every pipeline run recorded here)
CREATE TABLE tz_sync_runs (
    id              SERIAL PRIMARY KEY,
    pipeline_name   TEXT NOT NULL,
    report_id       INTEGER NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running','success','failed')),
    rows_fetched    INTEGER,
    rows_upserted   INTEGER,
    error_message   TEXT,
    is_backfill     BOOLEAN DEFAULT FALSE
);
CREATE INDEX ON tz_sync_runs (pipeline_name, completed_at DESC);

-- ── Cached tables ────────────────────────────────────────────

CREATE TABLE tz_sales_invoices (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 29,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invoice_date        DATE,
    invoice_number      TEXT,
    customer_name       TEXT,
    customer_code       TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    quantity            NUMERIC,
    unit_price          NUMERIC,
    line_total          NUMERIC,
    tax_amount          NUMERIC,
    invoice_total       NUMERIC,
    payment_status      TEXT,
    due_date            DATE
    -- Add columns discovered on Day 1 here before locking
);

CREATE TABLE tz_ar_aging (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 102,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    customer_name       TEXT,
    customer_code       TEXT,
    invoice_number      TEXT,
    invoice_date        DATE,
    due_date            DATE,
    invoice_amount      NUMERIC,
    outstanding_amount  NUMERIC,
    days_overdue        INTEGER,
    aging_bucket        TEXT   -- '0-30', '31-60', '61-90', '90+'
);

CREATE TABLE tz_sales_orders (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 2,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_date          DATE,
    order_number        TEXT,
    customer_name       TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    ordered_qty         NUMERIC,
    dispatched_qty      NUMERIC,
    pending_qty         NUMERIC,
    order_value         NUMERIC,
    delivery_date       DATE,
    status              TEXT
);

CREATE TABLE tz_purchase_invoices (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 77,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invoice_date        DATE,
    invoice_number      TEXT,
    vendor_name         TEXT,
    vendor_code         TEXT,
    item_code           TEXT,
    item_name           TEXT,
    quantity            NUMERIC,
    unit_price          NUMERIC,
    line_total          NUMERIC,
    invoice_total       NUMERIC
);

CREATE TABLE tz_purchase_orders (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 3,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    po_date             DATE,
    po_number           TEXT,
    vendor_name         TEXT,
    item_code           TEXT,
    item_name           TEXT,
    ordered_qty         NUMERIC,
    received_qty        NUMERIC,
    pending_qty         NUMERIC,
    po_value            NUMERIC,
    expected_date       DATE,
    status              TEXT
);

CREATE TABLE tz_grn_qir (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 34,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    grn_date            DATE,
    grn_number          TEXT,
    vendor_name         TEXT,
    po_number           TEXT,
    item_code           TEXT,
    item_name           TEXT,
    ordered_qty         NUMERIC,
    received_qty        NUMERIC,
    rejected_qty        NUMERIC
);

CREATE TABLE tz_sales_quotations (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 8,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quote_date          DATE,
    quote_number        TEXT,
    customer_name       TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    quoted_qty          NUMERIC,
    quoted_value        NUMERIC,
    status              TEXT,  -- 'won', 'lost', 'pending'
    valid_until         DATE
);

CREATE TABLE tz_inventory_valuation (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 9,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sku_code            TEXT,
    sku_name            TEXT,
    category            TEXT,
    warehouse           TEXT,
    quantity            NUMERIC,
    unit_cost           NUMERIC,
    total_value         NUMERIC
);

CREATE TABLE tz_process_routing (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 86,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sku_code            TEXT,
    sku_name            TEXT,
    process_name        TEXT,
    sequence_number     INTEGER,
    standard_hours      NUMERIC,
    machine_centre      TEXT
);

CREATE TABLE tz_process_details (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 25,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    production_date     DATE,
    work_order_number   TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    process_name        TEXT,
    planned_qty         NUMERIC,
    produced_qty        NUMERIC,
    rejected_qty        NUMERIC,
    status              TEXT  -- 'planned', 'wip', 'completed', 'pending'
);
```

**✅ Acceptance:** `\dt tz_*` in psql shows all 11 tables (10 cached + tz_sync_runs).

---

### Days 4–5 — `pipelines/base.py`

**File:** `vinayak/pipelines/base.py`

```python
"""
BasePipeline — all 10 pipelines inherit from this.

Subclasses must implement:
  - PIPELINE_NAME: str
  - REPORT_ID: str
  - TABLE_NAME: str
  - RowSchema: pydantic.BaseModel
  - _get_filters(from_date, to_date) -> dict
  - _upsert(conn, rows) -> int  (returns rows_upserted)
"""
import asyncio, logging
from abc import ABC, abstractmethod
from datetime import date, timedelta
import asyncpg
from vinayak.adapters.tranzact.client import fetch_report
from vinayak.config import DATABASE_URL

log = logging.getLogger(__name__)

class BasePipeline(ABC):
    PIPELINE_NAME: str
    REPORT_ID: str
    TABLE_NAME: str

    async def run(self, from_date: date, to_date: date) -> None:
        """Full pipeline: fetch → validate → upsert → log."""
        conn = await asyncpg.connect(DATABASE_URL)
        run_id = await conn.fetchval(
            """INSERT INTO tz_sync_runs (pipeline_name, report_id, status)
               VALUES ($1, $2, 'running') RETURNING id""",
            self.PIPELINE_NAME, int(self.REPORT_ID)
        )
        try:
            filters = self._get_filters(str(from_date), str(to_date))
            raw_rows = await fetch_report(self.REPORT_ID, filters)
            validated = self._validate(raw_rows)
            upserted = await self._upsert(conn, validated)
            await conn.execute(
                """UPDATE tz_sync_runs
                   SET status='success', rows_fetched=$1,
                       rows_upserted=$2, completed_at=NOW()
                   WHERE id=$3""",
                len(raw_rows), upserted, run_id
            )
            log.info(f"{self.PIPELINE_NAME}: {len(raw_rows)} fetched, {upserted} upserted")
        except Exception as exc:
            await conn.execute(
                """UPDATE tz_sync_runs
                   SET status='failed', error_message=$1, completed_at=NOW()
                   WHERE id=$2""",
                str(exc), run_id
            )
            log.error(f"{self.PIPELINE_NAME} FAILED: {exc}")
            raise
        finally:
            await conn.close()

    async def backfill(self, from_date: date, window_days: int = 30) -> None:
        """Split from_date → today into 30-day windows and run each."""
        today = date.today()
        cursor = from_date
        while cursor < today:
            end = min(cursor + timedelta(days=window_days - 1), today)
            log.info(f"Backfilling {self.PIPELINE_NAME}: {cursor} → {end}")
            await self.run(cursor, end)
            cursor = end + timedelta(days=1)
            await asyncio.sleep(1)  # gentle rate limit between windows

    def _validate(self, rows: list[dict]) -> list:
        """Validate rows with Pydantic. Bad rows are logged and skipped."""
        valid, skipped = [], 0
        for r in rows:
            try:
                valid.append(self.RowSchema(**r))
            except Exception as e:
                skipped += 1
                log.warning(f"Skipped invalid row: {e} | row={r}")
        if skipped:
            log.warning(f"{self.PIPELINE_NAME}: {skipped}/{len(rows)} rows skipped")
        return valid

    @abstractmethod
    def _get_filters(self, from_date: str, to_date: str) -> dict: ...

    @abstractmethod
    async def _upsert(self, conn: asyncpg.Connection, rows: list) -> int: ...
```

---

### Day 5 — First Two Pipelines (gates for schema lock)

#### `pipelines/sales_invoices.py`

```python
from datetime import date
from pydantic import BaseModel, field_validator
from typing import Optional
import asyncpg
from vinayak.pipelines.base import BasePipeline

class SalesInvoiceRow(BaseModel):
    raw_id: str
    invoice_date: Optional[date] = None
    invoice_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    tax_amount: Optional[float] = None
    invoice_total: Optional[float] = None
    payment_status: Optional[str] = None
    due_date: Optional[date] = None

    # Map TranzAct field names → our field names here as needed:
    # @field_validator("raw_id", mode="before")
    # def parse_raw_id(cls, v): return str(v)

class SalesInvoicesPipeline(BasePipeline):
    PIPELINE_NAME = "sales_invoices"
    REPORT_ID = "29"
    TABLE_NAME = "tz_sales_invoices"
    RowSchema = SalesInvoiceRow

    def _get_filters(self, from_date, to_date):
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    async def _upsert(self, conn: asyncpg.Connection, rows: list) -> int:
        count = 0
        for row in rows:
            await conn.execute("""
                INSERT INTO tz_sales_invoices
                    (raw_id, invoice_date, invoice_number, customer_name,
                     customer_code, sku_code, sku_name, quantity, unit_price,
                     line_total, tax_amount, invoice_total, payment_status,
                     due_date, fetched_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14, NOW())
                ON CONFLICT (raw_id) DO UPDATE SET
                    invoice_date=EXCLUDED.invoice_date,
                    invoice_total=EXCLUDED.invoice_total,
                    payment_status=EXCLUDED.payment_status,
                    fetched_at=NOW()
            """, row.raw_id, row.invoice_date, row.invoice_number,
                row.customer_name, row.customer_code, row.sku_code,
                row.sku_name, row.quantity, row.unit_price, row.line_total,
                row.tax_amount, row.invoice_total, row.payment_status,
                row.due_date)
            count += 1
        return count
```

Repeat the same pattern for `pipelines/ar_aging.py` (report 102).

**✅ End of Week 1 Gate — ALL of these must be true:**
- [ ] `auth.py` login + refresh verified
- [ ] `client.py` pagination confirmed against actual API response
- [ ] `tz_sales_invoices` and `tz_ar_aging` have real data in Postgres
- [ ] `tz_sync_runs` shows `status='success'` for both pipelines
- [ ] Schema columns match actual TranzAct field names (verified by spot-checking 10 rows)
- [ ] `schema/init.sql` committed to git — **schema is now locked**

---

## Phase 2 — All 10 Pipelines (Week 2)

### Task order for Week 2

Build the remaining 8 pipelines using the same pattern as `sales_invoices.py`. Prioritise operational (hourly) pipelines first since they block the most dashboard panels.

| Priority | File | Report | Table | Cadence |
|---|---|---|---|---|
| 1 | `pipelines/purchase_orders.py` | 3 | tz_purchase_orders | Hourly |
| 2 | `pipelines/sales_orders.py` | 2 | tz_sales_orders | Hourly |
| 3 | `pipelines/inventory_valuation.py` | 9 | tz_inventory_valuation | Hourly |
| 4 | `pipelines/process_details.py` | 25 | tz_process_details | Hourly |
| 5 | `pipelines/purchase_invoices.py` | 77 | tz_purchase_invoices | Daily |
| 6 | `pipelines/grn_qir.py` | 34 | tz_grn_qir | Daily |
| 7 | `pipelines/sales_quotations.py` | 8 | tz_sales_quotations | Daily |
| 8 | `pipelines/process_routing.py` | 86 | tz_process_routing | Daily |

### `pipelines/scheduler.py`

```python
"""
APScheduler — runs inside the FastAPI process.
Start with: included in api/main.py startup event.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import date, timedelta
from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
from vinayak.pipelines.ar_aging import ArAgingPipeline
# ... import all 10 pipelines

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

def _today_window():
    return date.today() - timedelta(days=1), date.today()

def _week_window():
    return date.today() - timedelta(days=7), date.today()

def _month_window():
    return date.today() - timedelta(days=30), date.today()

# ── Hourly pipelines (staggered to avoid bursting) ───────────
scheduler.add_job(lambda: ArAgingPipeline().run(*_today_window()),
                  "cron", minute=0)          # :00
scheduler.add_job(lambda: SalesOrdersPipeline().run(*_week_window()),
                  "cron", minute=8)          # :08
scheduler.add_job(lambda: PurchaseOrdersPipeline().run(*_week_window()),
                  "cron", minute=16)         # :16
scheduler.add_job(lambda: InventoryValuationPipeline().run(*_today_window()),
                  "cron", minute=24)         # :24
scheduler.add_job(lambda: ProcessDetailsPipeline().run(*_week_window()),
                  "cron", minute=32)         # :32

# ── Daily pipelines (3 AM IST, staggered by 5 min each) ──────
scheduler.add_job(lambda: SalesInvoicesPipeline().run(*_month_window()),
                  "cron", hour=3, minute=0)
scheduler.add_job(lambda: PurchaseInvoicesPipeline().run(*_month_window()),
                  "cron", hour=3, minute=5)
scheduler.add_job(lambda: GrnQirPipeline().run(*_month_window()),
                  "cron", hour=3, minute=10)
scheduler.add_job(lambda: SalesQuotationsPipeline().run(*_month_window()),
                  "cron", hour=3, minute=15)
scheduler.add_job(lambda: ProcessRoutingPipeline().run(*_month_window()),
                  "cron", hour=3, minute=20)
```

### Business logic decisions (get answers from Sandeep in Week 2)

Before writing `schema/queries.py`, you need these KBrushes-specific rules:

| Question | Why it matters |
|---|---|
| What SKU codes are Automotive / Home / Industrial / Export? | Category grouping in all inventory and revenue panels |
| What SKU codes are raw materials vs finished goods? | Filters production vs purchase analysis |
| What is the credit period per customer tier (30/45/60 days)? | AR overdue calculation |
| What is the "negative stock alert" threshold? | Inventory panel O flag |
| What does "dispatched %" mean for orders — partial ok or full only? | S12 / O5 panels |

Document answers in comments inside `schema/queries.py`.

**✅ End of Week 2 Gate:**
- [ ] All 10 tables have real data
- [ ] Scheduler verified running — `tz_sync_runs` shows entries for all pipelines
- [ ] Business logic decisions documented in `schema/queries.py` comments
- [ ] 6-month backfill run (or decision made to start from go-live date)

---

## Phase 3 — Dashboard (Week 3)

### `schema/queries.py` — 17 pre-aggregated functions

Each function maps 1:1 to one dashboard panel. The function signature is the contract — the dashboard HTML calls the FastAPI endpoint, which calls the query function. The AI (Phase 2) also calls these functions, never raw SQL.

**Example function structure:**

```python
import asyncpg
from vinayak.config import DATABASE_URL

# ── AI Top-N caps (constants only here) ────────────────────
MAX_CUSTOMERS = 15
MAX_SKUS = 20
MAX_INVOICES = 25
MAX_VENDORS = 10
MAX_PROCESSES = 30

async def get_ar_summary(conn: asyncpg.Connection) -> dict:
    """
    Returns AR aging summary for the AI and dashboard.
    Never returns raw rows — always aggregated.
    """
    rows = await conn.fetch("""
        SELECT aging_bucket, COUNT(*) as count,
               SUM(outstanding_amount) as value
        FROM tz_ar_aging
        GROUP BY aging_bucket ORDER BY aging_bucket
    """)
    overdue = await conn.fetchrow("""
        SELECT COUNT(*) as count, SUM(outstanding_amount) as value
        FROM tz_ar_aging WHERE days_overdue > 0
    """)
    top = await conn.fetch(f"""
        SELECT customer_name,
               SUM(outstanding_amount) as outstanding,
               MAX(days_overdue) as oldest_days
        FROM tz_ar_aging
        GROUP BY customer_name
        ORDER BY outstanding DESC
        LIMIT {MAX_CUSTOMERS}
    """)
    last_sync = await conn.fetchval("""
        SELECT MAX(completed_at) FROM tz_sync_runs
        WHERE pipeline_name='ar_aging' AND status='success'
    """)
    return {
        "aging_buckets": [dict(r) for r in rows],
        "overdue_count": overdue["count"],
        "overdue_value": float(overdue["value"] or 0),
        "top_exposures": [dict(r) for r in top],
        "last_synced_at": last_sync.isoformat() if last_sync else None,
        "stale": (last_sync is None)
    }
```

**Build one function per panel (17 total). The full list:**

| Function | Panel | Source table(s) |
|---|---|---|
| `get_revenue_summary` | S1 — Revenue KPIs | tz_sales_invoices |
| `get_revenue_trend` | S2 — Monthly trend | tz_sales_invoices |
| `get_customer_concentration` | S3 — Concentration doughnut | tz_sales_invoices |
| `get_top_customers_revenue` | S4 — Top 10 customers | tz_sales_invoices |
| `get_top_skus_revenue` | S5 — Top 10 SKUs | tz_sales_invoices |
| `get_inventory_summary` | S6 — Inventory KPIs | tz_inventory_valuation |
| `get_inventory_by_category` | S7 — Categories | tz_inventory_valuation |
| `get_top_stock_holdings` | S8 — High-value idle stock | tz_inventory_valuation |
| `get_purchases_summary` | S9 — Purchases KPIs | tz_purchase_invoices |
| `get_top_vendors_spend` | S10 — Top 10 vendors | tz_purchase_invoices |
| `get_production_summary` | S11 — Production KPIs | tz_process_details |
| `get_order_book_summary` | S12 — Order book KPIs | tz_sales_orders |
| `get_ar_summary` | O1 — AR aging | tz_ar_aging |
| `get_ar_customer_exposure` | O2 — Customer AR exposure | tz_ar_aging |
| `get_overdue_pos` | O3 — Overdue POs | tz_purchase_orders |
| `get_production_wip` | O4 — WIP status | tz_process_details |
| `get_overdue_orders` | O5 — Overdue OCs | tz_sales_orders |

### `api/main.py`

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from vinayak.pipelines.scheduler import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Vinayak Brain OS", lifespan=lifespan)

from vinayak.api.routes import dashboard, ai_tool
app.include_router(dashboard.router, prefix="/dashboard")
app.include_router(ai_tool.router, prefix="/ai")
```

### `api/routes/dashboard.py`

Every endpoint follows the same envelope pattern:

```python
from fastapi import APIRouter
import asyncpg
from vinayak.config import DATABASE_URL
from vinayak.schema import queries

router = APIRouter()

@router.get("/ar/aging")
async def ar_aging():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        data = await queries.get_ar_summary(conn)
    finally:
        await conn.close()
    return {
        "data": data,
        "meta": {
            "last_synced_at": data.pop("last_synced_at", None),
            "report_id": 102,
            "stale": data.pop("stale", False)
        }
    }

# Repeat for all 17 endpoints
```

### `dashboard/index.html`

Single-page HTML + Vanilla JS + Chart.js. Key constraints:
- No build step, no npm
- Every panel displays `last synced X min ago`
- Panels poll their respective API endpoints on page load
- "Refresh Now" button calls `POST /dashboard/sync/trigger` → invalidates cache for that pipeline
- Mobile-first layout (Sandeep opens this on his phone in the morning)

**Panel layout (left-to-right, top-to-bottom on desktop; stacked on mobile):**

```
Row 1: [S1 Revenue KPIs]  [S12 Order Book]  [O1 AR Aging]
Row 2: [S2 Monthly Trend — full width bar chart]
Row 3: [S3 Customer Concentration doughnut]  [S4 Top Customers bar]
Row 4: [S5 Top SKUs]  [S6 Inventory KPIs]  [S7 Inventory by Category]
Row 5: [S8 Top Holdings]  [S9 Purchases]  [S10 Top Vendors]
Row 6: [S11 Production]  [O3 Overdue POs]  [O5 Overdue Orders]
Row 7: [O2 AR Exposure table]  [O4 WIP table]
```

**✅ End of Week 3 Gate (Sandeep demo required):**
- [ ] All 17 panels render with real data
- [ ] Every panel shows `last synced X min ago`
- [ ] Mobile layout confirmed on Sandeep's phone
- [ ] Sandeep signs off on metric definitions (especially AR overdue logic)
- [ ] Page load under 3 seconds on mobile data

---

## Phase 4 — AI Layer + Polish (Week 4)

### `api/routes/ai_tool.py`

```python
"""
POST /ai/query — sandboxed TranzAct query for the AI layer.
Only whitelisted report IDs. Never returns raw rows. Never calls CREATE endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from vinayak.adapters.tranzact.reports import AI_WHITELIST
from vinayak.adapters.tranzact.client import fetch_report
from vinayak import schema

router = APIRouter()

class AIQueryRequest(BaseModel):
    report_id: str
    filters: Optional[dict] = None
    aggregate: bool = True

@router.post("/query")
async def ai_query(req: AIQueryRequest):
    if req.report_id not in AI_WHITELIST:
        raise HTTPException(403, f"report_id {req.report_id} not in AI whitelist")
    if not req.aggregate:
        raise HTTPException(400, "aggregate must be true — raw rows not permitted")
    rows = await fetch_report(req.report_id, req.filters)
    # Return summarised — never raw rows
    return {"rows_returned": len(rows), "sample": rows[:3]}
```

### AI system prompt (Phase 2 — draft)

```
You are Vinayak, the business intelligence assistant for KBrushes.
You have access to pre-aggregated query functions that read from a cached
PostgreSQL database. You never call TranzAct directly.

Available functions:
- get_ar_summary() → AR aging, overdue invoices, top exposures
- get_revenue_summary(period) → revenue KPIs
- get_inventory_summary() → stock levels, negative stock flags
- get_production_summary(period) → FG output, reject rate, WIP
- get_order_book_summary() → open orders, dispatched %
- get_overdue_pos() → overdue purchase orders
- get_top_customers_revenue(n=10) → top customers by revenue

Rules:
1. Always call the function — never answer from memory.
2. Every response must include a citations block with table name and fetched_at.
3. If data is stale (>25 hours), say so before answering.
4. Never return more than MAX_CUSTOMERS=15 / MAX_SKUS=20 items in a list.
```

### Context-rot test (run before AI goes live)

Ask: *"What is KBrushes' AR situation?"*

Inspect the context sent to the model:
- [ ] Fewer than 500 tokens of data
- [ ] All fields named (not raw SQL column names)
- [ ] `citations` block present with `table` and `fetched_at`
- [ ] No stale data (fetched_at within 25 hours)

If any check fails, fix `schema/queries.py` first.

### Final polish checklist

- [ ] "Refresh Now" button on each panel (calls pipeline-specific trigger endpoint)
- [ ] Sync health panel (`GET /dashboard/sync/health`) shows all 10 pipelines + last sync time
- [ ] All strategic panels load in <2 seconds
- [ ] Staleness badge (yellow/red) when data is >6h or >25h old
- [ ] Error state on each panel (shows "last known data from X" when sync failed)
- [ ] Deploy FastAPI service — set all env vars in deployment dashboard, never in code

---

## Deployment Checklist

```
1. Create Supabase project (https://supabase.com)
2. Settings → Database → Connection string → URI → Direct (port 5432) → copy DATABASE_URL
3. Run schema: psql $DATABASE_URL -f vinayak/schema/init.sql
   (or: python -m vinayak.scripts.setup_db)
4. Deploy FastAPI service (e.g. Render, Fly.io, or any VPS)
5. Set environment variables (from .env.example) in your hosting dashboard
6. Start command: uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
7. Run backfill: python -m vinayak.pipelines.backfill_all
8. Deploy Next.js to Vercel — set FASTAPI_INTERNAL_URL + INTERNAL_API_KEY
```

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| TranzAct pagination format differs from assumed | High | Day 1 test script mandatory |
| Rate limit hit during backfill | Medium | 1-second sleep between windows; 8 req/min cap |
| Token refresh endpoint path wrong | Medium | Test on Day 2; check TranzAct API docs |
| Report 9 (inventory) has no date filter | Medium | `PIPELINE_FILTERS["inventory_valuation"]` returns `{}` — confirm on Day 1 |
| Schema lock broken by silent column rename | Low | Commit `init.sql` to git; all changes require review meeting |
| Single worker token cache leak under multi-worker deploy | Low | Document multi-worker Redis upgrade path; don't premature-optimise |

---

*Vinayak Brain OS · KBrushes · BrewMyAgent · May 2026*
*Implementation plan version 1.0 — generated from ARCHITECTURE.md*
