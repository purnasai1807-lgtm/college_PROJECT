import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deployment_preflight.py"
spec = importlib.util.spec_from_file_location("deployment_preflight_phase54", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def by_name(checks):
    return {check.name: check for check in checks}


def production_env(**overrides):
    env = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "secure-unique-secret-key-for-phase-54-123456789",
        "DATABASE_URL": "postgresql+psycopg://app:secret@db/app",
        "AUTO_CREATE_TABLES": "false",
        "SEED_DEMO_DATA": "false",
        "HTTPS_TERMINATED": "true",
        "POSTGRES_PASSWORD": "a-very-long-unique-postgres-password",
    }
    env.update(overrides)
    return env


def test_production_https_is_a_blocking_release_gate():
    checks = by_name(module.run_checks(production_env(HTTPS_TERMINATED="false")))
    assert not checks["production_https_proxy"].ok
    assert checks["production_https_proxy"].severity == "error"


def test_payment_webhook_secret_must_be_configured_with_keys():
    checks = by_name(module.run_checks(production_env(
        RAZORPAY_KEY_ID="rzp_test_example", RAZORPAY_KEY_SECRET="test-secret"
    )))
    assert not checks["payment_webhook_configuration"].ok


def test_live_payment_gate_rejects_test_mode_key():
    checks = by_name(module.run_checks(production_env(
        RAZORPAY_KEY_ID="rzp_test_example", RAZORPAY_KEY_SECRET="test-secret",
        RAZORPAY_WEBHOOK_SECRET="webhook-secret"
    ), require_live_payment=True))
    assert checks["payment_credentials_required"].ok
    assert not checks["live_payment_key_mode"].ok


def test_live_payment_gate_accepts_complete_live_key_configuration():
    checks = by_name(module.run_checks(production_env(
        RAZORPAY_KEY_ID="rzp_live_example", RAZORPAY_KEY_SECRET="live-secret",
        RAZORPAY_WEBHOOK_SECRET="webhook-secret"
    ), require_live_payment=True))
    assert checks["payment_credentials_required"].ok
    assert checks["live_payment_key_mode"].ok


def test_preflight_does_not_print_secret_values(capsys, monkeypatch):
    secret = "this-is-a-secret-that-must-never-appear-in-output"
    monkeypatch.setenv("SECRET_KEY", secret)
    module.main(["--json"])
    output = capsys.readouterr().out
    assert secret not in output
