# Phase 41 — Runtime hardening

This phase closes two reliability gaps discovered during the application audit:

- SQLite now enables `PRAGMA foreign_keys=ON` for each DB-API connection. Declared
  constraints such as order-item/product and batch/product relationships are enforced
  locally rather than silently allowing new orphan records.
- Login throttling no longer creates an empty dictionary entry for every identifier
  checked. Expired entries are periodically pruned once the map grows, reducing
  unbounded memory growth from requests with arbitrary email/IP combinations.

## Verification

Run from the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
```

The rate limiter remains process-local. Multi-worker deployments should use a shared
store (for example Redis) or an edge/API-gateway limiter for consistent limits across
workers. Enabling SQLite constraints can expose legacy orphaned rows already present
in an old local database; back up and inspect that database before adopting this build.
