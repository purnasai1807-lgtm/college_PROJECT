# ACE Canteen security fixes — Phase 58

Date: 2026-10-22

This document records source-code changes and verification performed for the supplied project. It is **not** a claim that the currently deployed Vercel service has been updated or penetration-tested.

## Fixed in source

1. **Durable checkout idempotency**
   - Added `checkout_idempotency` ledger and Alembic migration `0017_checkout_idempotency`.
   - Checkout keys are scoped to the authenticated user and bound to a canonical request fingerprint.
   - Replaying the same key/cart returns the original response; reusing a key with a different cart returns `409`.
   - A concurrent in-progress request returns `409` instead of launching another provider checkout.
   - Browser checkout retains the idempotency key in session storage until payment recovery clears it.
   - Provider order ID, amount and currency are checked before the local order is created.
   - Inventory and price are re-locked/revalidated after the remote provider call and before reservation to reduce stale-stock and price races.

2. **Production rate-limit fail-closed behavior**
   - Production requires a reachable TLS-enabled Redis-compatible endpoint configured as `REDIS_URL=rediss://...`.
   - Production startup fails if the shared limiter is missing or unavailable; it no longer silently accepts per-process memory as the fallback.
   - Production login throttles both account/IP and IP-wide buckets; registration attempts are throttled by source IP.
   - Development/test mode retains in-memory throttling so local tests do not share global counters.

3. **Reduced public fingerprinting**
   - Production `/api/info` returns only the application name and online status instead of framework, database and version details.
   - HSTS is emitted in production even when TLS terminates at the hosting proxy. Browsers only honor HSTS over HTTPS.

4. **Deployment guardrails and regression coverage**
   - Deployment preflight now rejects missing or non-TLS Redis URLs in production.
   - Added regression tests for idempotent checkout replay, mismatched payloads, Redis fail-closed behavior and production information minimization.
   - Updated migration-head regression assertion to `0017_checkout_idempotency`.

## Verification completed locally

- Backend: `127 passed, 1 skipped`.
- Python compilation: passed.
- JavaScript syntax check (`node --check frontend/js/app.js`): passed.
- Alembic migration head: `0017_checkout_idempotency`.
- Local HTTP smoke test on a temporary SQLite database: homepage, health, readiness/database, product catalogue and categories passed (`5/5`).

## Must be completed in the real deployment

These items cannot be truthfully marked complete from source code alone:

- Set `ENVIRONMENT=production`, a unique `SECRET_KEY`, PostgreSQL `DATABASE_URL`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`, HTTPS `PUBLIC_BASE_URL`, and a reachable TLS-enabled `REDIS_URL` in the actual hosting environment.
- Apply `alembic upgrade head` to the production database after taking a verified backup. Confirm the migration completed before deploying code that uses the new ledger.
- Configure Razorpay keys and webhook secret in the provider dashboard; test duplicate clicks, network loss, delayed webhooks, captured/failed/ambiguous payments and reconciliation in test mode before live payments.
- Configure production SMTP and verify password-reset delivery.
- Run authenticated browser end-to-end tests and a passive security scan against staging. The Playwright dependency install did not complete in this environment, so browser E2E was not run.
- Verify live headers, HTTPS, API authorization boundaries, backup restoration, monitoring and rollback after deployment.

## Remaining security consideration

The existing frontend stores bearer tokens in `localStorage`. This is a known trade-off: any future same-origin XSS could read a token. The inspected JavaScript did not contain direct `innerHTML`, `insertAdjacentHTML`, or `document.write` sinks, and the app has a Content Security Policy, but those controls do not make localStorage immune to XSS. A full move to `HttpOnly; Secure; SameSite` cookies should be designed with CSRF protection and browser-flow regression tests as a separate authentication migration; it should not be partially switched without those protections.

## Release rule

Do not claim production-ready until the external configuration and deployment checks above are completed against the deployed environment. Never include `.env`, database files, provider credentials, or local backups in a source ZIP.
