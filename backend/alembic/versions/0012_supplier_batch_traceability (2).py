"""Supplier records and expiry-tracked inventory batches."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "0012_supplier_batch_traceability"
down_revision = "0011_payment_webhook_idempotency"
branch_labels = None
depends_on = None

def upgrade():
    # 0001 builds tables from the current models, so on a fresh database these already exist.
    if "suppliers" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table("suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("contact_name", sa.String(120)), sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(255)), sa.Column("notes", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    op.create_index("ix_suppliers_name", "suppliers", ["name"])
    op.create_table("product_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="SET NULL")),
        sa.Column("batch_code", sa.String(80), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False), sa.Column("quantity_remaining", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 2)), sa.Column("received_date", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("expiry_date", sa.Date()), sa.Column("notes", sa.String(255)),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("quantity_received > 0", name="ck_batch_received_positive"),
        sa.CheckConstraint("quantity_remaining >= 0", name="ck_batch_remaining_nonnegative"))
    op.create_index("ix_product_batches_product_id", "product_batches", ["product_id"])
    op.create_index("ix_product_batches_expiry", "product_batches", ["expiry_date"])

def downgrade():
    op.drop_index("ix_product_batches_expiry", table_name="product_batches")
    op.drop_index("ix_product_batches_product_id", table_name="product_batches")
    op.drop_table("product_batches")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
