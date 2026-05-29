"""
scripts/test_api.py — Day 1 TranzAct API Handshake Test
─────────────────────────────────────────────────────────
Run ONCE before writing any pipeline code to:
  1. Confirm login works and tokens are returned
  2. Pull page 1 of report 29 (Sales Invoice Register)
  3. Document the actual response shape (pagination keys, column names)
  4. Save a sample response to report_29_sample.json for reference

Usage:
    cd /path/to/os-vinayak
    python -m vinayak.scripts.test_api

Prerequisites:
    • .env file with TRANZACT_EMAIL, TRANZACT_PASSWORD, TRANZACT_BASE_URL
    • pip install -r kbrushes/requirements.txt

⚠️  After running, update client.py's _get_rows() and _get_total_pages()
    to match the actual response structure shown here.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Allow running from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv()

BASE_URL      = os.environ.get("TRANZACT_BASE_URL",      "https://be.letstranzact.com")
REPORTING_URL = os.environ.get("TRANZACT_REPORTING_URL", "https://reporting.letstranzact.com")
EMAIL         = os.environ["TRANZACT_EMAIL"]
PASSWORD      = os.environ["TRANZACT_PASSWORD"]
COMPANY_ID    = os.environ.get("DEFAULT_COMPANY_ID", "")

DIVIDER = "─" * 60


def banner(title: str) -> None:
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}")


def step_login() -> tuple[str, str]:
    banner("STEP 1 — Login")
    url = f"{BASE_URL}/main/login/password-login/"
    payload = {"email": EMAIL, "password": PASSWORD}
    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload)}")
    r = requests.post(url, json=payload, timeout=30)
    print(f"Status: {r.status_code}")

    if r.status_code != 200:
        print("BODY:", r.text[:500])
        raise SystemExit("❌  Login failed — check credentials in .env")

    body = r.json()
    print("Response keys:", list(body.keys()))

    # Based on API documentation: {"status": 1, "data": {"refresh_token": "...", "access_token": "..."}}
    if body.get("status") != 1:
        print("Full response:", json.dumps(body, indent=2)[:1000])
        raise SystemExit("❌  API returned non-success status")

    data = body.get("data", {})
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if not access_token:
        print("Full response:", json.dumps(body, indent=2)[:1000])
        raise SystemExit("❌  Could not find access_token in response")

    print(f"✅  access_token  : {access_token[:40]}...")
    print(f"✅  refresh_token : {refresh_token[:40] if refresh_token else 'NOT FOUND'}...")
    return access_token, refresh_token or ""


def step_fetch_report(access_token: str) -> dict:
    banner("STEP 2 — Fetch Report 29 (Sales Invoice Register), Page 1")
    # Confirmed endpoint: https://reporting.letstranzact.com/generate_report
    url = f"{REPORTING_URL}/generate_report"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload: dict = {
        "report": {"id": "29"},
        "pagination": {"page": 1, "per_page": 10},
    }
    if COMPANY_ID:
        payload["company_id"] = COMPANY_ID

    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    print(f"Status: {r.status_code}")

    if r.status_code != 200:
        print(f"BODY: {r.text[:500]}")
        raise SystemExit("❌  Fetch failed — check credentials and reporting URL")

    body = r.json()
    print(f"✅  Got response! success={body.get('success')}")
    return body


def step_document_shape(body: dict) -> None:
    banner("STEP 3 — Document Response Shape")

    print("\nTop-level keys:", list(body.keys()))
    print(f"success: {body.get('success')}")
    print(f"report_generated_at: {body.get('report_generated_at')}")

    data = body.get("data", {})
    if not isinstance(data, dict):
        print("⚠️  data is not a dict:", type(data))
        return

    print(f"\ndata keys: {list(data.keys())}")
    print(f"total_items: {data.get('total_items')}")

    rows = data.get("results", [])
    print(f"\n✅  Rows at data['results']: {len(rows)} rows on this page")

    if rows:
        print(f"\nColumn names on first row ({len(rows[0])} columns):")
        for col, val in list(rows[0].items())[:30]:
            print(f"  {col!r}: {val!r}")
        if len(rows[0]) > 30:
            print(f"  ... and {len(rows[0]) - 30} more columns")

    import math
    total_items = int(data.get("total_items", 0))
    per_page = 10
    total_pages = math.ceil(total_items / per_page) if total_items else 1
    print(f"\nPagination: {total_items} total items → {total_pages} pages at {per_page}/page")


def step_save_sample(body: dict) -> None:
    banner("STEP 4 — Save Sample Response")
    out_path = Path("report_29_sample.json")
    out_path.write_text(json.dumps(body, indent=2, default=str))
    print(f"✅  Saved to {out_path.absolute()}")
    print("   Review this file and update client.py accordingly.")


def step_test_refresh(access_token: str, refresh_token: str) -> None:
    banner("STEP 5 — Test Token Refresh (optional)")
    if not refresh_token:
        print("⚠️  No refresh_token found — skipping refresh test")
        return

    # Try common refresh endpoint paths
    for path in ["/main/login/token/refresh/", "/token/refresh/", "/auth/refresh/"]:
        url = f"{BASE_URL}{path}"
        r = requests.post(url, json={"refresh": refresh_token}, timeout=15)
        print(f"POST {url} → {r.status_code}")
        if r.status_code == 200:
            body = r.json()
            new_token = (body.get("access") or body.get("access_token")
                         or body.get("data", {}).get("access_token"))
            print(f"✅  Refresh works at {path}")
            print(f"   New access token: {(new_token or '')[:40]}...")
            print(f"\n⚠️  Update auth.py _do_refresh() to use path: {path}")
            return
        time.sleep(0.5)

    print("⚠️  Token refresh endpoint not found — full re-login will be used")
    print("   That is fine; update auth.py to remove the refresh attempt if needed.")


def main() -> None:
    print("\n🔍  Vinayak Brain OS — TranzAct API Handshake Test")
    print(f"    Base URL: {BASE_URL}")
    print(f"    Email:    {EMAIL}")
    print(f"    Company:  {COMPANY_ID or '(not set)'}")

    access_token, refresh_token = step_login()
    body = step_fetch_report(access_token)
    step_document_shape(body)
    step_save_sample(body)
    step_test_refresh(access_token, refresh_token)

    print(f"\n{DIVIDER}")
    print("  ✅  Day 1 handshake complete.")
    print("  Next steps:")
    print("  1. Open report_29_sample.json and note the exact column names")
    print("  2. Update client.py → _get_rows() and _get_total_pages()")
    print("  3. Update auth.py → _do_refresh() with the correct refresh URL")
    print("  4. Update reports.py → get_filters() with correct filter key names")
    print("  5. Update schema/init.sql column names to match actual field names")
    print(f"{DIVIDER}\n")


if __name__ == "__main__":
    main()
