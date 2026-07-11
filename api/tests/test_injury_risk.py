"""
Tests — Injury Risk Prediction Engine (Sprint 5 / B-15)
"""
import pytest
from .conftest import login

from ..services.injury_risk_service import (
    _acwr_risk_score, _hrv_risk_score, _monotony_risk_score,
    _labs_risk_score, _classify, _generate_alerts_and_recs,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: motores individuales
# ─────────────────────────────────────────────────────────────────────────────

class TestAcwrRiskScore:
    def test_optimal_zone_no_risk(self):
        assert _acwr_risk_score(1.0)  == 0.0
        assert _acwr_risk_score(0.8)  == 0.0
        assert _acwr_risk_score(1.3)  == 0.0

    def test_high_acwr_scales_to_100(self):
        assert _acwr_risk_score(1.8) == 100.0
        assert _acwr_risk_score(2.0) == 100.0

    def test_mid_high_interpolates(self):
        score = _acwr_risk_score(1.55)
        assert 40 < score < 60

    def test_detraining_low_risk(self):
        score = _acwr_risk_score(0.5)
        assert 0 < score <= 40

    def test_no_data_returns_base(self):
        assert _acwr_risk_score(None) == 20.0

    def test_score_always_0_to_100(self):
        for v in [0.0, 0.3, 0.8, 1.0, 1.3, 1.5, 1.8, 2.5]:
            s = _acwr_risk_score(v)
            assert 0.0 <= s <= 100.0, f"ACWR {v} → {s} out of range"


class TestHrvRiskScore:
    def test_no_data_base_risk(self):
        assert _hrv_risk_score(None, None) == 15.0
        assert _hrv_risk_score(50, None)   == 15.0

    def test_no_drop_zero_risk(self):
        score = _hrv_risk_score(65, 65)
        assert score == 0.0

    def test_small_drop_low_risk(self):
        score = _hrv_risk_score(62, 65)  # ~4.6% drop
        assert score < 15

    def test_critical_drop_high_risk(self):
        score = _hrv_risk_score(50, 70)   # ~28.5% drop
        assert score >= 70

    def test_8pct_threshold(self):
        # Exactamente 8% → score moderado
        hrv_avg = 60.0
        hrv_today = hrv_avg * 0.92   # 8% drop
        score = _hrv_risk_score(hrv_today, hrv_avg)
        assert 35 < score < 50

    def test_score_bounded(self):
        assert _hrv_risk_score(10, 100) <= 100.0
        assert _hrv_risk_score(100, 100) >= 0.0


class TestMonotonyRiskScore:
    def test_empty_loads_low_risk(self):
        score, mono, strain = _monotony_risk_score([])
        assert score == 10.0

    def test_too_few_loads(self):
        score, _, _ = _monotony_risk_score([100, 100])
        assert score <= 15.0

    def test_varied_loads_low_monotony(self):
        loads = [20, 100, 40, 120, 30, 90, 60]
        score, mono, _ = _monotony_risk_score(loads)
        assert mono < 2.0
        assert score < 30

    def test_identical_loads_high_monotony(self):
        # σ = 0 con cargas idénticas → monotonía infinita → score alto
        loads = [80, 80, 80, 80, 80, 80, 80]
        score, mono, strain = _monotony_risk_score(loads)
        # mono → ∞ pero score debe ser 100
        assert score >= 80.0

    def test_high_monotony_is_risky(self):
        # Cargas muy similares → monotonía alta
        loads = [95, 98, 97, 96, 99, 95, 97]
        score, mono, _ = _monotony_risk_score(loads)
        assert mono > 2.0
        assert score > 40


class TestLabsRiskScore:
    def test_empty_labs_no_risk(self):
        assert _labs_risk_score({}) == 0.0
        assert _labs_risk_score(None) == 0.0

    def test_low_ferritin_high_risk(self):
        score = _labs_risk_score({"ferritin": 10})
        assert score >= 40

    def test_borderline_ferritin_moderate(self):
        score = _labs_risk_score({"ferritin": 40})
        assert 5 <= score <= 20

    def test_optimal_ferritin_no_risk(self):
        score = _labs_risk_score({"ferritin": 90})
        assert score == 0.0

    def test_high_cortisol_adds_risk(self):
        score = _labs_risk_score({"cortisol": 30})
        assert score >= 25

    def test_multiple_bad_markers_accumulate(self):
        single = _labs_risk_score({"ferritin": 15})
        multi  = _labs_risk_score({"ferritin": 15, "cortisol": 28, "hb": 12.5})
        assert multi > single

    def test_capped_at_100(self):
        score = _labs_risk_score({
            "ferritin": 5, "cortisol": 35, "hb": 10, "ck": 2000, "urea": 9
        })
        assert score <= 100.0


class TestClassify:
    def test_low_level(self):
        assert _classify(0)[0]  == "low"
        assert _classify(29)[0] == "low"

    def test_moderate_level(self):
        assert _classify(30)[0] == "moderate"
        assert _classify(54)[0] == "moderate"

    def test_high_level(self):
        assert _classify(55)[0] == "high"
        assert _classify(74)[0] == "high"

    def test_critical_level(self):
        assert _classify(75)[0]  == "critical"
        assert _classify(100)[0] == "critical"

    def test_returns_color(self):
        _, color = _classify(80)
        assert color.startswith("#")
        assert len(color) == 7


class TestAlertsAndRecs:
    def test_high_acwr_generates_alert(self):
        alerts, recs = _generate_alerts_and_recs(
            acwr=1.6, hrv_drop_pct=2, monotony=1.2, strain=500,
            labs={}, risk_score=65, risk_level="high", tsb=-5
        )
        assert any(a["factor"] == "ACWR" for a in alerts)
        assert len(recs) > 0

    def test_critical_hrv_drop_generates_alert(self):
        alerts, recs = _generate_alerts_and_recs(
            acwr=1.0, hrv_drop_pct=20, monotony=1.5, strain=400,
            labs={}, risk_score=70, risk_level="high", tsb=0
        )
        assert any(a["factor"] == "HRV" for a in alerts)

    def test_low_ferritin_generates_alert(self):
        alerts, _ = _generate_alerts_and_recs(
            acwr=1.0, hrv_drop_pct=3, monotony=1.2, strain=300,
            labs={"ferritin": 15}, risk_score=40, risk_level="moderate", tsb=5
        )
        assert any(a["factor"] == "LABS" for a in alerts)

    def test_low_risk_gets_positive_rec(self):
        _, recs = _generate_alerts_and_recs(
            acwr=1.0, hrv_drop_pct=2, monotony=1.0, strain=200,
            labs={}, risk_score=10, risk_level="low", tsb=8
        )
        assert any("✓" in r or "Carga" in r for r in recs)

    def test_critical_risk_gets_warning_rec(self):
        _, recs = _generate_alerts_and_recs(
            acwr=1.9, hrv_drop_pct=25, monotony=3.0, strain=6000,
            labs={"ferritin": 10, "cortisol": 32},
            risk_score=90, risk_level="critical", tsb=-30
        )
        assert len(recs) >= 1
        assert any("CRÍTICO" in r or "Descansa" in r for r in recs)


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_risk_today_structure(client, auth_headers):
    resp = client.get("/api/injury/risk/today", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_score"  in data
    assert "risk_level"  in data
    assert "risk_color"  in data
    assert "factors"     in data
    assert "alerts"      in data
    assert "recommendations" in data
    assert 0 <= data["risk_score"] <= 100
    assert data["risk_level"] in ("low", "moderate", "high", "critical")


def test_risk_factors_all_present(client, auth_headers):
    resp = client.get("/api/injury/risk/today", headers=auth_headers)
    data = resp.json()
    factors = data["factors"]
    for key in ["acwr", "hrv", "monotony", "labs"]:
        assert key in factors, f"Factor '{key}' missing"
        assert "score" in factors[key]
        assert 0 <= (factors[key]["score"] or 0) <= 100


def test_risk_history_returns_list(client, auth_headers):
    resp = client.get("/api/injury/risk/history?days=14", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for item in data:
        assert "date_iso" in item
        assert "score"    in item
        assert "level"    in item


def test_risk_history_respects_days_param(client, auth_headers):
    r7  = client.get("/api/injury/risk/history?days=7",  headers=auth_headers)
    r30 = client.get("/api/injury/risk/history?days=30", headers=auth_headers)
    assert r7.status_code  == 200
    assert r30.status_code == 200
    assert len(r30.json()) >= len(r7.json())


def test_risk_date_specific(client, auth_headers):
    resp = client.get("/api/injury/risk/2026-01-15", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["date_iso"] == "2026-01-15"


def test_risk_invalid_date(client, auth_headers):
    resp = client.get("/api/injury/risk/not-a-date", headers=auth_headers)
    assert resp.status_code == 422


def test_risk_recalculate(client, auth_headers):
    resp = client.post("/api/injury/risk/recalculate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_score" in data
    assert "risk_level" in data


def test_risk_requires_auth(client):
    resp = client.get("/api/injury/risk/today")
    assert resp.status_code == 401


def test_risk_score_consistency(client, auth_headers):
    """El score debe ser consistente entre llamadas consecutivas el mismo día."""
    r1 = client.get("/api/injury/risk/today", headers=auth_headers).json()
    r2 = client.get("/api/injury/risk/today", headers=auth_headers).json()
    assert r1["risk_score"] == r2["risk_score"]
    assert r1["risk_level"] == r2["risk_level"]
