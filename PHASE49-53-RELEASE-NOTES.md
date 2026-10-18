# ACE Canteen — Phases 49–53

This release extends the Phase 48 integrated project. It preserves the `clg/` project root and the explicit no-refunds policy.

## Phase 49 — Payment reliability and reconciliation
- Added admin-only `GET /api/admin/payments/reconciliation` for aged pending and failed payment exceptions.
- Output includes order/payment state, gateway identifiers, age and recommended manual verification action.
- This is intentionally diagnostic only: it does not automatically mark payments paid/failed, capture payments, or initiate refunds.
- Added authorization and response-safety tests.

## Phase 50 — Procurement and purchasing
- Added purchase order creation for active suppliers and active products.
- Purchase orders validate quantity, unit cost, product/supplier existence and expiry dates.
- Added staff/admin purchase-order listing and a receive endpoint.
- Receiving creates traceable inventory batches, updates aggregate stock, writes inventory ledger entries and audit events.
- Receiving is idempotent: repeating a receive request does not add stock twice.
- Migration `0014_purchase_orders` adds the purchase order table and indexes.

## Phase 51 — Browser acceptance coverage
- Extended Playwright acceptance coverage for keyboard focus, empty search, guest cart state and client-side error absence.
- Run with `npm install` then `npm run test:e2e` after installing the backend dependencies. Browser tests require a working Chromium installation.

## Phase 52 — Production readiness gates
- Retained deployment preflight, readiness endpoint, database migration runbook, backup scripts, security headers, Docker configuration and operations checks.
- Production deployment remains blocked until operators provide unique secrets, configure a real database and HTTPS, verify backup restoration, and complete provider sandbox checks.
- Do not treat local tests as a production security audit or live-payment certification.

## Phase 53 — Student experience polish
- Preserved live catalogue search, type/category filters, sorting, pagination, cart feedback, saved favorites, reorder quote, reviews and PWA shell.
- Added acceptance coverage for keyboard focus and clear empty-search/cart states.
- Reduced-motion and visible-focus styles remain enabled.

## Verification
- Automated backend suite: run `PYTHONPATH=backend pytest -q backend/tests`.
- Browser acceptance: `npm run test:e2e` (requires Node/npm and Playwright Chromium).
- Payment provider sandbox/live transaction, webhook retries, browser matrix, production database, HTTPS, concurrency/load, accessibility audit and restore drill require environment-specific verification and are not asserted as passed here.
- No refund functionality has been added.
