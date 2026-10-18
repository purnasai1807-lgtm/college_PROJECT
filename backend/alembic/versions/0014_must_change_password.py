"""Require staff/admin accounts created with a temporary password to change it."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision = "0014_must_change_password"
down_revision = "0013_batch_reservations"
branch_labels = None
depends_on = None

def upgrade():
    if "must_change_password" in {c["name"] for c in inspect(op.get_bind()).get_columns("users")}:
        return
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("users", "must_change_password")
