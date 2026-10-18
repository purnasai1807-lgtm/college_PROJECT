"""Phase 19: repeatable smoke tests for the student-facing campus pilot path."""
from fastapi.testclient import TestClient
from app.main import app


def test_phase19_student_pilot_public_pages_and_catalogue():
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "ACE Canteen" in home.text
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/ready").json()["status"] == "ready"
        categories = client.get("/api/categories")
        products = client.get("/api/products")
        assert categories.status_code == 200 and categories.json()
        assert products.status_code == 200 and products.json()
        assert all(float(item["price"]) > 0 for item in products.json())


def test_phase19_checkout_quote_requires_valid_items():
    with TestClient(app) as client:
        # Anonymous requests must not be able to create an order directly.
        response = client.post("/api/orders", json={})
        assert response.status_code in (401, 403, 410, 422)


def test_phase19_feedback_summary_is_not_public():
    with TestClient(app) as client:
        response = client.get("/api/feedback/summary")
        assert response.status_code in (401, 403)
