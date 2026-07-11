"""
Redis client opcional para LabX.
Si REDIS_URL no está configurada, todas las operaciones son no-ops (fallback a DB/memoria).

Uso:
    from api.redis_client import redis_get, redis_set, redis_incr, redis_expire

Configurar en .env:
    REDIS_URL=redis://localhost:6379/0
    # o con autenticación:
    REDIS_URL=redis://:password@host:6379/0
    # TLS (Upstash, Railway, etc.):
    REDIS_URL=rediss://user:password@host:6379/0
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("labx.redis")

_REDIS_URL = os.getenv("REDIS_URL", "")
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not _REDIS_URL:
        return None
    try:
        import redis
        _client = redis.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
        )
        _client.ping()
        logger.info("Redis conectado: %s", _REDIS_URL.split("@")[-1])
    except ImportError:
        logger.warning("redis-py no instalado (pip install redis). Usando fallback en memoria.")
        _client = None
    except Exception as e:
        logger.warning("Redis no disponible (%s). Usando fallback en memoria/DB.", e)
        _client = None
    return _client


def is_available() -> bool:
    return _get_client() is not None


def redis_get(key: str) -> str | None:
    c = _get_client()
    if not c:
        return None
    try:
        return c.get(key)
    except Exception:
        return None


def redis_set(key: str, value: Any, ex: int | None = None) -> bool:
    """SET key value [EX seconds]. Retorna True si OK."""
    c = _get_client()
    if not c:
        return False
    try:
        c.set(key, str(value), ex=ex)
        return True
    except Exception:
        return False


def redis_delete(*keys: str) -> int:
    c = _get_client()
    if not c:
        return 0
    try:
        return c.delete(*keys)
    except Exception:
        return 0


def redis_incr(key: str, ex_seconds: int = 3600) -> int:
    """
    Incrementa un contador, seteando TTL si es la primera vez.
    Usado para rate limiting.
    Retorna el nuevo valor, o -1 si Redis no disponible.
    """
    c = _get_client()
    if not c:
        return -1
    try:
        pipe = c.pipeline()
        pipe.incr(key)
        pipe.expire(key, ex_seconds, nx=True)  # nx=True: solo si no tiene TTL
        results = pipe.execute()
        return results[0]
    except Exception:
        return -1


def redis_ttl(key: str) -> int:
    """Retorna TTL en segundos, -2 si no existe, -1 si sin TTL."""
    c = _get_client()
    if not c:
        return -2
    try:
        return c.ttl(key)
    except Exception:
        return -2


def redis_sadd(key: str, *members: str, ex: int | None = None) -> int:
    """Agrega miembros a un set. Si ex, setea TTL. Usado para blacklists."""
    c = _get_client()
    if not c:
        return 0
    try:
        count = c.sadd(key, *members)
        if ex:
            c.expire(key, ex, nx=True)
        return count
    except Exception:
        return 0


def redis_sismember(key: str, member: str) -> bool:
    c = _get_client()
    if not c:
        return False
    try:
        return bool(c.sismember(key, member))
    except Exception:
        return False


# ── Rate limiting helper ──────────────────────────────────────

def check_rate_limit_redis(
    key: str,
    max_count: int,
    window_seconds: int = 3600,
    strict: bool = False,
) -> tuple[bool, int]:
    """
    Verifica rate limit usando Redis INCR.
    Retorna (allowed: bool, current_count: int).

    Si Redis no disponible:
      - strict=False (default): permite — DB hará el check secundario
      - strict=True: bloquea — usado para endpoints críticos (login, AI, register)
        cuando no se puede confiar en un fallback más lento
    """
    count = redis_incr(key, ex_seconds=window_seconds)
    if count == -1:
        if strict:
            logger.warning("Redis no disponible — bloqueando por strict rate limit: %s", key)
            return False, 0
        return True, 0
    allowed = count <= max_count
    return allowed, count


# ── Cache helper ─────────────────────────────────────────────

import json as _json


def cache_get(key: str) -> Any | None:
    """GET y deserializar JSON. Retorna None si no existe o no disponible."""
    raw = redis_get(key)
    if raw is None:
        return None
    try:
        return _json.loads(raw)
    except Exception:
        return raw


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """Serializar a JSON y SET con TTL."""
    try:
        return redis_set(key, _json.dumps(value, default=str), ex=ttl_seconds)
    except Exception:
        return False


def cache_invalidate_prefix(prefix: str) -> int:
    """
    Elimina todas las keys con prefijo dado usando SCAN (O(N) seguro en producción).
    KEYS * está prohibido en producción por bloquear el event loop de Redis.
    """
    c = _get_client()
    if not c:
        return 0
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = c.scan(cursor, match=f"{prefix}*", count=100)
            if keys:
                deleted += c.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass
    return deleted
