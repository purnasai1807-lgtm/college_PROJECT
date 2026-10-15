"""Regression coverage for batch-level checkout reservations and safe releases."""
from datetime import date, timedelta
import uuid

from app.database import SessionLocal
from app.main import _reserve_batch_stock, _release_batch_stock
from app.models import BatchReservation, Order, OrderStatus, PaymentStatus, Product, ProductBatch, User, UserRole
from app.security import hash_password
from sqlalchemy import select


def test_batch_stock_is_reserved_fefo_and_release_is_idempotent():
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        user = User(full_name="Phase 39 test", email=f"phase39-{suffix}@example.edu", password_hash=hash_password("phase39-test-password"), role=UserRole.ADMIN, is_active=True)
        db.add(user); db.flush()
        product = db.scalar(select(Product).where(Product.is_archived.is_(False)))
        assert product is not None
        older = ProductBatch(product_id=product.id, batch_code=f"OLD-{suffix}", quantity_received=3, quantity_remaining=3, expiry_date=date.today()+timedelta(days=3))
        newer = ProductBatch(product_id=product.id, batch_code=f"NEW-{suffix}", quantity_received=5, quantity_remaining=5, expiry_date=date.today()+timedelta(days=15))
        expired = ProductBatch(product_id=product.id, batch_code=f"EXP-{suffix}", quantity_received=4, quantity_remaining=4, expiry_date=date.today()-timedelta(days=1))
        db.add_all([older, newer, expired]); db.flush()
        order = Order(user_id=user.id, status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal=1, gateway_order_id=f"test-{suffix}")
        db.add(order); db.flush()
        _reserve_batch_stock(db, product.id, 4, order.id)
        db.flush()
        assert older.quantity_remaining == 0
        assert newer.quantity_remaining == 4
        assert expired.quantity_remaining == 4
        allocations = db.scalars(select(BatchReservation).where(BatchReservation.order_id == order.id)).all()
        assert [(a.batch_id, a.quantity) for a in allocations] == [(older.id, 3), (newer.id, 1)]
        assert _release_batch_stock(db, order.id) == 4
        db.flush()
        assert older.quantity_remaining == 3
        assert newer.quantity_remaining == 5
        assert _release_batch_stock(db, order.id) == 0
        db.delete(order); db.delete(older); db.delete(newer); db.delete(expired); db.delete(user)
        db.commit()
