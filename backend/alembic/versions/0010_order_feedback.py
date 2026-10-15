"""Add verified student feedback for completed orders."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "0010_order_feedback"
down_revision = "0009_student_favorites"
branch_labels = None
depends_on = None
def upgrade():
    if "order_reviews" in inspect(op.get_bind()).get_table_names(): return
    op.create_table("order_reviews", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("rating", sa.Integer(), nullable=False), sa.Column("comment", sa.String(500)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()), sa.UniqueConstraint("order_id", name="uq_order_reviews_order"), sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_order_reviews_rating_range"))
    op.create_index("ix_order_reviews_user_id", "order_reviews", ["user_id"])
    op.create_index("ix_order_reviews_created", "order_reviews", ["created_at"])
def downgrade():
    op.drop_index("ix_order_reviews_created", table_name="order_reviews")
    op.drop_index("ix_order_reviews_user_id", table_name="order_reviews")
    op.drop_table("order_reviews")
