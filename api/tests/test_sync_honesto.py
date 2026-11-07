"""SYNC-HONESTO: sync_state / last_sync_at / data_until en garmin sync-status,
modelo de tarjeta/banner/franja y claves i18n. Sin red."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .conftest import login
from ..crypto import encrypt
from ..models import GarminActivity, GarminHealthDaily, GarminSyncStatus

ROOT = Path(__file__).resolve().parents[2]
URL = "/api/athlete/garmin/sync-status"


def _h(client):
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    return {"Authorization": f"Bearer {t}"}


def _creds(user, db):
    user.garmin_email = "a@garmin.com"
    user.garmin_password = encrypt("secret")
    db.commit()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _act(db, uid, d, n="1"):
    db.add(GarminActivity(user_id=uid, activity_id=n, date_iso=d, sport="run"))
    db.commit()


def test_none_sin_credenciales(client, athlete_user):
    h = _h(client)
    d = client.get(URL, headers=h).json()
    assert d["sync_state"] == "none" and d["data_until"] is None and d["last_sync_at"] is None


def test_never_con_credenciales_sin_fila(client, athlete_user, db):
    h = _h(client)
    _creds(athlete_user, db)
    d = client.get(URL, headers=h).json()
    assert d["sync_state"] == "never"
    assert "last_sync_at" in d and "has_credentials" in d


def test_never_con_fila_sin_sync_exitoso(client, athlete_user, db):
    h = _h(client)
    _creds(athlete_user, db)
    db.add(GarminSyncStatus(user_id=athlete_user.id, status="never"))
    db.commit()
    assert client.get(URL, headers=h).json()["sync_state"] == "never"


def test_needs_reauth_aunque_el_ultimo_ok_sea_reciente(client, athlete_user, db):
    h = _h(client)
    _creds(athlete_user, db)
    db.add(GarminSyncStatus(user_id=athlete_user.id, status="needs_reauth",
                            last_sync_at=_now() - timedelta(hours=1)))
    db.commit()
    d = client.get(URL, headers=h).json()
    assert d["sync_state"] == "needs_reauth"
    assert d["status"] == "needs_reauth" and d["last_sync_at"]


def test_live_y_stale_por_umbral_48h(client, athlete_user, db):
    h = _h(client)
    _creds(athlete_user, db)
    row = GarminSyncStatus(user_id=athlete_user.id, status="ok",
                           last_sync_at=_now() - timedelta(hours=47))
    db.add(row)
    db.commit()
    assert client.get(URL, headers=h).json()["sync_state"] == "live"
    row.last_sync_at = _now() - timedelta(hours=49)
    db.commit()
    assert client.get(URL, headers=h).json()["sync_state"] == "stale"


def test_data_until_maximo_entre_actividad_y_salud(client, athlete_user, db):
    h = _h(client)
    _act(db, athlete_user.id, "2026-06-25", "a1")
    _act(db, athlete_user.id, "2026-06-10", "a2")
    assert client.get(URL, headers=h).json()["data_until"] == "2026-06-25"
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso="2026-07-02"))
    db.commit()
    assert client.get(URL, headers=h).json()["data_until"] == "2026-07-02"


def test_datos_no_se_borran_con_conexion_caida(client, athlete_user, db):
    h = _h(client)
    _creds(athlete_user, db)
    db.add(GarminSyncStatus(user_id=athlete_user.id, status="needs_reauth"))
    _act(db, athlete_user.id, "2026-06-25")
    d = client.get(URL, headers=h).json()
    assert d["sync_state"] == "needs_reauth" and d["data_until"] == "2026-06-25"
    assert db.query(GarminActivity).filter_by(user_id=athlete_user.id).count() == 1


# -- Frontend / i18n ---------------------------------------------------------

WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
IW = (ROOT / "indoor_workout.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
KEYS = ("garmin_legacy_down", "garmin_data_until", "gmig_text_down",
        "gmig_text_down_until", "gmig_text_down_cta",
        "iw_watch_stale_title", "iw_watch_stale_nodate")


def test_i18n_claves_en_tres_idiomas_con_placeholders():
    for k in KEYS:
        vals = re.findall(rf"\b{k}: '((?:[^'\\]|\\.)*)'", I18N)
        assert len(vals) == 3, k
        assert len({tuple(re.findall(r"\{\w+\}", v)) for v in vals}) == 1, k


def test_modelo_y_consumidores_usan_sync_state():
    for src in (WEB, APP):
        assert "legacyDown" in src and "syncState" in src
        assert "garmin_legacy_down" in src and "garmin_data_until" in src
    assert "function gmigText(" in WEB and "gmig_text_down" in WEB
    assert "function iwWatchOffModel(" in IW and "iw_watch_stale_title" in IW
    assert "/athlete/garmin/sync-status" in IW


def test_sw_build_336():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 336
