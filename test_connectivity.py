#!/usr/bin/env python3
"""Test connectivity to various possible TranzAct URLs"""

import socket
import requests
from urllib.parse import urlparse

# Common TranzAct URL patterns to test
test_urls = [
    "https://app.tranzact.in",
    "https://tranzact.in", 
    "https://api.tranzact.in",
    "https://staging.tranzact.in",
    "https://demo.tranzact.in",
]

def test_dns_resolution(url):
    """Test if a domain resolves"""
    parsed = urlparse(url)
    domain = parsed.netloc
    try:
        socket.gethostbyname(domain)
        print(f"✅ {domain} - DNS resolves")
        return True
    except socket.gaierror:
        print(f"❌ {domain} - DNS resolution failed")
        return False

def test_http_connect(url):
    """Test HTTP connection"""
    try:
        r = requests.get(url, timeout=5)
        print(f"✅ {url} - HTTP {r.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ {url} - Connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing TranzAct connectivity...\n")
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        if test_dns_resolution(url):
            test_http_connect(url)
    
    print("\nIf none of these work, you need:")
    print("1. The correct TranzAct URL from your team")
    print("2. VPN access if it's a private domain")
    print("3. Update .env with TRANZACT_BASE_URL=<correct_url>")
