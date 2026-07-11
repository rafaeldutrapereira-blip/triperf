"""
Cifrado simétrico Fernet para credenciales sensibles (Garmin passwords).

Generar clave:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

B-03 — Rotación de clave entre deploys:
    Al cambiar FERNET_KEY, setear la anterior en FERNET_KEY_OLD.
    decrypt() intenta la nueva clave primero; si falla, prueba la vieja.
    encrypt() siempre usa la clave actual (re-encripta implícitamente al actualizar credenciales).
"""
from __future__ import annotations
import os
import warnings
from cryptography.fernet import Fernet, MultiFernet, InvalidToken

_raw_key     = os.getenv("FERNET_KEY", "")
_raw_key_old = os.getenv("FERNET_KEY_OLD", "")
_IS_PROD     = os.getenv("APP_ENV", "development") == "production"


def _make_fernet() -> MultiFernet:
    keys = []
    if _raw_key:
        keys.append(Fernet(_raw_key.encode() if isinstance(_raw_key, str) else _raw_key))
    if _raw_key_old:
        try:
            keys.append(Fernet(_raw_key_old.encode() if isinstance(_raw_key_old, str) else _raw_key_old))
        except Exception:
            pass

    if not keys:
        if _IS_PROD:
            raise RuntimeError(
                "FERNET_KEY no configurada en producción. "
                "La aplicación no puede arrancar sin esta variable de entorno. "
                "Generar con: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        tmp = Fernet.generate_key()
        keys.append(Fernet(tmp))
        warnings.warn(
            "FERNET_KEY no configurada — usando clave temporal efímera. "
            "Las credenciales Garmin NO sobrevivirán un reinicio del servidor. "
            "NUNCA usar en producción. Configura FERNET_KEY en .env.",
            RuntimeWarning, stacklevel=3,
        )
    return MultiFernet(keys)


_fernet = _make_fernet()


def encrypt(plain: str | None) -> str | None:
    """Cifra con la clave activa (FERNET_KEY). Devuelve None si la entrada es None/vacía."""
    if not plain:
        return None
    return _fernet.encrypt(plain.encode()).decode()


def decrypt(token: str | None) -> str | None:
    """
    Descifra probando la clave activa primero, luego FERNET_KEY_OLD (rotación).
    Devuelve None si falla o si la entrada es None.
    """
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return None


def is_encrypted(value: str | None) -> bool:
    """Heurística: los tokens Fernet empiezan con 'gAA' (base64 de un header específico)."""
    return bool(value and value.startswith("gAA"))


def encrypt_if_plain(value: str | None) -> str | None:
    """Cifra solo si el valor no está ya cifrado. Útil para migraciones."""
    if not value:
        return None
    if is_encrypted(value):
        return value
    return encrypt(value)


def decrypt_credential(stored: str | None) -> str | None:
    """
    Lee una credencial que puede estar cifrada (Fernet) o en texto plano (legacy).
    Si está en texto plano, devuelve el valor directamente — el caller debe
    llamar a encrypt_if_plain() y persistir el resultado para migrar.
    """
    if not stored:
        return None
    if is_encrypted(stored):
        return decrypt(stored)
    return stored  # legacy plaintext — caller es responsable de migrar
