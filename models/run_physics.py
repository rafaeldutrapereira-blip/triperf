"""
Run split predictor.

Models applied in sequence:
1. Minetti (2002) energy-cost model for grade adjustments.
2. Bärtsch & Saltin altitude VO2max penalty (>1500 m a.s.l.).
3. Surface factor (asfalto/trail/mixto).
4. Temperature factor (optimal 10–15 °C; degrades above 25 °C).
5. Post-bike fatigue model based on bike Intensity Factor.
6. Riegel formula cross-check (optional).

Minetti 2002: Cmet(i) = (155.4i⁵ − 30.4i⁴ − 43.3i³ + 46.3i² + 19.5i + 3.6) / 3.6
  where i = gradient in m/m.  Cmet(0) = 1.0 (flat normalised).
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class RunPhysicsParams:
    # Athlete
    threshold_pace_s_km: float = 300.0  # Lactate threshold pace (sec/km)
    weight_kg:           float = 62.0

    # Course
    distance_km:      float = 21.1
    elevation_gain_m: float = 120.0
    elevation_loss_m: float = 120.0
    surface:          str   = "asfalto"   # "asfalto" | "trail" | "mixto"

    # Environment
    altitude_m:    float = 0.0
    temperature_c: float = 22.0

    # Pacing
    race_fraction: float = 0.95   # fraction of threshold; 70.3 ~0.95, IM ~0.85

    # Post-bike fatigue
    bike_if: float = 0.75   # Intensity Factor of bike split


# ── Core adjustments ──────────────────────────────────────────────────────

def _minetti_cmet(grade_m_per_m: float) -> float:
    """
    Metabolic energy cost relative to flat (Cmet = 1.0 on flat).
    Validated range: i ∈ [−0.45, +0.45].
    """
    i = max(-0.40, min(0.40, grade_m_per_m))
    raw = (155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3
           + 46.3 * i**2 + 19.5 * i + 3.6)
    return max(0.4, raw / 3.6)


def _altitude_factor(altitude_m: float) -> float:
    """VO2max decreases ~1 % per 100 m above 1 500 m (Bärtsch & Saltin 2008)."""
    if altitude_m <= 1500.0:
        return 1.0
    return max(0.70, 1.0 - 0.01 * (altitude_m - 1500.0) / 100.0)


def _surface_factor(surface: str) -> float:
    """Metabolic cost multiplier per surface type."""
    return {"asfalto": 1.00, "mixto": 0.96, "trail": 0.91}.get(surface, 1.00)


def _temperature_factor(temp_c: float) -> float:
    """
    Running performance degrades above the thermoneutral zone (10–15 °C).
    Based on Tucker et al. 2006 and Ely et al. 2007.
    """
    if   temp_c <= 15:  return 1.000
    elif temp_c <= 25:  return 1.000 - 0.002 * (temp_c - 15)
    elif temp_c <= 32:  return 0.980 - 0.004 * (temp_c - 25)
    else:               return 0.952 - 0.007 * (temp_c - 32)


def _post_bike_fatigue(bike_if: float, distance_km: float) -> float:
    """
    Run pace degradation after cycling.
    Based on empirical triathlon data:
      IF 0.70 → ~3 % degradation
      IF 0.80 → ~7 % degradation
    Long runs also accumulate more fatigue.
    """
    if_penalty   = max(0.0, (bike_if - 0.60) * 0.20)   # 0–8 % for IF 0.6–1.0
    dist_penalty = max(0.0, (distance_km - 10) * 0.001) # +0.1 %/km beyond 10 km
    return 1.0 + if_penalty + dist_penalty


def _elevation_factor(gain_m: float, loss_m: float, distance_km: float) -> float:
    """
    Weighted Minetti factor for an out-and-back / net-zero elevation course.
    Splits distance equally into climbing and descending halves.
    """
    if distance_km <= 0:
        return 1.0

    half_dist_m = distance_km * 1000.0 / 2.0
    g_up   =  gain_m / half_dist_m if half_dist_m > 0 else 0.0
    g_down = -loss_m / half_dist_m if half_dist_m > 0 else 0.0

    cmet_up   = _minetti_cmet(g_up)
    cmet_down = _minetti_cmet(g_down)
    return (cmet_up + cmet_down) / 2.0


# ── Main prediction ───────────────────────────────────────────────────────

def predict_run(params: RunPhysicsParams) -> dict:
    """
    Returns:
      time_s, effective_pace_s_km, and breakdown of adjustment factors.
    """
    # 1. Base pace from threshold
    base_pace = params.threshold_pace_s_km / params.race_fraction

    # 2. Elevation (Minetti)
    elev_f = _elevation_factor(params.elevation_gain_m, params.elevation_loss_m,
                                params.distance_km)

    # 3. Altitude
    alt_f  = _altitude_factor(params.altitude_m)

    # 4. Surface
    surf_f = _surface_factor(params.surface)

    # 5. Temperature
    temp_f = _temperature_factor(params.temperature_c)

    # 6. Post-bike fatigue
    fatigue_f = _post_bike_fatigue(params.bike_if, params.distance_km)

    # Effective pace: higher factors = slower
    # altitude / surface / temp SLOW you down → divide (reduce speed)
    # elevation  → Minetti factor > 1 = slower → multiply pace
    # fatigue    → > 1 = slower → multiply pace
    effective_pace = (base_pace
                      * elev_f            # elevation penalty
                      * fatigue_f         # post-bike penalty
                      / alt_f             # altitude O2 benefit if < 1500 m
                      / surf_f            # surface efficiency
                      / temp_f)           # heat penalty

    total_time_s = effective_pace * params.distance_km

    return {
        'time_s':             total_time_s,
        'effective_pace_s_km': effective_pace,
        'base_pace_s_km':     base_pace,
        'factors': {
            'elevation':    round(elev_f,    4),
            'altitude':     round(alt_f,     4),
            'surface':      round(surf_f,    4),
            'temperature':  round(temp_f,    4),
            'fatigue':      round(fatigue_f, 4),
        },
        'elevation_gain_m': params.elevation_gain_m,
        'distance_km':      params.distance_km,
    }


# ── Sensitivity helper ────────────────────────────────────────────────────

def whatif_run_sweep(base: RunPhysicsParams, param: str, values: list) -> list:
    """Sweep one parameter, return [{param, time_s, pace_s_km}, ...]"""
    rows = []
    for val in values:
        kw = {**base.__dict__, param: val}
        result = predict_run(RunPhysicsParams(**kw))
        rows.append({param: val, 'time_s': result['time_s'],
                     'pace_s_km': result['effective_pace_s_km']})
    return rows
