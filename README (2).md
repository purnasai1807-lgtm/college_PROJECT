# ACE Canteen — Phases 1–15

A student-friendly college canteen and stationery application with secure role-based accounts, Razorpay checkout integration, live order tracking, staff workflow dashboards, and an auditable inventory system.

## Implemented in this release

### Phase 1 — Application foundation
- FastAPI backend and same-origin static frontend (HTML, CSS, vanilla JavaScript).
- Responsive homepage, logging, request validation errors, health and readiness endpoints.
- OpenAPI documentation at `/docs` in development; disabled in production mode.

### Phase 2 — Database and catalogue
- SQLAlchemy models for users, categories, products, orders and order items.
- Alembic schema migrations, including database-level checks for valid product prices, stock quantities, item types and future order values.
- SQLite configured by default for easy local startup; PostgreSQL supported through `DATABASE_URL`.
- Idempotent sample food and stationery data.
- Database-backed category/product listing and product detail endpoints, search across names/descriptions/categories, type/category filtering, sort order, bounded pagination, and catalogue summary APIs.

### Phase 3 — Authentication and access control
- Student registration (public registration cannot assign privileged roles).
- Login with PBKDF2-HMAC password hashing and signed, expiring bearer tokens.
- Per-IP-and-email login throttling after repeated failed attempts (in-memory for local development).
- `GET /api/auth/me` current-user endpoint and authenticated password change.
- Password change invalidates existing bearer sessions.
- Admin-only user listing, role updates, and account activation/deactivation, with a role-gated admin UI.
- Admin-only category creation; staff/admin product creation.
- Staff dashboard protected by role checks.
- Admin bootstrap command prompts for a password without echoing it.

### Phase 4 — Live catalogue and management
- Student-facing food and stationery catalogue with search, item type and category filters.
- Category names and stock counts are read from the database.
- Staff/admin can create, update details, price, stock, image URL, dietary/allergen notes and availability, or archive products without deleting records.
- Admins can create, rename, edit, archive/reactivate categories and manage account roles/status from the UI.
- Backend validates product/category type consistency, image URL schemes, prices, stock, names, duplicate category data, and protects management routes by role.

### Phase 11 — Inventory control (implemented)
- Immutable stock movement ledger for opening balances, supplier receipts, physical count adjustments, write-offs, checkout reservations, and released reservations. Records include before/after quantities, signed delta, reason, actor where available, order reference where applicable, and timestamp.
- Per-product low-stock threshold and automatic low-stock/out-of-stock alert summary for staff/admin.
- Staff/admin stock adjustment form with validation that prevents negative inventory; the physical-count mode sets the counted quantity.
- Ledger filtering by product and movement type; existing stock is captured as an opening balance when the migration runs.
- Soft-archived products are excluded from operational low-stock alerts and remain in the catalogue-management archive.
- Inventory APIs: `GET /api/admin/inventory/summary`, `GET /api/admin/inventory/movements`, `POST /api/admin/inventory/adjustments`, and `PATCH /api/admin/inventory/products/{product_id}/threshold`. All require staff/admin roles.

## Requirements
- Python 3.11+
- Windows 10/11, macOS, or Linux
- Internet access for first-time dependency installation

## Run on Windows 11
Run these commands from the extracted project root (the folder containing `README.md`):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Copy-Item .env.example .env
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir backend --reload
```

If PowerShell blocks virtual-environment activation, use Command Prompt:

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
copy .env.example .env
set PYTHONPATH=backend
python -m uvicorn app.main:app --app-dir backend --reload
```

Open:
- Website: http://127.0.0.1:8000/
- Interactive API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health
- Database readiness: http://127.0.0.1:8000/api/ready
- Catalogue: http://127.0.0.1:8000/api/products

Run the Alembic migration command before the first start and after every application upgrade so existing databases receive new columns and tables. The app can then create missing tables and seed demo catalogue records on startup when `AUTO_CREATE_TABLES=true` and `SEED_DEMO_DATA=true`. The default database file is `backend/ace_canteen.db`.

## Create the first administrator
Open a second terminal in the project root, activate the same `.venv`, then run:

```powershell
$env:PYTHONPATH = "backend"
python -m app.create_admin --email admin@college.edu --name "Canteen Admin"
```

Type a strong password when prompted (minimum 12 characters). This command creates the account or promotes an existing account with that email to admin. Keep access to this command restricted to the machine operator. Public registration always creates student accounts only.

## Authentication API
- `POST /api/auth/register` — `{ "full_name": "Student Name", "email": "student@college.edu", "password": "at-least-12-chars" }`
- `POST /api/auth/login` — returns `access_token`, `token_type`, expiry, and safe user profile.
- `GET /api/auth/me` — requires `Authorization: Bearer <access_token>`.
- `GET /api/admin/users` — admin only.
- `PATCH /api/admin/users/{user_id}/role` — admin only; body `{ "role": "student" }`, `staff`, or `admin`.
- `PATCH /api/admin/users/{user_id}/active?active=false` — admin only.
- `GET/POST /api/admin/categories` and `PATCH /api/admin/categories/{category_id}` — admin only.
- `GET/POST /api/admin/products` — staff/admin list all products (including archived) and create products.
- `PATCH/DELETE /api/admin/products/{product_id}` — staff/admin update or archive a product (soft archive; records are retained).
- `POST /api/auth/change-password` — authenticated user; new password must be at least 12 characters and existing sessions are invalidated.
- `GET /api/staff/dashboard` — staff/admin only.

## Database migrations
The app can create tables automatically for local development. To use Alembic migrations explicitly:

```powershell
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
```

For PostgreSQL, set `DATABASE_URL` in `.env` to a valid SQLAlchemy URL such as `postgresql+psycopg://user:password@localhost:5432/ace_canteen`. Create the database and use a strong unique `SECRET_KEY` before deployment.

## Tests
From the project root with `.venv` active:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend\tests -q
```

The automated suite covers foundation endpoints, catalogue filtering/search/sorting/pagination, registration/login, password changes and session invalidation, role restrictions, product metadata/image validation, category management, staff/admin catalogue operations, login throttling, database integrity constraints, idempotent seeding, inventory receipts/write-offs, thresholds, ledger records, and inventory route permissions. Razorpay end-to-end payments require your own provider test credentials. PostgreSQL needs a running PostgreSQL service for an actual integration test.

## Security and scope notes
- `.env.example` contains a development-only signing secret. Set `SECRET_KEY` to a long random value in `.env` before use outside local development; never commit real secrets.
- Tokens are bearer credentials; keep them private and use HTTPS in deployment. The sample browser UI keeps the token in memory only and does not persist it.
- This is a local development release, not a production security audit. Replace the in-memory login limiter with a shared Redis-backed limiter for multi-worker deployments; add email verification/password reset, HTTPS/reverse-proxy configuration, backups, monitoring, and security review before a public launch.
- **Not implemented yet:** refunds, email/push notifications, WebSocket transport, and production deployment hardening. Order updates use polling. Razorpay integration is implemented but requires valid provider credentials and real end-to-end testing before accepting payments.

### Phase 4 — Catalogue experience and staff management
- Live food/stationery catalogue UI with text search, item-type filtering, category filtering, availability and stock display.
- Staff/admin product creation and editing (price, stock and availability) through protected APIs and a role-gated management panel.
- Product archival uses soft-disable rather than hard-delete, preserving product references for future order history.
- Admin-only category creation and activation/description updates.
- API validation enforces category/item-type consistency and prevents public users from changing the catalogue.

Additional catalogue endpoints:
- `GET /api/products/{product_id}` — public detail lookup for available in-stock products.
- `GET /api/admin/products` — staff/admin-only list including archived products. Public requests to `/api/products?available_only=false` are rejected.
- `PATCH /api/admin/products/{product_id}` — staff/admin update product fields.
- `DELETE /api/admin/products/{product_id}` — staff/admin archive product.
- `PATCH /api/admin/categories/{category_id}` — admin update category name, description or active status.

The browser keeps the bearer token in memory only. Reloading the page requires signing in again. Password reset by email, email verification, distributed rate limiting, audit logging, backups, monitoring and deployment hardening remain necessary before a public production launch.


### Phase 5 — Cart and checkout
- Student-only multi-item cart with quantity increment/decrement, remove item, clear cart, and optional order notes. The cart is stored in browser local storage for convenience; checkout always revalidates prices and availability on the server.
- `POST /api/orders/quote` validates product IDs, availability, active categories and stock, merges repeated product IDs, and returns server-calculated line totals and subtotal without reserving stock.
- Checkout confirms the total before creating an order. The order endpoint performs its own stock and availability validation, stores a price/name snapshot, decrements stock in the same database transaction, and returns the daily pickup token. Failed checkout keeps the cart so the student can adjust and retry.
- Checkout now hands off to the Phase 6 Razorpay payment flow; paid status is set only after server-side verification.


## Phase 6: Razorpay test/live payments

1. Create a Razorpay account and use **Test Mode** keys first.
2. Copy `.env.example` to `.env`, then set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and a strong `SECRET_KEY`. Never commit `.env` or expose the secret key in frontend code.
3. Run database migrations: `python -m alembic -c backend/alembic.ini upgrade head`.
4. Configure a Razorpay webhook to `https://YOUR-DOMAIN/api/payments/webhook` with the event `payment.captured`; set the same webhook secret as `RAZORPAY_WEBHOOK_SECRET`.
5. Test the entire payment flow using Razorpay's current test credentials and supported test payment methods. Switch to live keys only after testing and account activation.

The application verifies the Razorpay checkout signature on the server before marking an order paid. A payment provider account and valid keys are required; without them, checkout intentionally returns a clear configuration error rather than pretending payment succeeded.


## Phase 7: order lifecycle and admin setup

The student order history shows payment and preparation status. The staff/admin queue only lists verified paid orders. Staff can move paid orders through `pending → confirmed → preparing → ready → completed`; invalid transitions are rejected by the API. Paid-order cancellation and refunds are intentionally not offered; clearly disclose the no-refunds policy to students before checkout. The queue can be refreshed manually.

Create the administrator account once after installing dependencies and configuring `.env`:

```powershell
$env:PYTHONPATH = "backend"
python -m app.create_admin --email purnasai1807@gmail.com --name "ACE Canteen Admin"
```

Enter the administrator password at the hidden prompt. The password is stored as a salted hash and is not embedded in the source code or ZIP. The setup command accepts 8+ characters for local compatibility; use a long, unique password before exposing the application to the internet and change it from the account panel after signing in.


## Phase 8: daily pickup tokens and queue board
The public pickup board at the bottom of the homepage shows token numbers and order states for paid active orders today. It does not show student names or email addresses. Preparing and ready tokens are highlighted separately. Estimated wait is a rough five-minute-per-active-order estimate, not a service guarantee. The board refreshes automatically. Authenticated users can query `/api/orders/{order_id}/queue-position`; students can only query their own orders, while staff/admin may query operational orders.

API endpoints: `GET /api/queue/overview` (public, privacy-safe), `GET /api/orders/{order_id}/queue-position` (authenticated and ownership-checked), and `GET /api/admin/orders` (staff/admin only).


## Phase 9 — Live order tracking
The header has a top-right Account shortcut. For students, each active paid order shows a live tracking panel with queue position, status, and an approximate wait estimate. Student order history, the staff/admin queue, and the privacy-safe public pickup board refresh every 15 seconds and when the tab becomes visible. Updates use HTTP polling (not WebSockets), so they are near-real-time rather than instantaneous. Queue-position reads require authentication and enforce order ownership.


## Phase 12 — Admin reports and audit trail
Sign in as an administrator to access date-filtered revenue/order KPIs, daily paid sales, top-selling products, CSV export, and the audit trail. Reporting and audit APIs are admin-only. Run `python -m alembic -c backend/alembic.ini upgrade head` before launching an existing installation to apply the Phase 12 migration.


## Phase 13 notifications
The account area contains a persistent in-app notification inbox. It surfaces payment confirmations, order status changes, and low-stock alerts for staff/admin users. Notifications can be marked read individually or in bulk and refresh automatically while the page is visible. Email/SMS/browser push delivery is not configured. Run the latest Alembic migrations before starting an existing installation.


### Phase 14 — Security hardening (implemented)
- Adds baseline security headers: Content Security Policy compatible with the Razorpay checkout flow, frame protection, MIME sniffing protection, referrer policy, permissions policy, and cross-origin opener policy. HSTS is only added for production requests served over HTTPS.
- Rejects requests with invalid `Content-Length` and declared request bodies larger than 1 MiB. Configure the reverse proxy/web server to enforce the same limit for chunked requests.
- Production settings reject the default development signing secret, demo-data seeding, and automatic schema creation. Production API docs/OpenAPI endpoints are disabled. Apply Alembic migrations explicitly before startup.
- Adds automated tests for security headers and request-size handling. Login throttling remains process-local; use a shared rate-limit store such as Redis behind a trusted proxy for multi-worker/public deployments.
- Verification performed locally: pytest suite and JavaScript syntax check. This is not a substitute for a third-party penetration test, browser-based end-to-end run, or a live Razorpay payment test.

## Production configuration checklist
1. Set `ENVIRONMENT=production`, a unique random `SECRET_KEY` (at least 32 characters), `AUTO_CREATE_TABLES=false`, and `SEED_DEMO_DATA=false`.
2. Use PostgreSQL with restricted credentials and TLS where supported; do not use the demo SQLite database for a public production deployment.
3. Run `python -m alembic -c backend/alembic.ini upgrade head` as a deployment step before starting the server.
4. Terminate HTTPS at a correctly configured reverse proxy, set request-body limits there, and restrict direct access to the application port.
5. Configure Razorpay keys and webhook secret in the deployment environment; never commit real credentials. Back up the database and test restoration before launch.
6. Use a shared login rate limiter for multiple workers, monitoring, and a documented incident/restore process before inviting real users.


### Phase 15 — Deployment and campus pilot (implemented starter kit)
- Adds a non-root Python Docker image, Docker Compose with PostgreSQL, database health checks, an explicit Alembic migration job, and an app readiness health check. The application port binds to `127.0.0.1` by default rather than exposing it directly to the internet.
- Adds an example HTTPS Nginx reverse-proxy configuration with a 1 MiB request limit, forwarded protocol/IP headers, and request ID forwarding. Replace example host/certificate paths and validate the config in the deployment environment.
- Adds response `X-Request-ID` correlation and request duration/status logging without logging request bodies or query strings. `/api/health` is liveness; `/api/ready` checks database connectivity.
- Adds timestamped backup scripts for local SQLite and Docker Compose PostgreSQL, plus restore and campus-pilot checklists in `docs/PHASE15-DEPLOYMENT.md`. SQLite backups should be taken with the app stopped; backups must be protected because they contain personal/order data.
- The container stack, actual PostgreSQL service, reverse proxy, backup restore, browser E2E, dependency scanning, and live Razorpay transactions still need to be exercised in the target environment. Login throttling is still process-local; use shared rate limiting before scaling to multiple replicas.

## Docker deployment quick start

1. Copy `.env.example` to `.env`; set `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`, a unique random `SECRET_KEY`, and a strong URL-safe `POSTGRES_PASSWORD`.
2. Run `docker compose up -d db`.
3. Apply schema migrations explicitly with `docker compose --profile ops run --rm migrate`.
4. Run `docker compose up -d --build app`.
5. Check `http://127.0.0.1:8000/api/health` and `/api/ready`.
6. Review `docs/PHASE15-DEPLOYMENT.md` before exposing the app remotely. Do not expose the app or database directly to the public internet; configure HTTPS at a reverse proxy.

Backup helpers: `powershell -ExecutionPolicy Bypass -File scripts/backup_db.ps1` on Windows, or `./scripts/backup_db.sh` on Linux/macOS.


### Phase 15 — Deployment and campus pilot (starter kit implemented)
- Adds a non-root Python Docker image, Docker Compose with PostgreSQL, database health checks, an explicit Alembic migration job, and an app readiness health check. The application port binds to `127.0.0.1` by default rather than exposing it directly to the internet.
- Adds an example HTTPS Nginx reverse-proxy configuration with a 1 MiB request limit, forwarded protocol/IP headers, and request ID forwarding. Replace example host/certificate paths and validate the config in the deployment environment.
- Adds response `X-Request-ID` correlation and request duration/status logging without logging request bodies or query strings. `/api/health` is liveness; `/api/ready` checks database connectivity.
- Adds timestamped backup scripts for local SQLite and Docker Compose PostgreSQL, plus restore and campus-pilot checklists in `docs/PHASE15-DEPLOYMENT.md`. SQLite backups should be taken with the app stopped; backups must be protected because they contain personal/order data.
- The container stack, actual PostgreSQL service, reverse proxy, backup restore, browser E2E, dependency scanning, and live Razorpay transactions still need to be exercised in the target environment. Login throttling is still process-local; use shared rate limiting before scaling to multiple replicas.

## Docker deployment quick start

1. Copy `.env.example` to `.env`; set `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`, a unique random `SECRET_KEY`, and a strong URL-safe `POSTGRES_PASSWORD`.
2. Run `docker compose up -d db`.
3. Apply schema migrations explicitly with `docker compose --profile ops run --rm migrate`.
4. Run `docker compose up -d --build app`.
5. Check `http://127.0.0.1:8000/api/health` and `/api/ready`.
6. Review `docs/PHASE15-DEPLOYMENT.md` before exposing the app remotely. Do not expose the app or database directly to the public internet; configure HTTPS at a reverse proxy.

Backup helpers: `powershell -ExecutionPolicy Bypass -File scripts/backup_db.ps1` on Windows, or `./scripts/backup_db.sh` on Linux/macOS.


### Phase 16 — Student favourites and safe reorder quote
Students can save catalogue items to a server-side favourites list. On past orders, the API can prepare a fresh reorder quote using current prices and stock, while listing unavailable items and avoiding stale or automatic charges. Run the Alembic migration before using these endpoints.

**Before campus launch:** verify the complete checkout in a Razorpay test account, duplicate webhooks, multi-user stock contention, browser accessibility, production HTTPS, monitoring and database restore procedures. This project follows a no-refunds policy: refund processing and refund requests are not offered or implemented; configure payment/order support messaging to make this policy clear before accepting payment. Unit-test success alone is not a production certification.


### Phase 17: Student feedback
After a paid order reaches **Completed**, a student can submit a 1–5 star rating and optional comment through `POST /api/orders/{order_id}/review`. Staff/admin can read the aggregate at `GET /api/feedback/summary`. Apply migrations before running the updated app.

### Phase 18: Payment webhook idempotency

Razorpay webhook deliveries are recorded in `payment_webhook_events` with a unique event key. Repeated deliveries with the same `X-Razorpay-Event-Id` are acknowledged without repeating stock release, payment state changes, notifications, or audit side effects. If the provider event ID header is absent, a SHA-256 digest of the signed request body is used as a deterministic fallback. Invalid signatures and malformed JSON are rejected. Apply the new migration before starting the updated application.


### No-refunds policy
This application does not provide refund requests, refund processing, or refund buttons. Paid orders cannot be cancelled by students through the application. Before enabling real payments, the college must display its no-refunds policy clearly before checkout and ensure it complies with applicable law and payment-provider rules. Payment failures and duplicate webhook deliveries must still be reconciled; these are not refund features.


## Phase 19 — Campus pilot validation

See `docs/PHASE19-CAMPUS-PILOT.md` for the staged rollout checklist and repeatable smoke tests. Refund functionality remains intentionally out of scope.
