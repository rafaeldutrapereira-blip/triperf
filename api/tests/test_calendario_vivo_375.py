"""CALENDARIO-VIVO (375): Mi Plan muestra los workouts planificados leidos de intervals.icu."""
import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock

from api import intervals_connector as ic
from api import intervals_sync_service as iss
from api.crypto import encrypt
from api.models import (AssignedWorkout, GarminPlannedWorkout, OwnPlanSession,
                        WorkoutTemplate)

from .conftest import auth_headers, login

SCOPE = "ACTIVITY:READ,CALENDAR:WRITE,SETTINGS:READ,WELLNESS:READ"
DAY = date.today().isoformat()


def _ev(i, typ, name, secs, day=DAY, **kw):
    # Forma real de GET /athlete/0/events (category WORKOUT)
    e = {"id": i, "start_date_local": f"{day}T00:00:00", "category": "WORKOUT", "type": typ,
         "name": name, "description": None, "moving_time": secs, "distance": None,
         "icu_training_load": None, "athlete_id": "i1234", "uid": "x%s" % i}
    e.update(kw)
    return e


EVENTS = [
    _ev(5001, "Ride", "intervalos UL extensivos", 83 * 60),
    _ev(5002, "Run", "easy z2", 30 * 60),
    _ev(5003, "Swim", "Natación", 60 * 60, distance=2000.0),
]


def _setup(db, user, monkeypatch, events, scope=SCOPE):
    user.intervals_access_token = encrypt("tok")
    user.intervals_scope = scope
    db.commit()
    fe = AsyncMock(return_value=events)
    monkeypatch.setattr(ic, "fetch_events", fe)
    monkeypatch.setattr(ic, "fetch_activities", AsyncMock(return_value=[]))
    monkeypatch.setattr(ic, "fetch_wellness", AsyncMock(return_value=[]))
    return fe


def _sync(db, user):
    return asyncio.run(iss.sync_intervals_user(db, user.id))


def _plan(client):
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(f"/api/athlete/planned-workouts?start={DAY}&end={DAY}", headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _rows(db, uid):
    return db.query(GarminPlannedWorkout).filter_by(user_id=uid, source="intervals").all()


def test_a_tres_workouts_aterrizan_y_aparecen_en_el_plan(client, db, athlete_user, monkeypatch):
    _setup(db, athlete_user, monkeypatch, EVENTS)
    res = _sync(db, athlete_user)
    assert res["planned_status"] == "ok" and res["planned_upserted"] == 3
    rows = {r.garmin_scheduled_id: r for r in _rows(db, athlete_user.id)}
    assert set(rows) == {"intervals:5001", "intervals:5002", "intervals:5003"}
    assert (rows["intervals:5001"].sport, rows["intervals:5001"].dur_min) == ("bike", 83.0)
    assert (rows["intervals:5002"].sport, rows["intervals:5002"].dur_min) == ("run", 30.0)
    assert (rows["intervals:5003"].sport, rows["intervals:5003"].dist_km) == ("swim", 2.0)
    assert all(r.tss_planned is None for r in rows.values())  # sin inventar TSS
    got = {p["title"]: p for p in _plan(client)}
    assert set(got) == {"intervalos UL extensivos", "easy z2", "Natación"}
    assert got["easy z2"]["source"] == "intervals"


def test_b_resync_no_duplica_y_refleja_cambios(client, db, athlete_user, monkeypatch):
    _setup(db, athlete_user, monkeypatch, EVENTS)
    _sync(db, athlete_user)
    _sync(db, athlete_user)
    assert len(_rows(db, athlete_user.id)) == 3
    changed = [dict(EVENTS[0], moving_time=90 * 60, start_date_local=f"{DAY}T18:00:00"), EVENTS[1], EVENTS[2]]
    ic.fetch_events.return_value = changed
    _sync(db, athlete_user)
    rows = _rows(db, athlete_user.id)
    assert len(rows) == 3
    assert [r.dur_min for r in rows if r.garmin_scheduled_id == "intervals:5001"] == [90.0]


def test_c_evento_borrado_en_origen_desaparece(client, db, athlete_user, monkeypatch):
    _setup(db, athlete_user, monkeypatch, EVENTS)
    _sync(db, athlete_user)
    ic.fetch_events.return_value = EVENTS[:2]
    res = _sync(db, athlete_user)
    assert res["planned_removed"] == 1
    assert {p["title"] for p in _plan(client)} == {"intervalos UL extensivos", "easy z2"}


def test_c2_pasado_se_conserva_y_fallo_no_borra(client, db, athlete_user, monkeypatch):
    past = (date.today() - timedelta(days=3)).isoformat()
    _setup(db, athlete_user, monkeypatch, [_ev(6001, "Run", "ayer", 1800, day=past)] + EVENTS)
    _sync(db, athlete_user)
    ic.fetch_events.return_value = []
    _sync(db, athlete_user)
    ids = {r.garmin_scheduled_id for r in _rows(db, athlete_user.id)}
    assert ids == {"intervals:6001"}  # el pasado queda; el futuro/hoy se espejo
    # fallo de la API: no borra nada y el sync de actividades no se rompe
    ic.fetch_events.side_effect = ic.IntervalsError("boom")
    _sync(db, athlete_user)
    assert {r.garmin_scheduled_id for r in _rows(db, athlete_user.id)} == {"intervals:6001"}


def test_d_sesion_propia_mismo_deporte_dia_no_se_duplica(client, db, athlete_user, monkeypatch):
    db.add(OwnPlanSession(user_id=athlete_user.id, date_iso=DAY, sport="bike",
                          name="Rodillo", dur_min=80))  # 83 vs 80: dentro de 25%
    db.add(OwnPlanSession(user_id=athlete_user.id, date_iso=DAY, sport="run",
                          name="Fondo largo", dur_min=90))  # 30 vs 90: NO calza
    db.commit()
    _setup(db, athlete_user, monkeypatch, EVENTS)
    _sync(db, athlete_user)
    titles = {p["title"] for p in _plan(client)}
    assert titles == {"easy z2", "Natación"}
    assert len(_rows(db, athlete_user.id)) == 3  # solo vista: nada se borra


def test_d2_sesion_asignada_tambien_gana(client, db, athlete_user, coach_user, monkeypatch):
    t = WorkoutTemplate(coach_id=coach_user.id, sport="swim", nombre="Técnica", dur_min=55)
    db.add(t)
    db.flush()
    db.add(AssignedWorkout(template_id=t.id, athlete_id=athlete_user.id, date_iso=DAY))
    db.commit()
    _setup(db, athlete_user, monkeypatch, EVENTS)
    _sync(db, athlete_user)
    assert "Natación" not in {p["title"] for p in _plan(client)}
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(f"/api/athlete/plan?start={DAY}&end={DAY}&include_garmin=1", headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    names = {x["template"]["nombre"] for x in r.json()}
    assert "Natación" not in names and "intervalos UL extensivos" in names


def test_e_sin_intervals_el_plan_queda_igual(client, db, athlete_user, monkeypatch):
    fe = AsyncMock(return_value=EVENTS)
    monkeypatch.setattr(ic, "fetch_events", fe)
    res = asyncio.run(iss.sync_intervals_user(db, athlete_user.id))
    assert res["status"] == "not_connected"
    fe.assert_not_called()
    assert _plan(client) == [] and _rows(db, athlete_user.id) == []


def test_f_sin_scope_de_calendario_no_llama(db, athlete_user, monkeypatch):
    fe = _setup(db, athlete_user, monkeypatch, EVENTS, scope="ACTIVITY:READ,WELLNESS:READ")
    res = _sync(db, athlete_user)
    assert res["planned_status"] == "sin_scope"
    fe.assert_not_called()


def test_g_mapeo_de_tipos():
    m = iss._plan_sport
    assert [m(x) for x in ("Ride", "VirtualRide", "Run", "VirtualRun", "Swim", "WeightTraining",
                           "Yoga", None)] == ["bike", "bike", "run", "run", "swim", "strength",
                                              "other", "other"]
