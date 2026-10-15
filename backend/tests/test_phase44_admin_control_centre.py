"""Phase 44: admin overview, order export and payment-event inspection are protected."""
from fastapi.testclient import TestClient
from app.main import app


def test_admin_control_centre_routes_require_authentication():
    with TestClient(app) as client:
        for path in ('/api/admin/dashboard/summary', '/api/admin/orders/export.csv', '/api/admin/payments/webhook-events'):
            assert client.get(path).status_code == 401


def test_student_cannot_access_admin_control_centre():
    with TestClient(app) as client:
        email = 'phase44-control-student@example.edu'
        client.post('/api/auth/register', json={'full_name': 'Control Student', 'email': email, 'password': 'correct-horse-123'})
        login = client.post('/api/auth/login', json={'email': email, 'password': 'correct-horse-123'})
        assert login.status_code == 200
        headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        for path in ('/api/admin/dashboard/summary', '/api/admin/orders/export.csv', '/api/admin/payments/webhook-events'):
            assert client.get(path, headers=headers).status_code == 403


def test_admin_control_centre_routes_are_documented():
    with TestClient(app) as client:
        paths = client.get('/openapi.json').json()['paths']
        assert '/api/admin/dashboard/summary' in paths
        assert '/api/admin/orders/export.csv' in paths
        assert '/api/admin/payments/webhook-events' in paths
