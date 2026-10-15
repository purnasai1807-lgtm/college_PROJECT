"""Add student saved items for faster repeat ordering."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "0009_student_favorites"
down_revision = "0008_in_app_notifications"
branch_labels = None
depends_on = None
def upgrade():
    if "favorites" in inspect(op.get_bind()).get_table_names(): return
    op.create_table("favorites", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()), sa.UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"))
    op.create_index("ix_favorites_user_created", "favorites", ["user_id", "created_at"])
def downgrade():
    op.drop_index("ix_favorites_user_created", table_name="favorites")
    op.drop_table("favorites")
