"""
Strava OAuth 2.0 + actividad import — D-06

Flujo:
  1. GET /api/strava/connect  → redirige a Strava authorization URL
  2. GET /api/strava/callback  → Strava redirige aquí con ?code=… → intercambia por tokens → guarda
  3. GET /api/strava/status    → ¿está conectado? último sync?
  4. POST /api/strava/sync     → importa actividades recientes y las guarda como GarminActivity
  5. DELETE /api/strava/disconnect → revoca tokens y desconecta

Env vars requeridas:
  STRAVA_CLIENT_ID
  STRAVA_CLIENT_SECRET
  STRAVA_REDIRECT_URI  (ej. https://labx.app/api/strava/callback)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import User, GarminActivity
from ..services.gear_service import assign_gear

logger = logging.getLogger("labx.strava")
router = APIRouter(prefix="/strava", tags=["strava"])

_CLIENT_ID     = os.getenv("STRAVA_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
_REDIRECT_URI  = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/api/strava/callback")
_STRAVA_AUTH   = "https://www.strava.com/oauth/authorize"
_STRAVA_TOKEN  = "https://www.strava.com/oauth/token"
_STRAVA_API    = "https://www.strava.com/api/v3"

# ── Sport mapping Strava → LabX ───────────────────────────────────────────────
_SPORT_MAP = {
    "Run": "run", "TrailRun": "run", "VirtualRun": "run",
    "Ride": "bike", "MountainBikeRide": "bike", "VirtualRide": "bike", "GravelRide": "bike",
    "Swim": "swim", "OpenWaterSwim": "swim",
    "WeightTraining": "gym", "Workout": "gym", "Crossfit": "gym",
    "Walk": "walk", "Hike": "walk",
    "Yoga": "gym", "Pilates": "gym",
}


def _strava_available() -> bool:
    return bool(_CLIENT_ID and _CLIENT_SECRET)


def _require_strava():
    if not _strava_available():
        raise HTTPException(503, "Strava no configurado — configura STRAVA_CLIENT_ID y STRAVA_CLIENT_SECRET")


# ── Helpers para guardar/leer tokens cifrados ────────────────────────────────
# C-18: Tokens Strava cifrados con Fernet antes de guardar en DB

from ..crypto import encrypt as _enc, decrypt as _dec, is_encrypted


def _save_strava_tokens(user: User, tokens: dict, db: Session):
    """C-18: Guarda tokens Strava CIFRADOS en DB con Fernet."""
    raw_access  = tokens.get("access_token")
    raw_refresh = tokens.get("refresh_token")
    user.strava_access_token   = _enc(raw_access)  if raw_access  else None
    user.strava_refresh_token  = _enc(raw_refresh) if raw_refresh else None
    user.strava_athlete_id     = str(tokens.get("athlete", {}).get("id", "") or tokens.get("strava_athlete_id", ""))
    exp = tokens.get("expires_at")
    if exp:
        user.strava_token_expires_at = datetime.utcfromtimestamp(int(exp))
    db.commit()


def _read_strava_access(user: User) -> str | None:
    """Descifra el access token almacenado (backward compat: si no está cifrado, devuelve tal cual)."""
    if not user.strava_access_token:
        return None
    if is_encrypted(user.strava_access_token):
        return _dec(user.strava_access_token)
    return user.strava_access_token  # token plaintext heredado


def _read_strava_refresh(user: User) -> str | None:
    if not user.strava_refresh_token:
        return None
    if is_encrypted(user.strava_refresh_token):
        return _dec(user.strava_refresh_token)
    return user.strava_refresh_token


async def _get_valid_access_token(user: User, db: Session) -> str:
    """Retorna un access token válido (descifrado), refrescando si está expirado."""
    if not user.strava_access_token:
        raise HTTPException(401, "Cuenta Strava no conectada")

    # Refrescar si expira en menos de 5 minutos
    exp = user.strava_token_expires_at
    if exp and datetime.now(timezone.utc).replace(tzinfo=None) >= (exp - timedelta(minutes=5)):
        refresh_token = _read_strava_refresh(user)
        if not refresh_token:
            raise HTTPException(401, "Token de refresco Strava inválido — reconecta tu cuenta")
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(_STRAVA_TOKEN, data={
                "client_id":     _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
            })
            if r.status_code != 200:
                raise HTTPException(502, "Error al refrescar token Strava")
            tokens = r.json()
            _save_strava_tokens(user, tokens, db)
            return tokens["access_token"]  # token fresco, ya cifrado en DB

    return _read_strava_access(user)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/connect")
def strava_connect(
    request: Request,
    me: User = Depends(get_current_user),
):
    """Inicia el flujo OAuth: redirige al usuario a Strava."""
    _require_strava()
    # Guardar user_id en state para recuperarlo en callback
    import base64, json
    state = base64.urlsafe_b64encode(json.dumps({"uid": me.id}).encode()).decode()
    url = (
        f"{_STRAVA_AUTH}"
        f"?client_id={_CLIENT_ID}"
        f"&redirect_uri={_REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope=read,activity:read_all"
        f"&state={state}"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def strava_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """Strava redirige aquí tras autorizar. Intercambia code por tokens."""
    _require_strava()

    if error or not code:
        return RedirectResponse("/athlete_profile.html?strava=denied")

    # Recuperar user_id del state — BP-15: padding correcto para base64 variable
    import base64, json
    try:
        # Padding dinámico: añadir solo los = necesarios
        padded = state + "=" * (-len(state) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        user_id = payload["uid"]
    except Exception:
        raise HTTPException(400, "State OAuth inválido")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    # Intercambiar code por tokens
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(_STRAVA_TOKEN, data={
            "client_id":     _CLIENT_ID,
            "client_secret": _CLIENT_SECRET,
            "code":          code,
            "grant_type":    "authorization_code",
        })
        if r.status_code != 200:
            logger.error("Strava token exchange failed: %s", r.text)
            return RedirectResponse("/athlete_profile.html?strava=error")
        tokens = r.json()

    _save_strava_tokens(user, tokens, db)
    logger.info("Strava conectado para user=%s athlete_id=%s", user_id, user.strava_athlete_id)

    return RedirectResponse("/athlete_profile.html?strava=connected")


@router.get("/status")
def strava_status(
    me: User = Depends(get_current_user),
):
    """Estado de la conexión Strava del usuario."""
    connected = bool(me.strava_access_token)
    return {
        "available":    _strava_available(),
        "connected":    connected,
        "athlete_id":   me.strava_athlete_id if connected else None,
        "token_expires": me.strava_token_expires_at.isoformat() if (connected and me.strava_token_expires_at) else None,
    }


@router.post("/sync")
async def strava_sync(
    days: int = 7,
    me: User  = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Importa actividades de Strava de los últimos `days` días.
    Crea/actualiza filas en garmin_activities (tabla compartida con Garmin).
    """
    _require_strava()
    if days < 1 or days > 90:
        raise HTTPException(400, "days debe ser entre 1 y 90")
    return await _sync_strava_activities(me, db, days)


async def _sync_strava_activities(me: User, db: Session, days: int = 7) -> dict:
    """
    Núcleo del sync — separado del endpoint HTTP para que también lo pueda
    llamar el job en background (scheduler): una vez que el usuario conecta
    su cuenta Strava, la sincronización queda automática (cada 2h, igual que
    Garmin) — no tiene que volver a apretar "Sincronizar" nunca más.
    """
    token = await _get_valid_access_token(me, db)

    after_ts = int((datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).timestamp())
    imported  = 0
    updated   = 0
    duplicates = 0  # ya existían como actividad Garmin — solo se les agregaron fotos
    errors    = 0
    page      = 1

    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            r = await client.get(
                f"{_STRAVA_API}/athlete/activities",
                headers={"Authorization": f"Bearer {token}"},
                params={"after": after_ts, "per_page": 50, "page": page},
            )
            if r.status_code == 429:
                raise HTTPException(429, "Rate limit Strava — espera 15 minutos")
            if r.status_code != 200:
                raise HTTPException(502, f"Error Strava API: {r.status_code}")

            acts = r.json()
            if not acts:
                break

            for a in acts:
                try:
                    status, target_activity_id = _upsert_strava_activity(a, me, db)
                    if status == "imported":
                        imported += 1
                    elif status == "updated":
                        updated += 1
                    elif status == "duplicate":
                        duplicates += 1

                    # Fotos: solo se consultan para actividades nuevas o
                    # recién detectadas como duplicado de Garmin — no en
                    # cada re-sync de una fila ya procesada, para no gastar
                    # cupo de la API de Strava innecesariamente.
                    if status in ("imported", "duplicate") and a.get("total_photo_count", 0) > 0:
                        photos = await _fetch_strava_photos(a["id"], token, client)
                        if photos:
                            target = db.query(GarminActivity).filter(
                                GarminActivity.activity_id == target_activity_id,
                                GarminActivity.user_id == me.id,
                            ).first()
                            if target:
                                target.strava_photos_json = json.dumps(photos)
                except Exception as exc:
                    logger.warning("Error importando actividad strava id=%s: %s", a.get("id"), exc)
                    errors += 1

            if len(acts) < 50:
                break
            page += 1

    db.commit()
    return {
        "ok":         True,
        "imported":   imported,
        "updated":    updated,
        "duplicates": duplicates,
        "errors":     errors,
        "days":       days,
    }


async def _fetch_strava_photos(strava_activity_id: int, token: str, client: httpx.AsyncClient) -> list[str]:
    """Fotos de una actividad Strava (ej. capturas de Zwift) — la URL de mayor tamaño disponible de cada una."""
    try:
        r = await client.get(
            f"{_STRAVA_API}/activities/{strava_activity_id}/photos",
            headers={"Authorization": f"Bearer {token}"},
            params={"size": 800},
        )
        if r.status_code != 200:
            return []
        urls = []
        for p in r.json():
            sizes = (p.get("urls") or {})
            if sizes:
                urls.append(list(sizes.values())[-1])  # el tamaño más grande queda al final
        return urls
    except Exception as exc:
        logger.warning("Error trayendo fotos Strava activity=%s: %s", strava_activity_id, exc)
        return []


def _upsert_strava_activity(a: dict[str, Any], user: User, db: Session) -> tuple[str, str]:
    """
    Convierte una actividad Strava y la inserta/actualiza en garmin_activities.
    Retorna (status, activity_id_afectado):
      - "updated":   ya existía esta misma fila de Strava, se refrescó
      - "duplicate": el mismo entrenamiento real ya existe como actividad
                     de OTRO origen (típicamente Garmin — ej. Zwift subió
                     a ambos) — no se crea una fila nueva, se devuelve el
                     activity_id de Garmin para adjuntarle las fotos ahí
      - "imported":  actividad nueva, no existía en ningún origen
    """
    from ..garmin_pull_service import _extract_tss, _parse_mmss

    user_id   = user.id
    act_id    = f"strava_{a['id']}"
    sport_raw = a.get("sport_type") or a.get("type") or "Run"
    sport     = _SPORT_MAP.get(sport_raw, "run")

    # Fecha
    start_str = a.get("start_date_local", "")[:10]  # YYYY-MM-DD

    # Duración (segundos → minutos)
    dur_s   = a.get("moving_time") or a.get("elapsed_time") or 0
    dur_min = round(dur_s / 60, 1)

    # Distancia (metros → km)
    dist_m  = a.get("distance") or 0
    dist_km = round(dist_m / 1000, 2)

    # Velocidad / ritmo
    avg_spd = a.get("average_speed") or 0   # m/s
    pace_str = None
    if sport in ("run", "walk") and avg_spd > 0.1:
        pace_min_km = 1000 / avg_spd / 60
        m = int(pace_min_km)
        s = int((pace_min_km - m) * 60)
        pace_str = f"{m}:{s:02d} /km"

    # Elevación
    elev = a.get("total_elevation_gain") or 0

    # TSS real — misma fórmula/prioridad que las actividades nativas de
    # Garmin (potencia/ritmo real vs. fallback por %FCmax personalizado),
    # NO la fórmula propia que había acá antes (dur_min×0.7/0.5, sin FC,
    # sin potencia, sin ritmo — un cuarto cálculo de TSS distinto en toda
    # la plataforma). Se arma un dict compatible con _extract_tss usando
    # los campos que Strava sí expone.
    fake_act = {
        "duration":   dur_s,
        "distance":   dist_m,
        "averageHR":  a.get("average_heartrate"),
        "avgPower":   a.get("average_watts"),
        "activityType": {"typeKey": sport_raw},
    }
    tss = _extract_tss(
        fake_act, user.ftp or 250, user.fcmax,
        _parse_mmss(user.run_pace), _parse_mmss(user.css),
    )

    # Ícono/color por deporte
    _icons  = {"run": "🏃", "bike": "🚴", "swim": "🏊", "gym": "💪", "walk": "🚶"}
    _colors = {"run": "#FF6535", "bike": "#0EA5E9", "swim": "#22D3EE", "gym": "#A855F7", "walk": "#10B981"}

    existing = db.query(GarminActivity).filter(
        GarminActivity.activity_id == act_id,
        GarminActivity.user_id     == user_id,
    ).first()

    if existing:
        # Actualizar si cambió
        existing.name       = a.get("name", "Strava activity")
        existing.dur_min    = dur_min
        existing.dist_km    = dist_km
        existing.avg_hr     = a.get("average_heartrate")
        existing.avg_power  = a.get("average_watts")
        existing.pace_str   = pace_str
        existing.calories   = a.get("calories") or a.get("kilojoules")
        existing.tss        = tss
        try:
            assign_gear(db, existing)
        except Exception as _gear_err:
            logger.debug("Gear assign fallo (no bloqueante) activity=%s: %s", existing.activity_id, _gear_err)
        return "updated", existing.activity_id

    # Deduplicar contra una actividad de OTRO origen que ya represente este
    # mismo entrenamiento real (típico: Zwift sube la misma sesión tanto a
    # Garmin como a Strava). Dos criterios, CUALQUIERA alcanza:
    #  1. Duración similar (tolerancia 5 min o 10%) — bici/carrera, donde
    #     Garmin y Strava miden el tiempo básicamente igual.
    #  2. Distancia casi idéntica (tolerancia 3%) — necesario para NATACIÓN,
    #     donde la duración puede diferir hasta 20 min entre plataformas
    #     según si cuentan o no el descanso en la pared (bug real
    #     encontrado auditando una cuenta real: 16 pares duplicados en un
    #     mes, todos con distancia idéntica pero duración muy distinta,
    #     invisibles para el criterio de duración solo).
    tol_min = max(5.0, dur_min * 0.10)
    candidates = db.query(GarminActivity).filter(
        GarminActivity.user_id == user_id,
        GarminActivity.date_iso == start_str,
        GarminActivity.sport == sport,
        GarminActivity.activity_id.notlike("strava_%"),
    ).all()
    dup = None
    for c in candidates:
        dur_match = c.dur_min is not None and abs(c.dur_min - dur_min) <= tol_min
        dist_match = (
            dist_km > 0 and c.dist_km is not None and c.dist_km > 0
            and abs(c.dist_km - dist_km) / max(c.dist_km, dist_km) <= 0.03
        )
        if dur_match or dist_match:
            dup = c
            break
    if dup:
        return "duplicate", dup.activity_id

    row = GarminActivity(
        activity_id = act_id,
        user_id     = user_id,
        sport       = sport,
        icon        = _icons.get(sport, "🏃"),
        color       = _colors.get(sport, "#FF6535"),
        name        = a.get("name", "Strava activity"),
        date_iso    = start_str,
        date_label  = start_str,
        dur_min     = dur_min,
        dist_km     = dist_km,
        avg_hr      = a.get("average_heartrate"),
        avg_power   = a.get("average_watts"),
        pace_str    = pace_str,
        calories    = a.get("calories") or a.get("kilojoules"),
        tss         = tss,
    )
    db.add(row)
    db.flush()
    try:
        assign_gear(db, row)
    except Exception as _gear_err:
        logger.debug("Gear assign fallo (no bloqueante) activity=%s: %s", row.activity_id, _gear_err)
    return "imported", row.activity_id


@router.delete("/disconnect")
async def strava_disconnect(
    me: User    = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """C-19: Revoca tokens Strava, desconecta la cuenta y notifica al atleta por email."""
    if not me.strava_access_token:
        raise HTTPException(400, "Strava no está conectado")

    # Revocar en Strava usando token descifrado
    raw_token = _read_strava_access(me)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://www.strava.com/oauth/deauthorize",
                data={"access_token": raw_token},
            )
    except Exception as exc:
        logger.warning("No se pudo revocar token Strava en servidor: %s", exc)

    athlete_id = me.strava_athlete_id

    # Limpiar en DB
    me.strava_access_token    = None
    me.strava_refresh_token   = None
    me.strava_athlete_id      = None
    me.strava_token_expires_at = None
    db.commit()

    # C-19: Notificar al atleta por email (best-effort)
    try:
        from ..mailer import send_email
        html = f"""
        <div style="font-family:Inter,sans-serif;background:#04080F;color:#F0F9FF;padding:40px 24px;max-width:560px;margin:0 auto;border-radius:16px">
          <h2 style="color:#FC4C02">Strava desconectado</h2>
          <p style="color:#7FB3CC;margin:16px 0">
            Hola <strong>{me.nombre}</strong>, tu cuenta de Strava (ID: {athlete_id}) fue
            desconectada de LabX correctamente. Tus actividades importadas se mantienen en tu perfil.
          </p>
          <p style="color:#3D6880;font-size:.8rem">
            Si no realizaste esta acción, contacta soporte de inmediato en
            <a href="mailto:partnerships@labxperformanceapp.com" style="color:#0EA5E9">partnerships@labxperformanceapp.com</a>.
          </p>
        </div>
        """
        send_email(me.email, "LabX — Strava desconectado", html)
    except Exception as exc:
        logger.warning("No se pudo enviar email de desconexión Strava user=%s: %s", me.id, exc)

    logger.info("Strava desconectado user_id=%s athlete_id=%s", me.id, athlete_id)
    return {"ok": True, "message": "Strava desconectado correctamente"}
