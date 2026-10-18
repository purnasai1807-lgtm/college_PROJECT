"""Regression coverage for payment reconciliation and supplier purchase orders."""
import uuid
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal, Base, engine
from app.models import User, UserRole, Category, Product, Supplier, PurchaseOrder, ProductBatch, InventoryMovement
from app.security import hash_password


def _headers(role="admin"):
    email = f"p49-50-{role}-{uuid.uuid4().hex[:8]}@example.edu"
    password = "Test-only-secure-password-123!"
    with SessionLocal() as db:
        db.add(User(full_name="Workflow Test", email=email, password_hash=hash_password(password), role=UserRole(role), is_active=True)); db.commit()
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_payment_reconciliation_is_admin_only_and_diagnostic():
    with TestClient(app) as client:
        assert client.get("/api/admin/payments/reconciliation").status_code == 401
        assert client.get("/api/admin/payments/reconciliation", headers=_headers("staff")).status_code == 403
        response = client.get("/api/admin/payments/reconciliation", headers=_headers())
        assert response.status_code == 200, response.text
        assert "No automatic capture" in response.json()["safety_note"]
        assert isinstance(response.json()["items"], list)


def test_purchase_order_receipt_adds_stock_once():
    Base.metadata.create_all(bind=engine)
    suffix = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        category = db.scalar(select(Category).where(Category.is_active.is_(True)))
        if category is None:
            category = Category(name=f"P50-{suffix}", slug=f"p50-{suffix}", item_type="food", is_active=True); db.add(category); db.flush()
        product = Product(category_id=category.id, name=f"PO product {suffix}", item_type=category.item_type, price=10, stock_quantity=2, low_stock_threshold=0, is_archived=False, is_available=True)
        supplier = Supplier(name=f"PO supplier {suffix}", is_active=True)
        db.add_all([product, supplier]); db.commit(); product_id, supplier_id = product.id, supplier.id
    try:
        with TestClient(app) as client:
            headers = _headers()
            created = client.post("/api/admin/purchase-orders", headers=headers, json={"supplier_id": supplier_id, "lines": [{"product_id": product_id, "quantity": 4, "unit_cost": "3.25", "expiry_date": (date.today()+timedelta(days=30)).isoformat()}]})
            assert created.status_code == 201, created.text
            po_id = created.json()["id"]
            first = client.post(f"/api/admin/purchase-orders/{po_id}/receive", headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["already_received"] is False
            second = client.post(f"/api/admin/purchase-orders/{po_id}/receive", headers=headers)
            assert second.status_code == 200 and second.json()["already_received"] is True
            with SessionLocal() as db:
                assert db.get(Product, product_id).stock_quantity == 6
                assert db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id)).status == "received"
                assert db.scalar(select(ProductBatch).where(ProductBatch.product_id == product_id)) is not None
    finally:
        with SessionLocal() as db:
            po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.supplier_id == supplier_id))
            if po: db.delete(po)
            # Keep product traceability safe by deleting isolated test movement and batch rows first.
            product = db.get(Product, product_id)
            if product:
                db.query(InventoryMovement).filter(InventoryMovement.product_id == product_id).delete(synchronize_session=False)
                db.query(ProductBatch).filter(ProductBatch.product_id == product_id).delete(synchronize_session=False)
                db.delete(product)
            supplier = db.get(Supplier, supplier_id)
            if supplier: db.delete(supplier)
            db.commit()
