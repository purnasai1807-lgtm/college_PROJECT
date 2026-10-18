import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deployment_preflight.py"
spec = importlib.util.spec_from_file_location("deployment_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def by_name(checks):
    return {check.name: check for check in checks}

def test_development_defaults_warn_about_default_secret():
    checks = by_name(module.run_checks({"ENVIRONMENT": "development"}))
    assert not checks["secret_key"].ok
    assert checks["demo_seed"].ok

def test_production_requires_postgres_migrations_disabled_and_no_demo_seed():
    checks = by_name(module.run_checks({
        "ENVIRONMENT": "production", "SECRET_KEY": "x" * 48,
        "DATABASE_URL": "postgresql+psycopg://app:secret@db/app",
        "AUTO_CREATE_TABLES": "false", "SEED_DEMO_DATA": "false",
        "POSTGRES_PASSWORD": "a" * 32,
    }))
    assert checks["secret_key"].ok
    assert checks["production_database"].ok
    assert checks["production_migrations"].ok
    assert checks["production_demo_seed"].ok
    assert checks["postgres_password"].ok

def test_production_default_secret_sqlite_and_seed_fail():
    checks = by_name(module.run_checks({"ENVIRONMENT": "production"}))
    assert not checks["secret_key"].ok
    assert not checks["production_database"].ok
    assert not checks["production_migrations"].ok
    assert not checks["production_demo_seed"].ok

def test_payment_keys_must_be_paired_and_webhook_when_required():
    checks = by_name(module.run_checks({"RAZORPAY_KEY_ID": "key_id"}, require_payment=True))
    assert not checks["payment_credentials_pair"].ok
    assert not checks["payment_credentials_required"].ok

def test_preflight_never_echoes_secret_values(capsys, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "super-secret-value-that-must-not-print")
    result = module.main([])
    output = capsys.readouterr().out
    assert result == 0  # Development mode treats the configured secret as acceptable.
    assert "super-secret-value-that-must-not-print" not in output
