"""HTTP smoke checks for a running ACE Canteen instance.

Usage: python scripts/smoke_test.py [base_url]
This checks the live HTTP surface without modifying accounts or orders.
"""
from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")

def get(path: str):
    request = urllib.request.Request(BASE + path, headers={"Accept": "application/json,text/html,*/*"})
    with urllib.request.urlopen(request, timeout=8) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        return response.status, content_type, body

def check(label: str, path: str, validate):
    try:
        status, content_type, body = get(path)
        payload = json.loads(body) if "json" in content_type else body.decode("utf-8", errors="replace")
        validate(status, content_type, payload)
        print(f"[PASS] {label}: HTTP {status}")
        return True
    except Exception as exc:
        print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
        return False

checks = [
    ("homepage", "/", lambda s, c, b: (_ for _ in ()).throw(AssertionError("missing ACE Canteen title")) if s != 200 or "ACE Canteen" not in b else None),
    ("health", "/api/health", lambda s, c, b: (_ for _ in ()).throw(AssertionError(f"unexpected payload: {b}")) if s != 200 or b.get("status") != "ok" else None),
    ("readiness/database", "/api/ready", lambda s, c, b: (_ for _ in ()).throw(AssertionError(f"not ready: {b}")) if s != 200 or b.get("status") != "ready" or b.get("checks", {}).get("database") != "ok" else None),
    ("product catalogue", "/api/products", lambda s, c, b: (_ for _ in ()).throw(AssertionError("catalogue is not a JSON list")) if s != 200 or not isinstance(b, list) else None),
    ("categories", "/api/categories", lambda s, c, b: (_ for _ in ()).throw(AssertionError("categories is not a JSON list")) if s != 200 or not isinstance(b, list) else None),
]
results = [check(*item) for item in checks]
print(f"\nHTTP smoke checks: {sum(results)}/{len(results)} passed against {BASE}")
sys.exit(0 if all(results) else 1)
