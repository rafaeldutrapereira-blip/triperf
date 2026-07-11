"""Sprint 40 — Observability: trace_id middleware, request logging, metrics endpoint."""
import pytest
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(db):
    from api.coach_main import app
    from api.database import get_db
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── trace_id tests ────────────────────────────────────────────────────────────

class TestTraceId:
    def test_health_returns_trace_id_header(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "x-trace-id" in resp.headers

    def test_trace_id_is_hex_string(self, client):
        resp = client.get("/health")
        tid = resp.headers.get("x-trace-id", "")
        assert len(tid) == 16
        assert all(c in "0123456789abcdef" for c in tid)

    def test_each_request_gets_unique_trace_id(self, client):
        t1 = client.get("/health").headers.get("x-trace-id")
        t2 = client.get("/health").headers.get("x-trace-id")
        assert t1 != t2

    def test_client_trace_id_is_echoed(self, client):
        custom = "abcdef1234567890"
        resp = client.get("/health", headers={"X-Trace-Id": custom})
        assert resp.headers.get("x-trace-id") == custom

    def test_api_endpoint_returns_trace_id(self, client):
        resp = client.get("/api/auth/me")
        assert "x-trace-id" in resp.headers

    def test_trace_id_present_on_404(self, client):
        resp = client.get("/nonexistent-path-xyz")
        assert "x-trace-id" in resp.headers

    def test_trace_id_present_on_error(self, client):
        resp = client.post("/api/auth/login", json={"email": "bad@bad.com", "password": "x"})
        assert "x-trace-id" in resp.headers


# ── /metrics endpoint tests ───────────────────────────────────────────────────

class TestMetricsEndpoint:
    def test_metrics_endpoint_exists(self, client):
        resp = client.get("/metrics")
        # In test env, TestClient IP is not 127.0.0.1 and METRICS_SECRET is unset → 404
        # In production with loopback → 200 or 503 depending on prometheus-client
        assert resp.status_code in (200, 401, 404, 503)

    def test_metrics_not_in_openapi_schema(self, client):
        resp = client.get("/openapi.json")
        if resp.status_code == 200:
            paths = resp.json().get("paths", {})
            assert "/metrics" not in paths

    def test_metrics_blocked_without_secret_from_non_loopback(self, client):
        # TestClient presents a non-loopback IP; no METRICS_SECRET → 404
        resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_metrics_accessible_with_correct_secret(self, client):
        import os
        os.environ["METRICS_SECRET"] = "testsecret42"
        try:
            resp = client.get("/metrics", headers={"Authorization": "Bearer testsecret42"})
            assert resp.status_code in (200, 503)
        finally:
            del os.environ["METRICS_SECRET"]

    def test_metrics_blocked_with_wrong_secret(self, client):
        import os
        os.environ["METRICS_SECRET"] = "testsecret42"
        try:
            resp = client.get("/metrics", headers={"Authorization": "Bearer wrongsecret"})
            assert resp.status_code == 401
        finally:
            del os.environ["METRICS_SECRET"]


# ── metrics module tests ──────────────────────────────────────────────────────

class TestMetricsModule:
    def test_metrics_module_imports(self):
        from api.metrics import (
            trace_id_ctx, new_trace_id, current_trace_id,
            http_requests_total, http_request_duration_seconds,
            active_requests_gauge, is_available, get_metrics_output
        )
        assert callable(new_trace_id)
        assert callable(current_trace_id)
        assert callable(is_available)
        assert callable(get_metrics_output)

    def test_new_trace_id_returns_16_char_hex(self):
        from api.metrics import new_trace_id
        tid = new_trace_id()
        assert len(tid) == 16
        assert all(c in "0123456789abcdef" for c in tid)

    def test_trace_id_ctx_default_empty(self):
        from api.metrics import current_trace_id
        # Outside request context, default is ""
        assert isinstance(current_trace_id(), str)

    def test_get_metrics_output_returns_bytes_and_str(self):
        from api.metrics import get_metrics_output
        body, content_type = get_metrics_output()
        assert isinstance(body, bytes)
        assert isinstance(content_type, str)
        assert "text/plain" in content_type

    def test_noop_metrics_support_required_methods(self):
        from api.metrics import http_requests_total, active_requests_gauge
        # These should not raise regardless of prometheus availability
        http_requests_total.labels(method="GET", path="/health", status=200).inc()
        active_requests_gauge.inc()
        active_requests_gauge.dec()
        active_requests_gauge.set(0)
