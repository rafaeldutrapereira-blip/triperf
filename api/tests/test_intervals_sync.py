"""Lectura desde intervals.icu: scopes, sync de actividades y wellness (APIs mockeadas)."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from api import intervals_connector as ic
from api import intervals_sync_service as iss
from api.crypto import encrypt
from api.models import GarminActivity, GarminHealthDaily, GarminSleepSession

from .conftest import auth_headers, login

READ_SCOPE = "ACTIVITY:READ,CALENDAR:WRITE,SETTINGS:READ,WELLNESS:READ"

ACT = {"id": "i9001", "start_date_local": "2026-11-01T07:30:00", "type": "Run", "name": "Rodaje",
       "moving_time": 3000, "distance": 10000.0, "average_heartrate": 150.4,
       "calories": 600, "total_elevation_gain": 45.0, "average_speed": 3.33,
       "icu_training_load": 55.2, "source": "OAUTH_CLIENT", "weather_temp": 21}
WELL = {"id": "2026-11-01", "restingHR": 48, "hrv": 62.5, "steps": 9000, "sleepSecs": 27000,
        "sleepScore": 82, "ctl": 40, "atl": 50}


def _connect(db, user, scope=READ_SCOPE):
    user.intervals_access_token = encrypt("tok-secret")
    user.intervals_scope = scope
    db.commit()


def _patch(monkeypatch, acts=None, well=None):
    fa, fw = AsyncMock(return_value=acts or []), AsyncMock(return_value=well or [])
    monkeypatch.setattr(ic, "fetch_activities", fa)
    monkeypatch.setattr(ic, "fetch_wellness", fw)
    return fa, fw


def _run(db, user, **kw):
    return asyncio.run(iss.sync_intervals_user(db, user.id, **kw))


def test_sync_imports_activities_and_is_idempotent(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    _patch(monkeypatch, acts=[ACT])
    r = _run(db, athlete_user)
    assert r["imported"] == 1 and r["merged"] == 0 and r["errors"] == 0
    a = db.query(GarminActivity).one()
    assert a.activity_id == "intervals:i9001" and a.sport == "run" and a.date_iso == "2026-11-01"
    assert a.dur_min == 50 and a.dist_km == 10.0 and a.avg_hr == 150 and a.pace_str == "5:00"
    assert a.tss == 55.2
    r2 = _run(db, athlete_user)
    assert r2["imported"] == 0 and r2["updated"] == 1
    assert db.query(GarminActivity).count() == 1


def test_matching_garmin_row_is_merged_not_duplicated(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    db.add(GarminActivity(user_id=athlete_user.id, activity_id="7700001", sport="run",
                          date_iso="2026-11-01", dur_min=49, name="Garmin run"))
    db.commit()
    _patch(monkeypatch, acts=[ACT])
    r = _run(db, athlete_user)
    assert r["merged"] == 1 and r["imported"] == 0
    rows = db.query(GarminActivity).all()
    assert len(rows) == 1 and rows[0].activity_id == "7700001" and rows[0].name == "Garmin run"


def test_wellness_never_overwrites_non_empty_with_empty(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso="2026-11-01", resting_hr=50, steps=None))
    db.add(GarminSleepSession(user_id=athlete_user.id, date_iso="2026-11-01", total_min=400))
    db.commit()
    # resting_hr vacio en el payload no debe borrar el 50; steps lo completa; sueno existente no se pisa
    well = dict(WELL, restingHR=None, sleepSecs=27000)
    _patch(monkeypatch, well=[well])
    r = _run(db, athlete_user)
    assert r["wellness_days"] == 1
    hd = db.query(GarminHealthDaily).one()
    assert hd.resting_hr == 50 and hd.steps == 9000
    sl = db.query(GarminSleepSession).one()
    assert sl.total_min == 400 and sl.sleep_score == 82  # hueco completado, valor previo intacto
    # un valor distinto de intervals tampoco pisa uno existente
    _patch(monkeypatch, well=[dict(WELL, restingHR=99, steps=1)])
    _run(db, athlete_user)
    hd = db.query(GarminHealthDaily).one()
    assert hd.resting_hr == 50 and hd.steps == 9000


def test_wellness_creates_rows_and_is_idempotent(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    _patch(monkeypatch, well=[WELL])
    _run(db, athlete_user)
    _run(db, athlete_user)
    hd = db.query(GarminHealthDaily).one()
    assert hd.resting_hr == 48 and hd.hrv_last_night == 62.5 and hd.steps == 9000
    assert db.query(GarminSleepSession).one().total_min == 450


def test_no_activity_scope_needs_reconnect_and_makes_no_api_calls(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, scope="CALENDAR:WRITE,SETTINGS:READ")
    fa, fw = _patch(monkeypatch, acts=[ACT])
    assert _run(db, athlete_user) == {"status": "needs_reconnect"}
    fa.assert_not_called()
    fw.assert_not_called()
    # conexion previa a la columna (scope NULL) tambien exige reconectar
    _connect(db, athlete_user, scope=None)
    assert _run(db, athlete_user) == {"status": "needs_reconnect"}
    assert ic.needs_reconnect(athlete_user) is True


def test_save_tokens_stores_granted_or_requested_scope(db, athlete_user):
    ic.save_tokens(athlete_user, "t", "1", db, scope="ACTIVITY:READ,CALENDAR:WRITE")
    assert athlete_user.intervals_scope == "ACTIVITY:READ,CALENDAR:WRITE"
    ic.save_tokens(athlete_user, "t", "1", db)
    assert athlete_user.intervals_scope == ic.SCOPE
    ic.clear_tokens(athlete_user, db)
    assert athlete_user.intervals_scope is None


def test_fetch_retries_once_on_429_with_retry_after(monkeypatch):
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json=[{"id": "x"}])

    real = httpx.AsyncClient
    monkeypatch.setattr(ic.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    async def fake_sleep(s):
        sleeps.append(s)
    monkeypatch.setattr(ic.asyncio, "sleep", fake_sleep)
    out = asyncio.run(ic.fetch_activities("tok", "2026-10-01", "2026-11-01"))
    assert out == [{"id": "x"}] and len(calls) == 2 and sleeps == [2.0]
    assert calls[0].url.params["oldest"] == "2026-10-01"


def test_fetch_second_429_raises_controlled_error(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(ic.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "0"})), **kw))
    with pytest.raises(ic.IntervalsError) as e:
        asyncio.run(ic.fetch_wellness("tok-secret", "2026-10-01", "2026-11-01"))
    assert "tok-secret" not in str(e.value)


# ── Rutas / flag ────────────────────────────────────────────────────────────

def _headers(client, user):
    h = auth_headers(login(client, user.email, "AthlPass123"))
    client.cookies.clear()
    return h


def test_sync_route_404_when_flag_off(client, db, athlete_user, monkeypatch):
    monkeypatch.delenv("INTERVALS_READ_ENABLED", raising=False)
    _connect(db, athlete_user)
    r = client.post("/api/integrations/intervals/sync", headers=_headers(client, athlete_user))
    assert r.status_code == 404


def test_sync_route_works_when_flag_on_and_validates_days(client, db, athlete_user, monkeypatch):
    monkeypatch.setenv("INTERVALS_READ_ENABLED", "true")
    _connect(db, athlete_user)
    _patch(monkeypatch, acts=[ACT])
    h = _headers(client, athlete_user)
    r = client.post("/api/integrations/intervals/sync?days=30", headers=h)
    assert r.status_code == 200 and r.json()["imported"] == 1
    assert client.post("/api/integrations/intervals/sync?days=400", headers=h).status_code in (400, 422)


def test_status_exposes_scopes_flag_and_needs_reconnect(client, db, athlete_user, monkeypatch):
    monkeypatch.setenv("INTERVALS_READ_ENABLED", "1")
    _connect(db, athlete_user, scope="CALENDAR:WRITE")
    h = _headers(client, athlete_user)
    s = client.get("/api/integrations/intervals/status", headers=h).json()
    assert s["connected"] is True and s["scopes"] == "CALENDAR:WRITE"
    assert s["read_enabled"] is True and s["needs_reconnect"] is True
    assert {"available", "athlete_id"} <= set(s)
    _connect(db, athlete_user)
    monkeypatch.delenv("INTERVALS_READ_ENABLED")
    s = client.get("/api/integrations/intervals/status", headers=h).json()
    assert s["read_enabled"] is False and s["needs_reconnect"] is False


def test_authorize_url_requests_read_scopes():
    url = ic.build_authorize_url("st")
    assert "ACTIVITY%3AREAD" in url and "WELLNESS%3AREAD" in url and "CALENDAR%3AWRITE" in url
