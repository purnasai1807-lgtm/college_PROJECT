# Phase 38 — Inventory reconciliation

## Endpoint

`GET /api/admin/inventory/reconciliation` (administrator bearer token required)

Returns each active product's aggregate stock and, when traceable batches exist, the sum of remaining batch quantities. Each product is labelled `matched`, `mismatch`, or `untracked_legacy_stock`; response totals include mismatch and untracked counts.

This endpoint is deliberately read-only. It never silently changes product stock or batch balances. Legacy products without batches are reported separately rather than incorrectly treating missing traceability records as zero stock. Resolve discrepancies only after a physical count and a reviewed stock adjustment. Batch-level consumption and expiry-aware FIFO depletion still require a separately tested order/inventory transaction workflow.

## Test

From the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
```

The regression test checks authorization, response shape, and that reading the reconciliation report does not alter inventory summary data.
