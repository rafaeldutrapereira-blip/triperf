"""Sprint 29 — Goal Race Intelligence unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations
import sys
import math
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.goal_race_service import (
    _ctl_target_for_distance,
    _taper_days_for_distance,
    _dist_label,
    _ctl_after_n_days,
    _required_daily_tss,
    _week_by_week_projection,
    _acwr_for_tss_daily,
    _tsb_form_label,
    compute_race_countdown,
    _CTL_DECAY,
    _ATL_DECAY,
)
from api.models import RaceEvent, GarminTrainingLoad


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_race(date_iso, distance="full", is_goal=True, name="Ironman Florida"):
    obj = MagicMock(spec=RaceEvent)
    obj.id          = "race-1"
    obj.name        = name
    obj.date_iso    = date_iso
    obj.distance    = distance
    obj.is_goal_race = is_goal
    return obj


def _make_load(ctl=65.0, atl=70.0, tss=70.0, date_iso=None):
    obj = MagicMock(spec=GarminTrainingLoad)
    obj.ctl      = ctl
    obj.atl      = atl
    obj.tsb      = ctl - atl
    obj.tss      = tss
    obj.date_iso = date_iso or date.today().isoformat()
    return obj


def _make_db(race=None, load=None, loads_28d=None):
    db = MagicMock()

    def query_side_effect(cls):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        if cls == RaceEvent:
            q.first.return_value = race
        elif cls == GarminTrainingLoad:
            q.first.return_value = load
            q.all.return_value = loads_28d if loads_28d is not None else ([load] * 10 if load else [])
        return q

    db.query.side_effect = query_side_effect
    return db


# ── TestCtlTargetForDistance ───────────────────────────────────────────────────

class TestCtlTargetForDistance:
    def test_sprint(self):     assert _ctl_target_for_distance("sprint") == 45
    def test_olympic(self):    assert _ctl_target_for_distance("olympic") == 60
    def test_half_703(self):   assert _ctl_target_for_distance("703") == 75
    def test_full_ironman(self): assert _ctl_target_for_distance("full") == 90
    def test_ironman_alias(self): assert _ctl_target_for_distance("ironman") == 90
    def test_marathon(self):   assert _ctl_target_for_distance("42k") == 65
    def test_half_marathon(self): assert _ctl_target_for_distance("21k") == 55
    def test_custom(self):     assert _ctl_target_for_distance("custom") == 65
    def test_none(self):       assert _ctl_target_for_distance(None) == 65
    def test_case_insensitive(self): assert _ctl_target_for_distance("FULL") == 90


# ── TestTaperDays ─────────────────────────────────────────────────────────────

class TestTaperDays:
    def test_sprint_7(self):   assert _taper_days_for_distance("sprint") == 7
    def test_olympic_10(self): assert _taper_days_for_distance("olympic") == 10
    def test_full_21(self):    assert _taper_days_for_distance("full") == 21
    def test_half_14(self):    assert _taper_days_for_distance("703") == 14
    def test_marathon_14(self):assert _taper_days_for_distance("42k") == 14
    def test_default_10(self): assert _taper_days_for_distance(None) == 10


# ── TestDistLabel ──────────────────────────────────────────────────────────────

class TestDistLabel:
    def test_ironman_label(self): assert _dist_label("full") == "Ironman"
    def test_olympic_label(self): assert "Ol" in _dist_label("olympic")
    def test_703_label(self):     assert "70.3" in _dist_label("703")


# ── TestCtlAfterNDays ─────────────────────────────────────────────────────────

class TestCtlAfterNDays:
    def test_zero_days_no_change(self):
        ctl = _ctl_after_n_days(60.0, 70.0, 0)
        assert ctl == 60.0

    def test_equilibrium_constant_tss(self):
        """With TSS equal to current CTL, CTL stays constant."""
        ctl = 60.0
        result = _ctl_after_n_days(ctl, ctl, 42)
        assert abs(result - ctl) < 0.5

    def test_higher_tss_increases_ctl(self):
        result = _ctl_after_n_days(60.0, 100.0, 42)
        assert result > 60.0

    def test_lower_tss_decreases_ctl(self):
        result = _ctl_after_n_days(60.0, 20.0, 42)
        assert result < 60.0

    def test_converges_to_tss_long_term(self):
        """After many days, CTL ≈ daily TSS."""
        result = _ctl_after_n_days(0.0, 80.0, 500)
        assert abs(result - 80.0) < 1.0

    def test_no_negative_with_zero_tss(self):
        result = _ctl_after_n_days(60.0, 0.0, 42)
        assert result >= 0.0


# ── TestRequiredDailyTss ───────────────────────────────────────────────────────

class TestRequiredDailyTss:
    def test_zero_build_days(self):
        assert _required_daily_tss(60.0, 80.0, 0) == 0.0

    def test_already_at_target(self):
        tss = _required_daily_tss(80.0, 80.0, 42)
        # Should return approximately 80 (maintaining equilibrium)
        assert tss >= 0.0

    def test_achieves_target(self):
        """Verify that applying the computed TSS actually reaches the target."""
        ctl_start  = 60.0
        ctl_target = 80.0
        build_days = 60
        tss_daily  = _required_daily_tss(ctl_start, ctl_target, build_days)
        ctl_result = _ctl_after_n_days(ctl_start, tss_daily, build_days)
        assert abs(ctl_result - ctl_target) < 0.5

    def test_larger_gap_requires_more_tss(self):
        tss_small = _required_daily_tss(60.0, 70.0, 60)
        tss_large = _required_daily_tss(60.0, 90.0, 60)
        assert tss_large > tss_small

    def test_more_days_requires_less_tss(self):
        """Same CTL gain over more days requires less daily TSS."""
        tss_short = _required_daily_tss(60.0, 80.0, 30)
        tss_long  = _required_daily_tss(60.0, 80.0, 90)
        assert tss_long < tss_short

    def test_non_negative(self):
        result = _required_daily_tss(80.0, 60.0, 42)
        assert result >= 0.0


# ── TestWeekByWeekProjection ───────────────────────────────────────────────────

class TestWeekByWeekProjection:
    def test_length_matches_total_days(self):
        rows = _week_by_week_projection(60.0, 65.0, 80.0, 40.0, 42, 14)
        assert len(rows) == 42 + 14 + 1

    def test_first_row_is_today(self):
        rows = _week_by_week_projection(60.0, 65.0, 80.0, 40.0, 14, 7)
        assert rows[0]["date_iso"] == date.today().isoformat()
        assert rows[0]["day_offset"] == 0

    def test_ctl_increases_during_build(self):
        rows = _week_by_week_projection(60.0, 65.0, 90.0, 45.0, 42, 14)
        build_rows = [r for r in rows if not r["is_taper"]]
        assert build_rows[-1]["ctl"] > build_rows[0]["ctl"]

    def test_ctl_decreases_during_taper(self):
        rows = _week_by_week_projection(60.0, 65.0, 90.0, 30.0, 42, 14)
        taper_rows = [r for r in rows if r["is_taper"]]
        if len(taper_rows) >= 2:
            assert taper_rows[-1]["ctl"] < taper_rows[0]["ctl"]

    def test_taper_flag_correct(self):
        build = 30
        taper = 10
        rows = _week_by_week_projection(60.0, 65.0, 80.0, 40.0, build, taper)
        for r in rows:
            if r["day_offset"] < build:
                assert not r["is_taper"]
            elif r["day_offset"] >= build:
                assert r["is_taper"]


# ── TestAcwrForTssDaily ───────────────────────────────────────────────────────

class TestAcwrForTssDaily:
    def test_equal_acute_chronic_is_1(self):
        assert _acwr_for_tss_daily(70.0, 70.0) == 1.0

    def test_higher_acute_acwr_above_1(self):
        acwr = _acwr_for_tss_daily(100.0, 70.0)
        assert acwr > 1.0

    def test_zero_chronic_returns_1(self):
        assert _acwr_for_tss_daily(70.0, 0.0) == 1.0

    def test_safe_zone(self):
        acwr = _acwr_for_tss_daily(70.0, 70.0)
        assert 0.8 <= acwr <= 1.3


# ── TestTsbFormLabel ───────────────────────────────────────────────────────────

class TestTsbFormLabel:
    def test_pico(self):       assert _tsb_form_label(15.0)  == "Forma Pico"
    def test_buena(self):      assert _tsb_form_label(8.0)   == "Buena Forma"
    def test_neutro(self):     assert _tsb_form_label(0.0)   == "Neutro"
    def test_fatiga_mod(self): assert _tsb_form_label(-10.0) == "Fatiga Moderada"
    def test_fatiga_alta(self):assert _tsb_form_label(-20.0) == "Fatiga Alta"
    def test_sobrecarga(self): assert _tsb_form_label(-30.0) == "Sobrecarga"
    def test_boundary_minus25(self): assert _tsb_form_label(-25.0) == "Sobrecarga"


# ── TestComputeRaceCountdown ───────────────────────────────────────────────────

class TestComputeRaceCountdown:
    def test_no_race_returns_false(self):
        db = _make_db(race=None, load=None, loads_28d=[])
        result = compute_race_countdown("user-1", db)
        assert result["has_race"] is False

    def test_has_race_returns_true(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        db = _make_db(race=_make_race(future), load=_make_load(ctl=65.0))
        result = compute_race_countdown("user-1", db)
        assert result["has_race"] is True

    def test_days_to_race_correct(self):
        future = (date.today() + timedelta(days=45)).isoformat()
        db = _make_db(race=_make_race(future), load=_make_load())
        result = compute_race_countdown("user-1", db)
        assert result["countdown"]["days_to_race"] == 45

    def test_ctl_gap_positive_when_below_target(self):
        future = (date.today() + timedelta(days=90)).isoformat()
        db = _make_db(race=_make_race(future, distance="full"), load=_make_load(ctl=60.0))
        result = compute_race_countdown("user-1", db)
        assert result["targets"]["ctl_gap"] == 30  # target 90 - current 60

    def test_already_fit_when_above_target(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        db = _make_db(race=_make_race(future, distance="sprint"), load=_make_load(ctl=70.0))
        result = compute_race_countdown("user-1", db)
        assert result["targets"]["already_fit"] is True
        assert result["targets"]["ctl_gap"] == 0

    def test_taper_days_match_distance(self):
        future = (date.today() + timedelta(days=90)).isoformat()
        db = _make_db(race=_make_race(future, distance="full"), load=_make_load())
        result = compute_race_countdown("user-1", db)
        assert result["countdown"]["taper_days"] == 21

    def test_build_days_is_days_minus_taper(self):
        days_total = 90
        future = (date.today() + timedelta(days=days_total)).isoformat()
        db = _make_db(race=_make_race(future, distance="full"), load=_make_load())
        result = compute_race_countdown("user-1", db)
        taper = result["countdown"]["taper_days"]
        build = result["countdown"]["build_days"]
        assert build == days_total - taper

    def test_projection_present_and_non_empty(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        db = _make_db(race=_make_race(future), load=_make_load())
        result = compute_race_countdown("user-1", db)
        assert len(result["projection"]) > 0

    def test_race_info_populated(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        db = _make_db(race=_make_race(future, name="IRONMAN Florida"), load=_make_load())
        result = compute_race_countdown("user-1", db)
        assert result["race"]["name"] == "IRONMAN Florida"

    def test_directive_message_non_empty(self):
        future = (date.today() + timedelta(days=90)).isoformat()
        db = _make_db(race=_make_race(future), load=_make_load())
        result = compute_race_countdown("user-1", db)
        assert len(result["directive"]["message"]) > 10

    def test_fallback_ctl_when_no_load(self):
        future = (date.today() + timedelta(days=90)).isoformat()
        db = _make_db(race=_make_race(future), load=None, loads_28d=[])
        result = compute_race_countdown("user-1", db)
        assert result["fitness"]["ctl_current"] == 40.0

    def test_peak_form_present(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        db = _make_db(race=_make_race(future), load=_make_load())
        result = compute_race_countdown("user-1", db)
        assert "peak_form" in result
        assert "date_iso" in result["peak_form"]

    def test_all_top_level_keys(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        db = _make_db(race=_make_race(future), load=_make_load())
        result = compute_race_countdown("user-1", db)
        for key in ["has_race","race","countdown","fitness","targets","directive","peak_form","projection"]:
            assert key in result
