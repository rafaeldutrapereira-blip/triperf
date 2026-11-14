"""PUSH-INTERVALS (BUILD 378): el entreno asignado por el coach se escribe en el
intervals.icu del atleta (send_workout_event), sin auto-entrega directa a Garmin."""
import json
from unittest.mock import AsyncMock

import pytest

from .conftest import login, auth_headers, TestingSessionLocal
from api import coach_intervals_push as cip
from api import intervals_connector as ic
from api.models import AssignedWorkout, Group, GroupMember, WorkoutTemplate
from .test_coach_destino_multiple import _mk_athletes

BIKE = [{"type": "steady", "duration": 600, "power": 0.75}]
RUN = [{"type": "steady", "duration": 600, "mode": "pace", "val": 270}]
SWIM = [{"type": "main", "reps": 4, "dist": 100, "rest": 20, "stroke": "full"}]


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _tpl(db, coach, sport, blocks=None, notas=None):
    t = WorkoutTemplate(coach_id=coach.id, sport=sport, nombre=f"T-{sport}", dur_min=45, tss=50,
                        notas=notas, blocks_json=json.dumps(blocks) if blocks else None)
    db.add(t); db.commit(); db.refresh(t)
    return t


def _connect(db, users):
    for u in users:
        u.intervals_access_token = "tok-" + u.id[:6]
    db.commit()


@pytest.fixture
def sync_push(monkeypatch):
    """El push corre en hilo: lo hacemos sincrono y con la BD de pruebas; y
    mockeamos send_workout_event (nunca sale a la red)."""
    from api.routes import coach_routes
    import api.database as database
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(coach_routes, "_start_intervals_push",
                        lambda ids: cip.push_assignments_background(list(ids)))
    users = []

    async def _fake(**kw):
        users.append(kw["user"].id)  # la sesion se cierra tras el push: guardar el id ahora
        return {"ok": True, "event_id": 777}

    mock = AsyncMock(side_effect=_fake)
    mock.users = users
    monkeypatch.setattr(ic, "send_workout_event", mock)
    # si alguien llamara a la auto-entrega directa a Garmin, el test falla
    import api.workout_delivery as wd
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("deliver_bike_workout no debe correr"))
    monkeypatch.setattr(wd, "deliver_bike_workout", boom)
    return mock


def _row(db, athlete_id):
    db.expire_all()
    return db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == athlete_id).all()


def test_asignar_individual_escribe_evento_en_intervals(client, db, coach_user, sync_push):
    ath = _mk_athletes(db, coach_user, 1)[0]
    _connect(db, [ath])
    tpl = _tpl(db, coach_user, "bike", BIKE)
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": ath.id, "date_iso": "2026-11-20", "notas": "ojo"})
    assert r.status_code == 201
    assert sync_push.await_count == 1
    kw = sync_push.await_args.kwargs
    assert kw["sport"] == "bike" and kw["blocks"] == BIKE
    assert kw["date_iso"] == "2026-11-20" and sync_push.users == [ath.id]
    assert kw["name"] == "T-bike"
    row = _row(db, ath.id)[0]
    assert row.intervals_push_status == "ok" and row.intervals_push_event_id == "777"
    assert row.intervals_push_at is not None and row.intervals_push_error is None


def test_asignar_en_lote_un_evento_por_miembro(client, db, coach_user, sync_push):
    ath = _mk_athletes(db, coach_user, 3)
    _connect(db, ath)
    tpl = _tpl(db, coach_user, "run", RUN)
    g = Group(coach_id=coach_user.id, nombre="G")
    db.add(g); db.flush()
    for a in ath:
        db.add(GroupMember(group_id=g.id, athlete_id=a.id))
    db.commit()
    h = _h(client)
    # grupo via /assign
    r = client.post("/api/coach/assign", headers=h, json={
        "template_id": tpl.id, "group_id": g.id, "date_iso": "2026-11-21"})
    assert r.status_code == 201
    assert sync_push.await_count == 3
    assert set(sync_push.users) == {a.id for a in ath}
    # /assign/batch con otra fecha: un evento por atleta
    sync_push.reset_mock()
    r = client.post("/api/coach/assign/batch", headers=h, json={"assignments": [
        {"template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-22"} for a in ath]})
    assert r.status_code == 201 and r.json()["created"] == 3
    assert sync_push.await_count == 3
    assert all(c.kwargs["date_iso"] == "2026-11-22" for c in sync_push.await_args_list)
    assert all(x.intervals_push_status == "ok" for a in ath for x in _row(db, a.id))


def test_batch_con_grupo_un_evento_por_miembro(client, db, coach_user, sync_push):
    ath = _mk_athletes(db, coach_user, 2)
    _connect(db, ath)
    tpl = _tpl(db, coach_user, "swim", SWIM)
    g = Group(coach_id=coach_user.id, nombre="G2")
    db.add(g); db.flush()
    for a in ath:
        db.add(GroupMember(group_id=g.id, athlete_id=a.id))
    db.commit()
    r = client.post("/api/coach/assign/batch", headers=_h(client), json={"assignments": [
        {"template_id": tpl.id, "group_id": g.id, "date_iso": "2026-11-23"}]})
    assert r.status_code == 201 and r.json()["created"] == 2
    assert sync_push.await_count == 2


def test_atleta_sin_intervals_asignacion_creada_y_estado_pendiente(client, db, coach_user, sync_push):
    ath = _mk_athletes(db, coach_user, 1)[0]          # sin token de intervals
    tpl = _tpl(db, coach_user, "bike", BIKE)
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": ath.id, "date_iso": "2026-11-24"})
    assert r.status_code == 201
    assert sync_push.await_count == 0
    row = _row(db, ath.id)[0]
    assert row.intervals_push_status == "pending" and "intervals" in row.intervals_push_error
    assert row.intervals_push_at is not None


def test_error_de_intervals_no_rompe_la_asignacion(client, db, coach_user, sync_push):
    ath = _mk_athletes(db, coach_user, 1)[0]
    _connect(db, [ath])
    sync_push.side_effect = ic.IntervalsError("intervals.icu rechazo el workout (500)")
    tpl = _tpl(db, coach_user, "run", RUN)
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": ath.id, "date_iso": "2026-11-25"})
    assert r.status_code == 201
    row = _row(db, ath.id)[0]
    assert row.intervals_push_status == "failed" and "500" in row.intervals_push_error


@pytest.mark.parametrize("sport,blocks,tipo", [("swim", SWIM, "swim"), ("str", None, "str")])
def test_natacion_y_fuerza_se_entregan(client, db, coach_user, sync_push, sport, blocks, tipo):
    ath = _mk_athletes(db, coach_user, 1)[0]
    _connect(db, [ath])
    tpl = _tpl(db, coach_user, sport, blocks, notas="3x10 sentadilla" if sport == "str" else None)
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": ath.id, "date_iso": "2026-11-26"})
    assert r.status_code == 201
    assert sync_push.await_count == 1
    kw = sync_push.await_args.kwargs
    assert kw["sport"] == tipo
    if sport == "str":
        assert kw["blocks"] == [] and "sentadilla" in kw["description"]
    else:
        assert kw["blocks"] == SWIM
    assert _row(db, ath.id)[0].intervals_push_status == "ok"


def test_tipo_intervals_por_deporte():
    """send_workout_event mapea str -> WeightTraining (swim/run/bike como antes)."""
    import asyncio
    import httpx
    sent = {}

    class _Resp:
        status_code = 200
        content = b"{}"
        def json(self): return {"id": 1}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, content=None):
            sent.update(json.loads(content)); return _Resp()

    class _U:
        intervals_access_token = "tok"

    orig = httpx.AsyncClient
    httpx.AsyncClient = _Client
    try:
        asyncio.run(ic.send_workout_event(_U(), "x", "str", [], "2026-11-26", "desc"))
    finally:
        httpx.AsyncClient = orig
    assert sent["type"] == "WeightTraining"


def test_correr_un_solo_evento_y_sin_auto_garmin(client, db, coach_user, sync_push):
    """Doble push resuelto: asignar correr = exactamente 1 evento intervals y 0
    entregas directas a Garmin (el stub de deliver_bike_workout hace fallar el test)."""
    ath = _mk_athletes(db, coach_user, 1)[0]
    _connect(db, [ath])
    tpl = _tpl(db, coach_user, "run", RUN)
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": ath.id, "date_iso": "2026-11-27"})
    assert r.status_code == 201
    assert sync_push.await_count == 1
    row = _row(db, ath.id)[0]
    assert row.garmin_push_status is None            # no hubo camino Garmin directo


def test_sport_sin_estructura_queda_skipped(client, db, coach_user, sync_push):
    ath = _mk_athletes(db, coach_user, 1)[0]
    _connect(db, [ath])
    tpl = _tpl(db, coach_user, "bike", None)         # bici sin bloques
    client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": ath.id, "date_iso": "2026-11-28"})
    assert sync_push.await_count == 0
    assert _row(db, ath.id)[0].intervals_push_status == "skipped"


def test_endpoints_manuales_sync_garmin_siguen_existiendo(client, db, coach_user):
    """Regresion: los respaldos manuales existen y responden (404 de negocio,
    no 404/405 de ruta inexistente: el cuerpo trae el envelope del backend)."""
    from api.routes.coach_routes import router
    paths = {getattr(r, "path", "") for r in router.routes}
    assert any(x.endswith("/coach/assign/{assignment_id}/sync-garmin") for x in paths)
    assert any(x.endswith("/coach/groups/{group_id}/sync-garmin") for x in paths)
    h = _h(client)
    r = client.post("/api/coach/assign/no-existe/sync-garmin", headers=h, json={})
    assert r.status_code == 404
    r = client.post("/api/coach/groups/no-existe/sync-garmin?start=2026-11-01&end=2026-11-30", headers=h, json={})
    assert r.status_code == 404
