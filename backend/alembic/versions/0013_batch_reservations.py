"""Track inventory batch quantities reserved by each checkout."""
from alembic import op
import sqlalchemy as sa
revision = "0013_batch_reservations"
down_revision = "0012_supplier_batch_traceability"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "batch_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("quantity > 0", name="ck_batch_reservation_quantity_positive"),
    )
    op.create_index("ix_batch_reservations_order", "batch_reservations", ["order_id"])

def downgrade():
    op.drop_index("ix_batch_reservations_order", table_name="batch_reservations")
    op.drop_table("batch_reservations")
