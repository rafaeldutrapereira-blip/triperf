"""TSS-LATENTE (BUILD 402): plan builder y matching leen la columna real `tss`
de GarminActivity (`training_stress_score` no existe y lanzaba AttributeError)."""
from datetime import date, timedelta

import pytest

from ..models import CoachAthlete, GarminActivity, PlanSession, TrainingPlan
from ..services.plan_matching_service import match_sessions_for_user
from .conftest import login


def _hdr(client, email, pw):
    t = login(client, email, pw)
    client.cookies.clear()
    return {"Authorization": f"Bearer {t}"}


def _plan(db, coach, athlete, start):
    p = TrainingPlan(coach_id=coach.id, athlete_id=athlete.id, name="P402",
                     start_date=start.isoformat(),
                     end_date=(start + timedelta(weeks=4)).isoformat(),
                     weeks=4, is_active=True)
    db.add(p)
    db.commit()
    db.add(PlanSession(plan_id=p.id, athlete_id=athlete.id,
                       date_iso=(start + timedelta(days=1)).isoformat(),
                       week_number=1, sport="run", tss_planned=100.0))
    db.commit()
    db.refresh(p)
    return p


def _acts(db, uid, d, tss_values, sport="run"):
    for i, v in enumerate(tss_values):
        db.add(GarminActivity(user_id=uid, activity_id=f"t402-{d}-{i}",
                              date_iso=d.isoformat(), sport=sport, tss=v))
    db.commit()


def test_plan_vs_actual_usa_tss_real(client, db, coach_user, athlete_user):
    start = date.today() - timedelta(days=7)
    p = _plan(db, coach_user, athlete_user, start)
    _acts(db, athlete_user.id, start + timedelta(days=1), [40.0, 35.5])
    h = _hdr(client, "athlete@test.com", "AthlPass123")
    r = client.get(f"/api/plans/{p.id}/plan-vs-actual", headers=h)
    assert r.status_code == 200, r.text
    w1 = r.json()["weeks"][0]
    assert w1["tss_actual"] == 75.5
    assert w1["compliance_pct"] == 75.5


def test_coach_compliance_usa_tss_real(client, db, coach_user, athlete_user):
    today = date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=1)
    _plan(db, coach_user, athlete_user, start)
    db.add(CoachAthlete(coach_id=coach_user.id, athlete_id=athlete_user.id, status="active"))
    db.commit()
    _acts(db, athlete_user.id, start + timedelta(days=1), [60.0, 20.0])
    h = _hdr(client, "coach@test.com", "CoachPass123")
    r = client.get("/api/coach/plans/compliance", headers=h)
    assert r.status_code == 200, r.text
    wk = {w["week"]: w for w in r.json()[0]["weeks"]}
    assert wk[1]["tss_actual"] == 80.0
    assert wk[1]["compliance_pct"] == 80.0


def test_matching_elige_actividad_con_tss_mas_cercano(db, coach_user, athlete_user, monkeypatch):
    # (BUILD 403: el matching ya usa dur_min/dist_km/date_iso; sin monkeypatch.)
    d = date.today() - timedelta(days=1)
    p = _plan(db, coach_user, athlete_user, d - timedelta(days=1))
    s = db.query(PlanSession).filter_by(plan_id=p.id).one()
    s.tss_planned = 100.0
    db.commit()
    _acts(db, athlete_user.id, d, [30.0, 95.0, 160.0], sport="running")
    res = match_sessions_for_user(athlete_user.id, db, days_back=7)
    assert res["matched"] == 1
    db.refresh(s)
    best = db.query(GarminActivity).filter_by(id=s.garmin_activity_id).one()
    assert best.tss == 95.0
    assert s.tss_actual == 95.0
    assert s.compliance_pct == 95.0
