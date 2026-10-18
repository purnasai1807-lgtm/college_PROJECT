# Phase 48 — account recovery, forced password change, durable sessions, deploy fixes

## Added
- `POST /api/auth/forgot-password` — emails a single-use reset link (valid `PASSWORD_RESET_MINUTES`, default 30). Always returns the same response, whether or not the email exists. Rate-limited per IP+email.
- `POST /api/auth/reset-password` — sets a new password from the token, signs out every existing session, writes an audit event. The link stops working once used because the token is bound to the current password hash.
- Reset link format is `PUBLIC_BASE_URL/#reset=<token>`; the token is in the URL fragment and removed from the address bar immediately.
- `users.must_change_password` (migration `0014`). Staff/admin accounts created by an admin must change the temporary password: until they do, staff/admin endpoints return 403 and the UI sends them to the password form.
- Sessions persist across refresh (token in `localStorage`, validated by `/api/auth/me`, cleared on sign-out or 401). This matters on phones, where switching to a UPI app can reload the page.
- Optional SMTP settings (`SMTP_*`, `PUBLIC_BASE_URL`). Without SMTP, development prints the link to the server log; production logs a warning and sends nothing.

## Fixed
- **Fresh databases could not be migrated.** Migration `0001` creates tables from the current models, so `0012`, `0013` (and `0014`) failed with "table already exists" on a new database — which is what the Docker `migrate` job runs. They are now idempotent, and a regression test and a CI step cover it.
- Docker image now runs uvicorn with `--proxy-headers`; behind nginx, login throttling previously saw only the proxy's IP and HTTPS/HSTS was not detected.
- `create_admin` documented 12 characters but accepted 8; it now enforces 12, bumps the session version when promoting an existing user, and no longer calls `create_all` on non-SQLite databases.
- Production settings now require an `https://` `PUBLIC_BASE_URL`; the preflight checks it and warns when SMTP is missing.
- Removed 41 accidental duplicate `(2)` files and stale caches from the upload.

## Tests
`python -m pytest backend/tests -q` — includes `test_phase48_account_recovery.py`.
