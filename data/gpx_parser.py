"""
GPX parser for custom race course profiles.

Extracts:
  - Elevation profile as (cumulative_km, elevation_m) list for the bike physics model
  - Total distance, elevation gain/loss, and gradient statistics
  - Swim/run segment distances (if the file has multiple tracks)

Supports GPX 1.1. Downsamples to ≤400 points for chart performance.
"""

import xml.etree.ElementTree as ET
import math
from typing import List, Tuple, Dict, Optional

# GPX namespaces
_NS = {
    "gpx":  "http://www.topografix.com/GPX/1/1",
    "gpx10":"http://www.topografix.com/GPX/1/0",
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _detect_ns(root: ET.Element) -> str:
    tag = root.tag
    if "1/1" in tag:
        return "gpx"
    return "gpx10"


def _parse_trkpts(root: ET.Element, ns_key: str) -> List[dict]:
    """Extract all trackpoints with lat, lon, ele."""
    ns  = _NS[ns_key]
    pts = []
    for tp in root.findall(f".//{{{ns}}}trkpt"):
        try:
            lat = float(tp.get("lat"))
            lon = float(tp.get("lon"))
        except (TypeError, ValueError):
            continue
        ele_el = tp.find(f"{{{ns}}}ele")
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else 0.0
        pts.append({"lat": lat, "lon": lon, "ele": ele})
    return pts


def _smooth_elevation(eles: List[float], window: int = 5) -> List[float]:
    """Simple moving-average smoother to remove GPS noise."""
    out = []
    for i, e in enumerate(eles):
        lo = max(0, i - window // 2)
        hi = min(len(eles), i + window // 2 + 1)
        out.append(sum(eles[lo:hi]) / (hi - lo))
    return out


def _downsample(pts: List[dict], max_pts: int = 400) -> List[dict]:
    if len(pts) <= max_pts:
        return pts
    step = max(1, len(pts) // max_pts)
    return pts[::step]


def parse_gpx_bytes(gpx_bytes: bytes) -> Dict:
    """
    Parse raw GPX bytes and return a course profile dict.

    Returns:
      {
        distance_km: float,
        elevation_gain_m: float,
        elevation_loss_m: float,
        avg_gradient_pct: float,
        profile: [(cumulative_km, elevation_m), ...],   ← for bike physics model
        raw_pts: [{'lat','lon','ele'}, ...],             ← for Plotly map
        stats: {max_ele, min_ele, n_pts, ...},
      }
    """
    try:
        root = ET.fromstring(gpx_bytes)
    except ET.ParseError as e:
        raise ValueError(f"GPX parse error: {e}")

    ns_key = _detect_ns(root)
    pts    = _parse_trkpts(root, ns_key)

    if len(pts) < 2:
        raise ValueError("GPX file has fewer than 2 track points.")

    # Smooth elevation
    eles   = _smooth_elevation([p["ele"] for p in pts])
    for i, p in enumerate(pts):
        p["ele"] = eles[i]

    # Compute cumulative distance
    cum_km    = 0.0
    gain      = 0.0
    loss      = 0.0
    profile   = [(0.0, pts[0]["ele"])]

    for i in range(1, len(pts)):
        d  = _haversine_m(pts[i-1]["lat"], pts[i-1]["lon"],
                           pts[i]["lat"],   pts[i]["lon"])
        de = pts[i]["ele"] - pts[i-1]["ele"]
        cum_km += d / 1000.0
        if de > 0:
            gain += de
        else:
            loss += abs(de)
        profile.append((round(cum_km, 3), round(pts[i]["ele"], 1)))

    # Downsample profile for chart/model (keep ≤400 pts)
    if len(profile) > 400:
        step = max(1, len(profile) // 400)
        profile = profile[::step]
        # Always include last point
        if profile[-1] != (round(cum_km, 3), round(pts[-1]["ele"], 1)):
            profile.append((round(cum_km, 3), round(pts[-1]["ele"], 1)))

    avg_grad = (gain / (cum_km * 10)) if cum_km > 0 else 0.0  # %

    return {
        "distance_km":      round(cum_km, 2),
        "elevation_gain_m": round(gain, 1),
        "elevation_loss_m": round(loss, 1),
        "avg_gradient_pct": round(avg_grad, 2),
        "profile":          profile,
        "raw_pts":          _downsample(pts, 600),
        "stats": {
            "max_ele_m":   round(max(p["ele"] for p in pts), 1),
            "min_ele_m":   round(min(p["ele"] for p in pts), 1),
            "n_pts_raw":   len(pts),
            "n_pts_profile": len(profile),
        },
    }


def gpx_to_race_dict(gpx_bytes: bytes, name: str = "Carrera Custom",
                      race_type: str = "703") -> dict:
    """
    Wrap parse_gpx_bytes into a race_database-compatible dict
    so it can be used directly in the predictor.
    """
    parsed = parse_gpx_bytes(gpx_bytes)
    dist   = parsed["distance_km"]

    dist_map = {
        "sprint":  {"swim": 0.75, "bike": 20.0,  "run": 5.0,  "t1_min": 2.0, "t2_min": 1.5},
        "olympic": {"swim": 1.5,  "bike": 40.0,  "run": 10.0, "t1_min": 2.5, "t2_min": 1.5},
        "703":     {"swim": 1.9,  "bike": 90.0,  "run": 21.1, "t1_min": 4.0, "t2_min": 3.0},
        "ironman": {"swim": 3.8,  "bike": 180.0, "run": 42.2, "t1_min": 5.0, "t2_min": 4.0},
    }
    distances = dist_map.get(race_type, dist_map["703"])

    # Always use GPX distance for the bike segment (it IS the course)
    if dist > 3:
        distances["bike"] = round(dist, 1)

    return {
        "id":       "custom-gpx",
        "name":     name,
        "type":     race_type.upper(),
        "distance": race_type,
        "date":     "",
        "location": "Custom GPX",
        "flag":     "📍",
        "org":      "Custom",
        "distances": distances,
        "swim": {"water_type": "lago", "wetsuit": True, "current_ms": 0.0, "water_temp_c": 22.0},
        "bike": {
            "elevation_gain_m": parsed["elevation_gain_m"],
            "elevation_loss_m": parsed["elevation_loss_m"],
            "surface":   "asfalto",
            "technical": 0.5,
            "profile":   parsed["profile"],
        },
        "run":     {"elevation_gain_m": 0, "elevation_loss_m": 0, "surface": "asfalto", "laps": 1},
        "climate": {"temp_c": 22, "humidity": 60, "wind_ms": 0, "altitude_m": 0},
        "reference_times": {},
        "notes":   f"GPX importado — {parsed['distance_km']:.1f} km, D+ {parsed['elevation_gain_m']:.0f}m",
        "_gpx_parsed": parsed,
    }
