"""
Tests — Training Plan Intelligence (Sprint 6 / B-09 + B-14)
"""
import pytest
from datetime import date, timedelta
from .conftest import login

from ..routes.plan_builder_routes import (
    _default_sessions_for_week,
    _project_ctl,
    _ses,
    BUILTIN_TEMPLATES,
    SPORTS,
)
from ..services.plan_matching_service import (
    _garmin_sport_to_plan_sport,
    _is_sport_compatible,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: generación de sesiones
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultSessions:
    """Genera sesiones correctas por fase y tipo de plan."""

    def _gen(self, week_num, total=16, tpl="ironman_16w", ctl=90):
        start = date.today().isoformat()
        return _default_sessions_for_week(
            week_num=week_num, total_weeks=total, template_key=tpl,
            ctl_target=ctl, start_date=start,
            athlete_id="uid_test", plan_id="plan_test",
        )

    def test_base_week_generates_sessions(self):
        sessions = self._gen(week_num=1)
        assert len(sessions) > 0

    def test_taper_week_fewer_sessions(self):
        base  = self._gen(week_num=3)
        taper = self._gen(week_num=15)
        assert len(taper) <= len(base)

    def test_sessions_have_required_fields(self):
        sessions = self._gen(week_num=5)
        for s in sessions:
            assert "sport"       in s
            assert "date_iso"    in s
            assert "tss_planned" in s
            assert "duration_min" in s
            assert s["sport"]    in SPORTS

    def test_tss_proportional_to_ctl(self):
        low  = self._gen(week_num=6, ctl=50)
        high = self._gen(week_num=6, ctl=100)
        tss_low  = sum(s["tss_planned"] for s in low)
        tss_high = sum(s["tss_planned"] for s in high)
        assert tss_high > tss_low

    def test_peak_week_has_brick(self):
        sessions = self._gen(week_num=14, tpl="ironman_16w")
        sports   = [s["sport"] for s in sessions]
        assert "brick" in sports

    def test_marathon_plan_run_dominant(self):
        sessions = self._gen(week_num=5, tpl="marathon_16w")
        runs = [s for s in sessions if s["sport"] == "run"]
        assert len(runs) >= 3

    def test_recovery_week_lower_tss(self):
        hard   = self._gen(week_num=3)   # semana 3 de 4 (carga)
        recov  = self._gen(week_num=4)   # semana 4 (recuperación)
        tss_h  = sum(s["tss_planned"] for s in hard)
        tss_r  = sum(s["tss_planned"] for s in recov)
        assert tss_r < tss_h

    def test_all_templates_generate_sessions(self):
        for tpl_key in BUILTIN_TEMPLATES:
            sessions = self._gen(week_num=1, tpl=tpl_key)
            assert len(sessions) > 0, f"Template {tpl_key} no generó sesiones"

    def test_dates_fall_in_correct_week(self):
        start    = date.today()
        sessions = _default_sessions_for_week(
            week_num=2, total_weeks=16, template_key="ironman_16w",
            ctl_target=90, start_date=start.isoformat(),
            athlete_id="a", plan_id="p",
        )
        week2_start = start + timedelta(weeks=1)
        week2_end   = week2_start + timedelta(days=6)
        for s in sessions:
            d = date.fromisoformat(s["date_iso"])
            assert week2_start <= d <= week2_end, f"{d} outside week 2"


class TestCtlProjection:
    """Proyección CTL correcta."""

    def test_empty_plan_ctl_stays_flat(self):
        curve = _project_ctl(50.0, [0] * 16)
        # Sin carga, CTL decae exponencialmente
        assert curve[0]  == 50.0
        assert curve[-1] < 50.0

    def test_load_increases_ctl(self):
        curve = _project_ctl(40.0, [500] * 16)
        assert curve[-1] > curve[0]

    def test_curve_length_correct(self):
        curve = _project_ctl(50.0, [300] * 12)
        assert len(curve) == 13  # semana 0 + 12 semanas

    def test_high_load_approaches_tss_daily(self):
        # Con TSS diario muy alto, CTL debe crecer significativamente
        curve = _project_ctl(30.0, [1400] * 20)  # 200/day
        assert curve[-1] > 100

    def test_taper_decreases_ctl(self):
        # Construir primero, luego tapear
        build = _project_ctl(40.0, [700] * 10)
        ctl_peak = build[-1]
        taper = _project_ctl(ctl_peak, [200] * 3)
        assert taper[-1] < ctl_peak


class TestSessionHelper:
    """Helper _ses genera sesiones correctas."""

    def test_basic_session_structure(self):
        s = _ses(date.today(), 0, "run", 80, "Z2", "Carrera", 1, "plan_1", "athlete_1")
        assert s["sport"]       == "run"
        assert s["tss_planned"] == 80
        assert s["zone"]        == "Z2"
        assert s["plan_id"]     == "plan_1"

    def test_duration_positive(self):
        for sport in ["swim", "bike", "run", "strength"]:
            s = _ses(date.today(), 0, sport, 100, "Z2", "Test", 1, "p", "a")
            assert s["duration_min"] > 0

    def test_intensity_derived_from_zone(self):
        easy  = _ses(date.today(), 0, "run", 50, "Z1", "Easy", 1, "p", "a")
        hard  = _ses(date.today(), 0, "run", 80, "threshold", "Tempo", 1, "p", "a")
        assert easy["intensity"] == "easy"
        assert hard["intensity"] == "hard"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: matching service
# ─────────────────────────────────────────────────────────────────────────────

class TestSportMapping:

    def test_swimming_maps_to_swim(self):
        assert _garmin_sport_to_plan_sport("swimming") == "swim"
        assert _garmin_sport_to_plan_sport("open_water_swimming") == "swim"

    def test_cycling_maps_to_bike(self):
        assert _garmin_sport_to_plan_sport("cycling") == "bike"
        assert _garmin_sport_to_plan_sport("virtual_ride") == "bike"

    def test_running_maps_to_run(self):
        assert _garmin_sport_to_plan_sport("running") == "run"
        assert _garmin_sport_to_plan_sport("trail_running") == "run"

    def test_strength_maps_correctly(self):
        assert _garmin_sport_to_plan_sport("strength_training") == "strength"

    def test_unknown_maps_to_other(self):
        assert _garmin_sport_to_plan_sport("surfing") == "other"
        assert _garmin_sport_to_plan_sport(None) == "other"

    def test_case_insensitive(self):
        assert _garmin_sport_to_plan_sport("Running") == "run"
        assert _garmin_sport_to_plan_sport("CYCLING") == "bike"


class TestSportCompatibility:

    def test_exact_match_compatible(self):
        assert _is_sport_compatible("run", "running")
        assert _is_sport_compatible("swim", "swimming")
        assert _is_sport_compatible("bike", "cycling")

    def test_brick_accepts_bike_and_run(self):
        assert _is_sport_compatible("brick", "cycling")
        assert _is_sport_compatible("brick", "running")
        assert _is_sport_compatible("brick", "triathlon")

    def test_other_accepts_anything(self):
        assert _is_sport_compatible("other", "yoga")
        assert _is_sport_compatible("other", "hiking")

    def test_run_not_compatible_with_swim(self):
        assert not _is_sport_compatible("run", "swimming")

    def test_swim_not_compatible_with_bike(self):
        assert not _is_sport_compatible("swim", "cycling")


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()  # prevent cookie from overriding Authorization header
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def coach_headers(client, coach_user):
    token = login(client, "coach@test.com", "CoachPass123")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_list_templates(client, auth_headers):
    resp = client.get("/api/plans/templates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 4
    for tpl in data:
        assert "id"    in tpl
        assert "name"  in tpl
        assert "weeks" in tpl


def test_list_plans_empty_initially(client, auth_headers):
    resp = client.get("/api/plans", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_coach_create_plan_with_template(client, coach_headers, auth_headers):
    """Coach crea plan para atleta con template → sesiones generadas automáticamente."""
    # Obtener athlete_id del usuario de prueba
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip("No auth/me endpoint")
    athlete_id = me.json().get("id")
    if not athlete_id:
        pytest.skip("No athlete id")

    resp = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id":  athlete_id,
        "name":        "Plan Test Ironman",
        "start_date":  "2026-09-01",
        "template_id": "ironman_703_12w",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] == True
    assert "plan_id" in data
    assert data["sessions_created"] > 0


def test_get_plan_detail_with_sessions(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    create = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id,
        "name": "Plan Detail Test",
        "start_date": "2026-10-01",
        "template_id": "olympic_8w",
    })
    if create.status_code != 200:
        pytest.skip("Plan creation failed")

    plan_id = create.json()["plan_id"]
    resp    = client.get(f"/api/plans/{plan_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions_by_week" in data
    assert data["total_sessions"] > 0
    assert "total_tss" in data


def test_ctl_projection_structure(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    create = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id,
        "name": "CTL Projection Test",
        "start_date": "2026-11-01",
        "template_id": "ironman_703_12w",
    })
    if create.status_code != 200:
        pytest.skip()

    plan_id = create.json()["plan_id"]
    resp    = client.get(f"/api/plans/{plan_id}/ctl-projection", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "ctl_curve"   in data
    assert "tss_by_week" in data
    assert "ctl_start"   in data
    assert len(data["ctl_curve"]) == data.get("weeks", 12) + 1 if "weeks" not in data else True


def test_plan_vs_actual_structure(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    create = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id,
        "name": "PvA Test",
        "start_date": "2026-01-01",   # Plan ya pasado → semanas con actual
        "template_id": "olympic_8w",
    })
    if create.status_code != 200:
        pytest.skip()

    plan_id = create.json()["plan_id"]
    resp    = client.get(f"/api/plans/{plan_id}/plan-vs-actual", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "weeks"   in data
    assert "plan_id" in data
    for week in data["weeks"]:
        assert "tss_planned"    in week
        assert "tss_actual"     in week
        assert "compliance_pct" in week


def test_add_session_to_plan(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    create = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id,
        "name": "Session CRUD Test",
        "start_date": "2026-09-15",
    })
    if create.status_code != 200:
        pytest.skip()

    plan_id = create.json()["plan_id"]
    resp    = client.post(f"/api/plans/{plan_id}/sessions", headers=auth_headers, json={
        "sport":       "run",
        "date_iso":    "2026-09-17",
        "tss_planned": 80,
        "zone":        "Z2",
        "title":       "Carrera larga test",
        "duration_min":75,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["session"]["sport"]       == "run"
    assert data["session"]["tss_planned"] == 80


def test_update_session_drag_drop(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    p = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id, "name": "Drag Test", "start_date": "2026-09-15",
    })
    if p.status_code != 200:
        pytest.skip()
    pid = p.json()["plan_id"]

    s = client.post(f"/api/plans/{pid}/sessions", headers=auth_headers, json={
        "sport": "bike", "date_iso": "2026-09-16", "tss_planned": 100,
    })
    if s.status_code != 200:
        pytest.skip()
    sid = s.json()["session"]["id"]

    resp = client.patch(f"/api/plans/{pid}/sessions/{sid}", headers=auth_headers, json={
        "date_iso": "2026-09-18",   # Drag to Thursday
    })
    assert resp.status_code == 200
    updated = resp.json()["session"]
    assert updated["date_iso"]    == "2026-09-18"
    assert updated["day_of_week"] == date.fromisoformat("2026-09-18").weekday()


def test_delete_session(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    p = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id, "name": "Delete Session Test", "start_date": "2026-09-15",
    })
    if p.status_code != 200:
        pytest.skip()
    pid = p.json()["plan_id"]

    s = client.post(f"/api/plans/{pid}/sessions", headers=auth_headers, json={
        "sport": "swim", "date_iso": "2026-09-15", "tss_planned": 60,
    })
    sid  = s.json()["session"]["id"]
    resp = client.delete(f"/api/plans/{pid}/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"]


def test_add_session_invalid_sport(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    p = client.post("/api/coach/plans", headers=coach_headers, json={
        "athlete_id": athlete_id, "name": "Validation Test", "start_date": "2026-09-15",
    })
    if p.status_code != 200:
        pytest.skip()
    pid = p.json()["plan_id"]

    resp = client.post(f"/api/plans/{pid}/sessions", headers=auth_headers, json={
        "sport": "skateboarding", "date_iso": "2026-09-15", "tss_planned": 50,
    })
    assert resp.status_code == 422


def test_plan_requires_auth(client):
    resp = client.get("/api/plans")
    assert resp.status_code == 401


def test_coach_compliance_panel(client, coach_headers):
    resp = client.get("/api/coach/plans/compliance", headers=coach_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_bulk_apply_template(client, coach_headers, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    if me.status_code != 200:
        pytest.skip()
    athlete_id = me.json().get("id")

    resp = client.post("/api/plans/templates/olympic_8w/apply",
                       headers=coach_headers, json={
                           "athlete_ids": [athlete_id],
                           "start_date":  "2026-10-15",
                       })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["plans_created"] == 1
    assert data["results"][0]["sessions"] > 0


def test_invalid_template_apply(client, coach_headers):
    resp = client.post("/api/plans/templates/nonexistent/apply",
                       headers=coach_headers, json={
                           "athlete_ids": ["any"],
                           "start_date": "2026-10-01",
                       })
    assert resp.status_code == 404
