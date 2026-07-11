"""Sprint 35 — Athlete Calendar Routes.

Endpoints:
  GET /calendar/monthly        — full month day-by-day breakdown (athlete)
  GET /calendar/weekly-summary — TSS/compliance for a week (athlete/coach)
  GET /calendar/upcoming       — next N days of pending workouts (athlete)
  GET /calendar/athlete/{id}/monthly — coach view of an athlete's month
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user, require_role
from ..models import User
from ..permissions import assert_coach_owns_athlete
from ..services.calendar_service import (
    get_monthly_calendar,
    get_weekly_summary,
    get_upcoming_workouts,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/monthly")
def my_monthly_calendar(
    year:  int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1,    le=12),
    db:    Session = Depends(get_db),
    me:    User    = Depends(require_role("athlete", "atleta", "coach", "admin")),
):
    """Athlete: full month calendar with prescriptions, TSS, and races."""
    return get_monthly_calendar(me.id, year, month, db)


@router.get("/weekly-summary")
def my_weekly_summary(
    week_start: Optional[str] = Query(None, description="YYYY-MM-DD (defaults to current week Monday)"),
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("athlete", "atleta", "coach", "admin")),
):
    """Athlete: training summary for a given week."""
    if week_start:
        try:
            ws = date.fromisoformat(week_start)
        except ValueError:
            raise HTTPException(400, "week_start must be YYYY-MM-DD")
    else:
        today = date.today()
        ws = today - __import__("datetime").timedelta(days=today.weekday())
    return get_weekly_summary(me.id, ws, db)


@router.get("/upcoming")
def my_upcoming_workouts(
    days: int = Query(7, ge=1, le=30),
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_role("athlete", "atleta", "coach", "admin")),
):
    """Athlete: next N days of pending prescriptions."""
    return get_upcoming_workouts(me.id, days, db)


@router.get("/athlete/{athlete_id}/monthly")
def athlete_monthly_calendar(
    athlete_id: str,
    year:  int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1,    le=12),
    db:    Session = Depends(get_db),
    me:    User    = Depends(require_role("coach", "admin")),
):
    """Coach: view a specific athlete's monthly calendar."""
    assert_coach_owns_athlete(me.id, athlete_id, db)
    return get_monthly_calendar(athlete_id, year, month, db)


@router.get("/athlete/{athlete_id}/weekly-summary")
def athlete_weekly_summary(
    athlete_id: str,
    week_start: Optional[str] = Query(None),
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("coach", "admin")),
):
    """Coach: weekly summary for a specific athlete."""
    assert_coach_owns_athlete(me.id, athlete_id, db)
    if week_start:
        try:
            ws = date.fromisoformat(week_start)
        except ValueError:
            raise HTTPException(400, "week_start must be YYYY-MM-DD")
    else:
        today = date.today()
        ws = today - __import__("datetime").timedelta(days=today.weekday())
    return get_weekly_summary(athlete_id, ws, db)
