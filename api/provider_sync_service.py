"""
Sync de actividades Polar/Wahoo (Sprint 56 paso 2). SOLO actividades: salud
diaria, sueno y splits de estos providers no existen (NotImplementedError a
proposito) y aqui no se simulan.

Escritura: replica _upsert_strava_activity (strava_routes.py) sobre
garmin_activities: dedupe por (user_id, activity_id), refresco de la fila
propia si ya existe, y descarte de actividades que ya existen con OTRO origen
(mismo dia/deporte y duracion o distancia casi iguales). No hay columna
`provider` en garmin_activities: el origen lo da el prefijo del activity_id
("polar_" / "wahoo_"), igual que "strava_".
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import provider_oauth
from .activity_dedupe import mark_new_activity
from .models import GarminActivity, User
from .providers import registry

logger = logging.getLogger("labx.provider_sync")

WAHOO_MAX_PAGES = 5
WAHOO_PER_PAGE = 100

_ICONS = {"run": "\U0001F3C3", "bike": "\U0001F6B4", "swim": "\U0001F3CA", "gym": "\U0001F4AA"}
_COLORS = {"run": "#FF6535", "bike": "#0EA5E9", "swim": "#22D3EE", "gym": "#A855F7"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _error_type(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "token_rejected"
    if status:
        return f"http_{status}"
    return type(exc).__name__


def _record_state(db: Session, conn, ok: bool, saved: int | None = None, error: str | None = None) -> None:
    try:
        conn.last_sync_at = _now()
        conn.last_sync_status = "ok" if ok else "error"
        conn.last_sync_error = None if ok else error
        conn.last_sync_saved = saved
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("no se pudo registrar estado de sync")


def _raw_start_date(raw: dict) -> str:
    return str(raw.get("starts") or "")[:10]


async def _fetch_wahoo(provider, token: str, cutoff: str) -> tuple[list[dict], int]:
    """-> (crudas dentro de ventana, cuantas se descartaron por viejas)."""
    kept: list[dict] = []
    dropped = 0
    for page in range(1, WAHOO_MAX_PAGES + 1):
        batch = await provider.list_activities(client=token, since=cutoff, page=page, per_page=WAHOO_PER_PAGE)
        if not batch:
            break
        fresh = [r for r in batch if not (len(_raw_start_date(r)) == 10 and _raw_start_date(r) < cutoff)]
        dropped += len(batch) - len(fresh)
        kept.extend(fresh)
        if not fresh:  # toda la pagina es anterior al cutoff
            break
    return kept, dropped


def _normalize_kwargs(provider_name: str, user: User | None) -> dict:
    # Misma fuente que el flujo Strava (_upsert_strava_activity): campos del User.
    # El normalizador de Polar no acepta ftp (no hay potencia en su payload).
    fcmax = user.fcmax if user else None
    if provider_name == "wahoo":
        return {"ftp": (user.ftp if user else None) or 250, "fcmax": fcmax}
    return {"fcmax": fcmax}


def _upsert(db: Session, user_id: str, prefix: str, d: dict) -> str:
    """-> 'saved' | 'updated' | 'duplicate'. Lanza ValueError si falta la fecha."""
    from .services.gear_service import assign_gear

    act_id = d["activity_id"]
    date_iso = d.get("date_iso") or ""
    if not date_iso:
        raise ValueError("actividad sin fecha")
    sport = d.get("sport") or "other"
    dur_min = d.get("dur_min") or 0
    dist_km = d.get("dist_km") or 0.0

    existing = db.query(GarminActivity).filter(
        GarminActivity.activity_id == act_id, GarminActivity.user_id == user_id).first()
    if existing:
        existing.name = d.get("name")
        existing.dur_min = dur_min
        existing.dist_km = dist_km
        existing.avg_hr = d.get("avg_hr")
        existing.avg_power = d.get("avg_power")
        existing.calories = d.get("calories")
        existing.elev_m = d.get("elev_m")
        existing.tss = d.get("tss")
        try:
            assign_gear(db, existing)
        except Exception as exc:
            logger.debug("gear assign fallo (no bloqueante): %s", exc)
        return "updated"

    tol_min = max(5.0, dur_min * 0.10)
    candidates = db.query(GarminActivity).filter(
        GarminActivity.user_id == user_id,
        GarminActivity.date_iso == date_iso,
        GarminActivity.sport == sport,
        GarminActivity.activity_id.notlike(f"{prefix}%"),
    ).all()
    for c in candidates:
        dur_match = c.dur_min is not None and abs(c.dur_min - dur_min) <= tol_min
        dist_match = (dist_km > 0 and c.dist_km is not None and c.dist_km > 0
                      and abs(c.dist_km - dist_km) / max(c.dist_km, dist_km) <= 0.03)
        if dur_match or dist_match:
            return "duplicate"

    extra = {}
    if sport in _ICONS:
        extra = {"icon": _ICONS[sport], "color": _COLORS[sport]}
    row = GarminActivity(
        activity_id=act_id, user_id=user_id, sport=sport, name=d.get("name"),
        date_iso=date_iso, date_label=date_iso, dur_min=dur_min, dist_km=dist_km,
        avg_hr=d.get("avg_hr"), avg_power=d.get("avg_power"), calories=d.get("calories"),
        elev_m=d.get("elev_m"), tss=d.get("tss"), **extra)
    db.add(row)
    db.flush()
    mark_new_activity(db, row)  # PILA 374
    try:
        assign_gear(db, row)
    except Exception as exc:
        logger.debug("gear assign fallo (no bloqueante): %s", exc)
    return "saved"


async def sync_provider_user(db: Session, user_id: str, provider_name: str, days: int = 30) -> dict:
    conn = provider_oauth.get_connection(db, user_id, provider_name)
    if not conn:
        return {"ok": False, "error": "not_connected", "provider": provider_name,
                "fetched": 0, "saved": 0, "skipped_dup": 0}

    fail = {"ok": False, "provider": provider_name, "fetched": 0, "saved": 0, "skipped_dup": 0}
    try:
        token = await provider_oauth.get_valid_access_token(db, user_id, provider_name)
    except Exception as exc:
        err = _error_type(exc)
        _record_state(db, conn, False, error=err)
        return {**fail, "error": err}
    if not token:
        _record_state(db, conn, False, error="token_invalid")
        return {**fail, "error": "token_invalid"}

    cutoff = (_now() - timedelta(days=days)).strftime("%Y-%m-%d")
    fetched = 0
    try:
        provider = registry.get_provider(provider_name, db)
        if provider_name == "wahoo":
            raws, dropped = await _fetch_wahoo(provider, token, cutoff)
            fetched = len(raws) + dropped
        else:
            # Polar entrega sus ejercicios pendientes: `days` no aplica.
            raws = await provider.list_activities(client=token, since=cutoff)
            dropped = 0
            fetched = len(raws)
    except Exception as exc:
        db.rollback()
        err = _error_type(exc)
        logger.warning("%s list_activities fallo user=%s: %s", provider_name, user_id, err)
        conn = provider_oauth.get_connection(db, user_id, provider_name) or conn
        _record_state(db, conn, False, error=err)
        return {**fail, "error": err, "fetched": fetched}

    user = db.query(User).filter(User.id == user_id).first()
    kwargs = _normalize_kwargs(provider_name, user)
    prefix = f"{provider_name}_"
    saved = skipped = updated = errors = 0
    new_raw_ids: list[str] = []
    for raw in raws:
        try:
            detail = provider.get_activity_detail(raw, **kwargs)
            status = _upsert(db, user_id, prefix, detail)
        except Exception as exc:
            db.rollback()
            logger.warning("%s actividad omitida user=%s: %s", provider_name, user_id, type(exc).__name__)
            errors += 1
            continue
        if status == "saved":
            saved += 1
            new_raw_ids.append(str(raw.get("id")))
        else:
            skipped += 1
            if status == "updated":
                updated += 1
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        err = _error_type(exc)
        _record_state(db, provider_oauth.get_connection(db, user_id, provider_name) or conn, False, error=err)
        return {**fail, "error": err, "fetched": fetched}

    if provider_name == "polar":
        for rid in new_raw_ids:
            try:
                await provider.download_gps(token, rid)
            except Exception as exc:  # best-effort
                logger.debug("polar gps omitido id=%s: %s", rid, type(exc).__name__)

    _record_state(db, provider_oauth.get_connection(db, user_id, provider_name) or conn, True, saved=saved)
    return {"ok": True, "provider": provider_name, "fetched": fetched, "saved": saved,
            "skipped_dup": skipped, "updated": updated, "filtered_old": dropped, "errors": errors}
