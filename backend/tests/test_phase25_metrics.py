from fastapi.testclient import TestClient
from app.main import app, _metrics, _metrics_lock


def test_metrics_endpoint_reports_aggregate_counts_without_request_labels():
    with _metrics_lock:
        before = _metrics["requests_total"]
    client = TestClient(app)
    response = client.get("/api/metrics", headers={"X-Request-ID": "phase25-test"})
    assert response.status_code == 200
    data = response.json()
    assert data["uptime_metrics_scope"] == "current_process"
    assert data["metrics"]["requests_total"] >= before
    assert "requests_4xx_total" in data["metrics"]
    assert "requests_5xx_total" in data["metrics"]
    assert "request_duration_ms_sum" in data["metrics"]
    assert "request_duration_ms_max" in data["metrics"]
    assert "path" not in data["metrics"]
    assert response.headers["cache-control"] == "no-store"


def test_request_id_is_returned_for_metrics_request():
    response = TestClient(app).get("/api/metrics", headers={"X-Request-ID": "safe_trace_123"})
    assert response.headers["x-request-id"] == "safe_trace_123"
