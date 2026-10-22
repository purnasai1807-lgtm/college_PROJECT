# SafeCore payment recovery

## Safety guarantee and limitation
No application can guarantee that a bank, payment provider, network, browser, or hosting platform will never fail. SafeCore is designed to avoid losing verified payments, avoid falsely marking payments as paid, and avoid asking for a second payment while the first is uncertain.

## Payment flow
- `POST /api/payments/create-order`: server calculates prices, creates a Razorpay order, reserves stock and records the internal order.
- `POST /api/payments/verify`: validates the Razorpay checkout signature and then queries Razorpay's order-payments API. Only a matching, correctly priced `captured` payment becomes locally paid.
- `GET /api/payments/status/{order_id}`: student-owned status check. It reconciles captured payments, reports processing/uncertain states without authorizing retry, and only indicates a retry may be safe after a successful provider lookup finds no captured or active attempt.
- `POST /api/payments/webhook`: validates the HMAC signature over the raw request body and deduplicates event IDs. A single `payment.failed` event is treated as an attempt failure, not proof that the whole order is permanently failed.

## Recovery behavior
If the browser closes, the frontend retains the internal order ID in the current page session and checks provider status before it permits another checkout attempt. If the page itself is closed, sign in and use order history/admin reconciliation; the persisted order and Razorpay references remain in the database. The status endpoint is also available for an authenticated student client.

Provider timeouts, malformed responses, and outages remain `verification_pending`; they are never converted into payment failure. Multiple captured payments for one order are flagged for administrative review. Administrators should reconcile against Razorpay before taking action. Do not manually mark paid without provider evidence.

## Configuration
Set server-side environment variables (never `VITE_`, `NEXT_PUBLIC_`, or other browser-exposed prefixes):
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `PAYMENT_CURRENCY=INR`
- `DATABASE_URL`
- `SECRET_KEY`

Configure Razorpay webhook URL as `https://YOUR_API_HOST/api/payments/webhook`, with at least `payment.captured` and `payment.failed`. Keep the webhook secret separate from the API key secret. Ensure the deployed backend has the same persistent database as the frontend's API. A static frontend deployment alone does not run the FastAPI backend.

## Deploy/test checklist
1. Configure Razorpay test-mode keys and webhook secret in the backend environment.
2. Apply the existing Alembic migrations using `PYTHONPATH=backend python -m alembic -c backend/alembic.ini upgrade head`.
3. Run backend tests with `cd backend && python -m pytest -q`.
4. Test browser close, callback timeout, provider API outage, duplicate webhook delivery, failed attempt followed by success, and captured payment reconciliation in Razorpay test mode.
5. Deploy and verify the backend and frontend together, then verify the webhook endpoint is reachable over HTTPS.
6. Only switch to live keys after reviewing logs and test results. Never test with a real charge.
7. Back up the database before migration. Roll back by redeploying the previous application version and applying a forward migration if schema changes are later introduced; this patch does not add a database schema migration.

## Current limitations
The recovery order ID held in the browser is lost if the entire page session is closed. The order itself remains persisted, so the order history or status endpoint can recover it after login. Automatic background reconciliation requires a scheduled task or worker in the deployment; this project currently uses on-demand reconciliation. Provider API reconciliation depends on valid Razorpay server credentials and network availability.
