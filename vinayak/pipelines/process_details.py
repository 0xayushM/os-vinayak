"""
pipelines/process_details.py
─────────────────────────────
Pulls TranzAct report 25 (Process Details / Shop Floor) and caches the
result in tz_process_details.

Dashboard panels fed:
  - Production output vs planned quantity by work order
  - Process-level rejection and rework rate
  - Work order completion status tracker
  - SKU-level daily production throughput
  - Process efficiency (produced_qty / planned_qty) trend
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

class ProcessDetailsRow(BaseModel):
    raw_id: str
    production_date: Optional[date] = None
    work_order_number: Optional[str] = None
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    process_name: Optional[str] = None
    planned_qty: Optional[float] = None
    produced_qty: Optional[float] = None
    rejected_qty: Optional[float] = None
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        raw_id = str(data.get("uuid") or data.get("process_id") or "").strip()
        if not raw_id:
            raise ValueError("Row has no uuid/process_id — cannot create raw_id")
        return {
            "raw_id":             raw_id,
            "production_date":    data.get("creation_date"),
            "work_order_number":  data.get("document_number"),
            "sku_code":           data.get("itemid"),
            "sku_name":           data.get("product_name"),
            "process_name":       data.get("bom_name"),
            "planned_qty":        data.get("req_mfg_quantity"),
            "produced_qty":       data.get("produced_quantity"),
            "rejected_qty":       data.get("fg_reject_quantity"),
            "status":             data.get("status_text"),
        }

    @field_validator("production_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class ProcessDetailsPipeline(BasePipeline):
    PIPELINE_NAME = "process_details"
    REPORT_ID = "25"
    TABLE_NAME = "tz_process_details"
    RowSchema = ProcessDetailsRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[ProcessDetailsRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.production_date,
                r.work_order_number,
                r.sku_code,
                r.sku_name,
                r.process_name,
                r.planned_qty,
                r.produced_qty,
                r.rejected_qty,
                r.status,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_process_details (
                raw_id, production_date, work_order_number, sku_code, sku_name,
                process_name, planned_qty, produced_qty, rejected_qty, status
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                production_date   = EXCLUDED.production_date,
                work_order_number = EXCLUDED.work_order_number,
                sku_code          = EXCLUDED.sku_code,
                sku_name          = EXCLUDED.sku_name,
                process_name      = EXCLUDED.process_name,
                planned_qty       = EXCLUDED.planned_qty,
                produced_qty      = EXCLUDED.produced_qty,
                rejected_qty      = EXCLUDED.rejected_qty,
                status            = EXCLUDED.status,
                fetched_at        = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
