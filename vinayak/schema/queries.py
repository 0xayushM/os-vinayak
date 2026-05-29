"""
schema/queries.py
──────────────────
Pre-aggregated business query functions — one per dashboard panel.

Rules:
  • Every function returns a typed dict, NEVER raw rows.
  • Top-N caps are defined as constants here and enforced in every query.
  • Phase 2 AI reads ONLY from these functions — never from raw SQL.
  • Adding a new function requires both builders to agree on the schema.

Anti-context-rot guarantee:
  An AI model calling get_ar_summary() receives ~15 keys, not 5,000 rows.
  The pre-aggregation happens in SQL, not in Python, keeping it fast.

Usage:
    import psycopg2
    from vinayak.schema.queries import get_ar_summary
    conn = psycopg2.connect(DATABASE_URL)
    data = get_ar_summary(conn)
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Top-N caps (AI safety — never return more than these) ────────────────────
MAX_CUSTOMERS  = 15
MAX_SKUS       = 20
MAX_INVOICES   = 25
MAX_VENDORS    = 10
MAX_PROCESSES  = 30
MAX_CATEGORIES = 15

# ── Staleness threshold ───────────────────────────────────────────────────────
STALE_HOURS = 25  # data older than this is flagged as stale


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _is_stale(last_sync: datetime | None) -> bool:
    if last_sync is None:
        return True
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)
    return (_now_utc() - last_sync).total_seconds() > STALE_HOURS * 3600


def _last_sync(conn, pipeline_name: str) -> datetime | None:
    """Return the most recent successful sync timestamp for a pipeline."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT MAX(completed_at) FROM tz_sync_runs
               WHERE pipeline_name = %s AND status = 'success'""",
            (pipeline_name,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _fmt(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


# ════════════════════════════════════════════════════════════════════════════
# STRATEGIC PANELS (daily cache)
# ════════════════════════════════════════════════════════════════════════════

def get_revenue_summary(conn, period_days: int = 30) -> dict:
    """
    S1 — Revenue KPIs.
    Returns: period_total, monthly_avg, ytd_total, invoice_count,
             customer_count, last_synced_at, stale
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE(SUM(invoice_total), 0)   AS period_total,
                COUNT(DISTINCT invoice_number)    AS invoice_count,
                COUNT(DISTINCT customer_code)     AS customer_count,
                COALESCE(SUM(invoice_total), 0) / NULLIF(%s / 30.0, 0) AS monthly_avg
            FROM tz_sales_invoices
            WHERE invoice_date >= %s
        """, (period_days, since))
        row = cur.fetchone()

        cur.execute("""
            SELECT COALESCE(SUM(invoice_total), 0)
            FROM tz_sales_invoices
            WHERE EXTRACT(YEAR FROM invoice_date) = EXTRACT(YEAR FROM CURRENT_DATE)
        """)
        ytd_row = cur.fetchone()

    ls = _last_sync(conn, "sales_invoices")
    return {
        "period_days":    period_days,
        "period_total":   float(row[0] or 0),
        "invoice_count":  int(row[1] or 0),
        "customer_count": int(row[2] or 0),
        "monthly_avg":    float(row[3] or 0),
        "ytd_total":      float(ytd_row[0] or 0),
        "last_synced_at": _fmt(ls),
        "stale":          _is_stale(ls),
    }


def get_revenue_trend(conn, months: int = 6) -> dict:
    """
    S2 — Monthly revenue trend (bar chart data).
    Returns: months list [{month, revenue, invoice_count}]
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                TO_CHAR(invoice_date, 'YYYY-MM') AS month,
                COALESCE(SUM(invoice_total), 0)  AS revenue,
                COUNT(DISTINCT invoice_number)   AS invoice_count
            FROM tz_sales_invoices
            WHERE invoice_date >= (CURRENT_DATE - INTERVAL '%s months')
            GROUP BY 1 ORDER BY 1
        """, (months,))
        rows = cur.fetchall()

    ls = _last_sync(conn, "sales_invoices")
    return {
        "months": [
            {"month": r[0], "revenue": float(r[1]), "invoice_count": int(r[2])}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_customer_concentration(conn, period_days: int = 30) -> dict:
    """
    S3 — Customer revenue concentration (doughnut chart).
    Returns top 5 customers + 'Others' slice.
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_name, COALESCE(SUM(invoice_total), 0) AS revenue
            FROM tz_sales_invoices
            WHERE invoice_date >= %s
            GROUP BY customer_name
            ORDER BY revenue DESC
            LIMIT 5
        """, (since,))
        top5 = cur.fetchall()

        cur.execute("""
            SELECT COALESCE(SUM(invoice_total), 0)
            FROM tz_sales_invoices WHERE invoice_date >= %s
        """, (since,))
        total = float(cur.fetchone()[0] or 0)

    top5_total = sum(float(r[1]) for r in top5)
    others = max(0.0, total - top5_total)
    slices = [{"name": r[0], "value": float(r[1])} for r in top5]
    if others > 0:
        slices.append({"name": "Others", "value": others})

    ls = _last_sync(conn, "sales_invoices")
    return {
        "total": total,
        "slices": slices,
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_top_customers_revenue(conn, period_days: int = 30) -> dict:
    """
    S4 — Top N customers by revenue.
    Returns: customers list [{customer_name, revenue, invoice_count, pct_of_total}]
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute(f"""
            WITH totals AS (
                SELECT SUM(invoice_total) AS grand_total
                FROM tz_sales_invoices WHERE invoice_date >= %s
            )
            SELECT
                customer_name,
                COALESCE(SUM(invoice_total), 0) AS revenue,
                COUNT(DISTINCT invoice_number)  AS invoice_count,
                ROUND(
                    100.0 * SUM(invoice_total) / NULLIF((SELECT grand_total FROM totals), 0),
                    1
                ) AS pct
            FROM tz_sales_invoices
            WHERE invoice_date >= %s
            GROUP BY customer_name
            ORDER BY revenue DESC
            LIMIT {MAX_CUSTOMERS}
        """, (since, since))
        rows = cur.fetchall()

    ls = _last_sync(conn, "sales_invoices")
    return {
        "period_days": period_days,
        "customers": [
            {"customer_name": r[0], "revenue": float(r[1]),
             "invoice_count": int(r[2]), "pct_of_total": float(r[3] or 0)}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_top_skus_revenue(conn, period_days: int = 30) -> dict:
    """
    S5 — Top N SKUs by revenue.
    Returns: skus list [{sku_code, sku_name, revenue, quantity, invoice_count}]
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                sku_code,
                MAX(sku_name) AS sku_name,
                COALESCE(SUM(line_total), 0) AS revenue,
                COALESCE(SUM(quantity), 0)   AS quantity,
                COUNT(DISTINCT invoice_number) AS invoice_count
            FROM tz_sales_invoices
            WHERE invoice_date >= %s
            GROUP BY sku_code
            ORDER BY revenue DESC
            LIMIT {MAX_SKUS}
        """, (since,))
        rows = cur.fetchall()

    ls = _last_sync(conn, "sales_invoices")
    return {
        "period_days": period_days,
        "skus": [
            {"sku_code": r[0], "sku_name": r[1], "revenue": float(r[2]),
             "quantity": float(r[3]), "invoice_count": int(r[4])}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_inventory_summary(conn) -> dict:
    """
    S6 — Inventory KPIs.
    Returns: total_value, total_skus, negative_stock_count, warehouse_count
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE(SUM(total_value), 0) AS total_value,
                COUNT(DISTINCT sku_code)      AS total_skus,
                COUNT(*) FILTER (WHERE quantity < 0) AS negative_stock_count,
                COUNT(DISTINCT warehouse)     AS warehouse_count
            FROM tz_inventory_valuation
        """)
        row = cur.fetchone()

    ls = _last_sync(conn, "inventory_valuation")
    return {
        "total_value":          float(row[0] or 0),
        "total_skus":           int(row[1] or 0),
        "negative_stock_count": int(row[2] or 0),
        "warehouse_count":      int(row[3] or 0),
        "last_synced_at":       _fmt(ls),
        "stale":                _is_stale(ls),
    }


def get_inventory_by_category(conn) -> dict:
    """
    S7 — Stock value by product category.
    Returns: categories list [{category, total_value, sku_count}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                COALESCE(category, 'Uncategorised') AS category,
                COALESCE(SUM(total_value), 0)        AS total_value,
                COUNT(DISTINCT sku_code)             AS sku_count
            FROM tz_inventory_valuation
            GROUP BY 1
            ORDER BY total_value DESC
            LIMIT {MAX_CATEGORIES}
        """)
        rows = cur.fetchall()

    ls = _last_sync(conn, "inventory_valuation")
    return {
        "categories": [
            {"category": r[0], "total_value": float(r[1]), "sku_count": int(r[2])}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_top_stock_holdings(conn) -> dict:
    """
    S8 — Highest-value SKUs in stock (potential working-capital lock-up).
    Returns: skus list [{sku_code, sku_name, category, quantity, total_value}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT sku_code, sku_name, category, quantity, total_value
            FROM tz_inventory_valuation
            WHERE quantity > 0
            ORDER BY total_value DESC
            LIMIT {MAX_SKUS}
        """)
        rows = cur.fetchall()

    ls = _last_sync(conn, "inventory_valuation")
    return {
        "skus": [
            {"sku_code": r[0], "sku_name": r[1], "category": r[2],
             "quantity": float(r[3] or 0), "total_value": float(r[4] or 0)}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_purchases_summary(conn, period_days: int = 30) -> dict:
    """
    S9 — Purchase KPIs.
    Returns: period_spend, vendor_count, invoice_count, overdue_po_count
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE(SUM(invoice_total), 0) AS period_spend,
                COUNT(DISTINCT vendor_code)     AS vendor_count,
                COUNT(DISTINCT invoice_number)  AS invoice_count
            FROM tz_purchase_invoices
            WHERE invoice_date >= %s
        """, (since,))
        row = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) FROM tz_purchase_orders
            WHERE expected_date < CURRENT_DATE
            AND status NOT IN ('received', 'cancelled')
        """)
        overdue_pos = cur.fetchone()[0]

    ls = _last_sync(conn, "purchase_invoices")
    return {
        "period_days":    period_days,
        "period_spend":   float(row[0] or 0),
        "vendor_count":   int(row[1] or 0),
        "invoice_count":  int(row[2] or 0),
        "overdue_po_count": int(overdue_pos or 0),
        "last_synced_at": _fmt(ls),
        "stale":          _is_stale(ls),
    }


def get_top_vendors_spend(conn, period_days: int = 30) -> dict:
    """
    S10 — Top N vendors by purchase spend.
    Returns: vendors list [{vendor_name, spend, invoice_count, pct_of_total}]
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute(f"""
            WITH totals AS (
                SELECT SUM(invoice_total) AS grand_total
                FROM tz_purchase_invoices WHERE invoice_date >= %s
            )
            SELECT
                vendor_name,
                COALESCE(SUM(invoice_total), 0) AS spend,
                COUNT(DISTINCT invoice_number)  AS invoice_count,
                ROUND(
                    100.0 * SUM(invoice_total) / NULLIF((SELECT grand_total FROM totals), 0),
                    1
                ) AS pct
            FROM tz_purchase_invoices
            WHERE invoice_date >= %s
            GROUP BY vendor_name
            ORDER BY spend DESC
            LIMIT {MAX_VENDORS}
        """, (since, since))
        rows = cur.fetchall()

    ls = _last_sync(conn, "purchase_invoices")
    return {
        "period_days": period_days,
        "vendors": [
            {"vendor_name": r[0], "spend": float(r[1]),
             "invoice_count": int(r[2]), "pct_of_total": float(r[3] or 0)}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_production_summary(conn, period_days: int = 30) -> dict:
    """
    S11 — Production KPIs.
    Returns: fg_produced, rejected, reject_rate_pct, wip_count, completed_count
    """
    since = (date.today() - timedelta(days=period_days)).isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE(SUM(produced_qty), 0)  AS fg_produced,
                COALESCE(SUM(rejected_qty), 0)  AS rejected,
                COUNT(*) FILTER (WHERE status = 'wip')       AS wip_count,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed_count
            FROM tz_process_details
            WHERE production_date >= %s
        """, (since,))
        row = cur.fetchone()

    fg = float(row[0] or 0)
    rej = float(row[1] or 0)
    reject_rate = round(100.0 * rej / (fg + rej), 2) if (fg + rej) > 0 else 0.0

    ls = _last_sync(conn, "process_details")
    return {
        "period_days":      period_days,
        "fg_produced":      fg,
        "rejected":         rej,
        "reject_rate_pct":  reject_rate,
        "wip_count":        int(row[2] or 0),
        "completed_count":  int(row[3] or 0),
        "last_synced_at":   _fmt(ls),
        "stale":            _is_stale(ls),
    }


def get_order_book_summary(conn) -> dict:
    """
    S12 — Sales order book KPIs.
    Returns: open_order_count, open_order_value, dispatched_pct, overdue_count
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('dispatched', 'cancelled')) AS open_count,
                COALESCE(SUM(order_value) FILTER (WHERE status NOT IN ('dispatched','cancelled')), 0) AS open_value,
                COUNT(*) FILTER (WHERE status = 'dispatched') AS dispatched_count,
                COUNT(*) AS total_count,
                COUNT(*) FILTER (
                    WHERE delivery_date < CURRENT_DATE
                    AND status NOT IN ('dispatched', 'cancelled')
                ) AS overdue_count
            FROM tz_sales_orders
        """)
        row = cur.fetchone()

    total = int(row[3] or 0)
    dispatched = int(row[2] or 0)
    dispatched_pct = round(100.0 * dispatched / total, 1) if total > 0 else 0.0

    ls = _last_sync(conn, "sales_orders")
    return {
        "open_order_count":  int(row[0] or 0),
        "open_order_value":  float(row[1] or 0),
        "dispatched_pct":    dispatched_pct,
        "overdue_count":     int(row[4] or 0),
        "last_synced_at":    _fmt(ls),
        "stale":             _is_stale(ls),
    }


# ════════════════════════════════════════════════════════════════════════════
# OPERATIONAL PANELS (hourly cache — Sandeep's morning alerts)
# ════════════════════════════════════════════════════════════════════════════

def get_ar_summary(conn) -> dict:
    """
    O1 — AR aging buckets + overdue invoice list.
    Returns: aging_buckets, overdue_count, overdue_value, top_exposures
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                aging_bucket,
                COUNT(*)                            AS count,
                COALESCE(SUM(outstanding_amount), 0) AS value
            FROM tz_ar_aging
            GROUP BY aging_bucket
            ORDER BY aging_bucket
        """)
        buckets = cur.fetchall()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE days_overdue > 0) AS overdue_count,
                COALESCE(SUM(outstanding_amount) FILTER (WHERE days_overdue > 0), 0) AS overdue_value,
                COALESCE(SUM(outstanding_amount), 0) AS total_outstanding
            FROM tz_ar_aging
        """)
        summary = cur.fetchone()

        cur.execute(f"""
            SELECT
                customer_name,
                COALESCE(SUM(outstanding_amount), 0) AS outstanding,
                MAX(days_overdue)                    AS oldest_days
            FROM tz_ar_aging
            GROUP BY customer_name
            ORDER BY outstanding DESC
            LIMIT {MAX_CUSTOMERS}
        """)
        exposures = cur.fetchall()

    ls = _last_sync(conn, "ar_aging")
    return {
        "aging_buckets": [
            {"bucket": r[0], "count": int(r[1]), "value": float(r[2])}
            for r in buckets
        ],
        "overdue_count":     int(summary[0] or 0),
        "overdue_value":     float(summary[1] or 0),
        "total_outstanding": float(summary[2] or 0),
        "top_exposures": [
            {"customer_name": r[0], "outstanding": float(r[1]),
             "oldest_days": int(r[2] or 0)}
            for r in exposures
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_ar_customer_exposure(conn) -> dict:
    """
    O2 — AR exposure per customer with oldest invoice age.
    Returns: customers list [{customer_name, outstanding, invoice_count, oldest_days, overdue_value}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                customer_name,
                COALESCE(SUM(outstanding_amount), 0)                            AS outstanding,
                COUNT(*)                                                         AS invoice_count,
                MAX(days_overdue)                                                AS oldest_days,
                COALESCE(SUM(outstanding_amount) FILTER (WHERE days_overdue > 0), 0) AS overdue_value
            FROM tz_ar_aging
            GROUP BY customer_name
            ORDER BY outstanding DESC
            LIMIT {MAX_CUSTOMERS}
        """)
        rows = cur.fetchall()

    ls = _last_sync(conn, "ar_aging")
    return {
        "customers": [
            {
                "customer_name": r[0],
                "outstanding":   float(r[1]),
                "invoice_count": int(r[2]),
                "oldest_days":   int(r[3] or 0),
                "overdue_value": float(r[4]),
            }
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_overdue_pos(conn) -> dict:
    """
    O3 — Overdue purchase orders (past expected date, not received).
    Returns: pos list [{po_number, vendor_name, item_name, pending_qty, po_value,
                        expected_date, days_overdue}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                po_number,
                vendor_name,
                item_name,
                pending_qty,
                po_value,
                expected_date,
                (CURRENT_DATE - expected_date) AS days_overdue
            FROM tz_purchase_orders
            WHERE expected_date < CURRENT_DATE
            AND status NOT IN ('received', 'cancelled')
            ORDER BY days_overdue DESC
            LIMIT {MAX_INVOICES}
        """)
        rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(po_value), 0)
            FROM tz_purchase_orders
            WHERE expected_date < CURRENT_DATE
            AND status NOT IN ('received', 'cancelled')
        """)
        totals = cur.fetchone()

    ls = _last_sync(conn, "purchase_orders")
    return {
        "total_overdue_count": int(totals[0] or 0),
        "total_value_at_risk": float(totals[1] or 0),
        "pos": [
            {
                "po_number":    r[0],
                "vendor_name":  r[1],
                "item_name":    r[2],
                "pending_qty":  float(r[3] or 0),
                "po_value":     float(r[4] or 0),
                "expected_date": str(r[5]) if r[5] else None,
                "days_overdue": int(r[6] or 0),
            }
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_production_wip(conn) -> dict:
    """
    O4 — WIP and production status breakdown.
    Returns: status_breakdown [{status, count, planned_qty, produced_qty}],
             wip_items list (most recent WIP work orders)
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                status,
                COUNT(*)                       AS count,
                COALESCE(SUM(planned_qty), 0)  AS planned_qty,
                COALESCE(SUM(produced_qty), 0) AS produced_qty
            FROM tz_process_details
            GROUP BY status
            ORDER BY count DESC
        """)
        breakdown = cur.fetchall()

        cur.execute(f"""
            SELECT
                work_order_number,
                sku_name,
                process_name,
                planned_qty,
                produced_qty,
                production_date
            FROM tz_process_details
            WHERE status = 'wip'
            ORDER BY production_date DESC
            LIMIT {MAX_PROCESSES}
        """)
        wip = cur.fetchall()

    ls = _last_sync(conn, "process_details")
    return {
        "status_breakdown": [
            {"status": r[0], "count": int(r[1]),
             "planned_qty": float(r[2]), "produced_qty": float(r[3])}
            for r in breakdown
        ],
        "wip_items": [
            {
                "work_order_number": r[0],
                "sku_name":          r[1],
                "process_name":      r[2],
                "planned_qty":       float(r[3] or 0),
                "produced_qty":      float(r[4] or 0),
                "production_date":   str(r[5]) if r[5] else None,
            }
            for r in wip
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_overdue_orders(conn) -> dict:
    """
    O5 — Overdue order confirmations (past delivery date, not dispatched).
    Returns: orders list [{order_number, customer_name, sku_name, pending_qty,
                           order_value, delivery_date, days_overdue}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                order_number,
                customer_name,
                sku_name,
                pending_qty,
                order_value,
                delivery_date,
                (CURRENT_DATE - delivery_date) AS days_overdue
            FROM tz_sales_orders
            WHERE delivery_date < CURRENT_DATE
            AND status NOT IN ('dispatched', 'cancelled')
            ORDER BY days_overdue DESC
            LIMIT {MAX_INVOICES}
        """)
        rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(order_value), 0)
            FROM tz_sales_orders
            WHERE delivery_date < CURRENT_DATE
            AND status NOT IN ('dispatched', 'cancelled')
        """)
        totals = cur.fetchone()

    ls = _last_sync(conn, "sales_orders")
    return {
        "total_overdue_count": int(totals[0] or 0),
        "total_value":         float(totals[1] or 0),
        "orders": [
            {
                "order_number":  r[0],
                "customer_name": r[1],
                "sku_name":      r[2],
                "pending_qty":   float(r[3] or 0),
                "order_value":   float(r[4] or 0),
                "delivery_date": str(r[5]) if r[5] else None,
                "days_overdue":  int(r[6] or 0),
            }
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


# ════════════════════════════════════════════════════════════════════════════
# UTILITY
# ════════════════════════════════════════════════════════════════════════════

def get_sync_health(conn) -> dict:
    """
    /dashboard/sync/health — freshness of all 10 pipelines.
    Always reads live from tz_sync_runs (no caching).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (pipeline_name)
                pipeline_name,
                status,
                completed_at,
                rows_fetched,
                rows_upserted,
                error_message
            FROM tz_sync_runs
            ORDER BY pipeline_name, completed_at DESC NULLS LAST
        """)
        rows = cur.fetchall()

    pipelines = []
    for r in rows:
        last_sync_ts = r[2]
        stale = _is_stale(last_sync_ts)
        pipelines.append({
            "pipeline_name":  r[0],
            "status":         r[1],
            "completed_at":   _fmt(last_sync_ts),
            "rows_fetched":   r[3],
            "rows_upserted":  r[4],
            "error_message":  r[5],
            "stale":          stale,
        })

    all_healthy = all(p["status"] == "success" and not p["stale"] for p in pipelines)
    return {
        "all_healthy":  all_healthy,
        "pipeline_count": len(pipelines),
        "pipelines":    pipelines,
        "checked_at":   _fmt(_now_utc()),
    }
