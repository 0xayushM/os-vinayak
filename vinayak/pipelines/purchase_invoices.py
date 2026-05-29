"""
pipelines/purchase_invoices.py
──────────────────────────────
Pulls TranzAct report 77 (Purchase Invoices) and caches the result in
tz_purchase_invoices.

Dashboard panels fed:
  - Total procurement spend by period
  - Vendor-level spend breakdown
  - Item / category cost analysis
  - Tax liability tracker (input tax)
  - Invoice volume and average value trends
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import psycopg2.extras
from pydantic import BaseModel, field_validator, model_validator

from vinayak.pipelines.base import BasePipeline
from vinayak.pipelines.helpers import epoch_to_date

logger = logging.getLogger(__name__)


# ── Row schema ────────────────────────────────────────────────────────────────

class PurchaseInvoiceRow(BaseModel):
    raw_id: str
    invoice_date: Optional[date] = None
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_code: Optional[str] = None
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    tax_amount: Optional[float] = None
    invoice_total: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        raw_id = str(data.get("uuid") or data.get("document_id") or "").strip()
        if not raw_id:
            raise ValueError("Row has no uuid/document_id — cannot create raw_id")
        return {
            "raw_id":         raw_id,
            "invoice_date":   data.get("document_date"),
            "invoice_number": data.get("document_no_text"),
            "vendor_name":    data.get("supplier_name"),
            "vendor_code":    None,
            "item_code":      data.get("itemid"),
            "item_name":      data.get("item_name"),
            "quantity":       data.get("quantity"),
            "unit_price":     data.get("item_price"),
            "line_total":     data.get("item_total_value"),
            "tax_amount":     data.get("tax"),
            "invoice_total":  data.get("grand_total"),
        }

    @field_validator("invoice_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PurchaseInvoicesPipeline(BasePipeline):
    PIPELINE_NAME = "purchase_invoices"
    REPORT_ID = "77"
    TABLE_NAME = "tz_purchase_invoices"
    RowSchema = PurchaseInvoiceRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[PurchaseInvoiceRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.invoice_date,
                r.invoice_number,
                r.vendor_name,
                r.vendor_code,
                r.item_code,
                r.item_name,
                r.quantity,
                r.unit_price,
                r.line_total,
                r.tax_amount,
                r.invoice_total,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_purchase_invoices (
                raw_id, invoice_date, invoice_number, vendor_name, vendor_code,
                item_code, item_name, quantity, unit_price, line_total,
                tax_amount, invoice_total
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                invoice_date   = EXCLUDED.invoice_date,
                invoice_number = EXCLUDED.invoice_number,
                vendor_name    = EXCLUDED.vendor_name,
                vendor_code    = EXCLUDED.vendor_code,
                item_code      = EXCLUDED.item_code,
                item_name      = EXCLUDED.item_name,
                quantity       = EXCLUDED.quantity,
                unit_price     = EXCLUDED.unit_price,
                line_total     = EXCLUDED.line_total,
                tax_amount     = EXCLUDED.tax_amount,
                invoice_total  = EXCLUDED.invoice_total,
                fetched_at     = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
