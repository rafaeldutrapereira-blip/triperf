"""Sprint 32 — Training Zones service.

Computes 5-zone models from FTP (bike), threshold pace (run/swim), and max HR.
All zone boundaries follow established sports-science conventions:
  - Bike power: Coggan 5-zone (% FTP)
  - Run/Swim pace: pace-based relative to threshold pace
  - HR: % of max HR (or LTHR-based when LTHR available)
"""
from __future__ import annotations

from typing import Optional
from ..models import PerformanceBenchmark

VALID_SPORTS = {"bike", "run", "swim"}


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_pace_km(sec: int) -> str:
    """Format seconds/km → 'm:ss/km'."""
    if sec <= 0:
        return "—"
    return f"{sec // 60}:{sec % 60:02d}/km"


def _fmt_pace_100m(sec: int) -> str:
    """Format seconds/100m → 'm:ss/100m'."""
    if sec <= 0:
        return "—"
    return f"{sec // 60}:{sec % 60:02d}/100m"


# ── Zone models ───────────────────────────────────────────────────────────────

def bike_power_zones(ftp_watts: int) -> list[dict]:
    """Coggan 5-zone power model based on FTP."""
    if ftp_watts <= 0:
        return []
    bands = [
        (1, "Recuperación Activa",  0,    55,   None,                    "Pedaleo suave, sin esfuerzo"),
        (2, "Resistencia",          55,   75,   "aeróbico prolongado",   "Base aeróbica, conversación posible"),
        (3, "Tempo",                76,   90,   "sweetspot",             "Esfuerzo sostenido, difícil hablar"),
        (4, "Umbral",               91,   105,  "threshold",             "Límite de 60 min, máximo aeróbico"),
        (5, "VO2max / Anaeróbico",  106,  150,  "VO2max",                "Intervalos cortos, 3-8 min máx"),
    ]
    zones = []
    for z, name, lo_pct, hi_pct, alias, desc in bands:
        lo_w = round(ftp_watts * lo_pct / 100) if lo_pct > 0 else 0
        hi_w = round(ftp_watts * hi_pct / 100)
        zones.append({
            "zone":    z,
            "name":    name,
            "alias":   alias,
            "desc":    desc,
            "min_pct": lo_pct,
            "max_pct": hi_pct,
            "min_w":   lo_w,
            "max_w":   hi_w,
            "label":   f"{lo_w}–{hi_w} W" if z < 5 else f"> {lo_w} W",
        })
    return zones


def run_pace_zones(threshold_sec_km: int) -> list[dict]:
    """5-zone pace model for running. Z4 = threshold pace ±5 s/km."""
    if threshold_sec_km <= 0:
        return []
    # Offsets from threshold (positive = slower, negative = faster)
    bands = [
        (1, "Recuperación",   +60, +999, "Muy suave, conversación fácil"),
        (2, "Resistencia",    +30,  +59, "Base aeróbica, cómodo"),
        (3, "Tempo",          +10,  +29, "Esfuerzo moderado-alto"),
        (4, "Umbral",          -5,   +9, "Ritmo máximo sostenible ~60 min"),
        (5, "VO2max",         -30,   -6, "Intervalos cortos, 800-2000m"),
    ]
    zones = []
    for z, name, delta_min, delta_max, desc in bands:
        lo_sec = max(threshold_sec_km + delta_min, 0)
        hi_sec = threshold_sec_km + delta_max
        if z == 1:
            label = f"< {_fmt_pace_km(threshold_sec_km + 60)}"
        elif z == 5:
            label = f"> {_fmt_pace_km(threshold_sec_km - 6)}"
        else:
            label = f"{_fmt_pace_km(hi_sec)} – {_fmt_pace_km(lo_sec)}"
        zones.append({
            "zone":          z,
            "name":          name,
            "desc":          desc,
            "pace_min_str":  _fmt_pace_km(lo_sec),
            "pace_max_str":  _fmt_pace_km(hi_sec),
            "pace_min_sec":  lo_sec,
            "pace_max_sec":  hi_sec,
            "label":         label,
        })
    return zones


def swim_pace_zones(css_sec_100m: int) -> list[dict]:
    """5-zone pace model for swimming. CSS (Critical Swim Speed) = threshold."""
    if css_sec_100m <= 0:
        return []
    # Offsets per 100m from CSS (positive = slower)
    bands = [
        (1, "Recuperación",  +15, +999, "Técnica, aeróbico muy suave"),
        (2, "Resistencia",    +8,  +14, "Aeróbico base, ritmo cómodo"),
        (3, "Umbral bajo",    +3,   +7, "Ritmo moderado sostenible"),
        (4, "CSS / Umbral",   -2,   +2, "Critical Swim Speed, ~400-1500m"),
        (5, "Velocidad",     -15,   -3, "Intervalos, 25-200m"),
    ]
    zones = []
    for z, name, delta_min, delta_max, desc in bands:
        lo_sec = max(css_sec_100m + delta_min, 0)
        hi_sec = css_sec_100m + delta_max
        if z == 1:
            label = f"< {_fmt_pace_100m(css_sec_100m + 15)}"
        elif z == 5:
            label = f"> {_fmt_pace_100m(css_sec_100m - 3)}"
        else:
            label = f"{_fmt_pace_100m(hi_sec)} – {_fmt_pace_100m(lo_sec)}"
        zones.append({
            "zone":          z,
            "name":          name,
            "desc":          desc,
            "pace_min_str":  _fmt_pace_100m(lo_sec),
            "pace_max_str":  _fmt_pace_100m(hi_sec),
            "pace_min_sec":  lo_sec,
            "pace_max_sec":  hi_sec,
            "label":         label,
        })
    return zones


def hr_zones(max_hr: int, lthr: Optional[int] = None) -> list[dict]:
    """5-zone HR model. Uses % of max HR."""
    if max_hr <= 0:
        return []
    pcts = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
    names = ["Recuperación", "Resistencia", "Aeróbico", "Umbral Anaeróbico", "VO2max"]
    descs = [
        "Muy baja intensidad, recuperación activa",
        "Base aeróbica, combustión de grasas",
        "Ritmo de carrera largo, aeróbico",
        "Límite entre aeróbico y anaeróbico",
        "Máximo esfuerzo, VO2max",
    ]
    zones = []
    for i, ((lo, hi), name, desc) in enumerate(zip(pcts, names, descs)):
        lo_bpm = round(max_hr * lo / 100)
        hi_bpm = round(max_hr * hi / 100)
        zones.append({
            "zone":    i + 1,
            "name":    name,
            "desc":    desc,
            "min_pct": lo,
            "max_pct": hi,
            "min_bpm": lo_bpm,
            "max_bpm": hi_bpm,
            "label":   f"{lo_bpm}–{hi_bpm} bpm" if i < 4 else f"> {lo_bpm} bpm",
            "lthr_based": False,
        })

    # If LTHR given, annotate Z4 boundary
    if lthr:
        for z in zones:
            if z["zone"] == 4:
                z["lthr_note"] = f"LTHR: {lthr} bpm (límite aeróbico/anaeróbico)"
                z["lthr_based"] = True

    return zones


# ── Main aggregation ──────────────────────────────────────────────────────────

def compute_zones(benchmark: PerformanceBenchmark) -> dict:
    """Compute all available training zones for a benchmark record."""
    result: dict = {
        "benchmark_id": benchmark.id,
        "athlete_id":   benchmark.athlete_id,
        "sport":        benchmark.sport,
        "test_date":    benchmark.test_date,
        "test_type":    benchmark.test_type,
        "power_zones":  None,
        "pace_zones":   None,
        "hr_zones":     None,
        "ftp_watts":    benchmark.ftp_watts,
        "ftp_wkg":      None,
        "threshold_pace_km":   None,
        "threshold_pace_100m": None,
        "max_hr":       benchmark.max_hr,
        "lthr":         benchmark.lthr,
    }

    if benchmark.ftp_watts and benchmark.sport == "bike":
        result["power_zones"] = bike_power_zones(benchmark.ftp_watts)
        if benchmark.weight_kg and benchmark.weight_kg > 0:
            result["ftp_wkg"] = round(benchmark.ftp_watts / benchmark.weight_kg, 2)

    if benchmark.threshold_pace_sec_km and benchmark.sport == "run":
        result["pace_zones"]        = run_pace_zones(benchmark.threshold_pace_sec_km)
        result["threshold_pace_km"] = _fmt_pace_km(benchmark.threshold_pace_sec_km)

    if benchmark.threshold_pace_sec_100m and benchmark.sport == "swim":
        result["pace_zones"]         = swim_pace_zones(benchmark.threshold_pace_sec_100m)
        result["threshold_pace_100m"] = _fmt_pace_100m(benchmark.threshold_pace_sec_100m)

    if benchmark.max_hr:
        result["hr_zones"] = hr_zones(benchmark.max_hr, benchmark.lthr)

    return result


def get_latest_zones(athlete_id: str, sport: str, db) -> Optional[dict]:
    """Return zones from the most recent benchmark for sport, or None."""
    bm = (
        db.query(PerformanceBenchmark)
        .filter(
            PerformanceBenchmark.athlete_id == athlete_id,
            PerformanceBenchmark.sport == sport,
        )
        .order_by(PerformanceBenchmark.test_date.desc())
        .first()
    )
    return compute_zones(bm) if bm else None


def get_all_latest_zones(athlete_id: str, db) -> dict:
    """Return latest zones for all 3 sports in one call."""
    return {
        sport: get_latest_zones(athlete_id, sport, db)
        for sport in ("bike", "run", "swim")
    }
