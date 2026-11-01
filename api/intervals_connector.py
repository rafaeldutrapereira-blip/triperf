"""
intervals_connector.py -- OAuth2 + envio de workouts a intervals.icu (S6).

Alcance ESTRICTO de este sprint: solo ESCRIBIR workouts en el calendario del
atleta (scope CALENDAR:WRITE). Nunca se lee actividad ni wellness desde acá.

Mecanismo de payload elegido y confirmado contra la documentacion/foro oficial
de intervals.icu durante el sprint: el texto DSL de "workout description" que
intervals.icu parsea en pasos (duracion + %FTP / %HR / pace), NO un archivo
adjunto .zwo/.mrc/.erg. Motivo: esos tres formatos de archivo solo expresan
potencia (bici) -- no hay forma de codificar un objetivo de ritmo o FC para
running en ellos, y S5 agrego bloques de running con mode pace|hr. El DSL de
texto es el unico mecanismo documentado que cubre ambos deportes con el MISMO
motor de bloques de S4/S5 (warmup/steady/intervals/ramp/freeride/cooldown).

OAuth2 (confirmado en forum.intervals.icu, hilo "intervals-icu-oauth-support"):
  - Authorize:  GET  https://intervals.icu/oauth/authorize
                ?client_id&redirect_uri&scope&state
  - Token:      POST https://intervals.icu/api/oauth/token
                (client_id, client_secret, code) -- code expira en 2 minutos
  - Los tokens de intervals.icu NO expiran y no tienen refresh_token.
  - API: Authorization: Bearer <token>; base https://intervals.icu/api/v1;
    athlete id "0" = el atleta dueño del token.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import httpx

from .crypto import encrypt as _enc, decrypt as _dec, is_encrypted

if TYPE_CHECKING:
    from .models import User

logger = logging.getLogger("labx.intervals")

CLIENT_ID     = os.getenv("INTERVALS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("INTERVALS_CLIENT_SECRET", "")
REDIRECT_URI  = os.getenv("INTERVALS_REDIRECT_URI", "http://localhost:8000/api/integrations/intervals/callback")

AUTHORIZE_URL = "https://intervals.icu/oauth/authorize"
TOKEN_URL     = "https://intervals.icu/api/oauth/token"
API_BASE      = "https://intervals.icu/api/v1"
SCOPE         = "CALENDAR:WRITE,SETTINGS:READ"  # SETTINGS:READ = lo minimo para identificar al atleta


def available() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


class IntervalsError(Exception):
    """Error de la API o de conexion -- nunca se traduce en un exito falso."""


# ── Tokens cifrados (mismo patron que Strava, ver routes/strava_routes.py) ──

def save_tokens(user: "User", access_token: str, athlete_id: str | None, db) -> None:
    user.intervals_access_token = _enc(access_token)
    user.intervals_athlete_id   = str(athlete_id) if athlete_id else None
    from datetime import datetime, timezone
    user.intervals_connected_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def read_access_token(user: "User") -> str | None:
    if not user.intervals_access_token:
        return None
    if is_encrypted(user.intervals_access_token):
        return _dec(user.intervals_access_token)
    return user.intervals_access_token  # legacy plaintext, no deberia ocurrir


def clear_tokens(user: "User", db) -> None:
    user.intervals_access_token = None
    user.intervals_athlete_id   = None
    user.intervals_connected_at = None
    db.commit()


# ── OAuth2 ────────────────────────────────────────────────────────────────

def build_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id":    CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope":        SCOPE,
        "state":        state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """POST a /api/oauth/token. Lanza IntervalsError si falla -- nunca inventa un token."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(TOKEN_URL, data={
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code":          code,
        })
        if r.status_code != 200:
            raise IntervalsError(f"intervals.icu rechazo el intercambio de token ({r.status_code})")
        return r.json()


async def fetch_athlete_id(access_token: str) -> str | None:
    """SETTINGS:READ minimo -- solo para identificar al atleta en la UI."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{API_BASE}/athlete/0",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 200:
                return str(r.json().get("id") or "") or None
    except Exception as exc:
        logger.warning("No se pudo identificar atleta intervals.icu: %s", exc)
    return None


# ── Motor de bloques -> texto DSL de intervals.icu ──────────────────────────
# Mismo motor de S5 (api/workout_delivery.py:generate_zwo_bytes para bici
# comparte el mismo blocks_json; este es el equivalente server-side que
# cubre TAMBIEN running, usando el texto que intervals.icu parsea en pasos).

def _fmt_dur(seconds: int) -> str:
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    if s == 0:
        return f"{m}m"
    if m == 0:
        return f"{s}s"
    return f"{m}m{s}s"


def _fmt_pace(sec_per_km: float) -> str:
    sec_per_km = max(1, round(sec_per_km))
    m, s = divmod(sec_per_km, 60)
    return f"{m}:{s:02d}/km"


def _bike_target(pct: float) -> str:
    return f"{round(pct * 100)}%"


def _run_target(mode: str, val: float) -> str:
    if mode == "hr":
        return f"{round(val * 100)}% HR"
    return f"{_fmt_pace(val)} Pace"


def _ramp_line(label: str, duration: int, lo: str, hi: str) -> str:
    return f"- {label}{_fmt_dur(duration)} ramp {lo}-{hi}"


def blocks_to_intervals_dsl(blocks: list[dict], sport: str) -> str:
    """Convierte blocks_json (mismo formato que ZWO/TCX de workout-blocks.js)
    en el texto DSL de intervals.icu. Nunca lanza -- bloques desconocidos se
    omiten (mejor un workout incompleto que una excepcion a mitad de envio)."""
    lines: list[str] = []
    is_run = sport == "run"

    def tgt(b: dict, key: str) -> str:
        if is_run:
            return _run_target(b.get("mode", "pace"), float(b.get(key, 0)))
        return _bike_target(float(b.get(key, 0)))

    for b in blocks:
        t = b.get("type", "steady")
        try:
            if t in ("warmup", "cooldown", "ramp"):
                d = int(b.get("duration", 600))
                label = {"warmup": "Warmup ", "cooldown": "Cooldown "}.get(t, "")
                if is_run:
                    lo_key, hi_key = ("val_low", "val_high")
                    lo, hi = tgt(b, lo_key), tgt(b, hi_key)
                else:
                    lo_val, hi_val = float(b.get("power_low", 0.5)), float(b.get("power_high", 0.75))
                    if t == "cooldown":
                        lo_val, hi_val = hi_val, lo_val  # ramp hacia abajo, mismo criterio que el .zwo
                    lo, hi = _bike_target(lo_val), _bike_target(hi_val)
                lines.append(_ramp_line(label, d, lo, hi))
            elif t == "steady":
                d = int(b.get("duration", 300))
                target = tgt(b, "val") if is_run else _bike_target(float(b.get("power", 0.75)))
                lines.append(f"- {_fmt_dur(d)} {target}")
            elif t == "freeride":
                d = int(b.get("duration", 300))
                lines.append(f"- {_fmt_dur(d)} Free Ride")
            elif t == "intervals":
                rep   = int(b.get("repeat", 1))
                on_d  = int(b.get("on_duration", 240))
                off_d = int(b.get("off_duration", 120))
                on_t  = tgt(b, "on_val") if is_run else _bike_target(float(b.get("on_power", 0.95)))
                off_t = tgt(b, "off_val") if is_run else _bike_target(float(b.get("off_power", 0.55)))
                if lines:
                    lines.append("")
                lines.append(f"{rep}x")
                lines.append(f"- {_fmt_dur(on_d)} {on_t}")
                lines.append(f"- {_fmt_dur(off_d)} {off_t}")
                lines.append("")
        except (TypeError, ValueError) as exc:
            logger.warning("Bloque %s omitido al armar DSL intervals.icu: %s", b.get("id"), exc)
            continue

    return "\n".join(lines).strip()


# ── Envio del evento ─────────────────────────────────────────────────────

async def send_workout_event(user: "User", name: str, sport: str, blocks: list[dict],
                             date_iso: str, description: str = "",
                             event_id: "str | int | None" = None) -> dict:
    """Crea (o, con `event_id`, ACTUALIZA) el evento WORKOUT en el calendario del
    atleta. Si el PUT responde 404 (el evento ya no existe alla) crea uno nuevo.
    Lanza IntervalsError con un mensaje claro si algo falla -- nunca devuelve
    exito si la API falló."""
    token = read_access_token(user)
    if not token:
        raise IntervalsError("Tu reloj no esta conectado a intervals.icu")

    dsl = blocks_to_intervals_dsl(blocks, sport)
    body_desc = (description.strip() + "\n\n" + dsl).strip() if description.strip() else dsl

    payload = {
        "category":         "WORKOUT",
        "start_date_local":  f"{date_iso}T00:00:00",
        "type":              "Run" if sport == "run" else "Ride",
        "name":              name[:120] or "Workout LabX",
        "description":       body_desc,
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    events_url = f"{API_BASE}/athlete/0/events"

    async with httpx.AsyncClient(timeout=15) as client:
        async def _call(method: str, url: str):
            try:
                return await getattr(client, method)(url, headers=headers, content=json.dumps(payload))
            except httpx.HTTPError as exc:
                raise IntervalsError(f"No se pudo contactar a intervals.icu: {exc}") from exc

        r = None
        if event_id:
            r = await _call("put", f"{events_url}/{event_id}")
            if r.status_code == 404:
                logger.info("Evento intervals.icu %s ya no existe; se crea uno nuevo", event_id)
                r = None
        if r is None:
            r = await _call("post", events_url)

        if r.status_code in (401, 403):
            raise IntervalsError("intervals.icu rechazo el token -- reconecta tu reloj")
        if r.status_code >= 400:
            raise IntervalsError(f"intervals.icu rechazo el workout ({r.status_code})")

        data = r.json() if r.content else {}
        new_id = data.get("id")
        if new_id is None and event_id and r.status_code < 300:
            new_id = event_id  # PUT sin cuerpo: el id sigue siendo el mismo
        return {"ok": True, "event_id": new_id, "description": body_desc}


async def delete_workout_event(user: "User", event_id: "str | int") -> bool:
    """Borra el evento remoto. Best-effort: nunca lanza; devuelve True si se
    borro (o ya no existia) y False si fallo (queda en el log)."""
    try:
        token = read_access_token(user)
        if not token:
            logger.warning("DELETE evento intervals.icu %s omitido: sin token", event_id)
            return False
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.delete(
                f"{API_BASE}/athlete/0/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code in (404, 410) or r.status_code < 300:
            return True
        logger.warning("DELETE evento intervals.icu %s fallo (%s)", event_id, r.status_code)
    except Exception as exc:  # noqa: BLE001 -- la baja local no depende del remoto
        logger.warning("DELETE evento intervals.icu %s fallo: %s", event_id, exc)
    return False
