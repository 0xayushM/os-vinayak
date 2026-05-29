"""
api/routes/ai_tool.py
──────────────────────
Phase 2 AI query endpoint.

Sandboxed TranzAct access for the AI layer:
  • Only whitelisted report IDs (10 cached + report 5)
  • Always returns aggregated data — raw rows never returned
  • Never calls CREATE/UPDATE endpoints
  • Every response includes citations (table name + fetched_at)

This endpoint is built in Week 4 but stubbed here so the router
can be registered without import errors during Phase 1–3.
"""
from __future__ import annotations

from typing import Optional

import psycopg2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vinayak.adapters.tranzact.reports import AI_WHITELIST
from vinayak.config import DATABASE_URL
from vinayak.schema import queries

router = APIRouter()


class AIQueryRequest(BaseModel):
    """Request body for the AI query endpoint."""
    query: str                          # Natural language question
    context_hints: Optional[list[str]] = None  # Pipeline names to pre-load


class AIQueryResponse(BaseModel):
    answer: str
    citations: list[dict]
    stale_data: bool


@router.post("/query", response_model=AIQueryResponse)
def ai_query(req: AIQueryRequest):
    """
    Phase 2 AI endpoint — answers natural-language questions about KBrushes data.

    The AI receives pre-aggregated data from queries.py, never raw rows.
    Every response includes citations showing which tables and sync timestamps
    were used to generate the answer.

    ⚠️  Full implementation in Week 4. This stub returns a placeholder.
    """
    # ── Phase 1–3 stub ───────────────────────────────────────────────────────
    return AIQueryResponse(
        answer=(
            "AI layer is not yet activated. "
            "This endpoint will be fully implemented in Week 4 (Phase 4). "
            "The dashboard is fully functional — use the panel endpoints instead."
        ),
        citations=[],
        stale_data=False,
    )

    # ── Week 4 implementation outline (uncomment and complete) ───────────────
    # conn = psycopg2.connect(DATABASE_URL)
    # try:
    #     # 1. Load context based on query intent (or all panels)
    #     context = {
    #         "ar": queries.get_ar_summary(conn),
    #         "revenue": queries.get_revenue_summary(conn),
    #         "inventory": queries.get_inventory_summary(conn),
    #         "production": queries.get_production_summary(conn),
    #         "orders": queries.get_order_book_summary(conn),
    #     }
    #
    #     # 2. Build citations from last_synced_at in each context block
    #     citations = [...]
    #
    #     # 3. Call Anthropic SDK with pre-aggregated context
    #     import anthropic
    #     client = anthropic.Anthropic()
    #     response = client.messages.create(
    #         model="claude-opus-4-6",
    #         max_tokens=1024,
    #         system=SYSTEM_PROMPT,
    #         messages=[{"role": "user", "content": f"Context: {context}\n\nQuestion: {req.query}"}]
    #     )
    #     answer = response.content[0].text
    #
    #     stale = any(c.get("stale") for c in context.values())
    #     return AIQueryResponse(answer=answer, citations=citations, stale_data=stale)
    # finally:
    #     conn.close()


SYSTEM_PROMPT = """
You are Vinayak, the business intelligence assistant for KBrushes.
You receive pre-aggregated data from the KBrushes database and answer
questions about the business concisely and accurately.

Rules:
1. Always base your answer on the provided context data — never use prior knowledge
   about KBrushes specifically.
2. Every response must reference which data source (table) you used.
3. If any data is marked stale (older than 25 hours), say so before answering.
4. Keep answers to 2-3 sentences unless a list is explicitly needed.
5. Format currency values in Indian notation (₹ X.XX L or ₹ X.XX Cr).
6. Do not expose technical field names like 'raw_id' or 'tz_ar_aging' to the user.
"""
