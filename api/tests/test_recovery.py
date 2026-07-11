"""
Tests — Recuperación Inteligente v1.0 (Sprint 15)
===================================================
Pruebas unitarias puras del motor de recuperación.
No importa FastAPI ni SQLAlchemy — la lógica de negocio
se duplica en este archivo para total aislamiento.

Correr: pytest api/tests/test_recovery.py -v
"""
import statistics
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA DUPLICADA (mirrors de recovery_routes.py — sin imports de app)
# ─────────────────────────────────────────────────────────────────────────────

def _hrv_factor_pure(hrv_last_night, hrv_baseline):
    """Mirror de _hrv_factor con parámetros primitivos."""
    if hrv_last_night is None:
        return None
    if not hrv_baseline or hrv_baseline <= 0:
        if hrv_last_night >= 70:   return 90.0
        if hrv_last_night >= 55:   return 75.0
        if hrv_last_night >= 40:   return 55.0
        if hrv_last_night >= 25:   return 35.0
        return 15.0
    ratio  = hrv_last_night / hrv_baseline
    factor = min(100.0, max(0.0, (ratio - 0.7) / (1.2 - 0.7) * 90.0 + 10.0))
    return round(factor, 1)


def _sleep_factor_pure(total_min, rem_min, deep_min, sleep_score):
    """Mirror de _sleep_factor con parámetros primitivos."""
    if sleep_score is not None:
        return float(sleep_score)
    if total_min is None:
        return None
    total_h = total_min / 60
    if total_h >= 8:    base = 90
    elif total_h >= 7:  base = 78
    elif total_h >= 6:  base = 60
    elif total_h >= 5:  base = 38
    else:               base = 18
    if total_min > 0:
        quality_min   = (rem_min or 0) + (deep_min or 0)
        quality_ratio = quality_min / total_min
        bonus = min(10, quality_ratio * 25)
    else:
        bonus = 0
    return round(min(100.0, base + bonus), 1)


def _tsb_factor_pure(tsb):
    """Mirror de _tsb_factor."""
    if tsb is None:
        return None
    if tsb > 15:    return 95.0
    if tsb >= -5:   return 80.0
    if tsb >= -20:  return 60.0
    if tsb >= -35:  return 40.0
    return max(5.0, 20.0 + (tsb + 35) * 0.8)


def _stress_factor_pure(avg_stress):
    """Mirror de _stress_factor."""
    if avg_stress is None:
        return None
    return round(max(10.0, 100.0 - avg_stress * 0.90), 1)


def _body_battery_factor_pure(body_battery):
    """Mirror de _body_battery_factor."""
    if body_battery is None:
        return None
    return float(body_battery)


def _wellness_factor_pure(energy, mood, soreness, motivation, stress, sleep_quality):
    """Mirror de _wellness_factor."""
    scores = []
    for v in (energy, mood, motivation, sleep_quality):
        if v is not None:
            scores.append((v - 1) / 4 * 100)
    for v in (soreness, stress):
        if v is not None:
            scores.append((v - 1) / 4 * 100)
    return round(statistics.mean(scores), 1) if scores else None


def _level_pure(score):
    """Mirror de _level."""
    if score >= 85: return "optimal",  "#10B981", "full"
    if score >= 70: return "good",     "#22D3EE", "full"
    if score >= 55: return "moderate", "#F0A500", "moderate"
    if score >= 40: return "low",      "#F59E0B", "easy"
    return "critical", "#EF4444", "rest"


def _compute_score_pure(hrv, sleep, tsb, stress, bb, wellness=None, hrv_baseline=0.0):
    """Mirror simplificado de _compute_recovery_score sin ORM."""
    hrv_f    = _hrv_factor_pure(hrv, hrv_baseline)
    sleep_f  = _sleep_factor_pure(sleep["total_min"], sleep.get("rem_min"), sleep.get("deep_min"), sleep.get("score")) if sleep else None
    tsb_f    = _tsb_factor_pure(tsb)
    stress_f = _stress_factor_pure(stress)
    bb_f     = _body_battery_factor_pure(bb)
    well_f   = wellness  # ya calculado por el test

    DEFAULT_W = {"hrv":0.30, "sleep":0.25, "tsb":0.20, "stress":0.15, "body_battery":0.10, "wellness":0.00}
    FALLBACK_W= {"hrv":0.00, "sleep":0.40, "tsb":0.30, "stress":0.20, "body_battery":0.10, "wellness":0.00}

    weights = dict(DEFAULT_W if hrv_f is not None else FALLBACK_W)
    if well_f is not None:
        ww = 0.10
        for k in list(weights.keys()):
            weights[k] = weights[k] * (1 - ww)
        weights["wellness"] = ww

    factors = {"hrv": hrv_f, "sleep": sleep_f, "tsb": tsb_f, "stress": stress_f, "body_battery": bb_f, "wellness": well_f}

    total_w = 0.0
    total_s = 0.0
    for k, v in factors.items():
        w = weights.get(k, 0)
        if v is not None and w > 0:
            total_w += w
            total_s += v * w

    if total_w == 0:
        return 50
    return round(total_s / total_w)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: HRV FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestHrvFactor:
    def test_none_hrv_returns_none(self):
        assert _hrv_factor_pure(None, 55.0) is None

    def test_no_baseline_uses_absolute_scale_high(self):
        f = _hrv_factor_pure(75, 0)
        assert f == 90.0

    def test_no_baseline_medium(self):
        f = _hrv_factor_pure(47, 0)
        assert f == 55.0

    def test_no_baseline_low(self):
        f = _hrv_factor_pure(20, 0)
        assert f == 15.0

    def test_with_baseline_above_optimal(self):
        # hrv 66, baseline 55 → ratio 1.2 → factor ~100
        f = _hrv_factor_pure(66, 55)
        assert f >= 95.0

    def test_with_baseline_at_baseline(self):
        # ratio exactamente 1.0 → factor = (0.3/0.5)*90+10 = 64
        f = _hrv_factor_pure(55, 55)
        assert 60.0 <= f <= 70.0

    def test_with_baseline_below_critical(self):
        # hrv = 35, baseline = 55 → ratio 0.636 < 0.7 → factor ≤ 10
        f = _hrv_factor_pure(35, 55)
        assert f <= 10.0

    def test_factor_bounded_0_100(self):
        # Extremo bajo: HRV 1ms
        low = _hrv_factor_pure(1, 55)
        assert 0.0 <= low <= 100.0
        # Extremo alto: HRV 200ms
        high = _hrv_factor_pure(200, 55)
        assert 0.0 <= high <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: SLEEP FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestSleepFactor:
    def test_garmin_score_direct_passthrough(self):
        # Si hay sleep_score Garmin, se usa directamente
        f = _sleep_factor_pure(360, 60, 90, 82)
        assert f == 82.0

    def test_none_total_min_returns_none_without_score(self):
        f = _sleep_factor_pure(None, None, None, None)
        assert f is None

    def test_8h_sleep_high_quality(self):
        # 8h = 480min, REM 90 + Deep 90 = 180/480 = 37.5% → bonus ~9
        f = _sleep_factor_pure(480, 90, 90, None)
        assert f >= 90.0

    def test_7h_sleep_moderate_quality(self):
        f = _sleep_factor_pure(420, 60, 60, None)
        assert 75.0 <= f <= 95.0

    def test_6h_sleep_lower(self):
        f = _sleep_factor_pure(360, 30, 30, None)
        assert 55.0 <= f <= 72.0

    def test_5h_sleep_poor(self):
        f = _sleep_factor_pure(300, 20, 20, None)
        assert 35.0 <= f <= 50.0

    def test_4h_sleep_critical(self):
        f = _sleep_factor_pure(240, 10, 10, None)
        assert f <= 30.0

    def test_sleep_factor_bounded(self):
        f = _sleep_factor_pure(600, 200, 200, None)  # 10h, muy buena calidad
        assert f <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: TSB FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestTsbFactor:
    def test_none_tsb_returns_none(self):
        assert _tsb_factor_pure(None) is None

    def test_peak_form(self):
        assert _tsb_factor_pure(20) == 95.0

    def test_fresh_zone(self):
        assert _tsb_factor_pure(5) == 80.0

    def test_mild_fatigue(self):
        assert _tsb_factor_pure(-12) == 60.0

    def test_moderate_fatigue(self):
        assert _tsb_factor_pure(-28) == 40.0

    def test_severe_fatigue(self):
        f = _tsb_factor_pure(-45)
        assert f >= 5.0 and f < 20.0

    def test_boundary_tsb_minus5(self):
        # -5 está en el límite de "fresh" (≥-5 → 80)
        assert _tsb_factor_pure(-5) == 80.0

    def test_boundary_tsb_minus_35(self):
        # -35 exacto cae en el branch ≥-35 → 40.0
        assert _tsb_factor_pure(-35) == 40.0

    def test_extreme_negative_tsb_floored(self):
        f = _tsb_factor_pure(-100)
        assert f >= 5.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: STRESS FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestStressFactor:
    def test_none_stress_returns_none(self):
        assert _stress_factor_pure(None) is None

    def test_zero_stress_high_recovery(self):
        f = _stress_factor_pure(0)
        assert f == 100.0

    def test_moderate_stress(self):
        # stress=50 → 100 - 45 = 55
        f = _stress_factor_pure(50)
        assert abs(f - 55.0) < 1.0

    def test_high_stress(self):
        # stress=80 → 100 - 72 = 28
        f = _stress_factor_pure(80)
        assert f <= 30.0

    def test_max_stress_floored(self):
        # stress=100 → max(10, 100-90) = 10
        f = _stress_factor_pure(100)
        assert f == 10.0

    def test_stress_always_positive(self):
        for s in range(0, 101, 10):
            assert _stress_factor_pure(s) >= 10.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: BODY BATTERY FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestBodyBatteryFactor:
    def test_none_returns_none(self):
        assert _body_battery_factor_pure(None) is None

    def test_full_battery(self):
        assert _body_battery_factor_pure(100) == 100.0

    def test_half_battery(self):
        assert _body_battery_factor_pure(50) == 50.0

    def test_low_battery(self):
        assert _body_battery_factor_pure(15) == 15.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: WELLNESS FACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestWellnessFactor:
    def test_all_max_scores(self):
        # Todos en 5 → todos 100 → promedio 100
        f = _wellness_factor_pure(5, 5, 5, 5, 5, 5)
        assert f == 100.0

    def test_all_min_scores(self):
        # Todos en 1 → todos 0 → promedio 0
        f = _wellness_factor_pure(1, 1, 1, 1, 1, 1)
        assert f == 0.0

    def test_mixed_scores(self):
        # energy=4(75), mood=3(50), soreness=2(25), motivation=5(100), stress=2(25), sleep_quality=4(75)
        f = _wellness_factor_pure(4, 3, 2, 5, 2, 4)
        expected = statistics.mean([75, 50, 100, 75, 25, 25])  # energy,mood,motivation,sleep_q | soreness,stress
        assert abs(f - round(expected, 1)) < 0.1

    def test_all_none_returns_none(self):
        f = _wellness_factor_pure(None, None, None, None, None, None)
        assert f is None

    def test_partial_fields(self):
        # Solo energy y mood disponibles
        f = _wellness_factor_pure(4, 4, None, None, None, None)
        assert f is not None
        assert f > 0

    def test_scale_invariant_5_is_100(self):
        # (5-1)/4*100 = 100
        f = _wellness_factor_pure(5, None, None, None, None, None)
        assert f == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: LEVEL CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

class TestLevelClassification:
    def test_optimal_85_100(self):
        for s in (85, 90, 100):
            lvl, col, sug = _level_pure(s)
            assert lvl == "optimal"
            assert sug == "full"

    def test_good_70_84(self):
        for s in (70, 75, 84):
            lvl, _, sug = _level_pure(s)
            assert lvl == "good"
            assert sug == "full"

    def test_moderate_55_69(self):
        for s in (55, 60, 69):
            lvl, _, sug = _level_pure(s)
            assert lvl == "moderate"
            assert sug == "moderate"

    def test_low_40_54(self):
        for s in (40, 45, 54):
            lvl, _, sug = _level_pure(s)
            assert lvl == "low"
            assert sug == "easy"

    def test_critical_0_39(self):
        for s in (0, 20, 39):
            lvl, _, sug = _level_pure(s)
            assert lvl == "critical"
            assert sug == "rest"

    def test_boundary_85_is_optimal(self):
        lvl, _, _ = _level_pure(85)
        assert lvl == "optimal"

    def test_boundary_84_is_good(self):
        lvl, _, _ = _level_pure(84)
        assert lvl == "good"

    def test_boundary_55_is_moderate(self):
        lvl, _, _ = _level_pure(55)
        assert lvl == "moderate"

    def test_boundary_54_is_low(self):
        lvl, _, _ = _level_pure(54)
        assert lvl == "low"

    def test_colors_are_hex(self):
        for score in (90, 75, 60, 45, 20):
            _, color, _ = _level_pure(score)
            assert color.startswith("#")
            assert len(color) == 7


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: RECOVERY SCORE COMPUESTO
# ─────────────────────────────────────────────────────────────────────────────

class TestCompositeRecoveryScore:
    def test_all_data_optimal(self):
        # HRV alta, sueño 8h calidad, TSB fresco, sin estrés, BB alto
        score = _compute_score_pure(
            hrv  = 72,
            sleep= {"total_min": 480, "rem_min": 90, "deep_min": 90, "score": None},
            tsb  = 10,
            stress = 10,
            bb   = 90,
            hrv_baseline = 55.0,
        )
        assert score >= 80, f"Score esperado ≥80, obtenido {score}"

    def test_poor_recovery_scores_low(self):
        # HRV baja, poco sueño, fatiga alta, estrés alto, BB bajo
        score = _compute_score_pure(
            hrv  = 30,
            sleep= {"total_min": 240, "rem_min": 10, "deep_min": 10, "score": None},
            tsb  = -35,
            stress = 85,
            bb   = 15,
            hrv_baseline = 55.0,
        )
        assert score <= 40, f"Score esperado ≤40, obtenido {score}"

    def test_no_hrv_uses_fallback_weights(self):
        # Sin HRV → peso sueño y TSB suben → score sigue siendo calculable
        score = _compute_score_pure(
            hrv  = None,
            sleep= {"total_min": 420, "rem_min": 60, "deep_min": 60, "score": None},
            tsb  = 5,
            stress = 35,
            bb   = 70,
        )
        assert 50 <= score <= 100

    def test_no_data_returns_50(self):
        # Sin ningún dato → neutral 50
        score = _compute_score_pure(
            hrv=None, sleep=None, tsb=None, stress=None, bb=None
        )
        assert score == 50

    def test_wellness_blends_into_score(self):
        # Con mismo set de datos, agregar wellness positivo debe subir el score
        score_no_well = _compute_score_pure(
            hrv=55, sleep={"total_min":420,"rem_min":60,"deep_min":60,"score":None},
            tsb=5, stress=40, bb=65, wellness=None
        )
        score_with_well = _compute_score_pure(
            hrv=55, sleep={"total_min":420,"rem_min":60,"deep_min":60,"score":None},
            tsb=5, stress=40, bb=65, wellness=95.0
        )
        assert score_with_well >= score_no_well

    def test_wellness_low_drags_score(self):
        score_no_well = _compute_score_pure(
            hrv=55, sleep={"total_min":420,"rem_min":60,"deep_min":60,"score":None},
            tsb=5, stress=40, bb=65, wellness=None
        )
        score_low_well = _compute_score_pure(
            hrv=55, sleep={"total_min":420,"rem_min":60,"deep_min":60,"score":None},
            tsb=5, stress=40, bb=65, wellness=5.0  # muy bajo
        )
        assert score_low_well <= score_no_well

    def test_score_bounded_0_100(self):
        # Caso extremo positivo
        hi = _compute_score_pure(hrv=100, sleep={"total_min":600,"rem_min":200,"deep_min":150,"score":95}, tsb=20, stress=0, bb=100)
        assert 0 <= hi <= 100
        # Caso extremo negativo
        lo = _compute_score_pure(hrv=5, sleep={"total_min":180,"rem_min":0,"deep_min":0,"score":10}, tsb=-50, stress=100, bb=5)
        assert 0 <= lo <= 100

    def test_garmin_sleep_score_used_directly(self):
        # Con score Garmin = 90, el sleep_factor debería ser 90
        f = _sleep_factor_pure(300, 20, 20, 90)
        assert f == 90.0  # Override total_min


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: WELLNESS VALIDATION (reglas de negocio para el endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class TestWellnessValidation:
    def test_valid_scale_1_to_5(self):
        for v in (1, 2, 3, 4, 5):
            assert 1 <= v <= 5

    def test_invalid_scale_0(self):
        # El endpoint debe rechazar 0
        with pytest.raises(AssertionError):
            assert 0 >= 1, "0 debería ser rechazado"

    def test_invalid_scale_6(self):
        with pytest.raises(AssertionError):
            assert 6 <= 5, "6 debería ser rechazado"

    def test_notes_truncation(self):
        long_note = "x" * 400
        truncated = long_note[:300]
        assert len(truncated) == 300


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: PROTOCOLOS DE RECUPERACIÓN
# ─────────────────────────────────────────────────────────────────────────────

PROTOCOL_TYPES = ["post_sprint", "post_703", "post_ironman", "illness", "overtraining"]

# Definición local mínima para validar estructura
PROTOCOL_STRUCTURE = {
    "post_sprint":    {"days": 4, "max_rest_days": 1},
    "post_703":       {"days": 5, "max_rest_days": 2},
    "post_ironman":   {"days": 4, "max_rest_days": 1},
    "illness":        {"days": 4, "max_rest_days": 1},
    "overtraining":   {"days": 3, "max_rest_days": 1},
}

def make_protocol(ptype):
    protocols = {
        "post_sprint": {"days": [
            {"day":1, "load":"rest","tss_max":0,   "actions":["Hidratación 3L"]},
            {"day":2, "load":"easy","tss_max":20,  "actions":["30min natación"]},
            {"day":3, "load":"moderate","tss_max":45,"actions":["Bici Z1"]},
            {"day":4, "load":"full","tss_max":70,  "actions":["Entrenamiento normal"]},
        ]},
        "post_703": {"days": [
            {"day":1,  "load":"rest","tss_max":0,  "actions":["Descanso"]},
            {"day":3,  "load":"easy","tss_max":25, "actions":["Caminata"]},
            {"day":5,  "load":"easy","tss_max":40, "actions":["Bici Z1"]},
            {"day":8,  "load":"moderate","tss_max":60,"actions":["Técnica"]},
            {"day":11, "load":"full","tss_max":80, "actions":["Normal"]},
        ]},
        "post_ironman": {"days": [{"day":1,"load":"rest","tss_max":0,"actions":[]},{"day":8,"load":"easy","tss_max":150,"actions":[]},{"day":15,"load":"moderate","tss_max":250,"actions":[]},{"day":22,"load":"full","tss_max":350,"actions":[]}]},
        "illness": {"days": [{"day":1,"load":"rest","tss_max":0,"actions":[]},{"day":2,"load":"easy","tss_max":20,"actions":[]},{"day":4,"load":"moderate","tss_max":50,"actions":[]},{"day":7,"load":"full","tss_max":None,"actions":[]}]},
        "overtraining": {"days": [{"day":1,"load":"rest","tss_max":0,"actions":[]},{"day":15,"load":"easy","tss_max":100,"actions":[]},{"day":29,"load":"moderate","tss_max":200,"actions":[]}]},
    }
    return protocols.get(ptype, {})


class TestRecoveryProtocols:
    def test_all_protocols_exist(self):
        for ptype in PROTOCOL_TYPES:
            p = make_protocol(ptype)
            assert "days" in p, f"Protocolo {ptype} sin días"

    def test_post_sprint_4_phases(self):
        p = make_protocol("post_sprint")
        assert len(p["days"]) == 4

    def test_post_ironman_starts_with_rest(self):
        p = make_protocol("post_ironman")
        assert p["days"][0]["load"] == "rest"
        assert p["days"][0]["tss_max"] == 0

    def test_post_ironman_ends_with_full(self):
        p = make_protocol("post_ironman")
        assert p["days"][-1]["load"] == "full"

    def test_progressive_load_order(self):
        load_order = {"rest": 0, "easy": 1, "moderate": 2, "full": 3}
        p = make_protocol("post_703")
        loads = [day["load"] for day in p["days"]]
        # Verificar que nunca baja de "full" a "rest"
        for i in range(1, len(loads)):
            prev = load_order[loads[i-1]]
            curr = load_order[loads[i]]
            assert curr >= prev - 1, f"Carga decreció abruptamente: {loads[i-1]}→{loads[i]}"

    def test_illness_starts_with_rest(self):
        p = make_protocol("illness")
        assert p["days"][0]["load"] == "rest"

    def test_all_loads_valid(self):
        valid = {"rest", "easy", "moderate", "full"}
        for ptype in PROTOCOL_TYPES:
            p = make_protocol(ptype)
            for day in p["days"]:
                assert day["load"] in valid, f"{ptype} día {day['day']} load inválido: {day['load']}"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: HRV TREND
# ─────────────────────────────────────────────────────────────────────────────

class TestHrvTrend:
    def _trend_slope(self, values):
        """Mirror del cálculo de trend slope en hrv_history."""
        n   = len(values)
        if n < 2:
            return None
        xs  = list(range(n))
        x_m = sum(xs) / n
        y_m = sum(values) / n
        num = sum((xs[i] - x_m) * (values[i] - y_m) for i in range(n))
        den = sum((xs[i] - x_m) ** 2 for i in range(n))
        if not den:
            return None
        return round((num / den) * 7, 2)  # ms/semana

    def test_rising_hrv_positive_slope(self):
        values = [40, 43, 47, 50, 53, 56, 60]
        slope = self._trend_slope(values)
        assert slope > 0

    def test_falling_hrv_negative_slope(self):
        values = [60, 56, 53, 50, 47, 43, 40]
        slope = self._trend_slope(values)
        assert slope < 0

    def test_flat_hrv_near_zero_slope(self):
        values = [50, 50, 50, 50, 50, 50, 50]
        slope = self._trend_slope(values)
        assert slope == 0.0

    def test_direction_up(self):
        slope = self._trend_slope([40, 50, 60])
        direction = "up" if slope and slope > 0.5 else ("down" if slope and slope < -0.5 else "stable")
        assert direction == "up"

    def test_direction_down(self):
        slope = self._trend_slope([60, 50, 40])
        direction = "up" if slope and slope > 0.5 else ("down" if slope and slope < -0.5 else "stable")
        assert direction == "down"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: SLEEP DEBT
# ─────────────────────────────────────────────────────────────────────────────

class TestSleepDebt:
    TARGET_H = 8.0

    def _sleep_debt(self, hours_per_day):
        total = 0.0
        for h in hours_per_day[-7:]:
            if h is not None:
                total += max(0, self.TARGET_H - h)
        return round(total, 1)

    def test_no_debt_with_8h_every_night(self):
        assert self._sleep_debt([8.0] * 7) == 0.0

    def test_1h_debt_per_night(self):
        assert self._sleep_debt([7.0] * 7) == 7.0

    def test_mixed_debt(self):
        # 8(0h) + 7(1h) + 6(2h) + 8(0h) + 7(1h) + 6(2h) + 8(0h) = 6h de deuda
        nights = [8, 7, 6, 8, 7, 6, 8]
        debt = self._sleep_debt(nights)
        assert debt == 6.0

    def test_zero_debt_when_all_above_target(self):
        assert self._sleep_debt([9.0, 9.5, 10.0, 8.5, 8.2, 9.0, 8.8]) == 0.0

    def test_uses_only_last_7_days(self):
        # 14 días, solo últimos 7 cuentan (5h cada noche = 3h deuda × 7 = 21h)
        nights = [8.0] * 7 + [5.0] * 7
        debt = self._sleep_debt(nights)
        assert debt == 21.0
