"""
Swim split predictor.

Adjustments applied to the athlete's CSS (Critical Swim Speed):
  - Race fraction:  70.3 races at ~92% CSS; Sprint ~97%; Full IM ~85%
  - Wetsuit bonus:  +3–4 % buoyancy/drag reduction
  - Water type:     Lago=neutral, Mar=±current, Río=current dependent
  - Current:        expressed as m/s ± (positive = favourable)
  - Temperature:    <18°C or >30°C incur a small penalty
  - Altitude:       negligible for swim (open water); included for completeness
"""

from dataclasses import dataclass


@dataclass
class SwimPhysicsParams:
    css_s_100m: float = 110.0     # Critical Swim Speed (sec/100m)

    # Course
    distance_km: float = 1.9     # km

    # Water
    water_type:     str   = "lago"    # "lago" | "mar" | "rio"
    wetsuit:        bool  = True
    current_ms:     float = 0.0       # m/s, positive = tailcurrent (favourable)
    water_temp_c:   float = 22.0

    # Environment
    altitude_m: float = 0.0

    # Pacing
    race_fraction: float = 0.92   # fraction of CSS to race at


# ── Adjustment factors ────────────────────────────────────────────────────

_RACE_FRACTIONS = {
    "sprint":  0.97,
    "olympic": 0.95,
    "703":     0.92,
    "ironman": 0.85,
}

_WATER_TYPE_BASE = {
    "lago": 1.000,   # neutral
    "mar":  0.995,   # slight salt-water buoyancy benefit, offset by chop
    "rio":  1.000,   # current handled separately
}


def _wetsuit_factor(wetsuit: bool, water_temp_c: float) -> float:
    """Wetsuit provides ~3.5 % speed increase via buoyancy + drag reduction."""
    if wetsuit:
        return 1.035
    # Cold water (no wetsuit) → slight stiffness penalty
    if water_temp_c < 18:
        return 0.97
    return 1.00


def _current_factor(current_ms: float, css_s_100m: float) -> float:
    """
    Convert current (m/s) to a speed multiplier on the swimmer.
    Swimmer's base speed ≈ 100 / css_s_100m  m/s.
    """
    base_speed = 100.0 / max(css_s_100m, 60.0)    # m/s
    effective   = base_speed + current_ms
    if effective <= 0:
        effective = 0.1
    return effective / base_speed


def _temperature_factor(temp_c: float) -> float:
    """Small penalty outside the optimal swim range (18–28 °C)."""
    if   temp_c < 15:  return 0.96
    elif temp_c < 18:  return 0.98
    elif temp_c <= 28: return 1.00
    elif temp_c <= 32: return 0.99
    else:              return 0.97


# ── Main prediction ───────────────────────────────────────────────────────

def predict_swim(params: SwimPhysicsParams) -> dict:
    """
    Returns:
      time_s, effective_pace_s_100m, and adjustment factor breakdown.
    """
    # Base pace from CSS + race fraction
    base_pace = params.css_s_100m / params.race_fraction   # sec/100m (slower than CSS)

    # Adjustment factors (> 1 means faster; applied to SPEED, so divide PACE)
    ws_f    = _wetsuit_factor(params.wetsuit, params.water_temp_c)
    curr_f  = _current_factor(params.current_ms, params.css_s_100m)
    wtype_f = _WATER_TYPE_BASE.get(params.water_type, 1.0)
    temp_f  = _temperature_factor(params.water_temp_c)

    # Effective pace: multiply base by slowdown factors, divide by speedup factors
    effective_pace = base_pace / ws_f / curr_f / wtype_f / temp_f

    # Total time
    total_100m     = params.distance_km * 10.0    # number of 100m lengths
    total_time_s   = effective_pace * total_100m

    return {
        'time_s':              total_time_s,
        'effective_pace_s_100m': effective_pace,
        'base_pace_s_100m':    base_pace,
        'factors': {
            'wetsuit':     round(ws_f,    4),
            'current':     round(curr_f,  4),
            'water_type':  round(wtype_f, 4),
            'temperature': round(temp_f,  4),
        },
        'distance_km': params.distance_km,
    }
