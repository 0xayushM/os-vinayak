"""
scripts/probe_fields.py
────────────────────────
Fetch 1 row from each of the 10 TranzAct reports and print every field name
with its sample value. Run this to capture real API field names so the
pipeline RowSchemas can be fixed.

Usage:
    cd /path/to/os-vinayak
    python -m vinayak.scripts.probe_fields 2>&1 | tee /tmp/tranzact_fields.txt
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv()

BASE_URL      = os.environ["TRANZACT_BASE_URL"]
REPORTING_URL = os.environ.get("TRANZACT_REPORTING_URL", "https://reporting.letstranzact.com")
EMAIL         = os.environ["TRANZACT_EMAIL"]
PASSWORD      = os.environ["TRANZACT_PASSWORD"]
COMPANY_ID    = os.environ.get("DEFAULT_COMPANY_ID", "")

REPORTS = [
    ("29",  "Sales Invoices",       True),
    ("102", "AR Aging",             True),
    ("2",   "Sales Orders",         True),
    ("77",  "Purchase Invoices",    True),
    ("3",   "Purchase Orders",      True),
    ("34",  "GRN / QIR",            True),
    ("8",   "Sales Quotations",     True),
    ("9",   "Inventory Valuation",  False),
    ("86",  "Process Routing",      False),
    ("25",  "Process Details",      True),
]


def login() -> str:
    url = f"{BASE_URL}/main/login/password-login/"
    r = requests.post(url, json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    body = r.json()
    data = body.get("data", {})
    tokens = data.get("tokens", data)
    token = (tokens.get("access_token") or tokens.get("access")
             or body.get("access_token") or body.get("access"))
    if not token:
        raise RuntimeError(f"No access_token in login response: {str(body)[:400]}")
    print(f"✅  Logged in as {EMAIL}")
    return token


def fetch_one_page(token: str, report_id: str, use_dates: bool) -> dict:
    url = f"{REPORTING_URL}/generate_report"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    today = date.today()
    payload: dict = {
        "report": {"id": report_id},
        "pagination": {"page": 1, "per_page": 3},
    }
    if COMPANY_ID:
        payload["company_id"] = COMPANY_ID
    if use_dates:
        payload["filters"] = {
            "from_date": str(today - timedelta(days=365)),
            "to_date": str(today),
        }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
    return r.json()


def print_fields(report_id: str, label: str, body: dict) -> None:
    print(f"\n{'='*70}")
    print(f"  Report {report_id}: {label}")
    print(f"{'='*70}")
    if "error" in body:
        print(f"  ERROR: {body['error']}")
        return
    data = body.get("data", {})
    rows = []
    if isinstance(data, dict):
        rows = data.get("results", [])
    elif isinstance(data, list):
        rows = data
    print(f"  total_items: {data.get('total_items', '?') if isinstance(data, dict) else '?'}")
    print(f"  rows on page: {len(rows)}")
    if not rows:
        print("  ⚠️  No rows returned — try expanding the date range or check company_id")
        # Print raw response for debugging
        print(f"  Raw response: {json.dumps(body, default=str)[:600]}")
        return
    row = rows[0]
    print(f"\n  Fields in first row ({len(row)} total):")
    for k, v in row.items():
        print(f"    {k!r:40s}: {repr(v)[:80]}")
    # Save full sample
    out = Path(f"/tmp/report_{report_id}_sample.json")
    out.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\n  💾  Full sample saved to {out}")


def main() -> None:
    print("🔍  TranzAct Field Probe — fetching 1 page from each report")
    token = login()
    for report_id, label, use_dates in REPORTS:
        time.sleep(8)  # ~7.5 req/min to stay under the 10/min limit
        try:
            body = fetch_one_page(token, report_id, use_dates)
            print_fields(report_id, label, body)
        except Exception as exc:
            print(f"\n  Report {report_id} FAILED: {exc}")


if __name__ == "__main__":
    main()
