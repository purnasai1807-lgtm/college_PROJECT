"""Add durable, user-scoped checkout idempotency ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0017_checkout_idempotency"
down_revision = "0016_order_collected_at"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if "checkout_idempotency" not in inspector.get_table_names():
        op.create_table(
            "checkout_idempotency",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("idempotency_key", sa.String(length=100), nullable=False),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="processing"),
            sa.Column("response_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "idempotency_key", name="uq_checkout_idempotency_user_key"),
        )
        op.create_index("ix_checkout_idempotency_created", "checkout_idempotency", ["created_at"])


def downgrade():
    if "checkout_idempotency" in inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_checkout_idempotency_created", table_name="checkout_idempotency")
        op.drop_table("checkout_idempotency")
