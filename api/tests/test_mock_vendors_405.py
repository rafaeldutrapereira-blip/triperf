"""BUILD 405 SIMULACION-MARCAS: Wahoo/Polar contra el mock local (corredor automatico).
El mock valida el lado de LabX; el handshake con el vendor real sigue pendiente."""
import importlib

import pytest

from api.providers import polar, wahoo
from api.tests import mock_vendors_runner as runner
from api.tests.mock_vendors import MockVendorServer, POLAR_FIXTURE, WAHOO_FIXTURE


def test_runner_end_to_end_with_gpx(tmp_path):
    rep = runner.run_end_to_end(tmp_path, gpx=True)
    failed = [c for c in rep["checks"] if not c["ok"]]
    assert not failed, failed
    assert rep["mock_stopped"] and rep["brands"]["polar"]["gpx_points"] == 2
    assert (tmp_path / "mock405_test.db").exists()


def test_runner_end_to_end_without_gpx_is_honest_404(tmp_path):
    rep = runner.run_end_to_end(tmp_path, gpx=False)
    assert rep["all_ok"], [c for c in rep["checks"] if not c["ok"]]


def test_mock_serves_fixtures_verbatim():
    import httpx
    with MockVendorServer() as srv:
        w = httpx.get(f"{srv.base_url}/v1/workouts/{WAHOO_FIXTURE['id']}", headers={"Authorization": "Bearer mock-wahoo-access-token"})
        p = httpx.get(f"{srv.base_url}/v3/exercises/{POLAR_FIXTURE['id']}", headers={"Authorization": "Bearer mock-polar-access-token"})
        assert w.json() == WAHOO_FIXTURE and p.json() == POLAR_FIXTURE
        assert httpx.get(f"{srv.base_url}/v3/exercises/{POLAR_FIXTURE['id']}/gpx", headers={"Authorization": "Bearer mock-polar-access-token"}).status_code == 404
        assert httpx.get(f"{srv.base_url}/nada").status_code == 404
        bad = httpx.post(f"{srv.base_url}/oauth/token", params={"grant_type": "authorization_code", "code": "x"})
        assert bad.status_code == 401


def test_default_urls_unchanged_without_env(monkeypatch):
    for k in ("WAHOO_API_BASE_URL", "WAHOO_TOKEN_URL", "POLAR_API_BASE_URL", "POLAR_TOKEN_URL", "POLAR_AUTH_URL"):
        monkeypatch.delenv(k, raising=False)
    assert wahoo._token_url() == "https://api.wahooligan.com/oauth/token"
    assert wahoo._api_base() == "https://api.wahooligan.com/v1"
    assert polar._token_url() == "https://polarremote.com/v2/oauth2/token"
    assert polar._api_base() == "https://www.polaraccesslink.com/v3"
    assert polar._auth_url() == "https://flow.polar.com/oauth2/authorization"


def test_env_overrides_apply(monkeypatch):
    monkeypatch.setenv("WAHOO_API_BASE_URL", "http://x/v1/")
    monkeypatch.setenv("POLAR_AUTH_URL", "http://x/auth")
    assert wahoo._api_base() == "http://x/v1" and polar._auth_url() == "http://x/auth"


def test_polar_unsupported_methods_still_not_implemented():
    p = polar.PolarProvider(None)
    for fn in (lambda: p.download_splits(None, "1"), lambda: p.get_health_daily(None, "2026-01-01"), lambda: p.get_sleep(None, "2026-01-01")):
        with pytest.raises(NotImplementedError):
            fn()
