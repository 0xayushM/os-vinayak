"""
pipelines/scheduler.py
───────────────────────
APScheduler configuration for all 10 Vinayak Brain OS pipelines.

Schedule summary (all times in IST, Asia/Kolkata):

  Hourly jobs  — run every hour at the specified minute offset:
    :00  ar_aging          — today only (point-in-time AR snapshot)
    :08  sales_orders      — last 7 days
    :16  purchase_orders   — last 7 days
    :24  inventory_valuation — snapshot (no date window)
    :32  process_details   — last 7 days

  Daily jobs   — run once at 3 AM IST, staggered by 5 minutes:
    03:00  sales_invoices      — last 30 days
    03:05  purchase_invoices   — last 30 days
    03:10  grn_qir             — last 30 days
    03:15  sales_quotations    — last 30 days
    03:20  process_routing     — last 30 days

Usage:
    from vinayak.pipelines.scheduler import scheduler, start_scheduler, stop_scheduler

    start_scheduler()   # starts background thread
    ...
    stop_scheduler()    # graceful shutdown
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Existing pipelines
from vinayak.pipelines.ar_aging import ARAgingPipeline
from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
from vinayak.pipelines.sales_orders import SalesOrdersPipeline
from vinayak.pipelines.purchase_invoices import PurchaseInvoicesPipeline
from vinayak.pipelines.purchase_orders import PurchaseOrdersPipeline

# New pipelines
from vinayak.pipelines.grn_qir import GRNQIRPipeline
from vinayak.pipelines.sales_quotations import SalesQuotationsPipeline
from vinayak.pipelines.inventory_valuation import InventoryValuationPipeline
from vinayak.pipelines.process_routing import ProcessRoutingPipeline
from vinayak.pipelines.process_details import ProcessDetailsPipeline

logger = logging.getLogger(__name__)

_IST = "Asia/Kolkata"

# ── Pipeline singletons ───────────────────────────────────────────────────────

_ar_aging = ARAgingPipeline()
_sales_invoices = SalesInvoicesPipeline()
_sales_orders = SalesOrdersPipeline()
_purchase_invoices = PurchaseInvoicesPipeline()
_purchase_orders = PurchaseOrdersPipeline()
_grn_qir = GRNQIRPipeline()
_sales_quotations = SalesQuotationsPipeline()
_inventory_valuation = InventoryValuationPipeline()
_process_routing = ProcessRoutingPipeline()
_process_details = ProcessDetailsPipeline()


# ── Job functions ─────────────────────────────────────────────────────────────

def _run_ar_aging() -> None:
    """AR Aging — today only (point-in-time snapshot)."""
    today = date.today()
    logger.info("Scheduler: starting ar_aging for %s", today)
    _ar_aging.run(today, today)


def _run_sales_orders() -> None:
    """Sales Orders — last 7 days."""
    today = date.today()
    from_date = today - timedelta(days=7)
    logger.info("Scheduler: starting sales_orders %s → %s", from_date, today)
    _sales_orders.run(from_date, today)


def _run_purchase_orders() -> None:
    """Purchase Orders — last 7 days."""
    today = date.today()
    from_date = today - timedelta(days=7)
    logger.info("Scheduler: starting purchase_orders %s → %s", from_date, today)
    _purchase_orders.run(from_date, today)


def _run_inventory_valuation() -> None:
    """Inventory Valuation — snapshot, date args accepted but not forwarded."""
    today = date.today()
    logger.info("Scheduler: starting inventory_valuation snapshot for %s", today)
    _inventory_valuation.run(today, today)


def _run_process_details() -> None:
    """Process Details — last 7 days."""
    today = date.today()
    from_date = today - timedelta(days=7)
    logger.info("Scheduler: starting process_details %s → %s", from_date, today)
    _process_details.run(from_date, today)


def _run_sales_invoices() -> None:
    """Sales Invoices — last 30 days."""
    today = date.today()
    from_date = today - timedelta(days=30)
    logger.info("Scheduler: starting sales_invoices %s → %s", from_date, today)
    _sales_invoices.run(from_date, today)


def _run_purchase_invoices() -> None:
    """Purchase Invoices — last 30 days."""
    today = date.today()
    from_date = today - timedelta(days=30)
    logger.info("Scheduler: starting purchase_invoices %s → %s", from_date, today)
    _purchase_invoices.run(from_date, today)


def _run_grn_qir() -> None:
    """GRN / QIR — last 30 days."""
    today = date.today()
    from_date = today - timedelta(days=30)
    logger.info("Scheduler: starting grn_qir %s → %s", from_date, today)
    _grn_qir.run(from_date, today)


def _run_sales_quotations() -> None:
    """Sales Quotations — last 30 days."""
    today = date.today()
    from_date = today - timedelta(days=30)
    logger.info("Scheduler: starting sales_quotations %s → %s", from_date, today)
    _sales_quotations.run(from_date, today)


def _run_process_routing() -> None:
    """Process Routing — last 30 days."""
    today = date.today()
    from_date = today - timedelta(days=30)
    logger.info("Scheduler: starting process_routing %s → %s", from_date, today)
    _process_routing.run(from_date, today)


# ── Scheduler instance ────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone=_IST)

# -- Hourly jobs (staggered by minute to avoid rate-limit bursting) -----------

scheduler.add_job(
    _run_ar_aging,
    trigger=CronTrigger(minute=0, timezone=_IST),
    id="ar_aging_hourly",
    name="AR Aging (hourly, :00)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_sales_orders,
    trigger=CronTrigger(minute=8, timezone=_IST),
    id="sales_orders_hourly",
    name="Sales Orders (hourly, :08)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_purchase_orders,
    trigger=CronTrigger(minute=16, timezone=_IST),
    id="purchase_orders_hourly",
    name="Purchase Orders (hourly, :16)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_inventory_valuation,
    trigger=CronTrigger(minute=24, timezone=_IST),
    id="inventory_valuation_hourly",
    name="Inventory Valuation (hourly, :24)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_process_details,
    trigger=CronTrigger(minute=32, timezone=_IST),
    id="process_details_hourly",
    name="Process Details (hourly, :32)",
    replace_existing=True,
    misfire_grace_time=300,
)

# -- Daily jobs at 3 AM IST (staggered by 5 minutes each) --------------------

scheduler.add_job(
    _run_sales_invoices,
    trigger=CronTrigger(hour=3, minute=0, timezone=_IST),
    id="sales_invoices_daily",
    name="Sales Invoices (daily, 03:00 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_purchase_invoices,
    trigger=CronTrigger(hour=3, minute=5, timezone=_IST),
    id="purchase_invoices_daily",
    name="Purchase Invoices (daily, 03:05 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_grn_qir,
    trigger=CronTrigger(hour=3, minute=10, timezone=_IST),
    id="grn_qir_daily",
    name="GRN / QIR (daily, 03:10 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_sales_quotations,
    trigger=CronTrigger(hour=3, minute=15, timezone=_IST),
    id="sales_quotations_daily",
    name="Sales Quotations (daily, 03:15 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_process_routing,
    trigger=CronTrigger(hour=3, minute=20, timezone=_IST),
    id="process_routing_daily",
    name="Process Routing (daily, 03:20 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)


# ── Public start / stop helpers ───────────────────────────────────────────────

def start_scheduler() -> None:
    """Start the APScheduler background loop (idempotent)."""
    if not scheduler.running:
        scheduler.start()
        logger.info(
            "Scheduler started — %d jobs registered (timezone: %s)",
            len(scheduler.get_jobs()),
            _IST,
        )
    else:
        logger.warning("start_scheduler() called but scheduler is already running.")


def stop_scheduler() -> None:
    """Gracefully shut down the APScheduler background loop."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped.")
    else:
        logger.warning("stop_scheduler() called but scheduler is not running.")
