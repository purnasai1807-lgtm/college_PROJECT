# ACE Canteen — Integrated Release (Phases 1–48)

This ZIP consolidates the latest project state through Phase 48 under the required `clg/` root.

## Included capabilities
- Student catalogue, cart, checkout quote, order history/tracking, saved items, reorder assistance and feedback.
- Staff kitchen/pickup workflows and role-protected operational views.
- Admin reporting, audit events, control-centre endpoints, order register, order investigation, staff account/role/activation management and last-active-admin safeguards.
- Inventory ledger, thresholds, stock receipts/counts/write-offs, suppliers, batches, expiry monitoring, FEFO checkout reservations and inventory reconciliation.
- Payment signature/webhook handling and idempotency foundations; payment provider behavior still requires sandbox testing with configured credentials.
- In-app notifications, PWA assets, health/readiness/metrics endpoints, local Windows scripts, Docker/PostgreSQL deployment configuration, migrations, backup/restore helpers and preflight checks.

## Local setup (Windows 11 / VS Code)
From the extracted `clg` directory:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_local.ps1
```

Open `http://127.0.0.1:8000/`. The startup script installs dependencies, prepares `.env` if missing, applies migrations and starts the app. Create an administrator using the documented command in `README.md`; do not hardcode or commit credentials.

## Test suite

```powershell
$env:PYTHONPATH = "backend"
python -m pytest -q
```

At packaging time, the full backend suite passed: **98 tests**. This is local automated test evidence, not certification of browser behavior, Razorpay live payments, production infrastructure, concurrency, accessibility or a third-party security audit.

## Scope and safety
- This consolidated release includes implemented work through Phase 48. Future roadmap work (Phases 49–53) is not represented as completed.
- No refund functionality is included.
- Razorpay live credentials are not included. Use test credentials and verify webhook delivery/retries in a staging environment before launch.
- Back up an existing database before upgrading; do not ship or replace the user's database with this source ZIP.

## Integrated Release — Phases 1–53

This release extends the Phase 48 project with Phases 49–53. New features include an admin-only payment exception/reconciliation report, supplier purchase orders with idempotent receiving into traceable batches, additional Playwright acceptance cases, and updated production-readiness and student-experience documentation. See `PHASE49-53-RELEASE-NOTES.md`.

Backend regression verification for this package: **100 tests passed**. Python compilation and Node syntax checks passed. Browser tests were added but not executed in this environment; live Razorpay and production infrastructure checks remain outstanding. No refund functionality is included.
