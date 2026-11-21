"""MATCHING (BUILD 403): match_sessions_for_user lee las columnas reales de
GarminActivity (dur_min, dist_km, tss, date_iso) y no moving_time_seconds /
distance_meters / started_at, que no existen y lanzaban AttributeError."""
from datetime import date, datetime, timedelta

from ..models import GarminActivity, PlanSession, TrainingPlan
from ..services.plan_matching_service import (
    match_sessions_all_users, match_sessions_for_user)


def _setup(db, coach, athlete, d, tss_planned=100.0):
    p = TrainingPlan(coach_id=coach.id, athlete_id=athlete.id, name="P403",
                     start_date=(d - timedelta(days=1)).isoformat(),
                     end_date=(d + timedelta(weeks=4)).isoformat(),
                     weeks=4, is_active=True)
    db.add(p)
    db.commit()
    s = PlanSession(plan_id=p.id, athlete_id=athlete.id, date_iso=d.isoformat(),
                    week_number=1, sport="run", tss_planned=tss_planned)
    db.add(s)
    db.commit()
    return s


def _act(db, uid, d, key, tss, dur_min, dist_km, sport="running"):
    a = GarminActivity(user_id=uid, activity_id=f"t403-{key}", date_iso=d.isoformat(),
                       sport=sport, tss=tss, dur_min=dur_min, dist_km=dist_km)
    db.add(a)
    db.commit()
    return a


def test_match_llena_campos_con_columnas_reales(db, coach_user, athlete_user):
    d = date.today() - timedelta(days=1)
    s = _setup(db, coach_user, athlete_user, d)
    _act(db, athlete_user.id, d, "a", 90.0, 62, 10.456)
    res = match_sessions_for_user(athlete_user.id, db, days_back=7)
    assert res["matched"] == 1
    db.refresh(s)
    best = db.query(GarminActivity).filter_by(activity_id="t403-a").one()
    assert s.garmin_activity_id == best.id
    assert s.tss_actual == 90.0
    assert s.duration_actual_min == best.dur_min == 62
    assert s.distance_actual_km == 10.46
    assert s.compliance_pct == 90.0
    # Sin hora real en GarminActivity: solo la fecha, medianoche.
    assert s.completed_at == datetime.combine(d, datetime.min.time())


def test_match_sin_duracion_ni_distancia_deja_none(db, coach_user, athlete_user):
    d = date.today() - timedelta(days=1)
    s = _setup(db, coach_user, athlete_user, d)
    _act(db, athlete_user.id, d, "b", 80.0, None, None)
    assert match_sessions_for_user(athlete_user.id, db, days_back=7)["matched"] == 1
    db.refresh(s)
    assert s.duration_actual_min is None and s.distance_actual_km is None
    assert s.tss_actual == 80.0


def test_regresion_corrida_completa_sin_attributeerror(db, coach_user, athlete_user):
    d = date.today() - timedelta(days=1)
    s = _setup(db, coach_user, athlete_user, d)
    _act(db, athlete_user.id, d, "c", 100.0, 45, 8.0)
    results = match_sessions_all_users(db, days_back=7)
    mine = [r for r in results if r.get("user_id") == athlete_user.id]
    assert mine and mine[0]["matched"] == 1
    assert "error" not in mine[0]
    db.refresh(s)
    assert s.garmin_activity_id is not None
