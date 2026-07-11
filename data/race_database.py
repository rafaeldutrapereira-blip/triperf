"""
Race profile database for the LabX 3-Curve Race Predictor.

Each entry contains:
  - Distances (swim/bike/run in km, T1/T2 in minutes)
  - Elevation profiles (representative, not exact GPS)
  - Swim conditions (water type, current, wetsuit rules, temperature)
  - Typical race-day climate
  - Reference finishing times (2023/2024 results)

Elevation profiles are sampled at consistent intervals for the Plotly chart
and the segment-by-segment bike physics model.
"""

from typing import Dict, Any, List

# ── Helper: generate smooth elevation profile ─────────────────────────────

import math


def _profile_sine(dist_km: float, n_points: int,
                  base_ele: float, gain: float,
                  n_hills: int = 2) -> List[tuple]:
    """
    Generate a representative elevation profile as sinusoidal waves.
    Returns list of (km, elevation_m) tuples.
    """
    pts = []
    for i in range(n_points + 1):
        km  = i * dist_km / n_points
        # Multiple sine waves to simulate rolling terrain
        ele = base_ele + (gain / 2) * (
            0.6 * math.sin(n_hills * math.pi * km / dist_km)
            + 0.4 * math.sin(n_hills * 2 * math.pi * km / dist_km)
        )
        pts.append((round(km, 2), round(ele, 1)))
    return pts


def _profile_mountain(dist_km: float, n_points: int,
                       base_ele: float, peak_gain: float) -> List[tuple]:
    """Single-summit profile (climb out, descend back)."""
    pts = []
    for i in range(n_points + 1):
        km   = i * dist_km / n_points
        frac = km / dist_km
        # Gaussian-shaped hill
        ele  = base_ele + peak_gain * math.exp(-((frac - 0.45) ** 2) / 0.08)
        pts.append((round(km, 2), round(ele, 1)))
    return pts


def _profile_out_back(dist_km: float, n_points: int,
                       base_ele: float, max_gain: float) -> List[tuple]:
    """Out-and-back profile (ascending half, descending half)."""
    pts = []
    for i in range(n_points + 1):
        km   = i * dist_km / n_points
        frac = km / dist_km
        # Triangle wave
        if frac < 0.5:
            ele = base_ele + max_gain * (frac / 0.5)
        else:
            ele = base_ele + max_gain * (1 - (frac - 0.5) / 0.5)
        pts.append((round(km, 2), round(ele, 1)))
    return pts


# ── Race database ─────────────────────────────────────────────────────────

RACE_DB: Dict[str, Any] = {

    # ── Olympic / Sprint ──────────────────────────────────────────────────

    "topman-concon-26": {
        "id":       "topman-concon-26",
        "name":     "TOPMAN Concón 2026",
        "type":     "Olímpico",
        "distance": "olympic",
        "date":     "2026-08-23",
        "location": "Concón, Valparaíso, Chile",
        "flag":     "🇨🇱",
        "org":      "TOPMAN",
        "distances": {"swim": 1.5, "bike": 40.0, "run": 10.0, "t1_min": 2.5, "t2_min": 1.5},
        "swim": {
            "water_type":   "mar",
            "wetsuit":      True,     # water ~12°C Aug — neopreno obligatorio
            "current_ms":   0.1,      # slight favourable
            "water_temp_c": 12.0,
        },
        "bike": {
            "elevation_gain_m": 180,
            "elevation_loss_m": 180,
            "surface": "asfalto",
            "technical": 0.4,
            "profile": _profile_sine(40, 40, 10, 180, 3),
        },
        "run": {
            "elevation_gain_m": 40,
            "elevation_loss_m": 40,
            "surface": "asfalto",
            "laps": 2,
        },
        "climate": {"temp_c": 14, "humidity": 75, "wind_ms": 3.0, "altitude_m": 5},
        "reference_times": {
            "winner_total":    "1:53:12",
            "ag_35_39_winner": "2:05:30",
            "median_total":    "2:25:00",
        },
        "notes": "Playa Amarilla — agua fría 12°C, circuito costero con viento SW habitual.",
    },

    "ftech-sgo-sprint-26": {
        "id":       "ftech-sgo-sprint-26",
        "name":     "FTECH Santiago Sprint",
        "type":     "Sprint",
        "distance": "sprint",
        "date":     "2026-03-15",
        "location": "Santiago, Chile",
        "flag":     "🇨🇱",
        "org":      "FTECH",
        "distances": {"swim": 0.75, "bike": 20.0, "run": 5.0, "t1_min": 2.0, "t2_min": 1.5},
        "swim": {
            "water_type": "lago", "wetsuit": True, "current_ms": 0.0, "water_temp_c": 20.0,
        },
        "bike": {
            "elevation_gain_m": 120, "elevation_loss_m": 120, "surface": "asfalto", "technical": 0.3,
            "profile": _profile_sine(20, 20, 520, 120, 2),
        },
        "run":  {"elevation_gain_m": 30, "elevation_loss_m": 30, "surface": "asfalto", "laps": 1},
        "climate": {"temp_c": 22, "humidity": 40, "wind_ms": 2.0, "altitude_m": 520},
        "reference_times": {
            "winner_total": "0:58:45", "ag_35_39_winner": "1:04:00", "median_total": "1:22:00",
        },
        "notes": "Parque O'Higgins — piscina o lago artificial.",
    },

    # ── 70.3 LATAM ────────────────────────────────────────────────────────

    "im703-pucon-25": {
        "id":       "im703-pucon-25",
        "name":     "Ironman 70.3 Pucón",
        "type":     "70.3",
        "distance": "703",
        "date":     "2025-01-12",
        "location": "Pucón, La Araucanía, Chile",
        "flag":     "🇨🇱",
        "org":      "IRONMAN",
        "distances": {"swim": 1.9, "bike": 90.0, "run": 21.1, "t1_min": 4.0, "t2_min": 3.0},
        "swim": {
            "water_type":   "lago",
            "wetsuit":      True,
            "current_ms":   0.0,
            "water_temp_c": 22.0,
        },
        "bike": {
            "elevation_gain_m": 1050,
            "elevation_loss_m": 1050,
            "surface":    "asfalto",
            "technical":  0.6,
            "profile": _profile_mountain(90, 90, 220, 850),
        },
        "run": {
            "elevation_gain_m": 130,
            "elevation_loss_m": 130,
            "surface": "asfalto",
            "laps": 2,
        },
        "climate": {"temp_c": 23, "humidity": 55, "wind_ms": 2.5, "altitude_m": 227},
        "reference_times": {
            "winner_total":    "3:51:08",
            "ag_35_39_winner": "4:25:00",
            "median_total":    "5:20:00",
        },
        "notes": "Lago Villarrica. Ciclismo exigente con subida al volcán. Pucón es el IM70.3 más icónico de Sudamérica.",
    },

    "im703-lima-26": {
        "id":       "im703-lima-26",
        "name":     "Ironman 70.3 Lima",
        "type":     "70.3",
        "distance": "703",
        "date":     "2026-05-10",
        "location": "Lima, Perú",
        "flag":     "🇵🇪",
        "org":      "IRONMAN",
        "distances": {"swim": 1.9, "bike": 90.0, "run": 21.1, "t1_min": 3.5, "t2_min": 2.5},
        "swim": {
            "water_type": "mar", "wetsuit": False, "current_ms": -0.1, "water_temp_c": 18.0,
        },
        "bike": {
            "elevation_gain_m": 420,
            "elevation_loss_m": 420,
            "surface":   "asfalto",
            "technical": 0.3,
            "profile": _profile_sine(90, 90, 30, 420, 2),
        },
        "run":  {"elevation_gain_m": 60, "elevation_loss_m": 60, "surface": "asfalto", "laps": 3},
        "climate": {"temp_c": 19, "humidity": 80, "wind_ms": 4.0, "altitude_m": 30},
        "reference_times": {
            "winner_total": "3:47:15", "ag_35_39_winner": "4:18:00", "median_total": "5:10:00",
        },
        "notes": "Chorrillos. Corriente sur Humboldt — agua fría. Circuito costero con brisa marina.",
    },

    "im703-bsas-26": {
        "id":       "im703-bsas-26",
        "name":     "Ironman 70.3 Buenos Aires",
        "type":     "70.3",
        "distance": "703",
        "date":     "2026-03-22",
        "location": "Buenos Aires, Argentina",
        "flag":     "🇦🇷",
        "org":      "IRONMAN",
        "distances": {"swim": 1.9, "bike": 90.0, "run": 21.1, "t1_min": 3.0, "t2_min": 2.5},
        "swim": {
            "water_type": "rio", "wetsuit": False, "current_ms": 0.3, "water_temp_c": 24.0,
        },
        "bike": {
            "elevation_gain_m": 180,
            "elevation_loss_m": 180,
            "surface":   "asfalto",
            "technical": 0.2,
            "profile": _profile_sine(90, 90, 5, 180, 4),
        },
        "run":  {"elevation_gain_m": 30, "elevation_loss_m": 30, "surface": "asfalto", "laps": 3},
        "climate": {"temp_c": 28, "humidity": 70, "wind_ms": 5.5, "altitude_m": 10},
        "reference_times": {
            "winner_total": "3:44:30", "ag_35_39_winner": "4:10:00", "median_total": "5:05:00",
        },
        "notes": "Río de La Plata — corriente favorable. Circuito plano, ideal para marcas personales.",
    },

    "im703-cancun-26": {
        "id":       "im703-cancun-26",
        "name":     "Ironman 70.3 Cancún",
        "type":     "70.3",
        "distance": "703",
        "date":     "2026-09-27",
        "location": "Cancún, Quintana Roo, México",
        "flag":     "🇲🇽",
        "org":      "IRONMAN",
        "distances": {"swim": 1.9, "bike": 90.0, "run": 21.1, "t1_min": 3.5, "t2_min": 2.5},
        "swim": {
            "water_type": "mar", "wetsuit": False, "current_ms": 0.15, "water_temp_c": 29.0,
        },
        "bike": {
            "elevation_gain_m": 280,
            "elevation_loss_m": 280,
            "surface":   "asfalto",
            "technical": 0.25,
            "profile": _profile_sine(90, 90, 5, 280, 3),
        },
        "run":  {"elevation_gain_m": 40, "elevation_loss_m": 40, "surface": "asfalto", "laps": 3},
        "climate": {"temp_c": 31, "humidity": 80, "wind_ms": 4.0, "altitude_m": 5},
        "reference_times": {
            "winner_total": "3:52:00", "ag_35_39_winner": "4:22:00", "median_total": "5:18:00",
        },
        "notes": "Calor y humedad extremos. Factor termogénico crítico para el run.",
    },

    "im703-cartagena-26": {
        "id":       "im703-cartagena-26",
        "name":     "Ironman 70.3 Cartagena",
        "type":     "70.3",
        "distance": "703",
        "date":     "2026-11-15",
        "location": "Cartagena de Indias, Colombia",
        "flag":     "🇨🇴",
        "org":      "IRONMAN",
        "distances": {"swim": 1.9, "bike": 90.0, "run": 21.1, "t1_min": 3.5, "t2_min": 2.5},
        "swim": {
            "water_type": "mar", "wetsuit": False, "current_ms": 0.0, "water_temp_c": 28.0,
        },
        "bike": {
            "elevation_gain_m": 320,
            "elevation_loss_m": 320,
            "surface": "asfalto",
            "technical": 0.3,
            "profile": _profile_sine(90, 90, 5, 320, 3),
        },
        "run":  {"elevation_gain_m": 50, "elevation_loss_m": 50, "surface": "asfalto", "laps": 2},
        "climate": {"temp_c": 32, "humidity": 85, "wind_ms": 5.0, "altitude_m": 5},
        "reference_times": {
            "winner_total": "3:58:00", "ag_35_39_winner": "4:28:00", "median_total": "5:22:00",
        },
        "notes": "Ciudad amurallada. El calor y humedad del Caribe son el factor determinante.",
    },

    "im703-vitoria-26": {
        "id":       "im703-vitoria-26",
        "name":     "Ironman 70.3 Vitória",
        "type":     "70.3",
        "distance": "703",
        "date":     "2026-05-31",
        "location": "Vitória, Espírito Santo, Brasil",
        "flag":     "🇧🇷",
        "org":      "IRONMAN",
        "distances": {"swim": 1.9, "bike": 90.0, "run": 21.1, "t1_min": 3.5, "t2_min": 2.5},
        "swim": {
            "water_type": "mar", "wetsuit": False, "current_ms": 0.0, "water_temp_c": 26.0,
        },
        "bike": {
            "elevation_gain_m": 1240,
            "elevation_loss_m": 1240,
            "surface":   "asfalto",
            "technical": 0.75,
            "profile": _profile_mountain(90, 90, 10, 950),
        },
        "run":  {"elevation_gain_m": 150, "elevation_loss_m": 150, "surface": "asfalto", "laps": 2},
        "climate": {"temp_c": 26, "humidity": 75, "wind_ms": 3.0, "altitude_m": 10},
        "reference_times": {
            "winner_total": "3:55:00", "ag_35_39_winner": "4:30:00", "median_total": "5:28:00",
        },
        "notes": "Uno de los 70.3 más duros de Brasil por la altimetría. Fuerte en ciclismo.",
    },

    # ── IRONMAN Full ──────────────────────────────────────────────────────

    "im-cozumel-25": {
        "id":       "im-cozumel-25",
        "name":     "Ironman Cozumel",
        "type":     "Ironman",
        "distance": "ironman",
        "date":     "2025-11-23",
        "location": "Cozumel, Quintana Roo, México",
        "flag":     "🇲🇽",
        "org":      "IRONMAN",
        "distances": {"swim": 3.8, "bike": 180.0, "run": 42.2, "t1_min": 5.0, "t2_min": 3.5},
        "swim": {
            "water_type": "mar", "wetsuit": False, "current_ms": 0.5, "water_temp_c": 28.0,
        },
        "bike": {
            "elevation_gain_m": 420,
            "elevation_loss_m": 420,
            "surface":   "asfalto",
            "technical": 0.2,
            "profile": _profile_sine(180, 180, 5, 420, 4),
        },
        "run":  {"elevation_gain_m": 60, "elevation_loss_m": 60, "surface": "asfalto", "laps": 3},
        "climate": {"temp_c": 29, "humidity": 78, "wind_ms": 5.0, "altitude_m": 5},
        "reference_times": {
            "winner_total": "7:41:15", "ag_35_39_winner": "9:12:00", "median_total": "11:30:00",
        },
        "notes": "Corriente del Canal Cozumel (+0.5 m/s) — natación muy rápida. Circuito plano; marcas mundiales.",
    },

    "im-chile-26": {
        "id":       "im-chile-26",
        "name":     "Ironman Chile",
        "type":     "Ironman",
        "distance": "ironman",
        "date":     "2026-12-06",
        "location": "Pucón, La Araucanía, Chile",
        "flag":     "🇨🇱",
        "org":      "IRONMAN",
        "distances": {"swim": 3.8, "bike": 180.0, "run": 42.2, "t1_min": 5.0, "t2_min": 4.0},
        "swim": {
            "water_type": "lago", "wetsuit": True, "current_ms": 0.0, "water_temp_c": 22.0,
        },
        "bike": {
            "elevation_gain_m": 1900,
            "elevation_loss_m": 1900,
            "surface":   "asfalto",
            "technical": 0.7,
            "profile": _profile_mountain(180, 180, 220, 1600),
        },
        "run":  {"elevation_gain_m": 260, "elevation_loss_m": 260, "surface": "asfalto", "laps": 4},
        "climate": {"temp_c": 22, "humidity": 50, "wind_ms": 3.0, "altitude_m": 227},
        "reference_times": {
            "winner_total": "8:08:00", "ag_35_39_winner": "9:45:00", "median_total": "12:00:00",
        },
        "notes": "Full Ironman en Pucón — uno de los más duros de LATAM por la altimetría.",
    },

    # ── PTO / World Triathlon ─────────────────────────────────────────────

    "pto-us-open-25": {
        "id":       "pto-us-open-25",
        "name":     "PTO US Open",
        "type":     "100km",
        "distance": "703",
        "date":     "2025-08-03",
        "location": "Milwaukee, WI, EEUU",
        "flag":     "🇺🇸",
        "org":      "PTO",
        "distances": {"swim": 2.0, "bike": 80.0, "run": 18.0, "t1_min": 3.0, "t2_min": 2.0},
        "swim": {
            "water_type": "lago", "wetsuit": True, "current_ms": 0.0, "water_temp_c": 21.0,
        },
        "bike": {
            "elevation_gain_m": 600,
            "elevation_loss_m": 600,
            "surface": "asfalto",
            "technical": 0.4,
            "profile": _profile_sine(80, 80, 180, 600, 3),
        },
        "run":  {"elevation_gain_m": 80, "elevation_loss_m": 80, "surface": "asfalto", "laps": 2},
        "climate": {"temp_c": 24, "humidity": 65, "wind_ms": 3.0, "altitude_m": 180},
        "reference_times": {
            "winner_total": "3:38:00", "median_total": "4:45:00",
        },
        "notes": "PTO T100 formato — 2km/80km/18km. Circuito espectador-friendly.",
    },
}


# ── Search function ───────────────────────────────────────────────────────

def search_races(query: str, race_type: str = "all") -> List[Dict]:
    """
    Search races by name/location. Optionally filter by type.
    Returns sorted list of matching race dicts.
    """
    q = query.strip().lower()
    results = []
    for race in RACE_DB.values():
        # Type filter
        if race_type != "all" and race.get("distance") != race_type:
            continue
        # Text search
        search_text = " ".join([
            race.get("name", ""),
            race.get("location", ""),
            race.get("org", ""),
            race.get("type", ""),
        ]).lower()
        if not q or q in search_text:
            results.append(race)

    return sorted(results, key=lambda r: r.get("name", ""))


def get_race(race_id: str) -> Dict:
    """Return race profile by ID, or empty dict if not found."""
    return RACE_DB.get(race_id, {})


def all_race_names() -> List[str]:
    """Return list of race names for display."""
    return [r["name"] for r in RACE_DB.values()]


def race_by_name(name: str) -> Dict:
    """Lookup by exact name."""
    for r in RACE_DB.values():
        if r["name"] == name:
            return r
    return {}
