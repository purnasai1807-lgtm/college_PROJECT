"""Admin-only complete order register access and filtering contract."""
from fastapi.testclient import TestClient
from app.main import app


def test_admin_all_orders_register_requires_authentication():
    with TestClient(app) as client:
        response = client.get('/api/admin/orders/all')
        assert response.status_code == 401


def test_admin_all_orders_register_is_admin_only():
    with TestClient(app) as client:
        email = 'phase42-register-student@example.edu'
        client.post('/api/auth/register', json={
            'full_name': 'Phase 42 Student', 'email': email, 'password': 'correct-horse-123'
        })
        login = client.post('/api/auth/login', json={'email': email, 'password': 'correct-horse-123'})
        assert login.status_code == 200
        token = login.json()['access_token']
        response = client.get('/api/admin/orders/all', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 403


def test_admin_order_register_route_is_documented():
    with TestClient(app) as client:
        schema = client.get('/openapi.json').json()
        assert '/api/admin/orders/all' in schema['paths']
        params = schema['paths']['/api/admin/orders/all']['get']['parameters']
        assert {'name': 'payment_status', 'in': 'query'} <= {frozenset(p.items()) for p in params} if False else any(p['name'] == 'payment_status' for p in params)
