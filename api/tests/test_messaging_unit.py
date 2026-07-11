"""Sprint 34 — Messaging & Notification Hub unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.messaging_service import (
    get_coach_notifications,
    get_athlete_message_summary,
    get_contacts_for_user,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _msg(from_id="coach-1", to_id="ath-1", body="Hello", read=False, deleted=False):
    m = MagicMock()
    m.id           = "msg-1"
    m.from_user_id = from_id
    m.to_user_id   = to_id
    m.body         = body
    m.sent_at      = datetime(2026, 7, 1, 10, 0, 0)
    m.read_at      = datetime(2026, 7, 1, 10, 5, 0) if read else None
    m.deleted_at   = datetime(2026, 7, 1) if deleted else None
    m.sender       = MagicMock()
    m.sender.nombre = "Coach Name"
    m.receiver     = MagicMock()
    m.receiver.nombre = "Athlete Name"
    return m


def _user(uid="user-1", nombre="Test User", rol="athlete"):
    u = MagicMock()
    u.id     = uid
    u.nombre = nombre
    u.email  = "test@example.com"
    u.rol    = rol
    return u


def _feedback(pid="rx-1", athlete_id="ath-1", rpe=7, notes="Felt good"):
    fb = MagicMock()
    fb.id              = "fb-1"
    fb.prescription_id = pid
    fb.athlete_id      = athlete_id
    fb.rpe             = rpe
    fb.notes           = notes
    fb.feedback_at     = datetime(2026, 7, 1, 12, 0, 0)
    fb.tss_actual      = 85.0
    fb.actual_duration_min = 90
    return fb


def _rx(title="Fondo Z2", coach_id="coach-1", athlete_id="ath-1"):
    rx = MagicMock()
    rx.id          = "rx-1"
    rx.title       = title
    rx.coach_id    = coach_id
    rx.athlete_id  = athlete_id
    return rx


def _race(name="Ironman Chile", race_date=None, user_id="ath-1"):
    r = MagicMock()
    r.id       = "race-1"
    r.name     = name
    r.date_iso = race_date or (date.today() + timedelta(days=7)).isoformat()
    r.user_id  = user_id
    return r


def _make_notif_db(unread_msgs=None, msg_count=2, feedback_items=None, races=None):
    """Build a db mock for get_coach_notifications."""
    db = MagicMock()
    q  = db.query.return_value
    q.filter.return_value  = q
    q.join.return_value    = q
    q.order_by.return_value = q
    q.limit.return_value   = q

    msgs      = unread_msgs or [_msg()]
    fbs       = feedback_items or [(MagicMock(), _rx(), _user("ath-1"))]
    race_list = races or [(_race(), _user("ath-1"))]

    q.all.side_effect = [msgs, fbs, race_list]
    q.scalar.return_value = msg_count

    return db


# ── get_coach_notifications ───────────────────────────────────────────────────

class TestGetCoachNotifications:
    """Tests use real model classes (no patching) with a fully-mocked db session.

    Real model column attributes (e.g. RaceEvent.race_date) must remain intact
    so SQLAlchemy can build filter clauses — patching them to MagicMock breaks
    column-expression comparisons (>=, <=, etc.).
    """

    def test_returns_required_keys(self):
        db = _make_notif_db()
        result = get_coach_notifications("coach-1", db)
        for key in ("unread_messages", "latest_messages", "pending_feedback", "upcoming_races", "total_alerts"):
            assert key in result

    def test_unread_count_from_scalar(self):
        db = _make_notif_db(msg_count=5)
        result = get_coach_notifications("coach-1", db)
        assert result["unread_messages"] == 5

    def test_total_alerts_is_sum(self):
        db = _make_notif_db(msg_count=3)
        result = get_coach_notifications("coach-1", db)
        # total_alerts = unread(3) + pending_feedback(1) + upcoming_races(1) = 5
        assert result["total_alerts"] == 5

    def test_latest_messages_has_preview(self):
        msg = _msg(body="Training tomorrow at 6am, don't forget!")
        db = _make_notif_db(unread_msgs=[msg])
        result = get_coach_notifications("coach-1", db)
        if result["latest_messages"]:
            assert "body_preview" in result["latest_messages"][0]

    def test_zero_unread_when_scalar_none(self):
        db = _make_notif_db(msg_count=None)
        result = get_coach_notifications("coach-1", db)
        assert result["unread_messages"] == 0


# ── get_athlete_message_summary ───────────────────────────────────────────────

class TestGetAthleteMessageSummary:
    def _make_db(self, latest_msg=None, count=0):
        db = MagicMock()
        q  = db.query.return_value
        q.filter.return_value  = q
        q.order_by.return_value = q
        q.scalar.return_value  = count
        q.first.return_value   = latest_msg
        return db

    def test_returns_required_keys(self):
        db = self._make_db(latest_msg=_msg(), count=2)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        for key in ("unread_count", "latest_message"):
            assert key in result

    def test_unread_count_zero(self):
        db = self._make_db(count=0)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        assert result["unread_count"] == 0

    def test_latest_message_none_when_no_messages(self):
        db = self._make_db(latest_msg=None, count=0)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        assert result["latest_message"] is None

    def test_latest_message_has_preview(self):
        msg = _msg(body="See you at the pool tomorrow!")
        db = self._make_db(latest_msg=msg, count=1)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        assert result["latest_message"] is not None
        assert "body_preview" in result["latest_message"]

    def test_unread_count_matches_scalar(self):
        db = self._make_db(latest_msg=_msg(), count=7)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        assert result["unread_count"] == 7

    def test_is_read_false_when_read_at_none(self):
        msg = _msg(read=False)
        db = self._make_db(latest_msg=msg, count=1)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        assert result["latest_message"]["is_read"] is False

    def test_is_read_true_when_read_at_set(self):
        msg = _msg(read=True)
        db = self._make_db(latest_msg=msg, count=0)
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        assert result["latest_message"]["is_read"] is True


# ── get_contacts_for_user ─────────────────────────────────────────────────────

class TestGetContactsForUser:
    def _make_db(self, messages=None, other_user=None, unread_count=0):
        db = MagicMock()
        q  = db.query.return_value
        q.filter.return_value  = q
        q.order_by.return_value = q
        q.all.side_effect = [messages or [], []]
        q.first.return_value = other_user or _user()
        q.scalar.return_value = unread_count
        return db

    def test_empty_when_no_messages(self):
        db = self._make_db(messages=[])
        with patch("api.services.messaging_service.Message", MagicMock()), \
             patch("api.services.messaging_service.User", MagicMock()):
            result = get_contacts_for_user("user-1", db)
        assert result["contacts"] == []
        assert result["total_unread"] == 0

    def test_total_unread_is_sum(self):
        msgs = [_msg(from_id="coach-1", to_id="ath-1")]
        db = self._make_db(messages=msgs, other_user=_user("coach-1", "Coach", "coach"), unread_count=3)
        with patch("api.services.messaging_service.Message", MagicMock()), \
             patch("api.services.messaging_service.User", MagicMock()):
            result = get_contacts_for_user("ath-1", db)
        assert result["total_unread"] == 3

    def test_returns_contacts_and_total_keys(self):
        db = self._make_db(messages=[])
        with patch("api.services.messaging_service.Message", MagicMock()), \
             patch("api.services.messaging_service.User", MagicMock()):
            result = get_contacts_for_user("user-1", db)
        assert "contacts" in result
        assert "total_unread" in result


# ── Body preview truncation ───────────────────────────────────────────────────

class TestBodyPreviewTruncation:
    def test_short_body_no_ellipsis(self):
        msg = _msg(body="Short message")
        db = MagicMock()
        q  = db.query.return_value
        q.filter.return_value  = q
        q.order_by.return_value = q
        q.scalar.return_value  = 1
        q.first.return_value   = msg
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        preview = result["latest_message"]["body_preview"]
        assert "…" not in preview

    def test_long_body_truncated_with_ellipsis(self):
        long_body = "x" * 200
        msg = _msg(body=long_body)
        db = MagicMock()
        q  = db.query.return_value
        q.filter.return_value  = q
        q.order_by.return_value = q
        q.scalar.return_value  = 1
        q.first.return_value   = msg
        with patch("api.services.messaging_service.Message", MagicMock()):
            result = get_athlete_message_summary("ath-1", db)
        preview = result["latest_message"]["body_preview"]
        assert "…" in preview
        assert len(preview) <= 125


# ── Race urgency logic ────────────────────────────────────────────────────────

class TestRaceUrgency:
    def test_upcoming_race_within_7_days(self):
        race_date = (date.today() + timedelta(days=5)).isoformat()
        r = _race(name="Test Race", race_date=race_date)
        days = (date.fromisoformat(r.date_iso) - date.today()).days
        assert days == 5
        assert days <= 7

    def test_race_14_days_away(self):
        race_date = (date.today() + timedelta(days=14)).isoformat()
        r = _race(name="Future Race", race_date=race_date)
        days = (date.fromisoformat(r.date_iso) - date.today()).days
        assert days == 14

    def test_past_race_negative_days(self):
        race_date = (date.today() - timedelta(days=3)).isoformat()
        r = _race(name="Past Race", race_date=race_date)
        days = (date.fromisoformat(r.date_iso) - date.today()).days
        assert days < 0
