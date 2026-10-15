# Phase 21 — Installable app shell and offline-safe behavior

## Included

- Web app manifest and install metadata for supported browsers.
- Root-scoped service worker and an install-app button when the browser offers an install prompt.
- A small cached app shell (homepage, CSS, JavaScript, logo, hero art, manifest) for faster repeat visits and offline shell access.
- API endpoints are network-only and never written into Cache Storage, including account, order, catalogue, and payment responses. The worker only caches explicitly listed app-shell resources and ignores query-string variants. Orders and payments cannot be completed offline.
- Updated browser smoke test to correctly assert that guests must sign in before attempting to add items to their cart.

## Run and test

Use `README.md` to start the FastAPI app. Service workers require HTTPS in deployment; `localhost` and `127.0.0.1` are supported for local development. Open browser DevTools → Application → Manifest/Service Workers to inspect installability and cache state. To test offline, first load the app online, then enable Offline in DevTools and reload; the cached shell may appear, while live data and checkout must remain unavailable.

## Limitations and safety

This is an offline-capable app shell, not offline ordering. Catalogue and queue data may be stale only insofar as the browser displays a previously cached shell; API data is never served from cache. The app should show live API errors when disconnected. Real install prompts depend on browser/device eligibility. No refunds or paid-order refund flow is introduced. Live payment, production HTTPS, PostgreSQL, load testing, and backup restore still require deployment-stage verification.
