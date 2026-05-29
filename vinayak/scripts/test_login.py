"""
kbrushes/scripts/test_login.py
──────────────────────────────
One-shot diagnostic for the TranzAct login / test-connection problem.

Run from the repo root with a populated .env:
    python -m vinayak.scripts.test_login

It does NOT use the production auth module — it hits the login endpoint
directly and prints the raw response so you can see the real envelope shape
(status vs success, where the tokens live, any error message). Use the output
to confirm the field mapping the app's auth modules now probe for.
"""
from __future__ import annotations

import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("TRANZACT_BASE_URL", "https://be.letstranzact.com")
EMAIL = os.getenv("TRANZACT_EMAIL", "")
PASSWORD = os.getenv("TRANZACT_PASSWORD", "")

ACCESS_KEYS = ("access_token", "access", "token", "accessToken")
REFRESH_KEYS = ("refresh_token", "refresh", "refreshToken")


def pick(obj, keys):
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("✗ TRANZACT_EMAIL / TRANZACT_PASSWORD not set in environment (.env)")
        return 2

    url = f"{BASE_URL}/main/login/password-login/"
    print(f"→ POST {url}")
    print(f"  email: {EMAIL}")

    try:
        resp = requests.post(url, json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    except requests.RequestException as exc:
        print(f"✗ Network error reaching {url}: {exc}")
        return 1

    print(f"← HTTP {resp.status_code}")

    try:
        body = resp.json()
    except ValueError:
        print("✗ Response was not JSON. First 500 chars:")
        print(resp.text[:500])
        return 1

    print("── Raw response body ──────────────────────────────")
    print(json.dumps(body, indent=2)[:2000])
    print("───────────────────────────────────────────────────")

    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else body.get("tokens", {})
    access = pick(data, ACCESS_KEYS) or pick(tokens, ACCESS_KEYS) or pick(body, ACCESS_KEYS)
    refresh = pick(data, REFRESH_KEYS) or pick(tokens, REFRESH_KEYS) or pick(body, REFRESH_KEYS)

    if access:
        print(f"✓ access token found ({access[:32]}...)")
        print(f"{'✓' if refresh else '⚠'} refresh token "
              f"{'found' if refresh else 'NOT found — refresh flow will fall back to re-login'}")
        return 0

    print("✗ No access token found in any known location.")
    print("  Top-level keys:", list(body.keys()))
    if isinstance(data, dict):
        print("  data keys:     ", list(data.keys()))
    print("  → Add the correct key name to ACCESS_KEYS/REFRESH_KEYS in")
    print("    lib/tranzact/auth.ts and kbrushes/adapters/tranzact/auth.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
