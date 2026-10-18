# Phase 20 — CI and browser journey tests

## What this phase adds

- GitHub Actions CI on pushes, pull requests, and manual runs.
- Backend pytest suite, frontend JavaScript syntax check, and Docker Compose configuration validation.
- Playwright Chromium browser tests covering branded homepage/catalogue load, item-type filtering and no-results search, add-to-cart/clear-cart behavior, and sign-in/registration form visibility.
- Isolated SQLite database files for CI and browser tests; they do not use the developer's local canteen database.
- Browser trace/screenshot artifacts on CI failure to help diagnose regressions.

## Run locally (Windows PowerShell)

1. Start from the project root and activate your Python virtual environment.
2. Install Python dependencies if not already installed:
   ```powershell
   pip install -r backend\requirements.txt
   ```
3. Install Node.js 20 or newer, then:
   ```powershell
   npm install
   npx playwright install chromium
   $env:PYTHONPATH = "backend"
   $env:DATABASE_URL = "sqlite:///./backend/e2e_canteen.db"
   $env:SECRET_KEY = "local-e2e-only-secret-key-change-this-before-deployment"
   $env:ENVIRONMENT = "development"
   $env:AUTO_CREATE_TABLES = "true"
   $env:SEED_DEMO_DATA = "true"
   npm run test:e2e
   ```
Playwright starts the app automatically on port 8000 if `BASE_URL` is not set. If port 8000 is already in use, stop that process or set `BASE_URL` to a running test instance.

## CI configuration

Add the project to GitHub and push this workflow. GitHub Actions will run both jobs. Branch protection can then require both jobs before a pull request can merge.

## Boundaries

These are smoke-level browser tests, not complete end-to-end payment verification. They do not exercise real Razorpay credentials, live payment capture, production PostgreSQL, deployment secrets, load/concurrency, accessibility audits, or backup restoration. Those remain launch gates. No refund or paid-order refund/cancellation flow is added; the existing no-refunds policy is retained.

## CI maintenance note

The workflow uses `npm install --no-audit --no-fund` because this repository does not commit a lockfile. For reproducible browser-tool dependency resolution, generate and commit `package-lock.json` with Node.js 20 in a trusted development environment, then change the workflow to `npm ci`. The Chromium browser suite must be run locally or in GitHub Actions; Python unit tests and JavaScript syntax checks alone are not browser acceptance.
