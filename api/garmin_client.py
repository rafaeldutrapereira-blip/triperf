"""
LabX — Garmin Training API Client
======================================
Maneja autenticación OAuth 2.0 + todas las llamadas HTTP a la
Garmin Training API (creación, actualización y scheduling de workouts).

Garmin Training API base URL:
  https://apis.garmin.com/training-api/

Flujo OAuth 2.0 (Authorization Code + PKCE):
  1. Redirect al atleta → https://connect.garmin.com/oauth-service/oauth/authorize
  2. Garmin redirige a nuestro callback con ?code=...
  3. Intercambiamos code → access_token + refresh_token
  4. Usamos access_token en cada request (Bearer)
  5. Si 401 → refresh automático
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx                    # pip install httpx
from tenacity import (          # pip install tenacity
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN (carga desde variables de entorno)
# ─────────────────────────────────────────────────────────────────────────────

GARMIN_CLIENT_ID     = os.getenv("GARMIN_CLIENT_ID",     "YOUR_CLIENT_ID")
GARMIN_CLIENT_SECRET = os.getenv("GARMIN_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
GARMIN_REDIRECT_URI  = os.getenv("GARMIN_REDIRECT_URI",  "https://kona.app/api/garmin/callback")

GARMIN_OAUTH_BASE    = "https://connect.garmin.com/oauth-service/oauth"
GARMIN_API_BASE      = "https://apis.garmin.com/training-api"

# Rate limit Garmin: 60 req/min por usuario, 3600 req/hr global
RATE_LIMIT_RPM       = 60


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPCIONES
# ─────────────────────────────────────────────────────────────────────────────

class GarminAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body

class GarminRateLimitError(GarminAPIError):
    """HTTP 429 — demasiadas solicitudes."""
    def __init__(self, retry_after: int = 60):
        super().__init__(f"Rate limited. Retry after {retry_after}s", 429)
        self.retry_after = retry_after

class GarminTokenExpiredError(GarminAPIError):
    """HTTP 401 — token expirado o inválido."""
    pass

class GarminNotFoundError(GarminAPIError):
    """HTTP 404 — workout o recurso no existe."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# OAUTH 2.0 — TOKEN STORE (interfaz abstracta; implementar con DB real)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OAuth2Token:
    access_token:  str
    refresh_token: str
    expires_at:    datetime
    scope:         list[str]

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        return datetime.now(timezone.utc) >= (self.expires_at - timedelta(seconds=buffer_seconds))


class TokenStore:
    """
    Interfaz para persistencia de tokens.
    Implementar con asyncpg / SQLAlchemy en producción.
    Esta versión en memoria es solo para testing.
    """
    def __init__(self) -> None:
        self._store: dict[str, OAuth2Token] = {}

    async def get(self, athlete_id: str) -> OAuth2Token | None:
        return self._store.get(athlete_id)

    async def save(self, athlete_id: str, token: OAuth2Token) -> None:
        self._store[athlete_id] = token

    async def delete(self, athlete_id: str) -> None:
        self._store.pop(athlete_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# OAUTH 2.0 — PKCE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def generate_pkce_pair() -> tuple[str, str]:
    """Genera code_verifier y code_challenge para PKCE."""
    verifier = secrets.token_urlsafe(96)[:128]
    digest   = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(state: str, code_challenge: str) -> str:
    """
    Genera la URL a la que redirigir al atleta para autorización.
    El state debe guardarse en sesión para validar en el callback.
    """
    params = {
        "response_type":         "code",
        "client_id":             GARMIN_CLIENT_ID,
        "redirect_uri":          GARMIN_REDIRECT_URI,
        "scope":                 "WORKOUT_WRITE SCHEDULE_WRITE",
        "state":                 state,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{GARMIN_OAUTH_BASE}/authorize?{urllib.parse.urlencode(params)}"


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class GarminClient:
    """
    Cliente asíncrono para la Garmin Training API.

    Ejemplo de uso:
        store  = TokenStore()
        client = GarminClient(store)
        wid    = await client.create_workout(athlete_id, payload)
        await client.schedule_workout(athlete_id, wid, "2026-07-15")
    """

    def __init__(self, token_store: TokenStore, timeout: float = 15.0):
        self._store   = token_store
        self._timeout = timeout
        self._http    = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ──────────────────────────────────────────
    # OAUTH 2.0 — EXCHANGE CODE → TOKEN
    # ──────────────────────────────────────────

    async def exchange_code(
        self,
        athlete_id:    str,
        code:          str,
        code_verifier: str,
    ) -> OAuth2Token:
        """
        Intercambia el code del callback por access_token + refresh_token.
        Guardar el token en DB inmediatamente.
        """
        resp = await self._http.post(
            f"{GARMIN_OAUTH_BASE}/token",
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  GARMIN_REDIRECT_URI,
                "client_id":     GARMIN_CLIENT_ID,
                "client_secret": GARMIN_CLIENT_SECRET,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._raise_for_status(resp)
        data  = resp.json()
        token = OAuth2Token(
            access_token  = data["access_token"],
            refresh_token = data["refresh_token"],
            expires_at    = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"]),
            scope         = data.get("scope", "").split(),
        )
        await self._store.save(athlete_id, token)
        logger.info("Garmin token obtenido para atleta %s", athlete_id)
        return token

    # ──────────────────────────────────────────
    # OAUTH 2.0 — REFRESH TOKEN
    # ──────────────────────────────────────────

    async def _refresh_token(self, athlete_id: str, token: OAuth2Token) -> OAuth2Token:
        """Renueva el access_token usando el refresh_token. Actualiza el store."""
        logger.info("Refrescando token Garmin para atleta %s", athlete_id)
        resp = await self._http.post(
            f"{GARMIN_OAUTH_BASE}/token",
            data={
                "grant_type":    "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id":     GARMIN_CLIENT_ID,
                "client_secret": GARMIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 400:
            # Refresh token también expiró → el atleta debe re-autorizar
            await self._store.delete(athlete_id)
            raise GarminTokenExpiredError(
                "Refresh token inválido. El atleta debe reconectar Garmin.",
                400,
            )
        self._raise_for_status(resp)
        data      = resp.json()
        new_token = OAuth2Token(
            access_token  = data["access_token"],
            refresh_token = data.get("refresh_token", token.refresh_token),
            expires_at    = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"]),
            scope         = token.scope,
        )
        await self._store.save(athlete_id, new_token)
        return new_token

    async def _get_valid_token(self, athlete_id: str) -> OAuth2Token:
        """Devuelve un token válido, refrescándolo si está cerca de expirar."""
        token = await self._store.get(athlete_id)
        if not token:
            raise GarminTokenExpiredError(
                f"No hay token Garmin para atleta {athlete_id}. "
                "El atleta debe autorizar LabX en Garmin Connect.",
                401,
            )
        if token.is_expired():
            token = await self._refresh_token(athlete_id, token)
        return token

    # ──────────────────────────────────────────
    # REQUEST HELPER (con retry automático)
    # ──────────────────────────────────────────

    @retry(
        retry     = retry_if_exception_type(httpx.TransportError),
        stop      = stop_after_attempt(3),
        wait      = wait_exponential(multiplier=1, min=1, max=8),
        reraise   = True,
    )
    async def _request(
        self,
        method:     str,
        path:       str,
        athlete_id: str,
        json:       Any = None,
        params:     dict | None = None,
    ) -> dict[str, Any]:
        """
        Ejecuta un request autenticado. Renueva el token si 401.
        Lanza GarminRateLimitError en 429.
        """
        token = await self._get_valid_token(athlete_id)
        url   = f"{GARMIN_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        resp = await self._http.request(
            method, url, json=json, params=params, headers=headers
        )

        # 401 → intentar refresh una vez
        if resp.status_code == 401:
            logger.warning("Token 401 para atleta %s — intentando refresh", athlete_id)
            token = await self._refresh_token(athlete_id, token)
            headers["Authorization"] = f"Bearer {token.access_token}"
            resp = await self._http.request(
                method, url, json=json, params=params, headers=headers
            )

        # 429 → Rate limit
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            raise GarminRateLimitError(retry_after)

        self._raise_for_status(resp)

        if resp.status_code == 204:   # No Content (DELETE, unschedule)
            return {}
        return resp.json()

    # ──────────────────────────────────────────
    # WORKOUT CRUD
    # ──────────────────────────────────────────

    async def create_workout(
        self, athlete_id: str, payload: dict[str, Any]
    ) -> int:
        """
        Crea el workout en Garmin.
        Retorna el garmin_workout_id (int).
        """
        data = await self._request("POST", "/workout", athlete_id, json=payload)
        wid  = data.get("workoutId") or data.get("workout_id")
        if not wid:
            raise GarminAPIError("Garmin no devolvió workoutId", body=data)
        logger.info("Workout creado en Garmin: %s (atleta %s)", wid, athlete_id)
        return int(wid)

    async def update_workout(
        self, athlete_id: str, garmin_workout_id: int, payload: dict[str, Any]
    ) -> None:
        """Actualiza un workout existente en Garmin."""
        await self._request(
            "PUT", f"/workout/{garmin_workout_id}", athlete_id, json=payload
        )
        logger.info("Workout %s actualizado en Garmin", garmin_workout_id)

    async def delete_workout(
        self, athlete_id: str, garmin_workout_id: int
    ) -> None:
        """Borra un workout de Garmin (no del calendario)."""
        await self._request("DELETE", f"/workout/{garmin_workout_id}", athlete_id)
        logger.info("Workout %s eliminado de Garmin", garmin_workout_id)

    # ──────────────────────────────────────────
    # SCHEDULING — Calendario del atleta
    # ──────────────────────────────────────────

    async def schedule_workout(
        self,
        athlete_id:        str,
        garmin_workout_id: int,
        date:              str,    # formato "YYYY-MM-DD"
    ) -> int:
        """
        Agrega el workout al calendario Garmin en la fecha indicada.
        Retorna el garmin_schedule_id.
        """
        data = await self._request(
            "POST",
            f"/workout/{garmin_workout_id}/schedule/{date}",
            athlete_id,
        )
        sid = data.get("scheduleId") or data.get("id")
        logger.info(
            "Workout %s scheduled el %s (scheduleId=%s)", garmin_workout_id, date, sid
        )
        return int(sid) if sid else 0

    async def unschedule_workout(
        self, athlete_id: str, garmin_schedule_id: int
    ) -> None:
        """Elimina un evento del calendario Garmin."""
        await self._request(
            "DELETE", f"/workout/schedule/{garmin_schedule_id}", athlete_id
        )
        logger.info("Schedule %s eliminado de Garmin", garmin_schedule_id)

    async def get_scheduled_workouts(
        self, athlete_id: str, start: str, end: str
    ) -> list[dict]:
        """
        Lista los workouts programados en un rango de fechas.
        start/end en formato "YYYY-MM-DD".
        """
        data = await self._request(
            "GET", "/workout/schedule",
            athlete_id,
            params={"start": start, "end": end},
        )
        return data if isinstance(data, list) else data.get("workouts", [])

    # ──────────────────────────────────────────
    # ERROR HANDLER
    # ──────────────────────────────────────────

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        body = None
        try:
            body = resp.json()
        except Exception:
            body = resp.text

        if resp.status_code == 404:
            raise GarminNotFoundError("Recurso no encontrado en Garmin", 404, body)
        if resp.status_code == 401:
            raise GarminTokenExpiredError("Token Garmin inválido", 401, body)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            raise GarminRateLimitError(retry_after)
        raise GarminAPIError(
            f"Garmin API error {resp.status_code}", resp.status_code, body
        )
