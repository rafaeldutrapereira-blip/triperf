"""FUENTE-UNICA (376): intervals.icu = fuente unica de lectura; Strava solo salida.

Cubre: tarjeta de intervals visible en ambos estados, estado honesto (invalido ante
401/403), desconectar idempotente que conserva datos, reconectar = OAuth fresco,
entrada de Strava apagada (y salida/conexion intacta).
"""
import asyncio
import base64
import json
import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from api import intervals_connector as ic
from api import intervals_sync_service as iss
from api.crypto import encrypt
from api.models import GarminActivity, GarminPlannedWorkout, User, WellnessLog
from api.routes import strava_routes as sr

from .conftest import auth_headers, login

ROOT = Path(__file__).resolve().parents[2]
SCOPE = "ACTIVITY:READ,CALENDAR:WRITE,SETTINGS:READ,WELLNESS:READ"
ST = "/api/integrations/intervals/status"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(ic, "CLIENT_ID", "test_intervals_id")
    monkeypatch.setattr(ic, "CLIENT_SECRET", "test_intervals_secret")


@pytest.fixture
def me(db, athlete_user):
    athlete_user.plan_nivel = "elite"
    db.commit()
    return athlete_user


def _h(client):
    h = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    client.cookies.clear()
    return h


def _connect(db, u, athlete="i794934"):
    ic.save_tokens(u, "tok", athlete, db, scope=SCOPE)


def _mock_reads(monkeypatch, acts=None, exc=None):
    monkeypatch.setattr(ic, "fetch_activities", AsyncMock(return_value=acts or [], side_effect=exc))
    monkeypatch.setattr(ic, "fetch_wellness", AsyncMock(return_value=[]))
    monkeypatch.setattr(ic, "fetch_events", AsyncMock(return_value=[]))


# ── Estado de la tarjeta ────────────────────────────────────────────────────

def test_status_sin_token_es_no_conectado(client, me):
    d = client.get(ST, headers=_h(client)).json()
    assert d["state"] == "not_connected" and d["connected"] is False
    assert d["has_token"] is False and d["athlete_id"] is None and d["last_sync"] is None


def test_status_con_token_expone_atleta_y_sin_sync_falsa(client, db, me):
    _connect(db, me)
    d = client.get(ST, headers=_h(client)).json()
    assert d["state"] == "connected" and d["connected"] is True
    assert d["athlete_id"] == "i794934"
    assert d["last_sync"] is None  # nada inventado: aun no hubo sync


def test_sync_ok_sella_la_ultima_sincronizacion_real(client, db, me, monkeypatch):
    _connect(db, me)
    _mock_reads(monkeypatch)
    res = asyncio.run(iss.sync_intervals_user(db, me.id))
    assert res["status"] == "ok"
    d = client.get(ST, headers=_h(client)).json()
    assert d["last_sync"] and d["state"] == "connected"


def test_401_en_sync_marca_conexion_invalida(client, db, me, monkeypatch):
    _connect(db, me)
    _mock_reads(monkeypatch, exc=ic.IntervalsAuthError("rechazo"))
    res = asyncio.run(iss.sync_intervals_user(db, me.id))
    assert res["status"] == "needs_reconnect"
    d = client.get(ST, headers=_h(client)).json()
    assert d["state"] == "invalid" and d["connected"] is False and d["invalid"] is True
    assert d["has_token"] is True and d["athlete_id"] == "i794934"
    assert d["last_sync"] is None
    # no se vuelve a golpear la API con un token muerto
    ic.fetch_activities.reset_mock()
    again = asyncio.run(iss.sync_intervals_user(db, me.id))
    assert again["status"] == "needs_reconnect"
    ic.fetch_activities.assert_not_called()


def test_error_no_auth_no_marca_invalido(client, db, me, monkeypatch):
    _connect(db, me)
    _mock_reads(monkeypatch, exc=ic.IntervalsError("respondio 500"))
    res = asyncio.run(iss.sync_intervals_user(db, me.id))
    assert res["errors"] >= 1
    d = client.get(ST, headers=_h(client)).json()
    assert d["state"] == "connected" and d["last_sync"] is None  # sync con error no se sella


def test_401_en_plan_marca_invalido(client, db, me, monkeypatch):
    _connect(db, me)
    monkeypatch.setattr(ic, "fetch_events", AsyncMock(side_effect=ic.IntervalsAuthError("x")))
    res = asyncio.run(iss.sync_planned_user(db, me.id))
    assert res["planned_status"] == "needs_reconnect"
    assert client.get(ST, headers=_h(client)).json()["state"] == "invalid"


def test_http_401_y_403_levantan_error_de_auth(monkeypatch):
    class _R:
        def __init__(self, code):
            self.status_code, self.headers = code, {}

    class _C:
        code = 401

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _R(_C.code)

    monkeypatch.setattr(ic.httpx, "AsyncClient", _C)
    for code in (401, 403):
        _C.code = code
        with pytest.raises(ic.IntervalsAuthError):
            asyncio.run(ic.fetch_activities("t", "2026-01-01", "2026-01-02"))
    _C.code = 500
    with pytest.raises(ic.IntervalsError) as e:
        asyncio.run(ic.fetch_activities("t", "2026-01-01", "2026-01-02"))
    assert not isinstance(e.value, ic.IntervalsAuthError)


def test_backfill_corta_ante_401(db, me, monkeypatch):
    _connect(db, me)
    _mock_reads(monkeypatch, exc=ic.IntervalsAuthError("x"))
    res = asyncio.run(iss.backfill_intervals_user(db, me.id, "2019-01-01"))
    assert res["status"] == "needs_reconnect" and res["windows"] == 1


# ── Desconectar ─────────────────────────────────────────────────────────────

def test_desconectar_limpia_credenciales_y_conserva_datos(client, db, me):
    _connect(db, me)
    ic.mark_synced(me, db)
    ic.mark_invalid(me, db)
    day = date.today().isoformat()
    db.add(GarminActivity(user_id=me.id, activity_id="intervals:1", sport="run", dur_min=30,
                          dist_km=5, name="x", tss=40, date_iso=day))
    db.add(WellnessLog(user_id=me.id, date_iso=day))
    db.add(GarminPlannedWorkout(user_id=me.id, date_iso=day, sport="run", title="p",
                                source="intervals", garmin_scheduled_id="intervals:9"))
    db.commit()
    h = _h(client)
    r = client.delete("/api/integrations/intervals/disconnect", headers=h)
    assert r.status_code == 200 and r.json() == {"ok": True, "was_connected": True}
    db.refresh(me)
    assert me.intervals_access_token is None and me.intervals_athlete_id is None
    assert me.intervals_scope is None and me.intervals_connected_at is None
    assert me.intervals_invalid_at is None and me.intervals_last_sync_at is None
    assert db.query(GarminActivity).filter_by(user_id=me.id).count() == 1
    assert db.query(WellnessLog).filter_by(user_id=me.id).count() == 1
    assert db.query(GarminPlannedWorkout).filter_by(user_id=me.id, source="intervals").count() == 1
    assert client.get(ST, headers=h).json()["state"] == "not_connected"


def test_desconectar_es_idempotente(client, db, me):
    h = _h(client)
    for _ in range(2):
        r = client.delete("/api/integrations/intervals/disconnect", headers=h)
        assert r.status_code == 200 and r.json()["was_connected"] is False


def test_token_de_otra_cuenta_se_puede_descartar_y_reconectar(client, db, me):
    """Caso real: token de una cuenta revocada -> invalido -> reconectar deja estado limpio."""
    _connect(db, me, athlete="i786864")
    ic.mark_invalid(me, db)
    h = _h(client)
    assert client.get(ST, headers=h).json()["state"] == "invalid"
    r = client.post("/api/integrations/intervals/reconnect?ret=profile", headers=h)
    assert r.status_code == 200
    d = client.get(ST, headers=h).json()
    assert d["state"] == "not_connected" and d["athlete_id"] is None


# ── Reconectar / OAuth ──────────────────────────────────────────────────────

def _state_of(url):
    st = re.search(r"state=([^&]+)", url).group(1)
    from urllib.parse import unquote
    st = unquote(st)
    return json.loads(base64.urlsafe_b64decode(st + "=" * (-len(st) % 4)).decode())


def test_reconectar_suelta_credenciales_e_inicia_oauth_fresco(client, db, me):
    _connect(db, me)
    r = client.post("/api/integrations/intervals/reconnect?ret=profile", headers=_h(client))
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert url.startswith("https://intervals.icu/oauth/authorize?")
    assert "client_id=test_intervals_id" in url
    assert _state_of(url) == {"uid": me.id, "ret": "profile"}
    db.refresh(me)
    assert me.intervals_access_token is None


def test_reconectar_sin_configuracion_no_toca_la_conexion(client, db, me, monkeypatch):
    _connect(db, me)
    monkeypatch.setattr(ic, "CLIENT_ID", "")
    r = client.post("/api/integrations/intervals/reconnect", headers=_h(client))
    assert r.status_code == 503
    db.refresh(me)
    assert me.intervals_access_token is not None


def test_ret_solo_acepta_destino_conocido(client, me):
    r = client.post("/api/integrations/intervals/reconnect?ret=https://evil.example", headers=_h(client))
    assert _state_of(r.json()["authorize_url"]) == {"uid": me.id}


def test_connect_redirige_a_intervals(client, me):
    r = client.get("/api/integrations/intervals/connect?ret=profile", headers=_h(client),
                   follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"].startswith("https://intervals.icu/oauth/authorize")


def test_callback_guarda_token_nuevo_limpia_invalido_y_vuelve_al_perfil(client, db, me, monkeypatch):
    _connect(db, me, athlete="i786864")
    ic.mark_invalid(me, db)
    ic.clear_tokens(me, db)  # lo que hizo /reconnect
    monkeypatch.setattr(ic, "exchange_code", AsyncMock(return_value={"access_token": "nuevo", "scope": SCOPE}))
    monkeypatch.setattr(ic, "fetch_athlete_id", AsyncMock(return_value="i794934"))
    state = base64.urlsafe_b64encode(json.dumps({"uid": me.id, "ret": "profile"}).encode()).decode()
    r = client.get(f"/api/integrations/intervals/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"].endswith("/athlete_profile.html?intervals=connected")
    d = client.get(ST, headers=_h(client)).json()
    assert d["state"] == "connected" and d["athlete_id"] == "i794934"


def test_callback_sin_ret_mantiene_el_destino_historico(client, me):
    state = base64.urlsafe_b64encode(json.dumps({"uid": me.id}).encode()).decode()
    r = client.get(f"/api/integrations/intervals/callback?error=access_denied&state={state}",
                   follow_redirects=False)
    assert r.headers["location"].endswith("/indoor_workout.html?intervals=denied")


# ── Strava solo salida ──────────────────────────────────────────────────────

def test_strava_entrada_apagada_por_defecto(client, me, monkeypatch):
    monkeypatch.delenv("STRAVA_INGEST_ENABLED", raising=False)
    h = _h(client)
    assert client.get("/api/strava/status", headers=h).json()["ingest_enabled"] is False
    assert client.post("/api/strava/sync?days=7", headers=h).status_code == 404


def test_strava_nucleo_no_toca_la_red_con_la_entrada_apagada(db, me, monkeypatch):
    monkeypatch.delenv("STRAVA_INGEST_ENABLED", raising=False)
    tok = AsyncMock(side_effect=AssertionError("no debe pedir token"))
    monkeypatch.setattr(sr, "_get_valid_access_token", tok)
    res = asyncio.run(sr._sync_strava_activities(me, db, 1))
    assert res["disabled"] is True and res["imported"] == 0
    tok.assert_not_called()


def test_strava_job_programado_no_trae_actividades(db, me, monkeypatch):
    from api import scheduler
    monkeypatch.delenv("STRAVA_INGEST_ENABLED", raising=False)
    me.strava_access_token = "x"
    db.commit()
    core = AsyncMock()
    monkeypatch.setattr(sr, "_sync_strava_activities", core)
    monkeypatch.setattr(sr, "_CLIENT_ID", "id")
    monkeypatch.setattr(sr, "_CLIENT_SECRET", "secret")
    scheduler._background_strava_sync_all()
    core.assert_not_called()


def test_strava_entrada_se_puede_encender_con_el_flag(client, me, monkeypatch):
    monkeypatch.setenv("STRAVA_INGEST_ENABLED", "1")
    monkeypatch.setattr(sr, "_CLIENT_ID", "id")
    monkeypatch.setattr(sr, "_CLIENT_SECRET", "secret")
    monkeypatch.setattr(sr, "_sync_strava_activities", AsyncMock(return_value={"ok": True, "imported": 0}))
    h = _h(client)
    assert client.get("/api/strava/status", headers=h).json()["ingest_enabled"] is True
    assert client.post("/api/strava/sync?days=7", headers=h).status_code == 200


def test_strava_conectar_y_desconectar_siguen_funcionando(client, db, me, monkeypatch):
    monkeypatch.delenv("STRAVA_INGEST_ENABLED", raising=False)
    monkeypatch.setattr(sr, "_CLIENT_ID", "id")
    monkeypatch.setattr(sr, "_CLIENT_SECRET", "secret")
    h = _h(client)
    r = client.get("/api/strava/connect", headers=h, follow_redirects=False)
    assert r.status_code in (302, 307) and "strava.com/oauth/authorize" in r.headers["location"]
    me.strava_access_token = "gAAtest"
    me.strava_athlete_id = "1"
    db.commit()
    assert client.get("/api/strava/status", headers=h).json()["connected"] is True
    assert client.delete("/api/strava/disconnect", headers=h).status_code == 200
    db.refresh(me)
    assert me.strava_access_token is None


# ── UI estatica ─────────────────────────────────────────────────────────────

def _read(name):
    return (ROOT / name).read_text(encoding="utf8")


def test_tarjeta_de_intervals_existe_siempre_y_no_cuelga_de_otro_estado():
    h = _read("athlete_profile.html")
    i = h.index('id="intervals-card"')
    head = h[max(0, i - 120):i]
    assert "display: none" not in head and "display:none" not in head
    for btn in ("btn-intervals-con", "btn-intervals-sync", "btn-intervals-re", "btn-intervals-dis"):
        assert f'id="{btn}"' in h
    assert "loadIntervalsStatus();" in h
    # se pinta en ambos estados: no esta dentro de la tarjeta de historial (hist-card, oculta)
    assert h.index('id="hist-card"') < i
    assert h.index('id="hist-card"') < h.index('<div class="card">', h.index('id="hist-card"')) < i


def test_textos_i18n_de_la_tarjeta_en_tres_idiomas():
    t = _read("i18n.js")
    for k in ("ivl_state_invalid", "ivl_state_off", "ivl_btn_reconnect", "ivl_confirm_disconnect",
              "ivl_strava_out_only"):
        assert len(re.findall(rf"\b{k}:", t)) == 3, k
    assert t.count("Solo para compartir tus entrenamientos hacia Strava") == 1


def test_sello_y_build_376():
    sw = _read("sw.js")
    assert "var BUILD_VERSION = '376';" in sw
    assert "'/i18n.js?v=376'" in sw
    assert "i18n.js?v=376" in _read("athlete_profile.html")


def test_politica_de_borrado_de_cuenta_cubre_las_columnas_nuevas():
    src = _read("api/account_deletion.py")
    assert "intervals_invalid_at" in src and "intervals_last_sync_at" in src
