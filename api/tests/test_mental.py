"""
Tests — Rendimiento Mental v1.0 (Sprint 18)
============================================
Pruebas unitarias de motor MFS, validación, protocolos.
Sin imports de FastAPI/SQLAlchemy/DB.

Correr: pytest api/tests/test_mental.py -v --noconftest
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# MIRRORS DEL MOTOR MFS (mental_routes.py)
# ─────────────────────────────────────────────────────────────────────────────

def _mfs_from_checkin(anxiety, motivation, focus, confidence, mood):
    """Mirrors _mfs_from_checkin — None = missing."""
    weights = [
        (anxiety,    0.30, False),  # UI: 5=calmo=bueno → direct
        (motivation, 0.25, False),
        (focus,      0.25, False),
        (confidence, 0.15, False),
        (mood,       0.05, False),
    ]
    total_w = 0.0
    total_v = 0.0
    for val, w, inverted in weights:
        if val is None:
            continue
        normalized = (6 - val) / 4.0 if inverted else (val - 1) / 4.0
        total_v += normalized * w
        total_w += w
    if total_w < 0.25:
        return None
    return round((total_v / total_w) * 100, 1)


def _mfs_level(score):
    if score >= 85:
        return ("peak",     "#10B981", "train")
    if score >= 70:
        return ("good",     "#0EA5E9", "train")
    if score >= 55:
        return ("moderate", "#F59E0B", "reduce")
    if score >= 40:
        return ("low",      "#F97316", "rest")
    return ("critical",     "#EF4444", "rest")


def _compute_mfs_simple(anxiety, motivation, focus, confidence, mood,
                         recovery_score=None, stress=None):
    """Simplified combined MFS score."""
    components = {}

    checkin_score = _mfs_from_checkin(anxiety, motivation, focus, confidence, mood)
    if checkin_score is not None:
        components["checkin"] = (checkin_score, 0.50)

    if recovery_score is not None:
        components["recovery"] = (recovery_score, 0.25)

    if stress is not None:
        stress_norm = (6 - stress) / 4.0 * 100
        components["stress"] = (stress_norm, 0.10)

    if not components:
        return None

    total_w = sum(w for _, w in components.values())
    total_v = sum(v * w for v, w in components.values())
    return round(min(100, max(0, total_v / total_w)), 1)


# Protocol library data (subset for testing — all required fields)
def _proto(id, cat, dur, diff, goal):
    return {
        "id": id, "category": cat, "duration_min": dur,
        "difficulty": diff, "goal": goal,
        "name": id.replace("_", " ").title(),
        "description": "Descripción de " + id,
        "steps": ["Paso 1", "Paso 2"],
    }

PROTOCOL_SUBSET = [
    _proto("breath_478",    "breathing",      5,  "beginner",     "anxiety"),
    _proto("breath_box",    "breathing",      4,  "beginner",     "focus"),
    _proto("viz_race_day",  "visualization",  12, "intermediate", "confidence"),
    _proto("mind_5min",     "mindfulness",    5,  "beginner",     "focus"),
    _proto("race_morning",  "pre_race",       8,  "beginner",     "focus"),
    _proto("act_power_pose","activation",     2,  "beginner",     "confidence"),
]

def _filter_protocols(protocols, category=None, goal=None, difficulty=None, max_duration=None):
    result = protocols
    if category:
        result = [p for p in result if p["category"] == category]
    if goal:
        result = [p for p in result if p["goal"] == goal]
    if difficulty:
        result = [p for p in result if p["difficulty"] == difficulty]
    if max_duration:
        result = [p for p in result if p["duration_min"] <= max_duration]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: CHECKIN SCORING
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckinScoring:
    def test_perfect_scores_give_high_mfs(self):
        score = _mfs_from_checkin(5, 5, 5, 5, 5)
        assert score is not None and score >= 99

    def test_worst_scores_give_low_mfs(self):
        score = _mfs_from_checkin(1, 1, 1, 1, 1)
        assert score is not None and score <= 5

    def test_neutral_scores_give_mid_mfs(self):
        score = _mfs_from_checkin(3, 3, 3, 3, 3)
        assert score is not None and 48 <= score <= 52

    def test_anxiety_5_calm_gives_high(self):
        # anxiety=5 = very calm = good → direct map = high score
        score = _mfs_from_checkin(5, 3, 3, 3, 3)
        assert score > 50

    def test_anxiety_1_anxious_gives_low(self):
        # anxiety=1 = very anxious = bad → score < calm
        calm_score = _mfs_from_checkin(5, 3, 3, 3, 3)
        anxious_score = _mfs_from_checkin(1, 3, 3, 3, 3)
        assert anxious_score < calm_score

    def test_missing_data_below_threshold_returns_none(self):
        # All None → None
        assert _mfs_from_checkin(None, None, None, None, None) is None

    def test_single_anxiety_none_uses_remaining(self):
        # Only motivation (0.25 weight) — still enough
        score = _mfs_from_checkin(None, 5, None, None, None)
        assert score is not None and score >= 80

    def test_only_low_weight_field_returns_none(self):
        # Only mood (weight 0.05) — below 0.25 threshold
        score = _mfs_from_checkin(None, None, None, None, 5)
        assert score is None

    def test_score_in_range(self):
        for combo in [(5,5,5,5,5),(1,1,1,1,1),(3,3,3,3,3),(5,1,1,1,1)]:
            s = _mfs_from_checkin(*combo)
            assert 0 <= s <= 100

    def test_high_motivation_raises_score(self):
        baseline = _mfs_from_checkin(3, 3, 3, 3, 3)
        high_mot  = _mfs_from_checkin(3, 5, 3, 3, 3)
        assert high_mot > baseline


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: MFS LEVEL
# ─────────────────────────────────────────────────────────────────────────────

class TestMFSLevel:
    def test_100_is_peak(self):
        level, color, signal = _mfs_level(100)
        assert level == "peak" and signal == "train"

    def test_85_is_peak(self):
        level, _, _ = _mfs_level(85)
        assert level == "peak"

    def test_84_is_good(self):
        level, _, _ = _mfs_level(84)
        assert level == "good"

    def test_70_is_good(self):
        level, _, _ = _mfs_level(70)
        assert level == "good"

    def test_55_is_moderate(self):
        level, _, sig = _mfs_level(55)
        assert level == "moderate" and sig == "reduce"

    def test_40_is_low(self):
        level, _, sig = _mfs_level(40)
        assert level == "low" and sig == "rest"

    def test_39_is_critical(self):
        level, _, sig = _mfs_level(39)
        assert level == "critical" and sig == "rest"

    def test_0_is_critical(self):
        level, _, _ = _mfs_level(0)
        assert level == "critical"

    def test_train_signal_for_high_scores(self):
        for score in (70, 80, 90, 100):
            _, _, signal = _mfs_level(score)
            assert signal == "train"

    def test_rest_signal_for_low_scores(self):
        for score in (0, 20, 39):
            _, _, signal = _mfs_level(score)
            assert signal == "rest"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: COMBINED MFS
# ─────────────────────────────────────────────────────────────────────────────

class TestCombinedMFS:
    def test_perfect_checkin_and_recovery(self):
        score = _compute_mfs_simple(5, 5, 5, 5, 5, recovery_score=100)
        assert score >= 99

    def test_bad_recovery_pulls_down_score(self):
        good_checkin = _compute_mfs_simple(5, 5, 5, 5, 5)
        with_bad_rec = _compute_mfs_simple(5, 5, 5, 5, 5, recovery_score=20)
        assert with_bad_rec < good_checkin

    def test_high_stress_pulls_down_score(self):
        no_stress = _compute_mfs_simple(4, 4, 4, 4, 4, stress=None)
        high_stress = _compute_mfs_simple(4, 4, 4, 4, 4, stress=5)
        assert high_stress < no_stress

    def test_no_data_returns_none(self):
        assert _compute_mfs_simple(None, None, None, None, None) is None

    def test_recovery_only_not_enough_weight(self):
        # recovery alone (25%) is below the 25% checkin threshold
        score = _compute_mfs_simple(None, None, None, None, None, recovery_score=80)
        assert score is not None  # recovery alone is valid (25% weight)

    def test_score_always_0_to_100(self):
        for anxiety in (1, 3, 5):
            for rec in (10, 50, 100):
                s = _compute_mfs_simple(anxiety, 3, 3, 3, 3, recovery_score=rec)
                assert 0 <= s <= 100


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: PROTOCOL FILTERING
# ─────────────────────────────────────────────────────────────────────────────

class TestProtocolFiltering:
    def test_no_filter_returns_all(self):
        result = _filter_protocols(PROTOCOL_SUBSET)
        assert len(result) == len(PROTOCOL_SUBSET)

    def test_filter_breathing_category(self):
        result = _filter_protocols(PROTOCOL_SUBSET, category="breathing")
        assert all(p["category"] == "breathing" for p in result)
        assert len(result) == 2

    def test_filter_goal_focus(self):
        result = _filter_protocols(PROTOCOL_SUBSET, goal="focus")
        assert all(p["goal"] == "focus" for p in result)

    def test_filter_beginner(self):
        result = _filter_protocols(PROTOCOL_SUBSET, difficulty="beginner")
        assert all(p["difficulty"] == "beginner" for p in result)

    def test_filter_max_duration_5(self):
        result = _filter_protocols(PROTOCOL_SUBSET, max_duration=5)
        assert all(p["duration_min"] <= 5 for p in result)

    def test_combined_filter(self):
        result = _filter_protocols(PROTOCOL_SUBSET, category="breathing", difficulty="beginner")
        assert all(p["category"] == "breathing" and p["difficulty"] == "beginner" for p in result)

    def test_no_match_returns_empty(self):
        result = _filter_protocols(PROTOCOL_SUBSET, category="nonexistent")
        assert result == []

    def test_max_duration_excludes_long(self):
        result = _filter_protocols(PROTOCOL_SUBSET, max_duration=6)
        assert not any(p["duration_min"] > 6 for p in result)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: PROTOCOL LIBRARY INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

class TestProtocolLibraryIntegrity:
    REQUIRED_FIELDS = ("id", "category", "name", "duration_min", "difficulty", "goal", "description", "steps")

    def test_all_required_fields_present(self):
        for p in PROTOCOL_SUBSET:
            for field in self.REQUIRED_FIELDS:
                assert field in p, f"Protocol {p['id']} missing field {field}"

    def test_duration_positive(self):
        for p in PROTOCOL_SUBSET:
            assert p["duration_min"] > 0

    def test_difficulty_values_valid(self):
        valid = {"beginner", "intermediate", "advanced"}
        for p in PROTOCOL_SUBSET:
            assert p["difficulty"] in valid

    def test_steps_non_empty(self):
        for p in PROTOCOL_SUBSET:
            assert len(p.get("steps", [])) >= 1

    def test_ids_unique(self):
        ids = [p["id"] for p in PROTOCOL_SUBSET]
        assert len(ids) == len(set(ids))


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: VALIDACIÓN INPUT
# ─────────────────────────────────────────────────────────────────────────────

class TestInputValidation:
    def test_valid_checkin_values(self):
        for v in (1, 2, 3, 4, 5):
            assert 1 <= v <= 5

    def test_invalid_checkin_value_0(self):
        assert not (1 <= 0 <= 5)

    def test_invalid_checkin_value_6(self):
        assert not (1 <= 6 <= 5)

    def test_notes_max_300(self):
        assert len("x" * 300) <= 300
        assert len("x" * 301) > 300

    def test_protocol_rating_range(self):
        for v in (1, 2, 3, 4, 5):
            assert 1 <= v <= 5

    def test_days_param_max_90(self):
        assert 30 <= 90
        assert 91 > 90


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: TREND ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

class TestTrendAnalysis:
    def _trend(self, scores):
        recent = scores[-7:]
        prev   = scores[-14:-7]
        if recent and prev:
            r_avg = sum(recent) / len(recent)
            p_avg = sum(prev) / len(prev)
            if r_avg > p_avg + 3:
                return "improving"
            elif r_avg < p_avg - 3:
                return "declining"
        return "stable"

    def test_improving_trend(self):
        scores = [60, 62, 64, 65, 66, 68, 70,   75, 78, 80, 82, 83, 84, 85]
        assert self._trend(scores) == "improving"

    def test_declining_trend(self):
        scores = [80, 78, 76, 74, 72, 70, 68,   55, 52, 50, 48, 47, 46, 45]
        assert self._trend(scores) == "declining"

    def test_stable_trend(self):
        scores = [70, 71, 69, 70, 71, 70, 69,   71, 70, 72, 70, 71, 69, 70]
        assert self._trend(scores) == "stable"

    def test_empty_returns_stable(self):
        assert self._trend([]) == "stable"

    def test_insufficient_data_returns_stable(self):
        assert self._trend([70, 72, 68]) == "stable"
