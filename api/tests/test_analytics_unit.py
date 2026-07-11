"""
Tests — Performance Analytics Service: Sprint 25 additions
============================================================
Unitarios puros para las 4 funciones nuevas:
  project_ctl_tsb, compute_ramp_rate_risk, compute_season_summary,
  generate_automated_insights, _tsb_form_label

Patrón: se inyectan objetos mock que replican la interfaz SQLAlchemy
sin levantar una DB real.

Correr: pytest api/tests/test_analytics_unit.py -v --noconftest
"""
import sys
import pathlib
import math
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.services.performance_analytics_service import (
    _tsb_form_label,
    _CTL_DECAY,
    _ATL_DECAY,
    _CTL_TAU,
    _ATL_TAU,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers: mock DB builder
# ─────────────────────────────────────────────────────────────────────────────

def _mock_tl(ctl=60.0, atl=65.0, tsb=None, tss_day=70.0, date_iso=None):
    """Build a mock GarminTrainingLoad-like object."""
    obj = MagicMock()
    obj.ctl     = ctl
    obj.atl     = atl
    obj.tsb     = tsb if tsb is not None else (ctl - atl)
    obj.tss_day = tss_day
    obj.date_iso = date_iso or date.today().isoformat()
    return obj


def _mock_db_with_loads(loads):
    """Return a mock DB session whose GarminTrainingLoad queries return `loads`."""
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = loads
    q.first.return_value = loads[0] if loads else None
    return db


# ─────────────────────────────────────────────────────────────────────────────
# § 1. _tsb_form_label
# ─────────────────────────────────────────────────────────────────────────────

class TestTsbFormLabel:
    def test_peak_form(self):
        assert _tsb_form_label(20)  == "Forma Pico"
        assert _tsb_form_label(100) == "Forma Pico"

    def test_good_form(self):
        assert _tsb_form_label(10) == "Buena Forma"
        assert _tsb_form_label(5)  == "Buena Forma"

    def test_neutral(self):
        assert _tsb_form_label(0)  == "Neutro"
        assert _tsb_form_label(-4) == "Neutro"

    def test_moderate_fatigue(self):
        assert _tsb_form_label(-10) == "Fatiga Moderada"

    def test_high_fatigue(self):
        assert _tsb_form_label(-20) == "Fatiga Alta"

    def test_overload(self):
        assert _tsb_form_label(-30) == "Sobrecarga"
        assert _tsb_form_label(-100)== "Sobrecarga"

    def test_boundary_at_15(self):
        assert _tsb_form_label(15) == "Forma Pico"
        assert _tsb_form_label(14) == "Buena Forma"

    def test_boundary_at_minus_25(self):
        assert _tsb_form_label(-25) == "Fatiga Alta"
        assert _tsb_form_label(-26) == "Sobrecarga"


# ─────────────────────────────────────────────────────────────────────────────
# § 2. Banister model constants
# ─────────────────────────────────────────────────────────────────────────────

class TestBanisterModelConstants:
    def test_ctl_tau_is_42(self):
        assert _CTL_TAU == 42

    def test_atl_tau_is_7(self):
        assert _ATL_TAU == 7

    def test_ctl_decay_correct(self):
        expected = 1 - math.exp(-1 / 42)
        assert abs(_CTL_DECAY - expected) < 1e-10

    def test_atl_decay_correct(self):
        expected = 1 - math.exp(-1 / 7)
        assert abs(_ATL_DECAY - expected) < 1e-10

    def test_atl_decay_faster_than_ctl(self):
        assert _ATL_DECAY > _CTL_DECAY

    def test_ctl_decay_between_0_and_1(self):
        assert 0 < _CTL_DECAY < 1

    def test_atl_decay_between_0_and_1(self):
        assert 0 < _ATL_DECAY < 1


# ─────────────────────────────────────────────────────────────────────────────
# § 3. project_ctl_tsb — integration tests via mock DB
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectCtlTsb:
    def _run(self, ctl=60.0, atl=70.0, planned_tss=60.0, days=14):
        from api.services.performance_analytics_service import project_ctl_tsb
        load = _mock_tl(ctl=ctl, atl=atl)
        db   = _mock_db_with_loads([load])
        return project_ctl_tsb("u1", db, planned_tss=planned_tss, days=days)

    def test_projection_has_correct_number_of_days(self):
        result = self._run(days=14)
        assert len(result["projection"]) == 14

    def test_zero_tss_ctl_decays(self):
        # With 0 TSS, CTL must decrease each day
        result = self._run(planned_tss=0.0, days=7)
        proj = result["projection"]
        assert proj[-1]["ctl"] < proj[0]["ctl"]

    def test_high_tss_ctl_increases(self):
        # With very high TSS (200), CTL must increase
        result = self._run(ctl=60.0, atl=60.0, planned_tss=200.0, days=14)
        proj = result["projection"]
        assert proj[-1]["ctl"] > proj[0]["ctl"]

    def test_atl_increases_faster_than_ctl_with_high_tss(self):
        result = self._run(ctl=60.0, atl=60.0, planned_tss=200.0, days=7)
        proj = result["projection"]
        ctl_delta = proj[-1]["ctl"] - proj[0]["ctl"]
        atl_delta = proj[-1]["atl"] - proj[0]["atl"]
        assert atl_delta > ctl_delta

    def test_tsb_equals_ctl_minus_atl(self):
        result = self._run()
        for p in result["projection"]:
            expected_tsb = round(p["ctl"] - p["atl"], 1)
            assert abs(p["tsb"] - expected_tsb) < 0.05

    def test_peak_form_day_has_highest_tsb(self):
        result = self._run(planned_tss=0.0, days=28)  # 0 TSS → TSB rises as ATL drops faster
        peak   = result["peak_form_window"]
        if peak:
            max_tsb = max(p["tsb"] for p in result["projection"])
            assert abs(peak["tsb"] - max_tsb) < 1.0

    def test_returns_current_ctl_atl_tsb(self):
        result = self._run(ctl=65.0, atl=72.0)
        assert result["current_ctl"] == 65.0
        assert result["current_atl"] == 72.0

    def test_no_loads_uses_fallback_defaults(self):
        from api.services.performance_analytics_service import project_ctl_tsb
        db = _mock_db_with_loads([])
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        result = project_ctl_tsb("u1", db, planned_tss=60.0, days=7)
        assert result["current_ctl"] == 40.0
        assert len(result["projection"]) == 7

    def test_form_labels_present(self):
        result = self._run()
        for p in result["projection"]:
            assert p["form_label"] in (
                "Forma Pico", "Buena Forma", "Neutro",
                "Fatiga Moderada", "Fatiga Alta", "Sobrecarga"
            )

    def test_day_offsets_sequential(self):
        result = self._run(days=10)
        offsets = [p["day_offset"] for p in result["projection"]]
        assert offsets == list(range(1, 11))


# ─────────────────────────────────────────────────────────────────────────────
# § 4. compute_ramp_rate_risk — ACWR logic (pure calculation tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestRampRateAcwr:
    """Test ACWR thresholds and risk levels using the compute_ramp_rate_risk function
    via mocked DB with controlled tss_day values."""

    def _make_loads_with_tss(self, acute_tss_per_day: float, chronic_tss_per_day: float):
        """Create 35 mock load objects: last 7 days with acute_tss, days 8-35 with chronic_tss."""
        today = date.today()
        loads = []
        for i in range(35, 0, -1):
            d = today - timedelta(days=i)
            tss = acute_tss_per_day if i <= 7 else chronic_tss_per_day
            obj = MagicMock()
            obj.date_iso = d.isoformat()
            obj.tss_day  = tss
            obj.ctl      = 60.0
            obj.atl      = 65.0
            loads.append(obj)
        return loads

    def _run_ramp(self, acute, chronic):
        from api.services.performance_analytics_service import compute_ramp_rate_risk
        loads = self._make_loads_with_tss(acute, chronic)
        db    = _mock_db_with_loads(loads)
        return compute_ramp_rate_risk("u1", db)

    def test_safe_zone_acwr_between_08_13(self):
        result = self._run_ramp(acute=70, chronic=70)  # ratio = 1.0
        assert result["risk_level"] == "Seguro"

    def test_elevated_risk_acwr_above_15(self):
        result = self._run_ramp(acute=150, chronic=70)  # ratio ≈ 2.14
        assert result["risk_level"] == "Elevado"

    def test_underdload_acwr_below_08(self):
        result = self._run_ramp(acute=30, chronic=80)   # ratio ≈ 0.375
        assert result["risk_level"] == "Bajo (infracarga)"

    def test_moderate_risk_acwr_between_13_15(self):
        result = self._run_ramp(acute=105, chronic=70)  # ratio = 1.5
        assert result["risk_level"] in ("Moderado", "Elevado")

    def test_acwr_is_float(self):
        result = self._run_ramp(acute=70, chronic=70)
        assert isinstance(result["acwr"], float)

    def test_week_trend_has_7_days(self):
        result = self._run_ramp(acute=70, chronic=70)
        assert len(result["week_trend"]) == 7

    def test_risk_color_is_hex(self):
        result = self._run_ramp(acute=70, chronic=70)
        assert result["risk_color"].startswith("#")

    def test_risk_action_is_non_empty(self):
        for acute, chronic in [(30, 80), (70, 70), (120, 80), (200, 70)]:
            result = self._run_ramp(acute=acute, chronic=chronic)
            assert len(result["risk_action"]) > 10

    def test_zero_chronic_doesnt_crash(self):
        from api.services.performance_analytics_service import compute_ramp_rate_risk
        loads = self._make_loads_with_tss(0, 0)
        db    = _mock_db_with_loads(loads)
        result = compute_ramp_rate_risk("u1", db)
        assert "acwr" in result

    def test_generated_at_is_today(self):
        result = self._run_ramp(70, 70)
        assert result["generated_at"] == date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# § 5. compute_season_summary — aggregate logic
# ─────────────────────────────────────────────────────────────────────────────

def _mock_activity(sport="run", dist_km=10.0, dur_min=60.0, tss=80.0, elev=200.0,
                   date_iso=None):
    obj = MagicMock()
    obj.sport           = sport
    obj.dist_km         = dist_km
    obj.dur_min         = dur_min
    obj.tss             = tss
    obj.elevation_gain_m = elev
    obj.date_iso        = date_iso or "2026-06-01"
    return obj


class TestSeasonSummary:
    def _build_db(self, activities, loads=None):
        db = MagicMock()
        # Need to handle TWO different query calls: GarminActivity and GarminTrainingLoad
        mock_query_act  = MagicMock()
        mock_query_tl   = MagicMock()

        mock_query_act.filter.return_value  = mock_query_act
        mock_query_act.order_by.return_value = mock_query_act
        mock_query_act.all.return_value = activities

        mock_query_tl.filter.return_value  = mock_query_tl
        mock_query_tl.order_by.return_value = mock_query_tl
        mock_query_tl.all.return_value = loads or []

        # Route queries by the first positional argument (the model class)
        import api.models as models
        def _query_router(model):
            if model is models.GarminActivity:
                return mock_query_act
            return mock_query_tl

        db.query.side_effect = _query_router
        return db

    def _run(self, activities, loads=None, year=0):
        from api.services.performance_analytics_service import compute_season_summary
        db = self._build_db(activities, loads)
        return compute_season_summary("u1", db, season_year=year)

    def test_empty_season(self):
        result = self._run([])
        assert result["total_activities"] == 0
        assert result["total_km"] == 0.0

    def test_total_km_sums_correctly(self):
        acts = [_mock_activity(dist_km=10) for _ in range(5)]
        result = self._run(acts)
        assert result["total_km"] == 50.0

    def test_total_hours_sums_correctly(self):
        acts = [_mock_activity(dur_min=60) for _ in range(3)]
        result = self._run(acts)
        assert abs(result["total_hours"] - 3.0) < 0.01

    def test_sport_breakdown_counts(self):
        acts = [
            _mock_activity(sport="run"),
            _mock_activity(sport="run"),
            _mock_activity(sport="bike"),
        ]
        result = self._run(acts)
        assert result["sport_breakdown"]["run"]["count"] == 2
        assert result["sport_breakdown"]["bike"]["count"] == 1

    def test_highlights_longest_session(self):
        acts = [
            _mock_activity(dur_min=60,  sport="run"),
            _mock_activity(dur_min=300, sport="bike"),
        ]
        result = self._run(acts)
        assert result["highlights"]["longest_session"]["sport"] == "bike"

    def test_highlights_hardest_session(self):
        acts = [
            _mock_activity(tss=80,  sport="run"),
            _mock_activity(tss=250, sport="bike"),
        ]
        result = self._run(acts)
        assert result["highlights"]["hardest_session"]["sport"] == "bike"

    def test_consistency_at_least_1_week(self):
        # 4 activities in the same week → consistent_weeks >= 1
        acts = [
            _mock_activity(date_iso="2026-06-01"),
            _mock_activity(date_iso="2026-06-02"),
            _mock_activity(date_iso="2026-06-03"),
            _mock_activity(date_iso="2026-06-04"),
        ]
        result = self._run(acts, year=2026)
        assert result["consistent_weeks"] >= 1

    def test_peak_ctl_from_loads(self):
        loads = [
            _mock_tl(ctl=55.0, date_iso="2026-03-01"),
            _mock_tl(ctl=80.0, date_iso="2026-05-01"),
            _mock_tl(ctl=70.0, date_iso="2026-06-01"),
        ]
        result = self._run([], loads=loads, year=2026)
        assert result["peak_ctl"] == 80.0
        assert result["peak_ctl_date"] == "2026-05-01"

    def test_year_returned_in_response(self):
        result = self._run([], year=2025)
        assert result["year"] == 2025

    def test_total_elevation_sums(self):
        acts = [_mock_activity(elev=500) for _ in range(4)]
        result = self._run(acts)
        assert result["total_elevation_m"] == 2000.0


# ─────────────────────────────────────────────────────────────────────────────
# § 6. generate_automated_insights — rule engine
# ─────────────────────────────────────────────────────────────────────────────

class TestAutomatedInsights:
    def _build_db(self, ctl=60.0, atl=70.0, tsb=None, tss_day=70.0, n_loads=14,
                  recovery_score=None, mental_score=None, ferritin=None):
        """Build a mock DB that responds to multiple model queries."""
        tsb_val = tsb if tsb is not None else (ctl - atl)
        today = date.today()

        loads = []
        for i in range(n_loads, 0, -1):
            obj = _mock_tl(ctl=ctl, atl=atl, tsb=tsb_val, tss_day=tss_day,
                           date_iso=(today - timedelta(days=i)).isoformat())
            loads.append(obj)

        db = MagicMock()

        import api.models as models

        def _build_query_chain(return_val):
            q = MagicMock()
            q.filter.return_value  = q
            q.order_by.return_value = q
            q.all.return_value     = return_val if isinstance(return_val, list) else [return_val]
            q.first.return_value   = return_val[0] if isinstance(return_val, list) and return_val else return_val
            return q

        def _query_router(model):
            if model is models.GarminTrainingLoad:
                return _build_query_chain(loads)
            try:
                if model.__name__ == "RecoveryScore" and recovery_score is not None:
                    r = MagicMock()
                    r.score = recovery_score
                    r.date_iso = today.isoformat()
                    return _build_query_chain([r])
                if model.__name__ == "MentalFatigueScore" and mental_score is not None:
                    m = MagicMock()
                    m.score = mental_score
                    m.date_iso = today.isoformat()
                    return _build_query_chain([m])
                if model.__name__ == "BloodLabExam":
                    if ferritin is not None:
                        import json as _json
                        exam = MagicMock()
                        exam.date_iso    = (today - timedelta(days=30)).isoformat()
                        exam.values_json = _json.dumps({"ferritin": ferritin})
                        return _build_query_chain(exam)
                    else:
                        q = MagicMock()
                        q.filter.return_value  = q
                        q.order_by.return_value = q
                        q.all.return_value     = []
                        q.first.return_value   = None
                        return q
            except AttributeError:
                pass
            q = MagicMock()
            q.filter.return_value  = q
            q.order_by.return_value = q
            q.all.return_value     = []
            q.first.return_value   = None
            return q

        db.query.side_effect = _query_router
        return db

    def _run(self, **kwargs):
        from api.services.performance_analytics_service import generate_automated_insights
        db = self._build_db(**kwargs)
        return generate_automated_insights("u1", db)

    def test_result_has_required_keys(self):
        result = self._run()
        assert "insights"       in result
        assert "total_insights" in result
        assert "critical_count" in result
        assert "warning_count"  in result
        assert "info_count"     in result
        assert "generated_at"   in result

    def test_high_negative_tsb_triggers_fatigue_warning(self):
        result = self._run(ctl=80, atl=110, tsb=-30)
        severities = [i["severity"] for i in result["insights"]]
        assert "warning" in severities or "critical" in severities

    def test_very_negative_tsb_triggers_critical(self):
        result = self._run(ctl=80, atl=115, tsb=-35)
        categories = [i["category"] for i in result["insights"]]
        assert "risk" in categories

    def test_high_positive_tsb_triggers_detraining_info(self):
        result = self._run(ctl=70, atl=50, tsb=20)
        cats = [i["category"] for i in result["insights"]]
        assert "performance" in cats

    def test_low_tss_with_high_ctl_triggers_insight(self):
        result = self._run(ctl=70, atl=72, tss_day=5)
        bodies = " ".join(i["body"] for i in result["insights"]).lower()
        assert "tss" in bodies or "carga" in bodies

    def test_high_ctl_triggers_fitness_info(self):
        result = self._run(ctl=85, atl=88, tsb=-3)
        titles = [i["title"] for i in result["insights"]]
        assert any("CTL" in t or "fitness" in t.lower() for t in titles)

    def test_insights_sorted_critical_first(self):
        result = self._run(ctl=80, atl=115, tsb=-35)
        severities = [i["severity"] for i in result["insights"]]
        _order = {"critical": 0, "warning": 1, "info": 2}
        numeric = [_order[s] for s in severities]
        assert numeric == sorted(numeric)

    def test_each_insight_has_required_fields(self):
        result = self._run()
        for insight in result["insights"]:
            assert "category" in insight
            assert "severity"  in insight
            assert "title"     in insight
            assert "body"      in insight
            assert "action"    in insight

    def test_total_count_matches_list_length(self):
        result = self._run()
        assert result["total_insights"] == len(result["insights"])

    def test_counts_sum_to_total(self):
        result = self._run(ctl=80, atl=115, tsb=-35)
        total = result["critical_count"] + result["warning_count"] + result["info_count"]
        assert total == result["total_insights"]

    def test_no_crash_with_no_loads(self):
        from api.services.performance_analytics_service import generate_automated_insights
        db = self._build_db(n_loads=0)
        # Force empty loads
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        # Should not raise
        result = generate_automated_insights("u1", db)
        assert "insights" in result
