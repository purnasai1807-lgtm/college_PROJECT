from fastapi.testclient import TestClient
from app.main import app


def test_manifest_is_served_with_install_metadata():
    with TestClient(app) as client:
        response = client.get("/manifest.webmanifest")
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "ACE Canteen"
        assert payload["start_url"] == "/"
        assert payload["display"] == "standalone"
        assert payload["icons"]


def test_service_worker_is_root_scoped_and_does_not_cache_api():
    with TestClient(app) as client:
        response = client.get("/sw.js")
        assert response.status_code == 200
        assert response.headers.get("service-worker-allowed") == "/"
        assert 'url.pathname.startsWith("/api/")' in response.text
        assert "Never cache API responses" in response.text
