"""
OAuth generico para wearables Polar y Wahoo: config, state, conexiones y refresh.

Espejo de garmin_official.py (state hasheado en DB, un solo uso, TTL 10 min). Los
tokens se guardan cifrados con Fernet (api/crypto.py) y nunca se registran en logs.
El flag de habilitacion NO se duplica: se delega en api/providers/registry.py.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import crypto
from .app_url import get_app_url
from .models import ProviderConnection, ProviderOAuthState
from .providers import registry

logger = logging.getLogger("labx.provider_oauth")

STATE_TTL = timedelta(minutes=10)
REFRESH_MARGIN = timedelta(seconds=60)

# scope: Polar se omite a proposito -- la documentacion AccessLink citada en
# providers/polar.py no menciona ningun parametro scope para el authorize.
PROVIDERS: dict[str, dict] = {
    "polar": {
        "authorize_url": "https://flow.polar.com/oauth2/authorization",
        "env_prefix": "POLAR",
        "scope": None,
    },
    "wahoo": {
        "authorize_url": "https://api.wahooligan.com/oauth/authorize",
        "env_prefix": "WAHOO",
        "scope": "user_read workouts_read power_zones_read offline_data",
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _env(provider: str, suffix: str) -> str:
    return (os.getenv(f"{PROVIDERS[provider]['env_prefix']}_{suffix}") or "").strip()


def client_id(provider: str) -> str:
    return _env(provider, "CLIENT_ID")


def client_secret(provider: str) -> str:
    return _env(provider, "CLIENT_SECRET")


def authorize_url(provider: str) -> str:
    return PROVIDERS[provider]["authorize_url"]


def scope(provider: str) -> str | None:
    return PROVIDERS[provider]["scope"]


def redirect_uri(provider: str) -> str:
    return _env(provider, "REDIRECT_URI") or f"{get_app_url()}/api/integrations/{provider}/callback"


def configured(provider: str) -> bool:
    return bool(client_id(provider) and client_secret(provider))


def enabled(provider: str) -> bool:
    return registry.is_provider_enabled(provider)


# ── state ───────────────────────────────────────────────────────────────────

def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _sign(raw: str, user_id: str, provider: str) -> str:
    from .auth import SECRET_KEY
    return hmac.new(SECRET_KEY.encode(), f"{raw}:{user_id}:{provider}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def create_state(db: Session, user_id: str, provider: str) -> str:
    db.query(ProviderOAuthState).filter(ProviderOAuthState.expires_at < _now()).delete()
    raw = secrets.token_urlsafe(24)
    state = f"{raw}.{_sign(raw, user_id, provider)}"
    db.add(ProviderOAuthState(state_hash=_hash(state), user_id=user_id, provider=provider,
                              expires_at=_now() + STATE_TTL))
    db.commit()
    return state


def consume_state(db: Session, state: str, provider: str) -> str | None:
    """Valida firma + provider + vigencia; un solo uso. -> user_id | None."""
    if not state or "." not in state:
        return None
    row = (db.query(ProviderOAuthState)
           .filter(ProviderOAuthState.state_hash == _hash(state),
                   ProviderOAuthState.provider == provider).first())
    if not row:
        return None
    user_id, expires = row.user_id, row.expires_at
    db.delete(row)
    db.commit()
    raw, sig = state.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(raw, user_id, provider)):
        return None
    if expires < _now():
        return None
    return user_id


# ── conexiones ──────────────────────────────────────────────────────────────

def get_connection(db: Session, user_id: str, provider: str) -> ProviderConnection | None:
    return (db.query(ProviderConnection)
            .filter(ProviderConnection.user_id == user_id,
                    ProviderConnection.provider == provider).first())


def save_connection(db: Session, user_id: str, provider: str, token_response: dict,
                    member_id: str | None = None) -> ProviderConnection:
    row = get_connection(db, user_id, provider)
    if not row:
        row = ProviderConnection(user_id=user_id, provider=provider, access_token="")
        db.add(row)
    row.access_token = crypto.encrypt(token_response["access_token"])
    if token_response.get("refresh_token"):
        row.refresh_token = crypto.encrypt(token_response["refresh_token"])
    if token_response.get("expires_in"):
        try:
            row.expires_at = _now() + timedelta(seconds=int(token_response["expires_in"]))
        except (TypeError, ValueError):
            row.expires_at = None
    else:
        row.expires_at = None
    if token_response.get("x_user_id") is not None:
        row.external_user_id = str(token_response["x_user_id"])
    if member_id:
        row.member_id = str(member_id)
    if token_response.get("scope"):
        row.scope = token_response["scope"]
    row.updated_at = _now()
    db.commit()
    return row


def delete_connection(db: Session, user_id: str, provider: str) -> bool:
    # Polar/Wahoo no exponen desautorizacion en estos providers: borrado local solamente.
    deleted = (db.query(ProviderConnection)
               .filter(ProviderConnection.user_id == user_id,
                       ProviderConnection.provider == provider).delete())
    db.commit()
    return bool(deleted)


async def get_valid_access_token(db: Session, user_id: str, provider: str) -> str | None:
    row = get_connection(db, user_id, provider)
    if not row:
        return None
    access = crypto.decrypt(row.access_token)
    if provider == "polar":
        return access  # el token de Polar no expira: sin refresh
    if row.expires_at is None or row.expires_at > _now() + REFRESH_MARGIN:
        return access
    refresh = crypto.decrypt(row.refresh_token)
    if not refresh:
        return None
    from .providers.wahoo import WahooProvider
    prov = WahooProvider(db)
    try:
        await prov.authenticate(user_id, refresh_token=refresh)
        if not prov.last_token_response:
            return None
        save_connection(db, user_id, provider, prov.last_token_response)
    except Exception as exc:
        logger.warning("Wahoo refresh fallo user=%s: %s", user_id, type(exc).__name__)
        return None
    return prov.last_token_response["access_token"]
