"""
Strava OAuth desde la app móvil: /strava/connect?client=mobile marca el state,
y el callback vuelve a /athlete-app.html. Sin el flag, sigue volviendo a
/athlete_profile.html (web sin cambios).
"""
import base64
import json
from urllib.parse import parse_qs, urlparse

import pytest

from api.routes import strava_routes
from .conftest import auth_headers, login


def _state_from(location: str) -> dict:
    qs = parse_qs(urlparse(location).query)
    raw = qs["state"][0]
    padded = raw + "=" * (-len(raw) % 4)
    return json.loads(base64.urlsafe_b64decode(padded).decode())


@pytest.fixture
def strava_on(monkeypatch):
    # El flujo solo existe si Strava está configurado en el servidor.
    monkeypatch.setattr(strava_routes, "_strava_available", lambda: True)
    monkeypatch.setattr(strava_routes, "_CLIENT_ID", "test-client")


def test_connect_web_no_marca_app(client, athlete_user, strava_on):
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/strava/connect", headers=auth_headers(token), follow_redirects=False)
    assert r.status_code in (302, 307)
    st = _state_from(r.headers["location"])
    assert "app" not in st
    assert st["uid"] == athlete_user.id


def test_connect_mobile_marca_app(client, athlete_user, strava_on):
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/strava/connect?client=mobile", headers=auth_headers(token), follow_redirects=False)
    assert r.status_code in (302, 307)
    st = _state_from(r.headers["location"])
    assert st == {"uid": athlete_user.id, "app": "mobile"}


def test_callback_denied_mobile_vuelve_a_athlete_app(client, athlete_user):
    state = base64.urlsafe_b64encode(json.dumps({"uid": athlete_user.id, "app": "mobile"}).encode()).decode()
    r = client.get(f"/api/strava/callback?error=access_denied&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/athlete-app.html?strava=denied"


def test_callback_denied_web_vuelve_a_perfil(client, athlete_user):
    state = base64.urlsafe_b64encode(json.dumps({"uid": athlete_user.id}).encode()).decode()
    r = client.get(f"/api/strava/callback?error=access_denied&state={state}", follow_redirects=False)
    assert r.headers["location"] == "/athlete_profile.html?strava=denied"


def test_callback_sin_state_vuelve_a_perfil(client):
    r = client.get("/api/strava/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/athlete_profile.html?strava=denied"


def test_return_path_state_corrupto_cae_a_web():
    assert strava_routes._oauth_return_path("%%%no-base64") == "/athlete_profile.html"
    assert strava_routes._oauth_return_path(None) == "/athlete_profile.html"
