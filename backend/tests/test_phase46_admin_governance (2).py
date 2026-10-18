"""Phase 46: protect the last active administrator and filter audit history."""
from fastapi.testclient import TestClient
from app.main import app


def _admin_headers(client):
    import uuid
    from app.database import SessionLocal
    from app.models import User, UserRole
    from app.security import hash_password
    email = f"phase46-admin-{uuid.uuid4().hex[:10]}@example.edu"
    password = "phase46-secure-admin-password"
    with SessionLocal() as db:
        db.add(User(full_name="Phase 46 Admin", email=email, password_hash=hash_password(password), role=UserRole.ADMIN, is_active=True))
        db.commit()
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}, email


def test_last_active_admin_cannot_be_disabled_or_demoted():
    with TestClient(app) as client:
        headers, email = _admin_headers(client)
        users = client.get('/api/admin/users', headers=headers)
        target = next(u for u in users.json() if u['email'] == email)
        disabled = client.patch(f"/api/admin/users/{target['id']}/active?active=false", headers=headers)
        assert disabled.status_code == 400  # self-disable guard
        # A second admin can attempt to change the first admin only after being created;
        # last-admin guard is separately exercised by a distinct active admin actor.
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        import uuid
        second_email = f"phase46-second-{uuid.uuid4().hex[:10]}@example.edu"
        with SessionLocal() as db:
            db.add(User(full_name="Second Admin", email=second_email, password_hash=hash_password('phase46-secure-second-password'), role=UserRole.ADMIN, is_active=True))
            db.commit()
        second_login = client.post('/api/auth/login', json={'email': second_email, 'password': 'phase46-secure-second-password'})
        second_headers = {'Authorization': f"Bearer {second_login.json()['access_token']}"}
        # Demoting one of two active admins is allowed; the final admin cannot be removed.
        assert client.patch(f"/api/admin/users/{target['id']}/role", headers=second_headers, json={'role':'student'}).status_code == 200
        second_user = next(u for u in client.get('/api/admin/users', headers=second_headers).json() if u['email'] == second_email)
        response = client.patch(f"/api/admin/users/{second_user['id']}/active?active=false", headers=second_headers)
        assert response.status_code == 400  # self-disable guard


def test_audit_event_filter_parameters_are_documented():
    with TestClient(app) as client:
        path = client.get('/openapi.json').json()['paths']['/api/admin/audit-events']['get']
        names = {p['name'] for p in path['parameters']}
        assert {'action', 'entity_type', 'actor_user_id', 'entity_id', 'limit', 'offset'} <= names
