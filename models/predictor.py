"""
Triathlon race time predictor.

Combines:
1. Riegel formula with sport-specific exponents and cumulative fatigue.
2. FTP/threshold-based physics model for bike split.
3. Post-bike run degradation model.
4. VO2Max Daniels' VDOT estimation.
5. Historical regression (if race data available).
"""

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from utils.formulas import (
    DISTANCES, RECOMMENDED_IF,
    riegel_time, predict_bike_time, predict_swim_time,
    run_fatigue_factor, vo2_to_pace_sec_km,
    fmt_time, _fmt,
)


@dataclass
class AthleteProfile:
    # Physiological thresholds
    ftp_w: float                       # Functional Threshold Power (watts)
    threshold_run_sec_km: float        # Threshold run pace (sec/km)
    threshold_swim_sec_100m: float     # CSS (sec/100m)
    vo2max_run: float = 50.0
    vo2max_bike: float = 52.0
    weight_kg: float = 70.0
    # Best recent performances (sec) for Riegel calibration
    best_1500m_swim_sec: Optional[float] = None
    best_40k_bike_sec: Optional[float]  = None
    best_10k_run_sec: Optional[float]   = None
    # Training load (last 12 weeks)
    weekly_swim_km: float = 10.0
    weekly_bike_km: float = 200.0
    weekly_run_km: float  = 50.0


@dataclass
class SplitPrediction:
    discipline: str
    distance_m: float
    time_sec: float
    pace_display: str   # "X:XX/km", "X:XX/100m", or "XX.X km/h"
    target_if: Optional[float] = None
    target_power: Optional[float] = None
    notes: str = ""

    @property
    def time_display(self) -> str:
        return fmt_time(self.time_sec)


@dataclass
class RacePrediction:
    distance_key: str
    swim: SplitPrediction
    t1: SplitPrediction
    bike: SplitPrediction
    t2: SplitPrediction
    run: SplitPrediction
    total_sec: float
    method: str = "hybrid"

    @property
    def total_display(self) -> str:
        return fmt_time(self.total_sec)

    def to_dict(self) -> dict:
        return {
            "Discipline": ["SWIM", "T1", "BIKE", "T2", "RUN", "TOTAL"],
            "Distance":   [
                f"{self.swim.distance_m:.0f}m",
                "—", f"{self.bike.distance_m/1000:.0f}km",
                "—", f"{self.run.distance_m/1000:.1f}km", "—"
            ],
            "Time":       [
                self.swim.time_display, self.t1.time_display,
                self.bike.time_display, self.t2.time_display,
                self.run.time_display, self.total_display
            ],
            "Pace / Watts": [
                self.swim.pace_display, "—",
                self.bike.pace_display, "—",
                self.run.pace_display, "—"
            ],
            "IF / Notes": [
                self.swim.notes, "—",
                f"IF {self.bike.target_if:.2f}" if self.bike.target_if else "—",
                "—", self.run.notes, "—"
            ],
        }


class TriathlonPredictor:
    """
    Hybrid predictor: uses physics/physiology model as primary,
    Riegel formula as secondary, and blends both with a configurable weight.
    Falls back to pure Riegel when athlete has race results.
    """

    def __init__(self, profile: AthleteProfile, riegel_weight: float = 0.35):
        self.p = profile
        self.riegel_weight = riegel_weight   # 0 = pure physics, 1 = pure Riegel

    # ------------------------------------------------------------------
    # Swim prediction
    # ------------------------------------------------------------------

    def _predict_swim(self, distance_m: float, distance_key: str) -> SplitPrediction:
        rec_fraction = {"sprint": 0.96, "olympic": 0.94, "703": 0.90, "ironman": 0.85}
        frac = rec_fraction[distance_key]
        pace_sec = self.p.threshold_swim_sec_100m / frac   # slower than CSS
        time_physics = predict_swim_time(distance_m, self.p.threshold_swim_sec_100m, frac)

        time_riegel = None
        if self.p.best_1500m_swim_sec:
            time_riegel = riegel_time(1500, self.p.best_1500m_swim_sec, distance_m, "swim")

        time_sec = self._blend(time_physics, time_riegel)
        actual_pace = (time_sec / distance_m) * 100

        return SplitPrediction(
            discipline="SWIM",
            distance_m=distance_m,
            time_sec=time_sec,
            pace_display=f"{_fmt_pace(actual_pace)}/100m",
            notes=f"~{frac*100:.0f}% CSS",
        )

    # ------------------------------------------------------------------
    # Bike prediction
    # ------------------------------------------------------------------

    def _predict_bike(self, distance_m: float, distance_key: str) -> SplitPrediction:
        target_if = RECOMMENDED_IF[distance_key]["bike"]
        time_physics = predict_bike_time(
            distance_m, self.p.ftp_w, target_if, self.p.weight_kg
        )

        time_riegel = None
        if self.p.best_40k_bike_sec:
            time_riegel = riegel_time(40_000, self.p.best_40k_bike_sec, distance_m, "bike")

        time_sec = self._blend(time_physics, time_riegel)
        speed_kmh = (distance_m / 1000) / (time_sec / 3600)
        target_np = self.p.ftp_w * target_if

        return SplitPrediction(
            discipline="BIKE",
            distance_m=distance_m,
            time_sec=time_sec,
            pace_display=f"{speed_kmh:.1f} km/h",
            target_if=target_if,
            target_power=round(target_np),
            notes=f"NP target: {target_np:.0f}W",
        )

    # ------------------------------------------------------------------
    # Run prediction
    # ------------------------------------------------------------------

    def _predict_run(self, distance_m: float, distance_key: str,
                     bike_if: float) -> SplitPrediction:
        fatigue = run_fatigue_factor(bike_if, distance_key)
        degraded_pace = self.p.threshold_run_sec_km * fatigue

        # VO2Max check: ensure pace isn't faster than aerobic capacity
        vo2_pace = vo2_to_pace_sec_km(self.p.vo2max_run, 0.88)
        final_pace = max(degraded_pace, vo2_pace * RECOMMENDED_IF[distance_key]["run_rtss_factor"])

        time_physics = (distance_m / 1000) * final_pace

        time_riegel = None
        if self.p.best_10k_run_sec:
            time_riegel = riegel_time(10_000, self.p.best_10k_run_sec, distance_m, "run")
            # Apply fatigue factor to Riegel too
            if time_riegel:
                time_riegel *= fatigue

        time_sec = self._blend(time_physics, time_riegel)
        actual_pace = time_sec / (distance_m / 1000)

        return SplitPrediction(
            discipline="RUN",
            distance_m=distance_m,
            time_sec=time_sec,
            pace_display=f"{_fmt_pace(actual_pace)}/km",
            notes=f"Fatigue ×{fatigue:.2f}",
        )

    # ------------------------------------------------------------------
    # Full race prediction
    # ------------------------------------------------------------------

    def predict(self, distance_key: str) -> RacePrediction:
        d = DISTANCES[distance_key]

        swim = self._predict_swim(d["swim"], distance_key)
        bike = self._predict_bike(d["bike"], distance_key)
        run  = self._predict_run(d["run"], distance_key, bike.target_if or RECOMMENDED_IF[distance_key]["bike"])

        t1 = SplitPrediction("T1", 0, d["t1"], "—")
        t2 = SplitPrediction("T2", 0, d["t2"], "—")

        total = swim.time_sec + t1.time_sec + bike.time_sec + t2.time_sec + run.time_sec

        return RacePrediction(
            distance_key=distance_key,
            swim=swim, t1=t1, bike=bike, t2=t2, run=run,
            total_sec=total,
        )

    def predict_all(self) -> dict[str, RacePrediction]:
        return {k: self.predict(k) for k in DISTANCES}

    # ------------------------------------------------------------------
    # Sensitivity analysis: what-if on FTP/threshold improvement
    # ------------------------------------------------------------------

    def sensitivity_table(self, distance_key: str, ftp_range: range = range(-20, 25, 5)) -> pd.DataFrame:
        rows = []
        base = self.predict(distance_key)
        for delta in ftp_range:
            p_mod = AthleteProfile(**{**self.p.__dict__, "ftp_w": self.p.ftp_w + delta})
            pred  = TriathlonPredictor(p_mod, self.riegel_weight).predict(distance_key)
            delta_sec = pred.total_sec - base.total_sec
            rows.append({
                "FTP (W)":      p_mod.ftp_w,
                "Total":        pred.total_display,
                "Δ vs Base":    f"{'+' if delta_sec >= 0 else ''}{fmt_time(abs(delta_sec))} {'slower' if delta_sec>0 else 'faster'}",
                "Bike split":   pred.bike.time_display,
                "Run split":    pred.run.time_display,
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------

    def _blend(self, physics: float, riegel: Optional[float]) -> float:
        if riegel is None:
            return physics
        return physics * (1 - self.riegel_weight) + riegel * self.riegel_weight


def _fmt_pace(sec: float) -> str:
    m = int(sec) // 60
    s = int(sec) % 60
    return f"{m}:{s:02d}"
