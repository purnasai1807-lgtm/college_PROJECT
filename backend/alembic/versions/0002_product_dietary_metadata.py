"""Add optional dietary and allergen metadata to products."""
from alembic import op
from sqlalchemy import inspect, String

revision = "0002_product_dietary"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    # 0001 creates tables from current metadata in this starter project, so guard
    # these additions to support both fresh databases and existing installations.
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("products")}
    if "dietary_info" not in columns:
        op.add_column("products", __import__("sqlalchemy").Column("dietary_info", String(255), nullable=True))
    if "allergens" not in columns:
        op.add_column("products", __import__("sqlalchemy").Column("allergens", String(255), nullable=True))

def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("products")}
    if "allergens" in columns:
        op.drop_column("products", "allergens")
    if "dietary_info" in columns:
        op.drop_column("products", "dietary_info")
