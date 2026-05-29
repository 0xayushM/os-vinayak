"""
pipelines/ar_aging.py
─────────────────────
Pulls TranzAct report 102 (AR Aging) and caches the result in tz_ar_aging.

Dashboard panels fed:
  - Outstanding AR balance overview (total, by bucket)
  - Aging bucket distribution chart (0-30 / 31-60 / 61-90 / 90+)
  - Customer-level overdue breakdown table
  - Days-overdue trend over time
  - At-risk customer flag list (>90 days outstanding)
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

class ARAgingRow(BaseModel):
    raw_id: str
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    invoice_amount: Optional[float] = None
    outstanding_amount: Optional[float] = None
    days_overdue: Optional[int] = None
    aging_bucket: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        raw_id = str(data.get("uuid") or data.get("id") or "").strip()
        if not raw_id:
            raise ValueError("Row has no uuid/id — cannot create raw_id")
        return {
            "raw_id":             raw_id,
            "customer_name":      data.get("company_name"),
            "customer_code":      None,
            "invoice_number":     data.get("document_number"),
            "invoice_date":       data.get("document_date"),
            "due_date":           data.get("payment_date"),
            "invoice_amount":     data.get("amount_owe"),
            "outstanding_amount": data.get("balance_amount"),
            "days_overdue":       None,
            "aging_bucket":       None,
        }

    @field_validator("invoice_date", "due_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return epoch_to_date(v)

    @model_validator(mode="after")
    def compute_days_and_bucket(self) -> "ARAgingRow":
        """
        Compute days_overdue from due_date vs today, then derive aging_bucket.
        Buckets: 0-30, 31-60, 61-90, 90+.
        """
        if self.due_date is not None and self.days_overdue is None:
            delta = (date.today() - self.due_date).days
            self.days_overdue = max(0, delta)
        if self.aging_bucket is None and self.days_overdue is not None:
            d = self.days_overdue
            if d <= 30:
                self.aging_bucket = "0-30"
            elif d <= 60:
                self.aging_bucket = "31-60"
            elif d <= 90:
                self.aging_bucket = "61-90"
            else:
                self.aging_bucket = "90+"
        return self


# ── Pipeline ──────────────────────────────────────────────────────────────────

class ARAgingPipeline(BasePipeline):
    PIPELINE_NAME = "ar_aging"
    REPORT_ID = "102"
    TABLE_NAME = "tz_ar_aging"
    RowSchema = ARAgingRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        return {"filters": {"from_date": from_date, "to_date": to_date}}

    def _upsert(self, conn, rows: list[ARAgingRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.customer_name,
                r.customer_code,
                r.invoice_number,
                r.invoice_date,
                r.due_date,
                r.invoice_amount,
                r.outstanding_amount,
                r.days_overdue,
                r.aging_bucket,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_ar_aging (
                raw_id, customer_name, customer_code, invoice_number,
                invoice_date, due_date, invoice_amount, outstanding_amount,
                days_overdue, aging_bucket
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                customer_name      = EXCLUDED.customer_name,
                customer_code      = EXCLUDED.customer_code,
                invoice_number     = EXCLUDED.invoice_number,
                invoice_date       = EXCLUDED.invoice_date,
                due_date           = EXCLUDED.due_date,
                invoice_amount     = EXCLUDED.invoice_amount,
                outstanding_amount = EXCLUDED.outstanding_amount,
                days_overdue       = EXCLUDED.days_overdue,
                aging_bucket       = EXCLUDED.aging_bucket,
                fetched_at         = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
