"""Sprint 30 — Coach Squad Overview service.

Aggregates per-athlete health signals for the coach's command-center view.
O(N × 6) DB queries where N = squad size; acceptable for typical coach squads (< 50 athletes).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from sqlalchemy.orm import Session

from sqlalchemy import text

from ..models import (
    User,
    GarminTrainingLoad,
    RecoveryScore,
    MentalFatigueScore,
    BloodLabAlert,
    WorkoutPrescription,
    RaceEvent,
)

_CTL_DECAY = 1 - math.exp(-1 / 42)


# ── Risk computation ────────────────────────────────────────────────────────

def _risk_level(
    acwr: float | None,
    recovery_score: int | None,
    missed_rxs: int,
    has_blood_critical: bool,
) -> str:
    """Return 'critical' | 'warning' | 'ok' | 'unknown'."""
    if has_blood_critical:
        return "critical"
    if acwr is not None and acwr > 1.5:
        return "critical"
    if acwr is not None and acwr > 1.3:
        return "warning"
    if recovery_score is not None and recovery_score < 35:
        return "warning"
    if missed_rxs >= 3:
        return "warning"
    if acwr is None and recovery_score is None:
        return "unknown"
    return "ok"


def _ctl_trend(loads: list) -> str:
    """Return 'up' | 'down' | 'stable'. Loads sorted descending by date_iso."""
    if len(loads) < 2:
        return "stable"
    recent = [l.ctl for l in loads[:7] if l.ctl is not None]
    prior = [l.ctl for l in loads[7:14] if l.ctl is not None]
    if not recent or not prior:
        return "stable"
    avg_r = sum(recent) / len(recent)
    avg_p = sum(prior) / len(prior)
    if avg_r > avg_p + 1.0:
        return "up"
    if avg_r < avg_p - 1.0:
        return "down"
    return "stable"


# ── Per-athlete card ────────────────────────────────────────────────────────

def _athlete_squad_card(athlete: User, db: Session) -> dict:
    today = date.today()
    week_ago = today - timedelta(days=7)

    # ── Training load ──
    loads = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == athlete.id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .limit(14)
        .all()
    )
    latest = loads[0] if loads else None
    ctl = round(latest.ctl, 1) if latest and latest.ctl is not None else None
    atl = round(latest.atl, 1) if latest and latest.atl is not None else None
    # Prefer stored acwr; fall back to computed
    if latest and latest.acwr is not None:
        acwr = round(latest.acwr, 2)
    elif ctl and atl and ctl > 0:
        acwr = round(atl / ctl, 2)
    else:
        acwr = None
    ctl_trend = _ctl_trend(loads)
    tss_7d = round(sum(l.tss for l in loads[:7] if l.tss is not None), 1)

    # ── Recovery ──
    rec = (
        db.query(RecoveryScore)
        .filter(RecoveryScore.user_id == athlete.id)
        .order_by(RecoveryScore.date_iso.desc())
        .first()
    )
    recovery_score = rec.score if rec and rec.score is not None else None

    # ── Mental ──
    mfs = (
        db.query(MentalFatigueScore)
        .filter(MentalFatigueScore.user_id == athlete.id)
        .order_by(MentalFatigueScore.date_iso.desc())
        .first()
    )
    mental_score = mfs.score if mfs and mfs.score is not None else None

    # ── Blood critical flag ──
    has_blood_critical = bool(
        db.query(BloodLabAlert)
        .filter(
            BloodLabAlert.user_id == athlete.id,
            BloodLabAlert.severity == "critical",
        )
        .first()
    )

    # ── Prescription compliance (last 7d) ──
    rxs = (
        db.query(WorkoutPrescription)
        .filter(
            WorkoutPrescription.athlete_id == athlete.id,
            WorkoutPrescription.date_iso >= week_ago.isoformat(),
        )
        .all()
    )
    rx_total = len(rxs)
    rx_completed = sum(1 for r in rxs if r.status == "completed")
    rx_missed = sum(
        1 for r in rxs
        if r.status == "pending" and r.date_iso < today.isoformat()
    )
    compliance_pct = round(rx_completed / rx_total * 100) if rx_total > 0 else None

    # ── Next race ──
    next_race = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == athlete.id,
            RaceEvent.date_iso >= today.isoformat(),
        )
        .order_by(RaceEvent.date_iso.asc())
        .first()
    )
    days_to_race = None
    race_name = None
    if next_race:
        race_date = date.fromisoformat(next_race.date_iso)
        days_to_race = (race_date - today).days
        race_name = next_race.name

    risk = _risk_level(acwr, recovery_score, rx_missed, has_blood_critical)

    name = getattr(athlete, "nombre", None) or athlete.email

    return {
        "athlete_id":      athlete.id,
        "name":            name,
        "email":           athlete.email,
        "ctl":             ctl,
        "atl":             atl,
        "acwr":            acwr,
        "ctl_trend":       ctl_trend,
        "tss_7d":          tss_7d,
        "recovery_score":  recovery_score,
        "mental_score":    mental_score,
        "blood_critical":  has_blood_critical,
        "rx_total_7d":     rx_total,
        "rx_completed_7d": rx_completed,
        "rx_missed":       rx_missed,
        "compliance_pct":  compliance_pct,
        "days_to_race":    days_to_race,
        "race_name":       race_name,
        "risk":            risk,
    }


# ── Squad overview ──────────────────────────────────────────────────────────

_RISK_ORDER = {"critical": 0, "warning": 1, "unknown": 2, "ok": 3}


def _coach_group_ids(coach_id: str, db: Session) -> list[str]:
    """Fetch IDs of groups owned by this coach from the 'groups' table.

    Uses raw SQL to avoid the naming collision between the coach Group
    (groups table) and the community Group (community_groups table) in models.py.
    """
    rows = db.execute(
        text("SELECT id FROM groups WHERE coach_id = :cid"),
        {"cid": coach_id},
    ).fetchall()
    return [r[0] for r in rows]


def _group_athlete_ids(group_ids: list[str], db: Session) -> list[str]:
    """Fetch distinct athlete_ids from group_members for the given groups."""
    if not group_ids:
        return []
    placeholders = ",".join(f":g{i}" for i in range(len(group_ids)))
    params = {f"g{i}": gid for i, gid in enumerate(group_ids)}
    rows = db.execute(
        text(f"SELECT DISTINCT athlete_id FROM group_members WHERE group_id IN ({placeholders})"),
        params,
    ).fetchall()
    return [r[0] for r in rows]


def get_squad_overview(coach: User, db: Session) -> dict:
    """Return full squad view for the coach: all athletes sorted by risk."""
    group_ids = _coach_group_ids(coach.id, db)
    if not group_ids:
        return {
            "squad_size": 0,
            "athletes":   [],
            "summary":    {"critical": 0, "warning": 0, "ok": 0, "unknown": 0},
        }

    athlete_ids = _group_athlete_ids(group_ids, db)
    # deduplicate (athlete may be in multiple groups)
    athlete_ids = list(dict.fromkeys(athlete_ids))

    if not athlete_ids:
        return {
            "squad_size": 0,
            "athletes":   [],
            "summary":    {"critical": 0, "warning": 0, "ok": 0, "unknown": 0},
        }

    athletes = (
        db.query(User)
        .filter(User.id.in_(athlete_ids), User.activo == True)
        .all()
    )

    cards = [_athlete_squad_card(a, db) for a in athletes]
    cards.sort(key=lambda c: _RISK_ORDER.get(c["risk"], 9))

    summary: dict[str, int] = {"critical": 0, "warning": 0, "ok": 0, "unknown": 0}
    for c in cards:
        summary[c["risk"]] = summary.get(c["risk"], 0) + 1

    return {
        "squad_size": len(cards),
        "athletes":   cards,
        "summary":    summary,
    }
