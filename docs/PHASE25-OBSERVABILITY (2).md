# Phase 25 — Operational metrics and request tracing

This phase adds lightweight process-local aggregate metrics for operational troubleshooting. It does not add a third-party telemetry dependency.

## Available checks

- `GET /api/health`: liveness response.
- `GET /api/ready`: checks database connectivity.
- `GET /api/metrics`: aggregate request counts (total, 4xx, 5xx) and response-duration sum/max for this process.
- Every successfully returned HTTP response includes `X-Request-ID`. A valid caller-provided ID containing only letters, digits, `_` or `-` is retained; otherwise the server creates one.

Metrics intentionally do not expose URL paths, query strings, account identifiers, or request contents. Metrics are process-local and reset when the process restarts; they are not a replacement for a durable monitoring backend.

## Production access

In production, `/api/metrics` is hidden unless `METRICS_TOKEN` is configured. When configured, the caller must send `Authorization: Bearer <METRICS_TOKEN>`. Use a long random token from the deployment secret manager and restrict this endpoint at the reverse proxy/network layer too. Do not commit the token to source control.

## Local verification

Start the app, then run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/ready
Invoke-RestMethod http://127.0.0.1:8000/api/metrics
```

For production metrics, attach the bearer header without placing the token in shell history where avoidable. Add a monitoring agent to scrape metrics and alert on sustained 5xx rates, failed readiness checks, or latency growth. Multi-worker deployments need a shared metrics backend because each process keeps independent counters.

## Test scope

Automated tests cover response structure, request ID propagation, and aggregate-only metric fields. These tests do not validate external monitoring, multi-process aggregation, production reverse-proxy access rules, or live incident alerts.
