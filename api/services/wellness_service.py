"""
S1 — Service Layer: Wellness aggregation & scoring.
"""
from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy.orm import Session

from ..models import WellnessLog


def wellness_score(log: WellnessLog) -> float:
    """
    Índice de bienestar 0-100 desde los 4 factores del WellnessLog.
    Cada uno va de 1 (peor) a 5 (mejor). Invertir fatigue y soreness.
    """
    if not log:
        return 0.0
    fatigue  = (6 - (log.fatigue  or 3)) * 5   # invertido: 5→25, 1→5
    sleep_q  = (log.sleep_q  or 3) * 5         # directo: 5→25, 1→5
    soreness = (6 - (log.soreness or 3)) * 5   # invertido
    mood     = (log.mood     or 3) * 5          # directo
    return round((fatigue + sleep_q + soreness + mood), 1)


def wellness_trend(db: Session, user_id: str, days: int = 14) -> list[dict]:
    """Devuelve los últimos N días de wellness con score calculado."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = (
        db.query(WellnessLog)
          .filter(
              WellnessLog.user_id == user_id,
              WellnessLog.date_iso >= cutoff,
              WellnessLog.deleted_at == None,
          )
          .order_by(WellnessLog.date_iso)
          .all()
    )
    return [
        {
            "date":     r.date_iso,
            "fatigue":  r.fatigue,
            "sleep_q":  r.sleep_q,
            "soreness": r.soreness,
            "mood":     r.mood,
            "score":    wellness_score(r),
        }
        for r in rows
    ]


def wellness_summary(db: Session, user_id: str) -> dict:
    """7-day wellness summary for dashboard widgets."""
    trend = wellness_trend(db, user_id, days=7)
    if not trend:
        return {"avg_score": None, "trend": [], "count": 0}
    avg = round(sum(t["score"] for t in trend) / len(trend), 1)
    return {"avg_score": avg, "trend": trend, "count": len(trend)}
