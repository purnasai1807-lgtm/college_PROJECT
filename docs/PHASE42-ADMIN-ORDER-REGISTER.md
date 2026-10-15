# Phase 42 — Admin complete order register

The admin order panel now uses `GET /api/admin/orders/all`, an administrator-only register separate from the paid-order operational queue.

## Included
- Review orders across payment states: pending, paid, failed, and refunded (read-only payment status; no refund feature is implemented).
- Filter by order lifecycle status and payment status.
- Search by customer name/email, order ID, or gateway order ID via the API's `search` query parameter.
- Newest-first pagination with `limit` (1–1000) and `offset`.
- Includes customer identity, item lines, total, timestamps, order status, gateway references, and payment status.
- Only admins may access the full register; ordinary staff retain the paid operational queue.
- Status transition buttons are shown only for paid orders; the server remains authoritative about allowed transitions.

## Endpoint examples

- `GET /api/admin/orders/all?limit=100&offset=0`
- `GET /api/admin/orders/all?status=ready&payment_status=paid`
- `GET /api/admin/orders/all?search=student@example.edu`

Requires a valid administrator bearer token. This register is for verification and operational visibility; it does not manually mark a payment as paid. Payment verification must continue through the configured payment-provider verification/webhook flow.
