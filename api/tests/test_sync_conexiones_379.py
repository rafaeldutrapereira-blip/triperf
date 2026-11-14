"""SYNC-CONEXIONES (BUILD 379): sync manual de Garmin oficial, vigilancia del push y
retorno OAuth. La red de Garmin esta mockeada; no hay secretos reales."""
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from api import garmin_official as go
from api.models import GarminActivity, GarminPushPayload
from api.routes import garmin_official_routes as gr
from api.tests.conftest import auth_headers, login

ROOT = Path(__file__).resolve().parents[2]
BASE = "/api/integrations/garmin"
TOKENS = {"access_token": "AT-1", "refresh_token": "RT-1", "expires_in": 3600, "scope": "ACTIVITY_EXPORT"}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GARMIN_CLIENT_ID", "cid-test")
    monkeypatch.setenv("GARMIN_CLIENT_SECRET", "fake-secret-value-for-tests")
    monkeypatch.setenv("GARMIN_REDIRECT_URI", "https://labxperformanceapp.com/api/integrations/garmin/callback")


def _h(client):
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    return auth_headers(t)


def _act(i=1, start=1763000000):
    return {"activityId": i, "startTimeInSeconds": start, "startTimeOffsetInSeconds": 0,
            "activityType": "RUNNING", "durationInSeconds": 1800, "distanceInMeters": 5000,
            "averageSpeedInMetersPerSecond": 2.8}


# -- POST /sync -----------------------------------------------------------------

def test_sync_requires_auth(client, configured):
    assert client.post(f"{BASE}/sync").status_code == 401


def test_sync_sin_conexion_oficial_es_error_honesto(client, db, athlete_user, configured):
    r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 409
    b = r.json()
    assert b["ok"] is False and b["status"] == "not_connected" and b["errors"][0]["message"]


def test_sync_solo_oficial_trae_actividades_por_pull(client, db, athlete_user, configured):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "_get_activities_window", return_value=[_act(11), _act(12, 1763100000)]) as win:
        r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ok"] is True and b["status"] == "ok" and b["via"] == "official"
    assert b["saved"] >= 2  # el mock repite las mismas ids por ventana: upsert idempotente
    assert b["health_included"] is False  # la salud jamas se promete
    assert b["last_sync"]
    assert win.call_count == go.PULL_MAX_DAYS
    # el access token viaja solo hacia Garmin: nunca en la respuesta
    assert "AT-1" not in r.text
    db.expire_all()
    ids = {a.activity_id for a in db.query(GarminActivity).filter_by(user_id=athlete_user.id)}
    assert ids == {"11", "12"}


def test_sync_pull_idempotente(client, db, athlete_user, configured):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "_get_activities_window", return_value=[_act(21)]):
        client.post(f"{BASE}/sync", headers=_h(client))
        client.post(f"{BASE}/sync", headers=_h(client))
    db.expire_all()
    assert db.query(GarminActivity).filter_by(user_id=athlete_user.id).count() == 1


def test_sync_pull_rechazado_sin_credenciales_error_honesto(client, db, athlete_user, configured):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "_get_activities_window", side_effect=go.GarminOfficialError("x (403)")), \
            patch.object(gr, "dispatch_garmin_sync") as d:
        r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 502
    b = r.json()
    assert b["ok"] is False and b["status"] == "pull_failed" and b["errors"][0]["message"]
    d.assert_not_called()  # sin credenciales legacy no hay fallback


def test_sync_pull_rechazado_con_credenciales_cae_al_dispatch_legacy(client, db, athlete_user, configured):
    h = _h(client)  # login ANTES de guardar credenciales (el login dispara un sync legacy en background)
    athlete_user.garmin_email = "a@b.c"
    db.commit()
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "_get_activities_window", side_effect=go.GarminOfficialError("x (403)")), \
            patch.object(gr, "dispatch_garmin_sync", return_value="background") as d:
        r = client.post(f"{BASE}/sync", headers=h)
    assert r.status_code == 200
    assert r.json()["via"] == "legacy" and r.json()["status"] == "syncing"
    assert d.call_args[0][0] == athlete_user.id


def test_sync_token_vencido_irrenovable_pide_reconectar(client, db, athlete_user, configured):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "get_valid_access_token", return_value=None):
        r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 409 and r.json()["status"] == "needs_reconnect"


def test_sync_sin_configurar_503(client, db, athlete_user, monkeypatch):
    for k in ("GARMIN_CLIENT_ID", "GARMIN_CLIENT_SECRET", "GARMIN_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 503 and r.json()["status"] == "unavailable"


def test_pull_ventanas_de_24h_y_tope_de_7_dias():
    calls = []
    with patch.object(go, "_get_activities_window", side_effect=lambda t, a, b: calls.append((a, b)) or []):
        go.fetch_recent_activities("tok", days=99)
    assert len(calls) == go.PULL_MAX_DAYS
    assert all(b - a == 86400 for a, b in calls)


def test_pull_http_errores_sin_filtrar_token():
    class R:
        def __init__(self, code, body=None):
            self.status_code, self._b = code, body

        def json(self):
            return self._b

    with patch.object(go.httpx, "get", return_value=R(403)):
        with pytest.raises(go.GarminOfficialError) as e:
            go._get_activities_window("SECRET-TOK", 1, 2)
    assert "SECRET-TOK" not in str(e.value)
    with patch.object(go.httpx, "get", return_value=R(200, {"no": "lista"})):
        with pytest.raises(go.GarminOfficialError):
            go._get_activities_window("t", 1, 2)
    with patch.object(go.httpx, "get", return_value=R(200, [{"a": 1}, "x"])):
        assert go._get_activities_window("t", 1, 2) == [{"a": 1}]


# -- GET /push-status -----------------------------------------------------------

def _payload(db, when, ptype="activities", user_id=None, processed=True, error=None):
    db.add(GarminPushPayload(received_at=when, payload_type=ptype, user_id=user_id,
                             payload_json="{}", processed=processed, error=error))
    db.commit()


def test_push_status_requires_auth(client):
    assert client.get(f"{BASE}/push-status").status_code == 401


def test_push_status_vacio_es_stale(client, db, athlete_user):
    b = client.get(f"{BASE}/push-status", headers=_h(client)).json()
    assert b["last_received_at"] is None and b["stale"] is True and b["count_7d"] == 0
    assert b["pending"] == 0 and b["errors"] == 0 and b["last_gap"] is None


def test_push_status_ultimo_conteos_pendientes_y_errores(client, db, athlete_user):
    now = gr._utcnow()
    _payload(db, now - timedelta(hours=2), "activities", athlete_user.id)
    _payload(db, now - timedelta(hours=3), "dailies", athlete_user.id, processed=False)
    _payload(db, now - timedelta(days=1), "sleeps", None, processed=False, error="ValueError: x")
    _payload(db, now - timedelta(days=20), "activities", None)  # fuera de la ventana de 7 d
    b = client.get(f"{BASE}/push-status", headers=_h(client)).json()
    assert b["stale"] is False and b["hours_since"] < 3
    assert b["count_7d"] == 3 and b["mine_count_7d"] == 2
    assert b["pending"] == 1 and b["errors"] == 1
    assert b["by_type"]["activities"]["count_7d"] == 1
    assert b["by_type"]["sleeps"]["last_received_at"]
    assert b["last_received_at"] and b["mine_last_received_at"]


def test_push_status_muerto_mas_de_48h(client, db, athlete_user):
    now = gr._utcnow()
    _payload(db, now - timedelta(hours=49), "activities", athlete_user.id)
    b = client.get(f"{BASE}/push-status", headers=_h(client)).json()
    assert b["stale"] is True and b["hours_since"] > 48
    _payload(db, now - timedelta(hours=47), "dailies", athlete_user.id)
    assert client.get(f"{BASE}/push-status", headers=_h(client)).json()["stale"] is False


def test_push_status_hueco_historico_11_13(client, db, athlete_user):
    """Reproduce el hueco real: datos 07-10/11, cero 11-13/11, revive el 14/11."""
    with patch.object(gr, "_utcnow", return_value=gr.datetime(2026, 11, 14, 18, 0)):
        for d in (7, 8, 9, 10, 14):
            _payload(db, gr.datetime(2026, 11, d, 12, 0), "activities", athlete_user.id)
        b = client.get(f"{BASE}/push-status", headers=_h(client)).json()
    assert b["stale"] is False  # hoy revivio
    assert b["last_gap"] == {"from": "2026-11-11", "to": "2026-11-13", "days": 3, "ongoing": False}


def test_push_status_hueco_en_curso(client, db, athlete_user):
    with patch.object(gr, "_utcnow", return_value=gr.datetime(2026, 11, 14, 18, 0)):
        _payload(db, gr.datetime(2026, 11, 10, 12, 0), "activities", athlete_user.id)
        b = client.get(f"{BASE}/push-status", headers=_h(client)).json()
    assert b["stale"] is True
    assert b["last_gap"]["ongoing"] is True and b["last_gap"]["from"] == "2026-11-11"


def test_push_status_no_expone_contenido(client, db, athlete_user):
    db.add(GarminPushPayload(payload_type="dailies", user_id=athlete_user.id,
                             payload_json='{"dailies":[{"steps":99999}]}', processed=True))
    db.commit()
    assert "99999" not in client.get(f"{BASE}/push-status", headers=_h(client)).text


# -- UI (retorno OAuth, botones, i18n, build) ----------------------------------

APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_retorno_garmin_no_duplica_la_tarjeta():
    assert "WEARABLE_OAUTH = ['polar', 'wahoo'];" in APP  # lista de tarjetas intacta
    assert "'garmin'" not in re.search(r"var WEARABLE_OAUTH = \[[^\]]*\]", APP).group(0)
    assert "function garminReturnRead(" in APP and "q.get('garmin')" in APP
    assert "garminReturnConsume()" in APP.split("function initApp(")[1][:1500]
    assert "dashboard.html" in APP.split("function garminReturnConsume(")[1][:1200]


def test_boton_sync_garmin_en_app_y_web():
    assert "/integrations/garmin/sync" in APP and "garminOfficialSync()" in APP
    assert "/integrations/garmin/sync" in WEB and 'id="btn-garmin-off-sync"' in WEB
    assert "/integrations/garmin/push-status" in APP and "/integrations/garmin/push-status" in WEB
    assert APP.count("showOfficialSync: offOn") == 1 and WEB.count("showOfficialSync: offOn") == 1


def test_boton_sync_intervals_en_la_app_y_sigue_en_la_web():
    assert "intervalsSyncApp()" in APP and "/integrations/intervals/sync" in APP
    # el boton solo se pinta con intervals conectado
    assert re.search(r"ivState === 'connected'\s*\?\s*'<button[^']*id=\"pf-ivl-sync\"", APP)
    assert 'id="btn-intervals-sync"' in WEB and "function intervalsSync()" in WEB  # web intacta


KEYS = ["gsync_btn", "gsync_busy", "gsync_ok", "gsync_legacy", "gsync_reconnect", "gsync_not_connected",
        "gsync_unavailable", "gsync_pull_failed", "gsync_err", "gsync_only_act", "gsync_last", "gpush_last",
        "gpush_none", "gpush_dead", "gpush_dead_none", "gpush_gap", "garmin_ret_ok", "garmin_ret_denied",
        "garmin_ret_err"]


@pytest.mark.parametrize("k", KEYS)
def test_i18n_tres_idiomas(k):
    assert len(re.findall(rf"\b{k}:", I18N)) == 3, k


def test_build_379_y_sello():
    # BUILD >= 379 (sube en cada pila); el sello de i18n.js no cambia con el BUILD
    assert int(re.search(r"var BUILD_VERSION = '(\d+)';", SW).group(1)) >= 379
    assert "'/i18n.js?v=379'" in SW
    assert "i18n.js?v=379" in APP and "i18n.js?v=379" in WEB
