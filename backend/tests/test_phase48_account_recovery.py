"""Phase 48: password reset by email token, forced temporary-password change."""
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, _login_attempts
from app.database import SessionLocal
from app.models import User, UserRole, AuditEvent
from app.security import hash_password, create_password_reset_token

PASSWORD = "Phase48-secure-password!"


def _make_user(role="student"):
    email = f"phase48-{role}-{uuid.uuid4().hex[:10]}@example.edu"
    with SessionLocal() as db:
        user = User(full_name=f"Phase 48 {role}", email=email, password_hash=hash_password(PASSWORD), role=UserRole(role), is_active=True)
        db.add(user)
        db.commit()
        return user.id, email


def _login(client, email, password=PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _token_for(email):
    with SessionLocal() as db:
        return create_password_reset_token(db.scalar(select(User).where(User.email == email)))


def test_forgot_password_response_does_not_reveal_whether_email_exists():
    _login_attempts.clear()
    with TestClient(app) as client:
        _, email = _make_user()
        known = client.post("/api/auth/forgot-password", json={"email": email})
        unknown = client.post("/api/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.edu"})
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()


def test_forgot_password_is_rate_limited():
    _login_attempts.clear()
    with TestClient(app) as client:
        email = f"limit-{uuid.uuid4().hex[:8]}@example.edu"
        codes = [client.post("/api/auth/forgot-password", json={"email": email}).status_code for _ in range(7)]
        assert 429 in codes and codes[0] == 200


def test_reset_token_sets_new_password_once_and_signs_out_old_sessions():
    _login_attempts.clear()
    with TestClient(app) as client:
        _, email = _make_user()
        old_headers = _login(client, email)
        token = _token_for(email)
        new_password = "Brand-new-password-48!"
        assert client.post("/api/auth/reset-password", json={"token": token, "new_password": new_password}).status_code == 200
        assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
        assert client.post("/api/auth/login", json={"email": email, "password": new_password}).status_code == 200
        assert client.get("/api/auth/me", headers=old_headers).status_code == 401  # old session invalidated
        # The same link cannot be reused.
        again = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Another-password-48!!"})
        assert again.status_code == 400
        with SessionLocal() as db:
            assert db.scalar(select(AuditEvent).where(AuditEvent.action == "user.password_reset")) is not None


def test_reset_rejects_garbage_token_and_disabled_account():
    _login_attempts.clear()
    with TestClient(app) as client:
        bad = client.post("/api/auth/reset-password", json={"token": "x" * 40, "new_password": "Valid-password-12345"})
        assert bad.status_code == 400
        _, email = _make_user()
        token = _token_for(email)
        with SessionLocal() as db:
            db.scalar(select(User).where(User.email == email)).is_active = False
            db.commit()
        assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "Valid-password-12345"}).status_code == 400


def test_new_staff_must_change_temporary_password_before_using_staff_tools():
    _login_attempts.clear()
    with TestClient(app) as client:
        _, admin_email = _make_user("admin")
        admin = _login(client, admin_email)
        staff_email = f"temp-staff-{uuid.uuid4().hex[:8]}@example.edu"
        created = client.post("/api/admin/users", headers=admin, json={"full_name": "Temp Staff", "email": staff_email, "role": "staff", "temporary_password": "Temporary-password-48!"})
        assert created.status_code == 201 and created.json()["must_change_password"] is True
        staff = _login(client, staff_email, "Temporary-password-48!")
        assert client.get("/api/staff/dashboard", headers=staff).status_code == 403
        assert client.get("/api/auth/me", headers=staff).json()["must_change_password"] is True
        changed = client.post("/api/auth/change-password", headers=staff, json={"current_password": "Temporary-password-48!", "new_password": "My-own-staff-password-48!"})
        assert changed.status_code == 200
        staff = _login(client, staff_email, "My-own-staff-password-48!")
        assert client.get("/api/staff/dashboard", headers=staff).status_code == 200
        assert client.get("/api/auth/me", headers=staff).json()["must_change_password"] is False


def test_alembic_migrations_apply_cleanly_to_a_fresh_database(tmp_path):
    """Regression: a brand-new database (the Docker 'migrate' job) must reach head without errors."""
    import os, subprocess, sys, sqlite3
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    db_file = tmp_path / "fresh.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}", "PYTHONPATH": str(root / "backend")}
    result = subprocess.run([sys.executable, "-m", "alembic", "-c", str(root / "backend" / "alembic.ini"), "upgrade", "head"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-1500:]
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("select version_num from alembic_version").fetchone()[0] == "0015_canteen_hours_slots"
