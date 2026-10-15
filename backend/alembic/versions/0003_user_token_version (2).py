"""Add token version for session invalidation after password changes."""
from alembic import op
from sqlalchemy import Column, Integer, inspect

revision = "0003_token_version"
down_revision = "0002_product_dietary"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "token_version" not in columns:
        op.add_column("users", Column("token_version", Integer(), nullable=False, server_default="0"))

def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "token_version" in columns:
        op.drop_column("users", "token_version")
