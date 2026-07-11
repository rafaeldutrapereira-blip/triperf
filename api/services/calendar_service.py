"""Sprint 35 — Athlete Calendar Service.

Provides monthly calendar view, weekly summary, and upcoming workout previews
by joining WorkoutPrescription + GarminTrainingLoad + RaceEvent data.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    WorkoutPrescription,
    GarminTrainingLoad,
    RaceEvent,
    PrescriptionFeedback,
)

# ── Sport colour palette (consistent with coach.html) ──────────────────────────
SPORT_COLORS = {
    "swim":    "#0ea5e9",
    "bike":    "#f59e0b",
    "run":     "#10b981",
    "strength":"#8b5cf6",
    "brick":   "#ef4444",
    "rest":    "#6b7280",
    "other":   "#64748b",
}

STATUS_LABELS = {
    "pending":   "Pendiente",
    "completed": "Completado",
    "skipped":   "Omitido",
    "partial":   "Parcial",
}


def _color(sport: str) -> str:
    return SPORT_COLORS.get((sport or "other").lower(), SPORT_COLORS["other"])


def _rx_to_dict(rx: WorkoutPrescription, feedback: Optional[object] = None) -> dict:
    d = {
        "id":           rx.id,
        "title":        rx.title,
        "sport":        rx.sport or "other",
        "color":        _color(rx.sport),
        "status":       rx.status or "pending",
        "status_label": STATUS_LABELS.get(rx.status or "pending", rx.status or "pending"),
        "tss_target":   rx.tss_target,
        "duration_min": rx.duration_min,
        "date_iso":     rx.date_iso,
    }
    if feedback:
        d["feedback"] = {
            "rpe":          feedback.rpe,
            "tss_actual":   feedback.tss_actual,
            "notes":        feedback.notes,
        }
    return d


# ── Monthly calendar ───────────────────────────────────────────────────────────

def get_monthly_calendar(athlete_id: str, year: int, month: int, db: Session) -> dict:
    """Return a per-day breakdown for the given month.

    Each day: list of prescriptions, Garmin TSS (if available), race flags.
    """
    # Date range for the month
    first_day = date(year, month, 1)
    last_day  = date(year, month, calendar.monthrange(year, month)[1])
    first_str = first_day.isoformat()
    last_str  = last_day.isoformat()

    # Prescriptions for the month
    rxs = (
        db.query(WorkoutPrescription)
        .filter(
            WorkoutPrescription.athlete_id == athlete_id,
            WorkoutPrescription.date_iso >= first_str,
            WorkoutPrescription.date_iso <= last_str,
        )
        .order_by(WorkoutPrescription.date_iso, WorkoutPrescription.sport)
        .all()
    )

    # Fetch feedback for those prescriptions
    rx_ids = [r.id for r in rxs]
    feedbacks: dict[str, object] = {}
    if rx_ids:
        fbs = (
            db.query(PrescriptionFeedback)
            .filter(PrescriptionFeedback.prescription_id.in_(rx_ids))
            .all()
        )
        for fb in fbs:
            feedbacks[fb.prescription_id] = fb

    # Garmin loads for the month (actual TSS)
    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id == athlete_id,
            GarminTrainingLoad.date_iso >= first_str,
            GarminTrainingLoad.date_iso <= last_str,
        )
        .all()
    )
    load_by_date: dict[str, GarminTrainingLoad] = {l.date_iso: l for l in loads}

    # Races in this month
    races = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == athlete_id,
            RaceEvent.date_iso >= first_str,
            RaceEvent.date_iso <= last_str,
        )
        .all()
    )
    races_by_date: dict[str, list] = {}
    for r in races:
        races_by_date.setdefault(r.date_iso, []).append({
            "id":           r.id,
            "name":         r.name,
            "distance":     r.distance,
            "is_goal_race": r.is_goal_race,
        })

    # Group prescriptions by day
    rx_by_date: dict[str, list] = {}
    for rx in rxs:
        fb = feedbacks.get(rx.id)
        rx_by_date.setdefault(rx.date_iso, []).append(_rx_to_dict(rx, fb))

    # Build day array
    today_str = date.today().isoformat()
    days = []
    cur = first_day
    while cur <= last_day:
        d_str = cur.isoformat()
        load  = load_by_date.get(d_str)
        day_rxs = rx_by_date.get(d_str, [])

        # Compliance flag for the day
        total   = len(day_rxs)
        done    = sum(1 for r in day_rxs if r["status"] == "completed")
        skipped = sum(1 for r in day_rxs if r["status"] == "skipped")

        days.append({
            "date":          d_str,
            "weekday":       cur.weekday(),        # 0=Mon
            "is_today":      d_str == today_str,
            "is_past":       d_str < today_str,
            "prescriptions": day_rxs,
            "tss_actual":    load.tss_actual if load else None,
            "ctl":           load.ctl        if load else None,
            "tsb":           load.tsb        if load else None,
            "races":         races_by_date.get(d_str, []),
            "rx_total":      total,
            "rx_done":       done,
            "rx_skipped":    skipped,
            "compliance_pct": round(done / total * 100) if total else None,
        })
        cur += timedelta(days=1)

    # Month totals
    total_rx    = sum(d["rx_total"] for d in days)
    total_done  = sum(d["rx_done"]  for d in days)
    tss_planned = sum(
        (r["tss_target"] or 0) for d in days for r in d["prescriptions"]
    )
    tss_actual  = sum(
        (d["tss_actual"] or 0) for d in days if d["tss_actual"] is not None
    )

    return {
        "year":              year,
        "month":             month,
        "month_name":        first_day.strftime("%B %Y"),
        "days_in_month":     last_day.day,
        "first_weekday":     first_day.weekday(),
        "days":              days,
        "summary": {
            "total_rx":       total_rx,
            "total_done":     total_done,
            "compliance_pct": round(total_done / total_rx * 100) if total_rx else None,
            "tss_planned":    round(tss_planned, 1),
            "tss_actual":     round(tss_actual,  1),
            "tss_pct":        round(tss_actual / tss_planned * 100) if tss_planned else None,
            "races_count":    len(races),
        },
    }


# ── Weekly summary ─────────────────────────────────────────────────────────────

def get_weekly_summary(athlete_id: str, week_start: date, db: Session) -> dict:
    """Return training summary for the 7-day window starting at week_start."""
    week_end = week_start + timedelta(days=6)
    ws = week_start.isoformat()
    we = week_end.isoformat()

    rxs = (
        db.query(WorkoutPrescription)
        .filter(
            WorkoutPrescription.athlete_id == athlete_id,
            WorkoutPrescription.date_iso >= ws,
            WorkoutPrescription.date_iso <= we,
        )
        .all()
    )

    rx_ids = [r.id for r in rxs]
    feedbacks: dict[str, object] = {}
    if rx_ids:
        fbs = (
            db.query(PrescriptionFeedback)
            .filter(PrescriptionFeedback.prescription_id.in_(rx_ids))
            .all()
        )
        for fb in fbs:
            feedbacks[fb.prescription_id] = fb

    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id == athlete_id,
            GarminTrainingLoad.date_iso >= ws,
            GarminTrainingLoad.date_iso <= we,
        )
        .all()
    )

    # Per-sport breakdown
    sport_map: dict[str, dict] = {}
    for rx in rxs:
        s = (rx.sport or "other").lower()
        if s not in sport_map:
            sport_map[s] = {"planned": 0, "done": 0, "tss_target": 0.0, "tss_actual": 0.0}
        sport_map[s]["planned"] += 1
        if rx.status == "completed":
            sport_map[s]["done"] += 1
        sport_map[s]["tss_target"] += rx.tss_target or 0
        fb = feedbacks.get(rx.id)
        if fb:
            sport_map[s]["tss_actual"] += fb.tss_actual or 0

    tss_garmin = sum(l.tss_actual or 0 for l in loads)
    latest_load = max(loads, key=lambda l: l.date_iso) if loads else None

    total_rx   = len(rxs)
    total_done = sum(1 for r in rxs if r.status == "completed")
    tss_planned = sum(r.tss_target or 0 for r in rxs)

    return {
        "week_start":    ws,
        "week_end":      we,
        "total_rx":      total_rx,
        "total_done":    total_done,
        "compliance_pct": round(total_done / total_rx * 100) if total_rx else None,
        "tss_planned":   round(tss_planned, 1),
        "tss_garmin":    round(tss_garmin,  1),
        "ctl_end":       latest_load.ctl if latest_load else None,
        "tsb_end":       latest_load.tsb if latest_load else None,
        "sports":        sport_map,
    }


# ── Upcoming workouts ──────────────────────────────────────────────────────────

def get_upcoming_workouts(athlete_id: str, days: int, db: Session) -> dict:
    """Return pending prescriptions for the next `days` days (today inclusive)."""
    today    = date.today()
    end_date = today + timedelta(days=days - 1)
    today_str    = today.isoformat()
    end_date_str = end_date.isoformat()

    rxs = (
        db.query(WorkoutPrescription)
        .filter(
            WorkoutPrescription.athlete_id == athlete_id,
            WorkoutPrescription.date_iso >= today_str,
            WorkoutPrescription.date_iso <= end_date_str,
            WorkoutPrescription.status == "pending",
        )
        .order_by(WorkoutPrescription.date_iso, WorkoutPrescription.sport)
        .all()
    )

    races = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == athlete_id,
            RaceEvent.date_iso >= today_str,
            RaceEvent.date_iso <= end_date_str,
        )
        .order_by(RaceEvent.date_iso)
        .all()
    )

    by_date: dict[str, dict] = {}
    for rx in rxs:
        d = rx.date_iso
        if d not in by_date:
            by_date[d] = {"date": d, "prescriptions": [], "races": []}
        by_date[d]["prescriptions"].append(_rx_to_dict(rx))

    for r in races:
        d = r.date_iso
        if d not in by_date:
            by_date[d] = {"date": d, "prescriptions": [], "races": []}
        by_date[d]["races"].append({
            "id": r.id, "name": r.name,
            "distance": r.distance, "is_goal_race": r.is_goal_race,
        })

    upcoming = sorted(by_date.values(), key=lambda x: x["date"])
    total_tss = sum(
        (rx["tss_target"] or 0)
        for day in upcoming for rx in day["prescriptions"]
    )

    return {
        "from_date":   today_str,
        "to_date":     end_date_str,
        "days":        days,
        "total_pending": len(rxs),
        "total_tss_planned": round(total_tss, 1),
        "schedule":    upcoming,
    }
