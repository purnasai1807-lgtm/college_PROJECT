# HTTP caching policy

This implementation uses HTTP response cache headers first; it does not add Redis or another paid service. Compatible shared CDNs may cache the explicitly public, read-only responses using `s-maxage`. `max-age=0` prevents a browser from reusing the response without revalidation. The short TTL is a safety bound for dynamic inventory and pickup capacity.

| Endpoint | Shared TTL | Rationale |
|---|---:|---|
| `GET /api/categories` | 60 seconds | Category metadata changes infrequently. |
| `GET /api/products` and numeric `GET /api/products/{id}` | 5 seconds | Product stock/availability changes during ordering. |
| `GET /api/catalogue/summary` | 15 seconds | Aggregate counts can tolerate a brief delay. |
| `GET /api/canteen/status` | 5 seconds | Ordering status should refresh quickly. |
| `GET /api/canteen/slots` | 3 seconds | Slot capacity can be consumed by concurrent orders. |
| All other `/api/` GETs | no-store | Private, operational, payment, order, staff and admin responses are excluded by default. |

Responses carrying an `Authorization` header and non-200 responses are marked `no-store`. Query strings remain part of the URL cache key, so different catalogue filters do not share a cache entry.

## Invalidation and limits

HTTP caches expire by TTL; there is no immediate CDN purge integration in this change. Therefore a product/stock update can remain visible to a compatible shared CDN for at most the configured short TTL (5 seconds for products and 3 seconds for pickup slots, excluding intermediary misconfiguration). Categories can remain stale for up to 60 seconds. If immediate invalidation becomes a requirement, add a supported CDN purge/tag mechanism or disable shared caching for the affected endpoint; do not add a process-local cache because it can diverge between Vercel container instances.

This policy reduces origin/database work only when the hosting proxy/CDN honors `s-maxage`. If requests bypass a shared cache, headers alone do not eliminate database queries. Measure CDN hit rate and response latency before considering Redis. No user-specific data is cached under a shared key.

## Verification

From the repository root:

```powershell
cd backend
python -m pytest -q
```

Inspect response headers against a local/staging server:

```powershell
curl.exe -sSI http://127.0.0.1:8000/api/categories
curl.exe -sSI http://127.0.0.1:8000/api/products
curl.exe -sSI http://127.0.0.1:8000/api/canteen/slots
```

Private API responses should include `Cache-Control: no-store`. Public cache policies should only be enabled for routes listed above.
