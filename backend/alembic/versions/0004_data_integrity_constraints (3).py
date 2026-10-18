"""Add database-level checks for catalogue and future order data."""
from alembic import op
from sqlalchemy import inspect

revision = "0004_integrity_checks"
down_revision = "0003_token_version"
branch_labels = None
depends_on = None

CHECKS = {
    "categories": [("ck_categories_item_type", "item_type IN ('food', 'stationery')")],
    "products": [
        ("ck_products_price_positive", "price > 0"),
        ("ck_products_stock_nonnegative", "stock_quantity >= 0"),
        ("ck_products_item_type", "item_type IN ('food', 'stationery')"),
    ],
    "orders": [("ck_orders_subtotal_nonnegative", "subtotal >= 0")],
    "order_items": [
        ("ck_order_items_quantity_positive", "quantity > 0"),
        ("ck_order_items_unit_price_positive", "unit_price > 0"),
        ("ck_order_items_line_total_nonnegative", "line_total >= 0"),
    ],
}

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    for table, checks in CHECKS.items():
        if table not in inspector.get_table_names():
            continue
        existing = {item.get("name") for item in inspector.get_check_constraints(table)}
        missing = [(name, condition) for name, condition in checks if name not in existing]
        if missing:
            with op.batch_alter_table(table) as batch:
                for name, condition in missing:
                    batch.create_check_constraint(name, condition)
            inspector = inspect(bind)

def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    for table, checks in reversed(list(CHECKS.items())):
        if table not in inspector.get_table_names():
            continue
        existing = {item.get("name") for item in inspector.get_check_constraints(table)}
        present = [name for name, _ in checks if name in existing]
        if present:
            with op.batch_alter_table(table) as batch:
                for name in present:
                    batch.drop_constraint(name, type_="check")
            inspector = inspect(bind)
