"""
api/routes/auth.py
───────────────────
Platform authentication routes for Vinayak Brain OS.

Endpoints:
  POST /auth/login       — verify email+password, issue httpOnly JWT cookie
  POST /auth/logout      — clear JWT cookie
  GET  /auth/me          — return current user from cookie

JWT is issued as an httpOnly, Secure, SameSite=Strict cookie so it is never
accessible to client-side JavaScript.

For Phase 1 (single-tenant KBrushes), we use a simple shared secret approach.
Replace with a proper user table lookup in Phase 2.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

router = APIRouter()

# ── JWT config ────────────────────────────────────────────────────────────────
JWT_SECRET    = os.environ.get("JWT_SECRET", "change-me-before-production")
JWT_ALGORITHM = "HS256"
JWT_TTL_SECS  = 60 * 60 * 8  # 8 hours

# ── Internal API key (service-to-service) ─────────────────────────────────────
# Next.js BFF routes send this header; any request without it to private
# endpoints is rejected.
INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "")

COOKIE_NAME = "vb_access_token"


# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenPayload(BaseModel):
    sub: str          # user email
    company_id: str
    exp: float


# ── Helpers ───────────────────────────────────────────────────────────────────
def _issue_jwt(email: str, company_id: str) -> str:
    payload = {
        "sub": email,
        "company_id": company_id,
        "iat": time.time(),
        "exp": time.time() + JWT_TTL_SECS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_jwt(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**data)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        )


def get_current_user(vb_access_token: Optional[str] = Cookie(default=None)) -> TokenPayload:
    """FastAPI dependency — extract and validate the platform JWT from cookie."""
    if not vb_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return _verify_jwt(vb_access_token)


def require_internal_key(request: Request) -> None:
    """FastAPI dependency — reject requests without the internal API key."""
    if not INTERNAL_KEY:
        return  # dev mode: skip if key not configured
    provided = request.headers.get("X-Internal-Key", "")
    if provided != INTERNAL_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid internal API key",
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/login", summary="Issue platform JWT as httpOnly cookie")
def login(req: LoginRequest, response: Response):
    """
    Phase 1: validate against a single env-var admin credential.
    Phase 2: replace with DB user lookup + bcrypt verify.
    """
    admin_email    = os.environ.get("ADMIN_EMAIL", "admin@vinayak.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    company_id     = os.environ.get("DEFAULT_COMPANY_ID", "kbrushes")

    if not admin_password:
        logger.warning("ADMIN_PASSWORD not set — rejecting all logins")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth not configured",
        )

    if req.email.lower() != admin_email.lower() or req.password != admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = _issue_jwt(req.email, company_id)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,          # HTTPS only
        samesite="strict",
        max_age=JWT_TTL_SECS,
        path="/",
    )
    logger.info("Login successful for %s", req.email)
    return {
        "status": "ok",
        "email": req.email,
        "company_id": company_id,
        "expires_at": datetime.fromtimestamp(
            time.time() + JWT_TTL_SECS, tz=timezone.utc
        ).isoformat(),
    }


@router.post("/logout", summary="Clear the platform JWT cookie")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me", summary="Return current user info from JWT")
def me(user: TokenPayload = __import__("fastapi").Depends(get_current_user)):
    return {
        "email":      user.sub,
        "company_id": user.company_id,
    }
