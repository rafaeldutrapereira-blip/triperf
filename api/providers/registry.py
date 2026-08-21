"""
Registry de providers + feature flags (Sprint 50). Ver
docs/plan-multi-brand-wearables.md.

Garmin y Strava ya están en producción y no requieren flag para estar
"habilitados" — Strava ya tiene su propio check de configuración
(`_strava_available()` en strava_routes.py, basado en si están seteadas
las credenciales OAuth). Las marcas nuevas (Wahoo/Polar/Coros/Apple
Health) sí requieren flag explícito, apagado por defecto, hasta que se
implementen y se validen con un usuario real de esa marca.
"""
from __future__ import annotations

import os

# Nombre del provider -> variable de entorno que lo habilita.
# Ausente de este dict == siempre habilitado (caso Garmin/Strava hoy).
_FLAG_ENV_VAR = {
    "wahoo":        "WAHOO_ENABLED",
    "polar":        "POLAR_ENABLED",
    "coros":        "COROS_ENABLED",
    "apple_health": "APPLE_HEALTH_ENABLED",
}

# Providers que ya existen implementados (aunque el flag esté apagado,
# no tiene sentido reportarlos como "disponibles" si ni siquiera hay
# código). Wahoo/Polar/Coros/Apple Health se agregan acá recién cuando
# su Sprint correspondiente (52-55) los implemente de verdad.
_IMPLEMENTED_PROVIDERS = {"garmin", "strava"}


def is_provider_enabled(name: str) -> bool:
    """True si el provider está implementado Y (no requiere flag O el flag está en 'true')."""
    if name not in _IMPLEMENTED_PROVIDERS:
        return False
    env_var = _FLAG_ENV_VAR.get(name)
    if env_var is None:
        return True
    return os.getenv(env_var, "false").strip().lower() == "true"


def enabled_providers() -> dict[str, bool]:
    """Estado de todos los providers conocidos (implementados o no), para
    que el frontend pueda decidir qué mostrar/ocultar en 'Conexiones'."""
    all_known = _IMPLEMENTED_PROVIDERS | set(_FLAG_ENV_VAR.keys())
    return {name: is_provider_enabled(name) for name in sorted(all_known)}
