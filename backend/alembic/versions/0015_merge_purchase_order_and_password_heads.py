"""Merge the purchase-order and password-reset migration branches."""
revision = "0015_merge_heads"
down_revision = ("0014_must_change_password", "0014_purchase_orders")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
