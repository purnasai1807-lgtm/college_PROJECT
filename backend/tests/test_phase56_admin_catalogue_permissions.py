"""Catalogue, price and inventory mutations must be administrator-only."""
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _headers(client, role):
    email = f"phase56-{role}-{uuid.uuid4().hex[:10]}@example.edu"
    password = "Phase56-test-password!"
    with SessionLocal() as db:
        db.add(User(full_name=f"Phase 56 {role}", email=email, password_hash=hash_password(password), role=UserRole(role), is_active=True))
        db.commit()
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_staff_cannot_read_or_change_admin_catalogue_and_inventory():
    with TestClient(app) as client:
        staff = _headers(client, "staff")
        assert client.get("/api/admin/products", headers=staff).status_code == 403
        assert client.get("/api/admin/inventory/summary", headers=staff).status_code == 403
        assert client.get("/api/admin/suppliers", headers=staff).status_code == 403
        assert client.post("/api/admin/products", headers=staff, json={"category_id": 1, "name": "Forbidden item", "item_type": "food", "price": "10.00", "stock_quantity": 1}).status_code == 403
        assert client.post("/api/admin/inventory/adjustments", headers=staff, json={"product_id": 1, "movement_type": "receipt", "quantity": 1, "reason": "Forbidden stock change"}).status_code == 403


def test_admin_can_access_catalogue_and_inventory_panels():
    with TestClient(app) as client:
        admin = _headers(client, "admin")
        assert client.get("/api/admin/products", headers=admin).status_code == 200
        assert client.get("/api/admin/inventory/summary", headers=admin).status_code == 200
        assert client.get("/api/admin/suppliers", headers=admin).status_code == 200
