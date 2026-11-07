"""A3: preview del impacto CTL/ATL/TSB de un plan antes de aplicarlo (solo lectura)."""
import math
from datetime import date, timedelta

import pytest

from .conftest import login, auth_headers
from ..models import (
    AssignedWorkout, CoachAthlete, GarminTrainingLoad, Macrocycle,
    MacrocycleWeek, PlanSession, TrainingPlan, WeekTemplate,
    WeekTemplateDay, WorkoutTemplate,
)
from ..services.performance_analytics_service import (
    _ATL_DECAY, _CTL_DECAY, build_plan_impact, project_pmc_from_daily_tss,
)

ANCHOR = date(2026, 1, 5)


# ── Matematica pura ───────────────────────────────────────────────────────────

def test_day_without_load_decays_with_pmc_constants():
    pts = project_pmc_from_daily_tss(60, 80, ANCHOR, {}, ANCHOR + timedelta(days=1))
    assert len(pts) == 1
    assert pts[0]["ctl"] == round(60 * (1 - _CTL_DECAY), 1)
    assert pts[0]["atl"] == round(80 * (1 - _ATL_DECAY), 1)
    assert pts[0]["tsb"] == round(pts[0]["ctl"] - pts[0]["atl"], 1)


def test_decay_matches_exponential_closed_form():
    n = 10
    pts = project_pmc_from_daily_tss(60, 80, ANCHOR, {}, ANCHOR + timedelta(days=n))
    assert pts[-1]["ctl"] == pytest.approx(60 * math.exp(-n / 42), abs=0.1)
    assert pts[-1]["atl"] == pytest.approx(80 * math.exp(-n / 7), abs=0.1)


def test_typical_week_raises_ctl_and_atl_faster():
    # 6 dias x 100 TSS + 1 descanso, 4 semanas, desde CTL=ATL=40
    daily = {}
    for w in range(4):
        for dd in range(6):
            daily[ANCHOR + timedelta(days=1 + w * 7 + dd)] = 100.0
    pts = project_pmc_from_daily_tss(40, 40, ANCHOR, daily, ANCHOR + timedelta(days=28))
    assert pts[-1]["ctl"] > 40
    assert pts[-1]["atl"] > pts[-1]["ctl"]           # la fatiga sube mas rapido
    assert pts[-1]["tsb"] < 0
    # valor esperado: iterar la EWMA a mano
    ctl = atl = 40.0
    for i in range(1, 29):
        t = daily.get(ANCHOR + timedelta(days=i), 0.0)
        ctl += (t - ctl) * (1 - math.exp(-1 / 42))
        atl += (t - atl) * (1 - math.exp(-1 / 7))
    assert pts[-1]["ctl"] == round(ctl, 1)
    assert pts[-1]["atl"] == round(atl, 1)


def test_projection_starts_day_after_anchor_and_ends_inclusive():
    end = ANCHOR + timedelta(days=5)
    pts = project_pmc_from_daily_tss(50, 50, ANCHOR, {}, end)
    assert pts[0]["date_iso"] == (ANCHOR + timedelta(days=1)).isoformat()
    assert pts[-1]["date_iso"] == end.isoformat()


# ── build_plan_impact (DB) ────────────────────────────────────────────────────

def _baseline(db, user_id, ctl=50.0, atl=60.0, days_ago=1):
    db.add(GarminTrainingLoad(
        user_id=user_id, date_iso=(date.today() - timedelta(days=days_ago)).isoformat(),
        ctl=ctl, atl=atl, tsb=ctl - atl, tss=0,
    ))
    db.commit()


def test_sessions_without_tss_are_counted_and_excluded(db, athlete_user):
    _baseline(db, athlete_user.id)
    d = date.today() + timedelta(days=3)
    r = build_plan_impact(db, athlete_user.id, [(d, 80), (d + timedelta(days=1), None),
                                                (d + timedelta(days=2), 0)])
    assert r["sessions_total"] == 3
    assert r["sessions_without_tss"] == 2
    assert r["total_tss"] == 80.0
    assert r["has_baseline"] is True
    by_date = {p["date_iso"]: p for p in r["points"]}
    assert by_date[(d + timedelta(days=1)).isoformat()]["tss"] == 0.0   # no se inventa TSS


def test_two_sessions_same_day_sum(db, athlete_user):
    _baseline(db, athlete_user.id)
    d = date.today() + timedelta(days=2)
    r = build_plan_impact(db, athlete_user.id, [(d, 40), (d, 35)])
    assert {p["date_iso"]: p for p in r["points"]}[d.isoformat()]["tss"] == 75.0


def test_no_baseline_does_not_invent_pmc(db, athlete_user):
    r = build_plan_impact(db, athlete_user.id, [(date.today() + timedelta(days=2), 80)])
    assert r["has_baseline"] is False
    assert r["points"] == [] and r["baseline"] is None
    assert r["sessions_total"] == 1


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _coach_headers(client, coach_user):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _relate(db, coach_user, athlete_user):
    db.add(CoachAthlete(coach_id=coach_user.id, athlete_id=athlete_user.id, activo=True))
    db.commit()


def _week_template(db, coach_user, tss_list):
    wt = WeekTemplate(coach_id=coach_user.id, nombre="Semana A3")
    db.add(wt)
    db.flush()
    for i, tss in enumerate(tss_list):
        w = WorkoutTemplate(coach_id=coach_user.id, sport="bike", nombre=f"W{i}", tss=tss)
        db.add(w)
        db.flush()
        db.add(WeekTemplateDay(week_template_id=wt.id, day_of_week=i, workout_template_id=w.id))
    db.commit()
    return wt


def _next_monday():
    d = date.today() + timedelta(days=7)
    return d - timedelta(days=d.weekday())


def test_week_template_preview_is_read_only_and_reports_missing_tss(client, db, coach_user, athlete_user):
    _relate(db, coach_user, athlete_user)
    _baseline(db, athlete_user.id)
    wt = _week_template(db, coach_user, [60, None, 90])
    before = db.query(AssignedWorkout).count()
    r = client.post(f"/api/coach/week-templates/{wt.id}/preview-impact",
                    headers=_coach_headers(client, coach_user),
                    json={"start_date": _next_monday().isoformat(), "athlete_id": athlete_user.id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sessions_total"] == 3
    assert data["sessions_without_tss"] == 1
    assert data["total_tss"] == 150.0
    assert data["points"][-1]["date_iso"] == (_next_monday() + timedelta(days=2)).isoformat()
    assert db.query(AssignedWorkout).count() == before            # no escribe nada


def test_week_template_preview_rejects_group_and_foreign_athlete(client, db, coach_user, athlete_user):
    wt = _week_template(db, coach_user, [60])
    h = _coach_headers(client, coach_user)
    body = {"start_date": _next_monday().isoformat(), "group_id": "g1"}
    assert client.post(f"/api/coach/week-templates/{wt.id}/preview-impact", headers=h, json=body).status_code == 400
    body = {"start_date": _next_monday().isoformat(), "athlete_id": athlete_user.id}
    assert client.post(f"/api/coach/week-templates/{wt.id}/preview-impact", headers=h, json=body).status_code == 403


def test_macrocycle_preview_spans_weeks(client, db, coach_user, athlete_user):
    _relate(db, coach_user, athlete_user)
    _baseline(db, athlete_user.id)
    wt = _week_template(db, coach_user, [50, 50])
    mc = Macrocycle(coach_id=coach_user.id, nombre="Macro A3")
    db.add(mc)
    db.flush()
    for pos in (1, 2, 3):
        db.add(MacrocycleWeek(macrocycle_id=mc.id, position=pos, week_template_id=wt.id))
    db.commit()
    r = client.post(f"/api/coach/macrocycles/{mc.id}/preview-impact",
                    headers=_coach_headers(client, coach_user),
                    json={"start_date": _next_monday().isoformat(), "athlete_id": athlete_user.id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sessions_total"] == 6
    assert data["total_tss"] == 300.0
    assert data["points"][-1]["date_iso"] == (_next_monday() + timedelta(days=15)).isoformat()


def test_builtin_template_preview_does_not_create_plans(client, db, coach_user, athlete_user):
    _relate(db, coach_user, athlete_user)
    _baseline(db, athlete_user.id, ctl=20.0, atl=20.0)   # base baja: el plan debe subir CTL
    h = _coach_headers(client, coach_user)
    body = {"athlete_id": athlete_user.id, "start_date": _next_monday().isoformat()}
    r = client.post("/api/plans/templates/olympic_8w/preview-impact", headers=h, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sessions_total"] > 0 and data["sessions_without_tss"] == 0
    assert data["points"][-1]["ctl"] > data["baseline"]["ctl"]
    assert db.query(TrainingPlan).count() == 0 and db.query(PlanSession).count() == 0
    # mismas sesiones que el apply real
    ra = client.post("/api/plans/templates/olympic_8w/apply", headers=h,
                     json={"athlete_ids": [athlete_user.id], "start_date": body["start_date"]})
    assert ra.json()["results"][0]["sessions"] == data["sessions_total"]


def test_builtin_preview_404_and_requires_coach(client, db, coach_user, athlete_user):
    h = _coach_headers(client, coach_user)
    assert client.post("/api/plans/templates/nope/preview-impact", headers=h,
                       json={"athlete_id": "x", "start_date": "2026-12-01"}).status_code == 404
    ha = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    assert client.post("/api/plans/templates/olympic_8w/preview-impact", headers=ha,
                       json={"athlete_id": athlete_user.id, "start_date": "2026-12-01"}).status_code == 403
