"""Add idempotency ledger for payment webhook deliveries."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "0011_payment_webhook_idempotency"
down_revision = "0010_order_feedback"
branch_labels = None
depends_on = None
def upgrade():
    if "payment_webhook_events" in inspect(op.get_bind()).get_table_names(): return
    op.create_table("payment_webhook_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_id", sa.String(160), nullable=False, unique=True), sa.Column("event_name", sa.String(100), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    op.create_index("ix_payment_webhook_events_received", "payment_webhook_events", ["received_at"])
def downgrade():
    op.drop_index("ix_payment_webhook_events_received", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")
