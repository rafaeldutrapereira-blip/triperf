"""CARGA-AL-DIA: el recalculo de garmin_training_load lo gatilla la via viva, el dashboard
dice hasta cuando llega la carga, y el sello de sync refleja la via viva mas reciente."""
import asyncio
import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from api import garmin_ingest as gi
from api import intervals_connector as ic
from api import intervals_sync_service as iss
from api.crypto import encrypt
from api.models import (
    GarminActivity, GarminOAuthToken, GarminPushPayload, GarminSyncStatus, GarminTrainingLoad,
)

from .conftest import login

ROOT = Path(__file__).resolve().parents[2]
READ_SCOPE = "ACTIVITY:READ,CALENDAR:WRITE,SETTINGS:READ,WELLNESS:READ"
DASH = "/api/athlete/dashboard?fresh=true"
SYNC = "/api/athlete/garmin/sync-status"


def _h(client):
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    return {"Authorization": f"Bearer {t}"}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(delta=0):
    return (date.today() + timedelta(days=delta)).isoformat()


def _connect_intervals(db, user):
    user.intervals_access_token = encrypt("tok-secret")
    user.intervals_scope = READ_SCOPE
    db.commit()


def _load_dates(db, uid):
    rows = db.query(GarminTrainingLoad).filter(GarminTrainingLoad.user_id == uid).all()
    return sorted(r.date_iso for r in rows)


def _seed_stale(db, uid, last_day=-2):
    """Actividades y carga que llegan solo hasta `last_day` (la tabla derivada congelada)."""
    db.add(GarminActivity(user_id=uid, activity_id="old-1", sport="run", date_iso=_iso(last_day - 1),
                          dur_min=50, tss=60.0, name="viejo"))
    db.commit()
    from api.services.training_service import recalculate_training_load
    recalculate_training_load(db, uid)
    # congelar: dejar la serie derivada solo hasta last_day
    db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id == uid, GarminTrainingLoad.date_iso > _iso(last_day)
    ).delete()
    db.commit()
    assert _load_dates(db, uid)[-1] == _iso(last_day)


def _run_intervals(db, user, monkeypatch, acts):
    monkeypatch.setattr(ic, "fetch_activities", AsyncMock(return_value=acts))
    monkeypatch.setattr(ic, "fetch_wellness", AsyncMock(return_value=[]))
    return asyncio.run(iss.sync_intervals_user(db, user.id))


def _icu_act(day_iso, tss=80.0, ext="i-today"):
    return {"id": ext, "start_date_local": day_iso + "T07:30:00", "type": "Run", "name": "Hoy",
            "moving_time": 3000, "distance": 10000.0, "average_heartrate": 150.0,
            "icu_training_load": tss}


def test_intervals_sync_triggers_recalc_and_dashboard_matches(db, client, athlete_user, monkeypatch):
    uid = athlete_user.id
    _connect_intervals(db, athlete_user)
    _seed_stale(db, uid)

    r = _run_intervals(db, athlete_user, monkeypatch, [_icu_act(_iso(0), tss=80.0)])
    assert r["status"] == "ok" and r["imported"] == 1

    dates = _load_dates(db, uid)
    assert dates[-1] == _iso(0)  # la serie llega hasta hoy
    assert len(dates) == len(set(dates))  # upsert por dia, sin duplicados

    d = client.get(DASH, headers=_h(client)).json()
    monday = _iso(-date.today().weekday())
    expected = sum(float(a.tss or 0) for a in db.query(GarminActivity).filter(
        GarminActivity.user_id == uid, GarminActivity.date_iso >= monday).all())
    assert abs(d["tss_week"] - round(expected, 1)) < 0.11
    assert d["load_last_date"] == _iso(0)
    assert d["load_projected"] is False


def test_failed_sync_does_not_recalc(db, athlete_user, monkeypatch):
    _connect_intervals(db, athlete_user)
    _seed_stale(db, athlete_user.id)
    called = []
    monkeypatch.setattr(iss, "recalc_load_after_sync", lambda *a, **k: called.append(1))
    r = asyncio.run(iss.sync_intervals_user(db, "no-existe"))
    assert r["status"] == "not_connected" and not called


def test_official_garmin_ingest_triggers_recalc(db, athlete_user):
    uid = athlete_user.id
    db.add(GarminOAuthToken(user_id=uid, garmin_user_id="g-1", access_token="x"))
    db.commit()
    _seed_stale(db, uid)
    start = int(datetime.combine(date.today(), datetime.min.time()).replace(
        tzinfo=timezone.utc).timestamp()) + 8 * 3600
    item = {"userId": "g-1", "summaryId": "s-1", "activityId": 991, "activityName": "Hoy",
            "activityType": "RUNNING", "startTimeInSeconds": start, "startTimeOffsetInSeconds": 0,
            "durationInSeconds": 3000, "distanceInMeters": 10000.0}
    db.add(GarminPushPayload(payload_type="activities", user_id=uid, processed=False,
                             payload_json=json.dumps({"activities": [item]})))
    db.commit()
    s = gi.process_pending(db)
    assert s["written"] == 1
    assert _load_dates(db, uid)[-1] == _iso(0)


def test_dashboard_marks_projection_when_load_is_stale(db, client, athlete_user):
    uid = athlete_user.id
    _seed_stale(db, uid)
    d = client.get(DASH, headers=_h(client)).json()
    assert d["load_last_date"] == _iso(-2)
    assert d["load_projected"] is True


def test_sync_stamp_reflects_most_recent_live_route(db, client, athlete_user):
    uid = athlete_user.id
    old = _now() - timedelta(days=5)
    db.add(GarminSyncStatus(user_id=uid, status="ok", last_sync_at=old))
    db.add(GarminActivity(user_id=uid, activity_id="intervals:z1", sport="run", date_iso=_iso(0),
                          dur_min=30, synced_at=_now()))
    db.commit()
    h = _h(client)
    body = client.get(SYNC, headers=h).json()
    assert body["last_sync"][:10] == _now().date().isoformat()  # via viva reciente
    assert body["last_sync_at"].startswith(old.date().isoformat())  # la fila legacy no se toca
    assert client.get(DASH, headers=h).json()["last_sync"][:10] == _now().date().isoformat()


def test_sync_stamp_without_activities_falls_back_to_row(db, client, athlete_user):
    old = _now() - timedelta(days=3)
    db.add(GarminSyncStatus(user_id=athlete_user.id, status="ok", last_sync_at=old))
    db.commit()
    body = client.get(SYNC, headers=_h(client)).json()
    assert body["last_sync"] == str(old)[:16]


def _repair_module():
    spec = importlib.util.spec_from_file_location("repair_training_load",
                                                  ROOT / "scripts" / "repair_training_load.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_repair_script_fixes_only_stale_users_and_is_idempotent(db, athlete_user):
    mod = _repair_module()
    uid = athlete_user.id
    _seed_stale(db, uid)
    # actividad nueva que la tabla derivada no ve
    db.add(GarminActivity(user_id=uid, activity_id="new-1", sport="bike", date_iso=_iso(0),
                          dur_min=60, tss=70.0))
    db.commit()
    assert [u[0] for u in mod.find_stale_users(db)] == [uid]
    assert mod.repair(db, dry_run=True)["repaired"] == 0
    assert _load_dates(db, uid)[-1] == _iso(-2)  # dry-run no toca nada

    res = mod.repair(db)
    assert res["stale"] == 1 and res["repaired"] == 1 and res["until"] == _iso(0)
    assert _load_dates(db, uid)[-1] == _iso(0)
    before = db.query(GarminTrainingLoad).filter_by(user_id=uid).count()

    res2 = mod.repair(db)
    assert res2["stale"] == 0 and res2["repaired"] == 0
    assert db.query(GarminTrainingLoad).filter_by(user_id=uid).count() == before


def test_ui_guards_in_dashboard_and_i18n():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    assert "load_last_date" in html and "load_projected" in html
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    assert i18n.count("dash_load_asof:") == 3 and i18n.count("dash_estimated:") == 3
