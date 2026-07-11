"""
Bike split predictor — aerodynamic physics model.

Equation: P = F_aero·v + F_grav·v + F_roll·v
  F_aero  = 0.5 · ρ · CdA · (v + v_wind)²
  F_grav  = m · g · sin(arctan(grad/100))
  F_roll  = Crr · m · g · cos(arctan(grad/100))

Solves for v given P via Newton-Raphson.
For courses with an elevation profile, integrates segment-by-segment.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

G = 9.81  # m/s²


@dataclass
class BikePhysicsParams:
    # Athlete
    weight_kg: float = 62.0
    bike_kg:   float = 8.0
    ftp_w:     float = 240.0
    cda:       float = 0.32    # drag area m²; TT aero: 0.22–0.28, road: 0.30–0.38
    crr:       float = 0.003   # rolling resistance; asfalto: 0.002–0.004

    # Course
    distance_km:     float = 90.0
    elevation_gain_m: float = 800.0
    elevation_loss_m: float = 800.0

    # Environment
    altitude_m:    float = 0.0
    temperature_c: float = 22.0
    wind_ms:       float = 0.0     # positive = headwind

    # Elevation profile: list of (cumulative_km, elevation_m)
    profile: Optional[List[Tuple[float, float]]] = None

    # Pacing
    if_factor: float = 0.75   # Intensity Factor (fraction of FTP)

    @property
    def total_mass_kg(self) -> float:
        return self.weight_kg + self.bike_kg


def _air_density(altitude_m: float, temp_c: float) -> float:
    """International Standard Atmosphere. Returns kg/m³."""
    T     = temp_c + 273.15
    P_atm = 101325.0 * (1.0 - 2.2557e-5 * altitude_m) ** 5.2559
    return P_atm / (287.058 * T)


def _solve_v(power_w: float, gradient_pct: float, rho: float,
             cda: float, crr: float, mass_kg: float, wind_ms: float) -> float:
    """Newton-Raphson: steady-state velocity (m/s) for given conditions."""
    theta  = math.atan(gradient_pct / 100.0)
    F_grav = mass_kg * G * math.sin(theta)
    F_roll = crr * mass_kg * G * math.cos(theta)

    # Initial guess: flat road approximation
    v = max(1.0, min(20.0, (power_w / (0.5 * rho * cda + 1e-9)) ** (1.0 / 3.0)))

    for _ in range(100):
        v_air   = v + wind_ms
        F_aero  = 0.5 * rho * cda * v_air ** 2
        F_total = F_aero + F_grav + F_roll
        f       = F_total * v - power_w
        df      = 0.5 * rho * cda * (3.0 * v_air ** 2) + F_grav + F_roll
        if abs(df) < 1e-12:
            break
        v_new = v - f / df
        v_new = max(0.5, min(22.0, v_new))
        if abs(v_new - v) < 1e-7:
            break
        v = v_new

    return max(0.5, v)


def _segment_power(gradient_pct: float, base_np: float, ftp_w: float) -> float:
    """
    Adjust power target by gradient.
    Racers push harder uphill, soft-pedal descents.
    """
    if   gradient_pct >  5:  return min(base_np * 1.12, ftp_w * 0.88)
    elif gradient_pct >  2:  return base_np * 1.05
    elif gradient_pct < -3:  return base_np * 0.55
    elif gradient_pct < -1:  return base_np * 0.75
    return base_np


def predict_bike(params: BikePhysicsParams) -> dict:
    """
    Main entry point. Returns:
      time_s, avg_speed_kmh, avg_power_w, segments (if profile), method
    """
    rho     = _air_density(params.altitude_m, params.temperature_c)
    base_np = params.ftp_w * params.if_factor

    if params.profile and len(params.profile) >= 2:
        return _predict_profile(params, rho, base_np)
    return _predict_simple(params, rho, base_np)


def _predict_profile(p: BikePhysicsParams, rho: float, base_np: float) -> dict:
    total_time_s  = 0.0
    weighted_psum = 0.0
    segments      = []
    covered_km    = 0.0

    for i in range(len(p.profile) - 1):
        km0, ele0 = p.profile[i]
        km1, ele1 = p.profile[i + 1]
        dist_km   = km1 - km0
        if dist_km <= 0:
            continue

        grad = (ele1 - ele0) / (dist_km * 1000.0) * 100.0
        pwr  = _segment_power(grad, base_np, p.ftp_w)
        v    = _solve_v(pwr, grad, rho, p.cda, p.crr, p.total_mass_kg, p.wind_ms)
        t    = dist_km * 1000.0 / v

        total_time_s  += t
        covered_km    += dist_km
        weighted_psum += pwr * t
        segments.append({
            'km_start':     round(km0, 1),
            'km_end':       round(km1, 1),
            'gradient_pct': round(grad, 1),
            'power_w':      round(pwr),
            'speed_kmh':    round(v * 3.6, 1),
            'time_s':       round(t),
            'elevation_m':  round(ele0),
        })

    # If profile doesn't cover the full race distance, extrapolate at average speed
    if covered_km > 0 and covered_km < p.distance_km * 0.9:
        avg_spd_from_profile = covered_km / (total_time_s / 3600.0)
        remaining_km = p.distance_km - covered_km
        total_time_s += remaining_km / avg_spd_from_profile * 3600.0

    avg_speed = p.distance_km / (total_time_s / 3600.0) if total_time_s > 0 else 0.0
    avg_power = weighted_psum / total_time_s if total_time_s > 0 else base_np

    return {
        'time_s':       total_time_s,
        'avg_speed_kmh': round(avg_speed, 2),
        'avg_power_w':  round(avg_power, 1),
        'np_w':         base_np,
        'if_factor':    p.if_factor,
        'segments':     segments,
        'method':       'profile',
        'rho':          round(rho, 4),
    }


def _predict_simple(p: BikePhysicsParams, rho: float, base_np: float) -> dict:
    """Single-pass using average climb/descent gradient (no profile)."""
    half_km = p.distance_km / 2.0

    if half_km > 0:
        g_up   =  (p.elevation_gain_m / (half_km * 1000.0)) * 100.0
        g_down = -(p.elevation_loss_m / (half_km * 1000.0)) * 100.0
    else:
        g_up = g_down = 0.0

    p_up   = _segment_power(g_up,   base_np, p.ftp_w)
    p_down = _segment_power(g_down, base_np, p.ftp_w)

    v_up   = _solve_v(p_up,   g_up,   rho, p.cda, p.crr, p.total_mass_kg, p.wind_ms)
    v_down = _solve_v(p_down, g_down, rho, p.cda, p.crr, p.total_mass_kg, p.wind_ms)

    t_up   = half_km * 1000.0 / v_up
    t_down = half_km * 1000.0 / v_down
    total  = t_up + t_down

    avg_speed = p.distance_km / (total / 3600.0) if total > 0 else 0.0

    return {
        'time_s':        total,
        'avg_speed_kmh': round(avg_speed, 2),
        'avg_power_w':   round(base_np, 1),
        'np_w':          base_np,
        'if_factor':     p.if_factor,
        'segments':      [],
        'method':        'simple',
        'rho':           round(rho, 4),
    }


# ── Sensitivity helpers ────────────────────────────────────────────────────

def whatif_sweep(base: BikePhysicsParams, param: str, values: list) -> list:
    """
    Sweep one parameter and return list of {param_value, time_s, speed_kmh}.
    param: 'ftp_w' | 'weight_kg' | 'cda' | 'if_factor' | 'wind_ms'
    """
    rows = []
    for val in values:
        kw = {**base.__dict__, param: val, 'profile': base.profile}
        result = predict_bike(BikePhysicsParams(**{k: kw[k] for k in BikePhysicsParams.__dataclass_fields__}))
        rows.append({param: val, 'time_s': result['time_s'], 'speed_kmh': result['avg_speed_kmh']})
    return rows
