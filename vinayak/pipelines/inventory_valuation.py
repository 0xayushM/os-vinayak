"""
pipelines/inventory_valuation.py
─────────────────────────────────
Pulls TranzAct report 9 (Inventory Valuation) and caches the result in
tz_inventory_valuation.

No date filter is applied — this report always returns a full snapshot of
current stock positions, so _get_filters() returns {}.

Dashboard panels fed:
  - Total inventory value and on-hand quantity
  - Inventory value breakdown by category and warehouse
  - Raw material vs finished goods split
  - Dead stock / low-turnover SKU list
  - Per-SKU unit cost and quantity position
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import psycopg2.extras
from pydantic import BaseModel, field_validator, model_validator

from vinayak.pipelines.base import BasePipeline

logger = logging.getLogger(__name__)


# ── Row schema ────────────────────────────────────────────────────────────────

class InventoryValuationRow(BaseModel):
    raw_id: str
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    category: Optional[str] = None
    warehouse: Optional[str] = None
    quantity: Optional[float] = None
    unit_cost: Optional[float] = None
    total_value: Optional[float] = None
    is_raw_material: Optional[bool] = False

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        raw_id = str(data.get("uuid") or data.get("product_id") or "").strip()
        if not raw_id:
            raise ValueError("Row has no uuid/product_id — cannot create raw_id")
        item_type = str(data.get("type") or "").strip().lower()
        return {
            "raw_id":          raw_id,
            "sku_code":        data.get("itemid"),
            "sku_name":        data.get("name"),
            "category":        data.get("category"),
            "warehouse":       None,
            "quantity":        data.get("cal_final_stock"),
            "unit_cost":       data.get("average_price"),
            "total_value":     data.get("cal_final_stock_cost"),
            "is_raw_material": item_type == "raw material",
        }

    @field_validator("is_raw_material", mode="before")
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

class InventoryValuationPipeline(BasePipeline):
    PIPELINE_NAME = "inventory_valuation"
    REPORT_ID = "9"
    TABLE_NAME = "tz_inventory_valuation"
    RowSchema = InventoryValuationRow

    def _get_filters(self, from_date: str, to_date: str) -> dict:
        # Inventory valuation is a point-in-time snapshot — no date window.
        return {}

    def _upsert(self, conn, rows: list[InventoryValuationRow]) -> int:
        if not rows:
            return 0

        records = [
            (
                r.raw_id,
                r.sku_code,
                r.sku_name,
                r.category,
                r.warehouse,
                r.quantity,
                r.unit_cost,
                r.total_value,
                r.is_raw_material,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_inventory_valuation (
                raw_id, sku_code, sku_name, category, warehouse,
                quantity, unit_cost, total_value, is_raw_material
            ) VALUES %s
            ON CONFLICT (raw_id) DO UPDATE SET
                sku_code        = EXCLUDED.sku_code,
                sku_name        = EXCLUDED.sku_name,
                category        = EXCLUDED.category,
                warehouse       = EXCLUDED.warehouse,
                quantity        = EXCLUDED.quantity,
                unit_cost       = EXCLUDED.unit_cost,
                total_value     = EXCLUDED.total_value,
                is_raw_material = EXCLUDED.is_raw_material,
                fetched_at      = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
