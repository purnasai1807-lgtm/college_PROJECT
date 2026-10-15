# Phase 39 — Inventory batch reservation integration

## What changed

- Added `batch_reservations` records tying checkout orders to received inventory batches.
- Checkout reservations consume traceable, non-expired batches in FEFO order (earliest expiry first; no-expiry batches last).
- Failed payment webhooks, expired unpaid checkouts, and eligible staff cancellation paths release batch allocations and mark them released so repeated handling does not return the same batch stock twice.
- Existing aggregate product stock ledger remains the order-facing availability counter; batch quantities are the traceability layer. Products with legacy stock not represented by batches can still sell from that legacy balance, and reconciliation continues to identify those differences.
- Added migration `0013_batch_reservations.py` and regression test for FEFO ordering, expired-batch exclusion, release, and idempotent release.

## Upgrade

From the project root, with the intended database configured:

```powershell
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
python -m pytest backend/tests -q
```

Back up the database before running migrations on any shared or production instance. Test the migration against a copy of the production database first.

## Limitations

This is an inventory traceability improvement, not a certification of live payment processing or production readiness. Aggregate stock and batch stock can differ for legacy/untracked inventory; use reconciliation and resolve discrepancies through reviewed adjustments. PostgreSQL concurrency and live payment-provider webhooks must be tested in staging before launch. Refund functionality remains intentionally excluded.
