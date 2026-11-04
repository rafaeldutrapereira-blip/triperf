"""W21 - Mi Plan muestra el realizado completo (actividades Adicionales)."""
from datetime import date
from pathlib import Path

from .conftest import login, auth_headers
from api.models import AssignedWorkout, GarminActivity, WorkoutTemplate

TODAY = date.today().isoformat()


def _act(db, uid, aid, sport="swim", dur=60, tss=40.0, name="Nat", day=TODAY, dist=2.9):
    db.add(GarminActivity(user_id=uid, activity_id=aid, name=name, sport=sport,
                          date_iso=day, dur_min=dur, dist_km=dist, tss=tss))
    db.commit()


def _assign(db, uid, sport="bike", dur=60):
    t = WorkoutTemplate(coach_id="c", sport=sport, nombre="Rodillo", dur_min=dur)
    db.add(t)
    db.flush()
    db.add(AssignedWorkout(template_id=t.id, athlete_id=uid, date_iso=TODAY))
    db.commit()


def _get(client):
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/athlete/plan/realizado?start=%s&end=%s" % (TODAY, TODAY),
                   headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    return r.json()


def test_actividad_extra_aparece_como_adicional_con_sus_datos(client, db, athlete_user):
    _assign(db, athlete_user.id)
    _act(db, athlete_user.id, "a-bike", sport="bike", dur=60, tss=50, name="Rodillo", dist=30)
    _act(db, athlete_user.id, "a-swim", sport="swim", dur=55, tss=35, name="Natacion", dist=2.9)
    by = {a["activity_id"]: a for a in _get(client)["activities"]}
    s = by["a-swim"]
    assert s["adicional"] is True
    assert (s["name"], s["sport"], s["dur_min"], s["dist_km"], s["tss"]) == ("Natacion", "swim", 55, 2.9, 35)


def test_actividad_calzada_no_se_duplica_como_adicional(client, db, athlete_user):
    _assign(db, athlete_user.id)
    _act(db, athlete_user.id, "a-bike", sport="bike", dur=60, tss=50)
    d = _get(client)
    assert len(d["activities"]) == 1
    assert d["activities"][0]["adicional"] is False
    assert d["totals"]["adicional_tss"] == 0


def test_totales_incluyen_adicionales(client, db, athlete_user):
    _assign(db, athlete_user.id)
    _act(db, athlete_user.id, "a-bike", sport="bike", dur=60, tss=50)
    _act(db, athlete_user.id, "a-swim", sport="swim", dur=55, tss=35)
    d = _get(client)
    assert d["totals"]["tss"] == 85 and d["totals"]["dur_min"] == 115
    assert d["totals"]["adicional_tss"] == 35 and d["totals"]["adicional_dur_min"] == 55
    assert d["by_date"][TODAY]["tss"] == 85


def test_segunda_actividad_mismo_deporte_es_adicional(client, db, athlete_user):
    _assign(db, athlete_user.id)
    _act(db, athlete_user.id, "b1", sport="bike", dur=60, tss=50)
    _act(db, athlete_user.id, "b2", sport="bike", dur=20, tss=10)
    flags = {a["activity_id"]: a["adicional"] for a in _get(client)["activities"]}
    assert flags == {"b1": False, "b2": True}


def test_aislamiento_entre_usuarios(client, db, athlete_user, coach_user):
    _act(db, coach_user.id, "otro", sport="run", dur=30, tss=20)
    _act(db, athlete_user.id, "mio", sport="swim")
    d = _get(client)
    assert [a["activity_id"] for a in d["activities"]] == ["mio"]
    assert d["totals"]["tss"] == 40


def test_front_usa_realizado_y_etiqueta_adicional():
    root = Path(__file__).resolve().parents[2]
    h = (root / "training_plan.html").read_text(encoding="utf-8")
    assert "/athlete/plan/realizado" in h and "tp_adicional" in h
    i = (root / "i18n.js").read_text(encoding="utf-8")
    assert i.count("tp_adicional:") == 3
