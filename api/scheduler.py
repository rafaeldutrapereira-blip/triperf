"""
APScheduler — jobs periódicos de LabX.

Jobs activos:
  drip_day3  — 3 días post-registro: email upgrade Pro
  drip_day7  — 7 días post-registro: email coach platform
  cleanup    — cada noche: limpia login_attempts > 24h
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.orm import Session

logger = logging.getLogger("labx.scheduler")
_scheduler: BackgroundScheduler | None = None


def _get_db() -> Session:
    from .database import SessionLocal
    return SessionLocal()


# ── Jobs ───────────────────────────────────────────────────────

def _send_drip_emails() -> None:
    """Ejecuta cada hora: envía drip day3 y day7 a usuarios que corresponda."""
    from .database import SessionLocal
    from .models import User
    from .mailer import send_day3_drip, send_day7_drip
    app_url = os.getenv("APP_URL", "http://localhost:8000")
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        users = db.query(User).filter(User.activo == True).all()
        for u in users:
            if not u.created_at:
                continue
            age_days = (now - u.created_at).days
            # Drip day3: enviar entre el día 3 y 4 (ventana de 24h para evitar duplicados)
            if age_days == 3 and not _drip_sent(u.id, "day3"):
                try:
                    send_day3_drip(u.email, u.nombre, app_url)
                    _mark_drip(u.id, "day3", db)
                    logger.info("Drip day3 enviado → %s", u.email)
                except Exception as e:
                    logger.error("Error drip day3 %s: %s", u.email, e)
            # Drip day7
            elif age_days == 7 and not _drip_sent(u.id, "day7"):
                try:
                    send_day7_drip(u.email, u.nombre, app_url)
                    _mark_drip(u.id, "day7", db)
                    logger.info("Drip day7 enviado → %s", u.email)
                except Exception as e:
                    logger.error("Error drip day7 %s: %s", u.email, e)
    finally:
        db.close()


def _cleanup_login_attempts() -> None:
    """Borra intentos de login con más de 24 horas."""
    from .database import SessionLocal
    from .models import LoginAttempt
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
        deleted = db.query(LoginAttempt).filter(LoginAttempt.attempted_at < cutoff).delete()
        db.commit()
        if deleted:
            logger.info("Cleanup: %d login_attempts eliminados", deleted)
    finally:
        db.close()


# ── S11: GDPR — retención de datos ────────────────────────────

def _gdpr_retention_cleanup() -> None:
    """
    S11: Elimina datos según política de retención:
    - audit_logs: conservar 2 años (GDPR Art.5 — minimización)
    - drip_logs:  conservar 6 meses
    - revoked_tokens: ya expirados (extra seguridad)
    """
    from .database import SessionLocal
    from .models import AuditLog, DripLog, RevokedToken
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Audit logs > 2 años
        audit_cutoff = now - timedelta(days=730)
        del_audit = db.query(AuditLog).filter(AuditLog.timestamp < audit_cutoff).delete()
        # Drip logs > 6 meses
        drip_cutoff = now - timedelta(days=183)
        del_drip = db.query(DripLog).filter(DripLog.sent_at < drip_cutoff).delete()
        # Tokens revocados ya expirados
        del_rt = db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete()
        db.commit()
        logger.info("GDPR retention: audit=%d drip=%d revoked_tokens=%d eliminados",
                    del_audit, del_drip, del_rt)
    except Exception as e:
        db.rollback()
        logger.error("GDPR retention error: %s", e)
    finally:
        db.close()


# ── S12/S14: Notificaciones periódicas ────────────────────────

def _send_weekly_summaries() -> None:
    """Envía resumen semanal a todos los atletas con notif_email_weekly=True."""
    from .database import SessionLocal
    from .models import User, GarminTrainingLoad
    from .mailer import send_email
    from .services.notification_service import email_weekly_summary
    from datetime import date, timedelta
    db = SessionLocal()
    try:
        athletes = db.query(User).filter(
            User.rol == "atleta",
            User.activo == True,
            User.notif_email_weekly == True,
        ).all()
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        for athlete in athletes:
            try:
                rows = db.query(GarminTrainingLoad).filter(
                    GarminTrainingLoad.user_id == athlete.id,
                    GarminTrainingLoad.date_iso >= week_ago,
                ).all()
                latest = rows[-1] if rows else None
                week_data = {
                    "tss_week": sum(r.tss for r in rows),
                    "ctl":      latest.ctl if latest else 0,
                }
                subject, body = email_weekly_summary(athlete.nombre, week_data)
                send_email(athlete.email, subject, body)
                logger.info("Weekly summary enviado → %s", athlete.email)
            except Exception as e:
                logger.error("Error weekly summary %s: %s", athlete.email, e)
    finally:
        db.close()


def _send_wellness_reminders() -> None:
    """
    Envía recordatorio wellness push a atletas que no registraron hoy
    y tienen notif_push_wellness=True.
    """
    from .database import SessionLocal
    from .models import User, WellnessLog
    from .services.notification_service import push_wellness_reminder
    from datetime import date
    db = SessionLocal()
    today = date.today().isoformat()
    try:
        athletes = db.query(User).filter(
            User.rol == "atleta",
            User.activo == True,
            User.notif_push_wellness == True,
        ).all()
        for athlete in athletes:
            try:
                already = db.query(WellnessLog).filter(
                    WellnessLog.user_id == athlete.id,
                    WellnessLog.date_iso == today,
                    WellnessLog.deleted_at == None,
                ).first()
                if not already:
                    from .routes.notification_routes import send_push_to_user
                    send_push_to_user(athlete.id, push_wellness_reminder(), db)
            except Exception as e:
                logger.error("Error wellness reminder %s: %s", athlete.id, e)
    finally:
        db.close()


# ── Blood Labs: recordatorio análisis periódico ───────────────────

def _blood_lab_reminders() -> None:
    """
    Mensual (1ro de cada mes): alerta a atletas cuyo último análisis
    tiene más de 75 días. Recomendación: análisis cada 3 meses.
    """
    from .database import SessionLocal
    from .models import User, BloodLabExam, AIInsight
    from datetime import date, timedelta
    db = SessionLocal()
    try:
        athletes = db.query(User).filter(
            User.rol == "atleta", User.activo == True
        ).all()
        cutoff_date = (date.today() - timedelta(days=75)).isoformat()
        for athlete in athletes:
            latest = (
                db.query(BloodLabExam)
                .filter(BloodLabExam.user_id == athlete.id)
                .order_by(BloodLabExam.date_iso.desc())
                .first()
            )
            if latest and latest.date_iso >= cutoff_date:
                continue  # análisis reciente, no recordar
            # Crear insight de recordatorio
            existing = db.query(AIInsight).filter(
                AIInsight.user_id == athlete.id,
                AIInsight.type    == "blood_lab_reminder",
                AIInsight.dismissed_at.is_(None),
            ).first()
            if not existing:
                db.add(AIInsight(
                    user_id  = athlete.id,
                    type     = "blood_lab_reminder",
                    severity = "info",
                    title    = "Análisis de sangre recomendado",
                    body     = ("Han pasado más de 75 días desde tu último análisis. "
                                "Registra tus labs para actualizar el Blood Labs Intelligence."),
                    cta_text = "Registrar análisis",
                    cta_url  = "/blood_labs.html",
                ))
        db.commit()
        logger.info("Blood lab reminders procesados")
    except Exception as e:
        db.rollback()
        logger.error("Blood lab reminders error: %s", e)
    finally:
        db.close()


# ── Context Engine: refresh diario ───────────────────────────────

def _refresh_ai_contexts() -> None:
    """
    6am diario: reconstruye el AthleteContext de todos los atletas activos.
    Incluye LabX Readiness Score, injury risk y datos de salud del día.
    """
    try:
        from .services.context_engine import refresh_all_active_contexts
        refresh_all_active_contexts(None)
        logger.info("AI context refresh completado")
    except Exception as e:
        logger.error("AI context refresh error: %s", e)


# ── B-13: Background Garmin sync 2h ───────────────────────────

def _background_garmin_sync_all() -> None:
    """
    B-13: Sincroniza datos Garmin de las últimas 24h para todos los atletas
    que tienen un token de Garmin válido. Corre cada 2 horas.
    Limitado a 1 día de datos para no saturar la API de Garmin.
    """
    from .database import SessionLocal
    from .models import User
    from pathlib import Path
    import json as _json

    db = SessionLocal()
    try:
        token_dir = Path("data/garmin_tokens")
        if not token_dir.exists():
            return

        users_with_token = set()
        for f in token_dir.glob("*.json"):
            try:
                uid = f.stem
                data = _json.loads(f.read_text())
                if data.get("oauth1_token") or data.get("oauth2_token"):
                    users_with_token.add(uid)
            except Exception:
                continue

        if not users_with_token:
            return

        users = db.query(User).filter(
            User.id.in_(list(users_with_token)),
            User.activo == True,
        ).all()

        synced = 0
        for u in users:
            try:
                from .garmin_pull_service import background_sync_user
                background_sync_user(u.id, days=1)   # solo últimas 24h en background sync
                synced += 1
            except Exception as e:
                logger.warning("Background sync failed user=%s: %s", u.id, e)

        if synced:
            logger.info("Background Garmin sync: %d atletas sincronizados", synced)

    except Exception as e:
        logger.error("Background sync global error: %s", e)
    finally:
        db.close()


# ── B-11: Proactive daily AI insights ──────────────────────────

def _daily_proactive_insights() -> None:
    """
    B-11: Genera un insight proactivo diario para cada atleta activo.
    Detecta patrones de sobreentrenamiento, recuperación incompleta,
    oportunidades de rendimiento, y recordatorios de carrera próxima.
    Genera un AIInsight tipo 'daily_coach_tip' si no hay uno de hoy.
    """
    from .database import SessionLocal
    from .models import User, AIInsight, GarminTrainingLoad, GarminHealthDaily
    from datetime import date
    import os as _os
    import anthropic as _anthropic

    api_key = _os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.debug("ANTHROPIC_API_KEY no configurada — saltando proactive insights")
        return

    db = SessionLocal()
    today = date.today().isoformat()

    try:
        users = db.query(User).filter(User.activo == True).all()
        generated = 0

        for u in users:
            # Solo 1 insight diario por atleta
            existing = db.query(AIInsight).filter(
                AIInsight.user_id    == u.id,
                AIInsight.type       == "daily_coach_tip",
                AIInsight.created_at >= datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0),
            ).first()
            if existing:
                continue

            # Solo atletas con datos recientes (activos en los últimos 14 días)
            recent_load = db.query(GarminTrainingLoad).filter(
                GarminTrainingLoad.user_id  == u.id,
                GarminTrainingLoad.date_iso >= (
                    datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=14)
                ).date().isoformat(),
            ).first()
            if not recent_load:
                continue

            try:
                from .services.context_engine import get_context_for_prompt
                context = get_context_for_prompt(u.id, db)

                client = _anthropic.Anthropic(api_key=api_key)
                resp   = client.messages.create(
                    model      = "claude-haiku-4-5-20251001",   # Haiku para jobs masivos (costo)
                    max_tokens = 300,
                    messages   = [{
                        "role": "user",
                        "content": f"""Datos del atleta (hoy {today}):
{context}

Genera UN tip de entrenamiento/recuperación personalizado y accionable para HOY.
Máximo 3 oraciones. Directo, específico a sus números, sin intro genérica.
Si hay riesgo de sobreentrenamiento → dilo. Si la forma está buena → recomienda.
Responde en español.""",
                    }],
                )
                tip_text = resp.content[0].text.strip() if resp.content else ""

                if tip_text:
                    db.add(AIInsight(
                        user_id    = u.id,
                        type       = "daily_coach_tip",
                        title      = f"Coach IA — {today}",
                        body       = tip_text,
                        priority   = 2,
                        is_read    = False,
                    ))
                    db.commit()
                    generated += 1

            except Exception as e:
                logger.warning("Proactive insight error user=%s: %s", u.id, e)
                db.rollback()

        if generated:
            logger.info("Proactive daily insights: %d generados (%s)", generated, today)

    except Exception as e:
        logger.error("Daily proactive insights error: %s", e)
    finally:
        db.close()


# ── B-15: Daily Injury Risk cálculo masivo ─────────────────────

def _daily_injury_risk_all() -> None:
    """
    B-15: Calcula el snapshot de riesgo de lesión para todos los atletas activos.
    Corre a las 6:30am (30 min después del sync Garmin 6am).
    Usa claude-haiku para minimizar costo si el score es crítico → genera alerta.
    """
    from .database import SessionLocal
    from .models import User
    from .services.injury_risk_service import compute_injury_risk

    db = SessionLocal()
    today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    try:
        users = db.query(User).filter(User.activo == True).all()
        computed = 0
        critical = 0

        for u in users:
            try:
                result = compute_injury_risk(u.id, db, today)
                computed += 1
                if result["risk_level"] in ("high", "critical"):
                    critical += 1
                    # Notificar al coach via AIInsight si riesgo alto
                    _notify_coach_injury_risk(u, result, db)
            except Exception as e:
                logger.warning("Injury risk calc error user=%s: %s", u.id, e)
                db.rollback()

        logger.info("Daily injury risk: %d calculados, %d en riesgo alto/crítico",
                    computed, critical)
    except Exception as e:
        logger.error("Daily injury risk global error: %s", e)
    finally:
        db.close()


def _notify_coach_injury_risk(user: "User", risk_result: dict, db) -> None:
    """
    Si el riesgo es high/critical, crea un AIInsight tipo 'injury_alert'
    visible para el coach en su panel de alertas.
    """
    from .models import AIInsight, CoachAthlete
    from datetime import date

    if risk_result["risk_level"] not in ("high", "critical"):
        return

    # Buscar coach del atleta
    ca = db.query(CoachAthlete).filter(
        CoachAthlete.athlete_id == user.id,
        CoachAthlete.activo     == True,
    ).first()
    if not ca:
        return

    top_alert = risk_result["alerts"][0]["msg"] if risk_result["alerts"] else "Riesgo elevado detectado"
    rec = risk_result["recommendations"][0] if risk_result["recommendations"] else ""
    score = risk_result["risk_score"]
    level = risk_result["risk_level"]

    # Evitar duplicados — solo 1 por atleta por día
    today = date.today().isoformat()
    existing = db.query(AIInsight).filter(
        AIInsight.user_id    == ca.coach_id,
        AIInsight.type       == "injury_alert",
        AIInsight.created_at >= datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0),
    ).filter(
        AIInsight.body.like(f"%{user.id}%")
    ).first()
    if existing:
        return

    db.add(AIInsight(
        user_id  = ca.coach_id,
        type     = "injury_alert",
        title    = f"⚠ Riesgo {'CRÍTICO' if level=='critical' else 'ALTO'}: {user.nombre or user.email}",
        body     = f"Score: {score:.0f}/100 — {top_alert}\n\nRecomendación: {rec}\n\nAtleta ID: {user.id}",
        priority = 1 if level == "critical" else 2,
        is_read  = False,
    ))
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("injury_alert insight commit falló user=%s: %s", user.id, exc)


# ── Control de drips enviados (tabla simple en BD) ─────────────

def _drip_sent(user_id: str, tag: str) -> bool:
    """Verifica si ya se envió este drip al usuario."""
    from .database import SessionLocal
    from .models import DripLog
    db = SessionLocal()
    try:
        return db.query(DripLog).filter(
            DripLog.user_id == user_id, DripLog.tag == tag
        ).first() is not None
    finally:
        db.close()


def _mark_drip(user_id: str, tag: str, db: Session) -> None:
    from .models import DripLog
    db.add(DripLog(user_id=user_id, tag=tag))
    db.commit()


# ── Arranque / parada ──────────────────────────────────────────

def _daily_plan_matching() -> None:
    """
    B-09: Corre a las 6:45am tras el sync de Garmin (6am) y el injury risk (6:30am).
    Auto-matchea sesiones planificadas con actividades Garmin reales de los últimos 7 días.
    También marca como skipped sesiones pasadas sin actividad correspondiente.
    """
    from .database import SessionLocal

    db = SessionLocal()
    try:
        from .services.plan_matching_service import match_sessions_all_users
        results = match_sessions_all_users(db, days_back=7)
        total_matched = sum(r.get("matched", 0) for r in results)
        total_skipped = sum(r.get("auto_skipped", 0) for r in results)
        if results:
            logger.info(
                "Plan matching: %d sesiones matcheadas, %d marcadas skipped en %d atletas",
                total_matched, total_skipped, len(results),
            )
    except Exception as e:
        logger.error("Plan matching global error: %s", e)
    finally:
        db.close()


def start_scheduler(database_url: str | None = None) -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    db_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/labx_coach.db")
    jobstore_url = db_url if not db_url.startswith("sqlite") else db_url

    jobstores = {}
    try:
        jobstores["default"] = SQLAlchemyJobStore(url=jobstore_url)
    except Exception:
        # Fallback: memory store si el jobstore falla
        logger.warning("Scheduler: usando memory store (jobstore DB falló)")

    _scheduler = BackgroundScheduler(jobstores=jobstores if jobstores else {})

    # Drip: cada hora
    _scheduler.add_job(
        _send_drip_emails,
        "interval", hours=1,
        id="drip_check", replace_existing=True,
        misfire_grace_time=3600,
    )
    # Cleanup: cada noche a las 3am — login_attempts + tokens revocados expirados
    _scheduler.add_job(
        _cleanup_login_attempts,
        "cron", hour=3, minute=0,
        id="cleanup_attempts", replace_existing=True,
    )
    # S11: GDPR retention — audit_logs > 2 años, drip_logs > 6 meses
    _scheduler.add_job(
        _gdpr_retention_cleanup,
        "cron", hour=4, minute=0,
        id="gdpr_retention", replace_existing=True,
    )
    # S12/S14: Resumen semanal — domingo a las 8am
    _scheduler.add_job(
        _send_weekly_summaries,
        "cron", day_of_week="sun", hour=8, minute=0,
        id="weekly_summaries", replace_existing=True,
    )
    # S14: Recordatorio wellness — diario a las 20:00
    _scheduler.add_job(
        _send_wellness_reminders,
        "cron", hour=20, minute=0,
        id="wellness_reminder", replace_existing=True,
    )

    # Context Engine: refrescar contexto IA de todos los atletas activos a las 6am
    _scheduler.add_job(
        _refresh_ai_contexts,
        "cron", hour=6, minute=0,
        id="ai_context_refresh", replace_existing=True,
    )
    # Blood Labs: recordatorio mensual (1ro de cada mes a las 9am)
    _scheduler.add_job(
        _blood_lab_reminders,
        "cron", day=1, hour=9, minute=0,
        id="blood_lab_reminders", replace_existing=True,
    )

    # B-13: Background Garmin sync cada 2h para todos los atletas con token activo
    _scheduler.add_job(
        _background_garmin_sync_all,
        "interval", hours=2,
        id="garmin_sync_2h", replace_existing=True,
        misfire_grace_time=1800,
    )

    # B-11: Proactive daily AI insight — 7:30am para atletas activos
    _scheduler.add_job(
        _daily_proactive_insights,
        "cron", hour=7, minute=30,
        id="daily_proactive_insights", replace_existing=True,
        misfire_grace_time=3600,
    )

    # B-15: Injury Risk — calcular snapshot diario a las 6:30am (tras el sync Garmin 6am)
    _scheduler.add_job(
        _daily_injury_risk_all,
        "cron", hour=6, minute=30,
        id="daily_injury_risk", replace_existing=True,
        misfire_grace_time=3600,
    )

    # B-09: Plan matching — auto-match sesiones planificadas con actividades reales tras sync Garmin
    _scheduler.add_job(
        _daily_plan_matching,
        "cron", hour=6, minute=45,
        id="plan_matching", replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info("Scheduler iniciado — %d jobs activos", len(_scheduler.get_jobs()))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
