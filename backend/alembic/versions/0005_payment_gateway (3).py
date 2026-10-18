"""Add Razorpay payment references to orders."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0005_payment_gateway"
down_revision = "0004_integrity_checks"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("orders")}
    with op.batch_alter_table("orders") as batch:
        if "gateway_order_id" not in columns:
            batch.add_column(sa.Column("gateway_order_id", sa.String(length=100), nullable=True))
        if "gateway_payment_id" not in columns:
            batch.add_column(sa.Column("gateway_payment_id", sa.String(length=100), nullable=True))
        if "payment_signature" not in columns:
            batch.add_column(sa.Column("payment_signature", sa.String(length=128), nullable=True))
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("orders")}
    with op.batch_alter_table("orders") as batch:
        if "ix_orders_gateway_order_id" not in indexes:
            batch.create_index("ix_orders_gateway_order_id", ["gateway_order_id"], unique=True)
        if "ix_orders_gateway_payment_id" not in indexes:
            batch.create_index("ix_orders_gateway_payment_id", ["gateway_payment_id"], unique=True)

def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("orders")}
    with op.batch_alter_table("orders") as batch:
        if "ix_orders_gateway_payment_id" in indexes:
            batch.drop_index("ix_orders_gateway_payment_id")
        if "ix_orders_gateway_order_id" in indexes:
            batch.drop_index("ix_orders_gateway_order_id")
    columns = {column["name"] for column in inspect(bind).get_columns("orders")}
    with op.batch_alter_table("orders") as batch:
        for name in ("payment_signature", "gateway_payment_id", "gateway_order_id"):
            if name in columns:
                batch.drop_column(name)
