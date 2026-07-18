"""
LabX AI Coach Assistant
========================
Chat con Coach IA usando contexto fisiológico real del atleta.

Cambios Sprint 1:
  - Usa context_engine.get_context_for_prompt() en lugar de _build_context()
    → El chat ahora conoce CTL/ATL/TSB/HRV/Body Battery/Sueño/Riesgo lesión
  - Persiste sesiones y mensajes en ai_sessions + ai_messages
  - Endpoint GET /ai/sessions para historial de conversaciones
  - Endpoint GET /ai/insights para insights proactivos activos
  - Corregidos bugs de nombres de columna (date_iso, dur_min, dist_km, sport)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AIInsight, AIMessage, AISession, User
from ..auth import get_current_user
from ..services.context_engine import get_context_for_prompt
from ..plan_features import require_feature

logger = logging.getLogger("labx.ai")
router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_feature("ai_coach"))])

_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT_BASE = """Eres el Coach IA de LabX, experto en triatlón y deportes de resistencia.
Tienes acceso al perfil fisiológico completo y datos de entrenamiento reales del atleta.

REGLAS:
- Responde SIEMPRE en el mismo idioma que el atleta (español o portugués).
- Sé específico con los números del atleta — nunca des consejos genéricos.
- Cuando el atleta mencione fatiga, carga o recuperación, usa sus datos de CTL/ATL/TSB/HRV.
- No hagas diagnósticos médicos. Ante síntomas físicos serios → recomienda médico deportivo.
- Enfócate en: carga, recuperación, zonas de entrenamiento, nutrición peri-entrenamiento,
  estrategia de carrera, análisis de actividades específicas del atleta.
- Si ves riesgo de lesión alto en los datos → mencionarlo proactivamente aunque no pregunten.
- Sé conciso: bullets cuando sea útil, no más de 5 párrafos por respuesta.

A continuación están los datos actuales del atleta:
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_session(session_id: str | None, user_id: str, db: Session) -> AISession:
    """Retorna sesión existente o crea una nueva."""
    if session_id:
        sess = db.query(AISession).filter(
            AISession.id      == session_id,
            AISession.user_id == user_id,
            AISession.deleted_at.is_(None),
        ).first()
        if sess:
            return sess

    sess = AISession(user_id=user_id, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(sess)
    db.flush()  # obtener ID antes del commit
    return sess


def _auto_title(text: str) -> str:
    """Genera un título corto desde el primer mensaje del usuario."""
    clean = text.strip()[:60]
    return clean + ("…" if len(text.strip()) > 60 else "")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/coach-suggest")
async def coach_suggest(
    body: dict,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    Consulta al Coach IA.
    El sistema prompt incluye el contexto fisiológico completo del atleta.
    Persiste la conversación en ai_sessions + ai_messages.

    Body:
      message:    str           — Mensaje del usuario (requerido)
      session_id: str|null      — ID de sesión existente (null = nueva sesión)
      history:    [{role,content}] — Historial reciente del frontend (hasta 10 turnos)
    """
    if not _ANTHROPIC_KEY:
        raise HTTPException(503, "AI Coach no configurado — agrega ANTHROPIC_API_KEY al .env")

    question   = (body.get("message") or "").strip()
    session_id = body.get("session_id")
    history    = body.get("history", [])

    if not question:
        raise HTTPException(422, "Mensaje requerido")
    if len(question) > 2000:
        raise HTTPException(422, "Mensaje demasiado largo (máx 2000 caracteres)")

    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, "anthropic SDK no instalado — pip install anthropic")

    # ── Contexto del atleta ──────────────────────────────────────────────────
    athlete_context = get_context_for_prompt(me.id, db)
    system_prompt   = SYSTEM_PROMPT_BASE + "\n" + athlete_context

    # ── Historial de mensajes ────────────────────────────────────────────────
    messages = []
    for turn in (history or [])[-10:]:
        role    = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    # ── Llamada a Anthropic (async con timeout) ──────────────────────────────
    import asyncio
    _AI_TIMEOUT = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))

    async def _call_ai():
        client = anthropic.AsyncAnthropic(api_key=_ANTHROPIC_KEY)
        return await client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 1024,
            system     = system_prompt,
            messages   = messages,
        )

    try:
        resp = await asyncio.wait_for(_call_ai(), timeout=_AI_TIMEOUT)
        answer     = resp.content[0].text if resp.content else "Sin respuesta"
        tokens_in  = resp.usage.input_tokens
        tokens_out = resp.usage.output_tokens

    except asyncio.TimeoutError:
        logger.error("Anthropic timeout (%ds) user=%s", _AI_TIMEOUT, me.id)
        raise HTTPException(504, f"AI Coach tardó más de {_AI_TIMEOUT}s. Intenta de nuevo.")
    except anthropic.APIStatusError as e:
        logger.error("Anthropic API error user=%s: %s", me.id, e)
        raise HTTPException(502, f"Error de API AI: {e.message}")
    except Exception as e:
        logger.error("AI coach error user=%s: %s", me.id, e)
        raise HTTPException(500, "Error interno del AI Coach")

    # ── Persistir sesión y mensajes ──────────────────────────────────────────
    try:
        sess = _get_or_create_session(session_id, me.id, db)

        # Auto-título de la sesión si es el primer mensaje
        if not sess.title:
            sess.title = _auto_title(question)

        sess.last_message_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Contexto snapshot (métricas clave en el momento del mensaje)
        from ..models import AIAthleteContext
        ctx_row = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == me.id).first()
        ctx_snapshot = None
        if ctx_row:
            ctx_snapshot = json.dumps({
                "ctl":       ctx_row.current_ctl,
                "atl":       ctx_row.current_atl,
                "tsb":       ctx_row.current_tsb,
                "acwr":      ctx_row.current_acwr,
                "hrv":       ctx_row.current_hrv,
                "readiness": ctx_row.current_readiness,
            }, default=str)

        db.add(AIMessage(
            session_id       = sess.id,
            role             = "user",
            content          = question,
            context_snapshot = ctx_snapshot,
            created_at       = datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.add(AIMessage(
            session_id    = sess.id,
            role          = "assistant",
            content       = answer,
            tokens_input  = tokens_in,
            tokens_output = tokens_out,
            model_version = "claude-sonnet-4-6",
            created_at    = datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.commit()
        session_id = sess.id

    except Exception as e:
        logger.warning("AI session persist error user=%s: %s", me.id, e)
        db.rollback()
        session_id = None

    logger.info("AI coach user=%s tokens_in=%d tokens_out=%d session=%s",
                me.id, tokens_in, tokens_out, session_id)

    return {
        "ok":        True,
        "answer":    answer,
        "session_id": session_id,
    }


@router.get("/sessions")
def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Lista las sesiones de chat del atleta, ordenadas por más reciente."""
    sessions = (
        db.query(AISession)
        .filter(AISession.user_id == me.id, AISession.deleted_at.is_(None))
        .order_by(AISession.last_message_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":              s.id,
            "title":           s.title or "Conversación",
            "last_message_at": s.last_message_at.isoformat() if s.last_message_at else None,
            "created_at":      s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Retorna los mensajes de una sesión de chat."""
    sess = db.query(AISession).filter(
        AISession.id      == session_id,
        AISession.user_id == me.id,
        AISession.deleted_at.is_(None),
    ).first()
    if not sess:
        raise HTTPException(404, "Sesión no encontrada")

    msgs = (
        db.query(AIMessage)
        .filter(AIMessage.session_id == session_id)
        .order_by(AIMessage.created_at)
        .all()
    )
    return {
        "session": {
            "id":    sess.id,
            "title": sess.title or "Conversación",
        },
        "messages": [
            {
                "role":       m.role,
                "content":    m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Soft-delete de una sesión de chat."""
    sess = db.query(AISession).filter(
        AISession.id      == session_id,
        AISession.user_id == me.id,
    ).first()
    if not sess:
        raise HTTPException(404, "Sesión no encontrada")
    sess.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


@router.get("/insights")
def get_insights(
    limit:    int  = Query(10, ge=1, le=50),
    include_dismissed: bool = Query(False),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Retorna los insights proactivos activos del atleta."""
    q = (
        db.query(AIInsight)
        .filter(AIInsight.user_id == me.id)
        .filter(
            (AIInsight.expires_at.is_(None)) |
            (AIInsight.expires_at > datetime.now(timezone.utc).replace(tzinfo=None))
        )
    )
    if not include_dismissed:
        q = q.filter(AIInsight.dismissed_at.is_(None))

    insights = q.order_by(AIInsight.severity.desc(), AIInsight.created_at.desc()).limit(limit).all()

    return [
        {
            "id":           i.id,
            "type":         i.type,
            "severity":     i.severity,
            "title":        i.title,
            "body":         i.body,
            "cta_text":     i.cta_text,
            "cta_url":      i.cta_url,
            "created_at":   i.created_at.isoformat() if i.created_at else None,
            "acknowledged": i.acknowledged_at is not None,
        }
        for i in insights
    ]


@router.patch("/insights/{insight_id}/dismiss")
def dismiss_insight(
    insight_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Dismissea (oculta) un insight proactivo."""
    insight = db.query(AIInsight).filter(
        AIInsight.id      == insight_id,
        AIInsight.user_id == me.id,
    ).first()
    if not insight:
        raise HTTPException(404, "Insight no encontrado")
    insight.dismissed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


@router.get("/context")
def get_my_context(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Retorna el contexto actual del atleta (métricas clave + factores del Readiness).
    Útil para el frontend mostrar el Readiness Score, factor bars e injury risk.
    """
    from ..models import AIAthleteContext, GarminHealthDaily
    from datetime import date
    import json as _json

    row = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == me.id).first()
    if not row:
        return {"available": False, "message": "Completa tu primer sync de Garmin para activar la IA."}

    # Readiness factors del día de hoy desde garmin_health_daily
    readiness_factors = {}
    today_iso = date.today().isoformat()
    health_row = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == me.id,
        GarminHealthDaily.date_iso == today_iso,
    ).first()
    if health_row and health_row.labx_readiness_factors:
        try:
            readiness_factors = _json.loads(health_row.labx_readiness_factors)
        except (ValueError, TypeError):
            pass

    # Injury risk level interpretado
    risk = row.injury_risk_score or 0.0
    risk_level = "critical" if risk > 0.6 else "caution" if risk > 0.3 else "low"
    risk_tips = {
        "critical": "Reduce la carga esta semana. ACWR elevado + HRV en declive.",
        "caution":  "Monitorea recuperación. Prioriza sueño y nutrición.",
        "low":      "Cargas dentro de zona segura. Puedes mantener el plan.",
    }

    return {
        "available":          True,
        "ctl":                row.current_ctl,
        "atl":                row.current_atl,
        "tsb":                row.current_tsb,
        "acwr":               row.current_acwr,
        "hrv":                row.current_hrv,
        "readiness":          row.current_readiness,
        "readiness_factors":  readiness_factors,
        "injury_risk":        round(risk, 2),
        "injury_risk_level":  risk_level,
        "injury_risk_tip":    risk_tips[risk_level],
        "days_to_race":       row.days_to_race,
        "built_at":           row.context_built_at.isoformat() if row.context_built_at else None,
    }


# ─── Sprint 20: AI Intelligence Engine v2 ─────────────────────────────────
from ..services.ai_engine import (
    generate_workout, generate_weekly_report, forecast_ctl,
    assess_injury_risk, generate_coach_insights,
)


@router.post("/generate-workout")
def api_generate_workout(
    body: dict,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    from ..models import AIAthleteContext, RecoveryScore
    from datetime import date as _date

    ctx = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == me.id).first()
    ctl = getattr(ctx, "current_ctl", None)
    tsb = getattr(ctx, "current_tsb", None)
    dtr = getattr(ctx, "days_to_race", None)

    rec_row = (
        db.query(RecoveryScore)
        .filter(RecoveryScore.user_id == me.id,
                RecoveryScore.date_iso == _date.today().isoformat())
        .first()
    )
    rec_score = rec_row.score if rec_row else None

    wkt = generate_workout(
        sport=str(body.get("sport", "run")).lower(),
        focus=str(body.get("focus", "endurance")).lower(),
        duration_min=int(body.get("duration_min", 60)),
        ctl=ctl, tsb=tsb, recovery_score=rec_score,
        days_to_race=body.get("days_to_race", dtr),
    )
    return {
        "title": wkt.title, "sport": wkt.sport, "focus": wkt.focus,
        "total_duration": wkt.total_duration_min, "estimated_tss": wkt.estimated_tss,
        "form_state": wkt.form_state, "override_reason": wkt.override_reason,
        "phases": [{"name": p.name, "duration_min": p.duration_min, "zone": p.zone,
                    "zone_range": p.zone_range, "description": p.description, "rpe": p.rpe}
                   for p in wkt.phases],
        "key_points": wkt.key_points, "warnings": wkt.warnings,
        "fitness_context": {"ctl": ctl, "tsb": tsb, "recovery_score": rec_score},
    }


@router.get("/weekly-report")
def api_weekly_report(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    from ..models import AIAthleteContext, GarminActivity
    from datetime import date as _date, timedelta as _td

    ctx  = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == me.id).first()
    ctl  = getattr(ctx, "current_ctl", None)
    atl  = getattr(ctx, "current_atl", None)
    tsb  = getattr(ctx, "current_tsb", None)
    dtr  = getattr(ctx, "days_to_race", None)
    risk = getattr(ctx, "injury_risk_score", None)
    hrv_trend = getattr(ctx, "hrv_trend", None) if ctx else None

    week_start = _date.today() - _td(days=7)
    acts = db.query(GarminActivity).filter(
        GarminActivity.user_id == me.id,
        GarminActivity.date_iso >= week_start.isoformat(),
    ).all()
    week_tss   = int(sum(a.tss or 0 for a in acts))
    week_hours = round(sum((a.dur_min or 0) for a in acts) / 60, 1)

    r = generate_weekly_report(ctl=ctl, atl=atl, tsb=tsb,
        week_tss=week_tss, week_hours=week_hours,
        injury_risk=risk, days_to_race=dtr, hrv_trend=hrv_trend)

    return {
        "week_label": r.week_label, "load_summary": r.load_summary,
        "form_assessment": r.form_assessment,
        "key_achievements": r.key_achievements, "concerns": r.concerns,
        "next_week": {
            "recommendations": r.next_week_recommendations,
            "tss_range": {"min": r.suggested_tss_range[0], "max": r.suggested_tss_range[1]},
            "focus": r.suggested_focus,
        },
        "week_score": r.score,
        "raw": {"ctl": ctl, "atl": atl, "tsb": tsb, "week_tss": week_tss,
                "week_hours": week_hours, "activities": len(acts)},
    }


@router.get("/forecast")
def api_forecast(
    weeks: int = Query(8, ge=2, le=16),
    tss_per_week: int = Query(None, ge=0, le=3000),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    from ..models import AIAthleteContext, GarminActivity
    from datetime import date as _date, timedelta as _td

    ctx = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == me.id).first()
    ctl = float(getattr(ctx, "current_ctl", 50) or 50)
    atl = float(getattr(ctx, "current_atl", 50) or 50)

    if tss_per_week is None:
        week_start = _date.today() - _td(days=7)
        acts = db.query(GarminActivity).filter(
            GarminActivity.user_id == me.id,
            GarminActivity.date_iso >= week_start.isoformat(),
        ).all()
        tss_per_week = max(100, int(sum(a.tss or 0 for a in acts) * 1.05))

    proj = forecast_ctl(current_ctl=ctl, current_atl=atl,
                        weekly_tss_plan=[tss_per_week], weeks=weeks)

    return {
        "current": {"ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(ctl - atl, 1)},
        "assumption_tss_per_week": tss_per_week,
        "projection": [{"week": p.week, "ctl": p.ctl, "atl": p.atl, "tsb": p.tsb,
                        "form_label": p.form_label, "planned_tss": p.planned_tss, "notes": p.notes}
                       for p in proj],
    }


@router.get("/injury-forecast")
def api_injury_forecast(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    from ..models import AIAthleteContext, GarminTrainingLoad

    ctx  = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == me.id).first()
    acwr = getattr(ctx, "current_acwr", None)
    dtr  = getattr(ctx, "days_to_race", None)

    load_row = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == me.id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    monotony  = getattr(load_row, "monotony", None)
    strain    = getattr(load_row, "strain", None)
    hrv_trend = getattr(ctx, "hrv_trend", "stable") if ctx else "stable"

    rpt = assess_injury_risk(acwr=acwr, monotony=monotony, strain=strain,
                              hrv_trend=hrv_trend, days_to_race=dtr)
    return {
        "risk_score": rpt.current_risk_score, "risk_level": rpt.risk_level,
        "primary_driver": rpt.primary_driver, "time_at_risk_days": rpt.time_at_risk_days,
        "recovery_days_needed": rpt.recovery_days_needed,
        "action_plan": rpt.action_plan, "warning_signs": rpt.warning_signs,
        "raw": {"acwr": acwr, "monotony": monotony, "strain": strain, "hrv_trend": hrv_trend},
    }


@router.get("/coach-copilot")
def api_coach_copilot(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    from ..models import CoachAthlete, AIAthleteContext, User as UserModel

    if me.rol not in ("coach", "admin"):
        raise HTTPException(403, "Acceso solo para coaches")

    links = db.query(CoachAthlete).filter(
        CoachAthlete.coach_id == me.id, CoachAthlete.active.is_(True)
    ).all()

    athletes_data = []
    for link in links:
        u   = db.query(UserModel).filter(UserModel.id == link.athlete_id).first()
        ctx = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == link.athlete_id).first()
        if not u:
            continue
        athletes_data.append({
            "user_id": link.athlete_id, "name": u.name or u.email,
            "ctl": getattr(ctx, "current_ctl", None), "atl": getattr(ctx, "current_atl", None),
            "tsb": getattr(ctx, "current_tsb", None),
            "recovery_score": getattr(ctx, "current_readiness", None),
            "injury_risk": getattr(ctx, "injury_risk_score", None),
            "days_to_race": getattr(ctx, "days_to_race", None),
        })

    rpt = generate_coach_insights(athletes_data)
    return {
        "summary": rpt.summary, "total_athletes": rpt.total_athletes,
        "team_avg_ctl": rpt.team_avg_ctl, "team_avg_tsb": rpt.team_avg_tsb,
        "alerts": [{"user_id": a.user_id, "name": a.name, "severity": a.severity,
                    "message": a.message, "action": a.action} for a in rpt.alerts],
        "clusters": [{"label": c.label, "count": len(c.athlete_ids),
                      "athlete_ids": c.athlete_ids, "recommendation": c.recommendation}
                     for c in rpt.clusters],
    }
