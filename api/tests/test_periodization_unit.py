"""Sprint 31 — Season Periodization unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.periodization_service import (
    _phase_color,
    _phase_label,
    _phases_overlap,
    validate_no_overlap,
    _phase_dict,
    _month_markers,
    build_season_gantt,
    get_athlete_phases,
    VALID_PHASE_TYPES,
)
from api.models import TrainingPhase, GarminTrainingLoad


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tp(
    phase_type="base",
    start=None, end=None,
    ctl_target=None,
    tss_weekly=None,
    label=None,
    notes=None,
    pid="phase-1",
    coach_id="c1",
    athlete_id="a1",
):
    obj = MagicMock(spec=TrainingPhase)
    obj.id               = pid
    obj.coach_id         = coach_id
    obj.athlete_id       = athlete_id
    obj.phase_type       = phase_type
    obj.label            = label
    obj.start_date       = start or "2026-01-01"
    obj.end_date         = end   or "2026-03-31"
    obj.ctl_target       = ctl_target
    obj.tss_weekly_target = tss_weekly
    obj.notes            = notes
    obj.created_at       = None
    return obj


def _load(ctl=65.0):
    obj = MagicMock(spec=GarminTrainingLoad)
    obj.ctl      = ctl
    obj.date_iso = date.today().isoformat()
    return obj


def _make_db(phases=None, load=None):
    db = MagicMock()
    def qs(cls):
        q = MagicMock()
        q.filter.return_value  = q
        q.order_by.return_value = q
        q.all.return_value   = phases if phases is not None else []
        q.first.return_value = load
        return q
    db.query.side_effect = qs
    return db


# ── TestPhaseColor ────────────────────────────────────────────────────────────

class TestPhaseColor:
    def test_base_is_green(self):        assert _phase_color("base")       == "#10B981"
    def test_build_is_blue(self):        assert _phase_color("build")      == "#0EA5E9"
    def test_peak_is_gold(self):         assert _phase_color("peak")       == "#F0A500"
    def test_taper_is_purple(self):      assert _phase_color("taper")      == "#A855F7"
    def test_transition_muted(self):     assert _phase_color("transition") == "#7FB3CC"
    def test_recovery_red(self):         assert _phase_color("recovery")   == "#EF4444"
    def test_unknown_returns_default(self): assert _phase_color("unknown") == "#7FB3CC"


# ── TestPhaseLabel ────────────────────────────────────────────────────────────

class TestPhaseLabel:
    def test_base(self):       assert _phase_label("base")       == "Base"
    def test_build(self):      assert _phase_label("build")      == "Build"
    def test_peak(self):       assert _phase_label("peak")       == "Peak"
    def test_taper(self):      assert _phase_label("taper")      == "Taper"
    def test_transition(self): assert "ransici" in _phase_label("transition")
    def test_recovery(self):   assert "cuperaci" in _phase_label("recovery")
    def test_unknown(self):    assert _phase_label("foo") == "Foo"


# ── TestValidPhaseTypes ───────────────────────────────────────────────────────

class TestValidPhaseTypes:
    def test_all_expected_types_present(self):
        for t in ["base","build","peak","taper","transition","recovery"]:
            assert t in VALID_PHASE_TYPES

    def test_invalid_type_not_present(self):
        assert "random" not in VALID_PHASE_TYPES


# ── TestPhasesOverlap ─────────────────────────────────────────────────────────

class TestPhasesOverlap:
    def test_no_overlap_before(self):
        assert not _phases_overlap("2026-01-01","2026-03-31","2026-04-01","2026-06-30")

    def test_no_overlap_after(self):
        assert not _phases_overlap("2026-04-01","2026-06-30","2026-01-01","2026-03-31")

    def test_adjacent_is_not_overlap(self):
        # A ends on 03-31, B starts on 04-01: no overlap (start > end)
        assert not _phases_overlap("2026-01-01","2026-03-31","2026-04-01","2026-06-30")

    def test_partial_overlap_start(self):
        assert _phases_overlap("2026-03-01","2026-05-31","2026-01-01","2026-03-31")

    def test_partial_overlap_end(self):
        assert _phases_overlap("2026-01-01","2026-03-31","2026-03-01","2026-05-31")

    def test_contained_overlap(self):
        assert _phases_overlap("2026-01-01","2026-12-31","2026-03-01","2026-06-30")

    def test_exact_same_dates(self):
        assert _phases_overlap("2026-01-01","2026-03-31","2026-01-01","2026-03-31")

    def test_single_day_overlap(self):
        assert _phases_overlap("2026-01-01","2026-03-15","2026-03-15","2026-06-30")


# ── TestValidateNoOverlap ─────────────────────────────────────────────────────

class TestValidateNoOverlap:
    def test_no_existing_phases_ok(self):
        db = _make_db(phases=[])
        ok, err = validate_no_overlap("a1","2026-01-01","2026-03-31", db)
        assert ok is True
        assert err == ""

    def test_non_overlapping_ok(self):
        existing = [_tp(start="2026-04-01", end="2026-06-30", pid="p2")]
        db = _make_db(phases=existing)
        ok, err = validate_no_overlap("a1","2026-01-01","2026-03-31", db)
        assert ok is True

    def test_overlapping_returns_false(self):
        existing = [_tp(start="2026-03-01", end="2026-05-31", pid="p2")]
        db = _make_db(phases=existing)
        ok, err = validate_no_overlap("a1","2026-01-01","2026-04-30", db)
        assert ok is False
        assert err != ""

    def test_exclude_id_skips_self(self):
        existing = [_tp(start="2026-01-01", end="2026-03-31", pid="p1")]
        db = _make_db(phases=existing)
        ok, err = validate_no_overlap("a1","2026-01-01","2026-03-31", db, exclude_id="p1")
        assert ok is True


# ── TestPhaseDict ─────────────────────────────────────────────────────────────

class TestPhaseDict:
    def test_required_keys_present(self):
        ph = _tp("build", start="2026-04-01", end="2026-06-30", ctl_target=70.0)
        d  = _phase_dict(ph)
        for key in ["id","phase_type","label","color","start_date","end_date",
                    "ctl_target","duration_days","duration_weeks","is_active",
                    "is_past","is_future","ctl_gap"]:
            assert key in d, f"Missing key: {key}"

    def test_duration_days_computed(self):
        ph = _tp(start="2026-01-01", end="2026-01-31")
        d  = _phase_dict(ph)
        assert d["duration_days"] == 31  # inclusive

    def test_duration_weeks_computed(self):
        ph = _tp(start="2026-01-01", end="2026-01-28")
        d  = _phase_dict(ph)
        assert d["duration_weeks"] == pytest.approx(4.0, abs=0.1)

    def test_ctl_gap_computed_when_both_set(self):
        ph = _tp(ctl_target=80.0)
        d  = _phase_dict(ph, current_ctl=65.0)
        assert d["ctl_gap"] == pytest.approx(15.0)

    def test_ctl_gap_none_when_no_target(self):
        ph = _tp(ctl_target=None)
        d  = _phase_dict(ph, current_ctl=65.0)
        assert d["ctl_gap"] is None

    def test_ctl_gap_none_when_no_current(self):
        ph = _tp(ctl_target=80.0)
        d  = _phase_dict(ph, current_ctl=None)
        assert d["ctl_gap"] is None

    def test_label_fallback_to_phase_type_label(self):
        ph = _tp("peak", label=None)
        d  = _phase_dict(ph)
        assert d["label"] == "Peak"

    def test_custom_label_preserved(self):
        ph = _tp("build", label="Build 2 — Intensidad")
        d  = _phase_dict(ph)
        assert d["label"] == "Build 2 — Intensidad"

    def test_past_phase_flags(self):
        ph = _tp(start="2025-01-01", end="2025-03-31")
        d  = _phase_dict(ph)
        assert d["is_past"] is True
        assert d["is_active"] is False
        assert d["is_future"] is False

    def test_future_phase_flags(self):
        ph = _tp(start="2030-01-01", end="2030-03-31")
        d  = _phase_dict(ph)
        assert d["is_future"] is True
        assert d["is_active"] is False

    def test_color_matches_phase_type(self):
        ph = _tp("taper")
        d  = _phase_dict(ph)
        assert d["color"] == "#A855F7"


# ── TestMonthMarkers ──────────────────────────────────────────────────────────

class TestMonthMarkers:
    def test_two_months_two_markers(self):
        start = date(2026, 1, 1)
        end   = date(2026, 2, 28)
        total = (end - start).days
        markers = _month_markers(start, end, total)
        assert len(markers) >= 2

    def test_first_marker_at_zero(self):
        start = date(2026, 1, 1)
        end   = date(2026, 3, 31)
        total = (end - start).days
        markers = _month_markers(start, end, total)
        assert markers[0]["pct_offset"] == 0.0

    def test_marker_labels_contain_month_name(self):
        start = date(2026, 6, 1)
        end   = date(2026, 7, 31)
        total = (end - start).days
        markers = _month_markers(start, end, total)
        assert any("Jun" in m["label"] or "Jul" in m["label"] for m in markers)

    def test_zero_total_days_no_crash(self):
        start = date(2026, 1, 1)
        markers = _month_markers(start, start, 0)
        assert isinstance(markers, list)


# ── TestBuildSeasonGantt ──────────────────────────────────────────────────────

class TestBuildSeasonGantt:
    def test_no_phases_returns_empty(self):
        db = _make_db(phases=[])
        result = build_season_gantt("a1", db)
        assert result["has_phases"] is False
        assert result["phases"] == []

    def test_has_phases_true(self):
        phases = [_tp(start="2026-01-01", end="2026-03-31")]
        db = _make_db(phases=phases, load=_load(65.0))
        result = build_season_gantt("a1", db)
        assert result["has_phases"] is True

    def test_season_start_end_set(self):
        phases = [
            _tp("base",  start="2026-01-01", end="2026-03-31", pid="p1"),
            _tp("build", start="2026-04-01", end="2026-06-30", pid="p2"),
        ]
        db = _make_db(phases=phases, load=_load())
        result = build_season_gantt("a1", db)
        assert result["season_start"] == "2026-01-01"
        assert result["season_end"]   == "2026-06-30"

    def test_gantt_pct_first_phase_starts_at_zero(self):
        phases = [
            _tp("base",  start="2026-01-01", end="2026-03-31", pid="p1"),
            _tp("build", start="2026-04-01", end="2026-06-30", pid="p2"),
        ]
        db = _make_db(phases=phases, load=_load())
        result = build_season_gantt("a1", db)
        assert result["phases"][0]["gantt_pct_start"] == 0.0

    def test_gantt_pct_widths_sum_to_approx_100(self):
        phases = [
            _tp("base",  start="2026-01-01", end="2026-03-31", pid="p1"),
            _tp("build", start="2026-04-01", end="2026-06-30", pid="p2"),
        ]
        db = _make_db(phases=phases, load=_load())
        result = build_season_gantt("a1", db)
        total_width = sum(ph["gantt_pct_width"] for ph in result["phases"])
        assert abs(total_width - 100.0) < 2.0

    def test_current_ctl_from_load(self):
        phases = [_tp(start="2026-01-01", end="2026-12-31")]
        db = _make_db(phases=phases, load=_load(72.5))
        result = build_season_gantt("a1", db)
        assert result["current_ctl"] == 72.5

    def test_current_ctl_none_when_no_load(self):
        phases = [_tp(start="2026-01-01", end="2026-12-31")]
        db = _make_db(phases=phases, load=None)
        result = build_season_gantt("a1", db)
        assert result["current_ctl"] is None

    def test_month_markers_present(self):
        phases = [_tp(start="2026-01-01", end="2026-06-30")]
        db = _make_db(phases=phases, load=_load())
        result = build_season_gantt("a1", db)
        assert isinstance(result["month_markers"], list)
        assert len(result["month_markers"]) >= 1

    def test_top_level_keys(self):
        phases = [_tp()]
        db = _make_db(phases=phases, load=_load())
        result = build_season_gantt("a1", db)
        for k in ["has_phases","phases","month_markers","season_start",
                  "season_end","total_days","today_pct","current_ctl"]:
            assert k in result


# ── TestGetAthletePhases ──────────────────────────────────────────────────────

class TestGetAthletePhases:
    def test_empty_returns_empty_list(self):
        db = _make_db(phases=[], load=None)
        result = get_athlete_phases("a1", db)
        assert result == []

    def test_returns_list_of_dicts(self):
        db = _make_db(phases=[_tp()], load=_load(65.0))
        result = get_athlete_phases("a1", db)
        assert isinstance(result, list)
        assert isinstance(result[0], dict)

    def test_ctl_gap_computed_with_current_ctl(self):
        ph = _tp(ctl_target=80.0, start="2026-04-01", end="2026-06-30")
        db = _make_db(phases=[ph], load=_load(65.0))
        result = get_athlete_phases("a1", db)
        assert result[0]["ctl_gap"] == pytest.approx(15.0)

    def test_multiple_phases_returned(self):
        phases = [_tp(pid="p1"), _tp(pid="p2"), _tp(pid="p3")]
        db = _make_db(phases=phases, load=_load())
        result = get_athlete_phases("a1", db)
        assert len(result) == 3
