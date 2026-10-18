"""Deployment safety preflight for ACE Canteen; never prints secret values."""
from __future__ import annotations
import argparse
import os
import re
import sys
from dataclasses import dataclass, asdict
from typing import Iterable

@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    severity: str = "error"

def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}

def run_checks(env: dict[str, str] | None = None, *, require_payment: bool = False, require_live_payment: bool = False) -> list[Check]:
    e = dict(os.environ if env is None else env)
    production = e.get("ENVIRONMENT", "development").lower() in {"prod", "production"}
    checks: list[Check] = []
    def add(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        checks.append(Check(name, bool(ok), detail, severity))

    secret = e.get("SECRET_KEY", "change-this-development-secret-before-deployment")
    secret_ok = len(secret) >= 32 and secret != "change-this-development-secret-before-deployment"
    add("secret_key", secret_ok,
        "A non-default secret of at least 32 characters is configured." if secret_ok else "Set a unique SECRET_KEY of at least 32 characters; value is never displayed.",
        "error" if production else "warning")
    add("environment", e.get("ENVIRONMENT", "development").lower() in {"development", "test", "staging", "production", "prod"}, "Environment value is recognised." if e.get("ENVIRONMENT", "development").lower() in {"development", "test", "staging", "production", "prod"} else "Use development, test, staging, or production.")
    if production:
        add("production_migrations", not _truthy(e.get("AUTO_CREATE_TABLES", "true")), "Automatic table creation is disabled for production." if not _truthy(e.get("AUTO_CREATE_TABLES", "true")) else "Set AUTO_CREATE_TABLES=false and run Alembic migrations explicitly.")
        add("production_demo_seed", not _truthy(e.get("SEED_DEMO_DATA", "true")), "Demo seeding is disabled for production." if not _truthy(e.get("SEED_DEMO_DATA", "true")) else "Set SEED_DEMO_DATA=false in production.")
        url = e.get("DATABASE_URL", "")
        add("production_database", url.startswith(("postgresql://", "postgresql+psycopg://")), "PostgreSQL URL configured." if url.startswith(("postgresql://", "postgresql+psycopg://")) else "Production DATABASE_URL must use PostgreSQL.")
        add("production_https_proxy", _truthy(e.get("HTTPS_TERMINATED", "false")), "HTTPS termination explicitly acknowledged." if _truthy(e.get("HTTPS_TERMINATED", "false")) else "Configure and verify HTTPS at the reverse proxy/load balancer, then set HTTPS_TERMINATED=true.")
        add("production_debug_docs", e.get("EXPOSE_API_DOCS", "false").lower() not in {"1", "true", "yes", "on"}, "Interactive API documentation is not requested." if e.get("EXPOSE_API_DOCS", "false").lower() not in {"1", "true", "yes", "on"} else "Do not expose interactive API docs publicly.")
    else:
        add("demo_seed", True, "Development/test mode: demo seeding may be enabled.", "info")
    key_id, key_secret = e.get("RAZORPAY_KEY_ID", "").strip(), e.get("RAZORPAY_KEY_SECRET", "").strip()
    add("payment_credentials_pair", bool(key_id) == bool(key_secret), "Razorpay key ID and secret are either both configured or both empty." if bool(key_id) == bool(key_secret) else "Configure both Razorpay key ID and secret, or leave both empty.")
    webhook_secret = e.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
    payment_configured = bool(key_id and key_secret and webhook_secret)
    payment_partial = bool(key_id or key_secret or webhook_secret) and not payment_configured
    add("payment_webhook_configuration", not payment_partial,
        "Razorpay key ID, key secret and webhook secret are all configured, or all are empty." if not payment_partial else
        "Configure the Razorpay key ID, key secret and webhook secret together, or leave all three empty.")
    if production and not payment_configured:
        add("production_payment_readiness", False,
            "Live payment checkout is not ready. Configure provider credentials in the deployment secret manager and verify them in staging before accepting payments.", "warning")
    if require_payment or require_live_payment:
        add("payment_credentials_required", payment_configured,
            "Razorpay keys and webhook secret are present." if payment_configured else
            "Payment was requested as required, but credentials/webhook secret are incomplete.")
    if require_live_payment:
        is_live_key = key_id.startswith("rzp_live_")
        add("live_payment_key_mode", is_live_key,
            "Razorpay key ID uses live mode." if is_live_key else
            "Live payment readiness requires a Razorpay live-mode key ID (rzp_live_...). Never paste credentials into source code or chat.")
    add("postgres_password", not production or len(e.get("POSTGRES_PASSWORD", "")) >= 24 and e.get("POSTGRES_PASSWORD", "") not in {"change-this-postgres-password-before-deployment", "postgres", "password"}, "Production database password meets the minimum length check." if not production or (len(e.get("POSTGRES_PASSWORD", "")) >= 24 and e.get("POSTGRES_PASSWORD", "") not in {"change-this-postgres-password-before-deployment", "postgres", "password"}) else "Set POSTGRES_PASSWORD to a unique value of at least 24 characters.")
    return checks

def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--require-payment", action="store_true", help="Fail if Razorpay credentials and webhook secret are not configured")
    parser.add_argument("--require-live-payment", action="store_true", help="Also require a Razorpay live-mode key ID; use only for final live-launch checks")
    args = parser.parse_args(argv)
    checks = run_checks(require_payment=args.require_payment, require_live_payment=args.require_live_payment)
    failures = [c for c in checks if not c.ok and c.severity == "error"]
    warnings = [c for c in checks if not c.ok and c.severity == "warning"]
    if args.json:
        import json
        print(json.dumps({"status": "fail" if failures else "pass", "checks": [asdict(c) for c in checks], "errors": len(failures), "warnings": len(warnings)}, indent=2))
    else:
        for c in checks:
            label = "PASS" if c.ok else ("WARN" if c.severity == "warning" else "FAIL")
            print(f"[{label}] {c.name}: {c.detail}")
        print(f"Preflight: {'FAILED' if failures else 'PASSED'} ({len(failures)} errors, {len(warnings)} warnings)")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
