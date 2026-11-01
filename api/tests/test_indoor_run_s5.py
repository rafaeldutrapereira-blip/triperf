"""
S5 -- Indoor multideporte v1 (ciclismo + running): persistencia de la disciplina,
validación de bloques de running, envío a Garmin por disciplina y traducción
de bloques de running (ritmo / FC) a workoutSteps de Garmin.
"""
import json

from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import User
from garmin_connector import _build_workout_body, _indoor_run_blocks_to_garmin_steps

BASE = "/api/athlete/indoor-workouts"
RUN_PACE = [
    {"id": "b1", "type": "warmup", "mode": "pace", "duration": 600, "val_low": 390, "val_high": 345},
    {"id": "b2", "type": "intervals", "mode": "pace", "repeat": 5, "on_duration": 240,
     "on_val": 260, "off_duration": 120, "off_val": 380},
    {"id": "b3", "type": "cooldown", "mode": "pace", "duration": 300, "val_low": 345, "val_high": 390},
]
RUN_HR = [
    {"id": "b1", "type": "steady", "mode": "hr", "duration": 1200, "val": 0.75},
    {"id": "b2", "type": "intervals", "mode": "hr", "repeat": 3, "on_duration": 180,
     "on_val": 0.9, "off_duration": 90, "off_val": 0.65},
]
BIKE = [{"type": "steady", "duration": 600, "power": 0.75}]
SEND = "/api/athlete/indoor-workout/send-to-garmin"


def _user(db, email, **extra):
    u = User(email=email, nombre=email, password_hash=hash_password("S5Pass-12345"),
             rol="athlete", plan_nivel="elite", activo=True, **extra)
    db.add(u)
    db.commit()
    return u


def _h(client, email):
    h = auth_headers(login(client, email, "S5Pass-12345"))
    client.cookies.clear()
    return h


def _garmin_user(client, db, email, **extra):
    _user(db, email)
    h = _h(client, email)
    u = db.query(User).filter(User.email == email).first()
    u.garmin_email, u.garmin_password = "g@x.com", "enc"
    for k, v in extra.items():
        setattr(u, k, v)
    db.commit()
    return h


def test_run_workout_roundtrip_keeps_sport_and_blocks(client, db):
    _user(db, "s5a@test.com")
    h = _h(client, "s5a@test.com")
    r = client.post(BASE, json={"name": "Series 5x4", "sport": "run", "blocks": RUN_PACE}, headers=h)
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["sport"] == "run" and w["blocks"] == RUN_PACE
    got = client.get(f"{BASE}/{w['id']}", headers=h).json()
    assert got["sport"] == "run" and got["blocks"] == RUN_PACE
    assert client.get(BASE, headers=h).json()["workouts"][0]["sport"] == "run"


def test_hr_run_workout_and_update_keeps_run(client, db):
    _user(db, "s5b@test.com")
    h = _h(client, "s5b@test.com")
    w = client.post(BASE, json={"name": "Z2", "sport": "run", "blocks": RUN_HR}, headers=h).json()
    assert w["blocks"] == RUN_HR
    r = client.put(f"{BASE}/{w['id']}", json={"name": "Z2 largo", "sport": "run", "blocks": RUN_HR[:1]}, headers=h)
    assert r.status_code == 200 and r.json()["sport"] == "run" and len(r.json()["blocks"]) == 1


def test_run_blocks_need_mode_and_swim_still_rejected(client, db):
    _user(db, "s5c@test.com")
    h = _h(client, "s5c@test.com")
    bad = [{"type": "steady", "duration": 600, "power": 0.75}]  # bloque de bici
    assert client.post(BASE, json={"name": "x", "sport": "run", "blocks": bad}, headers=h).status_code == 400
    bad2 = [dict(RUN_PACE[0], mode="watts")]
    assert client.post(BASE, json={"name": "x", "sport": "run", "blocks": bad2}, headers=h).status_code == 400
    assert client.post(BASE, json={"name": "x", "sport": "swim", "blocks": RUN_PACE}, headers=h).status_code == 400


def test_bike_workout_unchanged(client, db):
    _user(db, "s5d@test.com")
    h = _h(client, "s5d@test.com")
    w = client.post(BASE, json={"name": "FTP", "blocks": BIKE}, headers=h).json()
    assert w["sport"] == "bike" and w["blocks"] == BIKE


# ---------------- envío a Garmin por disciplina ----------------

def _patch_garmin(monkeypatch, captured):
    import garmin_connector
    monkeypatch.setattr(
        garmin_connector, "schedule_workout_for_athlete",
        lambda **kw: captured.update(kw) or {"workoutId": "123"},
    )
    import api.crypto
    monkeypatch.setattr(api.crypto, "decrypt_credential", lambda v: "pw")


def test_send_to_garmin_run_uses_run_sport(client, db, monkeypatch):
    h = _garmin_user(client, db, "s5e@test.com", fcmax=190)
    cap = {}
    _patch_garmin(monkeypatch, cap)
    r = client.post(SEND, headers=h,
                    json={"name": "Series", "date": "2026-11-10", "sport": "run", "blocks": RUN_PACE})
    assert r.status_code == 200, r.text
    s = cap["session"]
    assert s["sport"] == "run" and s["blocks_format"] == "indoor" and s["fcmax"] == 190
    assert cap["target_date"] == "2026-11-10"  # y sin FTP configurado: running no lo necesita


def test_send_to_garmin_bike_default_still_bike_and_needs_ftp(client, db, monkeypatch):
    h = _garmin_user(client, db, "s5f@test.com", ftp=250)
    cap = {}
    _patch_garmin(monkeypatch, cap)
    r = client.post(SEND, headers=h, json={"name": "FTP", "date": "2026-11-10", "blocks": BIKE})
    assert r.status_code == 200, r.text
    assert cap["session"]["sport"] == "bike" and cap["session"]["ftp"] == 250
    assert "blocks_format" not in cap["session"]

    h2 = _garmin_user(client, db, "s5g@test.com")
    r = client.post(SEND, headers=h2, json={"name": "FTP", "date": "2026-11-10", "blocks": BIKE})
    assert r.status_code == 400


def test_send_to_garmin_rejects_swim_and_hr_without_fcmax(client, db, monkeypatch):
    h = _garmin_user(client, db, "s5h@test.com")
    _patch_garmin(monkeypatch, {})
    r = client.post(SEND, headers=h, json={"name": "n", "date": "2026-11-10", "sport": "swim", "blocks": RUN_PACE})
    assert r.status_code == 400
    r = client.post(SEND, headers=h, json={"name": "n", "date": "2026-11-10", "sport": "run", "blocks": RUN_HR})
    assert r.status_code == 400


# ---------------- bloques de running -> Garmin ----------------

def _dump(steps):
    return [s.model_dump(exclude_none=True, mode="json") for s in steps]


def test_run_pace_blocks_to_garmin_pace_zone():
    d = _dump(_indoor_run_blocks_to_garmin_steps(RUN_PACE, None))
    warm = d[0]
    assert warm["stepType"]["stepTypeKey"] == "warmup" and warm["endConditionValue"] == 600
    assert warm["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert warm["targetValueOne"] == round(1000 / 390, 3)  # más lento = menos m/s
    assert warm["targetValueTwo"] == round(1000 / 345, 3)
    rep = d[1]
    assert rep["numberOfIterations"] == 5
    work, rec = rep["workoutSteps"]
    assert work["stepType"]["stepTypeKey"] == "interval" and work["endConditionValue"] == 240
    assert work["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert work["targetValueOne"] < work["targetValueTwo"]
    assert rec["stepType"]["stepTypeKey"] == "recovery"


def test_run_hr_blocks_to_garmin_hr_zone():
    d = _dump(_indoor_run_blocks_to_garmin_steps(RUN_HR, 200))
    steady = d[0]
    assert steady["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert steady["targetValueOne"] == 146 and steady["targetValueTwo"] == 154  # 75% ±2% de 200
    work = d[1]["workoutSteps"][0]
    assert work["targetValueOne"] == 176 and work["targetValueTwo"] == 184  # 90% ±2%


def test_build_workout_body_run_indoor_sport_and_other_paths_unchanged():
    session = {"name": "Series", "sport": "run", "dur_min": 30, "blocks_format": "indoor",
               "blocks_json": json.dumps(RUN_PACE), "fcmax": 190}
    body = _build_workout_body(session)
    assert body["sportType"]["sportTypeKey"] == "running"
    assert body["workoutSegments"][0]["sportType"]["sportTypeKey"] == "running"
    first = body["workoutSegments"][0]["workoutSteps"][0]
    assert first["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    # el formato propio de coach.html (sin blocks_format) sigue por su camino
    legacy = _build_workout_body({"name": "c", "sport": "run", "dur_min": 30,
                                  "blocks_json": json.dumps([{"type": "steady", "dur_min": 20, "pace": "4:30"}])})
    assert legacy["workoutSegments"][0]["workoutSteps"][0]["targetValueOne"] > 0
    # bici: sin cambios
    bike = _build_workout_body({"name": "b", "sport": "bike", "dur_min": 10, "ftp": 250,
                                "blocks_json": json.dumps(BIKE)})
    assert bike["sportType"]["sportTypeKey"] == "cycling"
    assert bike["workoutSegments"][0]["workoutSteps"][0]["targetType"]["workoutTargetTypeKey"] == "power.zone"
