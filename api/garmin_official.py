"""
Integracion OFICIAL Garmin Connect Developer Program (OAuth2 + PKCE + push).

Convive con la via no oficial (garmin_connector / garmin_pull_service), que NO se
toca. Este modulo solo maneja: configuracion, PKCE/state, intercambio y refresh de
tokens (cifrados en reposo). Nunca se registra ni se imprime el secreto ni tokens.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from . import crypto
from .models import GarminOAuthState, GarminOAuthToken

logger = logging.getLogger("labx.garmin_official")

AUTHORIZE_URL = "https://connect.garmin.com/oauth2Confirm"
TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
GARMIN_USER_ID_URL = "https://apis.garmin.com/wellness-api/rest/user/id"
# Activity API: pull por hora de subida (uploadStart/EndTimeInSeconds, ventana maxima 24 h).
GARMIN_ACTIVITIES_URL = "https://apis.garmin.com/wellness-api/rest/activities"
PULL_WINDOW_S = 86400
PULL_MAX_DAYS = 7
PULL_WORKERS = 4  # ventanas en paralelo: peor caso 2 rondas x 20 s = 40 s (antes 7 x 20 = 140 s)

STATE_TTL = timedelta(minutes=10)
REFRESH_MARGIN = timedelta(seconds=60)


class GarminOfficialError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Config (se lee en cada llamada: nada se cae si faltan) ──────────────────

def client_id() -> str:
    return (os.getenv("GARMIN_CLIENT_ID") or "").strip()


def client_secret() -> str:
    return (os.getenv("GARMIN_CLIENT_SECRET") or "").strip()


def redirect_uri() -> str:
    return (os.getenv("GARMIN_REDIRECT_URI") or "").strip()


def configured() -> bool:
    return bool(client_id() and client_secret() and redirect_uri())


# ── PKCE + state ────────────────────────────────────────────────────────────

def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)  # 86 chars, dentro de 43..128
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def _sign(raw: str, user_id: str) -> str:
    from .auth import SECRET_KEY
    return hmac.new(SECRET_KEY.encode(), f"{raw}:{user_id}".encode(), hashlib.sha256).hexdigest()[:32]


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def create_state(db: Session, user_id: str) -> tuple[str, str]:
    """Devuelve (state, code_challenge). El verifier queda server-side."""
    db.query(GarminOAuthState).filter(GarminOAuthState.expires_at < _now()).delete()
    raw = secrets.token_urlsafe(24)
    state = f"{raw}.{_sign(raw, user_id)}"
    verifier, challenge = make_pkce()
    db.add(GarminOAuthState(state_hash=_hash(state), user_id=user_id,
                            code_verifier=verifier, expires_at=_now() + STATE_TTL))
    db.commit()
    return state, challenge


def consume_state(db: Session, state: str) -> tuple[str, str] | None:
    """Valida firma + existencia + vigencia; es de un solo uso. -> (user_id, verifier) | None."""
    if not state or "." not in state:
        return None
    row = db.query(GarminOAuthState).filter(GarminOAuthState.state_hash == _hash(state)).first()
    if not row:
        return None
    raw = state.rsplit(".", 1)[0]
    user_id, verifier, expires = row.user_id, row.code_verifier, row.expires_at
    db.delete(row)
    db.commit()
    if not hmac.compare_digest(state.rsplit(".", 1)[1], _sign(raw, user_id)):
        return None
    if expires < _now():
        return None
    return user_id, verifier


def build_authorize_url(state: str, challenge: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })


# ── HTTP (puntos unicos de red; los tests parchean estos) ───────────────────

def _post_token(data: dict) -> dict:
    try:
        r = httpx.post(TOKEN_URL, data=data, timeout=15,
                       headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise GarminOfficialError(f"Garmin no respondio ({type(exc).__name__})") from None
    if r.status_code != 200:
        raise GarminOfficialError(f"Garmin rechazo el token ({r.status_code})")
    try:
        body = r.json()
    except Exception:
        raise GarminOfficialError("Respuesta de token invalida") from None
    if not isinstance(body, dict) or not body.get("access_token"):
        raise GarminOfficialError("Garmin no devolvio access_token")
    return body


def _fetch_garmin_user_id(access_token: str) -> str | None:
    try:
        r = httpx.get(GARMIN_USER_ID_URL, timeout=10,
                      headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code == 200:
            return str(r.json().get("userId") or "") or None
    except Exception:
        pass
    return None


# ── Tokens ──────────────────────────────────────────────────────────────────

def exchange_code(code: str, verifier: str) -> dict:
    return _post_token({
        "grant_type": "authorization_code",
        "client_id": client_id(),
        "client_secret": client_secret(),
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri(),
    })


def save_tokens(db: Session, user_id: str, tokens: dict, garmin_user_id: str | None = None) -> GarminOAuthToken:
    row = db.query(GarminOAuthToken).filter(GarminOAuthToken.user_id == user_id).first()
    if not row:
        row = GarminOAuthToken(user_id=user_id, access_token="")
        db.add(row)
    row.access_token = crypto.encrypt(tokens["access_token"])
    if tokens.get("refresh_token"):
        row.refresh_token = crypto.encrypt(tokens["refresh_token"])
    try:
        row.expires_at = _now() + timedelta(seconds=int(tokens["expires_in"])) if tokens.get("expires_in") else None
    except (TypeError, ValueError):
        row.expires_at = None
    row.scope = tokens.get("scope") or row.scope
    if garmin_user_id:
        row.garmin_user_id = garmin_user_id
    row.updated_at = _now()
    db.commit()
    return row


def get_valid_access_token(db: Session, user_id: str) -> str | None:
    """Access token vigente del usuario; lo renueva con el refresh_token si vencio.
    None si no esta conectado o no se pudo renovar. (Para futuras lecturas oficiales.)"""
    row = db.query(GarminOAuthToken).filter(GarminOAuthToken.user_id == user_id).first()
    if not row:
        return None
    if row.expires_at is None or row.expires_at > _now() + REFRESH_MARGIN:
        return crypto.decrypt(row.access_token)
    refresh = crypto.decrypt(row.refresh_token)
    if not refresh or not configured():
        return None
    try:
        tokens = _post_token({
            "grant_type": "refresh_token",
            "client_id": client_id(),
            "client_secret": client_secret(),
            "refresh_token": refresh,
        })
    except GarminOfficialError as exc:
        logger.warning("Garmin refresh fallo user=%s: %s", user_id, exc)
        return None
    save_tokens(db, user_id, tokens)
    return tokens["access_token"]


# -- Pull bajo demanda de actividades (SYNC-CONEXIONES) ----------------------

def _get_activities_window(access_token: str, start_s: int, end_s: int) -> list:
    """Una ventana (<=24 h) del pull de actividades. Unico punto de red del pull
    (los tests lo parchean). Nunca incluye el token en mensajes de error."""
    try:
        r = httpx.get(GARMIN_ACTIVITIES_URL, timeout=20,
                      params={"uploadStartTimeInSeconds": start_s, "uploadEndTimeInSeconds": end_s},
                      headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise GarminOfficialError(f"Garmin no respondio ({type(exc).__name__})") from None
    if r.status_code in (401, 403):
        raise GarminOfficialError(f"Garmin no autoriza el pull de actividades ({r.status_code})")
    if r.status_code != 200:
        raise GarminOfficialError(f"Garmin rechazo el pull de actividades ({r.status_code})")
    try:
        body = r.json()
    except Exception:
        raise GarminOfficialError("Respuesta de actividades invalida") from None
    if not isinstance(body, list):
        raise GarminOfficialError("Respuesta de actividades invalida")
    return [it for it in body if isinstance(it, dict)]


def _timed_window(access_token: str, start_s: int, end_s: int) -> tuple:
    """Una ventana con su duracion. Devuelve (items, error, segundos); nunca lanza GarminOfficialError."""
    t0 = time.monotonic()
    try:
        return _get_activities_window(access_token, start_s, end_s), None, time.monotonic() - t0
    except GarminOfficialError as exc:
        return [], exc, time.monotonic() - t0


def fetch_recent_activities_detailed(access_token: str, days: int = PULL_MAX_DAYS) -> tuple:
    """Pull de las ventanas de 24 h en paralelo (pool acotado a PULL_WORKERS, timeout por ventana
    intacto). Devuelve (items, errors, timings): items en orden de ventana (la mas reciente primero,
    igual que el secuencial), errors = [(indice_ventana, GarminOfficialError)] y timings = segundos
    por ventana. Una ventana fallida NO descarta las demas."""
    days = max(1, min(int(days), PULL_MAX_DAYS))
    end = int(_now().replace(tzinfo=timezone.utc).timestamp())
    bounds = [(end - i * PULL_WINDOW_S - PULL_WINDOW_S, end - i * PULL_WINDOW_S) for i in range(days)]
    with ThreadPoolExecutor(max_workers=min(PULL_WORKERS, days)) as pool:
        results = list(pool.map(lambda b: _timed_window(access_token, b[0], b[1]), bounds))
    items: list = []
    errors: list = []
    for idx, (win_items, err, _dur) in enumerate(results):
        items.extend(win_items)
        if err is not None:
            errors.append((idx, err))
    return items, errors, [round(r[2], 2) for r in results]


def fetch_recent_activities(access_token: str, days: int = PULL_MAX_DAYS) -> list:
    """Actividades subidas en los ultimos `days` dias (ventanas de 24 h, maximo 7).
    Solo actividades: la salud llega unicamente por push. Lanza el error de la primera
    ventana fallida (contrato anterior); el sync manual usa la variante _detailed."""
    items, errors, _ = fetch_recent_activities_detailed(access_token, days)
    if errors:
        raise errors[0][1]
    return items
