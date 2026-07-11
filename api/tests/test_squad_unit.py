"""Sprint 30 — Coach Squad Overview unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.squad_service import (
    _risk_level,
    _ctl_trend,
    _athlete_squad_card,
    _coach_group_ids,
    _group_athlete_ids,
    get_squad_overview,
    _RISK_ORDER,
)
from api.models import (
    User,
    GarminTrainingLoad,
    RecoveryScore,
    MentalFatigueScore,
    BloodLabAlert,
    WorkoutPrescription,
    RaceEvent,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _u(uid="a1", email="a@x.com", nombre="Ana"):
    obj = MagicMock(spec=User)
    obj.id     = uid
    obj.email  = email
    obj.nombre = nombre
    obj.activo = True
    return obj


def _load(ctl=65.0, atl=70.0, tss=70.0, acwr=None, date_iso=None):
    obj = MagicMock(spec=GarminTrainingLoad)
    obj.ctl      = ctl
    obj.atl      = atl
    obj.tss      = tss
    obj.acwr     = acwr
    obj.date_iso = date_iso or date.today().isoformat()
    return obj


def _rec(score=75, date_iso=None):
    obj = MagicMock(spec=RecoveryScore)
    obj.score    = score
    obj.date_iso = date_iso or date.today().isoformat()
    return obj


def _mfs(score=80, date_iso=None):
    obj = MagicMock(spec=MentalFatigueScore)
    obj.score    = score
    obj.date_iso = date_iso or date.today().isoformat()
    return obj


def _alert(severity="critical"):
    obj = MagicMock(spec=BloodLabAlert)
    obj.severity = severity
    return obj


def _rx(status="completed", date_iso=None):
    obj = MagicMock(spec=WorkoutPrescription)
    obj.status   = status
    obj.date_iso = date_iso or date.today().isoformat()
    return obj


def _race(days_ahead=45, name="Ironman"):
    obj = MagicMock(spec=RaceEvent)
    obj.name     = name
    obj.date_iso = (date.today() + timedelta(days=days_ahead)).isoformat()
    return obj


def _make_athlete_db(
    loads=None, rec=None, mfs=None, alert=None, rxs=None, race=None
):
    """Build a mock DB whose query().filter()... chains return appropriate data."""
    db = MagicMock()

    def query_side(cls):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q

        if cls == GarminTrainingLoad:
            q.all.return_value = loads if loads is not None else []
            q.first.return_value = loads[0] if loads else None
        elif cls == RecoveryScore:
            q.first.return_value = rec
        elif cls == MentalFatigueScore:
            q.first.return_value = mfs
        elif cls == BloodLabAlert:
            q.first.return_value = alert
        elif cls == WorkoutPrescription:
            q.all.return_value = rxs if rxs is not None else []
        elif cls == RaceEvent:
            q.first.return_value = race
        return q

    db.query.side_effect = query_side
    return db


def _make_squad_db(group_ids=None, athlete_ids=None, athletes=None):
    """Mock for get_squad_overview.

    Uses db.execute for raw SQL group/member lookups (avoiding ORM naming collision),
    and db.query for per-athlete data queries.
    """
    db    = MagicMock()
    gids  = group_ids   or []
    aids  = athlete_ids or []
    athl  = athletes    or []

    _call_count = [0]

    def execute_side(stmt, params=None):
        result = MagicMock()
        _call_count[0] += 1
        if _call_count[0] == 1:
            # SELECT id FROM groups WHERE coach_id = :cid
            result.fetchall.return_value = [(g,) for g in gids]
        else:
            # SELECT DISTINCT athlete_id FROM group_members WHERE ...
            result.fetchall.return_value = [(a,) for a in aids]
        return result

    db.execute.side_effect = execute_side

    def query_side(cls):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value    = q
        if cls == User:
            q.all.return_value = athl
        else:
            q.all.return_value   = []
            q.first.return_value = None
        return q

    db.query.side_effect = query_side
    return db


# ── TestRiskLevel ────────────────────────────────────────────────────────────

class TestRiskLevel:
    def test_blood_critical_is_critical(self):
        assert _risk_level(None, None, 0, True) == "critical"

    def test_blood_critical_overrides_ok(self):
        assert _risk_level(1.0, 90, 0, True) == "critical"

    def test_acwr_above_1_5_critical(self):
        assert _risk_level(1.6, None, 0, False) == "critical"

    def test_acwr_exactly_1_5_is_warning(self):
        # 1.5 is NOT > 1.5, so falls to warning check (> 1.3)
        assert _risk_level(1.5, None, 0, False) == "warning"

    def test_acwr_1_4_is_warning(self):
        assert _risk_level(1.4, None, 0, False) == "warning"

    def test_recovery_below_35_is_warning(self):
        assert _risk_level(1.0, 30, 0, False) == "warning"

    def test_recovery_35_is_ok(self):
        assert _risk_level(1.0, 35, 0, False) == "ok"

    def test_three_missed_rxs_is_warning(self):
        assert _risk_level(1.0, 80, 3, False) == "warning"

    def test_two_missed_rxs_is_ok(self):
        assert _risk_level(1.0, 80, 2, False) == "ok"

    def test_no_data_is_unknown(self):
        assert _risk_level(None, None, 0, False) == "unknown"

    def test_ok_baseline(self):
        assert _risk_level(1.1, 70, 0, False) == "ok"


# ── TestCtlTrend ─────────────────────────────────────────────────────────────

class TestCtlTrend:
    def test_empty_loads_stable(self):
        assert _ctl_trend([]) == "stable"

    def test_single_load_stable(self):
        assert _ctl_trend([_load(60)]) == "stable"

    def test_increasing_ctl_up(self):
        recent = [_load(ctl=70)] * 7
        prior  = [_load(ctl=60)] * 7
        assert _ctl_trend(recent + prior) == "up"

    def test_decreasing_ctl_down(self):
        recent = [_load(ctl=55)] * 7
        prior  = [_load(ctl=65)] * 7
        assert _ctl_trend(recent + prior) == "down"

    def test_equal_averages_stable(self):
        loads = [_load(ctl=65)] * 14
        assert _ctl_trend(loads) == "stable"

    def test_small_delta_under_1_stable(self):
        recent = [_load(ctl=65.5)] * 7
        prior  = [_load(ctl=65.0)] * 7
        assert _ctl_trend(recent + prior) == "stable"


# ── TestAthleteSquadCard ─────────────────────────────────────────────────────

class TestAthleteSquadCard:
    def test_returns_required_keys(self):
        db   = _make_athlete_db()
        card = _athlete_squad_card(_u(), db)
        for key in ["athlete_id","name","email","ctl","acwr","ctl_trend",
                    "tss_7d","recovery_score","mental_score","blood_critical",
                    "rx_total_7d","rx_completed_7d","rx_missed",
                    "compliance_pct","days_to_race","race_name","risk"]:
            assert key in card, f"Missing key: {key}"

    def test_no_loads_ctl_is_none(self):
        db   = _make_athlete_db(loads=[])
        card = _athlete_squad_card(_u(), db)
        assert card["ctl"] is None

    def test_ctl_populated_from_latest_load(self):
        db   = _make_athlete_db(loads=[_load(ctl=72.0)])
        card = _athlete_squad_card(_u(), db)
        assert card["ctl"] == 72.0

    def test_stored_acwr_preferred(self):
        db   = _make_athlete_db(loads=[_load(ctl=65, atl=70, acwr=1.35)])
        card = _athlete_squad_card(_u(), db)
        assert card["acwr"] == 1.35

    def test_recovery_score_populated(self):
        db   = _make_athlete_db(rec=_rec(score=55))
        card = _athlete_squad_card(_u(), db)
        assert card["recovery_score"] == 55

    def test_blood_critical_true(self):
        db   = _make_athlete_db(alert=_alert("critical"))
        card = _athlete_squad_card(_u(), db)
        assert card["blood_critical"] is True

    def test_blood_critical_false_when_none(self):
        db   = _make_athlete_db(alert=None)
        card = _athlete_squad_card(_u(), db)
        assert card["blood_critical"] is False

    def test_compliance_computed(self):
        today  = date.today().isoformat()
        rxs    = [_rx("completed", today), _rx("completed", today), _rx("pending", today)]
        db     = _make_athlete_db(rxs=rxs)
        card   = _athlete_squad_card(_u(), db)
        assert card["compliance_pct"] == 67  # 2/3

    def test_compliance_none_when_no_rxs(self):
        db   = _make_athlete_db(rxs=[])
        card = _athlete_squad_card(_u(), db)
        assert card["compliance_pct"] is None

    def test_days_to_race_computed(self):
        db   = _make_athlete_db(race=_race(30, "Race X"))
        card = _athlete_squad_card(_u(), db)
        assert card["days_to_race"] == 30
        assert card["race_name"] == "Race X"

    def test_risk_critical_when_blood_critical(self):
        db   = _make_athlete_db(alert=_alert("critical"))
        card = _athlete_squad_card(_u(), db)
        assert card["risk"] == "critical"

    def test_risk_ok_baseline(self):
        db   = _make_athlete_db(
            loads=[_load(ctl=65, atl=70, acwr=1.1)],
            rec=_rec(score=75),
            rxs=[],
            alert=None,
        )
        card = _athlete_squad_card(_u(), db)
        assert card["risk"] == "ok"

    def test_tss_7d_summed(self):
        loads = [_load(tss=80)] * 7
        db    = _make_athlete_db(loads=loads)
        card  = _athlete_squad_card(_u(), db)
        assert card["tss_7d"] == pytest.approx(560.0)


# ── TestCoachGroupIds / TestGroupAthleteIds ──────────────────────────────────

class TestCoachGroupIds:
    def test_returns_ids_from_execute(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [("g1",), ("g2",)]
        result = _coach_group_ids("coach1", db)
        assert result == ["g1", "g2"]

    def test_empty_when_no_groups(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        result = _coach_group_ids("coach1", db)
        assert result == []


class TestGroupAthleteIds:
    def test_returns_athlete_ids(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [("a1",), ("a2",)]
        result = _group_athlete_ids(["g1"], db)
        assert result == ["a1", "a2"]

    def test_empty_group_ids_returns_empty(self):
        result = _group_athlete_ids([], MagicMock())
        assert result == []


# ── TestGetSquadOverview ─────────────────────────────────────────────────────

class TestGetSquadOverview:
    def test_no_groups_returns_empty(self):
        coach = _u("coach1")
        db    = _make_squad_db(group_ids=[], athlete_ids=[], athletes=[])
        result = get_squad_overview(coach, db)
        assert result["squad_size"] == 0
        assert result["athletes"]   == []

    def test_empty_group_returns_empty(self):
        coach  = _u("c1")
        db     = _make_squad_db(group_ids=["g1"], athlete_ids=[], athletes=[])
        result = get_squad_overview(coach, db)
        assert result["squad_size"] == 0

    def test_squad_size_matches_athletes(self):
        athletes = [_u("a1"), _u("a2"), _u("a3")]
        db       = _make_squad_db(
            group_ids=["g1"],
            athlete_ids=["a1","a2","a3"],
            athletes=athletes,
        )
        result = get_squad_overview(_u("c1"), db)
        assert result["squad_size"] == 3

    def test_top_level_keys_present(self):
        db     = _make_squad_db(group_ids=["g1"], athlete_ids=["a1"], athletes=[_u("a1")])
        result = get_squad_overview(_u("c1"), db)
        for k in ["squad_size","athletes","summary"]:
            assert k in result

    def test_summary_keys_present(self):
        db     = _make_squad_db(group_ids=["g1"], athlete_ids=["a1"], athletes=[_u("a1")])
        result = get_squad_overview(_u("c1"), db)
        for k in ["critical","warning","ok","unknown"]:
            assert k in result["summary"]

    def test_summary_total_matches_squad_size(self):
        athletes = [_u("a1"), _u("a2")]
        db       = _make_squad_db(
            group_ids=["g1"], athlete_ids=["a1","a2"], athletes=athletes
        )
        result = get_squad_overview(_u("c1"), db)
        s     = result["summary"]
        total = s["critical"] + s["warning"] + s["ok"] + s["unknown"]
        assert total == result["squad_size"]

    def test_athletes_list_contains_dicts(self):
        db     = _make_squad_db(group_ids=["g1"], athlete_ids=["a1"], athletes=[_u("a1")])
        result = get_squad_overview(_u("c1"), db)
        assert isinstance(result["athletes"], list)
        if result["athletes"]:
            assert isinstance(result["athletes"][0], dict)

    def test_risk_order_critical_sorts_first(self):
        assert _RISK_ORDER["critical"] < _RISK_ORDER["warning"]
        assert _RISK_ORDER["warning"]  < _RISK_ORDER["unknown"]
        assert _RISK_ORDER["unknown"]  < _RISK_ORDER["ok"]

    def test_deduplication_of_athlete_in_multiple_groups(self):
        """execute returns unique athlete_ids (DB-level DISTINCT), service deduplicates too."""
        athlete = _u("a1")
        # Even if execute returned two rows for same athlete, dict.fromkeys deduplicates
        db = MagicMock()
        _call = [0]
        def ex(stmt, params=None):
            r = MagicMock()
            _call[0] += 1
            if _call[0] == 1:
                r.fetchall.return_value = [("g1",), ("g2",)]
            else:
                r.fetchall.return_value = [("a1",), ("a1",)]  # duplicate
            return r
        db.execute.side_effect = ex
        def qs(cls):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            q.limit.return_value    = q
            if cls == User:
                q.all.return_value = [athlete]
            else:
                q.all.return_value   = []
                q.first.return_value = None
            return q
        db.query.side_effect = qs
        result = get_squad_overview(_u("c1"), db)
        assert result["squad_size"] == 1

    def test_single_athlete_card_has_risk(self):
        db     = _make_squad_db(group_ids=["g1"], athlete_ids=["a1"], athletes=[_u("a1")])
        result = get_squad_overview(_u("c1"), db)
        if result["athletes"]:
            assert "risk" in result["athletes"][0]
