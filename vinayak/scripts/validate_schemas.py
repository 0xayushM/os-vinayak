"""
scripts/validate_schemas.py
────────────────────────────
Load the saved sample JSON files from probe_fields.py and run them through
each pipeline's RowSchema to confirm zero validation errors before a full sync.

Usage:
    python -m vinayak.scripts.validate_schemas
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vinayak.pipelines.sales_invoices import SalesInvoiceRow
from vinayak.pipelines.ar_aging import ARAgingRow
from vinayak.pipelines.sales_orders import SalesOrderRow
from vinayak.pipelines.purchase_invoices import PurchaseInvoiceRow
from vinayak.pipelines.purchase_orders import PurchaseOrderRow
from vinayak.pipelines.grn_qir import GRNQIRRow
from vinayak.pipelines.inventory_valuation import InventoryValuationRow
from vinayak.pipelines.process_routing import ProcessRoutingRow
from vinayak.pipelines.process_details import ProcessDetailsRow

CHECKS = [
    ("29",  "Sales Invoices",      SalesInvoiceRow),
    ("102", "AR Aging",            ARAgingRow),
    ("2",   "Sales Orders",        SalesOrderRow),
    ("77",  "Purchase Invoices",   PurchaseInvoiceRow),
    ("3",   "Purchase Orders",     PurchaseOrderRow),
    ("34",  "GRN / QIR",           GRNQIRRow),
    ("9",   "Inventory Valuation", InventoryValuationRow),
    ("86",  "Process Routing",     ProcessRoutingRow),
    ("25",  "Process Details",     ProcessDetailsRow),
]

all_pass = True
for report_id, label, Schema in CHECKS:
    path = Path(f"/tmp/report_{report_id}_sample.json")
    if not path.exists():
        print(f"  ⚠️   {label}: sample file not found at {path}")
        continue

    rows = json.loads(path.read_text())
    ok, fail = 0, 0
    for row in rows:
        try:
            Schema(**row)
            ok += 1
        except Exception as exc:
            fail += 1
            if fail == 1:
                print(f"  ❌  {label} first error: {exc}")

    status = "✅" if fail == 0 else "❌"
    print(f"  {status}  Report {report_id} {label}: {ok} ok / {fail} failed  (out of {ok+fail})")
    if fail > 0:
        all_pass = False

print()
print("All schemas pass" if all_pass else "Some schemas have errors — check above")
