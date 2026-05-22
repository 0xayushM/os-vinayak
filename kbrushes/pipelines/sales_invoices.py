"""
pipelines/sales_invoices.py
───────────────────────────
Pulls TranzAct report 29 (Sales Invoices) and caches the result in
tz_sales_invoices.

Dashboard panels fed:
  - Revenue by period (line / bar charts)
  - Invoice-level drill-down table
  - Top customers by revenue
  - SKU / category revenue mix
  - Payment status tracker (paid vs outstanding)
  - Salesperson performance summary
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import psycopg2.extras
from pydantic import BaseModel, field_validator, model_validator

from kbrushes.pipelines.base import BasePipeline

logger = logging.getLogger(__name__)


# ── Row schema ────────────────────────────────────────────────────────────────

class SalesInvoiceRow(BaseModel):
    raw_id: str
    invoice_date: Optional[date] = None
    invoice_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    tax_amount: Optional[float] = None
    invoice_total: Optional[float] = None
    payment_status: Optional[str] = None
    due_date: Optional[date] = None
    salesperson: Optional[str] = None

    @field_validator("invoice_date", "due_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v)[:10])
        except (ValueError, TypeError):
            return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

class SalesInvoicesPipeline(BasePipeline):
    PIPELINE_NAME = "sales_invoices"
    REPORT_ID = "29"
    TABLE_NAME = "tz_sales_invoices"
    RowSchema = SalesInvoiceRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[SalesInvoiceRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.invoice_date,
                r.invoice_number,
                r.customer_name,
                r.customer_code,
                r.sku_code,
                r.sku_name,
                r.category,
                r.quantity,
                r.unit_price,
                r.line_total,
                r.tax_amount,
                r.invoice_total,
                r.payment_status,
                r.due_date,
                r.salesperson,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_sales_invoices (
                raw_id, invoice_date, invoice_number, customer_name, customer_code,
                sku_code, sku_name, category, quantity, unit_price, line_total,
                tax_amount, invoice_total, payment_status, due_date, salesperson
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                invoice_date    = EXCLUDED.invoice_date,
                invoice_number  = EXCLUDED.invoice_number,
                customer_name   = EXCLUDED.customer_name,
                customer_code   = EXCLUDED.customer_code,
                sku_code        = EXCLUDED.sku_code,
                sku_name        = EXCLUDED.sku_name,
                category        = EXCLUDED.category,
                quantity        = EXCLUDED.quantity,
                unit_price      = EXCLUDED.unit_price,
                line_total      = EXCLUDED.line_total,
                tax_amount      = EXCLUDED.tax_amount,
                invoice_total   = EXCLUDED.invoice_total,
                payment_status  = EXCLUDED.payment_status,
                due_date        = EXCLUDED.due_date,
                salesperson     = EXCLUDED.salesperson,
                updated_at      = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
