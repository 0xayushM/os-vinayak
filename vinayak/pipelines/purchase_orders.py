"""
pipelines/purchase_orders.py
────────────────────────────
Pulls TranzAct report 3 (Purchase Orders) and caches the result in
tz_purchase_orders.

Dashboard panels fed:
  - Open PO value and volume by vendor
  - PO fulfilment rate (received_qty / ordered_qty)
  - Pending receipts and expected delivery tracker
  - Item-level procurement order analysis
  - PO status breakdown (open / partially received / closed)
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

class PurchaseOrderRow(BaseModel):
    raw_id: str
    po_date: Optional[date] = None
    po_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_code: Optional[str] = None
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    ordered_qty: Optional[float] = None
    received_qty: Optional[float] = None
    pending_qty: Optional[float] = None
    po_value: Optional[float] = None
    expected_date: Optional[date] = None
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
            "raw_id":       raw_id,
            "po_date":      data.get("document_date"),
            "po_number":    data.get("document_no_text"),
            "vendor_name":  data.get("supplier_name"),
            "vendor_code":  None,
            "item_code":    None,
            "item_name":    None,
            "ordered_qty":  None,
            "received_qty": None,
            "pending_qty":  None,
            "po_value":     data.get("grand_total"),
            "expected_date": data.get("doc_delivery_date"),
            "status":       data.get("document_status"),
        }

    @field_validator("po_date", "expected_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PurchaseOrdersPipeline(BasePipeline):
    PIPELINE_NAME = "purchase_orders"
    REPORT_ID = "3"
    TABLE_NAME = "tz_purchase_orders"
    RowSchema = PurchaseOrderRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[PurchaseOrderRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.po_date,
                r.po_number,
                r.vendor_name,
                r.vendor_code,
                r.item_code,
                r.item_name,
                r.ordered_qty,
                r.received_qty,
                r.pending_qty,
                r.po_value,
                r.expected_date,
                r.status,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_purchase_orders (
                raw_id, po_date, po_number, vendor_name, vendor_code,
                item_code, item_name, ordered_qty, received_qty, pending_qty,
                po_value, expected_date, status
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                po_date       = EXCLUDED.po_date,
                po_number     = EXCLUDED.po_number,
                vendor_name   = EXCLUDED.vendor_name,
                vendor_code   = EXCLUDED.vendor_code,
                item_code     = EXCLUDED.item_code,
                item_name     = EXCLUDED.item_name,
                ordered_qty   = EXCLUDED.ordered_qty,
                received_qty  = EXCLUDED.received_qty,
                pending_qty   = EXCLUDED.pending_qty,
                po_value      = EXCLUDED.po_value,
                expected_date = EXCLUDED.expected_date,
                status        = EXCLUDED.status,
                fetched_at    = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
