"""
pipelines/helpers.py
─────────────────────
Shared utilities for all TranzAct pipeline RowSchemas.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional


def epoch_to_date(v: Any) -> Optional[date]:
    """
    Coerce a value to a Python date.

    Handles:
      - None / empty string → None
      - date instance        → pass through
      - int/float > 1e12     → epoch milliseconds (TranzAct default)
      - int/float > 1e9      → epoch seconds
      - "DD/MM/YYYY" string  → parse with day-first
      - "YYYY-MM-DD" string  → ISO parse (first 10 chars)
    """
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, (int, float)):
        if v > 1_000_000_000_000:
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).date()
        if v > 1_000_000_000:
            return datetime.fromtimestamp(float(v), tz=timezone.utc).date()
    try:
        s = str(v).strip()
        if len(s) == 10 and s[2] == "/" and s[5] == "/":
            d, m, y = s.split("/")
            return date(int(y), int(m), int(d))
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None
