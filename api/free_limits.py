"""
B11 — Límites del plan Free (basico). Decisión de Rafael:

- 28 días de historial de carga (PMC): se recorta la RESPUESTA, no el cálculo.
  CTL/ATL/TSB se calculan con toda la historia; así el valor de hoy no cambia.
- Plan de entrenamiento: solo la semana actual (lunes a domingo).
- Recuperación: Free no accede (ya lo bloquea el gating de módulo).

Está APAGADO por defecto (env LABX_FREE_LIMITS=1 lo enciende). Se activa con
aviso previo a los usuarios Básico (33 hoy).
"""
from __future__ import annotations

import os
from datetime import date, timedelta

FREE_HISTORY_DAYS = 28
FLAG_ENV = "LABX_FREE_LIMITS"


def free_limits_enabled() -> bool:
    return os.getenv(FLAG_ENV, "0") == "1"


def is_free_athlete(user) -> bool:
    """Atleta en plan basico (BD). Coach y admin no tienen límites."""
    if user is None or user.rol in ("coach", "admin"):
        return False
    return (user.plan_nivel or "basico").lower() in ("basico", "basic")


def applies_to(user) -> bool:
    return free_limits_enabled() and is_free_athlete(user)


def history_cutoff(today: date) -> str:
    """Primera fecha (ISO) visible en el historial Free."""
    return (today - timedelta(days=FREE_HISTORY_DAYS)).isoformat()


def clip_history(rows: list[dict], today: date, key: str = "dt") -> list[dict]:
    cutoff = history_cutoff(today)
    return [r for r in rows if (r.get(key) or "") >= cutoff]


def week_bounds(today: date) -> tuple[str, str]:
    """Lunes y domingo de la semana de `today` (ISO)."""
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


def clip_range(start: str | None, end: str | None, today: date) -> tuple[str, str]:
    """Rango pedido recortado a la semana actual. Si no hay solape, devuelve un rango vacío."""
    w_start, w_end = week_bounds(today)
    s = max(start or w_start, w_start)
    e = min(end or w_end, w_end)
    if s > e:
        # rango vacío: inicio después del fin
        return w_end, w_start
    return s, e
