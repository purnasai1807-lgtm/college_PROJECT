"""Regression tests for conservative SafeCore retry decisions."""
from datetime import date, timedelta
from decimal import Decimal
import uuid
import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.database import SessionLocal
from app.main import app, settings
from app.models import BatchReservation, Category, InventoryMovement, Notification, Order, Product, ProductBatch, User


class FakeGatewayResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_payment_status_only_allows_retry_after_explicit_failed_attempt(monkeypatch):
    suffix = uuid.uuid4().hex[:12]
    email = f"phase57-{suffix}@example.edu"
    gateway_order_id = f"order_test_{suffix}"
    payment_id = f"pay_test_{suffix}"
    old_key_id, old_secret, old_webhook_secret = settings.razorpay_key_id, settings.razorpay_key_secret, settings.razorpay_webhook_secret
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "phase57-test-secret")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "phase57-webhook-secret")
    provider_items = {"items": []}

    with SessionLocal() as db:
        category = db.scalar(select(Category).where(Category.is_active.is_(True)))
        assert category is not None
        product = Product(category_id=category.id, name=f"Phase 57 item {suffix}", item_type=category.item_type,
                          price=Decimal("12.50"), stock_quantity=5, low_stock_threshold=0,
                          is_archived=False, is_available=True)
        db.add(product); db.flush()
        batch = ProductBatch(product_id=product.id, batch_code=f"P57-{suffix}", quantity_received=5,
                             quantity_remaining=5, received_date=date.today(), expiry_date=date.today()+timedelta(days=20))
        db.add(batch); db.commit()
        product_id, batch_id = product.id, batch.id

    try:
        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeGatewayResponse({"id": gateway_order_id, "amount": 2500, "currency": "INR"}))
        monkeypatch.setattr("httpx.get", lambda *args, **kwargs: FakeGatewayResponse(provider_items))
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"full_name": "Phase 57 Student", "email": email, "password": "safe-test-password-123"})
            assert registered.status_code == 201, registered.text
            logged_in = client.post("/api/auth/login", json={"email": email, "password": "safe-test-password-123"})
            assert logged_in.status_code == 200, logged_in.text
            headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
            created = client.post("/api/payments/create-order", headers=headers, json={"items": [{"product_id": product_id, "quantity": 1}]})
            assert created.status_code == 201, created.text
            order_id = created.json()["order"]["id"]

            # A capture webhook missing its currency is not accepted as proof of payment.
            webhook_body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
                "id": payment_id, "order_id": gateway_order_id, "amount": 1250
            }}}}).encode()
            webhook_signature = hmac.new(settings.razorpay_webhook_secret.encode(), webhook_body, hashlib.sha256).hexdigest()
            webhook = client.post("/api/payments/webhook", content=webhook_body, headers={
                "X-Razorpay-Signature": webhook_signature, "X-Razorpay-Event-Id": f"evt-phase57-{suffix}"
            })
            assert webhook.status_code == 200, webhook.text
            with SessionLocal() as db:
                assert db.get(Order, order_id).payment_status.value == "pending"

            # Empty response is ambiguous: provider propagation can be delayed.
            status = client.get(f"/api/payments/status/{order_id}", headers=headers)
            assert status.status_code == 200
            assert status.json()["retry_allowed"] is False
            assert status.json()["status"] == "verification_pending"

            provider_items["items"] = [{"id": payment_id, "order_id": gateway_order_id, "amount": 1250,
                                        "currency": "INR", "status": "authorized"}]
            status = client.get(f"/api/payments/status/{order_id}", headers=headers)
            assert status.json()["retry_allowed"] is False
            assert status.json()["status"] == "processing"

            # Even a captured payment with the wrong amount must never enable retry.
            provider_items["items"] = [{"id": payment_id, "order_id": gateway_order_id, "amount": 1,
                                        "currency": "INR", "status": "captured"}]
            status = client.get(f"/api/payments/status/{order_id}", headers=headers)
            assert status.json()["retry_allowed"] is False
            assert status.json()["status"] == "review_required"

            provider_items["items"] = [{"id": payment_id, "order_id": gateway_order_id, "amount": 1250,
                                        "currency": "INR", "status": "failed"}]
            status = client.get(f"/api/payments/status/{order_id}", headers=headers)
            assert status.json()["retry_allowed"] is True
            assert status.json()["status"] == "not_confirmed"

            provider_items["items"] = [{"id": payment_id, "order_id": gateway_order_id, "amount": 1250,
                                        "currency": "INR", "status": "captured"}]
            status = client.get(f"/api/payments/status/{order_id}", headers=headers)
            assert status.json()["retry_allowed"] is False
            assert status.json()["status"] == "paid"

            # A different event ID for the same capture must not create a duplicate notification.
            with SessionLocal() as db:
                order = db.get(Order, order_id)
                user_id = order.user_id
                notifications_before = db.scalar(select(func.count(Notification.id)).where(
                    Notification.user_id == user_id, Notification.title == "Payment confirmed")) or 0
            valid_webhook_body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
                "id": payment_id, "order_id": gateway_order_id, "amount": 1250, "currency": "INR"
            }}}}).encode()
            valid_webhook_signature = hmac.new(settings.razorpay_webhook_secret.encode(), valid_webhook_body, hashlib.sha256).hexdigest()
            duplicate_capture = client.post("/api/payments/webhook", content=valid_webhook_body, headers={
                "X-Razorpay-Signature": valid_webhook_signature, "X-Razorpay-Event-Id": f"evt-phase57-duplicate-{suffix}"
            })
            assert duplicate_capture.status_code == 200, duplicate_capture.text
            with SessionLocal() as db:
                notifications_after = db.scalar(select(func.count(Notification.id)).where(
                    Notification.user_id == user_id, Notification.title == "Payment confirmed")) or 0
            assert notifications_after == notifications_before
    finally:
        with SessionLocal() as db:
            order = db.scalar(select(Order).where(Order.gateway_order_id == gateway_order_id))
            if order:
                db.query(BatchReservation).filter(BatchReservation.order_id == order.id).delete(synchronize_session=False)
                db.delete(order)
            batch = db.get(ProductBatch, batch_id)
            product = db.get(Product, product_id)
            user = db.scalar(select(User).where(User.email == email))
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
        monkeypatch.setattr(settings, "razorpay_webhook_secret", old_webhook_secret)
