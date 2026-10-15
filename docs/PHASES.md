# ACE Canteen delivery phases

- **Phase 1 — Foundation:** responsive app shell, static frontend, health/readiness/info endpoints, settings validation, request logging, consistent errors, smoke tests.
- **Phase 2 — Database foundation:** SQLAlchemy schema, Alembic migrations, SQLite/PostgreSQL configuration, readiness query, idempotent demo seed data, database-backed catalogue APIs.
- **Phase 3 — Authentication and roles:** student registration/login, PBKDF2 password hashing, signed expiring bearer tokens, role checks, password change with session invalidation, admin bootstrap, admin user/role/activation management.
- **Phase 4 — Managed catalogue:** food/stationery browsing, search across names/descriptions/categories, category/type filters, price/name/stock sorting, bounded pagination, images and dietary/allergen metadata, staff/admin product create/edit/archive, admin category create/edit/archive/reactivate, role-validated APIs and UI.
- **Phase 5 — Cart and checkout:** implemented with multi-item basket and server-side price/stock validation.
- **Phase 6 — UPI gateway:** implemented with Razorpay checkout, server-side signature/webhook verification, and payment failure/expired reservation handling.
- **Phase 7 — Order lifecycle:** status transitions and order history.
- **Phase 8 — Tokens and queue:** daily token assignment and queue views.
- **Phase 9 — Live updates:** authenticated per-order queue tracking, privacy-safe public pickup board, automatic 15-second polling for student order history and staff queue, refresh on tab focus.
- **Phase 10 — Staff workflow:** role-protected kitchen and pickup-counter dashboards, live operational counts, stage-specific actions, and automatic refresh.
- **Phase 11 — Inventory (implemented):** immutable stock movement ledger, opening balance backfill, stock receipt/physical count/write-off operations, per-product low-stock thresholds, low/out-of-stock alerts, and role-protected UI/API.
- **Phase 12 — Admin reporting and audit (implemented):** date-filtered paid revenue/order KPIs, daily sales, top-selling products, CSV export, and role-protected audit-event search.
- **Phase 13 — Notifications (implemented):** persistent user-scoped in-app inbox, unread counts, mark-one/read-all controls, order/payment status updates, low-stock alerts for active staff/admin accounts, and polling refresh. Email/SMS delivery is not configured in this release.
- **Phase 14 — Security hardening (implemented):** baseline security headers and Razorpay-compatible Content Security Policy, declared request-body size validation, production-only configuration guards, production API-docs disablement, and automated tests for security headers and request validation. Login throttling is currently process-local; reverse-proxy enforcement is required for chunked request bodies. Browser automation, dependency vulnerability scanning, external penetration testing, and live payment validation remain deployment/release tasks.
- **Phase 15 — Deployment and pilot (starter kit implemented):** non-root Docker image, Docker Compose PostgreSQL service, explicit migration job, health checks, HTTPS reverse-proxy example, request IDs and duration logs, backup scripts, restore guidance, and campus-pilot checklist. Real infrastructure validation remains a deployment task.

Phases 1–12 provide the foundation, authentication, catalogue management, checkout/payment integration, order lifecycle, daily pickup queue, automatically refreshed order tracking, staff workflow, inventory ledger/alerts, admin reports, and audit history.


## Phase 5 — Cart and checkout (implemented)
- Student-only multi-item cart with persistent browser storage, quantity changes, item removal, clear cart, and notes.
- Server-side cart quote validates stock and active catalogue entries and calculates INR totals from database prices.
- Checkout revalidates at order creation, creates a daily token, snapshots item names/prices, and decrements stock transactionally.
- Online payment handoff is implemented in Phase 6; configure provider keys before checkout can collect payments.


## Phase 6 — payments
- Razorpay checkout order creation using server-calculated INR totals.
- Server-side HMAC signature verification before marking an order paid.
- Captured-payment webhook signature validation and reconciliation.
- Test/live credentials are environment-only; no payment is simulated when keys are missing.


## Phase 7 — Order lifecycle
- Paid orders only enter the staff/admin queue.
- API enforces legal transitions: pending → confirmed → preparing → ready → completed. Paid-order cancellation and refunds are intentionally not offered; clearly disclose the no-refunds policy before checkout.
- Student order history shows payment state, token, line items, and latest order state.
- Staff/admin access remains role-protected.
- Unpaid orders cannot be advanced into preparation.


## Phase 8 — Daily pickup tokens and queue views (implemented)
- Public queue overview shows today’s paid active tokens, preparing tokens, ready-for-pickup tokens, and approximate wait estimates without exposing student names or emails.
- Authenticated order queue-position endpoint checks ownership (or staff/admin role) and reports the current order position and estimate.
- Queue board refreshes automatically every 15 seconds and when the browser tab becomes visible.
- Daily token values are scoped by the token date; completed and cancelled orders are excluded from active queue calculations. Estimates are indicative only.


## Phase 9 — Live order tracking (implemented with polling)
- Header account shortcut is positioned at the top-right and updates to show the signed-in user's account label.
- Students see a live-tracking panel on each active, paid order, including current queue position or latest status and estimated wait.
- Public pickup board and student order history refresh automatically every 15 seconds; staff/admin queue also refreshes while signed in.
- Queue-position API enforces order ownership and does not expose personal details on the public board.
- This release uses short-interval HTTP polling rather than WebSockets/SSE; updates are near-real-time, not instantaneous.


## Phase 10 — Staff workflow (implemented)
- Separate kitchen board lists paid orders in pending, confirmed, or preparing states; actions only expose valid next steps for the kitchen workflow.
- Pickup counter board lists ready orders and allows staff to mark them completed after collection.
- Staff summary endpoint reports waiting, preparing, ready-for-pickup, and completed-today counts; it is protected for staff/admin roles.
- Boards and counts refresh on demand and every 15 seconds while staff/admin is signed in. Server-side role and state-transition validation remains authoritative.


## Phase 11 — Inventory control (implemented)
- Every application-managed stock change is recorded with signed quantity delta, before/after quantities, reason, timestamp, actor where available, and order reference where applicable.
- New products record opening stock; demo seed data records opening stock; checkout reservations and failed/expired reservation releases are ledgered; manual receipts, physical counts, write-offs, catalogue edits, and archival stock removal are recorded.
- Migration `0006_inventory_ledger` adds the per-product low-stock threshold and explicit archive flag, creates the ledger, and backfills opening-balance movements for existing positive stock.
- Staff/admin inventory UI provides product/type-filtered movement history, stock receipt, physical-count adjustment, write-off, configurable alert thresholds, and low/out-of-stock alert cards.
- Inventory API routes are protected by staff/admin role checks. Negative quantities and over-large write-offs are rejected.
- The dashboard refreshes every 30 seconds while visible and authorized. This is polling, not push delivery.


## Phase 12 — Admin reporting and audit trail (implemented)
- Admin-only reporting endpoints provide date-filtered paid revenue, paid/all order counts, average paid order value, order counts by lifecycle status, daily paid sales, and top-selling products by quantity and sales.
- The reporting UI includes date filters, KPI cards, daily sales table, top products, status summary, and CSV export for daily sales.
- The append-only `audit_events` table records key user role/activation changes, product create/update/archive actions, inventory adjustments/threshold changes, and order status transitions.
- Admin-only audit search supports action and entity filters and shows actor, entity, timestamp, and event details. Student and staff roles cannot access financial reports or the admin audit feed.
- Migration `0007_admin_reporting_audit` adds the audit table and indexes. Back up the database before applying migrations to an existing installation.
- Reports use paid orders for revenue and exclude pending/failed/refunded payments from paid sales. Dates use the server's calendar date; confirm deployment timezone settings before financial reconciliation.


## Phase 13 — In-app notifications (implemented)
- Durable `notifications` table stores per-user notification type, title, message, related entity, read state, creation time, and read time. Migration `0008_in_app_notifications` adds the table and indexes.
- Authenticated inbox endpoint returns only the current user's notifications and unread count; read-one checks ownership and read-all affects only the signed-in user.
- Payment verification/webhook reconciliation generates payment notifications; valid order-status transitions notify the customer; inventory adjustments at or below the configured threshold notify active staff/admin accounts.
- The account panel includes a notification center with unread state, timestamps, mark-as-read and mark-all-read actions. It polls every 20 seconds while visible and signed in.
- Notifications are in-app only. Email, SMS, browser push, and external delivery providers are not enabled or claimed.


## Phase 14 — Security hardening (implemented)
- Responses include `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, and a Content Security Policy that permits same-origin assets and Razorpay checkout origins. HSTS is added only when production mode receives an HTTPS request.
- Requests declaring a body larger than 1 MiB are rejected with HTTP 413; malformed `Content-Length` is rejected with HTTP 400. The reverse proxy must independently cap chunked/streamed requests.
- `ENVIRONMENT=production` requires a non-default secret, `AUTO_CREATE_TABLES=false`, and `SEED_DEMO_DATA=false`. `/docs`, `/redoc`, and `/openapi.json` are disabled in production. Apply Alembic migrations as an explicit deployment step.
- Tests cover headers, malformed content length, and oversized declared payloads. Existing per-IP/email login throttling remains in-memory and is not shared across workers.
- Not yet certified: automated real-browser E2E, dependency vulnerability scan, third-party security review, and live payment transaction.


## Phase 15 — Deployment and campus pilot
- `Dockerfile` runs the app as a non-root user; `docker-compose.yml` defines PostgreSQL, database health checks, explicit Alembic migration job, and application readiness checks. PostgreSQL is not published to the host, and the app port binds to loopback by default.
- `deploy/nginx-https-example.conf` documents HTTPS reverse proxying, a request body cap, and forwarding of `X-Request-ID`. The sample hostname and certificate paths must be replaced.
- All responses include a request ID; valid caller IDs are constrained to letters, digits, hyphens, and underscores. Logs include status and elapsed time without request body/query logging.
- `scripts/backup_db.ps1` and `scripts/backup_db.sh` provide timestamped backup helpers. Protect backups and test restore procedures before launch.
- `docs/PHASE15-DEPLOYMENT.md` contains the Docker runbook, admin bootstrap guidance, backup/restore notes, and pilot checklist.
- Not certified until tested on the target host: Docker/PostgreSQL integration, proxy TLS, real backup restore, external monitoring, browser E2E, dependency scanning, penetration testing, and Razorpay live payments. Process-local login throttling remains a multi-replica limitation.


## Phase 15 — Deployment and campus pilot
- `Dockerfile` runs the app as a non-root user; `docker-compose.yml` defines PostgreSQL, database health checks, explicit Alembic migration job, and application readiness checks. PostgreSQL is not published to the host, and the app port binds to loopback by default.
- `deploy/nginx-https-example.conf` documents HTTPS reverse proxying, a request body cap, and forwarding of `X-Request-ID`. The sample hostname and certificate paths must be replaced.
- All responses include a request ID; valid caller IDs are constrained to letters, digits, hyphens, and underscores. Logs include status and elapsed time without request body/query logging.
- `scripts/backup_db.ps1` and `scripts/backup_db.sh` provide timestamped backup helpers. Protect backups and test restore procedures before launch.
- `docs/PHASE15-DEPLOYMENT.md` contains the Docker runbook, admin bootstrap guidance, backup/restore notes, and pilot checklist.
- Not certified until tested on the target host: Docker/PostgreSQL integration, proxy TLS, real backup restore, external monitoring, browser E2E, dependency scanning, penetration testing, and Razorpay live payments. Process-local login throttling remains a multi-replica limitation.


## Phase 16 — Student-friendly saved items and reorder assistance
- Student-only persistent favorites with per-user ownership and duplicate-safe writes.
- Catalogue cards expose a Save action; unauthenticated visitors are guided to sign in.
- Reorder quote endpoint reads only the student's own historical order, refreshes prices/stock, caps quantities, and reports unavailable items. It never charges payment or silently recreates an order.
- Migration: `0009_student_favorites`.

## Campus launch readiness (Phases 17–21 roadmap)
The project includes operational, security, deployment and reporting foundations. Before a live campus launch, run browser E2E tests, concurrency/load tests, real Razorpay sandbox/webhook reconciliation (refunds are intentionally not supported), backup restore drills, HTTPS deployment verification, accessibility checks, and a supervised pilot. These require environment credentials and infrastructure and must not be considered passed merely because unit tests pass.


## Phase 17 — Student feedback
- Students can submit or update a 1–5 rating and optional comment only for their own paid, completed orders.
- One review is permitted per order; reviews are linked to verified order ownership.
- Staff/admin can view aggregate ratings and the latest feedback for service improvement.
- Migration: `0010_order_feedback`.

## Phase 18 — Payment webhook idempotency

- Persist provider webhook event IDs under a unique constraint.
- Acknowledge duplicate deliveries without reapplying order/payment/stock side effects.
- Reject malformed JSON and invalid signatures; use a signed-body digest only as a fallback when the provider event ID header is absent.
- Event ledger and order mutations are committed in the same database transaction in the normal processing path.
- Production validation still requires Razorpay test-mode delivery/retry tests and review of concurrent webhook behavior on the target database.


### No-refunds policy
This application does not provide refund requests, refund processing, or refund buttons. Paid orders cannot be cancelled by students through the application. Before enabling real payments, the college must display its no-refunds policy clearly before checkout and ensure it complies with applicable law and payment-provider rules. Payment failures and duplicate webhook deliveries must still be reconciled; these are not refund features.

## Phase 24 — production deployment hardening

Adds a secret-safe deployment preflight with blocking production configuration checks, JSON output for CI, PowerShell/POSIX wrappers, tests, and a production deployment sequence. This is a pre-deployment guardrail, not an automated cloud deployment.
