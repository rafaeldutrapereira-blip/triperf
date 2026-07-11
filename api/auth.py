"""
JWT authentication + bcrypt password hashing.
Soporta tokens via HttpOnly cookie Y Authorization header (backward compat).
Token revocation persistida en DB (tabla revoked_tokens).
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

_jwt_secret = os.getenv("JWT_SECRET", "")
if not _jwt_secret:
    if os.getenv("APP_ENV", "development") == "production":
        raise RuntimeError("JWT_SECRET no configurada — la aplicación no puede arrancar en producción sin esta variable.")
    import warnings
    _jwt_secret = "labx-local-dev-secret-INSEGURO-cambiar-antes-de-produccion"
    warnings.warn("JWT_SECRET no configurada — usando clave de desarrollo insegura.", RuntimeWarning, stacklevel=1)

SECRET_KEY  = _jwt_secret
ALGORITHM   = "HS256"
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "8"))
IS_PROD     = os.getenv("APP_ENV", "development") == "production"
_AUDIENCE   = os.getenv("JWT_AUDIENCE", "labx-app")   # S2/QW-08: audience claim

# Cache en memoria para lookup rápido (se recarga desde DB al importar)
_revoked_hashes: set[str] = set()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Passwords ──────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT ────────────────────────────────────────────────────
def create_token(user_id: str, rol: str, nombre: str, token_gen: int = 1,
                  remember: bool = False) -> str:
    """
    S2/QW-08: Include 'aud' claim. S5: remember=True → 30 días en vez de TOKEN_HOURS.
    """
    hours = 24 * 30 if remember else TOKEN_HOURS
    expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=hours)
    return jwt.encode(
        {
            "sub":  user_id,
            "rol":  rol,
            "nombre": nombre,
            "gen":  token_gen,
            "exp":  expire,
            "aud":  _AUDIENCE,        # QW-08: audience claim
            "iss":  "labx",           # issuer claim
        },
        SECRET_KEY, algorithm=ALGORITHM
    )

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=_AUDIENCE,       # QW-08: validate audience
        )
        if _token_hash(token) in _revoked_hashes:
            raise HTTPException(status_code=401, detail="Token revocado")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

def revoke_token(token: str, db: Optional[Session] = None) -> None:
    """
    Revoca un token añadiendo su hash a la blacklist.
    Si se provee db, persiste en la tabla revoked_tokens.
    El cache en memoria garantiza O(1) lookup en requests subsecuentes.
    """
    from .models import RevokedToken
    h = _token_hash(token)
    _revoked_hashes.add(h)

    if db is not None:
        try:
            # Decodificar sin validar para obtener exp
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                                 options={"verify_exp": False})
            exp = datetime.utcfromtimestamp(payload.get("exp", 0))
        except Exception:
            exp = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=TOKEN_HOURS)

        existing = db.query(RevokedToken).filter(RevokedToken.token_hash == h).first()
        if not existing:
            db.add(RevokedToken(token_hash=h, expires_at=exp))
            db.commit()
        # Limpiar tokens expirados (best-effort, no bloquea el request)
        try:
            db.query(RevokedToken).filter(RevokedToken.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)).delete()
            db.commit()
        except Exception:
            db.rollback()


def load_revoked_tokens_from_db() -> None:
    """Carga tokens revocados vigentes desde DB al cache en memoria. Llamar al arranque."""
    try:
        from .database import SessionLocal
        from .models import RevokedToken
        db = SessionLocal()
        rows = db.query(RevokedToken.token_hash).filter(
            RevokedToken.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
        ).all()
        _revoked_hashes.update(r[0] for r in rows)
        db.close()
    except Exception:
        pass  # Si falla el DB al arrancar, el cache queda vacío (degraded, no fatal)


def _extract_token(request: Request) -> Optional[str]:
    """Lee token desde HttpOnly cookie primero, luego Authorization header."""
    # 1. Cookie HttpOnly (más seguro — JS no puede leerla)
    token = request.cookies.get("lx_access_token")
    if token:
        return token
    # 2. Authorization header (backward compat para clientes que aún usan Bearer)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# ── FastAPI dependencies ────────────────────────────────────
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado",
                            headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido — falta sub",
                            headers={"WWW-Authenticate": "Bearer"})
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if not user.activo:
        # B-04: activo=False debe bloquear cualquier token existente
        raise HTTPException(status_code=403, detail="Cuenta desactivada — contacta al soporte")
    # Verificar generación de token (cierre de todas las sesiones)
    # B-02: token_gen ausente en tokens antiguos → .get con default 1
    token_gen = payload.get("gen", 1)
    user_gen  = user.token_gen or 1
    if token_gen < user_gen:
        raise HTTPException(status_code=401, detail="Sesión revocada — vuelve a ingresar")
    return user

def require_role(*roles: str):
    """Dependency factory — require_role('coach','admin') etc."""
    def _check(request: Request, db: Session = Depends(get_db)) -> User:
        current = get_current_user(request, db)
        if current.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere rol: {' o '.join(roles)}"
            )
        return current
    return _check
