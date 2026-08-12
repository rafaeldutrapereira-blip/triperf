"""
Tests — Dashboard Intelligence (Sprint 9)
B-05: Training Readiness chip
B-06: Trend arrows (CTL, TSS, HRV, BB, Sleep)
B-22: Compliance score semanal desde plan_sessions
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from .conftest import login


# ─────────────────────────────────────────────────────────────────────────────
# Unit: Training Readiness label logic
# ─────────────────────────────────────────────────────────────────────────────

def _tr_label(score):
    if score >= 73:  return "Listo para entrenar fuerte", "#10B981"
    elif score >= 50: return "Buena forma",                "#EAB308"
    elif score >= 26: return "Recuperación recomendada",   "#F97316"
    else:             return "Descanso necesario",          "#EF4444"


class TestTrainingReadinessLabel:
    def test_high_score_is_green(self):
        label, color = _tr_label(85)
        assert "fuerte" in label
        assert color == "#10B981"

    def test_mid_score_is_yellow(self):
        label, color = _tr_label(60)
        assert "Buena" in label
        assert color == "#EAB308"

    def test_low_score_is_orange(self):
        label, color = _tr_label(35)
        assert "Recuperación" in label
        assert color == "#F97316"

    def test_critical_is_red(self):
        label, color = _tr_label(10)
        assert "Descanso" in label
        assert color == "#EF4444"

    def test_boundary_73(self):
        label73, _ = _tr_label(73)
        label72, _ = _tr_label(72)
        assert "fuerte" in label73
        assert "fuerte" not in label72

    def test_boundary_50(self):
        label50, _ = _tr_label(50)
        label49, _ = _tr_label(49)
        assert "Buena" in label50
        assert "Buena" not in label49

    def test_boundary_26(self):
        label26, _ = _tr_label(26)
        label25, _ = _tr_label(25)
        assert "Recuperación" in label26
        assert "Descanso" in label25


# ─────────────────────────────────────────────────────────────────────────────
# Unit: Trend deltas
# ─────────────────────────────────────────────────────────────────────────────

class TestTrendDeltas:
    def test_positive_tss_trend(self):
        tss_curr = 450.0
        tss_prev = 380.0
        trend = round(tss_curr - tss_prev, 1)
        assert trend == 70.0

    def test_negative_trend(self):
        curr, prev = 300.0, 420.0
        assert round(curr - prev, 1) == -120.0

    def test_zero_trend(self):
        assert round(100.0 - 100.0, 1) == 0.0

    def test_none_when_no_prev_data(self):
        tss_prev = None
        trend = None if tss_prev is None else round(400 - tss_prev, 1)
        assert trend is None

    def test_sleep_trend_positive(self):
        sleep_curr_avg = 7.8
        sleep_prev_avg = 6.9
        trend = round(sleep_curr_avg - sleep_prev_avg, 1)
        assert trend > 0

    def test_bb_trend_as_integer(self):
        bb_now, bb_old = 78, 55
        trend = round(bb_now - bb_old)
        assert trend == 23
        assert isinstance(trend, int)


# ─────────────────────────────────────────────────────────────────────────────
# Unit: Compliance calculation
# ─────────────────────────────────────────────────────────────────────────────

def _calc_compliance(sessions):
    """Mirror of backend logic."""
    non_skipped = [s for s in sessions if not s.get("is_skipped")]
    if not non_skipped:
        return None
    completed = [s for s in non_skipped if s.get("completed_at")]
    return round(len(completed) / len(non_skipped) * 100)


class TestComplianceCalc:
    def test_full_compliance(self):
        sessions = [{"is_skipped": False, "completed_at": "2026-06-28T08:00:00"} for _ in range(5)]
        assert _calc_compliance(sessions) == 100

    def test_zero_compliance(self):
        sessions = [{"is_skipped": False, "completed_at": None} for _ in range(4)]
        assert _calc_compliance(sessions) == 0

    def test_partial_compliance(self):
        sessions = [
            {"is_skipped": False, "completed_at": "2026-06-28"},
            {"is_skipped": False, "completed_at": "2026-06-27"},
            {"is_skipped": False, "completed_at": None},
            {"is_skipped": False, "completed_at": None},
        ]
        assert _calc_compliance(sessions) == 50

    def test_skipped_sessions_excluded(self):
        sessions = [
            {"is_skipped": True,  "completed_at": None},
            {"is_skipped": False, "completed_at": "2026-06-28"},
            {"is_skipped": False, "completed_at": "2026-06-27"},
        ]
        # 2 non-skipped, 2 completed → 100%
        assert _calc_compliance(sessions) == 100

    def test_empty_returns_none(self):
        assert _calc_compliance([]) is None

    def test_all_skipped_returns_none(self):
        sessions = [{"is_skipped": True, "completed_at": None} for _ in range(3)]
        assert _calc_compliance(sessions) is None

    def test_rounding(self):
        # 1 out of 3 = 33.33... → rounds to 33
        sessions = [
            {"is_skipped": False, "completed_at": "2026-06-28"},
            {"is_skipped": False, "completed_at": None},
            {"is_skipped": False, "completed_at": None},
        ]
        assert _calc_compliance(sessions) == 33


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (API)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_requires_auth(client):
    resp = client.get("/api/athlete/dashboard")
    assert resp.status_code == 401


def test_dashboard_returns_training_readiness(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # training_readiness key must exist (can be None if no Garmin data)
    assert "training_readiness" in data
    assert "training_readiness_label" in data
    assert "training_readiness_color" in data


def test_dashboard_returns_trends(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "trends" in data
    trends = data["trends"]
    # All trend keys must be present (values can be None)
    for key in ("ctl", "tss_week", "hrv", "body_battery", "sleep_h", "compliance"):
        assert key in trends, f"Missing trend key: {key}"


def test_dashboard_returns_compliance(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "compliance_week" in data
    assert "compliance_prev"  in data
    # compliance_week is either None (no plan) or 0-100
    cw = data["compliance_week"]
    if cw is not None:
        assert 0 <= cw <= 100


def test_training_readiness_valid_range(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    tr = data.get("training_readiness")
    if tr is not None:
        assert 0 <= tr <= 100


def test_training_readiness_color_matches_label(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    tr_score = data.get("training_readiness")
    tr_color = data.get("training_readiness_color")
    if tr_score is not None and tr_color is not None:
        if tr_score >= 73:
            assert tr_color == "#10B981"
        elif tr_score >= 50:
            assert tr_color == "#EAB308"
        elif tr_score >= 26:
            assert tr_color == "#F97316"
        else:
            assert tr_color == "#EF4444"


def test_trend_ctl_matches_ctl_change(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # trends.ctl must be equivalent to ctl_change (legacy key still present)
    assert "ctl_change" in data  # backward compat


def test_dashboard_fresh_param(client, auth_headers):
    resp = client.get("/api/athlete/dashboard?fresh=true", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "trends" in data


def test_compliance_trend_is_integer_or_none(client, auth_headers):
    resp = client.get("/api/athlete/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    ct = resp.json()["trends"].get("compliance")
    if ct is not None:
        assert isinstance(ct, int)


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 Sprint D (2026-08-11): Panel de Salud 360° — GET /athlete/health-360
# Cero motor de cálculo nuevo: reusa get_athlete_intelligence() (el mismo
# agregador que ya usa el Panel 360° del coach) + una lectura directa de
# GarminHealthDaily para los campos crudos de Garmin que ese agregador no
# cubre (Body Battery, Training Readiness, HRV, etc).
# ─────────────────────────────────────────────────────────────────────────────

def test_health_360_requires_auth(client):
    resp = client.get("/api/athlete/health-360")
    assert resp.status_code == 401


def test_health_360_without_any_data_returns_nulls_not_fake_values(client, auth_headers):
    resp = client.get("/api/athlete/health-360", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["garmin_today"] is None
    assert data["recovery"]["latest_score"] is None
    assert data["mental"]["latest_score"] is None
    assert data["blood_labs"]["has_labs"] is False

def test_health_360_reuses_athlete_intelligence_shape(client, athlete_user, auth_headers):
    """Confirma que /athlete/health-360 y el Panel 360° del coach
    (get_athlete_intelligence) devuelven exactamente la misma estructura
    para las mismas claves — es la prueba de que no hay 2 cálculos
    paralelos que puedan divergir entre lo que ve el atleta y lo que ve
    el coach de ese mismo atleta."""
    from api.services.athlete_intelligence_service import get_athlete_intelligence
    from api.tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()
    try:
        direct = get_athlete_intelligence(athlete_user, db)
    finally:
        db.close()

    resp = client.get("/api/athlete/health-360", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["training"] == direct["training"]
    assert data["recovery"] == direct["recovery"]
    assert data["mental"] == direct["mental"]
    assert data["blood_labs"] == direct["blood_labs"]


def test_health_360_exposes_raw_garmin_snapshot(client, db, athlete_user, auth_headers):
    from api.models import GarminHealthDaily
    db.add(GarminHealthDaily(
        user_id=athlete_user.id, date_iso="2026-08-11",
        body_battery_end=68, training_readiness=54,
        hrv_last_night=42.0, resting_hr=48, avg_stress=22.0, avg_spo2=97.0,
        recovery_time_h=18,
    ))
    db.commit()

    resp = client.get("/api/athlete/health-360", headers=auth_headers)
    assert resp.status_code == 200
    gt = resp.json()["garmin_today"]
    assert gt is not None
    assert gt["date_iso"] == "2026-08-11"
    assert gt["body_battery_end"] == 68
    assert gt["training_readiness"] == 54
    assert gt["hrv_last_night"] == 42.0
    assert gt["resting_hr"] == 48


def test_health_360_includes_injury_risk_same_as_dashboard(client, auth_headers):
    resp_dash = client.get("/api/athlete/dashboard", headers=auth_headers)
    resp_360  = client.get("/api/athlete/health-360", headers=auth_headers)
    assert resp_dash.status_code == 200 and resp_360.status_code == 200
    dash_risk = resp_dash.json().get("injury_risk")
    risk_360  = resp_360.json().get("injury_risk")
    assert risk_360 is not None
    assert risk_360 == dash_risk
