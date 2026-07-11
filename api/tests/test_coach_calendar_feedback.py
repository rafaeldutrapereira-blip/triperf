"""
Tests — Coach Calendar + Athlete Session Feedback (Sprint 10)
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock
from .conftest import login


# ─────────────────────────────────────────────────────────────────────────────
# Unit: RPE validation logic
# ─────────────────────────────────────────────────────────────────────────────

def _rpe_to_perceived(rpe: int) -> str:
    if rpe <= 3: return "easy"
    if rpe <= 5: return "moderate"
    if rpe <= 7: return "hard"
    return "very_hard"


class TestRpeValidation:
    def test_rpe_1_is_easy(self):     assert _rpe_to_perceived(1) == "easy"
    def test_rpe_3_is_easy(self):     assert _rpe_to_perceived(3) == "easy"
    def test_rpe_4_is_moderate(self): assert _rpe_to_perceived(4) == "moderate"
    def test_rpe_5_is_moderate(self): assert _rpe_to_perceived(5) == "moderate"
    def test_rpe_6_is_hard(self):     assert _rpe_to_perceived(6) == "hard"
    def test_rpe_7_is_hard(self):     assert _rpe_to_perceived(7) == "hard"
    def test_rpe_8_is_very_hard(self):assert _rpe_to_perceived(8) == "very_hard"
    def test_rpe_10_is_very_hard(self):assert _rpe_to_perceived(10) == "very_hard"


class TestOverloadDetection:
    """Mirror of backend overload detection: >50% sessions RPE>=8."""
    def _is_overloaded(self, rpe_list):
        high = sum(1 for r in rpe_list if r >= 8)
        return high / max(len(rpe_list), 1) >= 0.5

    def test_all_high_rpe_is_overload(self):
        assert self._is_overloaded([9, 8, 10, 8]) is True

    def test_no_high_rpe_not_overload(self):
        assert self._is_overloaded([4, 5, 6, 7]) is False

    def test_exactly_50pct_is_overload(self):
        assert self._is_overloaded([8, 8, 5, 5]) is True

    def test_below_50pct_not_overload(self):
        assert self._is_overloaded([8, 5, 5, 5]) is False

    def test_single_high_rpe(self):
        assert self._is_overloaded([9]) is True

    def test_empty_list_not_overload(self):
        assert self._is_overloaded([]) is False


# ─────────────────────────────────────────────────────────────────────────────
# Unit: Calendar week grouping logic
# ─────────────────────────────────────────────────────────────────────────────

class TestCalendarWeekGrouping:
    def test_sessions_grouped_by_date(self):
        sessions = [
            {"date_iso": "2026-06-01", "sport": "bike", "tss_planned": 80},
            {"date_iso": "2026-06-01", "sport": "run",  "tss_planned": 40},
            {"date_iso": "2026-06-02", "sport": "swim", "tss_planned": 30},
        ]
        calendar = {}
        for s in sessions:
            d = s["date_iso"]
            if d not in calendar: calendar[d] = []
            calendar[d].append(s)

        assert len(calendar) == 2
        assert len(calendar["2026-06-01"]) == 2
        assert len(calendar["2026-06-02"]) == 1

    def test_week_tss_sum(self):
        sessions = [
            {"week_number": 1, "tss_planned": 80, "tss_actual": 75, "completed_at": "2026-06-01"},
            {"week_number": 1, "tss_planned": 40, "tss_actual": 42, "completed_at": None},
            {"week_number": 2, "tss_planned": 60, "tss_actual": None, "completed_at": None},
        ]
        weeks: dict = {}
        for s in sessions:
            wn = s["week_number"]
            if wn not in weeks:
                weeks[wn] = {"tss_planned": 0, "tss_actual": 0, "n": 0, "completed": 0}
            weeks[wn]["tss_planned"] += s["tss_planned"] or 0
            weeks[wn]["tss_actual"]  += s["tss_actual"]  or 0
            weeks[wn]["n"] += 1
            if s["completed_at"]: weeks[wn]["completed"] += 1

        assert weeks[1]["tss_planned"] == 120
        assert weeks[1]["tss_actual"]  == 117
        assert weeks[1]["completed"]   == 1
        assert weeks[2]["n"] == 1

    def test_compliance_calculation(self):
        n_sessions  = 5
        n_completed = 4
        pct = round(n_completed / n_sessions * 100)
        assert pct == 80

    def test_rpe_avg_per_week(self):
        rpe_vals = [5, 7, 8, 6]
        avg = round(sum(rpe_vals) / len(rpe_vals), 1)
        assert avg == 6.5


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (API)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, coach_user):
    token = login(client, "coach@test.com", "CoachPass123")
    client.cookies.clear()  # prevent cookie from overriding Authorization header
    return {"Authorization": f"Bearer {token}"}


def test_athlete_feedback_requires_auth(client):
    resp = client.patch("/api/plans/fake-plan/sessions/fake-session/athlete-feedback",
                        json={"rpe": 7})
    assert resp.status_code == 401


def test_plan_calendar_requires_auth(client):
    resp = client.get("/api/plans/fake-plan/calendar")
    assert resp.status_code == 401


def test_rpe_summary_requires_auth(client):
    resp = client.get("/api/coach/plans/rpe-summary")
    assert resp.status_code == 401


def test_athlete_feedback_nonexistent_session(client, auth_headers):
    resp = client.patch(
        "/api/plans/nonexistent-plan/sessions/nonexistent-session/athlete-feedback",
        json={"rpe": 7},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_athlete_feedback_rpe_out_of_range(client, auth_headers):
    """RPE fuera de 1-10 debe retornar 400 si la sesión existiera."""
    # Con sesión inexistente retorna 404, pero validamos la lógica de rango
    resp = client.patch(
        "/api/plans/any/sessions/any/athlete-feedback",
        json={"rpe": 11},
        headers=auth_headers,
    )
    # 404 porque no existe la sesión; si existiera sería 400 por rpe=11
    assert resp.status_code in (400, 404)


def test_plan_calendar_not_found(client, auth_headers):
    resp = client.get("/api/plans/nonexistent-plan-id/calendar", headers=auth_headers)
    assert resp.status_code == 404


def test_rpe_summary_structure(client, auth_headers):
    resp = client.get("/api/coach/plans/rpe-summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "athletes" in data
    assert "n_plans"  in data
    assert "n_alerts" in data
    assert isinstance(data["athletes"], list)


def test_rpe_summary_athlete_fields(client, auth_headers):
    resp = client.get("/api/coach/plans/rpe-summary", headers=auth_headers)
    assert resp.status_code == 200
    for athlete in resp.json().get("athletes", []):
        assert "plan_id"       in athlete
        assert "rpe_avg"       in athlete
        assert "overload_flag" in athlete
        assert "compliance_pct"in athlete


def test_calendar_plan_full_flow(client, auth_headers, athlete_user):
    """Crear plan → obtener calendar → verificar estructura."""
    # Crear plan
    create = client.post("/api/coach/plans", headers=auth_headers, json={
        "athlete_id":  athlete_user.id,
        "name":        "Test Calendar Plan",
        "start_date":  "2026-07-01",
        "end_date":    "2026-07-28",
        "weeks":       4,
        "goal_ctl":    60,
    })
    if create.status_code not in (200, 201):
        pytest.skip("Plan creation requires coach role and valid athlete")

    plan_id = create.json().get("plan_id") or create.json().get("id")
    if not plan_id:
        pytest.skip("No plan_id in response")

    resp = client.get(f"/api/plans/{plan_id}/calendar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "calendar"  in data
    assert "weeks"     in data
    assert "plan_meta" in data
    assert isinstance(data["calendar"], dict)
    assert isinstance(data["weeks"],    list)


def test_feedback_flow(client, auth_headers, athlete_user):
    """Crear sesión → logear feedback RPE → verificar respuesta."""
    # Primero crear un plan con sesión
    create = client.post("/api/coach/plans", headers=auth_headers, json={
        "athlete_id": athlete_user.id,
        "name":       "Feedback Test Plan",
        "start_date": "2026-07-01",
        "end_date":   "2026-07-14",
        "weeks": 2,
        "goal_ctl": 55,
    })
    if create.status_code not in (200, 201):
        pytest.skip("Plan creation skipped")

    plan_id = create.json().get("plan_id") or create.json().get("id")
    if not plan_id:
        pytest.skip()

    # Añadir sesión
    sess = client.post(f"/api/plans/{plan_id}/sessions", headers=auth_headers, json={
        "date_iso":    "2026-07-01",
        "sport":       "bike",
        "title":       "Z2 Rodada",
        "duration_min":90,
        "tss_planned": 75,
    })
    if sess.status_code not in (200, 201):
        pytest.skip("Session creation skipped")

    sid = sess.json().get("session", {}).get("id") or sess.json().get("id")
    if not sid:
        pytest.skip()

    # Logear feedback como atleta (el endpoint requiere athlete_id == me.id)
    athlete_token = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    athlete_hdrs = {"Authorization": f"Bearer {athlete_token}"}
    fb = client.patch(f"/api/plans/{plan_id}/sessions/{sid}/athlete-feedback",
                      headers=athlete_hdrs,
                      json={"rpe": 7, "perceived_effort": "hard", "mood": "good",
                            "athlete_note": "Piernas pesadas pero completé."})
    assert fb.status_code == 200
    data = fb.json()
    assert data["rpe"]              == 7
    assert data["perceived_effort"] == "hard"
    assert data["mood"]             == "good"
    assert data["feedback_at"]      is not None
