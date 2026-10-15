# Phase 40 — Checkout integration regression

## Purpose

This phase adds a repeatable integration test for the most important checkout boundary: a student creates a checkout, stock is reserved in both the aggregate product counter and traceable inventory batches, and the payment signature is verified before the order becomes paid.

## Coverage

- Creates a unique test product with an unexpired batch.
- Registers and authenticates a student through the public API.
- Mocks the HTTP response from Razorpay order creation; no external payment is made.
- Checks aggregate stock and batch stock both decrease by the requested quantity.
- Verifies a valid checkout signature marks the order paid.
- Verifies repeating the same payment verification is idempotent.
- Verifies a mismatched payment ID cannot be accepted as the already-paid payment.
- Cleans up test rows even when an assertion fails.

## Run

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests/test_phase40_checkout_integration.py -q
```

## Limits

This test does not replace Razorpay sandbox testing, webhook delivery tests against a provider sandbox, PostgreSQL concurrency tests, Playwright end-to-end browser tests, deployment validation, or a staged backup restore. Production readiness must not be inferred from this test alone.
