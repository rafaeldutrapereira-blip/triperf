"""
S6 -- Envio de workouts a intervals.icu: guardado/cifrado de tokens, aislamiento
por atleta, conversion de bloques (bici %FTP y running ritmo/FC) al texto DSL,
y manejo de errores de la API (sin conexion, API caida) -- nunca exito falso.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET",   "test-secret-key-labx-tests")
os.environ.setdefault("APP_ENV",      "test")
os.environ.setdefault("INTERVALS_CLIENT_ID",     "test_intervals_id")
os.environ.setdefault("INTERVALS_CLIENT_SECRET", "test_intervals_secret")

from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import User
from .. import intervals_connector as ic

BASE = "/api/athlete/indoor-workouts"

BIKE_BLOCKS = [
    {"id": "b1", "type": "warmup", "duration": 600, "power_low": 0.5, "power_high": 0.75},
    {"id": "b2", "type": "intervals", "repeat": 4, "on_duration": 240, "on_power": 0.95,
     "off_duration": 120, "off_power": 0.55},
    {"id": "b3", "type": "cooldown", "duration": 300, "power_low": 0.5, "power_high": 0.75},
]
RUN_PACE_BLOCKS = [
    {"id": "b1", "type": "steady", "mode": "pace", "duration": 600, "val": 300},
]
RUN_HR_BLOCKS = [
    {"id": "b1", "type": "intervals", "mode": "hr", "repeat": 3, "on_duration": 180,
     "on_val": 0.9, "off_duration": 90, "off_val": 0.65},
]


def _user(db, email, **extra):
    extra.setdefault("plan_nivel", "elite")
    u = User(email=email, nombre=email, password_hash=hash_password("S6Pass-12345"),
             rol="athlete", activo=True, **extra)
    db.add(u)
    db.commit()
    return u


def _h(client, email):
    h = auth_headers(login(client, email, "S6Pass-12345"))
    client.cookies.clear()
    return h


@pytest.fixture(autouse=True)
def _intervals_app_configured(monkeypatch):
    """Los módulos de la app ya se importaron (vía el fixture `client`) antes
    de que este archivo seteara INTERVALS_CLIENT_ID/SECRET por os.environ, así
    que los parchamos directo en el módulo -- mismo problema que ya evita
    test_strava.py permitiendo 503 en su test de /connect."""
    monkeypatch.setattr(ic, "CLIENT_ID", "test_intervals_id")
    monkeypatch.setattr(ic, "CLIENT_SECRET", "test_intervals_secret")


# ── Conversion de bloques a DSL (sin red) ───────────────────────────────────

class TestBlocksToDsl:
    def test_bike_warmup_steady_interval_cooldown(self):
        dsl = ic.blocks_to_intervals_dsl(BIKE_BLOCKS, "bike")
        assert "ramp 50%-75%" in dsl          # warmup sube
        assert "4x" in dsl
        assert "95%" in dsl and "55%" in dsl
        assert "ramp 75%-50%" in dsl          # cooldown baja (orden invertido)

    def test_run_pace_steady(self):
        dsl = ic.blocks_to_intervals_dsl(RUN_PACE_BLOCKS, "run")
        assert "5:00/km Pace" in dsl          # 300s/km

    def test_run_hr_intervals(self):
        dsl = ic.blocks_to_intervals_dsl(RUN_HR_BLOCKS, "run")
        assert "3x" in dsl
        assert "90% HR" in dsl and "65% HR" in dsl

    def test_unknown_block_type_skipped_not_raised(self):
        dsl = ic.blocks_to_intervals_dsl([{"type": "mystery"}], "bike")
        assert dsl == ""


# ── Tokens: guardado cifrado + aislamiento ──────────────────────────────────

class TestTokens:
    def test_save_encrypts_and_read_decrypts(self, db):
        u = _user(db, "s6tok@test.com")
        ic.save_tokens(u, "plain-access-token", "999", db)
        db.refresh(u)
        assert u.intervals_access_token != "plain-access-token"  # queda cifrado
        assert ic.read_access_token(u) == "plain-access-token"
        assert u.intervals_athlete_id == "999"
        assert u.intervals_connected_at is not None

    def test_tokens_isolated_per_user(self, db):
        a = _user(db, "s6a@test.com")
        b = _user(db, "s6b@test.com")
        ic.save_tokens(a, "token-a", "111", db)
        ic.save_tokens(b, "token-b", "222", db)
        assert ic.read_access_token(a) == "token-a"
        assert ic.read_access_token(b) == "token-b"
        assert a.intervals_access_token != b.intervals_access_token

    def test_clear_tokens(self, db):
        u = _user(db, "s6clear@test.com")
        ic.save_tokens(u, "tok", "1", db)
        ic.clear_tokens(u, db)
        assert u.intervals_access_token is None
        assert u.intervals_athlete_id is None


# ── status/connect/disconnect endpoints ─────────────────────────────────────

class TestStatusEndpoints:
    def test_status_not_connected(self, client, db):
        _user(db, "s6status@test.com")
        h = _h(client, "s6status@test.com")
        r = client.get("/api/integrations/intervals/status", headers=h)
        assert r.status_code == 200
        assert r.json() == {"available": True, "connected": False, "athlete_id": None}

    def test_status_connected(self, client, db):
        u = _user(db, "s6status2@test.com")
        h = _h(client, "s6status2@test.com")
        ic.save_tokens(u, "tok", "42", db)
        r = client.get("/api/integrations/intervals/status", headers=h)
        assert r.json()["connected"] is True
        assert r.json()["athlete_id"] == "42"

    def test_disconnect_not_connected_400(self, client, db):
        _user(db, "s6discon@test.com")
        h = _h(client, "s6discon@test.com")
        r = client.delete("/api/integrations/intervals/disconnect", headers=h)
        assert r.status_code == 400

    def test_disconnect_clears(self, client, db):
        u = _user(db, "s6discon2@test.com")
        h = _h(client, "s6discon2@test.com")
        ic.save_tokens(u, "tok", "7", db)
        r = client.delete("/api/integrations/intervals/disconnect", headers=h)
        assert r.status_code == 200
        db.refresh(u)
        assert u.intervals_access_token is None

    def test_connect_requires_feature_gate(self, client, db):
        _user(db, "s6free@test.com", plan_nivel="basico")
        h = _h(client, "s6free@test.com")
        r = client.get("/api/integrations/intervals/connect", headers=h, follow_redirects=False)
        assert r.status_code == 403

    def test_connect_redirects_when_available(self, client, db):
        _user(db, "s6connect@test.com")
        h = _h(client, "s6connect@test.com")
        r = client.get("/api/integrations/intervals/connect", headers=h, follow_redirects=False)
        assert r.status_code in (302, 307)
        assert "intervals.icu/oauth/authorize" in r.headers["location"]


# ── Envio de workout: mock de la API, sin conexion en vivo ──────────────────

class TestSendToWatch:
    def test_send_without_connection_fails_clearly(self, client, db):
        _user(db, "s6send1@test.com")
        h = _h(client, "s6send1@test.com")
        w = client.post(BASE, json={
            "name": "FTP test", "sport": "bike", "planned_date": "2026-11-10", "blocks": BIKE_BLOCKS,
        }, headers=h).json()
        r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
        assert r.status_code == 502
        assert "no esta conectado" in r.json()["errors"][0]["message"]

    def test_send_success_mocked(self, client, db):
        u = _user(db, "s6send2@test.com")
        h = _h(client, "s6send2@test.com")
        ic.save_tokens(u, "tok", "1", db)
        w = client.post(BASE, json={
            "name": "FTP test", "sport": "bike", "planned_date": "2026-11-10", "blocks": BIKE_BLOCKS,
        }, headers=h).json()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"id": 555}'
        mock_resp.json.return_value = {"id": 555}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__  = AsyncMock(return_value=False)

            r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "event_id": 555}

    def test_send_api_error_never_false_success(self, client, db):
        u = _user(db, "s6send3@test.com")
        h = _h(client, "s6send3@test.com")
        ic.save_tokens(u, "tok", "1", db)
        w = client.post(BASE, json={
            "name": "FTP test", "sport": "bike", "planned_date": "2026-11-10", "blocks": BIKE_BLOCKS,
        }, headers=h).json()

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.content = b""

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__  = AsyncMock(return_value=False)

            r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
        assert r.status_code == 502
        # el workout local sigue intacto
        assert client.get(f"{BASE}/{w['id']}", headers=h).status_code == 200

    def test_send_other_athlete_404(self, client, db):
        owner = _user(db, "s6owner@test.com")
        intruder_h = _h(client, "s6owner@test.com")
        w = client.post(BASE, json={
            "name": "FTP test", "sport": "bike", "planned_date": "2026-11-10", "blocks": BIKE_BLOCKS,
        }, headers=intruder_h).json()

        _user(db, "s6intruder@test.com")
        other_h = _h(client, "s6intruder@test.com")
        r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=other_h)
        assert r.status_code == 404

    def test_send_without_planned_date_needs_explicit_date(self, client, db):
        u = _user(db, "s6nodate@test.com")
        h = _h(client, "s6nodate@test.com")
        ic.save_tokens(u, "tok", "1", db)
        w = client.post(BASE, json={
            "name": "Sin fecha", "sport": "bike", "blocks": BIKE_BLOCKS,
        }, headers=h).json()
        assert w.get("planned_date") is None
        r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
        assert r.status_code == 400
