"""
pipelines/grn_qir.py
────────────────────
Pulls TranzAct report 34 (GRN / Quality Inspection Report) and caches the
result in tz_grn_qir.

Dashboard panels fed:
  - Goods received vs ordered quantity by vendor
  - Rejection rate tracker (rejected_qty / received_qty)
  - PO fulfilment and acceptance analysis
  - Vendor quality scorecard
  - Item-level receipt and inspection breakdown
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

class GRNQIRRow(BaseModel):
    raw_id: str
    grn_date: Optional[date] = None
    grn_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_code: Optional[str] = None
    po_number: Optional[str] = None
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    ordered_qty: Optional[float] = None
    received_qty: Optional[float] = None
    rejected_qty: Optional[float] = None
    accepted_qty: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        raw_id = str(data.get("uuid") or data.get("document_id") or "").strip()
        if not raw_id:
            raise ValueError("Row has no uuid/document_id — cannot create raw_id")
        received = data.get("received_quantity")
        return {
            "raw_id":       raw_id,
            "grn_date":     data.get("inward_date"),
            "grn_number":   data.get("inward_number"),
            "vendor_name":  data.get("supplier_name"),
            "vendor_code":  None,
            "po_number":    data.get("po_number"),
            "item_code":    data.get("itemid"),
            "item_name":    data.get("item_name"),
            "ordered_qty":  None,
            "received_qty": received,
            "rejected_qty": None,
            "accepted_qty": received,
        }

    @field_validator("grn_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class GRNQIRPipeline(BasePipeline):
    PIPELINE_NAME = "grn_qir"
    REPORT_ID = "34"
    TABLE_NAME = "tz_grn_qir"
    RowSchema = GRNQIRRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[GRNQIRRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.grn_date,
                r.grn_number,
                r.vendor_name,
                r.vendor_code,
                r.po_number,
                r.item_code,
                r.item_name,
                r.ordered_qty,
                r.received_qty,
                r.rejected_qty,
                r.accepted_qty,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_grn_qir (
                raw_id, grn_date, grn_number, vendor_name, vendor_code,
                po_number, item_code, item_name, ordered_qty, received_qty,
                rejected_qty, accepted_qty
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                grn_date     = EXCLUDED.grn_date,
                grn_number   = EXCLUDED.grn_number,
                vendor_name  = EXCLUDED.vendor_name,
                vendor_code  = EXCLUDED.vendor_code,
                po_number    = EXCLUDED.po_number,
                item_code    = EXCLUDED.item_code,
                item_name    = EXCLUDED.item_name,
                ordered_qty  = EXCLUDED.ordered_qty,
                received_qty = EXCLUDED.received_qty,
                rejected_qty = EXCLUDED.rejected_qty,
                accepted_qty = EXCLUDED.accepted_qty,
                fetched_at   = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
