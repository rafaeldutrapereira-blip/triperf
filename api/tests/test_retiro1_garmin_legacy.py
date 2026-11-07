"""RETIRO-1: conexion Garmin legacy cerrada por defecto + interruptor de sync.

Sin red: la autenticacion Garmin (start_mfa_flow) y garminconnect se mockean.
"""
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from .conftest import login
from ..crypto import encrypt

ROOT = Path(__file__).resolve().parents[2]
CREDS = {"garmin_email": "a@garmin.com", "garmin_password": "secret"}


@pytest.fixture(autouse=True)
def _flags_limpios(monkeypatch):
    monkeypatch.delenv("GARMIN_LEGACY_CONNECT_ENABLED", raising=False)
    monkeypatch.delenv("GARMIN_LEGACY_SYNC_ENABLED", raising=False)


def _tok(client, email="athlete@test.com", pw="AthlPass123"):
    t = login(client, email, pw)
    client.cookies.clear()
    return {"Authorization": f"Bearer {t}"}


def _mock_auth(monkeypatch):
    m = MagicMock(return_value={"ok": True, "needs_mfa": False})
    monkeypatch.setattr("api.garmin_pull_service.start_mfa_flow", m)
    return m


# ── Conexion nueva ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor", [None, "0", "", "true", "yes"])
def test_conexion_nueva_rechazada_410(client, athlete_user, db, monkeypatch, valor):
    if valor is not None:
        monkeypatch.setenv("GARMIN_LEGACY_CONNECT_ENABLED", valor)
    auth = _mock_auth(monkeypatch)
    r = client.post("/api/athlete/garmin-credentials", json=CREDS, headers=_tok(client))
    assert r.status_code == 410
    assert "cerrada" in r.text
    auth.assert_not_called()
    db.refresh(athlete_user)
    assert athlete_user.garmin_email is None and athlete_user.garmin_password is None


def test_conexion_permitida_con_flag_1(client, athlete_user, db, monkeypatch):
    monkeypatch.setenv("GARMIN_LEGACY_CONNECT_ENABLED", "1")
    auth = _mock_auth(monkeypatch)
    r = client.post("/api/athlete/garmin-credentials", json=CREDS, headers=_tok(client))
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    auth.assert_called_once()
    db.refresh(athlete_user)
    assert athlete_user.garmin_email == "a@garmin.com"


def test_admin_set_garmin_cerrado_por_defecto(client, admin_user, athlete_user, db):
    r = client.post(f"/api/admin/users/{athlete_user.id}/garmin", json=CREDS,
                    headers=_tok(client, "admin@test.com", "AdminPass123"))
    assert r.status_code == 410
    db.refresh(athlete_user)
    assert athlete_user.garmin_email is None


# ── Desconexion de usuario ya conectado (flags en default) ───────────────────

def test_desconexion_sigue_funcionando_con_defaults(client, athlete_user, db):
    h = _tok(client)
    athlete_user.garmin_email = "a@garmin.com"
    athlete_user.garmin_password = encrypt("secret")
    db.commit()
    r = client.delete("/api/athlete/garmin-credentials", headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True
    db.refresh(athlete_user)
    assert athlete_user.garmin_email is None and athlete_user.garmin_password is None


def test_desconexion_tambien_con_sync_apagado(client, athlete_user, db, monkeypatch):
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    h = _tok(client)
    athlete_user.garmin_email = "a@garmin.com"
    athlete_user.garmin_password = encrypt("secret")
    db.commit()
    r = client.delete("/api/athlete/garmin-credentials", headers=h)
    assert r.status_code == 200
    db.refresh(athlete_user)
    assert athlete_user.garmin_email is None


# ── Status expone los flags ──────────────────────────────────────────────────

def test_status_expone_flags(client, athlete_user, monkeypatch):
    h = _tok(client)
    d = client.get("/api/athlete/garmin/sync-status", headers=h).json()
    assert d["connect_enabled"] is False and d["sync_enabled"] is True
    monkeypatch.setenv("GARMIN_LEGACY_CONNECT_ENABLED", "1")
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    d = client.get("/api/athlete/garmin/sync-status", headers=h).json()
    assert d["connect_enabled"] is True and d["sync_enabled"] is False


def test_status_con_fila_de_sync_tambien_trae_flags(client, athlete_user, db):
    from ..models import GarminSyncStatus
    db.add(GarminSyncStatus(user_id=athlete_user.id, status="ok"))
    db.commit()
    d = client.get("/api/athlete/garmin/sync-status", headers=_tok(client)).json()
    assert d["status"] == "ok" and "connect_enabled" in d and "sync_enabled" in d


# ── Sync ─────────────────────────────────────────────────────────────────────

def _fake_garminconnect(monkeypatch):
    """Cualquier uso de garminconnect revienta el test: el no-op no debe tocarlo."""
    mod = types.ModuleType("garminconnect")
    boom = MagicMock(side_effect=AssertionError("garminconnect invocado"))
    mod.Garmin = boom
    monkeypatch.setitem(sys.modules, "garminconnect", mod)
    return boom


@pytest.mark.parametrize("valor", [None, "1"])
def test_sync_user_corre_con_flag_ausente_o_1(db, athlete_user, monkeypatch, valor):
    from ..garmin_pull_service import GarminPullService
    if valor is not None:
        monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", valor)
    boom = _fake_garminconnect(monkeypatch)
    athlete_user.garmin_email = "a@garmin.com"
    athlete_user.garmin_password = encrypt("secret")
    db.commit()
    res = GarminPullService(db).sync_user(athlete_user.id, force=True)
    # Llego al flujo real (intento de login con la libreria falsa), no al no-op
    assert res.get("reason") != "legacy_sync_disabled"
    assert boom.called


def test_sync_user_noop_limpio_con_flag_0(db, athlete_user, monkeypatch, caplog):
    from ..garmin_pull_service import GarminPullService
    from ..models import GarminSyncStatus
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    boom = _fake_garminconnect(monkeypatch)
    athlete_user.garmin_email = "a@garmin.com"
    athlete_user.garmin_password = encrypt("secret")
    db.commit()
    with caplog.at_level("INFO"):
        res = GarminPullService(db).sync_user(athlete_user.id, force=True)
    assert res == {"ok": True, "reason": "legacy_sync_disabled"}
    boom.assert_not_called()
    assert "GARMIN_LEGACY_SYNC_ENABLED=0" in caplog.text
    # no toca el estado de sync ni los datos del usuario
    assert db.query(GarminSyncStatus).filter_by(user_id=athlete_user.id).count() == 0
    db.refresh(athlete_user)
    assert athlete_user.garmin_email == "a@garmin.com"


def test_dispatch_omitido_con_flag_0(monkeypatch):
    from ..garmin_pull_service import dispatch_garmin_sync
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    bt = MagicMock()
    assert dispatch_garmin_sync("u1", bt) == "disabled"
    bt.add_task.assert_not_called()


def test_dispatch_normal_encola_con_defaults(monkeypatch):
    from ..garmin_pull_service import dispatch_garmin_sync
    monkeypatch.setattr("api.redis_client.is_available", lambda: False)
    bt = MagicMock()
    assert dispatch_garmin_sync("u1", bt) == "background"
    bt.add_task.assert_called_once()


def test_sync_manual_con_flag_0_no_encola(client, athlete_user, db, monkeypatch):
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    h = _tok(client)
    athlete_user.garmin_email = "a@garmin.com"
    athlete_user.garmin_password = encrypt("secret")
    db.commit()
    bg = MagicMock()
    monkeypatch.setattr("api.garmin_pull_service.background_sync_user", bg)
    r = client.post("/api/athlete/garmin/sync", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    bg.assert_not_called()


def test_sync_manual_con_defaults_encola(client, athlete_user, db, monkeypatch):
    h = _tok(client)
    athlete_user.garmin_email = "a@garmin.com"
    athlete_user.garmin_password = encrypt("secret")
    db.commit()
    monkeypatch.setattr("api.redis_client.is_available", lambda: False)
    monkeypatch.setattr("api.garmin_pull_service.background_sync_user", MagicMock())
    r = client.post("/api/athlete/garmin/sync", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "syncing"


def test_scheduler_omitido_con_flag_0(monkeypatch, caplog):
    from .. import scheduler
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    bg = MagicMock()
    monkeypatch.setattr("api.garmin_pull_service.background_sync_user", bg)
    with caplog.at_level("INFO"):
        scheduler._background_garmin_sync_all()
    bg.assert_not_called()
    assert "GARMIN_LEGACY_SYNC_ENABLED=0" in caplog.text


def test_provider_garmin_noop_con_flag_0(db, athlete_user, monkeypatch):
    """El proveedor 'garmin' delega en GarminPullService.sync_user: mismo no-op."""
    from ..garmin_pull_service import GarminPullService
    monkeypatch.setenv("GARMIN_LEGACY_SYNC_ENABLED", "0")
    boom = _fake_garminconnect(monkeypatch)
    athlete_user.garmin_email = "a@garmin.com"
    db.commit()
    assert GarminPullService(db).sync_user(athlete_user.id)["reason"] == "legacy_sync_disabled"
    boom.assert_not_called()


# ── Frontend / i18n / SW ─────────────────────────────────────────────────────

def test_front_sin_formulario_legacy():
    web = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
    onb = (ROOT / "onboarding.html").read_text(encoding="utf-8")
    for ident in ("g-email", "g-pass", "garmin-form", "btn-garmin-con"):
        assert f'id="{ident}"' not in web
    for fn in ("saveGarminCreds", "showGarminForm", "submitGarminMfa"):
        assert fn not in web
    assert "garmin-credentials" in web  # solo el DELETE (desconectar)
    assert "method: 'POST'" not in web.split("function garminDisconnect")[1][:600]
    assert "garmin-credentials" not in onb and "saveGarmin" not in onb
    # el estado de quien ya esta conectado sigue ahi
    assert 'id="btn-garmin-sync"' in web and 'id="btn-garmin-dis"' in web


def test_i18n_mensaje_onboarding_tres_idiomas_y_build():
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    assert len(re.findall(r"\bonb_garmin_connect_later:", i18n)) == 3
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert int(re.search(r"BUILD_VERSION = '(\d+)'", sw).group(1)) >= 334
