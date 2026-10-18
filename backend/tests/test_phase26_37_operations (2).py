from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password
import uuid
from datetime import date, timedelta
from contextlib import contextmanager


@contextmanager
def admin_headers():
    suffix = uuid.uuid4().hex[:10]
    email = f'ops-admin-{suffix}@example.edu'
    with SessionLocal() as db:
        db.add(User(full_name='Operations Admin', email=email, password_hash=hash_password('ops-test-password-123'), role=UserRole.ADMIN, is_active=True))
        db.commit()
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'email': email, 'password': 'ops-test-password-123'})
        assert response.status_code == 200
        yield client, {'Authorization': f"Bearer {response.json()['access_token']}"}, suffix


def test_supplier_create_and_list():
    with admin_headers() as (client, headers, suffix):
        created = client.post('/api/admin/suppliers', headers=headers, json={'name': f'Local Supplier {suffix}', 'phone': '9000000000'})
        assert created.status_code == 201, created.text
        assert created.json()['name'] == f'Local Supplier {suffix}'
        listed = client.get('/api/admin/suppliers', headers=headers)
        assert listed.status_code == 200
        assert any(x['id'] == created.json()['id'] for x in listed.json())


def test_batch_receipt_updates_stock_and_expiry_report():
    with admin_headers() as (client, headers, suffix):
        products = client.get('/api/admin/products', headers=headers)
        assert products.status_code == 200 and products.json()
        product = next(p for p in products.json() if not p.get('is_archived', False))
        supplier = client.post('/api/admin/suppliers', headers=headers, json={'name': f'Batch Supplier {suffix}'})
        assert supplier.status_code == 201
        old_stock = product['stock_quantity']
        receipt = client.post('/api/admin/inventory/batches', headers=headers, json={
            'product_id': product['id'], 'supplier_id': supplier.json()['id'],
            'batch_code': f'B-{suffix}', 'quantity': 3, 'expiry_date': (date.today() + timedelta(days=20)).isoformat()
        })
        assert receipt.status_code == 201, receipt.text
        assert receipt.json()['stock_after'] == old_stock + 3
        expiry = client.get('/api/admin/inventory/expiry?days=365', headers=headers)
        assert expiry.status_code == 200
        assert any(x['batch_code'] == f'B-{suffix}' for x in expiry.json()['batches'])


def test_demand_analytics_requires_admin():
    with TestClient(app) as client:
        assert client.get('/api/admin/analytics/demand').status_code == 401
    with admin_headers() as (client, headers, _):
        response = client.get('/api/admin/analytics/demand?days=30', headers=headers)
        assert response.status_code == 200
        assert response.json()['window_days'] == 30
        assert 'products' in response.json()


def test_inventory_reconciliation_is_admin_only_and_read_only():
    with TestClient(app) as client:
        assert client.get('/api/admin/inventory/reconciliation').status_code == 401
    with admin_headers() as (client, headers, _):
        before = client.get('/api/admin/inventory/summary', headers=headers)
        assert before.status_code == 200
        response = client.get('/api/admin/inventory/reconciliation', headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['products_checked'] >= 0
        assert payload['mismatches'] >= 0
        assert payload['untracked_legacy_products'] >= 0
        assert all(row['status'] in {'matched', 'mismatch', 'untracked_legacy_stock'} for row in payload['items'])
        after = client.get('/api/admin/inventory/summary', headers=headers)
        assert after.status_code == 200
        assert before.json() == after.json()
