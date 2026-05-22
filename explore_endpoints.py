#!/usr/bin/env python3
"""Explore TranzAct endpoints to find the correct login path"""

import requests
from urllib.parse import urljoin

BASE_URL = "https://tranzact.in"

# Common login endpoint patterns
login_paths = [
    "/main/login/password-login/",
    "/api/login/",
    "/auth/login/",
    "/login/",
    "/api/v1/login/",
    "/api/auth/login/",
    "/user/login/",
    "/accounts/login/",
]

def test_endpoint(path):
    """Test if an endpoint exists"""
    url = urljoin(BASE_URL, path)
    try:
        # Try POST first
        r = requests.post(url, json={"test": "data"}, timeout=5)
        print(f"POST {path:<30} -> {r.status_code}")
        if r.status_code not in [404, 405]:
            return True
    except requests.exceptions.RequestException:
        pass
    
    try:
        # Try GET
        r = requests.get(url, timeout=5)
        print(f"GET  {path:<30} -> {r.status_code}")
        if r.status_code not in [404, 405]:
            return True
    except requests.exceptions.RequestException:
        pass
    
    return False

if __name__ == "__main__":
    print(f"Exploring endpoints on {BASE_URL}\n")
    
    found = []
    for path in login_paths:
        if test_endpoint(path):
            found.append(path)
    
    if found:
        print(f"\n✅ Potential login endpoints found:")
        for path in found:
            print(f"  - {path}")
    else:
        print(f"\n❌ No working login endpoints found")
        print("You may need to check the browser dev tools or contact TranzAct team")
