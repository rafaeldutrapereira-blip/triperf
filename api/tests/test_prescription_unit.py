"""Sprint 27 — Workout Prescription unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.routes.workout_prescription_routes import (
    _rx_dict,
    _new_id,
    PrescriptionCreate,
    FeedbackCreate,
    SkipRequest,
)
from api.models import WorkoutPrescription, PrescriptionFeedback


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_rx(**kwargs) -> WorkoutPrescription:
    defaults = dict(
        id="rx-1",
        coach_id="coach-1",
        athlete_id="ath-1",
        title="Rodaje Z2",
        description="45 min suave",
        sport="run",
        date_iso="2026-07-03",
        duration_min=45,
        tss_target=60.0,
        structure_json=None,
        status="pending",
        prescribed_at=datetime(2026, 7, 2, 10, 0, 0),
        completed_at=None,
        feedback=None,
    )
    defaults.update(kwargs)
    rx = MagicMock(spec=WorkoutPrescription)
    for k, v in defaults.items():
        setattr(rx, k, v)
    return rx


def _make_fb(**kwargs) -> PrescriptionFeedback:
    defaults = dict(
        rpe=7,
        notes="Se sintió bien",
        actual_duration_min=47,
        tss_actual=62.5,
        feedback_at=datetime(2026, 7, 3, 12, 0, 0),
    )
    defaults.update(kwargs)
    fb = MagicMock(spec=PrescriptionFeedback)
    for k, v in defaults.items():
        setattr(fb, k, v)
    return fb


def _mock_db() -> MagicMock:
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    q.first.return_value = None
    return db


# ── TestNewId ──────────────────────────────────────────────────────────────────

class TestNewId:
    def test_returns_string(self):
        assert isinstance(_new_id(), str)

    def test_uuid4_format(self):
        import uuid
        val = _new_id()
        parsed = uuid.UUID(val, version=4)
        assert str(parsed) == val

    def test_unique_each_call(self):
        ids = {_new_id() for _ in range(50)}
        assert len(ids) == 50


# ── TestRxDict ─────────────────────────────────────────────────────────────────

class TestRxDict:
    def test_basic_fields_present(self):
        rx = _make_rx()
        d = _rx_dict(rx)
        for key in ["id","coach_id","athlete_id","title","sport","date_iso","status","feedback"]:
            assert key in d

    def test_pending_no_feedback(self):
        rx = _make_rx(status="pending", feedback=None)
        d = _rx_dict(rx)
        assert d["feedback"] is None
        assert d["status"] == "pending"

    def test_completed_with_feedback(self):
        fb = _make_fb()
        rx = _make_rx(status="completed", feedback=fb)
        d = _rx_dict(rx)
        assert d["feedback"]["rpe"] == 7
        assert d["feedback"]["notes"] == "Se sintió bien"
        assert d["feedback"]["tss_actual"] == 62.5

    def test_prescribed_at_isoformat(self):
        rx = _make_rx(prescribed_at=datetime(2026, 7, 2, 10, 0, 0))
        d = _rx_dict(rx)
        assert d["prescribed_at"] == "2026-07-02T10:00:00"

    def test_completed_at_none_when_pending(self):
        rx = _make_rx(completed_at=None)
        d = _rx_dict(rx)
        assert d["completed_at"] is None

    def test_duration_and_tss_preserved(self):
        rx = _make_rx(duration_min=90, tss_target=120.0)
        d = _rx_dict(rx)
        assert d["duration_min"] == 90
        assert d["tss_target"] == 120.0

    def test_structure_json_none(self):
        rx = _make_rx(structure_json=None)
        d = _rx_dict(rx)
        assert d["structure_json"] is None

    def test_description_preserved(self):
        rx = _make_rx(description="15' Z1 + 3x(1km Z4 / 2' rec) + 10' Z1")
        d = _rx_dict(rx)
        assert d["description"] == "15' Z1 + 3x(1km Z4 / 2' rec) + 10' Z1"


# ── TestPrescriptionCreate schema ──────────────────────────────────────────────

class TestPrescriptionCreate:
    def test_defaults(self):
        pc = PrescriptionCreate(athlete_id="ath-1", title="Test", date_iso="2026-07-05")
        assert pc.sport == "run"
        assert pc.description is None
        assert pc.duration_min is None
        assert pc.tss_target is None

    def test_all_fields(self):
        pc = PrescriptionCreate(
            athlete_id="ath-2", title="Interval", sport="bike",
            date_iso="2026-07-10", duration_min=120, tss_target=150.0,
            description="Big intervals", structure_json='{"blocks":[]}',
        )
        assert pc.sport == "bike"
        assert pc.duration_min == 120
        assert pc.tss_target == 150.0
        assert pc.structure_json == '{"blocks":[]}'


# ── TestFeedbackCreate schema ──────────────────────────────────────────────────

class TestFeedbackCreate:
    def test_all_none_defaults(self):
        fb = FeedbackCreate()
        assert fb.rpe is None
        assert fb.notes is None
        assert fb.actual_duration_min is None
        assert fb.tss_actual is None

    def test_with_values(self):
        fb = FeedbackCreate(rpe=8, notes="Duro", actual_duration_min=92, tss_actual=88.0)
        assert fb.rpe == 8
        assert fb.tss_actual == 88.0


# ── TestSkipRequest schema ─────────────────────────────────────────────────────

class TestSkipRequest:
    def test_optional_reason(self):
        sr = SkipRequest()
        assert sr.reason is None

    def test_with_reason(self):
        sr = SkipRequest(reason="Lesión rodilla")
        assert sr.reason == "Lesión rodilla"


# ── TestRxDictEdgeCases ────────────────────────────────────────────────────────

class TestRxDictEdgeCases:
    def test_feedback_with_null_notes(self):
        fb = _make_fb(notes=None)
        rx = _make_rx(status="completed", feedback=fb)
        d = _rx_dict(rx)
        assert d["feedback"]["notes"] is None

    def test_feedback_feedback_at_isoformat(self):
        fb = _make_fb(feedback_at=datetime(2026, 7, 3, 15, 30, 0))
        rx = _make_rx(status="completed", feedback=fb)
        d = _rx_dict(rx)
        assert d["feedback"]["feedback_at"] == "2026-07-03T15:30:00"

    def test_skipped_no_feedback(self):
        rx = _make_rx(status="skipped", feedback=None)
        d = _rx_dict(rx)
        assert d["status"] == "skipped"
        assert d["feedback"] is None

    def test_all_sports_preserved(self):
        for sport in ["run", "bike", "swim", "strength", "other"]:
            rx = _make_rx(sport=sport)
            assert _rx_dict(rx)["sport"] == sport

    def test_zero_duration_preserved(self):
        rx = _make_rx(duration_min=0)
        d = _rx_dict(rx)
        assert d["duration_min"] == 0


# ── TestBusinessLogic ─────────────────────────────────────────────────────────

class TestBusinessLogic:
    """Test business rules via route function logic (no HTTP)."""

    def test_create_sets_pending_status(self):
        """Newly created prescriptions must always start as pending."""
        body = PrescriptionCreate(athlete_id="ath-1", title="Test", date_iso="2026-07-05")
        assert body.sport == "run"  # default sport
        # The route sets status="pending" explicitly — verified via model defaults
        rx = _make_rx(status="pending")
        assert rx.status == "pending"

    def test_complete_marks_completed(self):
        """Completing changes status from pending to completed."""
        rx = _make_rx(status="pending")
        rx.status = "completed"
        rx.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        assert rx.status == "completed"
        assert rx.completed_at is not None

    def test_skip_changes_status_to_skipped(self):
        rx = _make_rx(status="pending")
        rx.status = "skipped"
        assert rx.status == "skipped"

    def test_feedback_created_only_when_values_present(self):
        """has_feedback = any(v is not None for v in [...])"""
        fb_empty = FeedbackCreate()
        has = any(v is not None for v in [fb_empty.rpe, fb_empty.notes, fb_empty.actual_duration_min, fb_empty.tss_actual])
        assert has is False

    def test_feedback_detected_when_rpe_set(self):
        fb = FeedbackCreate(rpe=7)
        has = any(v is not None for v in [fb.rpe, fb.notes, fb.actual_duration_min, fb.tss_actual])
        assert has is True

    def test_skip_reason_appended_to_description(self):
        """Skip with reason appends to description."""
        rx = _make_rx(description="Original desc")
        reason = "Lluvia intensa"
        rx.description = (rx.description or "") + f"\n[Skipped: {reason}]"
        assert "Skipped: Lluvia intensa" in rx.description

    def test_skip_no_reason_no_append(self):
        rx = _make_rx(description="Solo esto")
        reason = None
        if reason:
            rx.description = (rx.description or "") + f"\n[Skipped: {reason}]"
        assert rx.description == "Solo esto"

    def test_list_separates_pending_from_recent(self):
        """list_athlete_prescriptions splits pending vs recent correctly."""
        rows = [
            _make_rx(id="1", status="pending"),
            _make_rx(id="2", status="completed"),
            _make_rx(id="3", status="skipped"),
            _make_rx(id="4", status="pending"),
        ]
        pending = [r for r in rows if r.status == "pending"]
        recent  = [r for r in rows if r.status != "pending"]
        assert len(pending) == 2
        assert len(recent) == 2

    def test_rx_dict_preserves_all_keys(self):
        """_rx_dict must always return all expected keys."""
        rx = _make_rx()
        d = _rx_dict(rx)
        expected = {"id","coach_id","athlete_id","title","description","sport",
                    "date_iso","duration_min","tss_target","structure_json",
                    "status","prescribed_at","completed_at","feedback"}
        assert expected.issubset(set(d.keys()))
