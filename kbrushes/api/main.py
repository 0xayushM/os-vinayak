"""
api/main.py
────────────
FastAPI application entry point for Vinayak Brain OS.

Starts the APScheduler (pipelines run inside this process — no separate worker).
Exposes all dashboard and AI endpoints.

Run locally:
    uvicorn kbrushes.api.main:app --reload --port 8000

Deploy (Railway):
    uvicorn kbrushes.api.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kbrushes.pipelines.scheduler import start_scheduler, stop_scheduler

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

# Allow the dashboard HTML to call the API from any origin in dev.
# Tighten this to your production domain before shipping.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────────────────────────
from kbrushes.api.routes import dashboard, ai_tool  # noqa: E402

app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(ai_tool.router,   prefix="/ai",        tags=["AI"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "Vinayak Brain OS"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
