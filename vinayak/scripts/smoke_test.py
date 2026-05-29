"""
scripts/smoke_test.py
──────────────────────
Run all 9 fixed pipelines over a 90-day window and print upserted row counts.
Verifies that data actually lands in Supabase.

Usage:
    python -m vinayak.scripts.smoke_test
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv()

from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
from vinayak.pipelines.ar_aging import ARAgingPipeline
from vinayak.pipelines.sales_orders import SalesOrdersPipeline
from vinayak.pipelines.purchase_invoices import PurchaseInvoicesPipeline
from vinayak.pipelines.purchase_orders import PurchaseOrdersPipeline
from vinayak.pipelines.grn_qir import GRNQIRPipeline
from vinayak.pipelines.inventory_valuation import InventoryValuationPipeline
from vinayak.pipelines.process_routing import ProcessRoutingPipeline
from vinayak.pipelines.process_details import ProcessDetailsPipeline

TODAY = date.today()
FROM  = TODAY - timedelta(days=90)

PIPELINES = [
    ("Inventory Valuation", InventoryValuationPipeline),
    ("Process Routing",     ProcessRoutingPipeline),
    ("AR Aging",            ARAgingPipeline),
    ("Sales Invoices",      SalesInvoicesPipeline),
    ("Sales Orders",        SalesOrdersPipeline),
    ("Purchase Invoices",   PurchaseInvoicesPipeline),
    ("Purchase Orders",     PurchaseOrdersPipeline),
    ("GRN / QIR",           GRNQIRPipeline),
    ("Process Details",     ProcessDetailsPipeline),
]

print(f"\n🚀  Smoke test: {FROM} → {TODAY}\n")
total = 0
for label, PipelineCls in PIPELINES:
    try:
        rows = PipelineCls().run(FROM, TODAY)
        print(f"  ✅  {label:<25} {rows:>5} rows upserted")
        total += rows or 0
    except Exception as exc:
        print(f"  ❌  {label:<25} FAILED: {exc}")

print(f"\n  Total rows upserted: {total}\n")
