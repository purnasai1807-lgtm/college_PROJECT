# ACE Canteen — Integrated Source Release (Phases 1–54)

This package contains the ACE Canteen project under the required `clg/` root. It includes the source for Phases 1–53 plus Phase 54 release-readiness gates. No local SQLite database is distributed in the source ZIP; local startup/migrations create the database as needed.

## Application areas

- Student catalogue, cart, checkout, order tracking/history, saved items, reorder assistance and feedback.
- Staff kitchen/pickup workflows and role-protected operational views.
- Admin reports, audit events, control-centre APIs, order register/investigation, staff account and permission management, and last-active-admin safeguards.
- Inventory ledger, stock receipts/counts/write-offs, suppliers, purchase orders, batches, expiry monitoring, FEFO checkout reservations and reconciliation.
- Razorpay order creation, signature verification, webhook handling/idempotency foundations, and admin payment exception/reconciliation reports.
- In-app notifications, PWA assets, health/readiness/metrics endpoints, Windows local scripts, Docker/PostgreSQL configuration, Alembic migrations, backup/restore helpers and deployment preflight.
- Phase 54 adds stricter production HTTPS/payment configuration gates, live-key launch preflight, a repeatable local release gate, and release-readiness documentation.

## Local run (Windows 11 / VS Code)

From the extracted `clg/` folder:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_local.ps1
```

Open `http://127.0.0.1:8000/`. Create an administrator using the command documented in `README.md`. Use a unique password and never commit credentials.

## Verification

Run the reproducible local gate:

```powershell
python scripts/release_gate.py
```

This runs the backend regression suite, Python compilation and JavaScript syntax checks. Add `--browser` only after installing npm dependencies and the Playwright browser. Actual results should be recorded from the user's environment; a passing local gate does not certify external services.

## Production limitations

- Razorpay credentials are not included. The app has not been tested against live Razorpay or a real merchant account.
- The live-payment preflight checks configuration shape and key mode only; it does not prove credentials work or that settlement is correct.
- Browser tests, cloud deployment, load/concurrency tests, independent security audit, and off-host backup restoration require separate execution.
- Production should use PostgreSQL, deliberate Alembic migrations, disabled demo seeding, secrets management, verified HTTPS, monitoring and rehearsed backups/restore.
- Login throttling remains process-local; a multi-worker deployment should use a shared rate-limit store at the application or edge layer.
- No refund functionality is included.

See `docs/PHASE54-PRODUCTION-VERIFICATION.md` for deployment gates and outstanding external checks.
