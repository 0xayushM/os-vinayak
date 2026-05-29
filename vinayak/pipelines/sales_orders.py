"""
pipelines/sales_orders.py
─────────────────────────
Pulls TranzAct report 2 (Sales Orders) and caches the result in
tz_sales_orders.

Dashboard panels fed:
  - Open vs dispatched orders summary
  - Order fulfilment rate (dispatched_qty / ordered_qty)
  - Pending order backlog value by customer
  - Delivery date adherence tracker
  - SKU-level order volume and status breakdown
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

class SalesOrderRow(BaseModel):
    raw_id: str
    order_date: Optional[date] = None
    order_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    ordered_qty: Optional[float] = None
    dispatched_qty: Optional[float] = None
    pending_qty: Optional[float] = None
    order_value: Optional[float] = None
    delivery_date: Optional[date] = None
    status: Optional[str] = None

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
            "order_date":     data.get("oc_date"),
            "order_number":   data.get("oc_number"),
            "customer_name":  data.get("customer_name"),
            "customer_code":  None,
            "sku_code":       data.get("itemid"),
            "sku_name":       data.get("item_name"),
            "ordered_qty":    data.get("quantity"),
            "dispatched_qty": data.get("dispatched_quantity"),
            "pending_qty":    data.get("balance_quantity"),
            "order_value":    data.get("item_total_value"),
            "delivery_date":  data.get("doc_delivery_date"),
            "status":         data.get("document_status"),
        }

    @field_validator("order_date", "delivery_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class SalesOrdersPipeline(BasePipeline):
    PIPELINE_NAME = "sales_orders"
    REPORT_ID = "2"
    TABLE_NAME = "tz_sales_orders"
    RowSchema = SalesOrderRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[SalesOrderRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.order_date,
                r.order_number,
                r.customer_name,
                r.customer_code,
                r.sku_code,
                r.sku_name,
                r.ordered_qty,
                r.dispatched_qty,
                r.pending_qty,
                r.order_value,
                r.delivery_date,
                r.status,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_sales_orders (
                raw_id, order_date, order_number, customer_name, customer_code,
                sku_code, sku_name, ordered_qty, dispatched_qty, pending_qty,
                order_value, delivery_date, status
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                order_date     = EXCLUDED.order_date,
                order_number   = EXCLUDED.order_number,
                customer_name  = EXCLUDED.customer_name,
                customer_code  = EXCLUDED.customer_code,
                sku_code       = EXCLUDED.sku_code,
                sku_name       = EXCLUDED.sku_name,
                ordered_qty    = EXCLUDED.ordered_qty,
                dispatched_qty = EXCLUDED.dispatched_qty,
                pending_qty    = EXCLUDED.pending_qty,
                order_value    = EXCLUDED.order_value,
                delivery_date  = EXCLUDED.delivery_date,
                status         = EXCLUDED.status,
                fetched_at     = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
