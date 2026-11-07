"""Mi Plan: la copia Garmin de una sesion del plan propio no se muestra (gana LabX)."""
from .conftest import login, auth_headers
from api.models import GarminPlannedWorkout, OwnPlanSession

DAY = "2026-11-07"


def _own(db, uid, name, sport="swim", day=DAY):
    db.add(OwnPlanSession(user_id=uid, date_iso=day, sport=sport, name=name, dur_min=33, dist_km=1.6))
    db.commit()


def _gpw(db, uid, title, sport="swim", day=DAY, sid="g1"):
    db.add(GarminPlannedWorkout(user_id=uid, date_iso=day, garmin_scheduled_id=sid,
                                title=title, sport=sport, dur_min=35, dist_km=1.82, source="garmin"))
    db.commit()


def _get(client):
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/athlete/planned-workouts?start=%s&end=%s" % (DAY, DAY), headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    return r.json()


def test_copia_garmin_del_plan_propio_se_oculta(client, db, athlete_user):
    _own(db, athlete_user.id, "Nado 1600 mts")
    _gpw(db, athlete_user.id, "Nado 1600 mts")
    assert _get(client) == []
    # solo vista: la fila Garmin sigue en BD
    assert db.query(GarminPlannedWorkout).count() == 1


def test_garmin_sin_gemelo_se_muestra(client, db, athlete_user):
    _own(db, athlete_user.id, "Nado 1600 mts")
    _gpw(db, athlete_user.id, "z2", sport="bike", sid="g2")
    assert [r["title"] for r in _get(client)] == ["z2"]


def test_titulos_distintos_mismo_dia_y_deporte_se_muestran(client, db, athlete_user):
    _own(db, athlete_user.id, "Nado 1600 mts")
    _gpw(db, athlete_user.id, "Tecnica con paletas y pull buoy")
    assert len(_get(client)) == 1
