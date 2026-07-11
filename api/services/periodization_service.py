"""Sprint 31 — Season Periodization service.

Manages macro-cycles (Base/Build/Peak/Taper/Transition) per athlete.
Provides Gantt data for the coach timeline UI and phase validation.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from ..models import TrainingPhase, GarminTrainingLoad, User

# ── Phase metadata ───────────────────────────────────────────────────────────

_PHASE_COLORS = {
    "base":       "#10B981",  # green   — building aerobic base
    "build":      "#0EA5E9",  # blue    — building intensity
    "peak":       "#F0A500",  # gold    — peak performance
    "taper":      "#A855F7",  # purple  — reducing load pre-race
    "transition": "#7FB3CC",  # muted   — off-season / active recovery
    "recovery":   "#EF4444",  # red     — post-race recovery
}

_PHASE_LABELS = {
    "base":       "Base",
    "build":      "Build",
    "peak":       "Peak",
    "taper":      "Taper",
    "transition": "Transición",
    "recovery":   "Recuperación",
}

VALID_PHASE_TYPES = set(_PHASE_COLORS.keys())


def _phase_color(phase_type: str) -> str:
    return _PHASE_COLORS.get(phase_type, "#7FB3CC")


def _phase_label(phase_type: str) -> str:
    return _PHASE_LABELS.get(phase_type, phase_type.capitalize())


# ── Validation ───────────────────────────────────────────────────────────────

def _phases_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """Return True if two date ranges [a_start, a_end] and [b_start, b_end] overlap."""
    return a_start <= b_end and b_start <= a_end


def validate_no_overlap(
    athlete_id: str,
    start_date: str,
    end_date: str,
    db: Session,
    exclude_id: Optional[str] = None,
) -> tuple[bool, str]:
    """Check that the new/updated phase doesn't overlap with existing phases.

    Returns (ok: bool, error_message: str).
    """
    existing = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .all()
    )
    for ph in existing:
        if exclude_id and ph.id == exclude_id:
            continue
        if _phases_overlap(start_date, end_date, ph.start_date, ph.end_date):
            label = ph.label or _phase_label(ph.phase_type)
            return False, f"Solapamiento con fase '{label}' ({ph.start_date} → {ph.end_date})"
    return True, ""


# ── Phase serialization ──────────────────────────────────────────────────────

def _phase_dict(phase: TrainingPhase, current_ctl: Optional[float] = None) -> dict:
    start = date.fromisoformat(phase.start_date)
    end   = date.fromisoformat(phase.end_date)
    today = date.today()

    duration_days = (end - start).days + 1
    is_active     = start <= today <= end
    is_past       = end < today
    is_future     = start > today

    ctl_gap = None
    if phase.ctl_target is not None and current_ctl is not None:
        ctl_gap = round(phase.ctl_target - current_ctl, 1)

    return {
        "id":                phase.id,
        "coach_id":          phase.coach_id,
        "athlete_id":        phase.athlete_id,
        "phase_type":        phase.phase_type,
        "label":             phase.label or _phase_label(phase.phase_type),
        "phase_type_label":  _phase_label(phase.phase_type),
        "color":             _phase_color(phase.phase_type),
        "start_date":        phase.start_date,
        "end_date":          phase.end_date,
        "ctl_target":        phase.ctl_target,
        "tss_weekly_target": phase.tss_weekly_target,
        "notes":             phase.notes,
        "created_at":        phase.created_at.isoformat() if phase.created_at else None,
        "duration_days":     duration_days,
        "duration_weeks":    round(duration_days / 7, 1),
        "is_active":         is_active,
        "is_past":           is_past,
        "is_future":         is_future,
        "ctl_gap":           ctl_gap,
    }


# ── Gantt builder ────────────────────────────────────────────────────────────

def _month_markers(season_start: date, season_end: date, total_days: int) -> list[dict]:
    """Generate month label positions (pct offset) across the season timeline."""
    markers = []
    current = date(season_start.year, season_start.month, 1)
    while current <= season_end:
        offset_days = (current - season_start).days
        pct = round(offset_days / total_days * 100, 1) if total_days > 0 else 0
        if 0 <= pct <= 100:
            markers.append({
                "label":      current.strftime("%b %Y"),
                "pct_offset": pct,
            })
        # advance to next month
        year  = current.year + (current.month // 12)
        month = (current.month % 12) + 1
        current = date(year, month, 1)
    return markers


def build_season_gantt(athlete_id: str, db: Session) -> dict:
    """Return Gantt visualization data for all phases of an athlete."""
    phases = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .order_by(TrainingPhase.start_date.asc())
        .all()
    )

    if not phases:
        return {
            "has_phases":     False,
            "phases":         [],
            "month_markers":  [],
            "season_start":   None,
            "season_end":     None,
            "total_days":     0,
            "today_pct":      None,
            "current_ctl":    None,
        }

    # Current CTL
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == athlete_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    current_ctl = round(load.ctl, 1) if load and load.ctl is not None else None

    season_start = date.fromisoformat(phases[0].start_date)
    season_end   = date.fromisoformat(phases[-1].end_date)
    total_days   = max((season_end - season_start).days, 1)
    today        = date.today()

    today_pct = None
    if season_start <= today <= season_end:
        today_pct = round((today - season_start).days / total_days * 100, 1)

    gantt_phases = []
    for ph in phases:
        ph_start = date.fromisoformat(ph.start_date)
        ph_end   = date.fromisoformat(ph.end_date)
        pct_start = round((ph_start - season_start).days / total_days * 100, 1)
        pct_width = round((ph_end - ph_start).days / total_days * 100, 1)

        d = _phase_dict(ph, current_ctl)
        d["gantt_pct_start"] = pct_start
        d["gantt_pct_width"] = max(pct_width, 1.0)
        gantt_phases.append(d)

    return {
        "has_phases":    True,
        "phases":        gantt_phases,
        "month_markers": _month_markers(season_start, season_end, total_days),
        "season_start":  season_start.isoformat(),
        "season_end":    season_end.isoformat(),
        "total_days":    total_days,
        "today_pct":     today_pct,
        "current_ctl":   current_ctl,
    }


# ── Public queries ───────────────────────────────────────────────────────────

def get_athlete_phases(athlete_id: str, db: Session) -> list[dict]:
    """Return all phases for an athlete, sorted by start_date."""
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == athlete_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    current_ctl = round(load.ctl, 1) if load and load.ctl is not None else None

    phases = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .order_by(TrainingPhase.start_date.asc())
        .all()
    )
    return [_phase_dict(ph, current_ctl) for ph in phases]
