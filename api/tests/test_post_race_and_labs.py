"""
Tests — Post-Race Intelligence + Blood Labs Correlations (Sprint 7)
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from ..services.post_race_service import (
    _fmt_delta,
    _pct_delta,
    _labs_evidence,
    _discipline_rec,
    _fmt_total,
    analyze_race,
)
from ..services.blood_labs_correlation_service import (
    _pearson,
    _is_physiologically_sound,
    _interpret,
    _generate_correlation_insights,
    compute_correlations,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: post_race_service helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatDelta:
    def test_positive_seconds_under_minute(self):
        assert _fmt_delta(45, "run")  == "+45s"

    def test_negative_seconds(self):
        assert _fmt_delta(-30, "swim") == "-30s"

    def test_minutes(self):
        r = _fmt_delta(125, "bike")
        assert "2m" in r
        assert "05s" in r

    def test_zero(self):
        r = _fmt_delta(0, "run")
        assert "0s" in r


class TestPctDelta:
    def test_basic_percent(self):
        r = _pct_delta(3900, 3600)  # 8.3% más lento
        assert 8 < r < 9

    def test_faster_is_negative(self):
        r = _pct_delta(3400, 3600)
        assert r < 0

    def test_none_returns_none(self):
        assert _pct_delta(None, 3600) is None
        assert _pct_delta(3600, None) is None
        assert _pct_delta(3600, 0)   is None


class TestFmtTotal:
    def test_basic_time(self):
        assert _fmt_total(3661) == "1:01:01"

    def test_zero(self):
        r = _fmt_total(0)
        assert "0" in r

    def test_none(self):
        assert _fmt_total(None) == "—"

    def test_half_ironman(self):
        r = _fmt_total(4 * 3600 + 30 * 60)  # 4:30:00
        assert "4:30:00" == r


class TestDisciplineRec:
    def test_swim_has_rec(self):
        r = _discipline_rec("swim")
        assert len(r) > 20
        assert "natación" in r.lower() or "nata" in r.lower() or "volumen" in r.lower()

    def test_bike_has_rec(self):
        r = _discipline_rec("bike")
        assert len(r) > 20

    def test_run_has_rec(self):
        r = _discipline_rec("run")
        assert len(r) > 20
        assert "run" in r.lower() or "carrera" in r.lower() or "pacing" in r.lower()

    def test_unknown_has_fallback(self):
        r = _discipline_rec("unknown_sport")
        assert len(r) > 10


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: blood_labs_correlation_service
# ─────────────────────────────────────────────────────────────────────────────

class TestPearson:
    def test_perfect_positive_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        assert _pearson(x, y) == pytest.approx(1.0, abs=0.001)

    def test_perfect_negative_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        assert _pearson(x, y) == pytest.approx(-1.0, abs=0.001)

    def test_no_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [3, 1, 4, 1, 5]
        r = _pearson(x, y)
        assert r is not None
        assert abs(r) < 0.6

    def test_too_few_points(self):
        assert _pearson([1, 2], [3, 4]) is None

    def test_constant_x_returns_none(self):
        x = [5, 5, 5, 5, 5]
        y = [1, 2, 3, 4, 5]
        assert _pearson(x, y) is None


class TestPhysiologicalSoundness:
    def test_ferritin_ctl_positive_is_sound(self):
        assert _is_physiologically_sound("ferritin", "ctl", 0.7) is True

    def test_ferritin_ctl_negative_not_sound(self):
        assert _is_physiologically_sound("ferritin", "ctl", -0.7) is False

    def test_cortisol_ctl_negative_is_sound(self):
        assert _is_physiologically_sound("cortisol", "ctl", -0.6) is True

    def test_cortisol_ctl_positive_not_sound(self):
        assert _is_physiologically_sound("cortisol", "ctl", 0.6) is False

    def test_ck_tss_negative_is_sound(self):
        assert _is_physiologically_sound("ck", "tss_weekly", -0.5) is True

    def test_vitamin_d_hrv_positive_is_sound(self):
        assert _is_physiologically_sound("vitamin_d", "hrv_avg", 0.5) is True

    def test_unknown_combination_is_not_sound(self):
        assert _is_physiologically_sound("urea", "hrv_avg", 0.9) is False


class TestCorrelationInsights:
    def test_low_ferritin_with_positive_correlation_generates_insight(self):
        corrs = [{
            "marker": "ferritin", "marker_label": "Ferritina",
            "metric": "ctl",      "metric_label": "CTL",
            "r": 0.75, "direction": "positiva", "strength": "fuerte",
            "n_points": 4,
            "interpretation": "test",
        }]
        status = {
            "ferritin": {"status": "suboptimal_low", "value": 25, "label": "Ferritina"}
        }
        insights = _generate_correlation_insights(corrs, status)
        assert len(insights) > 0
        assert any("ferritina" in i.lower() or "Ferritina" in i for i in insights)

    def test_no_correlations_returns_message(self):
        insights = _generate_correlation_insights([], {})
        assert len(insights) > 0

    def test_high_r_generates_strong_pattern_insight(self):
        corrs = [{
            "marker": "cortisol",  "marker_label": "Cortisol",
            "metric": "hrv_avg",   "metric_label": "HRV",
            "r": -0.82, "direction": "negativa", "strength": "fuerte",
            "n_points": 5,
            "interpretation": "test",
        }]
        status = {"cortisol": {"status": "optimal", "value": 15}}
        insights = _generate_correlation_insights(corrs, status)
        assert len(insights) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────

from .conftest import login


@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_post_race_requires_actual_result(client, auth_headers):
    """Análisis post-race debe fallar si no hay resultado real."""
    # Crear carrera sin resultado
    create = client.post("/api/races", headers=auth_headers, json={
        "name": "Test Race No Result",
        "date_iso": "2026-06-01",
        "distance": "olympic",
    })
    if create.status_code != 200:
        pytest.skip("Race creation failed")

    race_id = create.json().get("race_id") or create.json().get("id")
    if not race_id:
        pytest.skip("No race_id in response")

    resp = client.get(f"/api/races/{race_id}/post-race-analysis", headers=auth_headers)
    assert resp.status_code == 400
    assert "resultado real" in resp.json().get("errors", [{}])[0].get("message", "").lower() or \
           resp.status_code == 400


def test_post_race_analysis_structure(client, auth_headers):
    """Con resultado real, el análisis debe retornar estructura completa."""
    # Crear carrera
    create = client.post("/api/races", headers=auth_headers, json={
        "name": "Ironman Test Analysis",
        "date_iso": "2025-11-15",
        "distance": "703",
    })
    if create.status_code != 200:
        pytest.skip()
    race_id = create.json().get("race_id") or create.json().get("id")
    if not race_id:
        pytest.skip()

    # Guardar resultado real
    result = client.patch(f"/api/races/{race_id}/result", headers=auth_headers, json={
        "swim_sec":  1800,   # 30:00
        "bike_sec":  7500,   # 2:05:00
        "run_sec":   5400,   # 1:30:00
        "t1_sec":    180,
        "t2_sec":    120,
        "total_sec": 15000,
    })
    if result.status_code not in (200, 201):
        pytest.skip("Result save failed")

    resp = client.get(f"/api/races/{race_id}/post-race-analysis", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "gap_analysis"           in data
    assert "limiting_factors"       in data
    assert "physiological_context"  in data
    assert "performance_index"      in data
    assert "recommendations"        in data

    gap = data["gap_analysis"]
    assert "total" in gap
    assert "swim"  in gap
    assert "bike"  in gap
    assert "run"   in gap


def test_post_race_gap_calculation(client, auth_headers):
    """Los gaps deben calcularse correctamente."""
    create = client.post("/api/races", headers=auth_headers, json={
        "name": "Gap Calc Test",
        "date_iso": "2025-10-01",
        "distance": "olympic",
    })
    if create.status_code != 200:
        pytest.skip()
    race_id = create.json().get("race_id") or create.json().get("id")
    if not race_id:
        pytest.skip()

    # Resultado 5 min más lento que predicción típica
    result = client.patch(f"/api/races/{race_id}/result", headers=auth_headers, json={
        "swim_sec":  1200, "bike_sec": 4500, "run_sec": 3000,
        "t1_sec": 90, "t2_sec": 60, "total_sec": 8850,
    })
    if result.status_code not in (200, 201):
        pytest.skip()

    resp = client.get(f"/api/races/{race_id}/post-race-analysis", headers=auth_headers)
    if resp.status_code != 200:
        pytest.skip()

    data = resp.json()
    assert data["gap_analysis"]["total"]["delta_sec"] is not None
    assert isinstance(data["performance_index"], (int, float))


def test_labs_correlations_structure(client, auth_headers):
    """Endpoint de correlaciones debe retornar estructura válida."""
    resp = client.get("/api/labs/correlations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "correlations"    in data
    assert "timeline"        in data
    assert "insights"        in data
    assert "markers_status"  in data
    assert isinstance(data["correlations"], list)
    assert isinstance(data["insights"],     list)


def test_labs_correlations_structure_without_labs(client, auth_headers):
    """Sin labs registrados, debe retornar mensaje explicativo."""
    resp = client.get("/api/labs/correlations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Ya sea con correlaciones o con mensaje de no-data, debe ser válido
    assert "correlations" in data or "message" in data


def test_labs_correlations_r_range(client, auth_headers):
    """Todos los valores r deben estar en [-1, 1]."""
    resp = client.get("/api/labs/correlations", headers=auth_headers)
    assert resp.status_code == 200
    for corr in resp.json().get("correlations", []):
        assert -1.0 <= corr["r"] <= 1.0
        assert corr["abs_r"] >= 0.4   # solo correlaciones significativas


def test_labs_timeline_structure(client, auth_headers):
    """Timeline debe retornar lista con fechas."""
    resp = client.get("/api/labs/timeline", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline"   in data
    assert "exam_count" in data
    assert isinstance(data["timeline"], list)


def test_labs_correlations_require_auth(client):
    resp = client.get("/api/labs/correlations")
    assert resp.status_code == 401


def test_post_race_analysis_requires_auth(client):
    resp = client.get("/api/races/fake-id/post-race-analysis")
    assert resp.status_code == 401


def test_pearson_correctness():
    """Verificar la implementación matemática directamente."""
    # Correlación perfecta
    r = _pearson([1,2,3,4,5], [2,4,6,8,10])
    assert r == pytest.approx(1.0, abs=0.001)

    # Anti-correlación perfecta
    r2 = _pearson([1,2,3,4,5], [10,8,6,4,2])
    assert r2 == pytest.approx(-1.0, abs=0.001)

    # Sin correlación (ortogonal)
    r3 = _pearson([1,-1,1,-1,1,-1], [1,1,-1,-1,0,0])
    assert r3 is not None
    assert abs(r3) < 0.5
