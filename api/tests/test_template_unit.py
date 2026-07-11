"""Sprint 33 — Training Plan Templates unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.template_service import (
    BUILTIN_TEMPLATES,
    VALID_SPORTS,
    VALID_PHASES,
    _tri_sessions,
    _week_dict,
    _template_dict,
    _builtin_template_dict,
    _iso,
    list_templates,
    get_template,
    create_template,
    update_template,
    delete_template,
    assign_template_to_athlete,
    compliance_trend,
)
from api.models import PlanTemplate, PlanTemplateWeek, WorkoutPrescription


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_template(**kwargs):
    t = MagicMock(spec=PlanTemplate)
    t.id            = "tpl-1"
    t.coach_id      = "coach-1"
    t.name          = "Test Plan"
    t.sport         = "triathlon"
    t.distance_type = "ironman"
    t.weeks         = 4
    t.difficulty    = "intermediate"
    t.description   = "Test description"
    t.is_public     = False
    t.created_at    = MagicMock()
    t.created_at.isoformat.return_value = "2026-07-02T00:00:00"
    t.plan_weeks    = []
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def _make_week(week_num=1, phase="base", label="Base 1", tss=350, hours=10.0, sessions=None):
    w = MagicMock(spec=PlanTemplateWeek)
    w.id           = f"wk-{week_num}"
    w.week_num     = week_num
    w.phase_type   = phase
    w.label        = label
    w.tss_target   = tss
    w.hours_target = hours
    w.sessions_json = json.dumps(sessions or [])
    w.notes        = None
    return w


def _make_db(first_result=None, all_results=None, scalar_results=None):
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.first.return_value = first_result
    q.all.return_value   = all_results or []
    if scalar_results is not None:
        q.scalar.side_effect = scalar_results
    return db


# ── Built-in templates ────────────────────────────────────────────────────────

class TestBuiltinTemplates:
    def test_three_builtin_templates(self):
        assert len(BUILTIN_TEMPLATES) == 3

    def test_ironman_20_weeks(self):
        im = next(b for b in BUILTIN_TEMPLATES if b["distance_type"] == "ironman")
        assert im["weeks"] == 20
        assert len(im["plan_weeks"]) == 20

    def test_703_12_weeks(self):
        t703 = next(b for b in BUILTIN_TEMPLATES if b["distance_type"] == "70.3")
        assert t703["weeks"] == 12
        assert len(t703["plan_weeks"]) == 12

    def test_sprint_8_weeks(self):
        spr = next(b for b in BUILTIN_TEMPLATES if b["distance_type"] == "sprint")
        assert spr["weeks"] == 8
        assert len(spr["plan_weeks"]) == 8

    def test_all_builtin_coach_id_none(self):
        assert all(b["coach_id"] is None for b in BUILTIN_TEMPLATES)

    def test_all_builtin_is_public(self):
        assert all(b["is_public"] for b in BUILTIN_TEMPLATES)

    def test_ironman_has_base_build_peak_taper(self):
        im = next(b for b in BUILTIN_TEMPLATES if b["distance_type"] == "ironman")
        phases = {w["phase_type"] for w in im["plan_weeks"]}
        assert {"base", "build", "peak", "taper"}.issubset(phases)

    def test_week_numbers_sequential(self):
        for bt in BUILTIN_TEMPLATES:
            nums = [w["week_num"] for w in bt["plan_weeks"]]
            assert nums == list(range(1, bt["weeks"] + 1))

    def test_tss_targets_positive(self):
        for bt in BUILTIN_TEMPLATES:
            for w in bt["plan_weeks"]:
                assert w.get("tss_target", 1) > 0


# ── _tri_sessions ─────────────────────────────────────────────────────────────

class TestTriSessions:
    def test_without_brick_returns_3(self):
        assert len(_tri_sessions(90, 45, 35)) == 3

    def test_with_brick_returns_4(self):
        assert len(_tri_sessions(90, 45, 35, brick=True)) == 4

    def test_sports_correct(self):
        sessions = _tri_sessions(90, 45, 35)
        sports = [s["sport"] for s in sessions]
        assert "swim" in sports and "bike" in sports and "run" in sports

    def test_tss_proportional_to_duration(self):
        sessions = _tri_sessions(120, 60, 40)
        bike = next(s for s in sessions if s["sport"] == "bike")
        assert bike["tss"] == round(120 * 0.6)

    def test_brick_sport_is_brick(self):
        sessions = _tri_sessions(90, 45, 35, brick=True)
        brick = sessions[-1]
        assert brick["sport"] == "brick"


# ── _week_dict / _template_dict ───────────────────────────────────────────────

class TestWeekDict:
    def test_returns_required_keys(self):
        w = _make_week()
        d = _week_dict(w)
        for key in ("id", "week_num", "phase_type", "label", "tss_target", "hours_target", "sessions", "notes"):
            assert key in d

    def test_sessions_parsed_from_json(self):
        sess = [{"sport": "bike", "title": "Test"}]
        w = _make_week(sessions=sess)
        d = _week_dict(w)
        assert d["sessions"] == sess

    def test_empty_sessions_json(self):
        w = _make_week()
        w.sessions_json = None
        d = _week_dict(w)
        assert d["sessions"] == []


class TestTemplateDict:
    def test_required_keys(self):
        t = _make_template()
        d = _template_dict(t)
        for key in ("id", "coach_id", "name", "sport", "weeks", "difficulty", "is_builtin"):
            assert key in d

    def test_is_builtin_false_for_coach_templates(self):
        t = _make_template(coach_id="coach-1")
        assert _template_dict(t)["is_builtin"] is False

    def test_is_builtin_true_for_null_coach(self):
        t = _make_template(coach_id=None)
        assert _template_dict(t)["is_builtin"] is True

    def test_no_weeks_by_default(self):
        t = _make_template()
        d = _template_dict(t)
        assert "plan_weeks" not in d

    def test_weeks_included_when_requested(self):
        t = _make_template(plan_weeks=[_make_week()])
        d = _template_dict(t, include_weeks=True)
        assert "plan_weeks" in d and len(d["plan_weeks"]) == 1


# ── _builtin_template_dict ────────────────────────────────────────────────────

class TestBuiltinTemplateDict:
    def test_returns_is_builtin_true(self):
        d = _builtin_template_dict(BUILTIN_TEMPLATES[0])
        assert d["is_builtin"] is True

    def test_no_weeks_by_default(self):
        d = _builtin_template_dict(BUILTIN_TEMPLATES[0])
        assert "plan_weeks" not in d

    def test_weeks_included(self):
        d = _builtin_template_dict(BUILTIN_TEMPLATES[0], include_weeks=True)
        assert len(d["plan_weeks"]) == 20


# ── list_templates ────────────────────────────────────────────────────────────

class TestListTemplates:
    def test_includes_builtins(self):
        db = _make_db(all_results=[])
        result = list_templates("coach-1", db)
        assert len(result) >= 3  # at minimum the 3 built-ins

    def test_builtins_come_first(self):
        db = _make_db(all_results=[])
        result = list_templates("coach-1", db)
        first_3 = result[:3]
        assert all(r["is_builtin"] for r in first_3)

    def test_coach_templates_appended(self):
        t = _make_template(id="own-1", coach_id="coach-1")
        db = _make_db(all_results=[t])
        result = list_templates("coach-1", db)
        ids = [r["id"] for r in result]
        assert "own-1" in ids


# ── get_template ──────────────────────────────────────────────────────────────

class TestGetTemplate:
    def test_returns_builtin_by_id(self):
        db = _make_db()
        result = get_template("builtin-ironman-20w", "coach-1", db)
        assert result is not None
        assert result["id"] == "builtin-ironman-20w"
        assert "plan_weeks" in result

    def test_returns_none_for_missing(self):
        db = _make_db(first_result=None)
        result = get_template("nonexistent", "coach-1", db)
        assert result is None

    def test_returns_coach_template(self):
        t = _make_template(plan_weeks=[_make_week()])
        db = _make_db(first_result=t)
        result = get_template("tpl-1", "coach-1", db)
        assert result is not None
        assert result["id"] == "tpl-1"


# ── create_template ───────────────────────────────────────────────────────────

class TestCreateTemplate:
    def test_creates_template_in_db(self):
        db = MagicMock()
        mock_tpl = _make_template(plan_weeks=[_make_week()])
        mock_tpl_cls = MagicMock(return_value=mock_tpl)
        mock_week_cls = MagicMock(return_value=_make_week())

        def refresh_side(obj):
            obj.plan_weeks = [_make_week()]
            obj.created_at = MagicMock()
            obj.created_at.isoformat.return_value = "2026-07-02T00:00:00"

        db.refresh.side_effect = refresh_side
        body = {
            "name": "My Plan", "sport": "run",
            "plan_weeks": [
                {"week_num": 1, "phase_type": "base", "label": "W1", "tss_target": 300, "sessions": []}
            ]
        }
        with patch("api.services.template_service.PlanTemplate", mock_tpl_cls), \
             patch("api.services.template_service.PlanTemplateWeek", mock_week_cls):
            create_template("coach-1", body, db)
        assert db.add.called
        assert db.commit.called

    def test_week_count_matches_plan_weeks(self):
        db = MagicMock()
        mock_tpl = _make_template(plan_weeks=[_make_week(1), _make_week(2)])
        mock_tpl_cls  = MagicMock(return_value=mock_tpl)
        mock_week_cls = MagicMock(side_effect=lambda **kw: _make_week(kw.get("week_num", 1)))

        def refresh_side(obj):
            obj.plan_weeks = [_make_week(1), _make_week(2)]
            obj.created_at = MagicMock()
            obj.created_at.isoformat.return_value = "2026-07-02T00:00:00"

        db.refresh.side_effect = refresh_side
        body = {
            "name": "2-week Plan", "sport": "triathlon",
            "plan_weeks": [
                {"week_num": 1, "phase_type": "base", "sessions": []},
                {"week_num": 2, "phase_type": "build", "sessions": []},
            ]
        }
        with patch("api.services.template_service.PlanTemplate", mock_tpl_cls), \
             patch("api.services.template_service.PlanTemplateWeek", mock_week_cls):
            create_template("coach-1", body, db)
        # 1 PlanTemplate + 2 PlanTemplateWeek = 3 db.add calls
        assert db.add.call_count >= 3


# ── _iso helper ───────────────────────────────────────────────────────────────

class TestIsoHelper:
    def test_formats_date(self):
        d = date(2026, 7, 7)
        assert _iso(d) == "2026-07-07"

    def test_pads_single_digits(self):
        d = date(2026, 1, 5)
        assert _iso(d) == "2026-01-05"


# ── assign_template_to_athlete ────────────────────────────────────────────────

def _with_mock_orm(fn, *args, **kwargs):
    """Run fn with WorkoutPrescription + TrainingPhase patched to avoid ORM mapper collision."""
    mock_rx  = MagicMock(return_value=MagicMock())
    mock_tp  = MagicMock(return_value=MagicMock())
    with patch("api.services.template_service.WorkoutPrescription", mock_rx), \
         patch("api.services.template_service.TrainingPhase", mock_tp):
        return fn(*args, **kwargs)


class TestAssignTemplate:
    def test_assigns_builtin_template(self):
        db = MagicMock()
        result = _with_mock_orm(
            assign_template_to_athlete,
            template_id="builtin-sprint-8w", athlete_id="ath-1",
            coach_id="coach-1", start_date="2026-08-03", db=db,
        )
        assert result["weeks"] == 8
        assert result["prescriptions_created"] > 0
        assert result["phases_created"] > 0
        assert db.commit.called

    def test_assign_unknown_template_returns_error(self):
        db = _make_db(first_result=None)
        result = _with_mock_orm(
            assign_template_to_athlete,
            template_id="nonexistent", athlete_id="ath-1",
            coach_id="coach-1", start_date="2026-08-03", db=db,
        )
        assert result.get("error") == "template_not_found"

    def test_ironman_20w_creates_many_prescriptions(self):
        db = MagicMock()
        result = _with_mock_orm(
            assign_template_to_athlete,
            template_id="builtin-ironman-20w", athlete_id="ath-1",
            coach_id="coach-1", start_date="2026-09-07", db=db,
        )
        assert result["prescriptions_created"] >= 60  # 20 weeks × ≥3 sessions each

    def test_start_and_end_date_span(self):
        db = MagicMock()
        result = _with_mock_orm(
            assign_template_to_athlete,
            template_id="builtin-sprint-8w", athlete_id="ath-1",
            coach_id="coach-1", start_date="2026-08-03", db=db,
        )
        start = date.fromisoformat(result["start_date"])
        end   = date.fromisoformat(result["end_date"])
        assert (end - start).days >= 55  # 8 weeks − 1 day ≥ 55 days

    def test_phases_created_correctly(self):
        db = MagicMock()
        result = _with_mock_orm(
            assign_template_to_athlete,
            template_id="builtin-703-12w", athlete_id="ath-1",
            coach_id="coach-1", start_date="2026-07-06", db=db,
        )
        # 70.3 has base/recovery/build/taper → at least 3 distinct phase blocks
        assert result["phases_created"] >= 3


# ── compliance_trend ──────────────────────────────────────────────────────────

class TestComplianceTrend:
    def _make_compliance_db(self, total_per_week, done_per_week):
        """Returns a db mock where scalar() alternates total/done per week."""
        db = MagicMock()
        from sqlalchemy import func as sqlfunc
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q

        scalars = []
        for total, done in zip(total_per_week, done_per_week):
            scalars.extend([total, done])
        q.scalar.side_effect = scalars
        return db

    def test_returns_correct_week_count(self):
        db = self._make_compliance_db([5, 3, 0], [4, 2, 0])
        result = compliance_trend("ath-1", 3, db)
        assert len(result) == 3

    def test_compliance_pct_calculated(self):
        db = self._make_compliance_db([10, 5], [8, 4])
        result = compliance_trend("ath-1", 2, db)
        assert result[0]["compliance_pct"] == 80
        assert result[1]["compliance_pct"] == 80

    def test_zero_total_returns_none(self):
        db = self._make_compliance_db([0], [0])
        result = compliance_trend("ath-1", 1, db)
        assert result[0]["compliance_pct"] is None

    def test_result_has_required_keys(self):
        db = self._make_compliance_db([4], [3])
        result = compliance_trend("ath-1", 1, db)
        for key in ("week_start", "week_end", "total_rx", "completed_rx", "compliance_pct"):
            assert key in result[0]

    def test_week_start_before_week_end(self):
        db = self._make_compliance_db([2], [1])
        result = compliance_trend("ath-1", 1, db)
        assert result[0]["week_start"] < result[0]["week_end"]

    def test_weeks_in_chronological_order(self):
        db = self._make_compliance_db([3, 3, 3], [2, 2, 2])
        result = compliance_trend("ath-1", 3, db)
        starts = [r["week_start"] for r in result]
        assert starts == sorted(starts)

    def test_valid_sports_set(self):
        assert "triathlon" in VALID_SPORTS
        assert "run" in VALID_SPORTS
        assert "bike" in VALID_SPORTS
        assert "swim" in VALID_SPORTS

    def test_valid_phases_set(self):
        assert "base" in VALID_PHASES
        assert "taper" in VALID_PHASES
        assert "recovery" in VALID_PHASES
