"""COACH-VARIANTES: factor de volumen por destino al materializar una asignacion.

Reglas (SPEC BUILD 363):
  - rango 0.5-1.5, default 1.0; el factor se guarda con 2 decimales.
  - duracion de la sesion (min) -> entero, redondeo half-up a 1 min.
  - distancia (km)              -> 1 decimal, half-up a 0.1 km.
  - duracion de cada bloque     -> entero (segundos; minutos si la clave es dur_min), half-up.
  - los % de intensidad (power, val, zone...) y los conteos (repeat) NO se tocan.
  - factor 1.0 (o ausente): no se escribe nada -> fila identica a la de antes.
"""
import json
import math
from types import SimpleNamespace
from typing import Optional

FACTOR_MIN = 0.5
FACTOR_MAX = 1.5

# claves de tiempo (segundos o minutos segun la clave) y de distancia de un bloque
_BLOCK_TIME_KEYS = ("duration", "on_duration", "off_duration", "dur", "dur_min", "duration_sec")
_BLOCK_DIST_KEYS = ("dist_m", "dist")


def _half_up(x: float, ndigits: int = 0) -> float:
    m = 10 ** ndigits
    return math.floor(x * m + 0.5 + 1e-9) / m


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def normalize_factor(f: Optional[float]) -> float:
    """None -> 1.0. Fuera de rango -> ValueError."""
    if f is None:
        return 1.0
    f = round(float(f), 2)
    if not (FACTOR_MIN <= f <= FACTOR_MAX):
        raise ValueError(f"volume_factor debe estar entre {FACTOR_MIN} y {FACTOR_MAX}")
    return f


def validate_factor(f):
    """Validador de pydantic: None pasa; fuera de rango o no finito se rechaza."""
    if f is None:
        return None
    if not _is_num(f) or not math.isfinite(f):
        raise ValueError("volume_factor debe ser un numero")
    return normalize_factor(f)


def scale_minutes(v, f):
    return None if v is None else int(_half_up(v * f, 0))


def scale_km(v, f):
    return None if v is None else _half_up(v * f, 1)


def _scale_block(b, f):
    if not isinstance(b, dict):
        return b
    out = dict(b)
    for k in _BLOCK_TIME_KEYS + _BLOCK_DIST_KEYS:
        if _is_num(out.get(k)):
            out[k] = int(_half_up(out[k] * f, 0))
    # grupos anidados (RepeatGroup y similares)
    for k in ("blocks", "steps", "children"):
        if isinstance(out.get(k), list):
            out[k] = [_scale_block(x, f) for x in out[k]]
    return out


def scale_blocks_json(blocks_json: Optional[str], f: float) -> Optional[str]:
    if not blocks_json:
        return blocks_json
    try:
        data = json.loads(blocks_json)
    except Exception:
        return blocks_json
    if isinstance(data, list):
        data = [_scale_block(b, f) for b in data]
    elif isinstance(data, dict):
        data = _scale_block(data, f)
    return json.dumps(data, ensure_ascii=False)


def apply_volume_factor(row, tpl, factor: Optional[float]) -> None:
    """Escribe en la fila (AssignedWorkout) el factor y los valores escalados.
    Con factor 1.0/None no toca nada (fila identica a la historica)."""
    f = normalize_factor(factor)
    if f == 1.0 or tpl is None:
        return
    row.volume_factor = f
    row.dur_min_scaled = scale_minutes(tpl.dur_min, f)
    row.dist_km_scaled = scale_km(tpl.dist_km, f)
    row.blocks_json_scaled = scale_blocks_json(tpl.blocks_json, f)


def effective_template(row, tpl):
    """Plantilla 'vista' por el atleta: valores escalados de la fila si los hay;
    si no, la plantilla tal cual (mismo objeto -> comportamiento historico)."""
    vf = getattr(row, "volume_factor", None)
    if not _is_num(vf) or vf == 1.0 or tpl is None or not hasattr(tpl, "__table__"):
        return tpl
    d = {c.name: getattr(tpl, c.name) for c in tpl.__table__.columns}
    d["dur_min"] = row.dur_min_scaled if row.dur_min_scaled is not None else tpl.dur_min
    d["dist_km"] = row.dist_km_scaled if row.dist_km_scaled is not None else tpl.dist_km
    d["blocks_json"] = (row.blocks_json_scaled
                        if row.blocks_json_scaled is not None else tpl.blocks_json)
    return SimpleNamespace(**d)
