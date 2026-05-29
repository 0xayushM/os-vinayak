"""
pipelines/sales_quotations.py
──────────────────────────────
Pulls TranzAct report 8 (Sales Quotations) and caches the result in
tz_sales_quotations.

Dashboard panels fed:
  - Quotation volume and value by period
  - Conversion rate tracker (quoted → order)
  - Customer-level quotation pipeline
  - SKU-level quote frequency and value analysis
  - Expiring quotations alert list
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

class SalesQuotationRow(BaseModel):
    raw_id: str
    quote_date: Optional[date] = None
    quote_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    quoted_qty: Optional[float] = None
    quoted_value: Optional[float] = None
    status: Optional[str] = None
    valid_until: Optional[date] = None
    converted_to_order: Optional[bool] = False

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        raw_id = str(data.get("uuid") or data.get("document_id") or "").strip()
        if not raw_id:
            raise ValueError("Row has no uuid/document_id — cannot create raw_id")
        return {
            "raw_id":             raw_id,
            "quote_date":         data.get("document_date") or data.get("creation_date"),
            "quote_number":       data.get("document_no_text"),
            "customer_name":      data.get("customer_name"),
            "customer_code":      None,
            "sku_code":           data.get("itemid"),
            "sku_name":           data.get("item_name"),
            "quoted_qty":         data.get("quantity"),
            "quoted_value":       data.get("item_total_value") or data.get("grand_total"),
            "status":             data.get("document_status"),
            "valid_until":        data.get("valid_till_date") or data.get("expiry_date"),
            "converted_to_order": data.get("converted_to_order", False),
        }

    @field_validator("quote_date", "valid_until", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)

    @field_validator("converted_to_order", mode="before")
    @classmethod
    def coerce_bool(cls, v):
        if v is None or v == "":
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "y")
        return False


# ── Pipeline ──────────────────────────────────────────────────────────────────

class SalesQuotationsPipeline(BasePipeline):
    PIPELINE_NAME = "sales_quotations"
    REPORT_ID = "8"
    TABLE_NAME = "tz_sales_quotations"
    RowSchema = SalesQuotationRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[SalesQuotationRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.quote_date,
                r.quote_number,
                r.customer_name,
                r.customer_code,
                r.sku_code,
                r.sku_name,
                r.quoted_qty,
                r.quoted_value,
                r.status,
                r.valid_until,
                r.converted_to_order,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_sales_quotations (
                raw_id, quote_date, quote_number, customer_name, customer_code,
                sku_code, sku_name, quoted_qty, quoted_value, status,
                valid_until, converted_to_order
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                quote_date         = EXCLUDED.quote_date,
                quote_number       = EXCLUDED.quote_number,
                customer_name      = EXCLUDED.customer_name,
                customer_code      = EXCLUDED.customer_code,
                sku_code           = EXCLUDED.sku_code,
                sku_name           = EXCLUDED.sku_name,
                quoted_qty         = EXCLUDED.quoted_qty,
                quoted_value       = EXCLUDED.quoted_value,
                status             = EXCLUDED.status,
                valid_until        = EXCLUDED.valid_until,
                converted_to_order = EXCLUDED.converted_to_order,
                fetched_at         = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
