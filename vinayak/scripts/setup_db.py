"""
scripts/setup_db.py
────────────────────
One-shot script to apply schema/init.sql against the configured Postgres DB.

Usage:
    python -m vinayak.scripts.setup_db

Run this ONCE before starting the server for the first time.
Safe to re-run — all CREATE TABLE statements use IF NOT EXISTS.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL is not set. Check your .env file.")
        sys.exit(1)

    sql_path = Path(__file__).parent.parent / "schema" / "init.sql"
    if not sql_path.exists():
        logger.error("schema/init.sql not found at %s", sql_path)
        sys.exit(1)

    sql = sql_path.read_text()

    logger.info("Connecting to database…")
    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:
        logger.error("Could not connect: %s", exc)
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            logger.info("Applying schema/init.sql…")
            cur.execute(sql)
        conn.commit()
        logger.info("✓ Schema applied successfully.")
    except Exception as exc:
        conn.rollback()
        logger.error("Schema application failed: %s", exc)
        sys.exit(1)
    finally:
        conn.close()

    # Verify key tables exist
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            tables = [
                "companies", "users", "tool_connections",
                "tz_sales_invoices", "tz_ar_aging", "tz_inventory_valuation",
                "tz_sync_runs",
            ]
            for table in tables:
                cur.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = %s)",
                    (table,),
                )
                exists = cur.fetchone()[0]
                status = "✓" if exists else "✗ MISSING"
                logger.info("  %s  %s", status, table)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
