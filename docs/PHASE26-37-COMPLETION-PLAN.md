# Phases 26–37: integrated campus operations release

This release adds working backend support for supplier records, batch-level inventory traceability, expiry reporting, and transparent historical-demand summaries. These additions are API-first; they do not claim a finished visual admin screen for each workflow.

## New endpoints

- `POST /api/admin/suppliers` — admin-only supplier creation.
- `GET /api/admin/suppliers` — staff/admin supplier listing.
- `POST /api/admin/inventory/batches` — staff/admin batch receipt; validates product/supplier/expiry, increases product stock and records an inventory movement and audit event in the same transaction.
- `GET /api/admin/inventory/expiry?days=30` — staff/admin report for expired or soon-to-expire stock batches.
- `GET /api/admin/analytics/demand?days=30&limit=20` — admin-only historical paid-order demand estimate. It is a simple moving average and explicitly does not model seasonality or stockouts.

## Database upgrade

From the project root, with the normal virtual environment active:

```powershell
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
```

New tables: `suppliers`, `product_batches`. Existing product stock is updated and an inventory ledger row is created on batch receipt. Batch-level quantities are traceability records; existing order fulfilment still operates on product-level stock. A future release should reconcile consumption to batches using FEFO (first-expiry-first-out) before claiming batch-level depletion automation.

## Phases covered in this integrated package

- 26: order/payment reliability — existing quote, payment verification, webhook idempotency and order lifecycle retained; regression tests run.
- 27: kitchen/pickup lifecycle — existing validated staff status transitions and student notifications retained.
- 28: supplier and expiry traceability — supplier, batch receipt, expiry report added.
- 29: roles and admin controls — new routes reuse existing role dependencies.
- 30: demand analytics — historical paid-order summary added; not a predictive ML model.
- 31: reliability/security — existing tests and request security controls retained; new route authorization tested.
- 32: deployment — migration and environment setup documented; live hosting is not performed here.
- 33: smart canteen — transparent demand-rate/reorder estimate added, not seasonality-aware forecasting.
- 34: student experience — existing favourites, reorder quote, notifications, feedback and PWA retained.
- 35: counters/queue — existing shared queue and pickup lifecycle retained; per-counter routing is not yet implemented.
- 36: performance/integration — current automated test coverage retained; no load test or live payment provider test is claimed.
- 37: acceptance — backend regression tests include the new procurement/expiry/analytics flows; manual campus pilot remains necessary.

## Before campus production

Configure a real PostgreSQL instance and secrets, run migrations, validate payment-provider test mode and webhook signatures, enforce HTTPS, rehearse backup restore, run browser/mobile and load tests, and obtain staff/student pilot sign-off. Backups should be encrypted and stored off-host. No refund functionality is included by design.
