"""Add targeted indexes for high-frequency read paths.

PostgreSQL indexes are built CONCURRENTLY so writes can continue while the index
is built. SQLite (used for local development/tests) uses ordinary CREATE INDEX.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0018_read_path_indexes"
down_revision = "0017_checkout_idempotency"
branch_labels = None
depends_on = None

# Keep this list intentionally limited to query shapes found in app/main.py.
INDEXES = (
    ("ix_orders_user_created", "orders", ["user_id", "created_at", "id"]),
    ("ix_orders_payment_created", "orders", ["payment_status", "created_at", "id"]),
    ("ix_orders_queue_lookup", "orders", ["token_date", "payment_status", "created_at", "id", "status"]),
    ("ix_audit_events_entity_created", "audit_events", ["entity_type", "entity_id", "created_at", "id"]),
    ("ix_inventory_movements_order_created", "inventory_movements", ["order_id", "created_at", "id"]),
)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    dialect = bind.dialect.name
    for name, table, columns in INDEXES:
        if table not in inspector.get_table_names():
            continue
        existing = {item["name"] for item in inspect(bind).get_indexes(table)}
        if name in existing:
            continue
        if dialect == "postgresql":
            # CONCURRENTLY cannot run inside a transaction block.
            with op.get_context().autocommit_block():
                op.execute(
                    sa.text(
                        f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" '
                        f'ON "{table}" ({", ".join(f"\"{column}\"" for column in columns)})'
                    )
                )
        else:
            op.create_index(name, table, columns, unique=False, if_not_exists=True)


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name
    for name, table, _columns in reversed(INDEXES):
        if dialect == "postgresql":
            with op.get_context().autocommit_block():
                op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"'))
        else:
            existing_tables = set(inspect(bind).get_table_names())
            if table in existing_tables:
                existing = {item["name"] for item in inspect(bind).get_indexes(table)}
                if name in existing:
                    op.drop_index(name, table_name=table)
