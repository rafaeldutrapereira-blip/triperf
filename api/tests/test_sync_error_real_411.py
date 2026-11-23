"""SYNC-ERROR-REAL (BUILD 411): log del intento de sync manual, error honesto por causa e
ingest del push idempotente. Red de Garmin mockeada."""
import logging
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from api import garmin_ingest as gi
from api import garmin_official as go
from api.models import GarminActivity, GarminSleepSession
from api.routes import garmin_official_routes as gr
from api.tests.test_sync_conexiones_379 import BASE, TOKENS, _act, _h, configured  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]


def _sync(client, db, athlete_user, exc):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "_get_activities_window", side_effect=exc):
        return client.post(f"{BASE}/sync", headers=_h(client))


# -- 1. log del intento ---------------------------------------------------------

def test_log_intento_ok(client, db, athlete_user, configured, caplog):
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with caplog.at_level(logging.INFO, logger="labx.garmin_official"), \
            patch.object(go, "_get_activities_window", return_value=[_act(21)]):
        r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 200
    lines = [m for m in caplog.messages if m.startswith("[GARMIN-SYNC]")]
    assert any(f"inicio user={athlete_user.id}" in m for m in lines)
    fin = [m for m in lines if " fin " in m][0]
    assert f"user={athlete_user.id}" in fin and "result=ok" in fin and re.search(r"dur_s=\d+\.\d", fin)


def test_log_intento_fallido_lleva_el_error_exacto(client, db, athlete_user, configured, caplog):
    with caplog.at_level(logging.INFO, logger="labx.garmin_official"):
        r = _sync(client, db, athlete_user, go.GarminOfficialError("Garmin rechazo el pull de actividades (500)"))
    assert r.status_code == 502
    fin = [m for m in caplog.messages if m.startswith("[GARMIN-SYNC]") and " fin " in m][0]
    assert "result=garmin_error" in fin and "rechazo el pull de actividades (500)" in fin


def test_log_sin_conexion(client, db, athlete_user, configured, caplog):
    with caplog.at_level(logging.INFO, logger="labx.garmin_official"):
        client.post(f"{BASE}/sync", headers=_h(client))
    assert any("result=not_connected" in m for m in caplog.messages)


# -- 2. error honesto por causa -------------------------------------------------

@pytest.mark.parametrize("msg,status", [
    ("Garmin no respondio (ReadTimeout)", "pull_timeout"),
    ("Garmin no respondio (ConnectTimeout)", "pull_timeout"),
    ("Garmin rechazo el pull de actividades (500)", "garmin_error"),
    ("Garmin rechazo el pull de actividades (503)", "garmin_error"),
    ("Garmin no respondio (ConnectError)", "garmin_error"),
    ("Garmin no autoriza el pull de actividades (403)", "pull_failed"),
    ("Respuesta de actividades invalida", "pull_failed"),
])
def test_error_distingue_la_causa(client, db, athlete_user, configured, msg, status):
    r = _sync(client, db, athlete_user, go.GarminOfficialError(msg))
    b = r.json()
    assert r.status_code == 502 and b["ok"] is False and b["status"] == status
    assert b["errors"][0]["message"] == b["message"] != ""


def test_mensajes_de_causa_son_distintos(client, db, athlete_user, configured):
    a = _sync(client, db, athlete_user, go.GarminOfficialError("x (ReadTimeout)")).json()["message"]
    b = _sync(client, db, athlete_user, go.GarminOfficialError("x (500)")).json()["message"]
    assert a != b and "tard" in a and "error" in b


def test_frontend_mapea_causas_con_i18n():
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    for page in ("athlete-app.html", "athlete_profile.html"):
        src = (ROOT / page).read_text(encoding="utf-8")
        assert "pull_timeout: ['gsync_timeout'" in src and "garmin_error: ['gsync_garmin_error'" in src, page
        assert "'gsync_network'" in src, page
    for k in ("gsync_timeout", "gsync_garmin_error", "gsync_network"):
        assert len(re.findall(rf"\b{k}:", i18n)) == 3, k


# -- 3. ingest idempotente ------------------------------------------------------

def test_actividad_duplicada_por_carrera_se_ignora_en_silencio(db, athlete_user, caplog):
    assert gi._upsert_activity(db, athlete_user.id, _act(31)) is True
    db.commit()
    real_first = db.query(GarminActivity).filter

    class _Miss:  # simula la carrera: la consulta previa no ve la fila que otra via ya inserto
        def first(self):
            return None

    def fake_filter(*a, **k):
        return _Miss()

    with caplog.at_level(logging.WARNING), patch.object(db, "query") as q:
        q.return_value.filter = fake_filter
        with patch.object(gi, "mark_new_activity"):
            assert gi._upsert_activity(db, athlete_user.id, _act(31)) is False
    db.rollback()
    assert db.query(GarminActivity).filter_by(user_id=athlete_user.id, activity_id="31").count() == 1
    assert not [m for m in caplog.messages if "IntegrityError" in m or "UNIQUE" in m]


def test_sueno_duplicado_por_carrera_se_ignora(db, athlete_user):
    it = {"calendarDate": "2026-11-20", "startTimeInSeconds": 1763600000, "durationInSeconds": 25000}
    assert gi._upsert_sleep(db, athlete_user.id, it) is True
    db.commit()

    class _Miss:
        def first(self):
            return None

    with patch.object(db, "query") as q:
        q.return_value.filter = lambda *a, **k: _Miss()
        assert gi._upsert_sleep(db, athlete_user.id, it) is False
    db.rollback()
    assert db.query(GarminSleepSession).filter_by(user_id=athlete_user.id, date_iso="2026-11-20").count() == 1


def test_duplicado_no_rompe_el_resto_del_lote(db, athlete_user):
    """Un duplicado dentro del savepoint no revierte lo escrito antes en la misma transaccion."""
    assert gi._upsert_activity(db, athlete_user.id, _act(41)) is True
    row = GarminActivity(user_id=athlete_user.id, activity_id="41", name="dup", sport="run",
                         date_iso="2025-11-13", date_label="13 Nov", dur_min=1, dist_km=1.0,
                         icon="x", color="c", stroke="s")
    assert gi._insert_ignoring_duplicate(db, row) is False
    assert gi._upsert_activity(db, athlete_user.id, _act(42)) is True
    db.commit()
    assert db.query(GarminActivity).filter_by(user_id=athlete_user.id).count() == 2
