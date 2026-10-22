# ACE Canteen k6 load test

This test is deliberately read-only: homepage, database readiness (`SELECT 1`), categories, product catalogue, and canteen status. It does not register accounts, create orders, send email, or call Razorpay/payment APIs.

## Safety

- Default target is `http://127.0.0.1:8000`.
- `collegeproject-sandy.vercel.app` and all `*.vercel.app` hosts are blocked by the script.
- Non-local targets are blocked unless `K6_ALLOW_STAGING=true` and the hostname includes `staging`, `stage`, `preprod`, or `test` as a hostname label. Only use a staging environment you own and have permission to test.
- Do not point this test at production. The 100-VU stage can put meaningful load on a small instance/database.

## Install k6 on Windows PowerShell

Recommended (Windows Package Manager):

```powershell
winget install k6 --source winget
```

Close and reopen PowerShell, then verify:

```powershell
k6 version
```

If `winget` is unavailable, install k6 from its official Windows installation guide: https://grafana.com/docs/k6/latest/set-up/install-k6/ .

## Start the app locally

From the project root in a first PowerShell terminal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start_local.ps1
```

Keep that terminal open. In a second terminal, confirm the local app is ready:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/ready
```

If the app already runs locally, do not start a second copy. Use a local development/test database; do not point a high-load test at a production database through a local tunnel.

## Run the load test

From the project root:

```powershell
k6 run .\loadtest\k6-canteen.js
```

Save a result for comparison:

```powershell
k6 run --summary-export .\loadtest\summary-local.json .\loadtest\k6-canteen.js
```

Stages: ramp to 20 VUs and hold 2 minutes; ramp to 50 and hold 2 minutes; ramp to 100 and hold 3 minutes; then ramp down. A VU repeats the five read-only requests with 1–3 second pauses.

Thresholds:

- `http_req_duration` p95 < 500 ms
- `http_req_failed` rate < 1%
- workflow-level failed checks < 1%
- product, category, and canteen-status p95 < 500 ms

## Optional dedicated staging environment

Use only a dedicated staging hostname, for example `https://staging.example.edu`, with permission to test and staging-only database/data. Set:

```powershell
$env:BASE_URL = 'https://staging.example.edu'
$env:K6_ALLOW_STAGING = 'true'
k6 run .\loadtest\k6-canteen.js
Remove-Item Env:BASE_URL
Remove-Item Env:K6_ALLOW_STAGING
```

The script refuses the known production Vercel host and all `*.vercel.app` domains even if the override is set.

## Reading results

- `http_req_duration p(95)`: 95% of requests finish at or below this latency. If it exceeds 500 ms, inspect the endpoint-specific p95 values.
- `http_req_failed`: fraction of requests with transport errors or unexpected HTTP status codes. Above 1% fails the test.
- The first VU stage where latency rises or failures begin is the approximate onset of saturation for this workload, not a universal maximum user count.
- If readiness degrades first, investigate DB connection pool/database capacity. If catalogue endpoints degrade first, inspect query plans, indexes, and response size. If all endpoints degrade together, check CPU, memory, worker count, and connection limits.

This script does not measure login throughput or authenticated order history. Do not load-test login with one shared account because account/IP rate limiting would distort results and can lock out the test account. Add a dedicated staging-only auth scenario with test accounts if login is a required capacity target.
