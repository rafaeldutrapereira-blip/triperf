"""
Athlete Intelligence Service — Sprint 28.

Aggregates all intelligence modules for a single athlete into one response.
Used by coaches to get a 360° view without N API calls from the frontend.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timedelta, date, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    User,
    GarminTrainingLoad,
    RecoveryScore,
    MentalFatigueScore,
    MentalCheckin,
    BloodLabExam,
    BloodLabAlert,
    FoodDiaryEntry,
    HydrationLog,
    SupplementLog,
    WorkoutPrescription,
    WellnessLog,
)

_CTL_TAU = 42
_ATL_TAU = 7
_CTL_DECAY = 1 - math.exp(-1 / _CTL_TAU)
_ATL_DECAY = 1 - math.exp(-1 / _ATL_TAU)


def _today_iso() -> str:
    return date.today().isoformat()


def _date_n_days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _tsb_form_label(tsb: float) -> str:
    if tsb >= 15:  return "Forma Pico"
    if tsb >= 5:   return "Buena Forma"
    if tsb >= -5:  return "Neutro"
    if tsb >= -15: return "Fatiga Moderada"
    if tsb > -25:  return "Fatiga Alta"
    return "Sobrecarga"


def _acwr_risk(acwr: float) -> tuple[str, str]:
    if acwr < 0.8:   return "undertrained", "#6b7280"
    if acwr <= 1.3:  return "safe",         "#10b981"
    if acwr <= 1.5:  return "moderate",     "#f59e0b"
    return "elevated", "#ef4444"


# ── Training snapshot ─────────────────────────────────────────────────────────

def _training_snapshot(athlete_id: str, db: Session) -> dict:
    today = _today_iso()
    cutoff_7d  = _date_n_days_ago(7)
    cutoff_28d = _date_n_days_ago(28)

    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id == athlete_id,
            GarminTrainingLoad.date_iso <= today,
        )
        .order_by(GarminTrainingLoad.date_iso.desc())
        .limit(35)
        .all()
    )

    latest = loads[0] if loads else None
    ctl    = round(latest.ctl, 1) if latest else 0.0
    atl    = round(latest.atl, 1) if latest else 0.0
    tsb    = round(latest.tsb, 1) if latest else 0.0

    tss_7d  = sum(l.tss for l in loads if l.date_iso >= cutoff_7d)
    tss_28d = sum(l.tss for l in loads if l.date_iso >= cutoff_28d)

    acute_avg   = tss_7d / 7.0
    chronic_avg = tss_28d / 28.0
    acwr = round(acute_avg / chronic_avg, 2) if chronic_avg > 0 else 1.0
    acwr_level, acwr_color = _acwr_risk(acwr)

    trend_7d = [
        {"date_iso": l.date_iso, "ctl": round(l.ctl, 1), "tsb": round(l.tsb, 1), "tss": round(l.tss, 1)}
        for l in reversed(loads[:7])
    ]

    return {
        "ctl": ctl,
        "atl": atl,
        "tsb": tsb,
        "form_label": _tsb_form_label(tsb),
        "acwr": acwr,
        "acwr_risk": acwr_level,
        "acwr_color": acwr_color,
        "tss_7d": round(tss_7d, 1),
        "tss_28d": round(tss_28d, 1),
        "trend_7d": trend_7d,
    }


# ── Recovery snapshot ─────────────────────────────────────────────────────────

def _recovery_snapshot(athlete_id: str, db: Session) -> dict:
    cutoff = _date_n_days_ago(14)
    scores = (
        db.query(RecoveryScore)
        .filter(RecoveryScore.user_id == athlete_id, RecoveryScore.date_iso >= cutoff)
        .order_by(RecoveryScore.date_iso.desc())
        .limit(14)
        .all()
    )

    latest = scores[0] if scores else None
    trend_7d = [
        {"date_iso": s.date_iso, "score": s.score, "level": s.level}
        for s in reversed(scores[:7])
    ]
    avg_7d = round(sum(s.score for s in scores[:7] if s.score) / max(1, len([s for s in scores[:7] if s.score])), 1)

    return {
        "latest_score": latest.score if latest else None,
        "latest_date": latest.date_iso if latest else None,
        "latest_level": latest.level if latest else None,
        "training_suggestion": latest.training_suggestion if latest else None,
        "avg_7d": avg_7d,
        "trend_7d": trend_7d,
    }


# ── Mental snapshot ───────────────────────────────────────────────────────────

def _mental_snapshot(athlete_id: str, db: Session) -> dict:
    cutoff = _date_n_days_ago(14)
    scores = (
        db.query(MentalFatigueScore)
        .filter(MentalFatigueScore.user_id == athlete_id, MentalFatigueScore.date_iso >= cutoff)
        .order_by(MentalFatigueScore.date_iso.desc())
        .limit(14)
        .all()
    )

    latest = scores[0] if scores else None
    recent_scores = [s.score for s in scores[:7] if s.score is not None]
    avg_7d = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None

    # Latest checkin for motivation/anxiety details
    checkin = (
        db.query(MentalCheckin)
        .filter(MentalCheckin.user_id == athlete_id)
        .order_by(MentalCheckin.date_iso.desc())
        .first()
    )

    trend_7d = [
        {"date_iso": s.date_iso, "score": s.score, "level": s.level}
        for s in reversed(scores[:7])
    ]

    return {
        "latest_score": latest.score if latest else None,
        "latest_level": latest.level if latest else None,
        "latest_date": latest.date_iso if latest else None,
        "avg_7d": avg_7d,
        "trend_7d": trend_7d,
        "latest_checkin": {
            "motivation": checkin.motivation,
            "anxiety": checkin.anxiety,
            "focus": checkin.focus,
            "confidence": checkin.confidence,
            "mood": checkin.mood,
            "date_iso": checkin.date_iso,
        } if checkin else None,
    }


# ── Blood labs snapshot ───────────────────────────────────────────────────────

def _blood_labs_snapshot(athlete_id: str, db: Session) -> dict:
    exam = (
        db.query(BloodLabExam)
        .filter(BloodLabExam.user_id == athlete_id)
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )

    if not exam:
        return {"has_labs": False, "days_since_exam": None, "trs": None,
                "critical_markers": [], "warning_markers": [], "last_exam_date": None}

    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    exam_date = datetime.fromisoformat(exam.date_iso).date()
    days_since = (today - exam_date).days

    alerts = (
        db.query(BloodLabAlert)
        .filter(BloodLabAlert.exam_id == exam.id, BloodLabAlert.dismissed_at.is_(None))
        .all()
    )

    critical = [a.marker_key for a in alerts if a.severity == "critical"]
    warning  = [a.marker_key for a in alerts if a.severity == "warning"]

    # TRS: 100 - sum of restriction scores
    restriction_weights = {
        "critical": 20,
        "warning": 10,
    }
    trs = max(0, 100 - sum(restriction_weights.get(a.severity, 0) for a in alerts))

    return {
        "has_labs": True,
        "last_exam_date": exam.date_iso,
        "days_since_exam": days_since,
        "trs": trs,
        "critical_markers": critical,
        "warning_markers": warning,
        "total_alerts": len(alerts),
        "lab_name": exam.lab_name,
    }


# ── Nutrition snapshot ────────────────────────────────────────────────────────

def _nutrition_snapshot(athlete_id: str, db: Session) -> dict:
    cutoff = _date_n_days_ago(7)
    entries = (
        db.query(FoodDiaryEntry)
        .filter(FoodDiaryEntry.user_id == athlete_id, FoodDiaryEntry.date_iso >= cutoff)
        .all()
    )

    days_with_data = len({e.date_iso for e in entries})
    kcal_avg = round(
        sum(e.kcal for e in entries if e.kcal) / max(1, days_with_data), 0
    ) if entries else None

    supplements_30d = (
        db.query(SupplementLog)
        .filter(SupplementLog.user_id == athlete_id, SupplementLog.date_iso >= _date_n_days_ago(30))
        .count()
    )

    return {
        "days_logged_7d": days_with_data,
        "kcal_avg_7d": kcal_avg,
        "supplements_active_30d": supplements_30d,
        "has_diary_data": days_with_data > 0,
    }


# ── Prescription snapshot ─────────────────────────────────────────────────────

def _prescription_snapshot(athlete_id: str, db: Session) -> dict:
    cutoff_30d = _date_n_days_ago(30)

    all_30d = (
        db.query(WorkoutPrescription)
        .filter(
            WorkoutPrescription.athlete_id == athlete_id,
            WorkoutPrescription.date_iso >= cutoff_30d,
        )
        .all()
    )

    pending   = [r for r in all_30d if r.status == "pending"]
    completed = [r for r in all_30d if r.status == "completed"]
    skipped   = [r for r in all_30d if r.status == "skipped"]

    total_decided = len(completed) + len(skipped)
    compliance_pct = round(len(completed) / total_decided * 100, 0) if total_decided else None

    return {
        "pending_count": len(pending),
        "completed_30d": len(completed),
        "skipped_30d": len(skipped),
        "compliance_pct": compliance_pct,
    }


# ── Alert generation ──────────────────────────────────────────────────────────

def _generate_athlete_alerts(
    training: dict,
    recovery: dict,
    mental: dict,
    blood: dict,
    prescriptions: dict,
) -> list[dict]:
    alerts: list[dict] = []

    def alert(severity: str, module: str, message: str):
        alerts.append({"severity": severity, "module": module, "message": message})

    # Training
    tsb = training.get("tsb", 0)
    if tsb <= -25:
        alert("critical", "training", f"TSB en sobrecarga ({tsb}) — riesgo lesión")
    elif tsb <= -15:
        alert("warning", "training", f"Fatiga alta (TSB {tsb}) — revisar carga")
    if training.get("acwr_risk") == "elevated":
        alert("critical", "training", f"ACWR elevado ({training['acwr']}) — riesgo sobreentrenamiento")
    elif training.get("acwr_risk") == "moderate":
        alert("warning", "training", f"ACWR moderado ({training['acwr']}) — monitorear")

    # Recovery
    rec_score = recovery.get("latest_score")
    if rec_score is not None:
        if rec_score < 40:
            alert("critical", "recovery", f"Recuperación crítica ({rec_score}/100)")
        elif rec_score < 55:
            alert("warning", "recovery", f"Recuperación baja ({rec_score}/100)")

    # Mental
    mental_score = mental.get("latest_score")
    if mental_score is not None:
        if mental_score < 35:
            alert("critical", "mental", f"Bienestar mental crítico ({mental_score}/100)")
        elif mental_score < 50:
            alert("warning", "mental", f"Bienestar mental bajo ({mental_score}/100)")
    latest_ci = mental.get("latest_checkin") or {}
    if latest_ci.get("motivation") is not None and latest_ci["motivation"] <= 2:
        alert("warning", "mental", "Motivación muy baja en último check-in")

    # Blood labs
    if blood.get("has_labs"):
        for marker in blood.get("critical_markers", []):
            alert("critical", "blood_labs", f"Marcador crítico: {marker}")
        for marker in blood.get("warning_markers", []):
            alert("warning", "blood_labs", f"Marcador alterado: {marker}")
        if blood.get("days_since_exam", 0) and blood["days_since_exam"] > 90:
            alert("warning", "blood_labs", f"Sin análisis de sangre en {blood['days_since_exam']} días")
    else:
        alert("info", "blood_labs", "Sin análisis de sangre registrado")

    # Prescriptions
    if prescriptions.get("pending_count", 0) >= 3:
        alert("warning", "prescriptions", f"{prescriptions['pending_count']} prescripciones pendientes sin completar")
    compliance = prescriptions.get("compliance_pct")
    if compliance is not None and compliance < 60:
        alert("warning", "prescriptions", f"Adherencia a prescripciones baja ({int(compliance)}%)")

    # Sort: critical → warning → info
    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 3))
    return alerts


# ── Public API ────────────────────────────────────────────────────────────────

def get_athlete_intelligence(athlete: User, db: Session) -> dict:
    """Aggregate all intelligence modules for a single athlete — O(6 DB round-trips)."""
    athlete_id = athlete.id

    training      = _training_snapshot(athlete_id, db)
    recovery      = _recovery_snapshot(athlete_id, db)
    mental        = _mental_snapshot(athlete_id, db)
    blood         = _blood_labs_snapshot(athlete_id, db)
    nutrition     = _nutrition_snapshot(athlete_id, db)
    prescriptions = _prescription_snapshot(athlete_id, db)
    alerts        = _generate_athlete_alerts(training, recovery, mental, blood, prescriptions)

    return {
        "athlete_id":   athlete_id,
        "athlete_name": getattr(athlete, "nombre", None) or getattr(athlete, "name", None) or athlete.email,
        "athlete_email": athlete.email,
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "training":     training,
        "recovery":     recovery,
        "mental":       mental,
        "blood_labs":   blood,
        "nutrition":    nutrition,
        "prescriptions": prescriptions,
        "alerts":       alerts,
        "alert_counts": {
            "critical": sum(1 for a in alerts if a["severity"] == "critical"),
            "warning":  sum(1 for a in alerts if a["severity"] == "warning"),
            "info":     sum(1 for a in alerts if a["severity"] == "info"),
        },
    }
