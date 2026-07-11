"""
Tests — Nutrition Intelligence Service (Sprint 24)
===================================================
Unitarios puros: sin DB, sin FastAPI, sin conftest.

Correr: pytest api/tests/test_nutrition_unit.py -v --noconftest
"""
import sys
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.services.nutrition_intelligence_service import (
    compute_macro_compliance,
    compute_lab_nutrition_bridge,
    compute_carb_loading_protocol,
    compute_daily_macro_targets,
    _pct_score,
    _race_category,
    MacroCompliance,
    LabNutritionBridgeReport,
    CarbLoadingProtocol,
    DailyMacroTargets,
)


# ─────────────────────────────────────────────────────────────────────────────
# § 1. _pct_score helper
# ─────────────────────────────────────────────────────────────────────────────

class TestPctScoreHelper:
    def test_on_target_gives_1(self):
        assert abs(_pct_score(100, 100) - 1.0) < 0.01

    def test_10_pct_under_still_gives_1_within_tolerance(self):
        # 90/100 = 0.9, tolerance=0.10, boundary = 0.9
        score = _pct_score(90, 100, tolerance=0.10)
        assert 0.99 <= score <= 1.01

    def test_zero_actual_gives_zero(self):
        assert _pct_score(0, 100) == 0.0

    def test_50_pct_below_target_penalized(self):
        score = _pct_score(50, 100)
        assert score < 0.6

    def test_zero_target_returns_1(self):
        assert _pct_score(0, 0) == 1.0

    def test_large_excess_capped_at_06(self):
        score = _pct_score(200, 100)
        assert score >= 0.6


# ─────────────────────────────────────────────────────────────────────────────
# § 2. compute_macro_compliance
# ─────────────────────────────────────────────────────────────────────────────

class TestMacroCompliance:
    def _perfect(self):
        return compute_macro_compliance(
            kcal_target=2500, kcal_actual=2500,
            carbs_target_g=300, carbs_actual_g=300,
            protein_target_g=140, protein_actual_g=140,
            fat_target_g=80, fat_actual_g=80,
            fiber_target_g=30, fiber_actual_g=30,
        )

    def test_perfect_compliance_score_is_100(self):
        c = self._perfect()
        assert c.compliance_score == 100
        assert c.compliance_label == "Óptimo"

    def test_perfect_has_no_gaps_or_excesses(self):
        c = self._perfect()
        assert c.gaps == []
        assert c.excesses == []

    def test_zero_intake_gives_deficiente(self):
        c = compute_macro_compliance(
            kcal_target=2500, kcal_actual=0,
            carbs_target_g=300, carbs_actual_g=0,
            protein_target_g=140, protein_actual_g=0,
            fat_target_g=80, fat_actual_g=0,
        )
        assert c.compliance_score < 30
        assert c.compliance_label == "Deficiente"
        assert len(c.gaps) > 0

    def test_protein_gap_reported(self):
        c = compute_macro_compliance(
            kcal_target=2500, kcal_actual=2500,
            carbs_target_g=300, carbs_actual_g=300,
            protein_target_g=160, protein_actual_g=80,  # 50% shortfall
            fat_target_g=80, fat_actual_g=80,
        )
        assert any("Proteína" in g for g in c.gaps)

    def test_carb_excess_reported(self):
        c = compute_macro_compliance(
            kcal_target=2500, kcal_actual=2500,
            carbs_target_g=200, carbs_actual_g=280,  # 40% excess
            protein_target_g=140, protein_actual_g=140,
            fat_target_g=80, fat_actual_g=80,
        )
        assert any("Carbohidrato" in e for e in c.excesses)

    def test_hydration_ok_true_when_met(self):
        c = compute_macro_compliance(
            kcal_target=2000, kcal_actual=2000,
            carbs_target_g=250, carbs_actual_g=250,
            protein_target_g=130, protein_actual_g=130,
            fat_target_g=70, fat_actual_g=70,
            hydration_ml=2500, hydration_target_ml=2500,
        )
        assert c.hydration_ok is True

    def test_hydration_false_when_below_85_pct(self):
        c = compute_macro_compliance(
            kcal_target=2000, kcal_actual=2000,
            carbs_target_g=250, carbs_actual_g=250,
            protein_target_g=130, protein_actual_g=130,
            fat_target_g=70, fat_actual_g=70,
            hydration_ml=1000, hydration_target_ml=2500,
        )
        assert c.hydration_ok is False

    def test_hydration_none_when_no_data(self):
        c = compute_macro_compliance(
            kcal_target=2000, kcal_actual=2000,
            carbs_target_g=250, carbs_actual_g=250,
            protein_target_g=130, protein_actual_g=130,
            fat_target_g=70, fat_actual_g=70,
        )
        assert c.hydration_ok is None

    def test_score_bounded_0_100(self):
        for actual_mult in [0.0, 0.3, 0.7, 1.0, 1.5, 2.0]:
            c = compute_macro_compliance(
                kcal_target=2500, kcal_actual=2500 * actual_mult,
                carbs_target_g=300, carbs_actual_g=300 * actual_mult,
                protein_target_g=140, protein_actual_g=140 * actual_mult,
                fat_target_g=80, fat_actual_g=80 * actual_mult,
            )
            assert 0 <= c.compliance_score <= 100

    def test_moderate_shortfall_gives_insuficiente_or_bueno(self):
        c = compute_macro_compliance(
            kcal_target=2500, kcal_actual=1800,
            carbs_target_g=300, carbs_actual_g=200,
            protein_target_g=140, protein_actual_g=110,
            fat_target_g=80, fat_actual_g=80,
        )
        assert c.compliance_label in ("Insuficiente", "Bueno", "Deficiente")

    def test_color_is_hex_string(self):
        c = self._perfect()
        assert c.compliance_color.startswith("#")


# ─────────────────────────────────────────────────────────────────────────────
# § 3. _race_category
# ─────────────────────────────────────────────────────────────────────────────

class TestRaceCategory:
    def test_sprint(self):
        assert _race_category("Sprint Triathlon") == "sprint"

    def test_olympic(self):
        assert _race_category("Olímpico") == "olympic"

    def test_half(self):
        assert _race_category("70.3") == "half"

    def test_full_ironman(self):
        assert _race_category("Ironman 140.6") == "full"

    def test_unknown_defaults_to_olympic(self):
        assert _race_category("unknown race") == "olympic"

    def test_case_insensitive_full(self):
        assert _race_category("FULL IRONMAN") == "full"


# ─────────────────────────────────────────────────────────────────────────────
# § 4. compute_lab_nutrition_bridge
# ─────────────────────────────────────────────────────────────────────────────

class TestLabNutritionBridge:
    def _ferritin_warning_marker(self):
        return [{"key": "ferritin", "name": "Ferritina", "status": "warning", "supplement_hint": "Hierro"}]

    def test_no_markers_gives_empty_report(self):
        report = compute_lab_nutrition_bridge([], [])
        assert report.gaps == []
        assert report.covered == []
        assert report.compliance_rate == 1.0
        assert report.alert_count == 0

    def test_gap_when_ferritin_low_no_iron_supplement(self):
        report = compute_lab_nutrition_bridge(
            markers_evaluated=self._ferritin_warning_marker(),
            supplement_logs_last_30d=[],
        )
        assert len(report.gaps) == 1
        assert report.gaps[0].marker_key == "ferritin"
        assert report.gaps[0].is_being_supplemented is False

    def test_covered_when_iron_supplement_logged(self):
        report = compute_lab_nutrition_bridge(
            markers_evaluated=self._ferritin_warning_marker(),
            supplement_logs_last_30d=[
                {"supplement": "hierro", "dose_mg": 18, "date_iso": "2026-06-01"},
                {"supplement": "hierro", "dose_mg": 18, "date_iso": "2026-06-02"},
            ],
        )
        assert len(report.covered) == 1
        assert report.covered[0].is_being_supplemented is True

    def test_compliance_rate_100_when_all_covered(self):
        report = compute_lab_nutrition_bridge(
            markers_evaluated=self._ferritin_warning_marker(),
            supplement_logs_last_30d=[
                {"supplement": "hierro", "dose_mg": 18, "date_iso": "2026-06-01"},
            ],
        )
        assert report.compliance_rate == 1.0

    def test_compliance_rate_0_when_nothing_covered(self):
        report = compute_lab_nutrition_bridge(
            markers_evaluated=self._ferritin_warning_marker(),
            supplement_logs_last_30d=[],
        )
        assert report.compliance_rate == 0.0

    def test_alert_count_only_critical_markers(self):
        markers = [
            {"key": "ferritin", "name": "Ferritina", "status": "critical", "supplement_hint": "Hierro"},
            {"key": "vitamin_d", "name": "Vitamina D", "status": "warning", "supplement_hint": "Vitamina D"},
        ]
        report = compute_lab_nutrition_bridge(markers_evaluated=markers, supplement_logs_last_30d=[])
        assert report.alert_count == 1

    def test_top_action_is_critical_first(self):
        markers = [
            {"key": "ferritin",   "name": "Ferritina", "status": "critical", "supplement_hint": None},
            {"key": "vitamin_d",  "name": "Vitamina D", "status": "warning", "supplement_hint": None},
        ]
        report = compute_lab_nutrition_bridge(markers_evaluated=markers, supplement_logs_last_30d=[])
        assert report.top_action is not None
        assert "ferritin" in report.top_action.lower() or "hierro" in report.top_action.lower()

    def test_cortisol_marker_maps_to_magnesium(self):
        markers = [{"key": "cortisol", "name": "Cortisol", "status": "warning", "supplement_hint": None}]
        report = compute_lab_nutrition_bridge(
            markers_evaluated=markers,
            supplement_logs_last_30d=[{"supplement": "magnesio", "dose_mg": 400, "date_iso": "2026-06-01"}],
        )
        assert len(report.covered) == 1


# ─────────────────────────────────────────────────────────────────────────────
# § 5. compute_carb_loading_protocol
# ─────────────────────────────────────────────────────────────────────────────

class TestCarbLoadingProtocol:
    def test_returns_4_days(self):
        p = compute_carb_loading_protocol("Test Race", "70.3", 70.0)
        assert len(p.days) == 4

    def test_day_offsets_are_minus3_to_0(self):
        p = compute_carb_loading_protocol("Test Race", "Ironman", 75.0)
        offsets = [d.day_offset for d in p.days]
        assert offsets == [-3, -2, -1, 0]

    def test_fullim_has_high_cho_d3(self):
        p = compute_carb_loading_protocol("IM", "full", 70.0)
        d3 = next(d for d in p.days if d.day_offset == -3)
        assert d3.carbs_g_per_kg >= 9.0

    def test_sprint_has_lower_cho_than_full(self):
        p_sprint = compute_carb_loading_protocol("R", "sprint", 70.0)
        p_full   = compute_carb_loading_protocol("R", "full",   70.0)
        cho_sprint = next(d for d in p_sprint.days if d.day_offset == -3).carbs_g
        cho_full   = next(d for d in p_full.days   if d.day_offset == -3).carbs_g
        assert cho_sprint < cho_full

    def test_race_day_has_low_cho(self):
        p = compute_carb_loading_protocol("R", "olympic", 70.0)
        race_day = next(d for d in p.days if d.day_offset == 0)
        assert race_day.carbs_g_per_kg <= 3.0

    def test_all_days_have_positive_kcal(self):
        p = compute_carb_loading_protocol("R", "half", 65.0)
        for d in p.days:
            assert d.kcal_target > 0
            assert d.carbs_g > 0
            assert d.protein_g > 0
            assert d.hydration_ml > 0

    def test_key_rules_non_empty(self):
        p = compute_carb_loading_protocol("R", "full", 80.0)
        assert len(p.key_rules) >= 3

    def test_ctl_boost_increases_cho_for_fit_athlete(self):
        p_unfit = compute_carb_loading_protocol("R", "full", 70.0, ctl=40)
        p_fit   = compute_carb_loading_protocol("R", "full", 70.0, ctl=100)
        cho_unfit = next(d for d in p_unfit.days if d.day_offset == -3).carbs_g
        cho_fit   = next(d for d in p_fit.days   if d.day_offset == -3).carbs_g
        assert cho_fit >= cho_unfit

    def test_weight_scales_carbs(self):
        p60 = compute_carb_loading_protocol("R", "half", 60.0)
        p80 = compute_carb_loading_protocol("R", "half", 80.0)
        cho60 = next(d for d in p60.days if d.day_offset == -2).carbs_g
        cho80 = next(d for d in p80.days if d.day_offset == -2).carbs_g
        assert cho80 > cho60


# ─────────────────────────────────────────────────────────────────────────────
# § 6. compute_daily_macro_targets
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyMacroTargets:
    def test_rest_day_lower_cho_than_intense(self):
        rest    = compute_daily_macro_targets(weight_kg=70, tss_today=0)
        intense = compute_daily_macro_targets(weight_kg=70, tss_today=150)
        assert rest.carbs_g < intense.carbs_g

    def test_intense_day_type(self):
        t = compute_daily_macro_targets(weight_kg=70, tss_today=150)
        assert t.day_type == "intense"

    def test_easy_day_type(self):
        t = compute_daily_macro_targets(weight_kg=70, tss_today=50)
        assert t.day_type == "easy"

    def test_race_day_type_when_days_to_race_0(self):
        t = compute_daily_macro_targets(weight_kg=70, tss_today=0, days_to_race=0, race_dist="full")
        assert t.day_type == "race"

    def test_pre_race_day_type(self):
        t = compute_daily_macro_targets(weight_kg=70, tss_today=20, days_to_race=2, race_dist="half")
        assert t.day_type == "pre-race"

    def test_protein_higher_for_intense(self):
        rest    = compute_daily_macro_targets(weight_kg=70, tss_today=0)
        intense = compute_daily_macro_targets(weight_kg=70, tss_today=150)
        assert intense.protein_g > rest.protein_g

    def test_fiber_reduced_pre_race(self):
        normal   = compute_daily_macro_targets(weight_kg=70, tss_today=50)
        pre_race = compute_daily_macro_targets(weight_kg=70, tss_today=20, days_to_race=1, race_dist="full")
        assert pre_race.fiber_g < normal.fiber_g

    def test_sodium_highest_on_race_day(self):
        race  = compute_daily_macro_targets(weight_kg=70, tss_today=0, days_to_race=0)
        rest  = compute_daily_macro_targets(weight_kg=70, tss_today=0)
        assert race.sodium_mg > rest.sodium_mg

    def test_kcal_positive_all_scenarios(self):
        for tss in [0, 30, 80, 130, 200]:
            t = compute_daily_macro_targets(weight_kg=70, tss_today=tss)
            assert t.kcal > 0

    def test_hydration_increases_with_tss(self):
        rest    = compute_daily_macro_targets(weight_kg=70, tss_today=0)
        intense = compute_daily_macro_targets(weight_kg=70, tss_today=150)
        assert intense.hydration_ml > rest.hydration_ml

    def test_rationale_is_non_empty_string(self):
        t = compute_daily_macro_targets(weight_kg=70, tss_today=80)
        assert isinstance(t.rationale, str)
        assert len(t.rationale) > 10

    def test_weight_scales_macros(self):
        t60 = compute_daily_macro_targets(weight_kg=60, tss_today=80)
        t80 = compute_daily_macro_targets(weight_kg=80, tss_today=80)
        assert t80.carbs_g > t60.carbs_g
        assert t80.protein_g > t60.protein_g

    def test_female_lower_fiber_target(self):
        male   = compute_daily_macro_targets(weight_kg=65, tss_today=0, sex="M")
        female = compute_daily_macro_targets(weight_kg=65, tss_today=0, sex="F")
        assert female.fiber_g < male.fiber_g
