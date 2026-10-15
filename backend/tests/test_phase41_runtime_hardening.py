"""Runtime hardening regressions: SQLite constraints and bounded login-throttle state."""
from sqlalchemy import text

from app.database import engine
from app.main import _check_login_rate, _login_attempts, _login_attempts_lock


def test_sqlite_foreign_key_enforcement_is_enabled_when_using_sqlite():
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_checking_unknown_login_key_does_not_allocate_rate_limit_state():
    key = "phase41-no-attempts-should-be-created"
    with _login_attempts_lock:
        _login_attempts.pop(key, None)
    assert _check_login_rate(key) == 0
    with _login_attempts_lock:
        assert key not in _login_attempts
