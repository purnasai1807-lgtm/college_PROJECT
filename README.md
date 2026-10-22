# ACE Canteen

Mobile-first canteen ordering software for ACE Engineering College. The application includes student accounts, a food/stationery catalogue, cart and order history, order queue tracking, kitchen and pickup boards, signed QR pickup links, inventory movements, supplier batches and expiry, admin reports, audit history, notifications and an installable web app.

## Role permissions

- **Student:** browse available items, order, see their own order history/QR, follow order status, save favourites and review completed orders.
- **Staff:** manage the order queue, prepare orders, scan pickup QR codes and confirm handover. Staff cannot create/edit/archive catalogue products or change stock/prices.
- **Admin:** manage products, prices, availability, stock, thresholds, categories, suppliers, batches, users, reports and audit records.

The role restrictions are enforced by backend authorization, not only by hiding frontend controls.

## QR pickup behavior

1. A paid order receives a unique signed pickup token.
2. The QR encodes an HTTPS link to `/pickup#code=...`, so a normal Android/iPhone camera can open it without installing a scanner app. The token stays in the URL fragment and is submitted to the API in a POST body to reduce leakage in browser history and access logs.
3. The public page fetches live order status, payment status, product names, quantities, totals, order time, pickup slot and collection time. It deliberately does not disclose student name/email.
4. Authorized staff can scan the same QR from the staff screen. The server validates the token and payment status, checks that the order is ready, and refuses already-collected orders.
5. Confirming handover records `collected_at` in UTC; the public page displays the timestamp in the phone's local time zone.

Treat the QR link like a private order ticket: anyone who has the link can see limited order details. Do not post it publicly.

## Local development

Use Python 3.11+ and Node.js for optional browser tests.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env  # if your checkout contains .env.example
uvicorn app.main:app --app-dir backend --reload
```

Set `DATABASE_URL` to a local SQLite path for development or PostgreSQL for a shared deployment. Keep `SECRET_KEY` unique and at least 32 characters. For production, set `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`, and `PUBLIC_BASE_URL=https://your-real-domain`; configure the database and run migrations before starting the web app.

## Create the first administrator

After setting the production `DATABASE_URL` and applying migrations, run the bootstrap command in the app environment. It prompts for the password without echoing it and requires at least 12 characters:

```bash
python -m app.create_admin --email admin@college.edu --name "Canteen Admin"
```

For Docker Compose, follow the matching command in `docs/GO-LIVE.md`. Never commit the administrator password or use shared demo credentials.

## Database migrations

```bash
PYTHONPATH=backend python -m alembic -c backend/alembic.ini upgrade head
```

Back up the database before applying migrations to an existing installation. Validate migration state against the target database before upgrading a live canteen.

## Tests and local release gate

```bash
python scripts/release_gate.py
```

The local release gate runs backend tests, Python compilation and JavaScript syntax checks. Browser acceptance tests require installing the Playwright dependencies and browser first. A local PASS does **not** certify production hosting, real phone camera permissions, database backups/restores, real concurrent traffic or third-party payment configuration; run those checks in the actual deployment before launch.

## Production launch checklist

- Use HTTPS and a production PostgreSQL database with backups and a tested restore procedure.
- Configure a strong `SECRET_KEY`, migrations, `PUBLIC_BASE_URL`, allowed origins and monitoring/logging.
- Create the first administrator through the project's admin bootstrap procedure; never deploy shared demo credentials.
- Test student/staff/admin permissions, stock reservations under concurrency, cancellations, QR collection and duplicate scans.
- Scan QR links using real Android and iPhone cameras on the deployed HTTPS domain.
- Run load tests and a canteen staff acceptance test before taking real orders.
