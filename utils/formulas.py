"""
Physiological and biomechanical formulas for triathlon performance.

References:
- Coggan, A. (2016). Training and Racing with a Power Meter.
- Riegel, P.S. (1981). Athletic Records and Human Endurance. American Scientist.
- Friel, J. (2009). The Triathlete's Training Bible.
- Noakes, T. (2003). Lore of Running.
- Laursen & Rhodes (2001). Factors Affecting Performance in an Ultraendurance Triathlon.
"""

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# TSS (Training Stress Score) by discipline
# ---------------------------------------------------------------------------

def compute_tss_bike(duration_sec: float, power_w: float, ftp_w: float) -> float:
    """
    Coggan's TSS for cycling.
    TSS = (t_sec × NP × IF) / (FTP × 3600) × 100
    """
    if not power_w or not ftp_w or ftp_w == 0:
        return 0.0
    if_factor = power_w / ftp_w
    return (duration_sec * power_w * if_factor) / (ftp_w * 3600) * 100


def compute_rtss_run(duration_sec: float, pace_sec_km: float, threshold_pace_sec_km: float) -> float:
    """
    Running TSS (rTSS) using pace as a proxy for intensity.
    rIF = threshold_pace / current_pace  (slower pace → lower IF)
    rTSS = (duration_h × rIF²) × 100
    """
    if not pace_sec_km or not threshold_pace_sec_km or pace_sec_km == 0:
        return 0.0
    r_if = threshold_pace_sec_km / pace_sec_km
    duration_h = duration_sec / 3600
    return duration_h * (r_if ** 2) * 100


def compute_sstss_swim(duration_sec: float, intensity_factor: float = 0.85) -> float:
    """
    Swim Stress Score (ssTSS). No power meter → use time × IF².
    Default IF=0.85 for moderate aerobic swim.
    """
    duration_h = duration_sec / 3600
    return duration_h * (intensity_factor ** 2) * 100


# ---------------------------------------------------------------------------
# Riegel Formula (modified for triathlon cumulative fatigue)
# ---------------------------------------------------------------------------

RIEGEL_EXPONENT = {
    "swim": 1.06,
    "bike": 1.05,
    "run":  1.07,   # higher exponent due to cumulative fatigue in tri context
}


def riegel_time(reference_distance: float, reference_time_sec: float,
                target_distance: float, sport: str = "run") -> float:
    """
    Riegel endurance formula: T2 = T1 × (D2/D1)^exp
    Returns predicted time in seconds.
    """
    exp = RIEGEL_EXPONENT.get(sport, 1.06)
    return reference_time_sec * (target_distance / reference_distance) ** exp


# ---------------------------------------------------------------------------
# Race distance constants (meters)
# ---------------------------------------------------------------------------

DISTANCES = {
    "sprint": {
        "swim": 750,   "bike": 20_000,  "run": 5_000,
        "t1": 150,     "t2": 60,
    },
    "olympic": {
        "swim": 1_500, "bike": 40_000,  "run": 10_000,
        "t1": 180,     "t2": 90,
    },
    "703": {
        "swim": 1_900, "bike": 90_000,  "run": 21_097,
        "t1": 240,     "t2": 120,
    },
    "ironman": {
        "swim": 3_800, "bike": 180_000, "run": 42_195,
        "t1": 300,     "t2": 180,
    },
}


# ---------------------------------------------------------------------------
# Intensity factor recommendations by distance
# ---------------------------------------------------------------------------

RECOMMENDED_IF = {
    "sprint":  {"bike": 0.85, "run_rtss_factor": 1.00},
    "olympic": {"bike": 0.82, "run_rtss_factor": 0.97},
    "703":     {"bike": 0.78, "run_rtss_factor": 0.92},
    "ironman": {"bike": 0.72, "run_rtss_factor": 0.85},
}


# ---------------------------------------------------------------------------
# Bike time from FTP + IF target
# ---------------------------------------------------------------------------

def predict_bike_time(bike_distance_m: float, ftp_w: float, target_if: float,
                       rider_weight_kg: float, cda: float = 0.32,
                       crr: float = 0.004, rho: float = 1.2) -> float:
    """
    Predict bike split using target NP (NP = FTP × IF).
    Uses a simplified power-velocity model:
        P = (F_aero + F_roll) × v
        F_aero = 0.5 × CdA × ρ × v²
        F_roll = Crr × m × g
    Returns seconds.
    """
    target_np_w = ftp_w * target_if
    g = 9.81
    # Cubic solve: CdA/2*ρ*v³ + Crr*m*g*v = P_target
    # Numerical solution via Newton-Raphson
    v = 10.0  # initial guess m/s
    for _ in range(50):
        f  = 0.5 * cda * rho * v**3 + crr * rider_weight_kg * g * v - target_np_w
        df = 1.5 * cda * rho * v**2 + crr * rider_weight_kg * g
        v -= f / df
        if v < 0:
            v = 1.0
    return bike_distance_m / v   # seconds


# ---------------------------------------------------------------------------
# Run degradation model (post-bike fatigue)
# ---------------------------------------------------------------------------

def run_fatigue_factor(bike_if: float, distance_key: str) -> float:
    """
    Estimate pace degradation on run leg caused by preceding bike effort.
    Based on empirical data from Laursen & Rhodes (2001):
        - Each 0.01 above recommended IF → ~0.5% pace degradation
        - Additional 2-4% for IM vs Olympic due to glycogen depletion
    Returns multiplier > 1 (e.g., 1.05 = 5% slower than standalone run pace).
    """
    base_degradation = {
        "sprint": 1.02,
        "olympic": 1.04,
        "703": 1.08,
        "ironman": 1.15,
    }
    rec_if = RECOMMENDED_IF[distance_key]["bike"]
    if_excess = max(0, bike_if - rec_if)
    extra_degradation = if_excess * 50   # 0.5% per 0.01 IF over target
    return base_degradation[distance_key] * (1 + extra_degradation)


# ---------------------------------------------------------------------------
# VO2Max-based velocity estimate (Daniels formula)
# ---------------------------------------------------------------------------

def vo2_to_pace_sec_km(vo2max: float, fraction: float = 0.90) -> float:
    """
    Estimate threshold pace from VO2Max using Daniels' VDOT tables (approximation).
    fraction: fraction of VO2Max at threshold (~0.88-0.92)
    Returns pace in sec/km.
    """
    # VO2 at target fraction
    vo2_target = vo2max * fraction
    # Velocity (km/min) from VO2 (ml/kg/min): v ≈ (VO2 + 3.5) / 3.5 / 3.5... simplified:
    # More accurate: VO2 = -4.60 + 0.182258*v_m/min + 0.000104*v²  (ACSM running equation)
    # Solving quadratic for v (m/min):
    a = 0.000104
    b = 0.182258
    c = -4.60 - vo2_target
    discriminant = b**2 - 4*a*c
    if discriminant < 0:
        return 300.0
    v_m_per_min = (-b + math.sqrt(discriminant)) / (2 * a)
    v_km_per_min = v_m_per_min / 1000
    return 60 / v_km_per_min   # sec/km


# ---------------------------------------------------------------------------
# Swim pace from CSS (Critical Swim Speed)
# ---------------------------------------------------------------------------

def css_from_time_trials(t_400m_sec: float, t_200m_sec: float) -> float:
    """
    Critical Swim Speed (CSS) = (400 - 200) / (t_400 - t_200) → m/s
    Returns CSS in sec/100m.
    """
    css_m_per_sec = (400 - 200) / (t_400m_sec - t_200m_sec)
    return 100 / css_m_per_sec   # sec/100m


def predict_swim_time(distance_m: float, pace_sec_100m: float, target_fraction: float = 0.95) -> float:
    """Predict swim split at target fraction of CSS."""
    adjusted_pace = pace_sec_100m / target_fraction
    return (distance_m / 100) * adjusted_pace


# ---------------------------------------------------------------------------
# Caloric expenditure
# ---------------------------------------------------------------------------

def caloric_expenditure_bike(power_avg_w: float, duration_sec: float,
                              efficiency: float = 0.23) -> float:
    """Kcal = Power × time / (efficiency × 4184)"""
    return (power_avg_w * duration_sec) / (efficiency * 4184)


def caloric_expenditure_run(weight_kg: float, distance_km: float,
                             efficiency: float = 1.04) -> float:
    """Running: ~1 kcal/kg/km (net), adjusted by efficiency."""
    return weight_kg * distance_km * efficiency


def caloric_expenditure_swim(weight_kg: float, duration_min: float,
                              met: float = 8.0) -> float:
    """MET × weight × hours"""
    return met * weight_kg * (duration_min / 60)


# ---------------------------------------------------------------------------
# SWOLF
# ---------------------------------------------------------------------------

def swolf_to_efficiency_rating(swolf: int) -> str:
    if swolf < 35:    return "Elite"
    elif swolf < 45:  return "Advanced"
    elif swolf < 55:  return "Intermediate"
    else:             return "Beginner"


# ---------------------------------------------------------------------------
# Training zones (7-zone model based on FTP/threshold)
# ---------------------------------------------------------------------------

def power_zones(ftp_w: float) -> dict:
    return {
        "Z1 Active Recovery":  (0,            round(ftp_w * 0.55)),
        "Z2 Endurance":        (round(ftp_w * 0.55), round(ftp_w * 0.75)),
        "Z3 Tempo":            (round(ftp_w * 0.75), round(ftp_w * 0.90)),
        "Z4 Threshold":        (round(ftp_w * 0.90), round(ftp_w * 1.05)),
        "Z5 VO2Max":           (round(ftp_w * 1.05), round(ftp_w * 1.20)),
        "Z6 Anaerobic":        (round(ftp_w * 1.20), round(ftp_w * 1.50)),
        "Z7 Neuromuscular":    (round(ftp_w * 1.50), 9999),
    }


def pace_zones_run(threshold_sec_km: float) -> dict:
    return {
        "Z1 Recovery":   _fmt(threshold_sec_km * 1.35),
        "Z2 Aerobic":    _fmt(threshold_sec_km * 1.20),
        "Z3 Tempo":      _fmt(threshold_sec_km * 1.08),
        "Z4 Threshold":  _fmt(threshold_sec_km * 1.00),
        "Z5 VO2Max":     _fmt(threshold_sec_km * 0.92),
        "Z6 Speed":      _fmt(threshold_sec_km * 0.85),
    }


def _fmt(sec_km: float) -> str:
    m = int(sec_km) // 60
    s = int(sec_km) % 60
    return f"{m}:{s:02d}/km"


def fmt_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h}:{m:02d}:{s:02d}"
