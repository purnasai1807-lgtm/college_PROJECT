#!/usr/bin/env python3
"""Operational checks for ACE Canteen health and backup freshness."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


def check_endpoint(url: str, timeout: float) -> dict:
    request = Request(url, headers={"User-Agent": "ACE-Canteen-Ops-Monitor/1.0"})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(65536)
            try: payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError): payload = {}
            ok = 200 <= response.status < 300
            return {"ok": ok, "status_code": response.status, "latency_ms": round((time.monotonic()-started)*1000, 1), "detail": payload.get("status", "HTTP response")}
    except HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "latency_ms": round((time.monotonic()-started)*1000, 1), "detail": "HTTP error"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status_code": None, "latency_ms": round((time.monotonic()-started)*1000, 1), "detail": type(exc).__name__}


def check_backup(directory: Path, max_age_hours: float) -> dict:
    now = time.time()
    candidates = []
    if directory.exists():
        for path in directory.iterdir():
            if path.is_file() and path.suffix in {".db", ".sql"} and Path(str(path)+".json").is_file():
                candidates.append(path)
    if not candidates:
        return {"ok": False, "latest": None, "age_hours": None, "detail": "No backup with manifest found"}
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    age = max(0.0, (now-latest.stat().st_mtime)/3600)
    manifest_path = Path(str(latest) + ".json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("file") != latest.name:
            raise ValueError("manifest filename mismatch")
        if manifest.get("size_bytes") != latest.stat().st_size:
            raise ValueError("manifest size mismatch")
        digest = hashlib.sha256()
        with latest.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if manifest.get("sha256") != digest.hexdigest():
            raise ValueError("manifest SHA-256 mismatch")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "latest": latest.name, "age_hours": round(age, 2), "max_age_hours": max_age_hours, "detail": f"backup verification failed: {exc}"}
    fresh = age <= max_age_hours
    return {"ok": fresh, "latest": latest.name, "age_hours": round(age, 2), "max_age_hours": max_age_hours, "detail": "fresh and checksum verified" if fresh else "backup is stale"}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.getenv('ACE_CANTEEN_BASE_URL','http://127.0.0.1:8000'))
    parser.add_argument('--backup-dir', type=Path, default=Path('backups'))
    parser.add_argument('--max-backup-age-hours', type=float, default=26.0)
    parser.add_argument('--timeout', type=float, default=5.0)
    parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON')
    args=parser.parse_args()
    if args.max_backup_age_hours <= 0 or args.timeout <= 0:
        parser.error('age and timeout must be positive')
    result={"checked_at":datetime.now(timezone.utc).isoformat(),"health":check_endpoint(args.base_url.rstrip('/')+'/api/health',args.timeout),"readiness":check_endpoint(args.base_url.rstrip('/')+'/api/ready',args.timeout),"backup":check_backup(args.backup_dir,args.max_backup_age_hours)}
    result['ok']=all(result[k]['ok'] for k in ('health','readiness','backup'))
    if args.json: print(json.dumps(result,indent=2))
    else:
        print('ACE Canteen operations monitor:', 'OK' if result['ok'] else 'ALERT')
        for key in ('health','readiness','backup'):
            item=result[key]; print(f"- {key}: {'OK' if item['ok'] else 'FAIL'} — {item.get('detail','')}")
        if result['backup'].get('latest'): print(f"  latest backup: {result['backup']['latest']} ({result['backup']['age_hours']} hours old)")
    return 0 if result['ok'] else 1

if __name__ == '__main__': raise SystemExit(main())
