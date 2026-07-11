
# ─────────────────────────────────────────────────────────────────────────────
# SPRINT 17 TEST ADDITIONS
# ─────────────────────────────────────────────────────────────────────────────
import pytest
from datetime import date, timedelta


COUNTRY_FLAG_S17 = {
    "CL": "🇨🇱", "BR": "🇧🇷", "AR": "🇦🇷", "MX": "🇲🇽",
    "CO": "🇨🇴", "PE": "🇵🇪", "EC": "🇪🇨", "UY": "🇺🇾",
    "PY": "🇵🇾", "BO": "🇧🇴", "VE": "🇻🇪",
    "US": "🇺🇸", "ES": "🇪🇸", "PT": "🇵🇹",
}

SPORT_EMOJI_S17 = {
    "running": "🏃", "run": "🏃",
    "cycling": "🚴", "bike": "🚴", "riding": "🚴",
    "swimming": "🏊", "swim": "🏊",
    "triathlon": "🏁",
    "trail_running": "🏔️", "trail": "🏔️",
    "other": "⚡",
}

RECOVERY_LEVEL_LABEL_S17 = {
    "optimal":  "Forma óptima",
    "good":     "Bien recuperado",
    "moderate": "Recuperación moderada",
    "low":      "Fatiga acumulada",
    "critical": "Descanso urgente",
}


def _get_sport_emoji_s17(activity_type):
    sport_raw = (activity_type or "other").lower()
    sport_key = next((k for k in SPORT_EMOJI_S17 if k in sport_raw), "other")
    return SPORT_EMOJI_S17.get(sport_key, "⚡")


def _leaderboard_period_start_s17(period):
    today = date.today()
    if period == "week":
        return (today - timedelta(days=today.weekday())).isoformat()
    if period == "month":
        return today.replace(day=1).isoformat()
    if period == "year":
        return today.replace(month=1, day=1).isoformat()
    return "2000-01-01"


def _aggregate_metric_s17(activities, metric, sport_filter):
    total = 0.0
    for a in activities:
        act_sport = (a.get("activity_type") or "").lower()
        if sport_filter != "all" and sport_filter not in act_sport:
            continue
        if metric == "tss":
            total += a.get("tss") or 0.0
        elif metric == "distance_km":
            total += (a.get("distance_m") or 0) / 1000
        elif metric == "elevation_m":
            total += a.get("elevation_gain_m") or 0.0
        elif metric == "duration_h":
            total += (a.get("duration_s") or 0) / 3600
    return round(total, 2)


def _rank_users_s17(rows):
    sorted_rows = sorted(rows, key=lambda x: x["value"], reverse=True)
    for i, row in enumerate(sorted_rows, 1):
        row["rank"] = i
    return sorted_rows


def _comment_body_valid_s17(body):
    return isinstance(body, str) and 1 <= len(body.strip()) <= 500


def _visibility_valid_s17(v):
    return v in ("public", "followers", "private", "coach_only")


def _club_name_valid_s17(name):
    return isinstance(name, str) and 2 <= len(name.strip()) <= 100


def _challenge_dates_valid_s17(start, end):
    return start < end


def _challenge_goal_valid_s17(goal):
    return isinstance(goal, (int, float)) and goal > 0


class TestCountryFlagsS17:
    def test_latam_countries_present(self):
        for cc in ("CL", "BR", "AR", "MX", "CO", "PE"):
            assert cc in COUNTRY_FLAG_S17

    def test_chile_flag(self):
        assert COUNTRY_FLAG_S17["CL"] == "🇨🇱"

    def test_brazil_flag(self):
        assert COUNTRY_FLAG_S17["BR"] == "🇧🇷"

    def test_unknown_not_in_dict(self):
        assert "XX" not in COUNTRY_FLAG_S17

    def test_all_non_empty(self):
        for cc, flag in COUNTRY_FLAG_S17.items():
            assert flag, f"Empty flag: {cc}"


class TestSportEmojiS17:
    def test_running(self):
        assert _get_sport_emoji_s17("running") == "🏃"

    def test_cycling(self):
        assert _get_sport_emoji_s17("cycling") == "🚴"

    def test_swim(self):
        assert _get_sport_emoji_s17("swim") == "🏊"

    def test_triathlon(self):
        assert _get_sport_emoji_s17("triathlon") == "🏁"

    def test_unknown_defaults(self):
        assert _get_sport_emoji_s17("unknown") == "⚡"

    def test_none_defaults(self):
        assert _get_sport_emoji_s17(None) == "⚡"

    def test_partial_match_bike(self):
        assert _get_sport_emoji_s17("outdoor_bike") == "🚴"

    def test_partial_match_run(self):
        assert _get_sport_emoji_s17("trail_run") == "🏃"


class TestLeaderboardPeriodS17:
    def test_week_is_monday(self):
        start = _leaderboard_period_start_s17("week")
        d = date.fromisoformat(start)
        assert d.weekday() == 0

    def test_month_first_day(self):
        start = _leaderboard_period_start_s17("month")
        d = date.fromisoformat(start)
        assert d.day == 1

    def test_year_jan_first(self):
        start = _leaderboard_period_start_s17("year")
        d = date.fromisoformat(start)
        assert d.month == 1 and d.day == 1

    def test_alltime_old_date(self):
        assert _leaderboard_period_start_s17("alltime") == "2000-01-01"

    def test_all_periods_valid_iso(self):
        for p in ("week", "month", "year", "alltime"):
            s = _leaderboard_period_start_s17(p)
            assert len(s) == 10 and s[4] == '-'


class TestMetricAggregationS17:
    ACTS = [
        {"activity_type": "running",  "tss": 80,  "distance_m": 10000, "elevation_gain_m": 50,  "duration_s": 3600},
        {"activity_type": "cycling",  "tss": 120, "distance_m": 50000, "elevation_gain_m": 500, "duration_s": 7200},
        {"activity_type": "swimming", "tss": 40,  "distance_m": 3000,  "elevation_gain_m": 0,   "duration_s": 3000},
    ]

    def test_tss_all(self):
        assert _aggregate_metric_s17(self.ACTS, "tss", "all") == pytest.approx(240.0)

    def test_tss_running_only(self):
        assert _aggregate_metric_s17(self.ACTS, "tss", "run") == pytest.approx(80.0)

    def test_distance_all(self):
        assert _aggregate_metric_s17(self.ACTS, "distance_km", "all") == pytest.approx(63.0, abs=0.1)

    def test_elevation_all(self):
        assert _aggregate_metric_s17(self.ACTS, "elevation_m", "all") == pytest.approx(550.0)

    def test_duration_hours(self):
        assert _aggregate_metric_s17(self.ACTS, "duration_h", "all") == pytest.approx(3.833, abs=0.01)

    def test_no_match_sport(self):
        assert _aggregate_metric_s17(self.ACTS, "tss", "triathlon") == 0.0

    def test_empty_list(self):
        assert _aggregate_metric_s17([], "tss", "all") == 0.0

    def test_none_tss_zero(self):
        acts = [{"activity_type": "run", "tss": None, "distance_m": 0, "elevation_gain_m": 0, "duration_s": 0}]
        assert _aggregate_metric_s17(acts, "tss", "all") == 0.0


class TestRankingS17:
    def test_highest_is_first(self):
        rows = [
            {"user": {"id": "a"}, "value": 100.0},
            {"user": {"id": "b"}, "value": 250.0},
            {"user": {"id": "c"}, "value": 175.0},
        ]
        ranked = _rank_users_s17(rows)
        assert ranked[0]["user"]["id"] == "b"
        assert ranked[0]["rank"] == 1

    def test_ranks_sequential(self):
        rows = [{"user": {"id": str(i)}, "value": float(i)} for i in range(5)]
        ranked = _rank_users_s17(rows)
        assert [r["rank"] for r in ranked] == [1, 2, 3, 4, 5]

    def test_empty_rows(self):
        assert _rank_users_s17([]) == []

    def test_single_row_rank_1(self):
        rows = [{"user": {"id": "x"}, "value": 99.0}]
        assert _rank_users_s17(rows)[0]["rank"] == 1


class TestInputValidationS17:
    def test_valid_comment(self):
        assert _comment_body_valid_s17("Gran entrenamiento!") is True

    def test_empty_comment(self):
        assert _comment_body_valid_s17("") is False

    def test_whitespace_only(self):
        assert _comment_body_valid_s17("   ") is False

    def test_too_long_comment(self):
        assert _comment_body_valid_s17("x" * 501) is False

    def test_valid_visibility(self):
        for v in ("public", "followers", "private"):
            assert _visibility_valid_s17(v) is True

    def test_invalid_visibility(self):
        assert _visibility_valid_s17("everyone") is False

    def test_valid_club_name(self):
        assert _club_name_valid_s17("Tri Club LATAM") is True

    def test_too_short_club(self):
        assert _club_name_valid_s17("A") is False

    def test_valid_challenge_dates(self):
        assert _challenge_dates_valid_s17("2026-07-01", "2026-07-31") is True

    def test_same_dates_invalid(self):
        assert _challenge_dates_valid_s17("2026-07-01", "2026-07-01") is False

    def test_positive_goal(self):
        assert _challenge_goal_valid_s17(100.0) is True

    def test_zero_goal_invalid(self):
        assert _challenge_goal_valid_s17(0) is False


class TestRecoveryLabelsS17:
    def test_all_levels_present(self):
        for level in ("optimal", "good", "moderate", "low", "critical"):
            assert level in RECOVERY_LEVEL_LABEL_S17

    def test_optimal_mentions_forma(self):
        assert "ptima" in RECOVERY_LEVEL_LABEL_S17["optimal"]

    def test_critical_mentions_descanso(self):
        assert "descanso" in RECOVERY_LEVEL_LABEL_S17["critical"].lower()

    def test_unknown_level_not_in_dict(self):
        assert RECOVERY_LEVEL_LABEL_S17.get("unknown") is None
