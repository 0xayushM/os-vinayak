"""
api/main.py
────────────
FastAPI application entry point for Vinayak Brain OS.

Starts the APScheduler (pipelines run inside this process — no separate worker).
Exposes all dashboard and AI endpoints.

Run locally:
    uvicorn vinayak.api.main:app --reload --port 8000

Deploy (production):
    uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vinayak.pipelines.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on startup; stop cleanly on shutdown."""
    logger.info("Starting APScheduler...")
    start_scheduler()
    yield
    logger.info("Stopping APScheduler...")
    stop_scheduler()


app = FastAPI(
    title="Vinayak Brain OS",
    description="TranzAct dashboard API — KBrushes",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: only allow requests from the Next.js BFF (Vercel URL or local dev).
# The browser NEVER talks to FastAPI directly — all calls go through /api/* on
# the Next.js host, so the wildcard here is safe in dev but lock it to the
# production Vercel URL before shipping.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    os.getenv("NEXT_PUBLIC_APP_URL", ""),
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_credentials=True,          # needed for httpOnly cookie flow
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Global exception handler — ensures all errors return JSON, not plain text ──
@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# ── Register routers ──────────────────────────────────────────────────────────
from vinayak.api.routes import auth, connections, dashboard, ai_tool  # noqa: E402

app.include_router(auth.router,        prefix="/auth",        tags=["Auth"])
app.include_router(connections.router, prefix="/connections",  tags=["Connections"])
app.include_router(dashboard.router,   prefix="/dashboard",    tags=["Dashboard"])
app.include_router(ai_tool.router,     prefix="/ai",           tags=["AI"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "Vinayak Brain OS"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
