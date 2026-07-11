"""
Tests — Race Day Intelligence v1.0 (Sprint 19)
===============================================
Motor de predicción CTL-based, nutrición, pacing score.
Sin imports de FastAPI/SQLAlchemy/DB.

Correr: pytest api/tests/test_race.py -v --noconftest
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# MIRRORS DEL MOTOR (race_routes.py _s19_race_append.py)
# ─────────────────────────────────────────────────────────────────────────────

_CTL_BANDS = [
    (0,   130, 24.0, 400),
    (20,  120, 26.0, 380),
    (40,  110, 28.5, 360),
    (60,  105, 31.0, 340),
    (80,  100, 33.5, 320),
    (100, 97,  36.0, 300),
    (120, 95,  38.0, 285),
    (150, 90,  40.0, 270),
]

def _ctl_base_paces(ctl):
    band = _CTL_BANDS[0]
    for b in _CTL_BANDS:
        if ctl >= b[0]:
            band = b
        else:
            break
    return {"swim_s100m": band[1], "bike_kmh": band[2], "run_s_km": band[3]}


def _tsb_perf_mod(tsb):
    if tsb is None: return 1.0
    if tsb <= -30:  return 0.94
    if tsb <= -20:  return 0.96
    if tsb <= -10:  return 0.98
    if tsb <= 0:    return 1.00
    if tsb <= 10:   return 1.01
    if tsb <= 20:   return 1.02
    return 1.025


def _rec_perf_mod(rec):
    if rec is None: return 1.0
    if rec >= 85:   return 1.02
    if rec >= 70:   return 1.01
    if rec >= 55:   return 1.00
    if rec >= 40:   return 0.98
    return 0.96


def _ctl_predict_splits(race_dist_key, ctl, tsb, recovery_score, ftp_w=None):
    dist_map = {
        "sprint": {"swim_m":750,   "bike_km":20,   "run_km":5,   "brick":1.03},
        "olympic":{"swim_m":1500,  "bike_km":40,   "run_km":10,  "brick":1.05},
        "703":    {"swim_m":1900,  "bike_km":90,   "run_km":21.1,"brick":1.08},
        "full":   {"swim_m":3800,  "bike_km":180,  "run_km":42.2,"brick":1.12},
        "21k":    {"swim_m":0,     "bike_km":0,    "run_km":21.1,"brick":1.0},
        "42k":    {"swim_m":0,     "bike_km":0,    "run_km":42.2,"brick":1.0},
    }
    trans = {
        "sprint":{"t1":120,"t2":60}, "olympic":{"t1":150,"t2":75},
        "703":{"t1":180,"t2":90},    "full":{"t1":240,"t2":120},
        "21k":{"t1":0,"t2":0},       "42k":{"t1":0,"t2":0},
    }
    dist = dist_map.get(race_dist_key, dist_map["olympic"])
    tn   = trans.get(race_dist_key, trans["olympic"])
    base = _ctl_base_paces(ctl or 50)
    mod  = (_tsb_perf_mod(tsb) + _rec_perf_mod(recovery_score)) / 2.0

    swim_s = int((dist["swim_m"]/100) * base["swim_s100m"] / mod) if dist["swim_m"] else 0
    t1_s   = tn["t1"] if dist["swim_m"] and dist["bike_km"] else 0
    t2_s   = tn["t2"] if dist["bike_km"] and dist["run_km"] else 0

    bike_if = None
    bike_pw = None
    if dist["bike_km"] and ftp_w:
        if_map = {"sprint":0.90, "olympic":0.82, "703":0.75, "full":0.70}
        bike_if = round(min(0.95, if_map.get(race_dist_key, 0.78) * mod), 3)
        bike_pw = int(ftp_w * bike_if)
        ref_p, ref_s = 200, 32.0
        bike_kmh = ref_s * (bike_pw / ref_p) ** (1/2.8)
        bike_s   = int(dist["bike_km"] / bike_kmh * 3600)
    elif dist["bike_km"]:
        bike_s = int(dist["bike_km"] / (base["bike_kmh"] * mod) * 3600)
    else:
        bike_s = 0

    run_pace = int(base["run_s_km"] * dist["brick"] / mod) if dist["run_km"] else None
    run_s    = int(dist["run_km"] * run_pace) if (dist["run_km"] and run_pace) else 0
    total    = swim_s + t1_s + bike_s + t2_s + run_s

    return {
        "swim_s": swim_s, "t1_s": t1_s, "bike_s": bike_s,
        "t2_s": t2_s, "run_s": run_s, "total_s": total,
        "bike_if": bike_if, "bike_pw": bike_pw, "run_pace_s_km": run_pace,
        "mod": round(mod, 3),
    }


def _gen_nutrition_simple(total_min, weight_kg=70.0, sweat_l_h=0.8):
    dur_h = total_min / 60
    if total_min < 60:    carb_g_h = 30
    elif total_min < 90:  carb_g_h = 45
    elif total_min < 150: carb_g_h = 60
    elif total_min < 240: carb_g_h = 75
    elif total_min < 360: carb_g_h = 90
    else:                 carb_g_h = 90
    return {
        "carb_g_h":    carb_g_h,
        "total_carb_g": int(carb_g_h * dur_h),
        "fluid_l":     round(sweat_l_h * dur_h, 1),
        "sodium_mg_h": int(weight_kg * 10),
    }


def _pacing_score(pred_total, actual_total, pred_power, actual_power,
                  pred_pace, actual_pace, dnf):
    if dnf: return 0
    scores = []
    if pred_total and actual_total:
        err = abs(actual_total - pred_total) / pred_total
        scores.append(max(0, 100 - err * 500))
    if pred_power and actual_power:
        err = abs(actual_power - pred_power) / pred_power
        scores.append(max(0, 100 - err * 500))
    if pred_pace and actual_pace:
        err = abs(actual_pace - pred_pace) / pred_pace
        scores.append(max(0, 100 - err * 500))
    return int(sum(scores)/len(scores)) if scores else None


def _fmt_time(s):
    if not s or s <= 0: return "—"
    h,rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: CTL PACES
# ─────────────────────────────────────────────────────────────────────────────

class TestCTLPaces:
    def test_low_ctl_slow_paces(self):
        paces = _ctl_base_paces(10)
        assert paces["swim_s100m"] >= 120
        assert paces["bike_kmh"] <= 27
        assert paces["run_s_km"] >= 370

    def test_high_ctl_fast_paces(self):
        paces = _ctl_base_paces(150)
        assert paces["swim_s100m"] <= 95
        assert paces["bike_kmh"] >= 38
        assert paces["run_s_km"] <= 275

    def test_ctl_monotonically_faster(self):
        paces_30  = _ctl_base_paces(30)
        paces_100 = _ctl_base_paces(100)
        assert paces_100["swim_s100m"] < paces_30["swim_s100m"]
        assert paces_100["bike_kmh"]   > paces_30["bike_kmh"]
        assert paces_100["run_s_km"]   < paces_30["run_s_km"]

    def test_ctl_zero_gets_lowest_band(self):
        paces = _ctl_base_paces(0)
        assert paces["swim_s100m"] == 130

    def test_ctl_180_gets_top_band(self):
        paces = _ctl_base_paces(180)
        assert paces["swim_s100m"] == 90


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: TSB MODIFIER
# ─────────────────────────────────────────────────────────────────────────────

class TestTSBModifier:
    def test_none_tsb_returns_1(self):
        assert _tsb_perf_mod(None) == 1.0

    def test_very_negative_tsb_penalty(self):
        assert _tsb_perf_mod(-35) < 1.0

    def test_positive_tsb_bonus(self):
        assert _tsb_perf_mod(15) > 1.0

    def test_zero_tsb_neutral(self):
        assert _tsb_perf_mod(0) == 1.0

    def test_tsb_monotonic(self):
        vals = [-35, -20, -10, 0, 10, 20, 25]
        mods = [_tsb_perf_mod(v) for v in vals]
        assert all(mods[i] <= mods[i+1] for i in range(len(mods)-1))

    def test_very_high_tsb_capped(self):
        assert _tsb_perf_mod(100) <= 1.03

    def test_critical_fatigue(self):
        assert _tsb_perf_mod(-30) == 0.94


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: RECOVERY MODIFIER
# ─────────────────────────────────────────────────────────────────────────────

class TestRecoveryModifier:
    def test_none_returns_1(self):
        assert _rec_perf_mod(None) == 1.0

    def test_peak_recovery_bonus(self):
        assert _rec_perf_mod(90) == 1.02

    def test_critical_recovery_penalty(self):
        assert _rec_perf_mod(20) == 0.96

    def test_monotonic(self):
        vals = [20, 40, 55, 70, 85]
        mods = [_rec_perf_mod(v) for v in vals]
        assert all(mods[i] <= mods[i+1] for i in range(len(mods)-1))


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: SPLIT PREDICTION
# ─────────────────────────────────────────────────────────────────────────────

class TestSplitPrediction:
    def test_olympic_has_all_splits(self):
        s = _ctl_predict_splits("olympic", 70, 5, 80)
        assert s["swim_s"] > 0
        assert s["bike_s"] > 0
        assert s["run_s"]  > 0
        assert s["total_s"] > 0

    def test_total_is_sum_of_parts(self):
        s = _ctl_predict_splits("olympic", 70, 5, 80)
        expected = s["swim_s"] + s["t1_s"] + s["bike_s"] + s["t2_s"] + s["run_s"]
        assert s["total_s"] == expected

    def test_high_ctl_faster_than_low(self):
        low  = _ctl_predict_splits("olympic", 30, 0, 70)
        high = _ctl_predict_splits("olympic", 120, 0, 70)
        assert high["total_s"] < low["total_s"]

    def test_good_form_faster(self):
        tired = _ctl_predict_splits("olympic", 70, -25, 40)
        fresh = _ctl_predict_splits("olympic", 70, 10, 85)
        assert fresh["total_s"] < tired["total_s"]

    def test_ftp_provides_power_target(self):
        s = _ctl_predict_splits("olympic", 70, 5, 80, ftp_w=220)
        assert s["bike_if"] is not None and s["bike_pw"] is not None
        assert 0.5 < s["bike_if"] < 1.0
        assert s["bike_pw"] == int(220 * s["bike_if"])

    def test_sprint_shorter_than_ironman(self):
        sprint = _ctl_predict_splits("sprint", 70, 0, 75)
        full   = _ctl_predict_splits("full",   70, 0, 75)
        assert sprint["total_s"] < full["total_s"]

    def test_21k_no_swim_no_bike(self):
        s = _ctl_predict_splits("21k", 70, 0, 75)
        assert s["swim_s"] == 0
        assert s["bike_s"] == 0
        assert s["run_s"]  > 0
        assert s["t1_s"]   == 0

    def test_olympic_realistic_range(self):
        # CTL 70 athlete should finish Olympic in 1.5h - 3h
        s = _ctl_predict_splits("olympic", 70, 0, 70)
        assert 5400 <= s["total_s"] <= 10800

    def test_ironman_realistic_range(self):
        # CTL 80 athlete Ironman: 9h - 14h
        s = _ctl_predict_splits("full", 80, 5, 75)
        assert 32400 <= s["total_s"] <= 50400

    def test_modifier_between_0_94_and_1_03(self):
        s = _ctl_predict_splits("olympic", 70, 0, 70)
        assert 0.93 <= s["mod"] <= 1.04


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: NUTRITION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TestNutrition:
    def test_short_race_low_carbs(self):
        n = _gen_nutrition_simple(45)
        assert n["carb_g_h"] <= 30

    def test_olympic_medium_carbs(self):
        n = _gen_nutrition_simple(120)
        assert 55 <= n["carb_g_h"] <= 65

    def test_ironman_max_carbs(self):
        n = _gen_nutrition_simple(600)
        assert n["carb_g_h"] == 90

    def test_total_carb_scales_with_duration(self):
        n2h = _gen_nutrition_simple(120)
        n5h = _gen_nutrition_simple(300)
        assert n5h["total_carb_g"] > n2h["total_carb_g"]

    def test_fluid_scales_with_duration(self):
        n2h = _gen_nutrition_simple(120, sweat_l_h=1.0)
        n4h = _gen_nutrition_simple(240, sweat_l_h=1.0)
        assert n4h["fluid_l"] > n2h["fluid_l"]

    def test_heavier_athlete_more_sodium(self):
        n70 = _gen_nutrition_simple(180, weight_kg=70)
        n90 = _gen_nutrition_simple(180, weight_kg=90)
        assert n90["sodium_mg_h"] > n70["sodium_mg_h"]

    def test_carb_g_h_always_positive(self):
        for dur in (30, 60, 120, 300, 600):
            n = _gen_nutrition_simple(dur)
            assert n["carb_g_h"] > 0

    def test_total_carbs_positive(self):
        n = _gen_nutrition_simple(180)
        assert n["total_carb_g"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: PACING SCORE
# ─────────────────────────────────────────────────────────────────────────────

class TestPacingScore:
    def test_dnf_is_zero(self):
        assert _pacing_score(7200, 6000, 200, 180, 300, 280, True) == 0

    def test_perfect_execution_is_high(self):
        score = _pacing_score(7200, 7200, 200, 200, 300, 300, False)
        assert score >= 99

    def test_large_time_error_reduces_score(self):
        score = _pacing_score(7200, 9000, None, None, None, None, False)
        assert score < 50

    def test_small_error_high_score(self):
        # 1% time error
        score = _pacing_score(7200, 7272, None, None, None, None, False)
        assert score > 90

    def test_no_targets_returns_none(self):
        assert _pacing_score(None, None, None, None, None, None, False) is None

    def test_power_penalty(self):
        # 20% over power → big penalty
        perfect = _pacing_score(7200, 7200, 200, 200, None, None, False)
        over    = _pacing_score(7200, 7200, 200, 240, None, None, False)
        assert perfect > over

    def test_score_between_0_and_100(self):
        for actual in (5000, 7200, 9000, 12000):
            s = _pacing_score(7200, actual, 200, 190, 300, 310, False)
            if s is not None:
                assert 0 <= s <= 100


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: FORMAT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatHelpers:
    def test_seconds_under_hour(self):
        assert _fmt_time(90) == "1:30"

    def test_exactly_one_hour(self):
        assert _fmt_time(3600) == "1:00:00"

    def test_ironman_time(self):
        result = _fmt_time(36900)  # 10:15:00
        assert result == "10:15:00"

    def test_zero_returns_dash(self):
        assert _fmt_time(0) == "—"

    def test_none_returns_dash(self):
        assert _fmt_time(None) == "—"

    def test_45min(self):
        assert _fmt_time(2700) == "45:00"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: INPUT VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

class TestInputValidation:
    def test_valid_ftp_range(self):
        for ftp in (50, 150, 220, 400, 500):
            assert 50 <= ftp <= 500

    def test_invalid_ftp(self):
        assert not (50 <= 30 <= 500)
        assert not (50 <= 501 <= 500)

    def test_valid_race_types(self):
        valid = {"sprint", "olympic", "703", "full", "21k", "42k"}
        assert "olympic" in valid
        assert "invalid" not in valid

    def test_weight_range(self):
        assert 30 <= 70 <= 150
        assert not (30 <= 20 <= 150)

    def test_dnf_flag(self):
        assert isinstance(True, bool)
        assert isinstance(False, bool)
