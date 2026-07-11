"""Sprint 35 — Athlete Calendar unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.calendar_service import (
    get_monthly_calendar,
    get_weekly_summary,
    get_upcoming_workouts,
    SPORT_COLORS,
    _color,
    _rx_to_dict,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _rx(title="Z2 Bike", sport="bike", status="pending",
        date_iso=None, tss=80.0, dur=90, rid=None):
    r = MagicMock()
    r.id           = rid or "rx-1"
    r.title        = title
    r.sport        = sport
    r.status       = status
    r.date_iso     = date_iso or date.today().isoformat()
    r.tss_target   = tss
    r.duration_min = dur
    return r


def _load(date_iso=None, tss=90.0, ctl=55.0, atl=60.0, tsb=-5.0):
    l = MagicMock()
    l.date_iso   = date_iso or date.today().isoformat()
    l.tss_actual = tss
    l.ctl        = ctl
    l.atl        = atl
    l.tsb        = tsb
    return l


def _race(name="Ironman Chile", date_iso=None, uid="ath-1", goal=False, dist="full"):
    r = MagicMock()
    r.id           = "race-1"
    r.name         = name
    r.date_iso     = date_iso or date.today().isoformat()
    r.user_id      = uid
    r.is_goal_race = goal
    r.distance     = dist
    return r


def _fb(rx_id="rx-1", rpe=7, tss=85.0, notes="Good session"):
    f = MagicMock()
    f.id              = "fb-1"
    f.prescription_id = rx_id
    f.rpe             = rpe
    f.tss_actual      = tss
    f.notes           = notes
    return f


def _make_db(rxs=None, loads=None, races=None, feedbacks=None):
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value   = q
    q.order_by.return_value = q
    # Feedback query is conditional: only called when rxs is non-empty.
    _rxs = rxs or []
    if _rxs:
        side = [_rxs, feedbacks or [], loads or [], races or []]
    else:
        side = [_rxs, loads or [], races or []]
    q.all.side_effect = side
    return db


def _make_weekly_db(rxs=None, loads=None, feedbacks=None):
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value   = q
    q.order_by.return_value = q
    _rxs = rxs or []
    if _rxs:
        side = [_rxs, feedbacks or [], loads or []]
    else:
        side = [_rxs, loads or []]
    q.all.side_effect = side
    return db


def _make_upcoming_db(rxs=None, races=None):
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value   = q
    q.order_by.return_value = q
    q.all.side_effect       = [rxs or [], races or []]
    return db


# ── _color helper ──────────────────────────────────────────────────────────────

class TestColorHelper:
    def test_known_sport_returns_color(self):
        assert _color("swim") == SPORT_COLORS["swim"]
        assert _color("bike") == SPORT_COLORS["bike"]
        assert _color("run")  == SPORT_COLORS["run"]

    def test_unknown_sport_returns_other(self):
        assert _color("yoga") == SPORT_COLORS["other"]

    def test_case_insensitive(self):
        assert _color("BIKE") == SPORT_COLORS["bike"]

    def test_none_returns_other(self):
        assert _color(None) == SPORT_COLORS["other"]

    def test_all_defined_sports(self):
        for sport in ("swim","bike","run","strength","brick","rest","other"):
            assert _color(sport) == SPORT_COLORS[sport]


# ── _rx_to_dict ────────────────────────────────────────────────────────────────

class TestRxToDict:
    def test_required_keys_present(self):
        rx = _rx()
        d  = _rx_to_dict(rx)
        for key in ("id","title","sport","color","status","status_label","tss_target","duration_min","date_iso"):
            assert key in d

    def test_color_matches_sport(self):
        rx = _rx(sport="run")
        d  = _rx_to_dict(rx)
        assert d["color"] == SPORT_COLORS["run"]

    def test_status_label_translated(self):
        rx = _rx(status="completed")
        d  = _rx_to_dict(rx)
        assert d["status_label"] == "Completado"

    def test_pending_label(self):
        rx = _rx(status="pending")
        d  = _rx_to_dict(rx)
        assert d["status_label"] == "Pendiente"

    def test_no_feedback_key_when_none(self):
        rx = _rx()
        d  = _rx_to_dict(rx, feedback=None)
        assert "feedback" not in d

    def test_feedback_key_present_when_given(self):
        rx = _rx()
        fb = _fb()
        d  = _rx_to_dict(rx, feedback=fb)
        assert "feedback" in d
        assert d["feedback"]["rpe"] == fb.rpe


# ── get_monthly_calendar ───────────────────────────────────────────────────────

class TestGetMonthlyCalendar:
    def test_returns_required_keys(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        for key in ("year","month","month_name","days_in_month","first_weekday","days","summary"):
            assert key in r

    def test_days_count_matches_month(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        assert len(r["days"]) == 31

    def test_february_non_leap(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 2, db)
        assert len(r["days"]) == 28

    def test_february_leap(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2024, 2, db)
        assert len(r["days"]) == 29

    def test_first_weekday_july_2026(self):
        # July 2026 starts on Wednesday (weekday 2)
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        assert r["first_weekday"] == 2

    def test_day_structure(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        day = r["days"][0]
        for key in ("date","weekday","is_today","is_past","prescriptions","tss_actual","races","rx_total","rx_done"):
            assert key in day

    def test_prescription_assigned_to_correct_day(self):
        today = date(2026, 7, 1)
        rx1   = _rx(date_iso="2026-07-01", rid="r1")
        rx2   = _rx(date_iso="2026-07-15", rid="r2")
        db    = _make_db(rxs=[rx1, rx2])
        r     = get_monthly_calendar("ath-1", 2026, 7, db)
        day1  = next(d for d in r["days"] if d["date"] == "2026-07-01")
        day15 = next(d for d in r["days"] if d["date"] == "2026-07-15")
        assert len(day1["prescriptions"]) == 1
        assert len(day15["prescriptions"]) == 1

    def test_empty_day_has_zero_rx_total(self):
        db  = _make_db()
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        day = r["days"][5]
        assert day["rx_total"] == 0

    def test_compliance_pct_none_when_no_rx(self):
        db  = _make_db()
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        day = r["days"][0]
        assert day["compliance_pct"] is None

    def test_compliance_pct_100_when_all_done(self):
        rx = _rx(date_iso="2026-07-01", status="completed")
        db = _make_db(rxs=[rx])
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        day = next(d for d in r["days"] if d["date"] == "2026-07-01")
        assert day["compliance_pct"] == 100

    def test_compliance_pct_50_when_half_done(self):
        rx1 = _rx(date_iso="2026-07-01", status="completed", rid="r1")
        rx2 = _rx(date_iso="2026-07-01", status="pending",   rid="r2")
        db  = _make_db(rxs=[rx1, rx2])
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        day = next(d for d in r["days"] if d["date"] == "2026-07-01")
        assert day["compliance_pct"] == 50

    def test_tss_actual_from_garmin_load(self):
        ld  = _load(date_iso="2026-07-05", tss=120.0)
        db  = _make_db(loads=[ld])
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        day = next(d for d in r["days"] if d["date"] == "2026-07-05")
        assert day["tss_actual"] == 120.0

    def test_ctl_from_garmin_load(self):
        ld  = _load(date_iso="2026-07-10", ctl=65.0)
        db  = _make_db(loads=[ld])
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        day = next(d for d in r["days"] if d["date"] == "2026-07-10")
        assert day["ctl"] == 65.0

    def test_race_assigned_to_correct_day(self):
        r_race = _race(date_iso="2026-07-20", name="Test Race")
        db     = _make_db(races=[r_race])
        r      = get_monthly_calendar("ath-1", 2026, 7, db)
        day    = next(d for d in r["days"] if d["date"] == "2026-07-20")
        assert len(day["races"]) == 1
        assert day["races"][0]["name"] == "Test Race"

    def test_summary_total_rx_correct(self):
        rx1 = _rx(date_iso="2026-07-01", rid="r1")
        rx2 = _rx(date_iso="2026-07-02", rid="r2")
        db  = _make_db(rxs=[rx1, rx2])
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        assert r["summary"]["total_rx"] == 2

    def test_summary_compliance_none_when_no_rx(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        assert r["summary"]["compliance_pct"] is None

    def test_summary_tss_planned(self):
        rx1 = _rx(date_iso="2026-07-01", tss=80, rid="r1")
        rx2 = _rx(date_iso="2026-07-02", tss=60, rid="r2")
        db  = _make_db(rxs=[rx1, rx2])
        r   = get_monthly_calendar("ath-1", 2026, 7, db)
        assert r["summary"]["tss_planned"] == 140.0

    def test_summary_races_count(self):
        races = [_race(date_iso="2026-07-15"), _race(date_iso="2026-07-28")]
        db    = _make_db(races=races)
        r     = get_monthly_calendar("ath-1", 2026, 7, db)
        assert r["summary"]["races_count"] == 2

    def test_year_and_month_echoed(self):
        db = _make_db()
        r  = get_monthly_calendar("ath-1", 2026, 7, db)
        assert r["year"] == 2026
        assert r["month"] == 7


# ── get_weekly_summary ─────────────────────────────────────────────────────────

class TestGetWeeklySummary:
    def _ws(self):
        today = date.today()
        return today - timedelta(days=today.weekday())

    def test_returns_required_keys(self):
        db = _make_weekly_db()
        r  = get_weekly_summary("ath-1", self._ws(), db)
        for key in ("week_start","week_end","total_rx","total_done","compliance_pct",
                    "tss_planned","tss_garmin","ctl_end","tsb_end","sports"):
            assert key in r

    def test_week_end_is_6_days_after_start(self):
        ws = self._ws()
        db = _make_weekly_db()
        r  = get_weekly_summary("ath-1", ws, db)
        assert r["week_end"] == (ws + timedelta(days=6)).isoformat()

    def test_total_rx_zero_when_empty(self):
        db = _make_weekly_db()
        r  = get_weekly_summary("ath-1", self._ws(), db)
        assert r["total_rx"] == 0

    def test_compliance_pct_none_when_no_rx(self):
        db = _make_weekly_db()
        r  = get_weekly_summary("ath-1", self._ws(), db)
        assert r["compliance_pct"] is None

    def test_compliance_100_all_done(self):
        ws  = self._ws()
        rx  = _rx(date_iso=ws.isoformat(), status="completed")
        db  = _make_weekly_db(rxs=[rx])
        r   = get_weekly_summary("ath-1", ws, db)
        assert r["compliance_pct"] == 100

    def test_sport_breakdown_created(self):
        ws = self._ws()
        rx = _rx(date_iso=ws.isoformat(), sport="swim", status="completed")
        db = _make_weekly_db(rxs=[rx])
        r  = get_weekly_summary("ath-1", ws, db)
        assert "swim" in r["sports"]

    def test_sport_tss_target_aggregated(self):
        ws  = self._ws()
        rx1 = _rx(date_iso=ws.isoformat(), sport="bike", tss=80, rid="r1")
        rx2 = _rx(date_iso=ws.isoformat(), sport="bike", tss=60, rid="r2")
        db  = _make_weekly_db(rxs=[rx1, rx2])
        r   = get_weekly_summary("ath-1", ws, db)
        assert r["sports"]["bike"]["tss_target"] == 140.0

    def test_garmin_tss_summed(self):
        ws  = self._ws()
        l1  = _load(date_iso=ws.isoformat(),              tss=90)
        l2  = _load(date_iso=(ws+timedelta(1)).isoformat(), tss=75)
        db  = _make_weekly_db(loads=[l1, l2])
        r   = get_weekly_summary("ath-1", ws, db)
        assert r["tss_garmin"] == 165.0

    def test_ctl_end_from_latest_load(self):
        ws  = self._ws()
        l1  = _load(date_iso=ws.isoformat(),              ctl=60)
        l2  = _load(date_iso=(ws+timedelta(2)).isoformat(), ctl=65)
        db  = _make_weekly_db(loads=[l1, l2])
        r   = get_weekly_summary("ath-1", ws, db)
        assert r["ctl_end"] == 65

    def test_ctl_end_none_when_no_loads(self):
        db = _make_weekly_db()
        r  = get_weekly_summary("ath-1", self._ws(), db)
        assert r["ctl_end"] is None

    def test_week_start_echoed(self):
        ws = self._ws()
        db = _make_weekly_db()
        r  = get_weekly_summary("ath-1", ws, db)
        assert r["week_start"] == ws.isoformat()

    def test_tss_planned_sum(self):
        ws  = self._ws()
        rx1 = _rx(date_iso=ws.isoformat(), tss=100, rid="r1")
        rx2 = _rx(date_iso=ws.isoformat(), tss=50,  rid="r2")
        db  = _make_weekly_db(rxs=[rx1, rx2])
        r   = get_weekly_summary("ath-1", ws, db)
        assert r["tss_planned"] == 150.0


# ── get_upcoming_workouts ──────────────────────────────────────────────────────

class TestGetUpcomingWorkouts:
    def test_returns_required_keys(self):
        db = _make_upcoming_db()
        r  = get_upcoming_workouts("ath-1", 7, db)
        for key in ("from_date","to_date","days","total_pending","total_tss_planned","schedule"):
            assert key in r

    def test_days_echoed(self):
        db = _make_upcoming_db()
        r  = get_upcoming_workouts("ath-1", 7, db)
        assert r["days"] == 7

    def test_from_date_is_today(self):
        db = _make_upcoming_db()
        r  = get_upcoming_workouts("ath-1", 7, db)
        assert r["from_date"] == date.today().isoformat()

    def test_to_date_is_today_plus_days_minus_1(self):
        db = _make_upcoming_db()
        r  = get_upcoming_workouts("ath-1", 7, db)
        expected = (date.today() + timedelta(days=6)).isoformat()
        assert r["to_date"] == expected

    def test_empty_when_no_pending(self):
        db = _make_upcoming_db()
        r  = get_upcoming_workouts("ath-1", 7, db)
        assert r["total_pending"] == 0
        assert r["schedule"] == []

    def test_prescription_grouped_by_date(self):
        today = date.today().isoformat()
        rx1   = _rx(date_iso=today, rid="r1")
        rx2   = _rx(date_iso=today, rid="r2")
        db    = _make_upcoming_db(rxs=[rx1, rx2])
        r     = get_upcoming_workouts("ath-1", 7, db)
        assert r["total_pending"] == 2
        assert len(r["schedule"]) == 1
        assert len(r["schedule"][0]["prescriptions"]) == 2

    def test_race_included_in_schedule(self):
        race = _race(date_iso=date.today().isoformat())
        db   = _make_upcoming_db(races=[race])
        r    = get_upcoming_workouts("ath-1", 7, db)
        # race appears in schedule even without prescriptions
        assert len(r["schedule"]) == 1
        assert len(r["schedule"][0]["races"]) == 1

    def test_tss_planned_sum(self):
        today = date.today().isoformat()
        rx1   = _rx(date_iso=today, tss=80, rid="r1")
        rx2   = _rx(date_iso=today, tss=60, rid="r2")
        db    = _make_upcoming_db(rxs=[rx1, rx2])
        r     = get_upcoming_workouts("ath-1", 7, db)
        assert r["total_tss_planned"] == 140.0

    def test_schedule_sorted_by_date(self):
        d1 = date.today().isoformat()
        d2 = (date.today() + timedelta(days=2)).isoformat()
        rx1 = _rx(date_iso=d2, rid="r1")
        rx2 = _rx(date_iso=d1, rid="r2")
        db  = _make_upcoming_db(rxs=[rx1, rx2])
        r   = get_upcoming_workouts("ath-1", 7, db)
        dates = [d["date"] for d in r["schedule"]]
        assert dates == sorted(dates)

    def test_tss_none_handled_gracefully(self):
        today = date.today().isoformat()
        rx    = _rx(date_iso=today, tss=None)
        rx.tss_target = None
        db    = _make_upcoming_db(rxs=[rx])
        r     = get_upcoming_workouts("ath-1", 7, db)
        assert r["total_tss_planned"] == 0.0


# ── SPORT_COLORS sanity ────────────────────────────────────────────────────────

class TestSportColors:
    def test_all_values_are_hex(self):
        for k, v in SPORT_COLORS.items():
            assert v.startswith("#"), f"{k} color should be hex: {v}"

    def test_has_all_expected_sports(self):
        for sport in ("swim","bike","run","strength","brick","rest","other"):
            assert sport in SPORT_COLORS

    def test_colors_are_unique(self):
        colors = list(SPORT_COLORS.values())
        assert len(set(colors)) == len(colors)
