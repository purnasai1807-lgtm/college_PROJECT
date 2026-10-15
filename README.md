
## Phase 24 — production deployment preflight

Before deploying, run a configuration-only safety check. It does not connect to the database, migrate schemas, or contact Razorpay:

```powershell
# Windows PowerShell, from the clg project root
python scripts/deployment_preflight.py
python scripts/deployment_preflight.py --json
```

For a production deployment, set the production environment variables in the deployment secret manager (not in source control), then run:

```powershell
python scripts/deployment_preflight.py --json
python -m alembic -c backend/alembic.ini upgrade head
```

The preflight checks the secret key, environment name, PostgreSQL URL, disabled automatic schema creation and demo seeding, password length, Razorpay credential pairing, and whether API docs were explicitly requested. It reports no secret values. HTTPS termination is a warning until `HTTPS_TERMINATED=true` is set after TLS is configured and verified. A passed preflight is not a substitute for migration rehearsal, a live readiness check, security review, or a staging restore drill.

Convenience wrappers: `scripts/deployment_preflight.ps1` (PowerShell) and `scripts/deployment_preflight.sh` (POSIX shell). Add the preflight to the deployment pipeline after injecting environment secrets and before applying migrations.

**Production checklist:** use unique secrets in a secret manager; keep `.env` out of Git; use PostgreSQL; run Alembic migrations as a deliberate deployment step; disable demo seeding; terminate TLS at a verified reverse proxy; keep the app port private; configure encrypted off-host backups and alerting; rehearse rollback and restore in staging. No refund functionality is provided.

## Phase 25 — Operational metrics and request tracing

Phase 25 adds process-local aggregate request metrics at `/api/metrics`, request-ID propagation, and production token protection for the metrics endpoint. See [`docs/PHASE25-OBSERVABILITY.md`](docs/PHASE25-OBSERVABILITY.md) for setup and limitations. In production, set a strong `METRICS_TOKEN` in the secret manager and restrict endpoint access at the proxy/network layer. Metrics reset when the app process restarts and are not shared across workers.

## Phase 26–37 integrated operations release

This release adds supplier management, inventory batch receipts with optional expiry dates, expiry alerts/reporting, and an admin demand summary derived from paid orders. See `docs/PHASE26-37-COMPLETION-PLAN.md` for endpoints, database migration, operational limitations, and remaining live-campus acceptance steps.

Apply the new database migration before using these endpoints:

```powershell
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
```

New endpoints are documented in the Phase 26–37 guide. These operational APIs require the documented staff/admin roles. No refund functionality is provided.

### Phase 38 — Inventory reconciliation

Administrators can compare each active product's aggregate stock with the remaining quantity across traceable stock batches using `GET /api/admin/inventory/reconciliation`. The report distinguishes mismatches from legacy products without batch records and is read-only; it will not silently change stock. See `docs/PHASE38-INVENTORY-RECONCILIATION.md`.

## Phase 39 — Batch reservation integration

Checkout now records batch-level reservations using earliest-expiry-first allocation, excludes expired batches from allocation, and supports idempotent batch-stock release on failed/expired checkout paths. Apply migration `0013_batch_reservations` before deploying this version. See `docs/PHASE39-INTEGRATION-HARDENING.md`. This does not replace staging tests of real payment-provider events, PostgreSQL concurrency, or production restore procedures.

## Phase 40 — checkout integration regression

Phase 40 adds an automated integration regression using a mocked Razorpay order-creation response. It exercises student registration/login, checkout creation, aggregate stock reservation, FEFO batch allocation, payment-signature verification, repeated verification, and rejection of a mismatched payment ID. The test does not contact Razorpay and does not prove live payment-provider behavior.

Run it from the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests/test_phase40_checkout_integration.py -q
```

## Quick start on Windows 11 (PowerShell / VS Code)

For a first local run, open a PowerShell terminal in the `clg` project folder and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_local.ps1
```

The script creates `.venv` if needed, creates `.env` only when missing, installs dependencies, applies Alembic migrations, and starts the server. It does not overwrite an existing `.env` or delete your database. Keep the terminal open and visit `http://127.0.0.1:8000/`. Stop with **Ctrl+C**. Internet access is needed for the first dependency installation.

Run backend regression tests after setup:

```powershell
.\scripts\run_tests.ps1
```

Local Razorpay checkout remains disabled until valid Razorpay test credentials are configured in `.env`. Never use live keys for local testing or commit credentials.

## Phase 41 — Runtime hardening

SQLite foreign-key enforcement is enabled on each connection, and login throttling
cleans up expired in-memory keys to avoid unbounded growth. See
`docs/PHASE41-RUNTIME-HARDENING.md` for limitations and verification steps.


## Phase 42 — Admin order verification

Administrators have a complete order register at `/api/admin/orders/all`, including pending/paid/failed/refunded payment states, customer and item details, status/payment filters, search, and pagination. The frontend admin order panel uses this register; staff continue to use the paid operational queue. The full register is admin-only. See `docs/PHASE42-ADMIN-ORDER-REGISTER.md`. Payment state must still be verified through the payment-provider flow; the register does not provide a manual payment override or refunds.

## Phase 44 — Admin control centre APIs

The admin control centre now includes:

- `GET /api/admin/dashboard/summary`: aggregate order, payment, revenue, low-stock, user and webhook KPIs.
- `GET /api/admin/orders/export.csv`: bounded CSV export of order records, optionally filtered by order/payment status. It excludes credentials and payment signatures.
- `GET /api/admin/payments/webhook-events`: paginated view of received webhook event IDs/names/timestamps for reconciliation.

All three endpoints require the administrator role. They are backend APIs; a polished dedicated frontend page for these additional panels is a separate remaining UI task. Payment states must still be confirmed by the payment provider flow, not manually edited by an administrator.


## Phase 46 — Admin governance

See `docs/PHASE46-ADMIN-GOVERNANCE.md` for last-active-admin safeguards and audit-event investigation filters.
