"""Regression tests for production security hardening added in Phase 58."""
import pytest
from fastapi import HTTPException

import app.main as main


def test_production_rate_limiter_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(main, "IS_PRODUCTION", True)
    monkeypatch.setattr(main.settings, "redis_url", "")
    monkeypatch.setattr(main, "_redis", None)
    with pytest.raises(HTTPException) as error:
        main._check_login_rate("phase58-test-no-redis")
    assert error.value.status_code == 503


def test_production_info_endpoint_does_not_disclose_framework_or_database(monkeypatch):
    monkeypatch.setattr(main, "IS_PRODUCTION", True)
    import asyncio
    result = asyncio.run(main.info())
    assert result == {"name": main.settings.app_name, "status": "online"}
    assert "database" not in result
    assert "backend" not in result
    assert "version" not in result


def test_development_info_endpoint_keeps_diagnostics(monkeypatch):
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    import asyncio
    result = asyncio.run(main.info())
    assert "database" in result
    assert "backend" in result
