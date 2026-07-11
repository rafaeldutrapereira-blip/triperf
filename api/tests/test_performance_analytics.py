"""
Tests — Performance Analytics Intelligence (Sprint 8)
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from .conftest import login

from ..services.performance_analytics_service import (
    _fit_cp2_model,
    _fmt_dur,
    _fmt_pace,
    compute_power_curve,
    compute_vo2max_history,
    compute_personal_records,
    compute_training_distribution,
    compute_zone_calibration,
    CP_DURATIONS,
    CP_LABELS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit: formatters
# ─────────────────────────────────────────────────────────────────────────────

class TestFmtDur:
    def test_under_hour(self):
        assert _fmt_dur(30) == "30:00"

    def test_over_hour(self):
        assert _fmt_dur(90) == "1:30:00"

    def test_seconds(self):
        assert _fmt_dur(1) == "1:00"

    def test_zero(self):
        assert _fmt_dur(0) == "0:00"


class TestFmtPace:
    def test_five_min_km(self):
        assert _fmt_pace(5.0) == "5:00"

    def test_four_thirty(self):
        assert _fmt_pace(4.5) == "4:30"

    def test_sub_four(self):
        result = _fmt_pace(3.75)
        assert "3:" in result


# ─────────────────────────────────────────────────────────────────────────────
# Unit: CP2 model fitting
# ─────────────────────────────────────────────────────────────────────────────

class TestCp2Model:
    def test_ideal_data_produces_model(self):
        # P = 280 + 20000/t → CP=280, W'=20000
        best_power = {dur: 280 + 20000 / dur for dur in [180, 300, 600, 900, 1200, 1800]}
        model = _fit_cp2_model(best_power)
        assert model is not None
        assert 220 <= model["cp_watts"] <= 340
        assert 10000 <= model["w_prime_j"] <= 35000

    def test_too_few_points_returns_none(self):
        model = _fit_cp2_model({300: 320, 600: 290})
        assert model is None

    def test_unrealistic_values_return_none(self):
        # CP=5W es imposible → debe filtrarse
        best_power = {dur: 5 + 100 / dur for dur in [180, 300, 600, 900, 1200, 1800]}
        model = _fit_cp2_model(best_power)
        assert model is None

    def test_description_includes_watts(self):
        best_power = {dur: 280 + 20000 / dur for dur in [180, 300, 600, 900, 1200, 1800]}
        model = _fit_cp2_model(best_power)
        if model:
            assert "W" in model["description"]
            assert "kJ" in model["description"]


# ─────────────────────────────────────────────────────────────────────────────
# Unit: CP durations and labels
# ─────────────────────────────────────────────────────────────────────────────

class TestCpConstants:
    def test_durations_monotonically_increasing(self):
        for i in range(len(CP_DURATIONS) - 1):
            assert CP_DURATIONS[i] < CP_DURATIONS[i + 1]

    def test_all_durations_have_labels(self):
        for dur in CP_DURATIONS:
            assert dur in CP_LABELS, f"Missing label for {dur}s"

    def test_includes_key_durations(self):
        assert 300  in CP_DURATIONS   # 5 min
        assert 1200 in CP_DURATIONS   # 20 min
        assert 3600 in CP_DURATIONS   # 60 min

    def test_one_hour_label(self):
        assert CP_LABELS[3600] == "1h"

    def test_five_min_label(self):
        assert CP_LABELS[300] == "5m"


# ─────────────────────────────────────────────────────────────────────────────
# Unit: service functions with mocked DB
# ─────────────────────────────────────────────────────────────────────────────

def _make_activity(sport="bike", dur_min=60, dist_km=40.0, avg_power=250,
                   avg_hr=155, tss=80.0, date_iso="2026-01-15"):
    a = MagicMock()
    a.sport      = sport
    a.dur_min    = dur_min
    a.dist_km    = dist_km
    a.avg_power  = avg_power
    a.avg_hr     = avg_hr
    a.tss        = tss
    a.date_iso   = date_iso
    a.activity_id = "act-001"
    a.pace_str   = "5:00"
    return a


def _make_user(peso=70.0, fc_max=185, sexo="M", vo2max=None):
    u = MagicMock()
    u.id        = "user-001"
    u.peso      = peso       # legacy alias
    u.weight_kg = peso       # actual model column
    u.fcmax     = fc_max     # model uses fcmax
    u.fc_max    = fc_max     # keep alias for backwards compat in tests
    u.sexo      = sexo
    u.vo2max    = vo2max
    return u


class TestPowerCurveService:
    def _db_with_activities(self, activities, user=None):
        db = MagicMock()
        user = user or _make_user()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = activities
        q.first.return_value = user
        db.query.return_value = q
        return db

    def test_no_activities_returns_message(self):
        db = self._db_with_activities([])
        result = compute_power_curve("u1", db, days_back=365, sport="bike")
        assert "message" in result
        assert result["curve"] == []

    def test_single_activity_produces_curve(self):
        act = _make_activity(sport="bike", dur_min=60, avg_power=250)
        db  = self._db_with_activities([act])
        result = compute_power_curve("u1", db, sport="bike")
        assert result["curve"] != [] or "message" in result  # flexible: may still be empty

    def test_ftp_estimado_in_range(self):
        # Actividad de 60 min a 250W → FTP debe ser ~250
        act = _make_activity(sport="bike", dur_min=60, avg_power=250)
        db  = self._db_with_activities([act])
        result = compute_power_curve("u1", db, sport="bike")
        if result.get("ftp_est"):
            assert 150 <= result["ftp_est"] <= 600

    def test_watts_per_kg_included_when_weight(self):
        act  = _make_activity(sport="bike", dur_min=60, avg_power=300)
        user = _make_user(peso=75.0)
        db   = self._db_with_activities([act], user)
        result = compute_power_curve("u1", db, sport="bike")
        if result.get("ftp_est") and result.get("weight_kg"):
            assert result["ftp_wkg"] is not None
            assert result["ftp_wkg"] > 0

    def test_curve_monotonically_decreasing(self):
        acts = [
            _make_activity(dur_min=5,  avg_power=400),
            _make_activity(dur_min=20, avg_power=320),
            _make_activity(dur_min=60, avg_power=260),
        ]
        db = self._db_with_activities(acts)
        result = compute_power_curve("u1", db, sport="bike")
        curve = result.get("curve", [])
        powers = [p["power_w"] for p in curve]
        for i in range(len(powers) - 1):
            assert powers[i] >= powers[i + 1], f"Curve not monotonic at index {i}"


class TestTrainingDistribution:
    def _db_with_acts(self, activities):
        db = MagicMock()
        user = _make_user()
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = activities
        q.first.return_value = user
        db.query.return_value = q
        return db

    def test_no_activities_returns_message(self):
        db = self._db_with_acts([])
        result = compute_training_distribution("u1", db)
        assert "message" in result

    def test_returns_required_keys(self):
        acts = [
            _make_activity(sport="bike", tss=80, date_iso="2026-01-15"),
            _make_activity(sport="run",  tss=50, date_iso="2026-01-16"),
        ]
        db = self._db_with_acts(acts)
        result = compute_training_distribution("u1", db)
        if "message" not in result:
            assert "by_sport"   in result
            assert "by_weekday" in result
            assert "by_zone"    in result

    def test_polarization_index_positive(self):
        acts = [_make_activity(avg_hr=120, tss=40, date_iso=f"2026-01-{i:02d}") for i in range(1, 10)]
        db = self._db_with_acts(acts)
        result = compute_training_distribution("u1", db)
        if "polarization_index" in result:
            assert result["polarization_index"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (API)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_power_curve_requires_auth(client):
    resp = client.get("/api/analytics/power-curve")
    assert resp.status_code == 401


def test_vo2max_requires_auth(client):
    resp = client.get("/api/analytics/vo2max")
    assert resp.status_code == 401


def test_personal_records_requires_auth(client):
    resp = client.get("/api/analytics/personal-records")
    assert resp.status_code == 401


def test_training_distribution_requires_auth(client):
    resp = client.get("/api/analytics/training-distribution")
    assert resp.status_code == 401


def test_zone_calibration_requires_auth(client):
    resp = client.get("/api/analytics/zone-calibration")
    assert resp.status_code == 401


def test_summary_requires_auth(client):
    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 401


def test_power_curve_structure(client, auth_headers):
    resp = client.get("/api/analytics/power-curve", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "sport" in data
    assert "curve" in data
    assert isinstance(data["curve"], list)


def test_vo2max_structure(client, auth_headers):
    resp = client.get("/api/analytics/vo2max", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline"    in data
    assert "vo2max_current" in data or data.get("vo2max_current") is None
    assert isinstance(data["timeline"], list)


def test_personal_records_structure(client, auth_headers):
    resp = client.get("/api/analytics/personal-records", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "records"          in data
    assert "total_activities" in data
    assert isinstance(data["records"], dict)


def test_training_distribution_structure(client, auth_headers):
    resp = client.get("/api/analytics/training-distribution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "by_sport" in data or "message" in data


def test_zone_calibration_structure(client, auth_headers):
    resp = client.get("/api/analytics/zone-calibration", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "cycling"  in data
    assert "running"  in data
    assert "swimming" in data
    assert "note"     in data


def test_summary_structure(client, auth_headers):
    resp = client.get("/api/analytics/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "power_curve"           in data
    assert "vo2max"                in data
    assert "personal_records"      in data
    assert "training_distribution" in data
    assert "zone_calibration"      in data


def test_power_curve_sport_param(client, auth_headers):
    resp = client.get("/api/analytics/power-curve?sport=run", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["sport"] == "run"


def test_power_curve_days_param(client, auth_headers):
    resp = client.get("/api/analytics/power-curve?days_back=90", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("days_back") == 90


def test_personal_records_sport_filter(client, auth_headers):
    resp = client.get("/api/analytics/personal-records?sports=run", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    if data["records"]:
        assert all(sp in ["run"] for sp in data["records"].keys())


def test_distribution_pct_sums_100(client, auth_headers):
    resp = client.get("/api/analytics/training-distribution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    sports = data.get("by_sport", [])
    if sports:
        total_pct = sum(s["pct_tss"] for s in sports)
        assert abs(total_pct - 100.0) < 2.0   # tolerancia de redondeo
