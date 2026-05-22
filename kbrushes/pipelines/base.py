"""
pipelines/base.py
──────────────────
BasePipeline — all 10 concrete pipelines inherit from this class.

Subclasses must define:
    PIPELINE_NAME : str   (matches tz_sync_runs.pipeline_name)
    REPORT_ID     : str   (TranzAct report ID, e.g. "29")
    TABLE_NAME    : str   (Postgres table, e.g. "tz_sales_invoices")
    RowSchema     : type  (Pydantic BaseModel for one row)

Subclasses must implement:
    _get_filters(from_date, to_date) -> dict
        Returns the filters dict to pass to fetch_report().
    _upsert(conn, rows) -> int
        Performs the INSERT … ON CONFLICT DO UPDATE and returns rows upserted.

The run() method provides the full pipeline contract:
    fetch → validate → upsert → log → error handling
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Type

import psycopg2
import psycopg2.extras

from kbrushes.adapters.tranzact.client import fetch_report
from kbrushes.config import DATABASE_URL

logger = logging.getLogger(__name__)


class BasePipeline(ABC):

    PIPELINE_NAME: str
    REPORT_ID: str
    TABLE_NAME: str
    RowSchema: type  # Pydantic model

    # ── Public methods ────────────────────────────────────────────────────────

    def run(self, from_date: date, to_date: date, is_backfill: bool = False) -> None:
        """
        Full pipeline run:
          1. Open a DB connection and log 'running' to tz_sync_runs
          2. Fetch all rows from TranzAct
          3. Validate rows with Pydantic (bad rows are skipped, not raised)
          4. Upsert valid rows into the cached table
          5. Update tz_sync_runs with 'success' or 'failed'
        """
        conn = psycopg2.connect(DATABASE_URL)
        run_id = self._start_run(conn, is_backfill)
        rows_fetched = 0
        rows_upserted = 0
        try:
            filters = self._get_filters(str(from_date), str(to_date))
            raw_rows = fetch_report(self.REPORT_ID, filters)
            rows_fetched = len(raw_rows)

            validated = self._validate(raw_rows)
            rows_upserted = self._upsert(conn, validated)

            self._finish_run(conn, run_id, "success", rows_fetched, rows_upserted)
            logger.info(
                "%s: ✅  fetched=%d upserted=%d",
                self.PIPELINE_NAME, rows_fetched, rows_upserted,
            )
        except Exception as exc:
            self._fail_run(conn, run_id, str(exc))
            logger.error("%s: ❌  %s", self.PIPELINE_NAME, exc)
            raise
        finally:
            conn.close()

    def backfill(
        self,
        from_date: date,
        window_days: int = 30,
        sleep_between_windows: float = 1.0,
    ) -> None:
        """
        Split the period from_date → today into windows and run each.

        Args:
            from_date:              First date to backfill from (e.g. date(2025, 11, 1))
            window_days:            Size of each fetch window (default 30 days)
            sleep_between_windows:  Seconds to sleep between windows (rate limit safety)
        """
        today = date.today()
        cursor = from_date
        window_count = 0

        while cursor < today:
            end = min(cursor + timedelta(days=window_days - 1), today)
            logger.info(
                "%s backfill: window %d — %s → %s",
                self.PIPELINE_NAME, window_count + 1, cursor, end,
            )
            self.run(cursor, end, is_backfill=True)
            cursor = end + timedelta(days=1)
            window_count += 1
            if cursor < today and sleep_between_windows > 0:
                time.sleep(sleep_between_windows)

        logger.info("%s backfill: complete — %d windows", self.PIPELINE_NAME, window_count)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _validate(self, raw_rows: list[dict]) -> list:
        """
        Run each row through RowSchema Pydantic validation.
        Bad rows are logged and skipped — a failed row never crashes the pipeline.
        Returns a list of validated Pydantic model instances.
        """
        valid, skipped = [], 0
        for row in raw_rows:
            try:
                valid.append(self.RowSchema(**row))
            except Exception as exc:
                skipped += 1
                logger.debug(
                    "%s: skipped invalid row (%s) | row=%s",
                    self.PIPELINE_NAME, exc, row,
                )
        if skipped:
            logger.warning(
                "%s: %d/%d rows skipped during validation",
                self.PIPELINE_NAME, skipped, len(raw_rows),
            )
        return valid

    def _start_run(self, conn, is_backfill: bool) -> int:
        """Insert a 'running' row into tz_sync_runs. Returns the run ID."""
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tz_sync_runs
                       (pipeline_name, report_id, status, is_backfill)
                   VALUES (%s, %s, 'running', %s)
                   RETURNING id""",
                (self.PIPELINE_NAME, int(self.REPORT_ID), is_backfill),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id

    def _finish_run(self, conn, run_id: int, status: str,
                    rows_fetched: int, rows_upserted: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tz_sync_runs
                   SET status=%s, rows_fetched=%s, rows_upserted=%s,
                       completed_at=NOW()
                   WHERE id=%s""",
                (status, rows_fetched, rows_upserted, run_id),
            )
        conn.commit()

    def _fail_run(self, conn, run_id: int, error_message: str) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tz_sync_runs
                       SET status='failed', error_message=%s, completed_at=NOW()
                       WHERE id=%s""",
                    (error_message[:2000], run_id),
                )
            conn.commit()
        except Exception as log_exc:
            logger.error("Could not log pipeline failure: %s", log_exc)

    # ── Abstract methods (subclasses implement these) ─────────────────────────

    @abstractmethod
    def _get_filters(self, from_date: str, to_date: str) -> dict:
        """Return the filters dict for fetch_report()."""
        ...

    @abstractmethod
    def _upsert(self, conn, rows: list) -> int:
        """Insert/update rows into the cached table. Return count of rows upserted."""
        ...
