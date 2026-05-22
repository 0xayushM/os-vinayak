"""
adapters/tranzact/reports.py
─────────────────────────────
Canonical map of TranzAct report IDs → human names.
Used by every pipeline, sync logging, and the Phase 2 AI whitelist.

⚠️  Do not change report IDs after the schema lock (end of Week 1).
    These IDs are the foreign key between TranzAct and our Postgres tables.
"""

# ── Report ID registry ───────────────────────────────────────────────────────

REPORT_IDS: dict[str, str] = {
    "sales_invoices":       "29",
    "ar_aging":             "102",
    "sales_orders":         "2",
    "purchase_invoices":    "77",
    "purchase_orders":      "3",
    "grn_qir":              "34",
    "sales_quotations":     "8",
    "inventory_valuation":  "9",
    "process_routing":      "86",
    "process_details":      "25",
}

# Reverse map: report_id string → pipeline name
REPORT_ID_TO_NAME: dict[str, str] = {v: k for k, v in REPORT_IDS.items()}

# ── AI tool whitelist ────────────────────────────────────────────────────────
# Phase 2: the AI endpoint may only call these report IDs.
# Report "5" is the stock ledger — added for ad-hoc AI queries.
AI_WHITELIST: set[str] = set(REPORT_IDS.values()) | {"5"}

# ── Sync cadence metadata ────────────────────────────────────────────────────
PIPELINE_CADENCE: dict[str, str] = {
    "sales_invoices":       "daily",
    "ar_aging":             "hourly",
    "sales_orders":         "hourly",
    "purchase_invoices":    "daily",
    "purchase_orders":      "hourly",
    "grn_qir":              "daily",
    "sales_quotations":     "daily",
    "inventory_valuation":  "hourly",
    "process_routing":      "daily",
    "process_details":      "hourly",
}

# ── Date-window helpers ──────────────────────────────────────────────────────
# Returns the date-filter dict to pass to fetch_report().
# ⚠️  Update filter key names after the Day 1 API handshake test
#     to match what TranzAct actually accepts.

def get_filters(pipeline_name: str, from_date: str, to_date: str) -> dict:
    """
    Return the filters payload for a given pipeline.

    Args:
        pipeline_name: key from REPORT_IDS
        from_date:     ISO date string, e.g. "2026-01-01"
        to_date:       ISO date string, e.g. "2026-01-31"

    Returns:
        dict to merge into the fetch_report() `filters` argument.
    """
    if pipeline_name == "inventory_valuation":
        # Inventory report typically has no date range — fetches current stock.
        # Confirm on Day 1 whether TranzAct accepts date filters here.
        return {}

    return {
        "filters": {
            "from_date": from_date,
            "to_date":   to_date,
        }
    }
