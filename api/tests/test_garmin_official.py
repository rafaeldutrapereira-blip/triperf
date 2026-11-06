"""Sprint GARMIN: integracion oficial (OAuth2 + PKCE + webhook). HTTP de Garmin mockeado."""
import base64
import hashlib
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

import pytest

from api import garmin_official as go
from api.models import GarminOAuthState, GarminOAuthToken, User
from api.routes import garmin_official_routes as gr
from api.tests.conftest import auth_headers, login

BASE = "/api/integrations/garmin"
FAKE_SECRET = "fake-secret-value-for-tests"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GARMIN_CLIENT_ID", "cid-test")
    monkeypatch.setenv("GARMIN_CLIENT_SECRET", FAKE_SECRET)
    monkeypatch.setenv("GARMIN_REDIRECT_URI", "https://labxperformanceapp.com/api/integrations/garmin/callback")


@pytest.fixture
def unconfigured(monkeypatch):
    for k in ("GARMIN_CLIENT_ID", "GARMIN_CLIENT_SECRET", "GARMIN_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)


def _h(client):
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    return auth_headers(t)


def _start(client, db, athlete_user):
    r = client.get(f"{BASE}/connect", headers=_h(client), follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    return r.headers["location"], q


TOKENS = {"access_token": "AT-1", "refresh_token": "RT-1", "expires_in": 3600, "scope": "ACTIVITY_EXPORT"}


# ── 503 sin credenciales ────────────────────────────────────────────────────

def test_503_without_config(client, athlete_user, unconfigured):
    h = _h(client)
    assert client.get(f"{BASE}/connect", headers=h, follow_redirects=False).status_code == 503
    assert client.get(f"{BASE}/callback?code=x&state=y", follow_redirects=False).status_code == 503
    # status sigue respondiendo y reporta available=False
    r = client.get(f"{BASE}/status", headers=h)
    assert r.status_code == 200 and r.json()["available"] is False


def test_connect_requires_auth(client, configured):
    assert client.get(f"{BASE}/connect", follow_redirects=False).status_code == 401


# ── PKCE / connect ──────────────────────────────────────────────────────────

def test_pkce_challenge_matches_verifier():
    v, c = go.make_pkce()
    assert 43 <= len(v) <= 128
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")


def test_connect_redirects_with_pkce_and_stores_state(client, db, athlete_user, configured):
    loc, q = _start(client, db, athlete_user)
    assert loc.startswith(go.AUTHORIZE_URL)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["cid-test"]
    assert FAKE_SECRET not in loc
    row = db.query(GarminOAuthState).one()
    assert row.user_id == athlete_user.id
    assert q["code_challenge"][0] == base64.urlsafe_b64encode(
        hashlib.sha256(row.code_verifier.encode()).digest()).decode().rstrip("=")
    assert row.state_hash != q["state"][0]  # solo se guarda el hash


# ── callback ────────────────────────────────────────────────────────────────

def test_callback_invalid_state_rejected(client, db, athlete_user, configured):
    with patch.object(go, "_post_token") as m:
        r = client.get(f"{BASE}/callback?code=abc&state=nope.nope", follow_redirects=False)
        r2 = client.get(f"{BASE}/callback?code=abc", follow_redirects=False)
    assert "garmin=error_state" in r.headers["location"]
    assert "garmin=error_state" in r2.headers["location"]
    m.assert_not_called()
    assert db.query(GarminOAuthToken).count() == 0


def test_callback_forged_signature_rejected(client, db, athlete_user, configured):
    _, q = _start(client, db, athlete_user)
    raw = q["state"][0].rsplit(".", 1)[0]
    with patch.object(go, "_post_token") as m:
        r = client.get(f"{BASE}/callback?code=abc&state={raw}.deadbeef", follow_redirects=False)
    assert "error_state" in r.headers["location"]
    m.assert_not_called()


def test_callback_ok_saves_encrypted_tokens_and_state_single_use(client, db, athlete_user, configured):
    _, q = _start(client, db, athlete_user)
    state = q["state"][0]
    verifier = db.query(GarminOAuthState).one().code_verifier
    with patch.object(go, "_post_token", return_value=TOKENS) as post, \
         patch.object(go, "_fetch_garmin_user_id", return_value="G-123"):
        r = client.get(f"{BASE}/callback?code=abc&state={state}", follow_redirects=False)
        assert "garmin=connected" in r.headers["location"]
        sent = post.call_args[0][0]
        assert sent["code"] == "abc" and sent["code_verifier"] == verifier
        assert sent["grant_type"] == "authorization_code"
        # reuso del state => rechazado
        r2 = client.get(f"{BASE}/callback?code=abc&state={state}", follow_redirects=False)
        assert "error_state" in r2.headers["location"]
    db.expire_all()
    row = db.query(GarminOAuthToken).one()
    assert row.user_id == athlete_user.id and row.garmin_user_id == "G-123"
    assert row.access_token != "AT-1" and row.refresh_token != "RT-1"  # cifrados
    assert row.scope == "ACTIVITY_EXPORT" and row.expires_at is not None


def test_callback_garmin_error_redirects_error(client, db, athlete_user, configured):
    _, q = _start(client, db, athlete_user)
    with patch.object(go, "_post_token", side_effect=go.GarminOfficialError("boom")):
        r = client.get(f"{BASE}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    assert "garmin=error" in r.headers["location"] and "error_state" not in r.headers["location"]
    assert db.query(GarminOAuthToken).count() == 0


def test_callback_user_denied(client, db, athlete_user, configured):
    _, q = _start(client, db, athlete_user)
    r = client.get(f"{BASE}/callback?error=access_denied&state={q['state'][0]}", follow_redirects=False)
    assert "garmin=denied" in r.headers["location"]


def test_callback_expired_state(client, db, athlete_user, configured):
    _, q = _start(client, db, athlete_user)
    row = db.query(GarminOAuthState).one()
    row.expires_at = go._now() - timedelta(minutes=1)
    db.commit()
    r = client.get(f"{BASE}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    assert "error_state" in r.headers["location"]


# ── status / disconnect ─────────────────────────────────────────────────────

def test_status_and_disconnect(client, db, athlete_user, configured):
    h = _h(client)
    assert client.get(f"{BASE}/status", headers=h).json()["connected"] is False
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    body = client.get(f"{BASE}/status", headers=h).json()
    assert body["connected"] is True and body["available"] is True
    assert "AT-1" not in str(body) and "access_token" not in body
    assert client.post(f"{BASE}/disconnect", headers=h).json()["ok"] is True
    assert client.get(f"{BASE}/status", headers=h).json()["connected"] is False
    assert db.query(GarminOAuthToken).count() == 0


# ── refresh ─────────────────────────────────────────────────────────────────

def test_refresh_when_expired(db, athlete_user, configured):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    row = db.query(GarminOAuthToken).one()
    row.expires_at = go._now() - timedelta(minutes=5)
    db.commit()
    new = {"access_token": "AT-2", "refresh_token": "RT-2", "expires_in": 7200}
    with patch.object(go, "_post_token", return_value=new) as post:
        assert go.get_valid_access_token(db, athlete_user.id) == "AT-2"
    assert post.call_args[0][0]["grant_type"] == "refresh_token"
    assert post.call_args[0][0]["refresh_token"] == "RT-1"
    db.expire_all()
    assert go.get_valid_access_token(db, athlete_user.id) == "AT-2"  # vigente: sin red


def test_refresh_not_needed_or_failure(db, athlete_user, configured):
    go.save_tokens(db, athlete_user.id, TOKENS)
    with patch.object(go, "_post_token") as post:
        assert go.get_valid_access_token(db, athlete_user.id) == "AT-1"
    post.assert_not_called()
    db.query(GarminOAuthToken).one().expires_at = go._now() - timedelta(minutes=5)
    db.commit()
    with patch.object(go, "_post_token", side_effect=go.GarminOfficialError("x")):
        assert go.get_valid_access_token(db, athlete_user.id) is None
    assert go.get_valid_access_token(db, "nadie") is None


# ── webhook ─────────────────────────────────────────────────────────────────

def test_notify_valid_known_user_queues_sync(client, db, athlete_user):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-777")
    with patch.object(gr, "dispatch_garmin_sync", return_value="background") as d:
        r = client.post(f"{BASE}/notify", json={"activities": [{"userId": "G-777", "activityId": 1}]})
    assert r.status_code == 200 and r.json()["queued"] == 1
    assert d.call_args[0][0] == athlete_user.id


def test_notify_unknown_user_200(client, db, athlete_user):
    with patch.object(gr, "dispatch_garmin_sync") as d:
        r = client.post(f"{BASE}/notify", json={"dailies": [{"userId": "ghost"}]})
        r2 = client.post(f"{BASE}/notify", json={})
    assert r.status_code == 200 and r.json()["queued"] == 0
    assert r2.status_code == 200
    d.assert_not_called()


def test_notify_malformed_never_500(client, db, athlete_user):
    assert client.post(f"{BASE}/notify", content=b"not json",
                       headers={"Content-Type": "application/json"}).status_code == 400
    assert client.post(f"{BASE}/notify", json=[1, 2]).status_code == 400
    r = client.post(f"{BASE}/notify", json={"activities": "x", "dailies": [1, None, {"userId": None}]})
    assert r.status_code == 200


def test_notify_dispatch_error_still_200(client, db, athlete_user):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-9")
    with patch.object(gr, "dispatch_garmin_sync", side_effect=RuntimeError("down")):
        r = client.post(f"{BASE}/notify", json={"activities": [{"userId": "G-9"}]})
    assert r.status_code == 200


# ── bandeja de entrada push (ingestor fase A) ───────────────────────────────

def test_notify_stores_raw_payload_per_type_unprocessed(client, db, athlete_user, caplog):
    import json, logging
    from api.models import GarminPushPayload
    caplog.set_level(logging.INFO, logger="garmin_official_ingest")
    go.save_tokens(db, athlete_user.id, TOKENS, "G-555")
    body = {"activities": [{"userId": "G-555", "activityId": 1}],
            "dailies": [{"userId": "G-555", "calendarDate": "2026-11-05"}]}
    with patch.object(gr, "dispatch_garmin_sync", return_value="background") as d:
        r = client.post(f"{BASE}/notify", json=body)
    assert r.status_code == 200 and r.json()["queued"] == 1
    d.assert_called_once()
    rows = {x.payload_type: x for x in db.query(GarminPushPayload).all()}
    assert set(rows) == {"activities", "dailies"}
    for x in rows.values():
        assert x.processed is False and x.user_id == athlete_user.id and x.received_at
    assert json.loads(rows["activities"].payload_json) == {"activities": body["activities"]}
    log = " ".join(rec.getMessage() for rec in caplog.records if rec.name == "garmin_official_ingest")
    assert "activityId" in log and "G-555" not in log


def test_notify_unresolved_user_still_stored_with_null_user(client, db, athlete_user):
    from api.models import GarminPushPayload
    r = client.post(f"{BASE}/notify", json={"dailies": [{"userId": "ghost", "calendarDate": "2026-11-05"}]})
    assert r.status_code == 200
    row = db.query(GarminPushPayload).one()
    assert row.user_id is None and row.payload_type == "dailies"


def test_notify_empty_or_ping_only_not_stored(client, db, athlete_user):
    from api.models import GarminPushPayload
    client.post(f"{BASE}/notify", json={})
    client.post(f"{BASE}/notify", json={"activities": [], "dailies": [{"userId": "G-1"}], "x": "y"})
    assert db.query(GarminPushPayload).count() == 0


def test_notify_invalid_payload_400_and_not_stored(client, db, athlete_user):
    from api.models import GarminPushPayload
    assert client.post(f"{BASE}/notify", json=[1]).status_code == 400
    assert db.query(GarminPushPayload).count() == 0


def test_notify_inbox_failure_does_not_break_response(client, db, athlete_user):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-8")
    with patch.object(gr, "dispatch_garmin_sync", return_value="background") as d, \
         patch.object(gr, "GarminPushPayload", side_effect=RuntimeError("db")):
        r = client.post(f"{BASE}/notify", json={"activities": [{"userId": "G-8", "activityId": 2}]})
    assert r.status_code == 200 and r.json()["queued"] == 1
    d.assert_called_once()


def test_secret_never_in_logs(client, db, athlete_user, configured, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    _, q = _start(client, db, athlete_user)
    with patch.object(go, "_post_token", side_effect=go.GarminOfficialError("boom")):
        client.get(f"{BASE}/callback?code=abc&state={q['state'][0]}", follow_redirects=False)
    assert FAKE_SECRET not in caplog.text
