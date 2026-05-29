"""
api/routes/dashboard.py
────────────────────────
All 17 dashboard panel endpoints + sync health.

Every endpoint returns the same JSON envelope:
    {
        "data":  { ... },          ← result of the query function
        "meta": {
            "report_id":     int,
            "last_synced_at": str | null,
            "stale":          bool
        }
    }

The data dict is what gets rendered in the dashboard panels.
The meta dict is shown to the user as the "last synced X min ago" stamp.
"""
from __future__ import annotations

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

import logging
logger = logging.getLogger(__name__)

from vinayak.config import DATABASE_URL
from vinayak.schema import queries

router = APIRouter()


def _conn():
    """Open a new psycopg2 connection. Caller is responsible for closing."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except psycopg2.OperationalError as exc:
        logger.error("DB connection failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — check DATABASE_URL (Supabase direct connection, port 5432)",
        ) from exc


def _envelope(data: dict, report_id: int) -> dict:
    """Wrap a query result in the standard API envelope."""
    return {
        "data": {k: v for k, v in data.items()
                 if k not in ("last_synced_at", "stale")},
        "meta": {
            "report_id":     report_id,
            "last_synced_at": data.get("last_synced_at"),
            "stale":          data.get("stale", False),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# STRATEGIC PANELS (daily cache)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/revenue/summary")
def revenue_summary(period_days: int = Query(default=30, ge=7, le=365)):
    """S1 — Revenue KPIs for the selected period."""
    conn = _conn()
    try:
        data = queries.get_revenue_summary(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/trend")
def revenue_trend(months: int = Query(default=6, ge=1, le=24)):
    """S2 — Monthly revenue trend (bar chart data)."""
    conn = _conn()
    try:
        data = queries.get_revenue_trend(conn, months)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/concentration")
def customer_concentration(period_days: int = Query(default=30, ge=7, le=365)):
    """S3 — Customer revenue concentration (doughnut chart)."""
    conn = _conn()
    try:
        data = queries.get_customer_concentration(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/customers")
def top_customers_revenue(period_days: int = Query(default=30, ge=7, le=365)):
    """S4 — Top customers by revenue."""
    conn = _conn()
    try:
        data = queries.get_top_customers_revenue(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/skus")
def top_skus_revenue(period_days: int = Query(default=30, ge=7, le=365)):
    """S5 — Top SKUs by revenue."""
    conn = _conn()
    try:
        data = queries.get_top_skus_revenue(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/inventory/summary")
def inventory_summary():
    """S6 — Inventory KPIs (current stock snapshot)."""
    conn = _conn()
    try:
        data = queries.get_inventory_summary(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/inventory/categories")
def inventory_by_category():
    """S7 — Stock value by product category."""
    conn = _conn()
    try:
        data = queries.get_inventory_by_category(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/inventory/top-holdings")
def top_stock_holdings():
    """S8 — Highest-value SKUs in stock."""
    conn = _conn()
    try:
        data = queries.get_top_stock_holdings(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/purchases/summary")
def purchases_summary(period_days: int = Query(default=30, ge=7, le=365)):
    """S9 — Purchase spend KPIs."""
    conn = _conn()
    try:
        data = queries.get_purchases_summary(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=77)


@router.get("/purchases/vendors")
def top_vendors_spend(period_days: int = Query(default=30, ge=7, le=365)):
    """S10 — Top vendors by purchase spend."""
    conn = _conn()
    try:
        data = queries.get_top_vendors_spend(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=77)


@router.get("/production/summary")
def production_summary(period_days: int = Query(default=30, ge=7, le=365)):
    """S11 — Production KPIs (FG output, reject rate)."""
    conn = _conn()
    try:
        data = queries.get_production_summary(conn, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=25)


@router.get("/orders/summary")
def order_book_summary():
    """S12 — Sales order book KPIs."""
    conn = _conn()
    try:
        data = queries.get_order_book_summary(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=2)


# ════════════════════════════════════════════════════════════════════════════
# OPERATIONAL PANELS (hourly cache — Sandeep's morning alerts)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/ar/aging")
def ar_aging():
    """O1 — AR aging buckets + overdue summary."""
    conn = _conn()
    try:
        data = queries.get_ar_summary(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=102)


@router.get("/ar/customers")
def ar_customer_exposure():
    """O2 — AR exposure per customer."""
    conn = _conn()
    try:
        data = queries.get_ar_customer_exposure(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=102)


@router.get("/purchases/overdue-pos")
def overdue_pos():
    """O3 — Overdue purchase orders."""
    conn = _conn()
    try:
        data = queries.get_overdue_pos(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=3)


@router.get("/production/wip")
def production_wip():
    """O4 — WIP and production status breakdown."""
    conn = _conn()
    try:
        data = queries.get_production_wip(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=25)


@router.get("/orders/overdue")
def overdue_orders():
    """O5 — Overdue order confirmations."""
    conn = _conn()
    try:
        data = queries.get_overdue_orders(conn)
    finally:
        conn.close()
    return _envelope(data, report_id=2)


# ════════════════════════════════════════════════════════════════════════════
# SYNC HEALTH (always live — reads from tz_sync_runs directly)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/sync/health")
def sync_health():
    """Freshness status for all 10 pipelines. Never cached."""
    conn = _conn()
    try:
        data = queries.get_sync_health(conn)
    finally:
        conn.close()
    return data


@router.post("/sync/trigger/{pipeline_name}")
def trigger_sync(pipeline_name: str):
    """
    Manually trigger a pipeline run (cache invalidation).
    Runs synchronously — response returns after the sync completes.
    Only available for the 5 hourly pipelines (to avoid triggering heavy daily syncs).
    """
    from datetime import date, timedelta
    from vinayak.pipelines import (
        ar_aging as ar_mod,
        sales_orders as so_mod,
        purchase_orders as po_mod,
        inventory_valuation as inv_mod,
        process_details as pd_mod,
    )

    ALLOWED = {
        "ar_aging":             (ar_mod.ARAgingPipeline,          1, 1),
        "sales_orders":         (so_mod.SalesOrdersPipeline,      7, 7),
        "purchase_orders":      (po_mod.PurchaseOrdersPipeline,   7, 7),
        "inventory_valuation":  (inv_mod.InventoryValuationPipeline, 1, 1),
        "process_details":      (pd_mod.ProcessDetailsPipeline,   7, 7),
    }

    if pipeline_name not in ALLOWED:
        raise HTTPException(
            400,
            detail=f"Manual trigger only available for: {list(ALLOWED.keys())}"
        )

    PipelineClass, from_days, to_days = ALLOWED[pipeline_name]
    today = date.today()
    from_date = today - timedelta(days=from_days)
    to_date = today

    try:
        PipelineClass().run(from_date, to_date)
    except Exception as exc:
        raise HTTPException(500, detail=f"Pipeline failed: {exc}")

    return {"status": "ok", "pipeline": pipeline_name,
            "from_date": str(from_date), "to_date": str(to_date)}
