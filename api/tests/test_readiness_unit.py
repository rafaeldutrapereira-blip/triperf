"""
Tests — Daily Athlete Readiness Service (Sprint 23)
=====================================================
Tests unitarios puros: sin DB, sin FastAPI, sin conftest.

Correr: pytest api/tests/test_readiness_unit.py -v --noconftest
"""
import sys
import pathlib
import math
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.services.readiness_service import (
    compute_daily_readiness,
    compute_readiness_history,
    tsb_to_form_score,
    _drs_metadata,
    _W_RECOVERY, _W_MENTAL, _W_TRS, _W_FORM,
)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: TSB → Form Score conversion
# ─────────────────────────────────────────────────────────────────────────────

class TestTSBToFormScore:
    def test_very_negative_tsb_gives_low_score(self):
        score = tsb_to_form_score(-35)
        assert score == 10.0

    def test_tsb_minus_30_boundary(self):
        score = tsb_to_form_score(-30)
        assert abs(score - 10.0) < 0.5

    def test_tsb_zero_gives_60(self):
        score = tsb_to_form_score(0)
        assert abs(score - 60.0) < 0.5

    def test_tsb_plus_10_gives_80(self):
        score = tsb_to_form_score(10)
        assert abs(score - 80.0) < 0.5

    def test_tsb_plus_25_gives_95(self):
        score = tsb_to_form_score(25)
        assert abs(score - 95.0) < 1.0

    def test_very_positive_tsb_decreases_score(self):
        score_25 = tsb_to_form_score(25)
        score_40 = tsb_to_form_score(40)
        assert score_40 < score_25   # too rested = detraining

    def test_monotonically_increasing_in_range_minus30_to_plus25(self):
        scores = [tsb_to_form_score(t) for t in range(-30, 26)]
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i-1] - 0.1

    def test_score_bounded_0_to_100(self):
        for tsb in [-100, -50, -30, 0, 10, 25, 50, 100]:
            s = tsb_to_form_score(tsb)
            assert 0 <= s <= 100

    def test_moderate_fatigue_tsb_minus_15(self):
        score = tsb_to_form_score(-15)
        # -30→10, 0→60; -15 → midpoint ~35
        assert 30 <= score <= 40


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: DRS metadata labels
# ─────────────────────────────────────────────────────────────────────────────

class TestDRSMetadata:
    def test_drs_90_is_optimo(self):
        label, color, _, _, _ = _drs_metadata(90)
        assert label == "Óptimo"
        assert color == "#10b981"

    def test_drs_72_is_bueno(self):
        label, color, _, _, _ = _drs_metadata(72)
        assert label == "Bueno"

    def test_drs_58_is_moderado(self):
        label, _, _, _, _ = _drs_metadata(58)
        assert label == "Moderado"

    def test_drs_40_is_bajo(self):
        label, _, _, _, _ = _drs_metadata(40)
        assert label == "Bajo"

    def test_drs_20_is_critico(self):
        label, color, _, _, _ = _drs_metadata(20)
        assert label == "Crítico"
        assert color == "#ef4444"

    def test_all_thresholds_coverage(self):
        # Ensure every point has a valid label
        for drs in [0, 34, 35, 54, 55, 69, 70, 84, 85, 100]:
            label, color, emoji, rec, guidance = _drs_metadata(drs)
            assert label
            assert color.startswith("#")
            assert rec
            assert guidance


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: compute_daily_readiness — main function
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeDailyReadiness:
    def test_no_data_returns_neutral_70(self):
        report = compute_daily_readiness()
        assert report.drs == 70
        assert report.data_completeness == 0.0
        assert len(report.computed_from) == 0

    def test_all_100_scores_gives_near_100(self):
        report = compute_daily_readiness(
            recovery_score=100,
            mental_score=100,
            trs=100,
            tsb=25,  # ~95 form score
        )
        assert report.drs >= 90
        assert report.trs_label == "Óptimo" if hasattr(report, 'trs_label') else True

    def test_all_50_scores_gives_around_50(self):
        report = compute_daily_readiness(
            recovery_score=50,
            mental_score=50,
            trs=50,
            tsb=0,   # form score = 60
        )
        # weighted avg: (50×.35 + 50×.25 + 50×.20 + 60×.20) = 52
        assert 40 <= report.drs <= 65

    def test_critical_recovery_drags_drs_down(self):
        report_ok   = compute_daily_readiness(recovery_score=90, mental_score=85, trs=90, tsb=5)
        report_crit = compute_daily_readiness(recovery_score=10, mental_score=85, trs=90, tsb=5)
        assert report_crit.drs < report_ok.drs

    def test_only_recovery_available(self):
        report = compute_daily_readiness(recovery_score=80)
        assert report.drs > 0
        assert report.data_completeness == 0.25
        assert "Recuperación" in report.computed_from

    def test_only_tsb_available(self):
        report = compute_daily_readiness(tsb=10)  # form_score=80
        assert report.drs > 0
        assert "Forma" in report.computed_from

    def test_data_completeness_all_four(self):
        report = compute_daily_readiness(
            recovery_score=80, mental_score=70, trs=85, tsb=5
        )
        assert report.data_completeness == 1.0

    def test_data_completeness_two_of_four(self):
        report = compute_daily_readiness(recovery_score=80, mental_score=70)
        assert abs(report.data_completeness - 0.5) < 0.01

    def test_missing_dims_apply_penalty(self):
        full = compute_daily_readiness(
            recovery_score=80, mental_score=80, trs=80, tsb=5
        )
        partial = compute_daily_readiness(recovery_score=80)
        # partial should be lower due to completeness penalty
        assert partial.drs <= full.drs

    def test_primary_limiter_identified_when_one_dim_low(self):
        report = compute_daily_readiness(
            recovery_score=10,  # very low
            mental_score=80,
            trs=85,
            tsb=10,
        )
        assert report.primary_limiter == "Recuperación"

    def test_no_primary_limiter_when_all_good(self):
        report = compute_daily_readiness(
            recovery_score=80, mental_score=85, trs=90, tsb=10
        )
        assert report.primary_limiter is None

    def test_four_dimensions_always_returned(self):
        report = compute_daily_readiness(recovery_score=70)
        assert len(report.dimensions) == 4

    def test_dimensions_have_correct_weights(self):
        report = compute_daily_readiness(recovery_score=70)
        weights = {d.name: d.weight for d in report.dimensions}
        assert abs(weights["Recuperación"] - _W_RECOVERY) < 0.001
        assert abs(weights["Estado Mental"] - _W_MENTAL) < 0.001
        assert abs(weights["Bioquímica"]   - _W_TRS) < 0.001
        assert abs(weights["Forma"]        - _W_FORM) < 0.001

    def test_weights_sum_to_1(self):
        total = _W_RECOVERY + _W_MENTAL + _W_TRS + _W_FORM
        assert abs(total - 1.0) < 0.001

    def test_drs_bounded_0_to_100(self):
        for rec in [0, 50, 100]:
            for tsb in [-50, 0, 30]:
                report = compute_daily_readiness(recovery_score=rec, tsb=tsb)
                assert 0 <= report.drs <= 100

    def test_has_recommendation_and_guidance(self):
        report = compute_daily_readiness(recovery_score=85, mental_score=80, trs=90, tsb=5)
        assert report.recommendation
        assert report.training_guidance

    def test_critical_drs_has_rest_guidance(self):
        report = compute_daily_readiness(recovery_score=5, mental_score=5, trs=5, tsb=-40)
        assert report.drs < 35
        assert "descanso" in report.training_guidance.lower() or "z1" in report.training_guidance.lower()

    def test_optimal_drs_has_quality_guidance(self):
        report = compute_daily_readiness(recovery_score=95, mental_score=92, trs=98, tsb=15)
        assert report.drs >= 80
        assert "alta intensidad" in report.training_guidance.lower() or "plan" in report.training_guidance.lower()

    def test_warning_in_report_for_no_data(self):
        report = compute_daily_readiness()
        assert len(report.warnings) > 0

    def test_tsb_conversion_affects_form_dimension(self):
        report_good_form = compute_daily_readiness(tsb=15)
        report_bad_form  = compute_daily_readiness(tsb=-30)
        form_good = next(d for d in report_good_form.dimensions if d.name == "Forma")
        form_bad  = next(d for d in report_bad_form.dimensions if d.name == "Forma")
        assert form_good.score > form_bad.score


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: compute_readiness_history
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeReadinessHistory:
    def test_empty_input(self):
        result = compute_readiness_history([])
        assert result == []

    def test_sorted_by_date(self):
        points = [
            {"date_iso": "2026-06-15", "recovery_score": 80, "mental_score": None, "trs": None, "tsb": None},
            {"date_iso": "2026-06-10", "recovery_score": 70, "mental_score": None, "trs": None, "tsb": None},
            {"date_iso": "2026-06-20", "recovery_score": 60, "mental_score": None, "trs": None, "tsb": None},
        ]
        result = compute_readiness_history(points)
        dates = [p.date_iso for p in result]
        assert dates == sorted(dates)

    def test_each_point_has_drs(self):
        points = [
            {"date_iso": f"2026-06-{10+i:02d}", "recovery_score": 70+i*5,
             "mental_score": None, "trs": None, "tsb": None}
            for i in range(5)
        ]
        result = compute_readiness_history(points)
        assert len(result) == 5
        for p in result:
            assert 0 <= p.drs <= 100
            assert p.label in ("Óptimo", "Bueno", "Moderado", "Bajo", "Crítico")

    def test_good_recovery_trend_increasing_drs(self):
        points = [
            {"date_iso": "2026-06-01", "recovery_score": 20, "mental_score": None, "trs": None, "tsb": None},
            {"date_iso": "2026-06-07", "recovery_score": 80, "mental_score": None, "trs": None, "tsb": None},
        ]
        result = compute_readiness_history(points)
        assert result[0].drs < result[1].drs

    def test_no_data_points_give_neutral(self):
        points = [{"date_iso": "2026-06-01", "recovery_score": None, "mental_score": None, "trs": None, "tsb": None}]
        result = compute_readiness_history(points)
        assert result[0].drs == 70

    def test_history_point_has_all_fields(self):
        points = [{"date_iso": "2026-06-01", "recovery_score": 75, "mental_score": 80, "trs": 90, "tsb": 5}]
        result = compute_readiness_history(points)
        p = result[0]
        assert p.date_iso == "2026-06-01"
        assert p.recovery_score == 75
        assert p.mental_score == 80
        assert p.trs == 90
        assert p.form_score is not None
        assert p.color.startswith("#")
