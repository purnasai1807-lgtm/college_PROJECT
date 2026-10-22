# ACE Canteen caching optimization

## Implemented

- Added an explicit HTTP cache policy in the existing FastAPI request middleware.
- Public read-only catalogue and canteen endpoints opt into short shared-cache TTLs via `s-maxage`; `max-age=0` avoids browser reuse without revalidation.
- Requests carrying an `Authorization` header, non-200 responses, and all other API GET routes receive `Cache-Control: no-store`.
- Added tests for public TTLs and private-response exclusion.
- Added `docs/performance/CACHING.md` with TTL rationale, operational limits and verification commands.

## Cache TTLs

| Route | Shared cache TTL |
|---|---:|
| `GET /api/categories` | 60 seconds |
| `GET /api/products`, `GET /api/products/{numeric_id}` | 5 seconds |
| `GET /api/catalogue/summary` | 15 seconds |
| `GET /api/canteen/status` | 5 seconds |
| `GET /api/canteen/slots` | 3 seconds |
| Other API GET routes | `no-store` |

## Cost and consistency

No Redis or external caching service was added. There is no new managed-service cost. Shared caching only reduces database work if the hosting CDN/proxy honors `s-maxage`; measure cache-hit rate in staging. HTTP TTL expiry is the invalidation mechanism in this change, so dynamic product and pickup-slot data can be stale for up to 5 and 3 seconds respectively. Immediate CDN purge on write is not configured because this repository has no CDN purge credentials/integration. If strict immediate invalidation is required, keep those endpoints uncacheable until a supported purge/tag mechanism is configured.

## Verification

- `python -m py_compile backend/app/main.py` passed.
- `python -m pytest -q backend/tests/test_main.py -x` passed: 57 tests at the time of the run.
- Running the whole duplicated test tree was not used as the acceptance test; the archive contains duplicate test/source filenames. Run the canonical test module as shown above.
