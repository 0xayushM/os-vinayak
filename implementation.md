# Vinayak Brain OS — Implementation & Run Guide

A phase-by-phase guide to set up, run, and verify the TranzAct dashboard.

The system has two processes that run side by side:

- **`apps/web`** — Next.js app (UI + BFF proxy routes). The browser only ever talks to this.
- **`vinayak/`** — Python/FastAPI backend (auth, connections, pipelines, dashboard queries). Private; reached only through the Next.js BFF.

Data path: **Browser → Next.js `/api/*` (BFF) → FastAPI → Supabase Postgres / TranzAct**. The FastAPI URL and the TranzAct token never reach the browser.

---

## Phase 0 — Prerequisites

- Node.js ≥ 20 and pnpm 9.15.0 (`corepack use pnpm@9.15.0` or `npm i -g pnpm@9.15.0`)
- Python ≥ 3.11
- A Supabase project (free tier is fine) — you need its **direct** connection string (port 5432)
- TranzAct login credentials for KBrushes

---

## Phase 1 — Environment configuration

There are **two** env files: one for the FastAPI backend (repo root) and one for the Next.js app (`apps/web`). Keep them separate — the Next app roots at `apps/web/`, so it does **not** read the root `.env`.

### 1a. Backend — repo root `.env`

`vinayak/config.py` loads this via `load_dotenv()`. `TRANZACT_EMAIL`, `TRANZACT_PASSWORD`, and `DATABASE_URL` are **required** (the process won't start without them).

```dotenv
# TranzAct (the ERP account you connect through the UI)
TRANZACT_EMAIL=your@email.com
TRANZACT_PASSWORD=your_password
TRANZACT_BASE_URL=https://be.letstranzact.com
TRANZACT_REPORTING_URL=https://reporting.letstranzact.com
TRANZACT_REQUESTS_PER_MINUTE=8

# Supabase Postgres (direct connection, port 5432 — NOT the pooler)
DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres

# Platform login ("Vinayak ID") — what the user types on the /login screen
ADMIN_EMAIL=admin@vinayak.com
ADMIN_PASSWORD=choose-a-strong-password
DEFAULT_COMPANY_ID=vinayak

# Secrets
JWT_SECRET=$(openssl rand -hex 32)
INTERNAL_API_KEY=$(openssl rand -hex 32)
FERNET_KEY=   # see command below
```

Generate the Fernet key (used to AES-256-encrypt stored TranzAct credentials):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 1b. Frontend — `apps/web/.env.local`

The BFF routes need to reach FastAPI and authenticate with the same internal key:

```dotenv
FASTAPI_INTERNAL_URL=http://localhost:8000
INTERNAL_API_KEY=   # must match the value in the root .env
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

> The `INTERNAL_API_KEY` must be identical in both files — FastAPI rejects any BFF call whose `X-Internal-Key` header doesn't match.

---

## Phase 2 — Backend (FastAPI) setup

```bash
# from repo root
python -m venv vinayak/.venv
source vinayak/.venv/bin/activate           # Windows: vinayak\.venv\Scripts\activate
pip install -r vinayak/requirements.txt     # fastapi, uvicorn, psycopg2-binary,
                                             # apscheduler, requests, python-jose,
                                             # cryptography, pydantic, python-dotenv
```

Initialise the database schema (creates `tool_connections`, the `tz_*` cache tables, and `tz_sync_runs`):

```bash
python -m vinayak.scripts.setup_db
```

Sanity-check TranzAct auth in isolation before running the full app:

```bash
python -m vinayak.scripts.test_login
```

Start the API (this also starts the APScheduler that runs pipelines on a cron):

```bash
uvicorn vinayak.api.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` → `{"status":"ok"}`.

---

## Phase 3 — Frontend (Next.js monorepo) setup

```bash
# from repo root — installs all workspaces (apps/* + packages/*)
pnpm install

# run the web app (this is `pnpm --filter @vinayak/web dev`)
pnpm dev
```

The app starts on `http://localhost:3000`. Useful root scripts: `pnpm build`, `pnpm start`, `pnpm lint`, `pnpm typecheck`.

---

## Phase 4 — The user flow (what happens at runtime)

This is the flow the app now implements:

1. **Log in with the Vinayak ID.** Visiting any page redirects to `/login`. The user enters `ADMIN_EMAIL` / `ADMIN_PASSWORD`; FastAPI issues an httpOnly JWT cookie (`vb_access_token`) and the app lands on `/dashboard`.

2. **Connect TranzAct first.** The dashboard is wrapped in an `OnboardingGate`. On load it calls `/api/connections/` — if there's no active, verified TranzAct connection it shows the **Connect TranzAct** card instead of empty panels.

3. **Enter credentials → test → sync (one button).** "Connect & Sync" runs three steps in sequence:
   - `POST /api/connections/tranzact` — credentials are AES-256 encrypted and stored.
   - `POST /api/connections/tranzact/test` — logs in to TranzAct to confirm the credentials work (token is never returned).
   - `POST /api/connections/tranzact/sync` — kicks off a background pull of **all 10 reports** into the cache tables, priming the token cache with the credentials the user just entered.

4. **Data lands → dashboard renders.** The card polls `/api/dashboard/sync-health` and shows "N/10 reports loaded". Once data has landed the gate flips to "connected" and the 18-panel overview renders. Thereafter APScheduler keeps the data fresh (operational panels hourly, strategic panels daily at 03:00 IST).

You can re-test or re-sync any time from **Settings & Connections** (same component, compact mode). **Sync Health** shows the last 25 pipeline runs.

---

## Phase 5 — Verification checklist

- [ ] `GET /health` returns ok and the uvicorn log shows "Scheduler started — N jobs registered".
- [ ] Login with the Vinayak ID succeeds and sets the `vb_access_token` cookie.
- [ ] A fresh login (no connection yet) shows the **Connect TranzAct** card, not empty panels.
- [ ] "Connect & Sync" reports success and the health poll counts reports up to 10.
- [ ] Dashboard panels populate; **Sync Health** lists `success` runs for all pipelines.
- [ ] Browser network tab shows only `/api/*` calls — never `localhost:8000` or a TranzAct URL.

---

## Phase 6 — Cleanup (run once)

The old browser-direct "explorer" path is no longer wired in. Remove it:

```bash
bash scripts/cleanup-dead-code.sh
```

This drops `explorer.tsx`, the `/api/tranzact/{login,report}` routes, `lib/tranzact/auth.ts`, and the now-unused `NoConnectionBanner.tsx`, and untracks any committed `__pycache__`.

---

## Phase 7 — Later (optional)

- **Docker + Postgres** to replace Supabase: add a `docker-compose.yml` with a `postgres:16` service and point `DATABASE_URL` at it; everything else is unchanged.
- **Multi-ERP**: the `tool_connections.source` column and the adapter pattern mean a new ERP is "new row + new adapter module" — no schema migration. Tally Prime and Busy are stubbed in Settings.
- **Multi-tenant auth**: `auth.py` currently validates one admin credential from env (Phase 1, single-tenant). Replace `login()` with a users-table lookup + bcrypt for Phase 2.
- **Shared types**: `packages/shared` exports the `ApiEnvelope<T>` shape; the BFF and panels can import from `@vinayak/shared` to stay in sync with the API.

---

## Known notes

- `config.py` reads `TRANZACT_EMAIL`/`TRANZACT_PASSWORD` from env and treats them as required. In this single-tenant build they are the same KBrushes account the user connects through the UI; the full-sync endpoint primes the token cache with the **stored** credentials so the sync is genuinely driven by what the user entered.
- Three panels (`quote-summary`, `bom-coverage`, `grn-summary`) are served as zero-value stubs by the BFF until their FastAPI queries are implemented.
- The TranzAct 10 req/min/machine limit is respected by throttling to 8/min; a full initial sync of all reports therefore takes a few minutes.
