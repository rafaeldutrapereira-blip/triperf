"""Sprint 56 paso 1: rutas OAuth Polar/Wahoo. Sin red: authenticate de los providers se parchea."""
import asyncio
from datetime import timedelta
from urllib.parse import urlparse, parse_qs

import pytest

from api import crypto, provider_oauth as po
from api.models import ProviderConnection, ProviderOAuthState
from api.providers.polar import PolarProvider
from api.providers.wahoo import WahooProvider
from api.tests.conftest import auth_headers, login

BASE = "/api/integrations"
AUTH_URL = {
    "polar": "https://flow.polar.com/oauth2/authorization",
    "wahoo": "https://api.wahooligan.com/oauth/authorize",
}
FAKE_SECRET = "fake-secret-value-for-tests"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for p in ("POLAR", "WAHOO"):
        monkeypatch.setenv(f"{p}_ENABLED", "true")
        monkeypatch.setenv(f"{p}_CLIENT_ID", "cid-test")
        monkeypatch.setenv(f"{p}_CLIENT_SECRET", FAKE_SECRET)
        monkeypatch.delenv(f"{p}_REDIRECT_URI", raising=False)
    monkeypatch.delenv("APP_URL", raising=False)


@pytest.fixture(autouse=True)
def _fake_auth(monkeypatch):
    async def polar_auth(self, user_id, **creds):
        assert creds["member_id"] == str(user_id)
        self.last_token_response = {"access_token": "POLAR-AT", "token_type": "bearer",
                                    "expires_in": 31536000, "x_user_id": 998877}
        return "POLAR-AT"

    async def wahoo_auth(self, user_id, **creds):
        if "refresh_token" in creds:
            self.last_token_response = {"access_token": "WAHOO-AT-2", "refresh_token": "WAHOO-RT-2",
                                        "expires_in": 7200}
        else:
            self.last_token_response = {"access_token": "WAHOO-AT", "refresh_token": "WAHOO-RT",
                                        "expires_in": 7200}
        return self.last_token_response["access_token"]

    monkeypatch.setattr(PolarProvider, "authenticate", polar_auth)
    monkeypatch.setattr(WahooProvider, "authenticate", wahoo_auth)


def _h(client):
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    return auth_headers(t)


def _start(client, provider):
    r = client.get(f"{BASE}/{provider}/connect", headers=_h(client), follow_redirects=False)
    assert r.status_code == 302
    return r.headers["location"], parse_qs(urlparse(r.headers["location"]).query)


PROVIDERS = ["polar", "wahoo"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_connect_redirects_and_stores_state(client, db, athlete_user, provider):
    loc, q = _start(client, provider)
    assert loc.startswith(AUTH_URL[provider] + "?")
    assert q["response_type"] == ["code"] and q["client_id"] == ["cid-test"]
    assert q["redirect_uri"] == [f"https://labxperformanceapp.com/api/integrations/{provider}/callback"]
    if provider == "wahoo":
        assert q["scope"] == ["user_read workouts_read power_zones_read offline_data"]
    else:
        assert "scope" not in q
    assert FAKE_SECRET not in loc
    row = db.query(ProviderOAuthState).one()
    assert row.user_id == athlete_user.id and row.provider == provider
    assert row.state_hash != q["state"][0]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_connect_requires_auth(client, provider):
    assert client.get(f"{BASE}/{provider}/connect", follow_redirects=False).status_code == 401


@pytest.mark.parametrize("provider", PROVIDERS)
def test_flag_off_connect_404(client, athlete_user, monkeypatch, provider):
    monkeypatch.setenv(f"{provider.upper()}_ENABLED", "false")
    h = _h(client)
    assert client.get(f"{BASE}/{provider}/connect", headers=h, follow_redirects=False).status_code == 404
    assert client.get(f"{BASE}/{provider}/status", headers=h).json()["available"] is False


@pytest.mark.parametrize("provider", PROVIDERS)
def test_no_credentials_503(client, athlete_user, monkeypatch, provider):
    monkeypatch.delenv(f"{provider.upper()}_CLIENT_ID")
    monkeypatch.delenv(f"{provider.upper()}_CLIENT_SECRET")
    h = _h(client)
    assert client.get(f"{BASE}/{provider}/connect", headers=h, follow_redirects=False).status_code == 503
    assert client.get(f"{BASE}/{provider}/status", headers=h).json()["available"] is False


@pytest.mark.parametrize("provider", PROVIDERS)
def test_callback_saves_connection(client, db, athlete_user, provider):
    _, q = _start(client, provider)
    r = client.get(f"{BASE}/{provider}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith(f"/athlete-app.html?{provider}=connected")
    row = db.query(ProviderConnection).one()
    assert row.user_id == athlete_user.id and row.provider == provider
    assert row.access_token not in ("POLAR-AT", "WAHOO-AT")  # cifrado en reposo
    assert crypto.decrypt(row.access_token) == ("POLAR-AT" if provider == "polar" else "WAHOO-AT")
    if provider == "wahoo":
        assert crypto.decrypt(row.refresh_token) == "WAHOO-RT"
        assert row.expires_at is not None
        assert row.member_id is None
    else:
        assert row.member_id == athlete_user.id
        assert row.external_user_id == "998877"
    assert db.query(ProviderOAuthState).count() == 0


@pytest.mark.parametrize("provider", PROVIDERS)
def test_callback_state_reuse_and_invalid(client, db, athlete_user, provider):
    _, q = _start(client, provider)
    url = f"{BASE}/{provider}/callback?code=abc&state={q['state'][0]}"
    assert f"{provider}=connected" in client.get(url, follow_redirects=False).headers["location"]
    assert f"{provider}=error_state" in client.get(url, follow_redirects=False).headers["location"]
    r = client.get(f"{BASE}/{provider}/callback?code=abc&state=nope.nope", follow_redirects=False)
    assert f"{provider}=error_state" in r.headers["location"]
    r = client.get(f"{BASE}/{provider}/callback?code=abc", follow_redirects=False)
    assert f"{provider}=error_state" in r.headers["location"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_callback_state_from_other_provider_rejected(client, db, athlete_user, provider):
    other = "wahoo" if provider == "polar" else "polar"
    _, q = _start(client, other)
    r = client.get(f"{BASE}/{provider}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    assert f"{provider}=error_state" in r.headers["location"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_callback_denied_and_provider_error(client, db, athlete_user, monkeypatch, provider):
    _, q = _start(client, provider)
    r = client.get(f"{BASE}/{provider}/callback?error=access_denied&state={q['state'][0]}", follow_redirects=False)
    assert f"{provider}=denied" in r.headers["location"]

    async def boom(self, user_id, **creds):
        raise RuntimeError("fallo de red")
    monkeypatch.setattr(PolarProvider if provider == "polar" else WahooProvider, "authenticate", boom)
    _, q = _start(client, provider)
    r = client.get(f"{BASE}/{provider}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    assert f"{provider}=error" in r.headers["location"] and "error_state" not in r.headers["location"]
    assert db.query(ProviderConnection).count() == 0


@pytest.mark.parametrize("provider", PROVIDERS)
def test_status_and_disconnect(client, db, athlete_user, provider):
    h = _h(client)
    s = client.get(f"{BASE}/{provider}/status", headers=h).json()
    assert s == {"provider": provider, "available": True, "connected": False, "updated_at": None,
                 "last_sync_at": None, "last_sync_status": None}
    _, q = _start(client, provider)
    client.get(f"{BASE}/{provider}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    s = client.get(f"{BASE}/{provider}/status", headers=h).json()
    assert s["connected"] is True and s["updated_at"]
    r = client.post(f"{BASE}/{provider}/disconnect", headers=h)
    assert r.json() == {"ok": True, "disconnected": True}
    assert db.query(ProviderConnection).count() == 0
    assert client.post(f"{BASE}/{provider}/disconnect", headers=h).json()["disconnected"] is False
    assert client.get(f"{BASE}/{provider}/status", headers=h).json()["connected"] is False


def test_redirect_uri_env_override(monkeypatch):
    monkeypatch.setenv("POLAR_REDIRECT_URI", "https://x.test/cb")
    assert po.redirect_uri("polar") == "https://x.test/cb"
    assert po.redirect_uri("wahoo").endswith("/api/integrations/wahoo/callback")


# ── get_valid_access_token ──────────────────────────────────────────────────

def test_polar_token_returned_as_is(db, athlete_user):
    po.save_connection(db, athlete_user.id, "polar", {"access_token": "P1", "x_user_id": 5}, member_id=athlete_user.id)
    assert asyncio.run(po.get_valid_access_token(db, athlete_user.id, "polar")) == "P1"
    assert asyncio.run(po.get_valid_access_token(db, athlete_user.id, "wahoo")) is None


def test_wahoo_token_valid_not_refreshed(db, athlete_user):
    po.save_connection(db, athlete_user.id, "wahoo",
                       {"access_token": "W1", "refresh_token": "R1", "expires_in": 7200})
    assert asyncio.run(po.get_valid_access_token(db, athlete_user.id, "wahoo")) == "W1"


def test_wahoo_expired_token_refreshed_and_persisted(db, athlete_user):
    row = po.save_connection(db, athlete_user.id, "wahoo",
                             {"access_token": "W1", "refresh_token": "R1", "expires_in": 7200})
    row.expires_at = row.expires_at - timedelta(hours=5)
    db.commit()
    assert asyncio.run(po.get_valid_access_token(db, athlete_user.id, "wahoo")) == "WAHOO-AT-2"
    db.refresh(row)
    assert crypto.decrypt(row.access_token) == "WAHOO-AT-2"
    assert crypto.decrypt(row.refresh_token) == "WAHOO-RT-2"
    assert row.expires_at > po._now()


def test_wahoo_refresh_failure_returns_none(db, athlete_user, monkeypatch):
    row = po.save_connection(db, athlete_user.id, "wahoo",
                             {"access_token": "W1", "refresh_token": "R1", "expires_in": 7200})
    row.expires_at = row.expires_at - timedelta(hours=5)
    db.commit()

    async def boom(self, user_id, **creds):
        raise RuntimeError("401")
    monkeypatch.setattr(WahooProvider, "authenticate", boom)
    assert asyncio.run(po.get_valid_access_token(db, athlete_user.id, "wahoo")) is None


@pytest.mark.parametrize("provider", PROVIDERS)
def test_status_expone_ultima_sync_real(client, db, athlete_user, provider):
    """S-D: last_sync_at/status vienen de la fila; nunca inventados."""
    from datetime import datetime
    h = _h(client)
    _, q = _start(client, provider)
    client.get(f"{BASE}/{provider}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    s = client.get(f"{BASE}/{provider}/status", headers=h).json()
    assert s["last_sync_at"] is None and s["last_sync_status"] is None
    row = db.query(ProviderConnection).first()
    row.last_sync_at = datetime(2026, 11, 6, 12, 30)
    row.last_sync_status = "ok"
    db.commit()
    s = client.get(f"{BASE}/{provider}/status", headers=h).json()
    assert s["last_sync_at"].startswith("2026-11-06T12:30")
    assert s["last_sync_status"] == "ok"
