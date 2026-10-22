"""Add supplier purchase orders for Phase 50 (safe for schemas created from current metadata)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0014_purchase_orders"
down_revision = "0013_batch_reservations"
branch_labels = None
depends_on = None

def upgrade():
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "purchase_orders" not in tables:
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("lines_json", sa.Text(), nullable=False),
            sa.Column("notes", sa.String(length=500)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("ordered_at", sa.DateTime(timezone=True)),
            sa.Column("received_at", sa.DateTime(timezone=True)),
        )
    indexes = {idx["name"] for idx in inspect(op.get_bind()).get_indexes("purchase_orders")}
    if "ix_purchase_orders_supplier_id" not in indexes:
        op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    if "ix_purchase_orders_status" not in indexes:
        op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])

def downgrade():
    if "purchase_orders" in inspect(op.get_bind()).get_table_names():
        indexes = {idx["name"] for idx in inspect(op.get_bind()).get_indexes("purchase_orders")}
        if "ix_purchase_orders_status" in indexes:
            op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
        if "ix_purchase_orders_supplier_id" in indexes:
            op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
        op.drop_table("purchase_orders")
