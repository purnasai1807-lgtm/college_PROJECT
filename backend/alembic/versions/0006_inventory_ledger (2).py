"""Add inventory thresholds and auditable stock movement ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006_inventory_ledger"
down_revision = "0005_payment_gateway"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    product_columns = {c["name"] for c in inspector.get_columns("products")}
    if "low_stock_threshold" not in product_columns or "is_archived" not in product_columns:
        with op.batch_alter_table("products") as batch:
            if "low_stock_threshold" not in product_columns:
                batch.add_column(sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="5"))
            if "is_archived" not in product_columns:
                batch.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "inventory_movements" not in inspect(bind).get_table_names():
        op.create_table(
            "inventory_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("movement_type", sa.String(length=20), nullable=False),
            sa.Column("quantity_delta", sa.Integer(), nullable=False),
            sa.Column("quantity_before", sa.Integer(), nullable=False),
            sa.Column("quantity_after", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("quantity_delta != 0", name="ck_inventory_movement_nonzero_delta"),
            sa.CheckConstraint("quantity_before >= 0", name="ck_inventory_movement_before_nonnegative"),
            sa.CheckConstraint("quantity_after >= 0", name="ck_inventory_movement_after_nonnegative"),
        )
        op.create_index("ix_inventory_movements_product_created", "inventory_movements", ["product_id", "created_at"])
        op.create_index("ix_inventory_movements_created", "inventory_movements", ["created_at"])
    # 0001 uses current metadata for new databases, so the table may already exist here.
    # Backfill only products with no ledger entries to keep this migration idempotent.
    op.get_bind().execute(sa.text("""INSERT INTO inventory_movements (product_id, actor_user_id, order_id, movement_type, quantity_delta, quantity_before, quantity_after, reason, created_at) SELECT p.id, NULL, NULL, 'INITIAL', p.stock_quantity, 0, p.stock_quantity, 'Opening balance recorded during Phase 11 migration', CURRENT_TIMESTAMP FROM products p WHERE p.stock_quantity > 0 AND NOT EXISTS (SELECT 1 FROM inventory_movements m WHERE m.product_id = p.id)"""))

def downgrade():
    op.drop_index("ix_inventory_movements_created", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_product_created", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("is_archived")
        batch.drop_column("low_stock_threshold")
