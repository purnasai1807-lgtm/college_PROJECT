"""Public phone-camera pickup links expose useful order facts without student PII."""
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, _pickup_qr_code, _pickup_code_from_input
from app.database import SessionLocal, Base, engine
from app.models import User, UserRole, Product, Category, Order, OrderItem, OrderStatus, PaymentStatus
from app.security import hash_password


def _make_paid_order(status=OrderStatus.READY):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = User(full_name="Private QR Student", email=f"qr-student-{uuid.uuid4().hex[:10]}@example.edu", password_hash=hash_password("QR-test-password-123!"), role=UserRole.STUDENT, is_active=True)
        db.add(user); db.flush()
        category = db.scalar(select(Category).limit(1))
        if category is None:
            category = Category(name=f"QR-{uuid.uuid4().hex[:5]}", slug=f"qr-{uuid.uuid4().hex[:8]}", item_type="food", is_active=True)
            db.add(category); db.flush()
        product = Product(category_id=category.id, name="QR Test Sandwich", item_type="food", price=45, stock_quantity=4, is_available=True)
        db.add(product); db.flush()
        order = Order(user_id=user.id, status=status, payment_status=PaymentStatus.PAID, subtotal=45, gateway_order_id=f"qr_order_{uuid.uuid4().hex}")
        db.add(order); db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product.id, product_name=product.name, unit_price=45, quantity=1, line_total=45))
        db.commit()
        return order.id


def test_phone_qr_url_opens_mobile_pickup_page_and_displays_non_private_order_details():
    order_id = _make_paid_order()
    code = _pickup_qr_code(order_id)
    with TestClient(app) as client:
        page = client.get(f"/pickup#code={code}")
        assert page.status_code == 200
        assert "ACE Canteen" in page.text
        response = client.post("/api/pickup/status", json={"code": code})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["order_id"] == order_id
        assert body["payment_status"] == "paid"
        assert body["created_at"]
        assert body["items"][0]["product_name"] == "QR Test Sandwich"
        assert body["subtotal"] == "45.00"
        assert "customer_name" not in body and "customer_email" not in body and "user_id" not in body


def test_staff_scanner_accepts_the_https_url_encoded_in_qr():
    code = "123.abcdef"
    assert _pickup_code_from_input(f"https://canteen.example.edu/pickup#code={code}") == code
    assert _pickup_code_from_input(code) == code


def test_invalid_public_pickup_qr_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/pickup/status", json={"code": "not-a-valid-code"})
        assert response.status_code in (404, 422)


def test_staff_scan_and_collection_records_one_time_collection_timestamp():
    order_id = _make_paid_order()
    code = _pickup_qr_code(order_id)
    email = f"qr-staff-{uuid.uuid4().hex[:10]}@example.edu"
    with SessionLocal() as db:
        db.add(User(full_name="QR Counter Staff", email=email, password_hash=hash_password("QR-staff-password-123!"), role=UserRole.STAFF, is_active=True))
        db.commit()
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": email, "password": "QR-staff-password-123!"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        scanned = client.post("/api/staff/pickup/scan", headers=headers, json={"code": f"https://canteen.example.edu/pickup#code={code}"})
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["payment_status"] == "paid"
        completed = client.patch(f"/api/admin/orders/{order_id}/status", headers=headers, json={"status": "completed"})
        assert completed.status_code == 200, completed.text
        status = client.post("/api/pickup/status", json={"code": code})
        assert status.status_code == 200
        assert status.json()["collected_at"] is not None
        duplicate = client.post("/api/staff/pickup/scan", headers=headers, json={"code": code})
        assert duplicate.status_code == 409
