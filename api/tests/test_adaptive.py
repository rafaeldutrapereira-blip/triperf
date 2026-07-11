"""
Tests — Plan Adaptativo de Entrenamiento v1.0 (Sprint 16)
==========================================================
Pruebas unitarias del motor adaptativo.
Totalmente autocontenidas — sin imports de FastAPI/SQLAlchemy.

Correr: pytest api/tests/test_adaptive.py -v --noconftest
"""
import math
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# MIRRORS DE adaptive_routes.py
# ─────────────────────────────────────────────────────────────────────────────

def _intensity_factor(recovery_score):
    if recovery_score is None: return 1.0
    if recovery_score >= 85: return 1.10
    if recovery_score >= 70: return 1.00
    if recovery_score >= 55: return 0.85
    if recovery_score >= 40: return 0.70
    return 0.50


def _taper_factor(days_to_race):
    if days_to_race is None or days_to_race > 21: return 1.0
    if days_to_race >= 15: return 0.85
    if days_to_race >= 10: return 0.70
    if days_to_race >= 7:  return 0.55
    if days_to_race >= 4:  return 0.40
    if days_to_race >= 1:  return 0.25
    return 0.15


def _compliance_factor(compliance_7d):
    if compliance_7d is None: return 1.0
    c = compliance_7d
    if c > 1.05:  return 0.95
    if c >= 0.90: return 1.00
    if c >= 0.75: return 0.95
    if c >= 0.60: return 0.85
    return 0.75


def _combined_factor(intensity_f, taper_f, compliance_f):
    if taper_f < 0.90:
        combined = taper_f * 0.60 + intensity_f * 0.25 + compliance_f * 0.15
    else:
        combined = intensity_f * 0.55 + compliance_f * 0.30 + taper_f * 0.15
    return round(min(1.15, max(0.15, combined)), 3)


def _signal(recovery_score, combined_f, days_to_race):
    if days_to_race is not None and days_to_race <= 21:
        return "taper"
    if recovery_score is not None and recovery_score < 40:
        return "rest"
    if combined_f >= 1.05: return "increase"
    if combined_f >= 0.93: return "maintain"
    if combined_f >= 0.60: return "decrease"
    return "rest"


def _adjust_intensity_label(original, factor):
    order = ["rest", "easy", "moderate", "hard", "race"]
    if original not in order: return original
    idx = order.index(original)
    if factor >= 1.08 and idx < len(order) - 1: return order[min(idx + 1, len(order) - 1)]
    if factor <= 0.70 and idx > 0: return order[max(idx - 1, 0)]
    if factor <= 0.52: return "rest"
    return original


def _current_phase_simple(days_to_race, dist="703"):
    DURATIONS = {
        "703": {"taper": 2, "peak": 3, "build": 5, "base": 6},
        "full":{"taper": 3, "peak": 4, "build": 6, "base": 8},
    }
    durs = DURATIONS.get(dist, DURATIONS["703"])
    taper_d = durs["taper"] * 7
    peak_d  = (durs["taper"] + durs["peak"]) * 7
    build_d = (durs["taper"] + durs["peak"] + durs["build"]) * 7
    if days_to_race < 0:     return "recovery"
    if days_to_race <= taper_d: return "taper"
    if days_to_race <= peak_d:  return "peak"
    if days_to_race <= build_d: return "build"
    return "base"


def _compliance_7d_simple(planned_tsss, actual_tsss):
    """Simula el cálculo de compliance dado listas de TSS."""
    planned = sum(planned_tsss)
    actual  = sum(actual_tsss)
    if planned < 5: return None
    return round(actual / planned, 3)


RACE_WEEKLY_TSS = {
    "sprint":  {"base": 180, "build": 250, "peak": 300, "taper": 150, "recovery": 70},
    "olympic": {"base": 260, "build": 360, "peak": 420, "taper": 200, "recovery": 110},
    "703":     {"base": 360, "build": 500, "peak": 580, "taper": 280, "recovery": 150},
    "full":    {"base": 500, "build": 680, "peak": 800, "taper": 380, "recovery": 190},
}


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: INTENSITY FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestIntensityFactor:
    def test_none_recovery_is_nominal(self):
        assert _intensity_factor(None) == 1.0

    def test_optimal_recovery_boosts(self):
        assert _intensity_factor(85) == 1.10
        assert _intensity_factor(100) == 1.10

    def test_good_recovery_nominal(self):
        assert _intensity_factor(70) == 1.00
        assert _intensity_factor(75) == 1.00
        assert _intensity_factor(84) == 1.00

    def test_moderate_recovery_reduces(self):
        assert _intensity_factor(55) == 0.85
        assert _intensity_factor(60) == 0.85
        assert _intensity_factor(69) == 0.85

    def test_low_recovery_significant_reduction(self):
        assert _intensity_factor(40) == 0.70
        assert _intensity_factor(50) == 0.70
        assert _intensity_factor(54) == 0.70

    def test_critical_recovery_heavy_reduction(self):
        assert _intensity_factor(0) == 0.50
        assert _intensity_factor(39) == 0.50

    def test_boundary_85_is_optimal(self):
        assert _intensity_factor(85) == 1.10

    def test_boundary_84_is_good(self):
        assert _intensity_factor(84) == 1.00

    def test_boundary_70_is_good(self):
        assert _intensity_factor(70) == 1.00

    def test_boundary_55_is_moderate(self):
        assert _intensity_factor(55) == 0.85


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: TAPER FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestTaperFactor:
    def test_none_no_taper(self):
        assert _taper_factor(None) == 1.0

    def test_far_future_no_taper(self):
        assert _taper_factor(60) == 1.0
        assert _taper_factor(22) == 1.0

    def test_3_weeks_out_slight_reduction(self):
        # 15-21 días → 0.85
        assert _taper_factor(21) == 0.85
        assert _taper_factor(15) == 0.85

    def test_2_weeks_out_moderate(self):
        assert _taper_factor(14) == 0.70
        assert _taper_factor(10) == 0.70

    def test_1_week_out_real_taper(self):
        assert _taper_factor(9) == 0.55
        assert _taper_factor(7) == 0.55

    def test_race_week_heavy(self):
        assert _taper_factor(6) == 0.40
        assert _taper_factor(4) == 0.40

    def test_pre_race(self):
        assert _taper_factor(3) == 0.25
        assert _taper_factor(1) == 0.25

    def test_race_day(self):
        assert _taper_factor(0) == 0.15

    def test_taper_monotone_decreasing(self):
        # Factor siempre decrece cuando nos acercamos a la carrera
        prev = 1.0
        for d in [21, 14, 10, 7, 4, 1, 0]:
            curr = _taper_factor(d)
            assert curr <= prev, f"Días {d}: factor {curr} no es <= {prev}"
            prev = curr

    def test_boundary_22_is_no_taper(self):
        assert _taper_factor(22) == 1.0

    def test_boundary_21_is_taper(self):
        assert _taper_factor(21) == 0.85


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: COMPLIANCE FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceFactor:
    def test_none_is_nominal(self):
        assert _compliance_factor(None) == 1.0

    def test_overtraining_reduces(self):
        assert _compliance_factor(1.10) == 0.95
        assert _compliance_factor(1.06) == 0.95

    def test_on_track_nominal(self):
        assert _compliance_factor(1.05) == 1.00
        assert _compliance_factor(0.90) == 1.00
        assert _compliance_factor(1.00) == 1.00

    def test_slight_miss_slight_reduction(self):
        assert _compliance_factor(0.89) == 0.95
        assert _compliance_factor(0.75) == 0.95

    def test_moderate_miss_moderate_reduction(self):
        assert _compliance_factor(0.74) == 0.85
        assert _compliance_factor(0.60) == 0.85

    def test_major_miss_significant_reduction(self):
        assert _compliance_factor(0.59) == 0.75
        assert _compliance_factor(0.10) == 0.75

    def test_boundary_105_is_nominal(self):
        assert _compliance_factor(1.05) == 1.00

    def test_boundary_106_is_reduced(self):
        assert _compliance_factor(1.06) == 0.95


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: COMBINED FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestCombinedFactor:
    def test_all_nominal(self):
        f = _combined_factor(1.0, 1.0, 1.0)
        assert abs(f - 1.0) < 0.01

    def test_taper_dominates_when_active(self):
        # Taper 0.4, recovery óptimo 1.1, compliance perfecto 1.0
        f_taper  = _combined_factor(1.10, 0.40, 1.00)
        f_normal = _combined_factor(1.10, 1.00, 1.00)
        assert f_taper < f_normal, "Taper debe reducir el factor combinado"
        # Con taper=0.4 activo (0.60 weight): ~0.4*0.6 + 1.1*0.25 + 1.0*0.15 = 0.24+0.275+0.15 = 0.665
        assert f_taper < 0.75

    def test_critical_recovery_low_combined(self):
        # Recovery 0.50, no taper, compliance OK
        # 0.50*0.55 + 1.0*0.30 + 1.0*0.15 = 0.725
        f = _combined_factor(0.50, 1.0, 1.0)
        assert f < 0.75

    def test_optimal_recovery_high_combined(self):
        # Recovery 1.1, no taper, compliance OK
        f = _combined_factor(1.10, 1.0, 1.0)
        assert f >= 1.05

    def test_combined_bounded_minimum(self):
        # Peor caso posible
        f = _combined_factor(0.50, 0.15, 0.75)
        assert f >= 0.15

    def test_combined_bounded_maximum(self):
        # Mejor caso posible
        f = _combined_factor(1.15, 1.15, 1.15)
        assert f <= 1.15

    def test_compliance_matters_without_taper(self):
        # Sin taper: compliance peso 30%
        f_good_comp = _combined_factor(1.0, 1.0, 1.00)
        f_bad_comp  = _combined_factor(1.0, 1.0, 0.75)
        assert f_good_comp > f_bad_comp


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: SIGNAL
# ─────────────────────────────────────────────────────────────────────────────

class TestSignal:
    def test_taper_overrides_all(self):
        # Aunque combined sea alto, si hay carrera en ≤21 días → taper
        assert _signal(90, 1.10, 15) == "taper"
        assert _signal(30, 0.20, 3)  == "taper"

    def test_increase_when_optimal(self):
        assert _signal(88, 1.10, None) == "increase"
        assert _signal(85, 1.08, None) == "increase"

    def test_maintain_when_normal(self):
        assert _signal(72, 1.00, None) == "maintain"
        assert _signal(70, 0.95, None) == "maintain"
        assert _signal(65, 0.93, None) == "maintain"

    def test_decrease_when_tired(self):
        assert _signal(45, 0.70, None) == "decrease"
        assert _signal(55, 0.60, None) == "decrease"

    def test_rest_when_critical(self):
        assert _signal(25, 0.50, None) == "rest"
        assert _signal(30, 0.35, None) == "rest"

    def test_taper_boundary_22_days_no_taper(self):
        # 22 días → sin taper signal
        result = _signal(72, 1.0, 22)
        assert result == "maintain"

    def test_taper_boundary_21_days_taper(self):
        # 21 días → taper signal
        result = _signal(72, 1.0, 21)
        assert result == "taper"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: INTENSITY LABEL ADJUSTMENT
# ─────────────────────────────────────────────────────────────────────────────

class TestIntensityLabelAdjust:
    def test_high_factor_upgrades_label(self):
        assert _adjust_intensity_label("moderate", 1.10) == "hard"
        assert _adjust_intensity_label("easy",     1.10) == "moderate"

    def test_nominal_factor_keeps_label(self):
        assert _adjust_intensity_label("hard", 1.00) == "hard"
        assert _adjust_intensity_label("easy", 0.85) == "easy"

    def test_low_factor_downgrades(self):
        assert _adjust_intensity_label("hard",     0.70) == "moderate"
        assert _adjust_intensity_label("moderate", 0.70) == "easy"

    def test_very_low_factor_downgrades_one_step(self):
        # factor 0.50 ≤ 0.70 → downgrade one step (not forced rest)
        assert _adjust_intensity_label("moderate", 0.50) == "easy"
        assert _adjust_intensity_label("hard",     0.50) == "moderate"
        # rest stays rest at low factor (≤0.52 guard for already-rest)
        assert _adjust_intensity_label("rest",     0.40) == "rest"

    def test_rest_stays_rest(self):
        assert _adjust_intensity_label("rest", 1.10) == "easy"  # sube desde rest
        assert _adjust_intensity_label("rest", 0.50) == "rest"

    def test_race_cant_go_higher(self):
        # race es el máximo — no puede subir
        assert _adjust_intensity_label("race", 1.10) == "race"

    def test_unknown_label_passthrough(self):
        assert _adjust_intensity_label("unknown_sport", 0.80) == "unknown_sport"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: PHASE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestPhaseDetection:
    def test_past_race_is_recovery(self):
        assert _current_phase_simple(-1) == "recovery"
        assert _current_phase_simple(-30) == "recovery"

    def test_taper_zone_703(self):
        # 703: taper = 2 semanas = 14 días
        assert _current_phase_simple(14) == "taper"
        assert _current_phase_simple(7)  == "taper"
        assert _current_phase_simple(1)  == "taper"

    def test_peak_zone_703(self):
        # 703: peak = 3 sem, taper = 2 sem → peak: 15-35 días
        assert _current_phase_simple(15) == "peak"
        assert _current_phase_simple(25) == "peak"

    def test_build_zone_703(self):
        # build = 5 sem → 36-70 días
        assert _current_phase_simple(50) == "build"
        assert _current_phase_simple(65) == "build"

    def test_base_far_from_race(self):
        # >70 días para 703 → base
        assert _current_phase_simple(120) == "base"
        assert _current_phase_simple(200) == "base"

    def test_full_taper_longer(self):
        # full: taper = 3 semanas = 21 días
        assert _current_phase_simple(21, "full") == "taper"
        assert _current_phase_simple(22, "full") == "peak"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: COMPLIANCE CALCULATION
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceCalculation:
    def test_perfect_compliance(self):
        planned = [70, 80, 60, 90, 50, 85, 65]
        actual  = [70, 80, 60, 90, 50, 85, 65]
        c = _compliance_7d_simple(planned, actual)
        assert c == 1.0

    def test_partial_compliance(self):
        planned = [100] * 7
        actual  = [75]  * 7
        c = _compliance_7d_simple(planned, actual)
        assert c == 0.75

    def test_no_planned_returns_none(self):
        c = _compliance_7d_simple([0] * 7, [50] * 7)
        assert c is None

    def test_overtraining_compliance(self):
        planned = [50] * 7
        actual  = [65] * 7  # 130%
        c = _compliance_7d_simple(planned, actual)
        assert c == pytest.approx(1.3, abs=0.01)

    def test_zero_actual(self):
        planned = [100] * 7
        actual  = [0]   * 7
        c = _compliance_7d_simple(planned, actual)
        assert c == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: WEEKLY TSS TARGETS
# ─────────────────────────────────────────────────────────────────────────────

class TestWeeklyTssTargets:
    def test_ironman_build_highest(self):
        # IM build debe ser mayor que sprint build
        im_build     = RACE_WEEKLY_TSS["full"]["build"]
        sprint_build = RACE_WEEKLY_TSS["sprint"]["build"]
        assert im_build > sprint_build

    def test_taper_lower_than_build(self):
        for dist in RACE_WEEKLY_TSS:
            taper = RACE_WEEKLY_TSS[dist]["taper"]
            build = RACE_WEEKLY_TSS[dist]["build"]
            assert taper < build, f"{dist}: taper {taper} debe ser < build {build}"

    def test_taper_lower_than_base(self):
        for dist in RACE_WEEKLY_TSS:
            taper = RACE_WEEKLY_TSS[dist]["taper"]
            base  = RACE_WEEKLY_TSS[dist]["base"]
            assert taper < base

    def test_recovery_is_lowest(self):
        for dist in RACE_WEEKLY_TSS:
            rec   = RACE_WEEKLY_TSS[dist]["recovery"]
            for phase in ("base","build","peak","taper"):
                other = RACE_WEEKLY_TSS[dist][phase]
                assert rec < other, f"{dist}: recovery {rec} debe ser < {phase} {other}"

    def test_peak_higher_than_build(self):
        for dist in RACE_WEEKLY_TSS:
            peak  = RACE_WEEKLY_TSS[dist]["peak"]
            build = RACE_WEEKLY_TSS[dist]["build"]
            assert peak >= build, f"{dist}: peak debe ser >= build"

    def test_all_phases_positive(self):
        for dist, phases in RACE_WEEKLY_TSS.items():
            for phase, tss in phases.items():
                assert tss > 0, f"{dist}/{phase}: TSS debe ser > 0"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: END-TO-END ADAPTATION SCENARIO
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndAdaptation:
    def _adapt(self, recovery_score, days_to_race, compliance_7d):
        """Simula el pipeline completo del motor."""
        if_f  = _intensity_factor(recovery_score)
        tf_f  = _taper_factor(days_to_race)
        cf_f  = _compliance_factor(compliance_7d)
        comb  = _combined_factor(if_f, tf_f, cf_f)
        sig   = _signal(recovery_score, comb, days_to_race)
        orig  = 100  # TSS original del plan
        adj   = round(orig * comb, 1)
        i_adj = _adjust_intensity_label("hard", comb)
        return {"signal": sig, "combined": comb, "adjusted_tss": adj, "intensity": i_adj}

    def test_illness_scenario(self):
        # Atleta enfermo: recovery 25 (<40 → override a rest), sin carrera
        # combined ≈ 0.68 pero recovery_score < 40 → señal "rest" por override
        r = self._adapt(25, None, 0.60)
        assert r["signal"] == "rest"
        assert r["adjusted_tss"] <= 75

    def test_race_week_scenario(self):
        # Semana de carrera (5 días): bien descansado pero tapering
        # tf=0.40 (activo), combined ≈ 0.40*0.60 + 1.0*0.25 + 1.0*0.15 = 0.64
        r = self._adapt(80, 5, 0.90)
        assert r["signal"] == "taper"
        assert r["combined"] < 0.70  # reducido por taper

    def test_peak_form_scenario(self):
        # Forma óptima: recovery 90, buen compliance
        # if_f=1.10, tf=1.0, cf=1.0 → combined = 1.10*0.55 + 1.0*0.30 + 1.0*0.15 = 1.055
        r = self._adapt(90, None, 0.95)
        assert r["signal"] == "increase"
        assert r["combined"] >= 1.05
        assert r["adjusted_tss"] >= 100

    def test_normal_training_scenario(self):
        # Día normal: recovery 72, sin carrera cercana, buen compliance
        r = self._adapt(72, None, 0.92)
        assert r["signal"] == "maintain"
        assert 90 <= r["adjusted_tss"] <= 110

    def test_overtraining_prevention(self):
        # Demasiada carga acumulada: recovery 45, compliance 110%
        r = self._adapt(45, None, 1.10)
        # Recovery bajo + compliance alto (sobreentrenamiento) → reducir
        assert r["combined"] < 0.85
        assert r["adjusted_tss"] < 90

    def test_travel_week_scenario(self):
        # Semana de viaje: solo 50% completado, recovery moderado (68)
        # if_f=0.85 (55-69), cf_f=0.75 (compliance<0.60), combined≈0.8425
        r = self._adapt(68, None, 0.50)
        assert r["signal"] in ("decrease", "rest")
        assert r["adjusted_tss"] <= 90

    def test_build_phase_peak_form(self):
        # Build phase, forma óptima, compliance perfecto
        r = self._adapt(87, 30, 1.00)
        # 30 días → no taper, recovery óptimo → increase
        assert r["signal"] == "increase"

    def test_taper_overrides_good_recovery(self):
        # Aunque recovery sea 95, si hay carrera en 10 días → taper
        r = self._adapt(95, 10, 1.0)
        assert r["signal"] == "taper"
        # Factor debe ser bajo por tapering
        tf = _taper_factor(10)
        assert tf == 0.70
        assert r["combined"] < 0.85
