# Phase 54 — Production Verification & Reliability

Phase 54 is a release-readiness gate and hardening pass, not a claim that third-party infrastructure has been tested.

## Changes

- Production preflight now treats unverified HTTPS termination as a blocking error.
- Razorpay key ID, key secret, and webhook secret must be configured as a complete set or all left empty. A partial set fails preflight.
- Added `--require-live-payment` for the final payment-launch check. It requires all provider settings and a key ID with the `rzp_live_` prefix; it does not contact Razorpay or prove the credentials work.
- Added regression tests for HTTPS gating, partial payment configuration, live/test key mode, and secret-safe preflight output.
- Added `scripts/release_gate.py` to run backend tests, Python compilation and frontend JavaScript syntax checks in one command. `--browser` additionally invokes Playwright.
- Updated release status to match the actual Phase 1–54 source state and removed the bundled local SQLite database from the release archive to avoid distributing local data.

## Local release gate

From the `clg/` root:

```powershell
python scripts/release_gate.py
```

For browser tests, install JavaScript dependencies and a Playwright browser first, then run:

```powershell
npm ci
npx playwright install chromium
python scripts/release_gate.py --browser
```

## Cloud deployment preflight

Inject secrets through the hosting provider's secret manager. Do not commit them to `.env`, a container image, or source control. Use PostgreSQL, disable auto table creation and demo seeding, run Alembic migrations as a separate deployment step, and configure TLS at the reverse proxy/load balancer before acknowledging HTTPS termination.

```bash
python scripts/deployment_preflight.py --json
```

For the final live-payment launch gate, after adding the provider's live credentials in the secret manager:

```bash
python scripts/deployment_preflight.py --require-live-payment --json
```

A successful configuration check does **not** contact the payment provider or validate that credentials belong to the correct merchant. In staging, verify Razorpay order creation, payment signature validation, webhook signatures, webhook retries/idempotency, delayed capture/failure cases, and reconciliation against the provider dashboard before production. Never put credentials in this repository or in support chats.

## Still requires external verification

- Cloud provider networking, DNS, TLS certificate and reverse-proxy behavior.
- Actual Razorpay test and live transactions, webhook delivery and settlement reconciliation.
- Browser acceptance tests on an installed Playwright browser and target browsers/devices.
- PostgreSQL concurrent-checkout/load testing, backup restoration from an off-host backup, and a rollback drill.
- Independent security review and operational alert delivery.

No refund functionality is included.
