"""CUENTA-BORRADO (BUILD 367): eliminacion de cuenta en dos tiempos.

1) `request_deletion` (inmediato, al confirmar con la contrasena): desactiva la cuenta,
   invalida todas las sesiones, revoca integraciones, cancela cobros, cierra la relacion
   coach<->atleta y deja una solicitud en `account_deletion_requests`.
2) `purge_user` (job diario, tras el periodo de gracia; plazo maximo declarado 30 dias):
   aplica el mapa de cascada POLICY, borra los archivos y deja la fila de `users` como
   "tumba" anonima (necesaria para conservar los registros de pago sin datos personales).

POLICY es el mapa del Paso 0: cada columna con FK a users.id y su destino. Un test
verifica que ninguna FK quede fuera del mapa.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .database import Base
from .models import AccountDeletionRequest, User

logger = logging.getLogger("labx.account_deletion")

GRACE_DAYS = int(os.getenv("ACCOUNT_DELETION_GRACE_DAYS", "7"))
MAX_DAYS = 30            # plazo maximo declarado en pantalla y en la pagina publica
MAX_ATTEMPTS = 10

# Destinos:
#   delete : se borran las filas del usuario (y lo que depende de ellas)
#   null   : se desvincula (la fila es de un tercero)
#   scrub  : la fila se conserva (registro de auditoria) pero se vacian ip/agente/detalle
#   keep   : se conserva ligada a la cuenta anonimizada (pagos, o contenido que el
#            usuario creo para OTROS y no lo identifica una vez anonimizada la cuenta)
POLICY: dict[str, str] = {
    # -- datos propios del usuario: se borran
    "ai_athlete_context.user_id": "delete", "ai_insights.user_id": "delete",
    "ai_sessions.user_id": "delete", "ai_usage_daily.user_id": "delete",
    "activity_photos.user_id": "delete", "bikes.user_id": "delete",
    "blood_lab_alerts.user_id": "delete", "blood_lab_exams.user_id": "delete",
    "challenge_entries.user_id": "delete", "comments.user_id": "delete",
    "community_group_members.user_id": "delete", "community_notifications.user_id": "delete",
    "community_posts.user_id": "delete", "custom_foods.user_id": "delete",
    "drip_logs.user_id": "delete", "favorite_foods.user_id": "delete",
    "follows.follower_id": "delete", "follows.followed_id": "delete",
    "food_diary_entries.user_id": "delete", "garmin_activities.user_id": "delete",
    "garmin_health_daily.user_id": "delete", "garmin_oauth_states.user_id": "delete",
    "garmin_oauth_tokens.user_id": "delete", "garmin_planned_workouts.user_id": "delete",
    "garmin_sleep_sessions.user_id": "delete", "garmin_sync_status.user_id": "delete",
    "garmin_training_load.user_id": "delete", "hydration_logs.user_id": "delete",
    "indoor_workouts.user_id": "delete", "injury_risk_snapshots.user_id": "delete",
    "kudos.user_id": "delete", "mental_checkins.user_id": "delete",
    "mental_fatigue_scores.user_id": "delete", "mental_protocol_sessions.user_id": "delete",
    "messages.to_user_id": "delete", "messages.from_user_id": "delete",
    "nutrition_insights.user_id": "delete", "nutrition_plans.user_id": "delete",
    "own_plan_sessions.user_id": "delete", "password_reset_tokens.user_id": "delete",
    "personal_records.user_id": "delete", "plan_adaptations.user_id": "delete",
    "provider_connections.user_id": "delete", "provider_oauth_states.user_id": "delete",
    "push_subscriptions.user_id": "delete", "race_events.user_id": "delete",
    "race_plans.user_id": "delete", "race_results.user_id": "delete",
    "recovery_scores.user_id": "delete", "running_shoes.user_id": "delete",
    "social_comments.author_id": "delete", "social_follows.follower_id": "delete",
    "social_follows.following_id": "delete", "social_kudos.user_id": "delete",
    "supplement_logs.user_id": "delete", "web_handoffs.user_id": "delete",
    "weekly_plan_snapshots.user_id": "delete", "weight_logs.user_id": "delete",
    "wellness_logs.user_id": "delete", "workout_logs.user_id": "delete",
    # -- el usuario como atleta: lo que un coach le asigno/anoto sobre el, se borra
    "assigned_workouts.athlete_id": "delete", "athlete_notes.athlete_id": "delete",
    "coach_athletes.athlete_id": "delete", "group_members.athlete_id": "delete",
    "performance_benchmarks.athlete_id": "delete", "plan_sessions.athlete_id": "delete",
    "prescription_feedbacks.athlete_id": "delete", "training_phases.athlete_id": "delete",
    "training_plans.athlete_id": "delete", "workout_prescriptions.athlete_id": "delete",
    # -- el usuario como coach: su biblioteca y su estructura se borran
    "coach_athletes.coach_id": "delete", "groups.coach_id": "delete",
    "plan_templates.coach_id": "delete", "week_templates.coach_id": "delete",
    "workout_templates.coach_id": "delete",
    "performance_benchmarks.coach_id": "null",
    # -- terceros: se desvincula
    "community_posts.flagged_by": "null", "community_notifications.actor_id": "null",
    # -- auditoria: se conserva sin ip/agente/detalle
    "audit_logs.user_id": "scrub",
    # -- pagos (obligacion tributaria): se conservan ligados a la cuenta anonimizada
    "entitlements.user_id": "keep", "flow_subscriptions.user_id": "keep",
    # -- contenido que el coach/creador hizo para otros: sin datos personales una vez
    #    anonimizada la cuenta, y los demas usuarios siguen necesitandolo
    "athlete_notes.coach_id": "keep", "community_groups.owner_id": "keep",
    "challenges.creator_id": "keep", "macrocycles.coach_id": "keep",
    "training_phases.coach_id": "keep", "training_plans.coach_id": "keep",
    "workout_prescriptions.coach_id": "keep",
}

# Tablas sin FK declarada que tambien guardan el id del usuario.
NO_FK_DELETE = [("garmin_push_payloads", "user_id")]
NO_FK_KEEP = [("flow_payment_events", "user_id")]   # registro de pago, solo ids


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def user_ref(user_id: str) -> str:
    return hashlib.sha256(("labx-del:" + user_id).encode()).hexdigest()[:16]


def fk_user_columns() -> list[tuple[str, str]]:
    out = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == "users":
                out.append((table.name, fk.parent.name))
    return out


def unmapped_columns() -> list[str]:
    return [f"{t}.{c}" for t, c in fk_user_columns() if f"{t}.{c}" not in POLICY]


# ── borrado recursivo ─────────────────────────────────────────────

def _delete_where(db: Session, table, cond, counts: dict, depth: int = 0) -> None:
    """Borra las filas de `table` que cumplen `cond`, primero lo que depende de ellas:
    hijos con FK NOT NULL se borran; hijos con FK nullable se desvinculan."""
    if depth > 8:
        return
    pk = list(table.primary_key.columns)
    if len(pk) == 1:
        pk_col = pk[0]
        for child in Base.metadata.sorted_tables:
            for fk in child.foreign_keys:
                if fk.column is not pk_col or fk.column.table.name == "users":
                    continue
                sub = select(pk_col).where(cond)
                if child is table:
                    if fk.parent.nullable:
                        db.execute(update(child).where(fk.parent.in_(sub)).values({fk.parent.name: None}))
                    continue
                if fk.parent.nullable:
                    db.execute(update(child).where(fk.parent.in_(sub)).values({fk.parent.name: None}))
                else:
                    _delete_where(db, child, fk.parent.in_(sub), counts, depth + 1)
    n = db.execute(delete(table).where(cond)).rowcount or 0
    if n:
        counts[table.name] = counts.get(table.name, 0) + n


def _table(name: str):
    return Base.metadata.tables[name]


# ── fase 1: solicitud (inmediata) ─────────────────────────────────

def _strava_deauthorize(access_token: str) -> None:
    import httpx
    httpx.post("https://www.strava.com/oauth/deauthorize",
               data={"access_token": access_token}, timeout=8)


def _revoke_integrations(db: Session, user: User) -> list[str]:
    """Quita todos los tokens de integraciones. Devuelve que se revoco (para el resumen)."""
    done = []
    uid = user.id
    # Strava: revocar en el servidor del proveedor (best-effort) y limpiar
    if user.strava_access_token:
        try:
            from .routes.strava_routes import _read_strava_access
            raw = _read_strava_access(user)
            if raw:
                _strava_deauthorize(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Strava deauthorize fallo en borrado de cuenta: %s", type(exc).__name__)
        done.append("strava")
    user.strava_access_token = None
    user.strava_refresh_token = None
    user.strava_athlete_id = None
    user.strava_token_expires_at = None
    # intervals.icu
    if user.intervals_access_token:
        done.append("intervals")
    user.intervals_access_token = None
    user.intervals_athlete_id = None
    user.intervals_scope = None
    user.intervals_connected_at = None
    user.intervals_invalid_at = None
    user.intervals_last_sync_at = None
    # Garmin (credenciales legacy y OAuth oficial), Polar, Wahoo
    if user.garmin_email or user.garmin_password:
        done.append("garmin_legacy")
    user.garmin_email = None
    user.garmin_password = None
    for tname, label in (("garmin_oauth_tokens", "garmin"), ("provider_connections", "polar_wahoo")):
        t = _table(tname)
        if db.execute(delete(t).where(t.c.user_id == uid)).rowcount:
            done.append(label)
    for tname in ("garmin_oauth_states", "provider_oauth_states", "web_handoffs", "push_subscriptions"):
        t = _table(tname)
        db.execute(delete(t).where(t.c.user_id == uid))
    return done


def _cancel_billing(user: User, db: Session) -> list[str]:
    """Corta cobros futuros (best-effort: si el proveedor falla, la cuenta ya esta inactiva
    y el plan vence solo; se registra el tipo de error)."""
    done = []
    try:
        from .flow_client import flow_enabled, get_client
        from .models import FlowSubscription
        subs = db.query(FlowSubscription).filter(
            FlowSubscription.user_id == user.id, FlowSubscription.status.in_(("activa", "pendiente"))).all()
        for s in subs:
            if s.flow_subscription_id and flow_enabled():
                try:
                    get_client().cancel_subscription(s.flow_subscription_id, at_period_end=False)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Flow cancel fallo en borrado: %s", type(exc).__name__)
            s.status = "cancelada"
            s.cancel_at_period_end = True
            s.updated_at = _now()
            done.append("flow")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cancelar Flow fallo: %s", type(exc).__name__)
    if user.stripe_subscription_id and os.getenv("STRIPE_SECRET_KEY"):
        try:
            import stripe
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
            stripe.Subscription.cancel(user.stripe_subscription_id)
            done.append("stripe")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stripe cancel fallo en borrado: %s", type(exc).__name__)
    return done


def pending_request(db: Session, user_id: str) -> AccountDeletionRequest | None:
    return (db.query(AccountDeletionRequest)
            .filter(AccountDeletionRequest.user_id == user_id,
                    AccountDeletionRequest.status.in_(("pendiente", "error"))).first())


def request_deletion(db: Session, user: User) -> AccountDeletionRequest:
    """Desactiva la cuenta ya y agenda la purga. Idempotente."""
    existing = pending_request(db, user.id)
    if existing:
        return existing
    now = _now()
    revoked = _revoke_integrations(db, user)
    revoked += _cancel_billing(user, db)
    user.activo = False
    user.token_gen = (user.token_gen or 1) + 1      # invalida todas las sesiones
    user.notif_email_weekly = False
    user.notif_email_workout = False
    user.notif_push_wellness = False
    # Cierra la relacion coach<->atleta (en ambos sentidos)
    ca = _table("coach_athletes")
    db.execute(update(ca).where((ca.c.athlete_id == user.id) | (ca.c.coach_id == user.id))
               .values(activo=False, status="ended"))
    req = AccountDeletionRequest(
        user_ref=user_ref(user.id), user_id=user.id, status="pendiente",
        requested_at=now, purge_after=now + timedelta(days=GRACE_DAYS),
        deadline_at=now + timedelta(days=MAX_DAYS),
        summary_json=json.dumps({"revoked": sorted(set(revoked))}),
    )
    db.add(req)
    db.commit()
    return req


# ── fase 2: purga ─────────────────────────────────────────────────

def _purge_files(db: Session, user: User) -> int:
    from .storage import storage
    n = 0
    keys = []
    if user.avatar_photo_path:
        keys.append(user.avatar_photo_path)
    ga = _table("garmin_activities")
    keys += [r[0] for r in db.execute(select(ga.c.photo_path).where(
        ga.c.user_id == user.id, ga.c.photo_path.isnot(None)))]
    ap = _table("activity_photos")
    keys += [r[0] for r in db.execute(select(ap.c.storage_key).where(ap.c.user_id == user.id))]
    for k in keys:
        try:
            storage.delete(k)
            n += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo borrar archivo en purga: %s", type(exc).__name__)
    for prefix in ("blood_lab_files", "blood_lab_pending"):
        try:
            n += storage.delete_prefix(f"{prefix}/{user.id}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete_prefix fallo en purga: %s", type(exc).__name__)
    return n


_USER_SCRUB = dict(
    nombre="Cuenta eliminada", password_hash="!", activo=False, pending_invite=False,
    plan_nivel="basico", last_login_at=None, garmin_email=None, garmin_password=None,
    race_goal_name=None, race_goal_date=None, race_goal_dist=None, ftp=None, ftp_indoor=None,
    weight_kg=None, height_cm=None, age=None, sexo=None, vo2max=None, fcmax=None, css=None,
    run_pace=None, totp_secret=None, totp_enabled=False, totp_backup_hash=None,
    last_device_hash=None, strava_access_token=None, strava_refresh_token=None,
    strava_athlete_id=None, strava_token_expires_at=None, intervals_access_token=None,
    intervals_athlete_id=None, intervals_connected_at=None, intervals_scope=None,
    intervals_invalid_at=None, intervals_last_sync_at=None,
    stripe_customer_id=None, stripe_subscription_id=None, trial_end_at=None, sports=None,
    onboarding_completed_at=None, gdpr_consent_at=None, gdpr_consent_ip=None,
    country_code=None, community_share_prefs=None, avatar_photo_path=None,
    notif_email_weekly=False, notif_email_workout=False, notif_push_wellness=False,
)


def purge_user(db: Session, req: AccountDeletionRequest) -> dict:
    """Aplica POLICY al usuario de la solicitud y deja la cuenta anonimizada."""
    uid = req.user_id
    user = db.get(User, uid) if uid else None
    counts: dict[str, int] = {}
    if user is not None:
        files = _purge_files(db, user)
        # auditoria: se conserva sin ip/agente/detalle
        al = _table("audit_logs")
        db.execute(update(al).where(al.c.user_id == uid).values(ip=None, user_agent=None, detail=None, resource=None))
        for key, action in POLICY.items():
            tname, col = key.split(".")
            t = _table(tname)
            if action == "delete":
                _delete_where(db, t, t.c[col] == uid, counts)
            elif action == "null":
                n = db.execute(update(t).where(t.c[col] == uid).values({col: None})).rowcount or 0
                if n:
                    counts[f"{tname}.{col}->null"] = n
        for tname, col in NO_FK_DELETE:
            t = _table(tname)
            n = db.execute(delete(t).where(t.c[col] == uid)).rowcount or 0
            if n:
                counts[tname] = n
        # pagos: se conservan los ids, se vacian los identificadores del cliente
        fs = _table("flow_subscriptions")
        db.execute(update(fs).where(fs.c.user_id == uid).values(flow_customer_id=None, register_token=None))
        # la cuenta queda como tumba anonima (la fila se necesita por los pagos conservados)
        ref = user_ref(uid)
        for k, v in _USER_SCRUB.items():
            setattr(user, k, v)
        user.email = f"deleted+{ref}@deleted.invalid"
        user.token_gen = (user.token_gen or 1) + 1
        counts["_archivos"] = files
    summary = json.loads(req.summary_json or "{}")
    summary["purged"] = counts
    req.summary_json = json.dumps(summary)
    req.status = "completada"
    req.completed_at = _now()
    req.user_id = None              # el registro ya no apunta a nadie
    req.last_error = None
    db.commit()
    return counts


def process_due_requests(db: Session, now: datetime | None = None) -> dict:
    """Job: purga las solicitudes cuyo periodo de gracia vencio. Reintenta las fallidas."""
    now = now or _now()
    ok = failed = 0
    rows = (db.query(AccountDeletionRequest)
            .filter(AccountDeletionRequest.status.in_(("pendiente", "error")),
                    AccountDeletionRequest.purge_after <= now,
                    AccountDeletionRequest.attempts < MAX_ATTEMPTS).all())
    for req in rows:
        rid = req.id
        try:
            req.attempts = (req.attempts or 0) + 1
            purge_user(db, req)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            failed += 1
            logger.error("Purga de cuenta fallo (req=%s): %s", rid, type(exc).__name__)
            r2 = db.get(AccountDeletionRequest, rid)
            if r2:
                r2.attempts = (r2.attempts or 0) + 1
                r2.status = "error"
                r2.last_error = type(exc).__name__[:200]
                db.commit()
    return {"purged": ok, "failed": failed}
