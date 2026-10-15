# Phase 15 — Deployment and campus pilot

Phase 15 adds containerized deployment, PostgreSQL for deployments, health checks, request correlation IDs, operational backups, and a reverse-proxy example. It does not claim the application has been deployed to a real campus or that a payment provider transaction has been tested.

## Option A: Windows development (SQLite)

Follow the Windows steps in the root README. Keep `ENVIRONMENT=development` for local use. Never expose the development server directly to the internet.

## Option B: Docker Compose + PostgreSQL

Prerequisites: Docker Desktop with Compose v2. Extract the project and open a terminal in the `clg` root.

1. Copy `.env.example` to `.env`.
2. Set `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`, and set `SECRET_KEY` to a random secret of at least 32 characters. For example, generate one with Python: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Set `POSTGRES_PASSWORD` to a long random password made of URL-safe letters/numbers/underscore/hyphen. The compose file uses it in a database URL, so avoid URI-reserved characters unless you URL-encode the password.
4. Set `DATABASE_URL` in `.env` only as a reminder for other tooling; Compose injects the internal PostgreSQL URL for the app and migration job.
5. Build and start PostgreSQL: `docker compose up -d db`.
6. Run migrations explicitly: `docker compose --profile ops run --rm migrate`.
7. Start the application: `docker compose up -d --build app`.
8. Verify `http://127.0.0.1:8000/api/health` and `http://127.0.0.1:8000/api/ready`.

The application port binds to loopback by default. Put it behind a correctly configured HTTPS reverse proxy before remote access. `deploy/nginx-https-example.conf` is a starting template; replace the example domain and certificate paths. Do not publish PostgreSQL's port publicly.

## Admin bootstrap

With the application container running, create the first admin from the project root using the app image and the same production environment, or run the command from a local Python environment pointed at the same `DATABASE_URL`:

`docker compose exec app python -m app.create_admin --email admin@college.edu --name "Canteen Admin"`

Follow the password prompt. Use a unique long password. Do not place passwords in shell history or source control.

## Backup and restore

- Windows: `powershell -ExecutionPolicy Bypass -File scripts/backup_db.ps1`
- Linux/macOS: `./scripts/backup_db.sh`
- For PostgreSQL, these scripts call `pg_dump` inside the Compose database service and write a timestamped SQL file under `backups/`.
- For SQLite, they copy the local `backend/ace_canteen.db`; stop the application first to avoid capturing a database during a write.
- Backups may contain personal and order information. Store them encrypted with restricted access, define retention, and periodically test restoration to a separate database.
- PostgreSQL restore example: `docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backups/your-backup.sql` (run from a shell where the variables are available). Test this on a non-production database first.

## Pilot checklist

- [ ] Use a dedicated PostgreSQL database/user and a unique production `SECRET_KEY`.
- [ ] Configure HTTPS, DNS, firewall rules, and a reverse proxy with request-body limits.
- [ ] Configure Razorpay test credentials and webhook secret; verify signature and webhook events in provider test mode before considering live mode.
- [ ] Create the admin account and verify role boundaries with student, staff, and admin test accounts.
- [ ] Confirm scheduled backups and complete a restore drill.
- [ ] Monitor application logs and `/api/ready`; use `X-Request-ID` to correlate a reported request with its log entry.
- [ ] Run dependency vulnerability scanning, browser-based end-to-end tests, accessibility checks, and an independent security review.
- [ ] Start with a small campus pilot and a documented process for payment reconciliation, refunds, outages, and data incidents.

## Observability

Each response includes `X-Request-ID`. Valid caller-supplied IDs containing only letters, numbers, hyphens, and underscores are preserved; invalid IDs are replaced. Request logs include the request ID, method, path, status, and duration in milliseconds, and do not intentionally log request bodies or query strings.

The liveness endpoint `/api/health` reports process information. `/api/ready` runs a database query and returns HTTP 503 if the database is unavailable. Neither endpoint is a substitute for an external uptime monitor.

## Explicit limitations

This release is a deployment-ready starting point, not a production certification. Login throttling remains in-process and is not shared across replicas; use a shared limiter and trusted-proxy IP handling for multi-worker deployment. There is no email verification, password-reset delivery, refund workflow, external monitoring integration, or live Razorpay transaction proof. Docker/Compose execution, Nginx syntax, real PostgreSQL connectivity, and restore procedures must be exercised in the target environment before launch.
