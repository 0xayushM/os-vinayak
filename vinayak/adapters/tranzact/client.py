"""
adapters/tranzact/client.py
────────────────────────────
Single public function: fetch_report()

Handles:
  • Attaches Bearer token via auth.get_access_token()
  • Pagination loop — fetches all pages until exhausted
  • Exponential backoff on 429 / 5xx responses
  • 401 → force token refresh → one retry before raising
  • Rate limiting: enforces TRANZACT_REQUESTS_PER_MINUTE (default 8/min)

Confirmed endpoint (2026-05-22):
  POST https://reporting.letstranzact.com/generate_report
  Response: {"success": true, "data": {"results": [...], "total_items": N, ...}}
  Login:    POST https://be.letstranzact.com/main/login/password-login/
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from vinayak.adapters.tranzact.auth import get_access_token
from vinayak.config import (
    DEFAULT_COMPANY_ID,
    TRANZACT_BASE_URL,
    TRANZACT_REPORTING_URL,
    TRANZACT_EMAIL,
    TRANZACT_PASSWORD,
    TRANZACT_REQUESTS_PER_MINUTE,
)

logger = logging.getLogger(__name__)

# ── Rate limiter (module-level state) ────────────────────────────────────────

_MIN_INTERVAL: float = 60.0 / TRANZACT_REQUESTS_PER_MINUTE  # seconds between calls
_last_request_at: float = 0.0


def _throttle() -> None:
    """Block until at least _MIN_INTERVAL seconds have passed since last request."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = _MIN_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


# ── Response shape helpers (confirmed 2026-05-22) ────────────────────────────
# Response: {"success": true, "data": {"results": [...], "total_items": N, ...}}

def _get_rows(body: dict) -> list[dict]:
    """Extract the list of data rows from a /generate_report response."""
    data = body.get("data", {})
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return results
    # Legacy fallbacks
    if isinstance(data, list):
        return data
    return []


def _get_total_pages(body: dict, per_page: int) -> int:
    """Compute total pages from total_items / per_page."""
    import math
    data = body.get("data", {})
    total_items = 0
    if isinstance(data, dict):
        total_items = int(data.get("total_items", 0))
    if total_items <= 0:
        return 1
    return math.ceil(total_items / per_page)


# ── Core request function ─────────────────────────────────────────────────────

def _post_with_retry(
    session: requests.Session,
    payload: dict,
    max_retries: int = 3,
) -> dict:
    """
    POST to /generate_report with Bearer token, backoff on errors.
    Returns the parsed JSON body.
    Raises RuntimeError after exhausting retries.
    """
    for attempt in range(max_retries):
        _throttle()
        token = get_access_token(
            base_url=TRANZACT_BASE_URL,
            email=TRANZACT_EMAIL,
            password=TRANZACT_PASSWORD,
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            resp = session.post(
                f"{TRANZACT_REPORTING_URL}/generate_report",
                headers=headers,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.warning("fetch_report: network error (attempt %d): %s", attempt + 1, exc)
            time.sleep(2 ** attempt * 3)
            continue

        if resp.status_code == 401:
            logger.warning("fetch_report: 401 — forcing token refresh (attempt %d)", attempt + 1)
            token = get_access_token(
                base_url=TRANZACT_BASE_URL,
                email=TRANZACT_EMAIL,
                password=TRANZACT_PASSWORD,
                force_refresh=True,
            )
            continue  # retry immediately after forced refresh

        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2 ** attempt * 5  # 5 s, 10 s, 20 s
            logger.warning(
                "fetch_report: HTTP %d — backing off %ds (attempt %d)",
                resp.status_code, wait, attempt + 1,
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError(
        f"fetch_report failed after {max_retries} attempts for payload {payload}"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_report(
    report_id: str,
    filters: dict | None = None,
    per_page: int = 50,
) -> list[dict]:
    """
    Fetch ALL rows of a TranzAct report across all pages.

    Args:
        report_id:  String report ID (e.g. "29" for Sales Invoice Register)
        filters:    Dict merged into the request payload (date ranges, etc.)
        per_page:   Rows per page. TranzAct default is 50; reduce if timeouts occur.

    Returns:
        Flat list of row dicts — all pages concatenated.

    Usage:
        rows = fetch_report("29", {"filters": {"from_date": "2026-01-01",
                                               "to_date":   "2026-01-31"}})
    """
    all_rows: list[dict] = []
    page = 1

    with requests.Session() as session:
        while True:
            payload: dict[str, Any] = {
                "report": {"id": report_id},
                "pagination": {"page": page, "per_page": per_page},
            }
            if DEFAULT_COMPANY_ID:
                payload["company_id"] = DEFAULT_COMPANY_ID
            if filters:
                payload.update(filters)

            logger.debug(
                "fetch_report: report_id=%s page=%d per_page=%d",
                report_id, page, per_page,
            )

            body = _post_with_retry(session, payload)
            rows = _get_rows(body)
            all_rows.extend(rows)

            total_pages = _get_total_pages(body, per_page)
            logger.debug(
                "fetch_report: got %d rows (page %d/%d)",
                len(rows), page, total_pages,
            )

            if page >= total_pages or not rows:
                break
            page += 1

    logger.info(
        "fetch_report: report_id=%s total rows=%d", report_id, len(all_rows)
    )
    return all_rows
