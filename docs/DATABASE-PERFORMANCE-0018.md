# Database read-path indexing review — migration 0018

## Scope and limitations

This review inspected the SQLAlchemy read paths in `backend/app/main.py` and the local SQLite database at `backend/ace_canteen.db` (92 orders, 437 users, 66 products, 30 order items, 313 audit events, and 102 inventory movements at review time). The app is configured to use PostgreSQL in production, but no production PostgreSQL connection or credentials were available in this environment. Therefore:

- `pg_stat_statements` was **not** queried, and production query frequency/latency is unknown.
- PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` was **not** run. Only read-only SQLite `EXPLAIN QUERY PLAN` and a small local timing comparison were performed.
- SQLite's small local dataset is not representative of production-scale latency. Times below are illustrative local medians/averages from 1,000 executions, not production promises.
- Index usage counters are not available for this SQLite database, so no existing index can honestly be labeled “never used.” A production PostgreSQL usage query is included below.

## Added indexes and query mapping

Migration `0018_read_path_indexes.py` adds these indexes. On PostgreSQL it uses `CREATE INDEX CONCURRENTLY` inside Alembic's autocommit block; SQLite test/development databases use ordinary `CREATE INDEX`. The migration is reversible.

| Index | Query/read path helped | Why |
|---|---|---|
| `ix_orders_user_created (user_id, created_at, id)` | `GET /api/orders/mine` | Equality filter by owner followed by newest-first order history; avoids scanning all orders for a user. |
| `ix_orders_payment_created (payment_status, created_at, id)` | Admin payment reconciliation and filtered payment/order listings | Filters by payment state and reads recent rows first. Also supports payment-state dashboard lookups. |
| `ix_orders_queue_lookup (token_date, payment_status, created_at, id, status)` | Public queue overview and queue-position lookup | Uses date + paid-state equality and preserves creation-time ordering; status is included for the queue filter. |
| `ix_audit_events_entity_created (entity_type, entity_id, created_at, id)` | Order investigation/audit history | Filters audit records to one entity and sorts its timeline chronologically. |
| `ix_inventory_movements_order_created (order_id, created_at, id)` | Order investigation/inventory movement history | Fetches movements for one order in chronological order instead of scanning movement history. |

Existing indexes were retained. Some may overlap with these indexes, but dropping any without PostgreSQL usage statistics would be guesswork and could regress writes/reads. In particular, `ix_orders_status_created`, the single-column audit timestamp index, and the inventory timestamp index may still serve other routes.

## Read-query plan findings (local SQLite, before index migration)

The representative queries below are read-only. “Scan” means the plan indicates a full table/index scan; plans can differ by engine, statistics, data distribution, and table size.

| Read path | Before plan | Plain-English interpretation |
|---|---|---|
| Student order history: `WHERE user_id = ? ORDER BY created_at DESC LIMIT 100` | `SCAN orders; USE TEMP B-TREE FOR ORDER BY` | Scans all orders and sorts them to find the current student's latest 100. |
| Payment reconciliation: `payment_status IN (...) ORDER BY created_at DESC LIMIT 500` | `SCAN orders; USE TEMP B-TREE FOR ORDER BY` | Scans all orders and sorts before returning matching payment states. |
| Pickup queue: date + paid state + active statuses, ordered by creation | Used `ix_orders_status_created` for status, then temporary sort | It did not use an index starting with date/payment state; could read many rows for each status and sort. |
| Order audit history: `entity_type = ? AND entity_id = ? ORDER BY created_at` | `SCAN audit_events USING INDEX ix_audit_events_created` | Walks the timestamp index and filters other entities out. |
| Order inventory history: `order_id = ? ORDER BY created_at` | `SCAN inventory_movements USING INDEX ix_inventory_movements_created` | Walks the timestamp index and filters movements for other orders out. |

## Local before/after measurements

Ran each read-only query 1,000 times against the local SQLite file. Values are milliseconds per execution and are noisy because this database is small and most queries return few rows.

| Read path | Before | After | Observed plan after |
|---|---:|---:|---|
| Student order history | 0.0082 ms | 0.0034 ms | `SEARCH orders USING COVERING INDEX ix_orders_user_created (user_id=?)` |
| Payment reconciliation | 0.0095 ms | 0.0065 ms | `SEARCH orders USING COVERING INDEX ix_orders_payment_created (payment_status=?)`; SQLite still uses a temporary sort for the multiple payment states. |
| Pickup queue | 0.0063 ms | 0.0034 ms | With the final index column order, SQLite uses `ix_orders_queue_lookup` for date + payment state and creation ordering. |
| Order audit history | 0.0293 ms | 0.0034 ms | `SEARCH audit_events USING COVERING INDEX ix_audit_events_entity_created (entity_type=? AND entity_id=?)` |
| Order inventory history | 0.0100 ms | 0.0041 ms | `SEARCH inventory_movements USING COVERING INDEX ix_inventory_movements_order_created (order_id=?)` |

These are not PostgreSQL `EXPLAIN ANALYZE` results. After deploying to PostgreSQL, rerun the plan/timing queries in the deployment checklist below before claiming production performance gains.

## PostgreSQL production diagnostics (read-only)

Enable `pg_stat_statements` with your managed provider's supported procedure, then inspect frequent and slow statements:

```sql
SELECT queryid, calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       rows, shared_blks_read, shared_blks_hit,
       left(query, 500) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 30;
```

Run `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` only on SELECT statements copied from the app or the stats view. Do not use `EXPLAIN ANALYZE` on INSERT/UPDATE/DELETE, because ANALYZE executes the statement. Use a staging copy with representative data if you need to compare index effects safely.

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, status, payment_status
FROM orders
WHERE user_id = 1
ORDER BY created_at DESC
LIMIT 100;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, status, payment_status
FROM orders
WHERE payment_status IN ('pending', 'failed')
ORDER BY created_at DESC
LIMIT 500;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, status
FROM orders
WHERE token_date = CURRENT_DATE::text
  AND payment_status = 'paid'
  AND status IN ('pending', 'confirmed', 'preparing', 'ready')
ORDER BY created_at, id;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, action, details_json
FROM audit_events
WHERE entity_type = 'order' AND entity_id = '1'
ORDER BY created_at, id;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, product_id, movement_type, quantity_delta
FROM inventory_movements
WHERE order_id = 1
ORDER BY created_at, id;
```

Check indexes with zero recorded scans (these counters reset and only reflect the current stats lifetime):

```sql
SELECT schemaname, relname AS table_name, indexrelname AS index_name,
       idx_scan, idx_tup_read, idx_tup_fetch,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

Do not drop a zero-scan index solely from one snapshot: primary/unique indexes protect constraints, and stats may have reset or the index may support infrequent operational paths. Verify `pg_stat_database.stats_reset`, constraint ownership, and a representative business cycle first.

## Apply and rollback

1. Back up the production database and verify restore procedure.
2. Apply the normal migration command from the project root/environment: `cd backend && alembic upgrade head`.
3. Because PostgreSQL builds each index concurrently, each index build commits independently; a failed concurrent build can leave an invalid index. Check `pg_index.indisvalid` and remove/rebuild any invalid index before retrying.
4. Run the five read-only `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` queries and save results with date, row counts, and `pg_stat_statements` snapshot.
5. Roll back with `cd backend && alembic downgrade 0017_checkout_idempotency` if needed. Downgrade drops only the five indexes, concurrently on PostgreSQL; it does not alter application data.

No application behavior, route, schema data, or business rule is changed by this migration. Index creation consumes disk and adds some write overhead, so retain only indexes confirmed useful by representative PostgreSQL plans/metrics.
