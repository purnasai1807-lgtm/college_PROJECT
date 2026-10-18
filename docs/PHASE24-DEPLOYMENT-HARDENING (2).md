# Phase 24 — deployment hardening

## Included

- `scripts/deployment_preflight.py`: deterministic preflight for deployment environment configuration, with text and JSON output and nonzero exit on blocking errors.
- PowerShell and POSIX wrappers for CI/deployment use.
- Automated tests for development and production configuration cases, payment credential pairing, and secret-value redaction.

## Run locally

```powershell
python scripts/deployment_preflight.py
python scripts/deployment_preflight.py --json
```

Development defaults intentionally report the development secret as a failed check but the command remains successful in development, so local setup can continue. For production, errors block the command. HTTPS termination is a warning because TLS may terminate at infrastructure outside this process.

## Production sequence

1. Inject a unique `SECRET_KEY`, PostgreSQL `DATABASE_URL`, `POSTGRES_PASSWORD`, and optional payment credentials through your hosting secret manager.
2. Set `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`, and `EXPOSE_API_DOCS=false`.
3. Run `python scripts/deployment_preflight.py --json`; resolve every error.
4. Run `python -m alembic -c backend/alembic.ini upgrade head` in the migration job, using the same database URL as the app.
5. Start the application and verify `/api/health` and `/api/ready` through the intended private/public network paths.
6. Configure HTTPS and trusted proxy behavior; set `HTTPS_TERMINATED=true` only after validating TLS externally.
7. Rehearse backup restoration and rollback in staging before live traffic.

## Limits

The preflight validates configuration values only. It does not verify that PostgreSQL is reachable, prove migrations are current, inspect cloud IAM rules, test TLS certificates, verify live Razorpay credentials, or establish production readiness. Never put real secrets in Git, issue trackers, screenshots, or the downloadable project ZIP. Keep refunds disabled as requested.
