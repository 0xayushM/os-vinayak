-- ============================================================
-- Vinayak Brain OS — TranzAct Cache Schema
-- BrewMyAgent · May 2026
--
-- ⚠️  SCHEMA LOCK: Finalize column names at end of Week 1.
--     After lock, no changes without a joint review meeting.
--     The column names here must match actual TranzAct field names
--     discovered during the Day 1 handshake test.
--
-- Run:
--   psql $DATABASE_URL -f kbrushes/schema/init.sql
-- ============================================================

-- ── Companies (multi-tenant root) ───────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,          -- e.g. 'kbrushes'
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed KBrushes as the first tenant
INSERT INTO companies (id, name)
VALUES ('kbrushes', 'KBrushes')
ON CONFLICT (id) DO NOTHING;

-- ── Users ────────────────────────────────────────────────────
-- Phase 1: single admin user, password checked via env var.
-- Phase 2: add bcrypt_hash column + proper user table.
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    email       TEXT NOT NULL UNIQUE,
    role        TEXT NOT NULL DEFAULT 'admin',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── ERP Tool Connections ─────────────────────────────────────
-- One row per (company, tool). Credentials are AES-256 encrypted.
-- Bearer tokens are NEVER stored here — in-memory only.
CREATE TABLE IF NOT EXISTS tool_connections (
    id                      SERIAL PRIMARY KEY,
    company_id              TEXT NOT NULL REFERENCES companies(id),
    tool_name               TEXT NOT NULL,          -- 'tranzact', 'tally', 'busy'
    connection_method       TEXT NOT NULL DEFAULT 'cloud_pull',
                                                    -- 'cloud_pull' | 'local_push' | 'unknown'
    encrypted_credentials   TEXT,                   -- Fernet(JSON{email,password,...})
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    last_verified_at        TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ,
    UNIQUE (company_id, tool_name)
);

CREATE INDEX IF NOT EXISTS idx_tc_company ON tool_connections (company_id);

-- ── Sync audit log ───────────────────────────────────────────
-- Every pipeline run is recorded here for freshness tracking
-- and the /dashboard/sync/health endpoint.

CREATE TABLE IF NOT EXISTS tz_sync_runs (
    id              SERIAL PRIMARY KEY,
    company_id      TEXT NOT NULL DEFAULT 'kbrushes',
    pipeline_name   TEXT NOT NULL,
    report_id       INTEGER NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    rows_fetched    INTEGER,
    rows_upserted   INTEGER,
    error_message   TEXT,
    is_backfill     BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_pipeline_time
    ON tz_sync_runs (pipeline_name, completed_at DESC);

-- ── Sales invoices (report 29, daily) ───────────────────────
-- Source: Sales Invoice Register
-- Used for: S1 Revenue KPIs, S2 Monthly trend, S3–S5 customer/SKU panels

CREATE TABLE IF NOT EXISTS tz_sales_invoices (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 29,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Core fields (update column names after Day 1 test)
    invoice_date        DATE,
    invoice_number      TEXT,
    customer_name       TEXT,
    customer_code       TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    category            TEXT,       -- mapped from SKU code (KBrushes-specific)
    quantity            NUMERIC,
    unit_price          NUMERIC,
    line_total          NUMERIC,
    tax_amount          NUMERIC,
    invoice_total       NUMERIC,
    payment_status      TEXT,       -- 'paid', 'unpaid', 'partial'
    due_date            DATE,
    salesperson         TEXT
);

CREATE INDEX IF NOT EXISTS idx_si_invoice_date ON tz_sales_invoices (invoice_date DESC);
CREATE INDEX IF NOT EXISTS idx_si_customer ON tz_sales_invoices (customer_code);

-- ── AR aging (report 102, hourly) ────────────────────────────
-- Source: AR Aging Report
-- Used for: O1 AR aging, O2 customer exposure

CREATE TABLE IF NOT EXISTS tz_ar_aging (
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
    aging_bucket        TEXT        -- '0-30', '31-60', '61-90', '90+'
);

CREATE INDEX IF NOT EXISTS idx_ar_customer ON tz_ar_aging (customer_code);
CREATE INDEX IF NOT EXISTS idx_ar_overdue ON tz_ar_aging (days_overdue DESC);

-- ── Sales orders (report 2, hourly) ──────────────────────────
-- Source: Order Confirmation Register
-- Used for: S12 Order book KPIs, O5 Overdue order confirmations

CREATE TABLE IF NOT EXISTS tz_sales_orders (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 2,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    order_date          DATE,
    order_number        TEXT,
    customer_name       TEXT,
    customer_code       TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    ordered_qty         NUMERIC,
    dispatched_qty      NUMERIC,
    pending_qty         NUMERIC,
    order_value         NUMERIC,
    delivery_date       DATE,
    status              TEXT        -- 'open', 'partial', 'dispatched', 'cancelled'
);

CREATE INDEX IF NOT EXISTS idx_so_delivery_date ON tz_sales_orders (delivery_date);
CREATE INDEX IF NOT EXISTS idx_so_status ON tz_sales_orders (status);

-- ── Purchase invoices (report 77, daily) ─────────────────────
-- Source: Purchase Invoice Register
-- Used for: S9 Purchases KPIs, S10 Top vendors

CREATE TABLE IF NOT EXISTS tz_purchase_invoices (
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
    tax_amount          NUMERIC,
    invoice_total       NUMERIC
);

CREATE INDEX IF NOT EXISTS idx_pi_invoice_date ON tz_purchase_invoices (invoice_date DESC);
CREATE INDEX IF NOT EXISTS idx_pi_vendor ON tz_purchase_invoices (vendor_code);

-- ── Purchase orders (report 3, hourly) ───────────────────────
-- Source: Purchase Order Register
-- Used for: O3 Overdue POs

CREATE TABLE IF NOT EXISTS tz_purchase_orders (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 3,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    po_date             DATE,
    po_number           TEXT,
    vendor_name         TEXT,
    vendor_code         TEXT,
    item_code           TEXT,
    item_name           TEXT,
    ordered_qty         NUMERIC,
    received_qty        NUMERIC,
    pending_qty         NUMERIC,
    po_value            NUMERIC,
    expected_date       DATE,
    status              TEXT        -- 'open', 'partial', 'received', 'cancelled'
);

CREATE INDEX IF NOT EXISTS idx_po_expected_date ON tz_purchase_orders (expected_date);
CREATE INDEX IF NOT EXISTS idx_po_status ON tz_purchase_orders (status);

-- ── GRN / QIR (report 34, daily) ─────────────────────────────
-- Source: Goods Received Note / Quality Inspection Report
-- Used for: goods received vs ordered analysis

CREATE TABLE IF NOT EXISTS tz_grn_qir (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 34,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    grn_date            DATE,
    grn_number          TEXT,
    vendor_name         TEXT,
    vendor_code         TEXT,
    po_number           TEXT,
    item_code           TEXT,
    item_name           TEXT,
    ordered_qty         NUMERIC,
    received_qty        NUMERIC,
    rejected_qty        NUMERIC,
    accepted_qty        NUMERIC
);

CREATE INDEX IF NOT EXISTS idx_grn_date ON tz_grn_qir (grn_date DESC);

-- ── Sales quotations (report 8, daily) ───────────────────────
-- Source: Quotation Register
-- Used for: quote conversion rate analysis

CREATE TABLE IF NOT EXISTS tz_sales_quotations (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 8,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    quote_date          DATE,
    quote_number        TEXT,
    customer_name       TEXT,
    customer_code       TEXT,
    sku_code            TEXT,
    sku_name            TEXT,
    quoted_qty          NUMERIC,
    quoted_value        NUMERIC,
    status              TEXT,       -- 'won', 'lost', 'pending'
    valid_until         DATE,
    converted_to_order  BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_quote_date ON tz_sales_quotations (quote_date DESC);
CREATE INDEX IF NOT EXISTS idx_quote_status ON tz_sales_quotations (status);

-- ── Inventory valuation (report 9, hourly) ───────────────────
-- Source: Inventory Valuation Report (no date range — always current stock)
-- Used for: S6–S8 Inventory panels, negative stock alerts

CREATE TABLE IF NOT EXISTS tz_inventory_valuation (
    raw_id              TEXT PRIMARY KEY,
    source_report       INTEGER NOT NULL DEFAULT 9,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    sku_code            TEXT,
    sku_name            TEXT,
    category            TEXT,       -- mapped from SKU code (KBrushes-specific)
    warehouse           TEXT,
    quantity            NUMERIC,
    unit_cost           NUMERIC,
    total_value         NUMERIC,
    is_raw_material     BOOLEAN DEFAULT FALSE,
    is_negative_stock   BOOLEAN GENERATED ALWAYS AS (quantity < 0) STORED
);

CREATE INDEX IF NOT EXISTS idx_inv_sku ON tz_inventory_valuation (sku_code);
CREATE INDEX IF NOT EXISTS idx_inv_negative ON tz_inventory_valuation (is_negative_stock);

-- ── Process routing (report 86, daily) ───────────────────────
-- Source: Process Routing (BOM + machine routing)
-- Used for: production planning context

CREATE TABLE IF NOT EXISTS tz_process_routing (
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

-- ── Process details (report 25, hourly) ──────────────────────
-- Source: Production Process Details
-- Used for: S11 Production KPIs, O4 WIP status

CREATE TABLE IF NOT EXISTS tz_process_details (
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
    status              TEXT        -- 'planned', 'wip', 'completed', 'pending'
);

CREATE INDEX IF NOT EXISTS idx_pd_date ON tz_process_details (production_date DESC);
CREATE INDEX IF NOT EXISTS idx_pd_status ON tz_process_details (status);

-- ── Verification query ───────────────────────────────────────
-- Run this after applying the schema to confirm all 11 tables exist:
--
--   SELECT table_name FROM information_schema.tables
--   WHERE table_name LIKE 'tz_%' ORDER BY table_name;
--
-- Expected output: 11 rows (10 cached tables + tz_sync_runs)
