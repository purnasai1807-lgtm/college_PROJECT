"""Persist the exact server timestamp when a pickup is handed over."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0016_order_collected_at"
down_revision = "0015_canteen_hours_slots"
branch_labels = None
depends_on = None

def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("orders")}
    if "collected_at" not in columns:
        op.add_column("orders", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("orders")}
    if "collected_at" in columns:
        op.drop_column("orders", "collected_at")
