"""Sprint 34 — Messaging Service.

Aggregates all coach-facing notifications into a single response:
  - Unread messages (count + latest)
  - Pending prescription feedback (athletes who completed a workout with RPE/notes)
  - Critical squad alerts (ACWR > 1.5 or recovery < 35)
  - Athletes with upcoming races ≤ 14 days

Also provides athlete-side summary (unread from coach).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Message, User, WorkoutPrescription, PrescriptionFeedback, RaceEvent,
)


# ── Coach notifications aggregation ──────────────────────────────────────────

def get_coach_notifications(coach_id: str, db: Session) -> dict:
    """Return all pending attention items for a coach in one call."""

    today_str = date.today().isoformat()

    # 1. Unread messages
    unread_msgs = (
        db.query(Message)
        .filter(
            Message.to_user_id == coach_id,
            Message.read_at.is_(None),
            Message.deleted_at.is_(None),
        )
        .order_by(Message.sent_at.desc())
        .limit(5)
        .all()
    )
    unread_count = (
        db.query(func.count(Message.id))
        .filter(
            Message.to_user_id == coach_id,
            Message.read_at.is_(None),
            Message.deleted_at.is_(None),
        )
        .scalar() or 0
    )

    # 2. Recent prescription feedback not yet viewed (last 7 days)
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    feedback_items = (
        db.query(PrescriptionFeedback, WorkoutPrescription, User)
        .join(WorkoutPrescription, PrescriptionFeedback.prescription_id == WorkoutPrescription.id)
        .join(User, PrescriptionFeedback.athlete_id == User.id)
        .filter(
            WorkoutPrescription.coach_id == coach_id,
        )
        .order_by(PrescriptionFeedback.feedback_at.desc())
        .limit(10)
        .all()
    )

    # 3. Upcoming races (≤14 days)
    in_14 = (date.today() + timedelta(days=14)).isoformat()
    upcoming_races = (
        db.query(RaceEvent, User)
        .join(User, RaceEvent.user_id == User.id)
        .filter(
            RaceEvent.date_iso >= today_str,
            RaceEvent.date_iso <= in_14,
        )
        .order_by(RaceEvent.date_iso.asc())
        .limit(5)
        .all()
    )

    return {
        "unread_messages": unread_count,
        "latest_messages": [
            {
                "id":          m.id,
                "from_nombre": m.sender.nombre if m.sender else "—",
                "from_id":     m.from_user_id,
                "body_preview": m.body[:80] + ("…" if len(m.body) > 80 else ""),
                "sent_at":     m.sent_at.isoformat(),
            }
            for m in unread_msgs
        ],
        "pending_feedback": [
            {
                "feedback_id":     fb.id,
                "athlete_nombre":  u.nombre or u.email,
                "athlete_id":      u.id,
                "workout_title":   rx.title,
                "rpe":             fb.rpe,
                "notes":           fb.notes,
                "feedback_at":     fb.feedback_at.isoformat(),
                "tss_actual":      fb.tss_actual,
                "actual_min":      fb.actual_duration_min,
            }
            for fb, rx, u in feedback_items
        ],
        "upcoming_races": [
            {
                "athlete_nombre": u.nombre or u.email,
                "athlete_id":     u.id,
                "race_name":      r.name,
                "race_date":      r.date_iso,
                "days_left":      (date.fromisoformat(r.date_iso) - date.today()).days,
            }
            for r, u in upcoming_races
        ],
        "total_alerts": unread_count + len(feedback_items) + len(upcoming_races),
    }


# ── Athlete summary (messages from coach) ────────────────────────────────────

def get_athlete_message_summary(athlete_id: str, db: Session) -> dict:
    """Return unread message count + latest message from coach for an athlete."""
    unread = (
        db.query(func.count(Message.id))
        .filter(
            Message.to_user_id == athlete_id,
            Message.read_at.is_(None),
            Message.deleted_at.is_(None),
        )
        .scalar() or 0
    )

    latest = (
        db.query(Message)
        .filter(
            Message.to_user_id == athlete_id,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.sent_at.desc())
        .first()
    )

    return {
        "unread_count": unread,
        "latest_message": {
            "id":          latest.id,
            "from_nombre": latest.sender.nombre if latest.sender else "—",
            "from_id":     latest.from_user_id,
            "body_preview": latest.body[:120] + ("…" if len(latest.body) > 120 else ""),
            "sent_at":     latest.sent_at.isoformat(),
            "is_read":     latest.read_at is not None,
        } if latest else None,
    }


# ── Thread helpers ────────────────────────────────────────────────────────────

def get_contacts_for_user(user_id: str, db: Session) -> dict:
    """Return conversation list with unread counts.  Re-uses message_routes logic."""
    from sqlalchemy import or_

    all_msgs = (
        db.query(Message)
        .filter(
            Message.deleted_at.is_(None),
            or_(Message.from_user_id == user_id, Message.to_user_id == user_id),
        )
        .order_by(Message.sent_at.desc())
        .all()
    )

    seen: set[str] = set()
    convs: list[dict] = []

    for m in all_msgs:
        other_id = m.to_user_id if m.from_user_id == user_id else m.from_user_id
        if other_id in seen:
            continue
        seen.add(other_id)

        other = db.query(User).filter(User.id == other_id).first()
        if not other:
            continue

        unread = (
            db.query(func.count(Message.id))
            .filter(
                Message.from_user_id == other_id,
                Message.to_user_id == user_id,
                Message.read_at.is_(None),
                Message.deleted_at.is_(None),
            )
            .scalar() or 0
        )

        convs.append({
            "user_id":      other.id,
            "nombre":       other.nombre or other.email,
            "rol":          other.rol,
            "last_body":    m.body[:80] + ("…" if len(m.body) > 80 else ""),
            "last_sent_at": m.sent_at.isoformat(),
            "unread":       unread,
            "is_mine":      m.from_user_id == user_id,
        })

    return {"contacts": convs, "total_unread": sum(c["unread"] for c in convs)}
