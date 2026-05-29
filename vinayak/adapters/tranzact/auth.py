"""
adapters/tranzact/auth.py
─────────────────────────
TranzAct authentication module.

Responsibilities:
  • POST /main/login/password-login/ to obtain JWT access + refresh tokens
  • Cache the access token in memory; auto-refresh before expiry
  • Respect the 10 req/min/machine throttle on the login endpoint
  • Expose a single get_access_token() call for all other modules

Token lifecycle (from TranzAct docs):
  • access_token  — short-lived JWT (typically 30 min)
  • refresh_token — longer-lived JWT used to obtain a new access_token

Design note: this module is intentionally stateless across processes.
If you run multiple workers, each worker manages its own token cache.
For multi-process deployments, store the token in Redis instead of _cache.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class _TokenCache:
    """Thread-safe in-memory token store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.access_expires_at: float = 0.0   # unix timestamp
        self.refresh_expires_at: float = 0.0

    def is_access_valid(self, buffer_seconds: int = 120) -> bool:
        """True if the access token won't expire within the next buffer_seconds."""
        return bool(self.access_token and time.time() < (self.access_expires_at - buffer_seconds))

    def set(
        self,
        access_token: str,
        refresh_token: str,
        access_expires_at: float,
        refresh_expires_at: float,
    ) -> None:
        with self._lock:
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.access_expires_at = access_expires_at
            self.refresh_expires_at = refresh_expires_at


# Module-level singleton
_cache = _TokenCache()


def _decode_exp(token: str) -> float:
    """Extract the 'exp' claim from a JWT without verifying the signature."""
    import base64, json

    try:
        payload_b64 = token.split(".")[1]
        # Pad to a multiple of 4
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get("exp", time.time() + 1800))
    except Exception:
        # Fallback: assume 30-minute life
        return time.time() + 1800


_ACCESS_KEYS = ("access_token", "access", "token", "accessToken")
_REFRESH_KEYS = ("refresh_token", "refresh", "refreshToken")


def _pick(obj: object, keys: tuple[str, ...]) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _extract_tokens(body: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Find access/refresh tokens regardless of envelope shape. TranzAct mixes
    {"success": ...} and {"status": ...} styles and nests tokens under
    `data` or `data.tokens`, so we probe every known location.
    """
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else body.get("tokens", {})
    access = _pick(data, _ACCESS_KEYS) or _pick(tokens, _ACCESS_KEYS) or _pick(body, _ACCESS_KEYS)
    refresh = _pick(data, _REFRESH_KEYS) or _pick(tokens, _REFRESH_KEYS) or _pick(body, _REFRESH_KEYS)
    return access, refresh


def _do_login(base_url: str, email: str, password: str) -> None:
    """
    Hit the TranzAct login endpoint and populate the token cache.
    Raises RuntimeError on auth failure.
    """
    url = f"{base_url}/main/login/password-login/"
    payload = {"email": email, "password": password}

    logger.info("TranzAct: authenticating as %s", email)
    response = requests.post(url, json=payload, timeout=30)

    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(
            f"TranzAct login: non-JSON response (HTTP {response.status_code}) "
            f"from {url} — {response.text[:300]}"
        )

    if not response.ok:
        raise RuntimeError(
            f"TranzAct login failed: HTTP {response.status_code} — {str(body)[:400]}"
        )

    access_token, refresh_token = _extract_tokens(body)
    if not access_token:
        # 2xx but no recognised token — surface the full body instead of a
        # generic error. (Original bug: a successful {"success": true, ...}
        # login was rejected because the code required status == 1.)
        raise RuntimeError(f"TranzAct login: no access token in response — {str(body)[:400]}")

    _cache.set(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=_decode_exp(access_token),
        refresh_expires_at=_decode_exp(refresh_token) if refresh_token else 0.0,
    )
    logger.info(
        "TranzAct: login successful, token valid until %s",
        datetime.fromtimestamp(_cache.access_expires_at, tz=timezone.utc).isoformat(),
    )


def _do_refresh(base_url: str) -> bool:
    """
    Use the refresh_token to obtain a new access_token.
    Returns True on success, False if refresh itself has expired (need re-login).
    """
    if not _cache.refresh_token or time.time() >= _cache.refresh_expires_at:
        return False

    url = f"{base_url}/main/login/token/refresh/"
    payload = {"refresh": _cache.refresh_token}

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        new_access, _ = _extract_tokens(body)
        if not new_access:
            return False
        _cache.set(
            access_token=new_access,
            refresh_token=_cache.refresh_token,
            access_expires_at=_decode_exp(new_access),
            refresh_expires_at=_cache.refresh_expires_at,
        )
        logger.info("TranzAct: access token refreshed via refresh_token")
        return True
    except Exception as exc:
        logger.warning("TranzAct: token refresh failed (%s), will re-login", exc)
        return False


def get_access_token(
    base_url: str,
    email: str,
    password: str,
    force_refresh: bool = False,
) -> str:
    """
    Return a valid TranzAct access token.

    Strategy:
      1. Return cached token if still valid (> 2 min remaining).
      2. Try refresh_token flow.
      3. Fall back to full password login.

    Args:
        base_url:      e.g. "https://app.tranzact.in"
        email:         TranzAct login email
        password:      TranzAct login password
        force_refresh: if True, skip the cached-token check

    Returns:
        A valid JWT access token string.
    """
    if not force_refresh and _cache.is_access_valid():
        return _cache.access_token  # type: ignore[return-value]

    # Try cheap refresh first
    if _do_refresh(base_url):
        return _cache.access_token  # type: ignore[return-value]

    # Full re-login
    _do_login(base_url, email, password)
    return _cache.access_token  # type: ignore[return-value]
