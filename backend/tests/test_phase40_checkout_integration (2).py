"""Integration regression: mocked gateway checkout, batch reservation, and signature verification."""
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import hmac
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app, settings
from app.models import BatchReservation, Category, InventoryMovement, Order, Product, ProductBatch, User


class FakeGatewayResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_checkout_reserves_stock_and_signature_verification_marks_paid(monkeypatch):
    suffix = uuid.uuid4().hex[:12]
    email = f"phase40-{suffix}@example.edu"
    gateway_order_id = f"order_test_{suffix}"
    old_key_id, old_secret = settings.razorpay_key_id, settings.razorpay_key_secret
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "phase40-test-secret")

    with SessionLocal() as db:
        category = db.scalar(select(Category).where(Category.is_active.is_(True)))
        assert category is not None
        product = Product(category_id=category.id, name=f"Phase 40 item {suffix}", item_type=category.item_type,
                          price=Decimal("12.50"), stock_quantity=5, low_stock_threshold=0,
                          is_archived=False, is_available=True)
        db.add(product); db.flush()
        batch = ProductBatch(product_id=product.id, batch_code=f"P40-{suffix}", quantity_received=5,
                             quantity_remaining=5, received_date=date.today(), expiry_date=date.today()+timedelta(days=20))
        db.add(batch); db.commit()
        product_id, batch_id = product.id, batch.id

    try:
        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeGatewayResponse({"id": gateway_order_id, "amount": 2500, "currency": "INR"}))
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"full_name": "Phase 40 Student", "email": email, "password": "safe-test-password-123"})
            assert registered.status_code == 201, registered.text
            token_response = client.post("/api/auth/login", json={"email": email, "password": "safe-test-password-123"})
            assert token_response.status_code == 200, token_response.text
            token = token_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            created = client.post("/api/payments/create-order", headers=headers, json={"items": [{"product_id": product_id, "quantity": 2}]})
            assert created.status_code == 201, created.text
            order_data = created.json()["order"]
            assert order_data["payment_status"] == "pending"
            with SessionLocal() as db:
                assert db.get(Product, product_id).stock_quantity == 3
                assert db.get(ProductBatch, batch_id).quantity_remaining == 3
                allocation = db.scalar(select(BatchReservation).where(BatchReservation.order_id == order_data["id"], BatchReservation.batch_id == batch_id, BatchReservation.released_at.is_(None)))
                assert allocation is not None and allocation.quantity == 2

            payment_id = f"pay_test_{suffix}"
            signature = hmac.new(settings.razorpay_key_secret.encode(), f"{gateway_order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
            verified = client.post("/api/payments/verify", headers=headers, json={"razorpay_order_id": gateway_order_id,
                "razorpay_payment_id": payment_id, "razorpay_signature": signature})
            assert verified.status_code == 200, verified.text
            assert verified.json()["verified"] is True
            assert verified.json()["order"]["payment_status"] == "paid"
            repeated = client.post("/api/payments/verify", headers=headers, json={"razorpay_order_id": gateway_order_id,
                "razorpay_payment_id": payment_id, "razorpay_signature": signature})
            assert repeated.status_code == 200
            invalid = client.post("/api/payments/verify", headers=headers, json={"razorpay_order_id": gateway_order_id,
                "razorpay_payment_id": payment_id + "x", "razorpay_signature": "invalid"})
            assert invalid.status_code == 409
    finally:
        with SessionLocal() as db:
            order = db.scalar(select(Order).where(Order.gateway_order_id == gateway_order_id))
            if order:
                db.query(BatchReservation).filter(BatchReservation.order_id == order.id).delete(synchronize_session=False)
                db.delete(order)
            batch = db.get(ProductBatch, batch_id)
            product = db.get(Product, product_id)
            user = db.scalar(select(User).where(User.email == email))
            # Audit movements intentionally reference products with RESTRICT. Remove
            # only rows generated by this isolated integration test before its fixture.
            db.query(InventoryMovement).filter(InventoryMovement.product_id == product_id).delete(synchronize_session=False)
            if batch:
                db.delete(batch)
            if product:
                db.delete(product)
            if user:
                db.delete(user)
            db.commit()
        monkeypatch.setattr(settings, "razorpay_key_id", old_key_id)
        monkeypatch.setattr(settings, "razorpay_key_secret", old_secret)
