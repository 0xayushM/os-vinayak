"""
api/routes/connections.py
──────────────────────────
ERP tool connection management.

Endpoints:
  GET  /connections/              — list all tool connections for this company
  POST /connections/tranzact      — save TranzAct credentials (encrypted)
  POST /connections/tranzact/test — test connectivity with stored credentials
  DELETE /connections/{tool_name} — remove a connection

Credential storage:
  Credentials are AES-256 encrypted via Fernet before writing to DB.
  The encryption key lives in FERNET_KEY env var (32-byte URL-safe base64).
  Bearer tokens are NEVER persisted — they live only in the in-memory cache
  in adapters/tranzact/auth.py.

Multi-ERP design:
  The tool_connections table has a `source` column (e.g., 'tranzact', 'tally').
  Adding a new ERP = new row in tool_connections + new adapter module.
  No schema migration needed.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, timedelta
from typing import Optional

import psycopg2
import psycopg2.errors
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL
from vinayak.api.routes.auth import get_current_user, TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Full-sync orchestration (initial data pull after connecting) ──────────────
# A single background worker runs all 10 pipelines once, in rate-limit-safe
# order. State is process-local; the frontend polls /dashboard/sync/health to
# render progress.
_sync_lock = threading.Lock()
_sync_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "total": 0,
    "completed": 0,
    "current": None,
    "pipelines": [],   # [{"key", "label", "status", "rows", "error"}]
}


def _full_sync_plan():
    """(PipelineClass, from_days_back, key, label) for every pipeline, ordered
    fast→slow so operational panels light up first."""
    from vinayak.pipelines.ar_aging import ARAgingPipeline
    from vinayak.pipelines.sales_orders import SalesOrdersPipeline
    from vinayak.pipelines.purchase_orders import PurchaseOrdersPipeline
    from vinayak.pipelines.inventory_valuation import InventoryValuationPipeline
    from vinayak.pipelines.process_details import ProcessDetailsPipeline
    from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
    from vinayak.pipelines.purchase_invoices import PurchaseInvoicesPipeline
    from vinayak.pipelines.grn_qir import GRNQIRPipeline
    from vinayak.pipelines.sales_quotations import SalesQuotationsPipeline
    from vinayak.pipelines.process_routing import ProcessRoutingPipeline

    return [
        (ARAgingPipeline, 1, "ar_aging", "AR Aging"),
        (SalesOrdersPipeline, 7, "sales_orders", "Sales Orders"),
        (PurchaseOrdersPipeline, 7, "purchase_orders", "Purchase Orders"),
        (InventoryValuationPipeline, 1, "inventory_valuation", "Inventory Valuation"),
        (ProcessDetailsPipeline, 7, "process_details", "Production Details"),
        (SalesInvoicesPipeline, 30, "sales_invoices", "Sales Invoices"),
        (PurchaseInvoicesPipeline, 30, "purchase_invoices", "Purchase Invoices"),
        (GRNQIRPipeline, 30, "grn_qir", "GRN / Quality"),
        (SalesQuotationsPipeline, 30, "sales_quotations", "Sales Quotations"),
        (ProcessRoutingPipeline, 30, "process_routing", "Process Routing"),
    ]


def _run_full_sync(email: str, password: str) -> None:
    """Prime the token cache with the user's stored credentials, then run
    every pipeline once. Per-pipeline failures are logged (recorded in
    tz_sync_runs by BasePipeline) but never abort the whole run."""
    global _sync_state
    import datetime as _dt
    plan = _full_sync_plan()

    # Seed the per-pipeline checklist up front so the UI can render all rows.
    with _sync_lock:
        _sync_state["total"] = len(plan)
        _sync_state["completed"] = 0
        _sync_state["current"] = None
        _sync_state["pipelines"] = [
            {"key": key, "label": label, "status": "pending", "rows": None, "error": None}
            for _, _, key, label in plan
        ]

    def _set(key, **fields):
        with _sync_lock:
            for p in _sync_state["pipelines"]:
                if p["key"] == key:
                    p.update(fields)
                    break

    try:
        # Prime the in-memory token cache using the credentials the user just
        # connected with, so the whole sync is driven by THEIR account.
        from vinayak.adapters.tranzact.auth import get_access_token
        get_access_token(
            base_url=TRANZACT_BASE_URL,
            email=email,
            password=password,
            force_refresh=True,
        )
        today = date.today()
        for PipelineCls, days_back, key, _label in plan:
            with _sync_lock:
                _sync_state["current"] = key
            _set(key, status="running")
            try:
                rows = PipelineCls().run(today - timedelta(days=days_back), today)
                _set(key, status="success", rows=rows)
            except Exception as exc:  # noqa: BLE001
                logger.error("Full sync: %s failed: %s", PipelineCls.__name__, exc)
                _set(key, status="failed", error=str(exc))
            finally:
                with _sync_lock:
                    _sync_state["completed"] += 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Full sync aborted: %s", exc)
        with _sync_lock:
            _sync_state["error"] = str(exc)
    finally:
        with _sync_lock:
            _sync_state["running"] = False
            _sync_state["current"] = None
            _sync_state["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

# ── Fernet encryption ─────────────────────────────────────────────────────────
_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    key = os.environ.get("FERNET_KEY", "")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FERNET_KEY not configured — cannot store credentials",
        )
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode())
        return _fernet
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fernet init failed: {exc}",
        )


def _encrypt(data: dict) -> str:
    f = _get_fernet()
    return f.encrypt(json.dumps(data).encode()).decode()


def _decrypt(blob: str) -> dict:
    f = _get_fernet()
    return json.loads(f.decrypt(blob.encode()).decode())


# ── DB helper ─────────────────────────────────────────────────────────────────
def _conn():
    return psycopg2.connect(DATABASE_URL)


def _raise_if_schema_missing(exc: Exception) -> None:
    """Convert UndefinedTable → a readable 503 with setup instructions."""
    msg = str(exc)
    if "UndefinedTable" in type(exc).__name__ or "does not exist" in msg:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Database schema not initialised. "
                "Run: python -m vinayak.scripts.setup_db"
            ),
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Database error: {exc}",
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class TranzActCredentials(BaseModel):
    email: str
    password: str


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/", summary="List all tool connections for this company")
def list_connections(user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tool_name, connection_method, is_active,
                       last_verified_at, created_at
                FROM tool_connections
                WHERE company_id = %s
                ORDER BY created_at
                """,
                (user.company_id,),
            )
            rows = cur.fetchall()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    return {
        "connections": [
            {
                "tool_name":        r[0],
                "connection_method": r[1],
                "is_active":        r[2],
                "last_verified_at": r[3].isoformat() if r[3] else None,
                "created_at":       r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]
    }


@router.post("/tranzact", summary="Save TranzAct credentials (encrypted)")
def save_tranzact(
    creds: TranzActCredentials,
    user: TokenPayload = Depends(get_current_user),
):
    """
    Encrypts email+password and upserts into tool_connections.
    The encryption key (FERNET_KEY) never leaves the server.
    Bearer tokens are NOT stored here — they're fetched on demand.
    """
    encrypted = _encrypt({"email": creds.email, "password": creds.password})

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tool_connections
                    (company_id, tool_name, connection_method, encrypted_credentials, is_active)
                VALUES (%s, 'tranzact', 'cloud_pull', %s, TRUE)
                ON CONFLICT (company_id, tool_name)
                DO UPDATE SET
                    encrypted_credentials = EXCLUDED.encrypted_credentials,
                    is_active             = TRUE,
                    updated_at            = NOW()
                """,
                (user.company_id, encrypted),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    logger.info("Saved TranzAct credentials for company %s", user.company_id)
    return {"status": "ok", "tool_name": "tranzact", "message": "Credentials saved"}


@router.post("/tranzact/test", summary="Test TranzAct auth with stored credentials")
def test_tranzact(user: TokenPayload = Depends(get_current_user)):
    """
    Decrypts stored credentials and attempts a TranzAct login.
    Returns ok=True if the bearer token was obtained successfully.
    Does NOT expose the token — only confirms connectivity.
    """
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT encrypted_credentials FROM tool_connections
                WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE
                """,
                (user.company_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )

    creds = _decrypt(row[0])

    try:
        from vinayak.adapters.tranzact.auth import get_access_token
        token = get_access_token(
            base_url=TRANZACT_BASE_URL,
            email=creds["email"],
            password=creds["password"],
            force_refresh=True,
        )
        # Update last_verified_at
        db = _conn()
        try:
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE tool_connections
                       SET last_verified_at = NOW()
                       WHERE company_id = %s AND tool_name = 'tranzact'""",
                    (user.company_id,),
                )
            db.commit()
        finally:
            db.close()

        # Return only the first 12 chars of the token as proof — never the full token
        return {
            "ok": True,
            "tool_name": "tranzact",
            "token_preview": token[:12] + "...",
            "message": "Authentication successful",
        }
    except Exception as exc:
        logger.warning("TranzAct test failed for %s: %s", user.company_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TranzAct authentication failed: {exc}",
        )


@router.post("/tranzact/sync", summary="Run the initial full data sync (all pipelines)")
def trigger_full_sync(user: TokenPayload = Depends(get_current_user)):
    """
    Kick off a one-time pull of all 10 TranzAct reports into the cache tables,
    using the stored (encrypted) credentials. Runs in a background thread and
    returns immediately — poll GET /dashboard/sync/health for progress.
    """
    global _sync_state
    with _sync_lock:
        if _sync_state["running"]:
            return {"status": "already_running", "started_at": _sync_state["started_at"]}

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT encrypted_credentials FROM tool_connections
                WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE
                """,
                (user.company_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )

    creds = _decrypt(row[0])

    import datetime as _dt
    with _sync_lock:
        _sync_state.update(
            running=True,
            started_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            finished_at=None,
            error=None,
        )

    threading.Thread(
        target=_run_full_sync,
        args=(creds["email"], creds["password"]),
        daemon=True,
    ).start()

    logger.info("Full sync started for company %s", user.company_id)
    return {"status": "started", "pipeline_count": 10}


@router.get("/tranzact/sync", summary="Full-sync progress state")
def full_sync_status(user: TokenPayload = Depends(get_current_user)):
    with _sync_lock:
        return dict(_sync_state)


@router.delete("/{tool_name}", summary="Remove a tool connection")
def delete_connection(
    tool_name: str,
    user: TokenPayload = Depends(get_current_user),
):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tool_connections
                   SET is_active = FALSE, updated_at = NOW()
                   WHERE company_id = %s AND tool_name = %s""",
                (user.company_id, tool_name),
            )
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active connection found for tool '{tool_name}'",
        )

    return {"status": "ok", "tool_name": tool_name, "message": "Connection removed"}
