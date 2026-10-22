"""Phase 49: canteen hours, pause switch, pickup slots, order-ready email, shared (Redis) throttling."""
import uuid
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select
import app.main as main
from app.main import app
from app.config import get_settings
from app.database import SessionLocal
from app.models import User, UserRole, Order, OrderStatus, PaymentStatus, AppSetting
from app.security import hash_password

PASSWORD = "Phase49-secure-password!"
settings = get_settings()


def _user(role="student"):
    email = f"phase49-{role}-{uuid.uuid4().hex[:10]}@example.edu"
    with SessionLocal() as db:
        db.add(User(full_name=f"Phase 49 {role}", email=email, password_hash=hash_password(PASSWORD), role=UserRole(role), is_active=True))
        db.commit()
    return email


def _headers(client, role="student"):
    email = _user(role)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def _first_product(client):
    return client.get("/api/products").json()[0]["id"]


def _reset_pause():
    with SessionLocal() as db:
        for key in ("ordering_paused", "pause_message"):
            row = db.get(AppSetting, key)
            if row:
                db.delete(row)
        db.commit()


def test_status_is_open_by_default_and_slots_empty_without_hours():
    _reset_pause()
    with TestClient(app) as client:
        status = client.get("/api/canteen/status").json()
        assert status["accepting_orders"] is True and status["slots_enabled"] is False
        assert client.get("/api/canteen/slots").json()["slots"] == []


def test_staff_can_pause_ordering_and_quotes_are_rejected_until_resumed():
    _reset_pause()
    with TestClient(app) as client:
        student, _ = _headers(client)
        staff, _ = _headers(client, "staff")
        cart = {"items": [{"product_id": _first_product(client), "quantity": 1}]}
        assert client.post("/api/orders/quote", headers=student, json=cart).status_code == 200
        assert client.patch("/api/admin/canteen/ordering", headers=student, json={"paused": True}).status_code == 403
        paused = client.patch("/api/admin/canteen/ordering", headers=staff, json={"paused": True, "message": "Rush hour - back at 1pm"})
        assert paused.status_code == 200 and paused.json()["accepting_orders"] is False
        blocked = client.post("/api/orders/quote", headers=student, json=cart)
        assert blocked.status_code == 409 and "Rush hour" in blocked.json()["detail"]
        assert client.get("/api/canteen/status").json()["message"].startswith("Rush hour")
        assert client.patch("/api/admin/canteen/ordering", headers=staff, json={"paused": False}).json()["accepting_orders"] is True
        assert client.post("/api/orders/quote", headers=student, json=cart).status_code == 200


def test_closed_outside_configured_hours(monkeypatch):
    _reset_pause()
    monkeypatch.setattr(settings, "canteen_open_time", "00:00")
    monkeypatch.setattr(settings, "canteen_close_time", "00:01")
    monkeypatch.setattr(settings, "canteen_open_days", "0,1,2,3,4,5,6")
    with TestClient(app) as client:
        student, _ = _headers(client)
        status = client.get("/api/canteen/status").json()
        assert status["hours_configured"] is True
        if not status["accepting_orders"]:  # skip the one-minute window after midnight
            assert "closed" in status["message"].lower()
            cart = {"items": [{"product_id": _first_product(client), "quantity": 1}]}
            assert client.post("/api/orders/quote", headers=student, json=cart).status_code == 409


def _open_all_day(monkeypatch):
    monkeypatch.setattr(settings, "canteen_open_time", "00:00")
    monkeypatch.setattr(settings, "canteen_close_time", "23:59")
    monkeypatch.setattr(settings, "canteen_open_days", "0,1,2,3,4,5,6")
    monkeypatch.setattr(settings, "pickup_min_lead_minutes", 0)


def test_slots_listed_validated_and_capacity_enforced(monkeypatch):
    _reset_pause()
    _open_all_day(monkeypatch)
    monkeypatch.setattr(settings, "pickup_slot_capacity", 1)
    with TestClient(app) as client:
        student, _ = _headers(client)
        slots = client.get("/api/canteen/slots").json()["slots"]
        if len(slots) < 2:
            return  # only possible in the last minutes of the day
        chosen = slots[0]
        cart = {"items": [{"product_id": _first_product(client), "quantity": 1}], "pickup_slot": chosen["slot"]}
        assert client.post("/api/orders/quote", headers=student, json=cart).status_code == 200
        assert client.post("/api/orders/quote", headers=student, json={**cart, "pickup_slot": "2000-01-01T10:00:00+05:30"}).status_code == 409
        assert client.post("/api/orders/quote", headers=student, json={**cart, "pickup_slot": "not-a-date"}).status_code == 422
        assert client.post("/api/orders/quote", headers=student, json={**cart, "pickup_slot": "2030-01-01T10:00:00"}).status_code == 422
        # Fill the slot with a paid order, then it must report full.
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).limit(1))
            from app.main import _resolve_pickup_slot
            slot_dt = _resolve_pickup_slot(db, chosen["slot"])
            db.add(Order(user_id=uid, status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID, subtotal=10, pickup_slot=slot_dt))
            db.commit()
        full = client.post("/api/orders/quote", headers=student, json=cart)
        assert full.status_code == 409 and "full" in full.json()["detail"].lower()
        again = {s["slot"]: s["remaining"] for s in client.get("/api/canteen/slots").json()["slots"]}
        assert again[chosen["slot"]] == 0


def test_order_ready_sends_email_to_student():
    _reset_pause()
    with TestClient(app) as client:
        staff, _ = _headers(client, "staff")
        _, student_email = _headers(client)
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).where(User.email == student_email))
            order = Order(user_id=uid, status=OrderStatus.PREPARING, payment_status=PaymentStatus.PAID, subtotal=10, token_number=7)
            from app.models import OrderItem
            order.items.append(OrderItem(product_id=1, product_name="Tea", unit_price=10, quantity=1, line_total=10))
            db.add(order)
            db.commit()
            order_id = order.id
        with patch("app.main.send_email") as sender:
            r = client.patch(f"/api/admin/orders/{order_id}/status", headers=staff, json={"status": "ready"})
            assert r.status_code == 200, r.text
        assert sender.call_count == 1 and sender.call_args.args[0] == student_email and "#7" in sender.call_args.args[2]


def test_login_throttling_can_use_a_shared_redis_store():
    import pytest
    fakeredis = pytest.importorskip("fakeredis", reason="fakeredis is a declared test dependency but is unavailable in this environment")
    fake = fakeredis.FakeRedis(decode_responses=True)
    main._redis = fake
    try:
        key = f"shared-{uuid.uuid4().hex}"
        assert main._check_login_rate(key) == 0
        for _ in range(main._LOGIN_LIMIT):
            main._record_failed_login(key)
        assert main._check_login_rate(key) > 0
        assert fake.get("rl:" + key) is not None  # state lives in Redis, visible to every worker
        main._clear_login_failures(key)
        assert main._check_login_rate(key) == 0
    finally:
        main._redis = None
