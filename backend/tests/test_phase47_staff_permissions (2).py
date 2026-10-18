"""Phase 47: admin-managed staff accounts and permission lifecycle."""
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, UserRole, AuditEvent
from app.security import hash_password
from sqlalchemy import select


def _login(client, role='admin'):
    email = f'phase47-{role}-{uuid.uuid4().hex[:10]}@example.edu'
    password = 'Phase47-secure-password!'
    with SessionLocal() as db:
        db.add(User(full_name=f'Phase 47 {role}', email=email, password_hash=hash_password(password), role=UserRole(role), is_active=True))
        db.commit()
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}, email


def test_admin_can_create_staff_account_and_audit_it():
    with TestClient(app) as client:
        headers, admin_email = _login(client)
        email = f'new-staff-{uuid.uuid4().hex[:10]}@example.edu'
        response = client.post('/api/admin/users', headers=headers, json={
            'full_name': 'New Canteen Staff', 'email': email, 'role': 'staff',
            'temporary_password': 'Staff-temporary-password-47!'
        })
        assert response.status_code == 201, response.text
        body = response.json()
        assert body['email'] == email and body['role'] == 'staff' and body['is_active'] is True
        login = client.post('/api/auth/login', json={'email': email, 'password': 'Staff-temporary-password-47!'})
        assert login.status_code == 200
        staff_headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
        assert client.get('/api/admin/users', headers=staff_headers).status_code == 403
        with SessionLocal() as db:
            event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'user.created_by_admin', AuditEvent.entity_id == str(body['id'])))
            assert event is not None
            assert event.actor_user_id is not None


def test_admin_account_creation_rejects_duplicates_and_student_role():
    with TestClient(app) as client:
        headers, _ = _login(client)
        email = f'duplicate-{uuid.uuid4().hex[:10]}@example.edu'
        payload = {'full_name':'Managed Staff','email':email,'role':'staff','temporary_password':'Staff-temporary-password-47!'}
        assert client.post('/api/admin/users', headers=headers, json=payload).status_code == 201
        assert client.post('/api/admin/users', headers=headers, json=payload).status_code == 409
        payload['email'] = f'student-{uuid.uuid4().hex[:10]}@example.edu'
        payload['role'] = 'student'
        assert client.post('/api/admin/users', headers=headers, json=payload).status_code == 422


def test_staff_cannot_create_accounts_and_short_password_is_rejected():
    with TestClient(app) as client:
        staff_headers, _ = _login(client, 'staff')
        payload = {'full_name':'Blocked Account','email':f'blocked-{uuid.uuid4().hex[:10]}@example.edu','role':'staff','temporary_password':'short'}
        assert client.post('/api/admin/users', headers=staff_headers, json=payload).status_code == 403
        admin_headers, _ = _login(client)
        assert client.post('/api/admin/users', headers=admin_headers, json=payload).status_code == 422


def test_role_change_revokes_existing_token():
    with TestClient(app) as client:
        admin_headers, _ = _login(client)
        target_email = f'role-target-{uuid.uuid4().hex[:10]}@example.edu'
        created = client.post('/api/admin/users', headers=admin_headers, json={
            'full_name':'Role Target','email':target_email,'role':'staff','temporary_password':'Staff-temporary-password-47!'
        })
        assert created.status_code == 201
        old_login = client.post('/api/auth/login', json={'email':target_email,'password':'Staff-temporary-password-47!'})
        old_headers = {'Authorization': f"Bearer {old_login.json()['access_token']}"}
        changed = client.patch(f"/api/admin/users/{created.json()['id']}/role", headers=admin_headers, json={'role':'student'})
        assert changed.status_code == 200
        assert client.get('/api/auth/me', headers=old_headers).status_code == 401
