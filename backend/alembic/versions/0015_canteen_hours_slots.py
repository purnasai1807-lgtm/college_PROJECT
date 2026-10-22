"""Runtime canteen settings table and optional pickup time slot on orders."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "0015_canteen_hours_slots"
down_revision = "0015_merge_heads"
branch_labels = None
depends_on = None

def upgrade():
    insp = inspect(op.get_bind())
    if "app_settings" not in insp.get_table_names():
        op.create_table("app_settings",
            sa.Column("key", sa.String(60), primary_key=True),
            sa.Column("value", sa.String(500), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    if "pickup_slot" not in {c["name"] for c in insp.get_columns("orders")}:
        op.add_column("orders", sa.Column("pickup_slot", sa.DateTime(timezone=True)))
        op.create_index("ix_orders_pickup_slot", "orders", ["pickup_slot"])

def downgrade():
    op.drop_index("ix_orders_pickup_slot", table_name="orders")
    op.drop_column("orders", "pickup_slot")
    op.drop_table("app_settings")
