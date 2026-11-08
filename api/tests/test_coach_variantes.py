"""COACH-VARIANTES (BUILD 363): factor de volumen por destino al asignar."""
import json
import sys
import types

import pytest

from .conftest import login, auth_headers
from api.volume_factor import scale_blocks_json, scale_minutes, scale_km
from api.models import (
    AssignedWorkout, WorkoutTemplate, WeekTemplate, WeekTemplateDay,
    Macrocycle, MacrocycleWeek,
)
from .test_coach_destino_multiple import _mk_athletes

BLOCKS = [
    {"type": "warmup", "duration": 600, "power_low": 0.5, "power_high": 0.75},
    {"type": "intervals", "repeat": 5, "on_duration": 240, "off_duration": 120,
     "on_power": 0.95, "off_power": 0.55},
    {"type": "cooldown", "duration": 300, "power_low": 0.4, "power_high": 0.6},
]


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


@pytest.fixture
def tpl(db, coach_user):
    t = WorkoutTemplate(coach_id=coach_user.id, sport="bike", nombre="Umbral", dur_min=50,
                        dist_km=12.3, tss=60, blocks_json=json.dumps(BLOCKS))
    db.add(t); db.commit(); db.refresh(t)
    return t


def _rows(db, aid):
    db.expire_all()
    return db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == aid).all()


# ── reglas puras ─────────────────────────────────────────────
def test_redondeo_reglas():
    assert scale_minutes(45, 0.8) == 36
    assert scale_minutes(50, 1.25) == 63          # 62.5 -> half-up
    assert scale_km(10, 0.8) == 8.0
    assert scale_km(12.3, 1.25) == 15.4           # 15.375 -> 15.4
    assert scale_minutes(None, 0.8) is None and scale_km(None, 0.8) is None


def test_bloques_08_solo_duracion():
    out = json.loads(scale_blocks_json(json.dumps(BLOCKS), 0.8))
    assert out[0]["duration"] == 480 and out[2]["duration"] == 240
    assert out[1]["on_duration"] == 192 and out[1]["off_duration"] == 96
    assert out[1]["repeat"] == 5                       # conteo intacto
    assert out[0]["power_low"] == 0.5 and out[1]["on_power"] == 0.95   # % intactos


def test_bloques_125_y_anidados():
    nested = [{"type": "group", "repeat": 2, "blocks": [{"type": "steady", "duration": 90, "power": 0.8}]},
              {"type": "steady", "dist_m": 400, "val": 0.9}]
    out = json.loads(scale_blocks_json(json.dumps(nested), 1.25))
    assert out[0]["blocks"][0]["duration"] == 113      # 112.5 -> 113
    assert out[1]["dist_m"] == 500 and out[1]["val"] == 0.9


# ── asignación individual / batch ────────────────────────────
def test_assign_factor_08_guarda_y_escala(client, db, coach_user, tpl):
    a, = _mk_athletes(db, coach_user, 1)
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10", "volume_factor": 0.8})
    assert r.status_code == 201
    body = r.json()
    assert body["volume_factor"] == 0.8
    assert body["template"]["dur_min"] == 40 and body["template"]["dist_km"] == 9.8
    row, = _rows(db, a.id)
    assert (row.volume_factor, row.dur_min_scaled, row.dist_km_scaled) == (0.8, 40, 9.8)
    assert json.loads(row.blocks_json_scaled)[0]["duration"] == 480
    db.refresh(tpl)
    assert tpl.dur_min == 50                          # la plantilla no se toca


def test_assign_factor_125(client, db, coach_user, tpl):
    a, = _mk_athletes(db, coach_user, 1)
    client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10", "volume_factor": 1.25})
    row, = _rows(db, a.id)
    assert row.dur_min_scaled == 63 and row.dist_km_scaled == 15.4
    assert json.loads(row.blocks_json_scaled)[1]["on_duration"] == 300


@pytest.mark.parametrize("bad", [0.49, 1.51, 0, -1, 5])
def test_factor_fuera_de_rango_rechazado(client, db, coach_user, tpl, bad):
    a, = _mk_athletes(db, coach_user, 1)
    h = _h(client)
    r = client.post("/api/coach/assign", headers=h, json={
        "template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10", "volume_factor": bad})
    assert r.status_code in (400, 422)
    r = client.post("/api/coach/assign/batch", headers=h, json={"assignments": [
        {"template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10", "volume_factor": bad}]})
    assert r.status_code in (400, 422)
    assert _rows(db, a.id) == []


def test_regresion_factor_1_identico_a_sin_factor(client, db, coach_user, tpl):
    a1, a2, a3 = _mk_athletes(db, coach_user, 3)
    h = _h(client)
    for aid, extra in ((a1.id, {}), (a2.id, {"volume_factor": 1.0}), (a3.id, {"volume_factor": None})):
        assert client.post("/api/coach/assign", headers=h, json={
            "template_id": tpl.id, "athlete_id": aid, "date_iso": "2026-11-10", **extra}).status_code == 201
    for aid in (a1.id, a2.id, a3.id):
        row, = _rows(db, aid)
        assert (row.volume_factor, row.dur_min_scaled, row.dist_km_scaled, row.blocks_json_scaled) == \
               (None, None, None, None)
    r = client.get(f"/api/coach/assignments/athlete/{a2.id}", headers=h).json()
    assert r[0]["template"]["dur_min"] == 50 and r[0]["template"]["blocks_json"] == tpl.blocks_json


def test_batch_factor_por_destino(client, db, coach_user, tpl):
    a, b = _mk_athletes(db, coach_user, 2)
    r = client.post("/api/coach/assign/batch", headers=_h(client), json={"assignments": [
        {"template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10", "volume_factor": 0.8},
        {"template_id": tpl.id, "athlete_id": b.id, "date_iso": "2026-11-10"}]})
    assert r.json()["created"] == 2
    assert _rows(db, a.id)[0].dur_min_scaled == 40
    assert _rows(db, b.id)[0].volume_factor is None


def test_ver_plan_coach_y_atleta_ven_valores_escalados(client, db, coach_user, tpl):
    a, = _mk_athletes(db, coach_user, 1)
    h = _h(client)
    client.post("/api/coach/assign", headers=h, json={
        "template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10", "volume_factor": 0.8})
    lst = client.get(f"/api/coach/assignments/athlete/{a.id}", headers=h).json()
    assert lst[0]["volume_factor"] == 0.8 and lst[0]["template"]["dur_min"] == 40
    ah = auth_headers(login(client, "m0@test.com", "Passw0rd123"))
    plan = client.get("/api/athlete/plan?start=2026-11-01&end=2026-11-30", headers=ah)
    assert plan.status_code == 200, plan.text
    assert plan.json()[0]["template"]["dur_min"] == 40


# ── semana tipo / macrociclo ─────────────────────────────────
def _week(db, coach, tpl):
    wt = WeekTemplate(coach_id=coach.id, nombre="W")
    db.add(wt); db.flush()
    db.add(WeekTemplateDay(week_template_id=wt.id, day_of_week=0, workout_template_id=tpl.id))
    db.commit(); db.refresh(wt)
    return wt


def test_semana_tipo_factor_por_atleta(client, db, coach_user, tpl):
    a, b = _mk_athletes(db, coach_user, 2)
    wt = _week(db, coach_user, tpl)
    r = client.post(f"/api/coach/week-templates/{wt.id}/apply", headers=_h(client), json={
        "start_date": "2026-11-09", "athlete_ids": [a.id, b.id],
        "volume_factor": 0.8, "volume_factors": {b.id: 1.2}})
    assert r.status_code == 200, r.text
    assert _rows(db, a.id)[0].dur_min_scaled == 40
    assert _rows(db, b.id)[0].dur_min_scaled == 60 and _rows(db, b.id)[0].volume_factor == 1.2


def test_semana_tipo_rechaza_fuera_de_rango_y_default(client, db, coach_user, tpl):
    a, = _mk_athletes(db, coach_user, 1)
    wt = _week(db, coach_user, tpl)
    h = _h(client)
    assert client.post(f"/api/coach/week-templates/{wt.id}/apply", headers=h, json={
        "start_date": "2026-11-09", "athlete_id": a.id, "volume_factor": 2}).status_code in (400, 422)
    assert client.post(f"/api/coach/week-templates/{wt.id}/apply", headers=h, json={
        "start_date": "2026-11-09", "athlete_id": a.id}).status_code == 200
    assert _rows(db, a.id)[0].volume_factor is None


def test_macrociclo_factor(client, db, coach_user, tpl):
    a, = _mk_athletes(db, coach_user, 1)
    wt = _week(db, coach_user, tpl)
    mc = Macrocycle(coach_id=coach_user.id, nombre="M")
    db.add(mc); db.flush()
    db.add(MacrocycleWeek(macrocycle_id=mc.id, position=1, week_template_id=wt.id))
    db.commit()
    r = client.post(f"/api/coach/macrocycles/{mc.id}/apply", headers=_h(client), json={
        "start_date": "2026-11-09", "athlete_ids": [a.id], "volume_factor": 1.25})
    assert r.status_code == 200, r.text
    assert _rows(db, a.id)[0].dist_km_scaled == 15.4


# ── entrega ──────────────────────────────────────────────────
def _fake_garmin(monkeypatch):
    from api import workout_delivery
    captured = {}
    fake = types.ModuleType("garmin_connector")
    fake.schedule_workout_for_athlete = lambda **kw: captured.update(kw) or {"workoutId": "1"}
    monkeypatch.setitem(sys.modules, "garmin_connector", fake)
    monkeypatch.setattr(workout_delivery, "decrypt_credential", lambda v: "pw")
    monkeypatch.setattr(workout_delivery, "_persist_push_status", lambda *a, **k: None)
    return workout_delivery, captured


def test_entrega_garmin_usa_valores_escalados(db, coach_user, tpl, monkeypatch):
    from api.volume_factor import apply_volume_factor
    wd, captured = _fake_garmin(monkeypatch)
    a, = _mk_athletes(db, coach_user, 1)
    a.garmin_email, a.garmin_password, a.ftp = "g@x.com", "enc", 250
    db.commit()
    row = AssignedWorkout(template_id=tpl.id, athlete_id=a.id, date_iso="2026-11-10")
    apply_volume_factor(row, tpl, 0.8)
    db.add(row); db.commit()
    res = wd.deliver_bike_workout(row, a, tpl)
    assert res["garmin_ok"] is True
    s = captured["session"]
    assert s["dur_min"] == 40 and s["dist_km"] == 9.8 and s["ftp"] == 250
    assert json.loads(s["blocks_json"])[0]["duration"] == 480


def test_entrega_sin_factor_usa_plantilla(db, coach_user, tpl, monkeypatch):
    wd, captured = _fake_garmin(monkeypatch)
    a, = _mk_athletes(db, coach_user, 1)
    a.garmin_email, a.garmin_password = "g@x.com", "enc"
    row = AssignedWorkout(template_id=tpl.id, athlete_id=a.id, date_iso="2026-11-10")
    db.add(row); db.commit()
    wd.deliver_bike_workout(row, a, tpl)
    assert captured["session"]["dur_min"] == 50
    assert captured["session"]["blocks_json"] == tpl.blocks_json
