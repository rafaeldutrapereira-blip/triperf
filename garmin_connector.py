"""
Garmin Connect data extraction pipeline.
Requires: pip install garminconnect
Uses the unofficial garminconnect library by cyberjunky.
"""

import os
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Module-level singleton — authenticate once per process
_CLIENT = None


def _get_client(email: str = None, password: str = None):
    """
    Return a cached Garmin client, authenticating only when needed.
    Pass email/password explicitly to work in Streamlit context where
    os.getenv() may not reflect values set after process start.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    try:
        from garminconnect import Garmin
    except ImportError:
        raise ImportError("Run: pip install garminconnect")

    _email = email or os.getenv("GARMIN_EMAIL")
    _pw    = password or os.getenv("GARMIN_PASSWORD")
    if not _email or not _pw:
        raise ValueError("Set GARMIN_EMAIL and GARMIN_PASSWORD in your .env file")

    log.info("Authenticating with Garmin Connect...")
    client = Garmin(_email, _pw)
    client.login()
    _CLIENT = client
    log.info("Authentication successful.")
    return _CLIENT


def _cache_path(name: str, start: date, end: date) -> Path:
    return CACHE_DIR / f"{name}_{start}_{end}.json"


def _load_or_fetch(name: str, start: date, end: date, fetch_fn):
    """Simple file-based cache so we don't hammer the Garmin API."""
    path = _cache_path(name, start, end)
    if path.exists():
        log.info("Cache hit: %s", path.name)
        return json.loads(path.read_text())
    data = fetch_fn()
    path.write_text(json.dumps(data, default=str))
    return data


# ---------------------------------------------------------------------------
# Public extraction functions
# ---------------------------------------------------------------------------

def fetch_activities(start: date, end: date) -> pd.DataFrame:
    """Return all activities between start and end as a DataFrame."""
    def _fetch():
        client = _get_client()
        return client.get_activities_by_date(
            start.isoformat(), end.isoformat()
        )

    raw = _load_or_fetch("activities", start, end, _fetch)
    if not raw:
        return pd.DataFrame()

    rows = []
    for a in raw:
        rows.append({
            "activity_id":       a.get("activityId"),
            "name":              a.get("activityName"),
            "sport":             a.get("activityType", {}).get("typeKey", ""),
            "date":              pd.to_datetime(a.get("startTimeLocal")),
            "duration_sec":      a.get("duration", 0),
            "distance_m":        a.get("distance", 0),
            "avg_hr":            a.get("averageHR"),
            "max_hr":            a.get("maxHR"),
            "calories":          a.get("calories"),
            # Cycling
            "avg_power":         a.get("avgPower"),
            "norm_power":        a.get("normPower"),
            "tss":               a.get("trainingStressScore"),
            "if_factor":         a.get("intensityFactor"),
            "ftp":               a.get("ftp"),
            # Running
            "avg_pace_sec_km":   a.get("averageSpeed"),     # m/s → convertido abajo
            "avg_cadence":       a.get("averageRunningCadenceInStepsPerMinute"),
            "vertical_osc_cm":   a.get("avgVerticalOscillation"),
            "ground_contact_ms": a.get("avgGroundContactTime"),
            # Swimming
            "avg_pace_100m":     a.get("avgPace"),
            "swolf":             a.get("avgSwolf"),
            "strokes":           a.get("avgStrokes"),
            # Load
            "aerobic_te":        a.get("aerobicTrainingEffect"),
            "anaerobic_te":      a.get("anaerobicTrainingEffect"),
        })

    df = pd.DataFrame(rows)
    # Normalize sport labels
    sport_map = {
        "swimming": "swim", "lap_swimming": "swim", "open_water_swimming": "swim",
        "cycling": "bike", "road_biking": "bike", "indoor_cycling": "bike", "virtual_ride": "bike",
        "running": "run", "trail_running": "run", "treadmill_running": "run",
        "strength_training": "str", "fitness_equipment": "str", "indoor_rowing": "str",
        "yoga": "str", "pilates": "str", "hiit": "str", "cross_training": "str",
        "multi_sport": "triathlon",
    }
    df["sport"] = df["sport"].map(lambda s: sport_map.get(s, s))
    # m/s → sec/km
    df["avg_pace_sec_km"] = df["avg_pace_sec_km"].apply(
        lambda v: 1000 / v if v and v > 0 else None
    )
    return df


def fetch_hrv_status(start: date, end: date) -> pd.DataFrame:
    """Fetch HRV status using the most recent date (garminconnect 0.3+)."""
    def _fetch():
        client = _get_client()
        # get_hrv_data returns last ~7 days of HRV summaries
        return client.get_hrv_data(end.isoformat())

    try:
        raw = _load_or_fetch("hrv", start, end, _fetch)
    except Exception as e:
        log.warning("HRV fetch failed: %s", e)
        return pd.DataFrame()

    if not raw or not isinstance(raw, dict):
        return pd.DataFrame()

    rows = []
    for r in raw.get("hrvSummaries", []):
        rows.append({
            "date":           pd.to_datetime(r.get("calendarDate")),
            "hrv_weekly_avg": r.get("weeklyAvg"),
            "hrv_last_night": r.get("lastNight"),
            "hrv_status":     r.get("status"),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_sleep(start: date, end: date) -> pd.DataFrame:
    """Fetch daily sleep scores for the full date range (day-by-day, cached)."""
    rows = []
    current = start
    client = _get_client()
    while current <= end:
        cache_path = CACHE_DIR / f"sleep_{current}_{current}_{current}.json"
        if cache_path.exists():
            raw = json.loads(cache_path.read_text())
        else:
            try:
                raw = client.get_sleep_data(current.isoformat())
                cache_path.write_text(json.dumps(raw, default=str))
            except Exception as e:
                log.debug("Sleep fetch skipped for %s: %s", current, e)
                current += timedelta(days=1)
                continue
        dto = raw.get("dailySleepDTO", {}) if isinstance(raw, dict) else {}
        rows.append({
            "date":              pd.to_datetime(current),
            "sleep_score":       dto.get("sleepScores", {}).get("overall", {}).get("value"),
            "sleep_duration_h":  (dto.get("sleepTimeSeconds") or 0) / 3600,
            "deep_sleep_h":      (dto.get("deepSleepSeconds") or 0) / 3600,
            "rem_sleep_h":       (dto.get("remSleepSeconds") or 0) / 3600,
        })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def fetch_resting_hr(start: date, end: date) -> pd.DataFrame:
    """Fetch daily stats (RHR, Body Battery, Stress) from Garmin Connect (cached)."""
    rows = []
    current = start
    client = _get_client()
    while current <= end:
        cache_path = CACHE_DIR / f"rhr_{current}_{current}_{current}.json"
        if cache_path.exists():
            raw = json.loads(cache_path.read_text())
        else:
            try:
                raw = client.get_stats(current.isoformat())
                cache_path.write_text(json.dumps(raw, default=str))
            except Exception as e:
                log.debug("Stats fetch skipped for %s: %s", current, e)
                current += timedelta(days=1)
                continue
        if not isinstance(raw, dict):
            current += timedelta(days=1)
            continue
        rhr = raw.get("restingHeartRate")
        bb  = raw.get("bodyBatteryMostRecentValue")
        bb_hi = raw.get("bodyBatteryHighestValue")
        stress = raw.get("averageStressLevel")
        if rhr and int(rhr) > 20:
            rows.append({
                "date":        pd.to_datetime(current),
                "rhr":         int(rhr),
                "body_battery": int(bb)    if bb    is not None else None,
                "bb_high":     int(bb_hi) if bb_hi is not None else None,
                "stress":      int(stress) if stress is not None else None,
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def fetch_vo2max() -> dict:
    """Fetch latest VO2Max estimates."""
    client = _get_client()
    data = client.get_max_metrics(date.today().isoformat())
    return {
        "vo2max_run":  data.get("mostRecentVO2MaxRunning"),
        "vo2max_bike": data.get("mostRecentVO2MaxCycling"),
    }


def fetch_power_curve(activity_id: int) -> dict:
    """Fetch mean-max power curve for a specific cycling activity."""
    client = _get_client()
    return client.get_activity_hr_in_timezones(activity_id)


TRACKS_DIR = Path("data/tracks")


def _parse_gpx(gpx_bytes: bytes) -> list:
    """Parse GPX bytes → list of {lat, lon, ele} dicts, downsampled to ≤600 pts."""
    import xml.etree.ElementTree as ET
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    try:
        root = ET.fromstring(gpx_bytes)
    except ET.ParseError:
        return []
    pts = []
    for tp in root.findall(".//g:trkpt", ns):
        try:
            lat = float(tp.get("lat"))
            lon = float(tp.get("lon"))
        except (TypeError, ValueError):
            continue
        ele_el = tp.find("g:ele", ns)
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else 0.0
        pts.append({"lat": lat, "lon": lon, "ele": ele})
    # Downsample for map performance
    if len(pts) > 600:
        step = max(1, len(pts) // 600)
        pts = pts[::step]
    return pts


def fetch_activity_gps(activity_id: int,
                       email: str = None, password: str = None) -> list:
    """
    Download and cache GPS track for one activity.
    Returns list of {lat, lon, ele} or [] if no GPS data.
    Cached in data/tracks/{activity_id}.json (only when non-empty).
    """
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = TRACKS_DIR / f"{activity_id}.json"

    # Return cached result only if file is non-empty
    if cache_file.exists() and cache_file.stat().st_size > 10:
        try:
            pts = json.loads(cache_file.read_text())
            if isinstance(pts, list) and pts:
                log.info("GPS cache hit: activity %s (%d pts)", activity_id, len(pts))
                return pts
        except Exception:
            pass

    from garminconnect import Garmin
    client    = _get_client(email, password)
    gpx_bytes = client.download_activity(
        activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX
    )
    pts = _parse_gpx(gpx_bytes)
    log.info("GPS downloaded: activity %s → %d points (raw %d bytes)",
             activity_id, len(pts), len(gpx_bytes) if gpx_bytes else 0)

    if pts:
        cache_file.write_text(json.dumps(pts))
    return pts


_SPORT_MAP = {
    "swim": {"sportTypeId": 4,  "sportTypeKey": "lap_swimming"},
    "bike": {"sportTypeId": 2,  "sportTypeKey": "cycling"},
    "run":  {"sportTypeId": 1,  "sportTypeKey": "running"},
    "str":  {"sportTypeId": 13, "sportTypeKey": "strength_training"},
}
_DEFAULT_SPORT = {"sportTypeId": 0, "sportTypeKey": "other"}


_STEP_TYPE_META = {
    "warmup":    (1, "warmup",    1),
    "cooldown":  (2, "cooldown",  2),
    "interval":  (3, "interval",  3),
    "recovery":  (4, "recovery",  4),
}


def _executable_power_step(step_order: int, step_kind: str, duration_seconds: float,
                            power_low_frac: float | None, power_high_frac: float | None,
                            ftp: int | None):
    """
    Construye un ExecutableStep directamente (no vía los helpers create_*_step
    de la librería) porque esos helpers solo aceptan un dict `targetType` —
    targetValueOne/targetValueTwo son campos EXTRA del step, hermanos de
    targetType, no anidados dentro — un primer intento los anidó mal ahí
    adentro (bug encontrado antes de cualquier push real, corregido acá).
    Target en watts absolutos (no %FTP — así lo espera Garmin, a diferencia
    del %FTP relativo de un .zwo de Zwift).
    """
    from garminconnect.workout import ExecutableStep, ConditionType, TargetType

    step_type_id, step_type_key, display_order = _STEP_TYPE_META[step_kind]
    kwargs = dict(
        stepOrder=step_order,
        stepType={"stepTypeId": step_type_id, "stepTypeKey": step_type_key, "displayOrder": display_order},
        endCondition={
            "conditionTypeId": ConditionType.TIME, "conditionTypeKey": "time",
            "displayOrder": 2, "displayable": True,
        },
        endConditionValue=duration_seconds,
    )
    if power_low_frac is None or power_high_frac is None or not ftp:
        kwargs["targetType"] = {"workoutTargetTypeId": TargetType.NO_TARGET, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
    else:
        kwargs["targetType"] = {
            "workoutTargetTypeId": TargetType.POWER_ZONE,
            "workoutTargetTypeKey": "power.zone",
            "displayOrder": TargetType.POWER_ZONE,
        }
        kwargs["targetValueOne"] = round(power_low_frac * ftp)
        kwargs["targetValueTwo"] = round(power_high_frac * ftp)
    return ExecutableStep(**kwargs)


def _bike_blocks_to_garmin_steps(blocks: list, ftp: int) -> list:
    """
    Traduce blocks_json (mismo formato wire que workout-blocks.js/
    workout_delivery.py: duration en segundos, power como fracción 0..1)
    a workoutSteps reales de Garmin con targets de potencia — en vez del
    step único "sin objetivo" que se mandaba antes. Los intervalos se
    codifican como un RepeatGroup (N iteraciones de trabajo+descanso),
    que es como Garmin modela series repetidas — no como pasos sueltos.
    """
    from garminconnect.workout import create_repeat_group

    steps = []
    order = 1
    for b in blocks:
        t = b.get("type", "steady")
        if t == "warmup":
            steps.append(_executable_power_step(
                order, "warmup", b.get("duration", 300),
                b.get("power_low", 0.5), b.get("power_high", 0.75), ftp))
            order += 1
        elif t == "cooldown":
            steps.append(_executable_power_step(
                order, "cooldown", b.get("duration", 300),
                b.get("power_high", 0.75), b.get("power_low", 0.5), ftp))
            order += 1
        elif t == "ramp":
            # Garmin no tiene un step-type de "rampa" propio — se modela como
            # interval con target de rango amplio (low→high), igual que se
            # hace ya con warmup/cooldown.
            steps.append(_executable_power_step(
                order, "interval", b.get("duration", 300),
                b.get("power_low", 0.6), b.get("power_high", 1.0), ftp))
            order += 1
        elif t == "steady":
            p = b.get("power", 0.75)
            steps.append(_executable_power_step(order, "interval", b.get("duration", 300), p, p, ftp))
            order += 1
        elif t == "freeride":
            steps.append(_executable_power_step(order, "interval", b.get("duration", 300), None, None, None))
            order += 1
        elif t == "intervals":
            on_power  = b.get("on_power", 0.95)
            off_power = b.get("off_power", 0.55)
            on_step  = _executable_power_step(1, "interval", b.get("on_duration", 240), on_power, on_power, ftp)
            off_step = _executable_power_step(2, "recovery", b.get("off_duration", 120), off_power, off_power, ftp)
            steps.append(create_repeat_group(b.get("repeat", 1), [on_step, off_step], order))
            order += 1
    return steps


def _pace_str_to_speed_range_mps(pace_str: str, tolerance_sec_per_km: int = 3) -> tuple[float, float] | None:
    """
    '4:30' (min:seg por km) -> rango de velocidad en m/s (±tolerance_sec_per_km),
    que es como Garmin guarda un target de ritmo (PACE_ZONE) — velocidad, no
    el ritmo en sí. Más rápido = más m/s, por eso el ritmo objetivo pasa a
    ser el límite ALTO de velocidad (targetValueTwo) y el ritmo +tolerancia
    (más lento) el límite BAJO (targetValueOne).
    """
    if not pace_str or ":" not in pace_str:
        return None
    try:
        m, s = pace_str.split(":")
        pace_sec = int(m) * 60 + int(s)
    except (ValueError, TypeError):
        return None
    if pace_sec <= 0:
        return None
    slow_sec = pace_sec + tolerance_sec_per_km
    fast_sec = max(pace_sec - tolerance_sec_per_km, 1)
    return (1000.0 / slow_sec, 1000.0 / fast_sec)  # (m/s más lento, m/s más rápido)


def _executable_run_step(step_order: int, step_kind: str, duration_seconds: float | None,
                          distance_meters: float | None,
                          pace_str: str | None, hr_zone: str | None, fcmax: int | None):
    """
    Análogo a _executable_power_step() pero para carrera: target de ritmo
    (PACE_ZONE, en m/s) si hay pace_str, si no target de zona de FC
    (HEART_RATE_ZONE, en bpm) si hay hr_zone+fcmax, si no sin objetivo.
    El end-condition es por DISTANCIA si se pasa distance_meters (series con
    metros objetivo), o por TIEMPO si se pasa duration_seconds (calentamiento/
    vuelta a la calma/continuo) — nunca ambos.
    """
    from garminconnect.workout import ExecutableStep, ConditionType, TargetType

    step_type_id, step_type_key, display_order = _STEP_TYPE_META[step_kind]
    kwargs = dict(
        stepOrder=step_order,
        stepType={"stepTypeId": step_type_id, "stepTypeKey": step_type_key, "displayOrder": display_order},
    )
    if distance_meters is not None:
        kwargs["endCondition"] = {
            "conditionTypeId": ConditionType.DISTANCE, "conditionTypeKey": "distance",
            "displayOrder": 3, "displayable": True,
        }
        kwargs["endConditionValue"] = distance_meters
    else:
        kwargs["endCondition"] = {
            "conditionTypeId": ConditionType.TIME, "conditionTypeKey": "time",
            "displayOrder": 2, "displayable": True,
        }
        kwargs["endConditionValue"] = duration_seconds or 300

    speed_range = _pace_str_to_speed_range_mps(pace_str) if pace_str else None
    if speed_range:
        kwargs["targetType"] = {
            "workoutTargetTypeId": TargetType.PACE_ZONE,
            "workoutTargetTypeKey": "pace.zone",
            "displayOrder": TargetType.PACE_ZONE,
        }
        kwargs["targetValueOne"] = round(speed_range[0], 3)
        kwargs["targetValueTwo"] = round(speed_range[1], 3)
    elif hr_zone and fcmax:
        from api.services.zones_service import hr_zones
        zone_n = int(str(hr_zone).replace("Z", "") or 0)
        zones = hr_zones(fcmax)
        z = next((zz for zz in zones if zz["zone"] == zone_n), None)
        if z:
            kwargs["targetType"] = {
                "workoutTargetTypeId": TargetType.HEART_RATE_ZONE,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": TargetType.HEART_RATE_ZONE,
            }
            kwargs["targetValueOne"] = z["min_bpm"]
            kwargs["targetValueTwo"] = z["max_bpm"]
        else:
            kwargs["targetType"] = {"workoutTargetTypeId": TargetType.NO_TARGET, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
    else:
        kwargs["targetType"] = {"workoutTargetTypeId": TargetType.NO_TARGET, "workoutTargetTypeKey": "no.target", "displayOrder": 1}

    return ExecutableStep(**kwargs)


def _run_blocks_to_garmin_steps(blocks: list, fcmax: int | None) -> list:
    """
    Traduce el blocks_json de carrera (formato propio de coach.html —
    _mwGetRunJson(): distinto del de bici, ver ese código — dur_min/zone
    para warmup-cooldown-steady, repeat/dist_m/pace/rec_sec/rec_zone para
    series) a workoutSteps reales de Garmin.
    """
    from garminconnect.workout import create_repeat_group

    steps = []
    order = 1
    for b in blocks:
        t = b.get("type", "steady")
        if t in ("warmup", "cooldown"):
            dur = (b.get("dur_min") or 5) * 60
            steps.append(_executable_run_step(order, t, dur, None, None, b.get("zone"), fcmax))
            order += 1
        elif t == "steady":
            dur = (b.get("dur_min") or 20) * 60
            steps.append(_executable_run_step(order, "interval", dur, None, b.get("pace"), b.get("zone"), fcmax))
            order += 1
        elif t == "intervals":
            on_step  = _executable_run_step(1, "interval", None, b.get("dist_m", 400), b.get("pace"), None, fcmax)
            off_step = _executable_run_step(2, "recovery", b.get("rec_sec", 60), None, None, b.get("rec_zone"), fcmax)
            steps.append(create_repeat_group(b.get("repeat", 1), [on_step, off_step], order))
            order += 1
    return steps


def _build_workout_body(session: dict) -> dict:
    """
    Build Garmin workout JSON with required segment/step structure.

    Si session trae blocks_json (bloques estructurados) y sport=='bike' y
    ftp real del atleta, genera los workoutSteps reales con targets de
    potencia por zona — así el atleta ve las series en el reloj, no solo
    "andá en bici 45min sin objetivo". Sin eso (otros deportes por ahora,
    o un template simple sin bloques), sigue el step único genérico de
    antes — comportamiento sin cambios para esos casos.
    """
    sport    = _SPORT_MAP.get(session.get("sport", ""), _DEFAULT_SPORT)
    dur_secs = int((session.get("dur_min") or 60) * 60)
    dist_m   = int((session.get("dist_km") or 0) * 1000) or None

    blocks_json = session.get("blocks_json")
    ftp         = session.get("ftp")
    fcmax       = session.get("fcmax")
    workout_steps = None
    try:
        if session.get("sport") == "bike" and blocks_json and ftp:
            blocks = json.loads(blocks_json)
            garmin_steps = _bike_blocks_to_garmin_steps(blocks, ftp)
            if garmin_steps:
                workout_steps = [s.model_dump(exclude_none=True, mode="json") for s in garmin_steps]
        elif session.get("sport") == "run" and blocks_json:
            blocks = json.loads(blocks_json)
            garmin_steps = _run_blocks_to_garmin_steps(blocks, fcmax)
            if garmin_steps:
                workout_steps = [s.model_dump(exclude_none=True, mode="json") for s in garmin_steps]
    except Exception as e:
        log.warning("No se pudo construir workoutSteps estructurados, usando fallback genérico: %s", e)
        workout_steps = None

    if not workout_steps:
        workout_steps = [
            {
                "type":      "ExecutableStepDTO",
                "stepOrder": 1,
                "stepType":  {"stepTypeId": 3, "stepTypeKey": "interval"},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                "endConditionValue": dur_secs,
                "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
            }
        ]

    return {
        "workoutName": session.get("name", "LabX Workout"),
        "description": session.get("notes") or "",
        "sportType":   sport,
        "estimatedDurationInSecs":   dur_secs,
        "estimatedDistanceInMeters": dist_m,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType":    sport,
                "workoutSteps": workout_steps,
            }
        ],
    }


def schedule_workout(session: dict, target_date: str) -> dict:
    """
    Create a workout on Garmin Connect and schedule it to target_date.

    session dict keys: name, sport, dur_min, dist_km, notes
    target_date: 'YYYY-MM-DD'
    """
    client = _get_client()
    workout_body = _build_workout_body(session)

    log.info("Creating Garmin workout: %s for %s", workout_body["workoutName"], target_date)

    # Step 1 — create workout definition
    created = client.upload_workout(workout_body)
    workout_id = (created or {}).get("workoutId")
    if not workout_id:
        raise RuntimeError(f"Garmin did not return a workoutId: {created}")

    log.info("Garmin workout created: id=%s", workout_id)

    # Step 2 — schedule it to the target date
    scheduled = client.schedule_workout(workout_id, target_date)
    log.info("Garmin workout %s scheduled on %s: %s", workout_id, target_date, scheduled)

    return {"workoutId": workout_id, "scheduled": scheduled, "date": target_date}


def reschedule_workout(session: dict, old_date: str, new_date: str) -> dict:
    """
    Convenience wrapper: schedule a previously planned session to a new date.
    old_date is logged only; Garmin has no native "move" endpoint — we create fresh.
    """
    log.info(
        "Rescheduling '%s' from %s to %s",
        session.get("name"), old_date, new_date
    )
    return schedule_workout(session, new_date)


def schedule_workout_for_athlete(
    session: dict,
    target_date: str,
    athlete_id: str,
    athlete_email: str,
    athlete_password: str,
) -> dict:
    """
    Push a workout to a *specific athlete's* Garmin account.

    Uses a temporary, per-call client — does NOT touch the module-level
    singleton (_CLIENT) which belongs to the coach/admin account.

    Reutiliza api.garmin_pull_service._garmin_login() (mismo helper que usa
    el sync normal de actividades) en vez de loguearse con usuario/contraseña
    desde cero en cada asignación — ese login "fresco" repetido es lo que
    generaba riesgo real de rate-limit/bloqueo de Garmin al asignar a un
    grupo grande (N atletas = N logins simultáneos). _garmin_login() intenta
    primero resumir la sesión guardada (garth token en data/garmin_tokens/)
    y solo cae a login por credenciales si hace falta.

    session dict keys: name, sport, dur_min, dist_km, notes
    target_date: 'YYYY-MM-DD'
    """
    from api.garmin_pull_service import _garmin_login, GarminMFARequired

    log.info("Authenticating Garmin for athlete: %s (id=%s)", athlete_email, athlete_id)
    try:
        client = _garmin_login(athlete_id, athlete_email, athlete_password)
    except GarminMFARequired:
        # Un push en background no puede resolver un código MFA interactivo —
        # fallar con un mensaje claro en vez de colgar o crashear el thread.
        raise RuntimeError(
            "Garmin requiere verificación (MFA) para este atleta — "
            "debe reconectar su cuenta desde Perfil → Reconectar Garmin "
            "antes de que el push automático pueda funcionar."
        )
    log.info("Garmin auth OK for %s", athlete_email)

    workout_body = _build_workout_body(session)
    created    = client.upload_workout(workout_body)
    workout_id = (created or {}).get("workoutId")
    if not workout_id:
        raise RuntimeError(f"Garmin did not return workoutId: {created}")

    scheduled = client.schedule_workout(workout_id, target_date)
    log.info("Workout %s scheduled on %s for %s", workout_id, target_date, athlete_email)

    return {"workoutId": str(workout_id), "scheduled": scheduled, "date": target_date}


def build_training_load(df_activities: pd.DataFrame, ftp: float, threshold_run_sec: float) -> pd.DataFrame:
    """
    Compute daily TSS for each sport and aggregate into a load timeline.
    Uses Coggan's TSS model for cycling, rTSS for running, ssTSS for swimming.
    """
    from utils.formulas import compute_tss_bike, compute_rtss_run, compute_sstss_swim

    df = df_activities.copy()
    df["tss_computed"] = None

    mask_bike = df["sport"] == "bike"
    mask_run  = df["sport"] == "run"
    mask_swim = df["sport"] == "swim"

    df.loc[mask_bike, "tss_computed"] = df[mask_bike].apply(
        lambda r: compute_tss_bike(r["duration_sec"], r["norm_power"] or r["avg_power"], ftp), axis=1
    )
    df.loc[mask_run, "tss_computed"] = df[mask_run].apply(
        lambda r: compute_rtss_run(r["duration_sec"], r["avg_pace_sec_km"], threshold_run_sec), axis=1
    )
    df.loc[mask_swim, "tss_computed"] = df[mask_swim].apply(
        lambda r: compute_sstss_swim(r["duration_sec"]), axis=1
    )

    # Use Garmin's native TSS when available (more accurate)
    df["tss_final"] = df["tss"].fillna(df["tss_computed"])

    daily = df.groupby(df["date"].dt.date)["tss_final"].sum().reset_index()
    daily.columns = ["date", "tss"]
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").set_index("date").reindex(
        pd.date_range(daily["date"].min(), daily["date"].max(), freq="D"), fill_value=0
    ).reset_index().rename(columns={"index": "date"})

    # Exponential weighted averages (Coggan's ATL/CTL model)
    # CTL τ=42 days, ATL τ=7 days
    daily["ctl"] = daily["tss"].ewm(span=42, adjust=False).mean()
    daily["atl"] = daily["tss"].ewm(span=7,  adjust=False).mean()
    daily["tsb"] = daily["ctl"] - daily["atl"]   # Training Stress Balance (Form)
    daily["acwr"] = daily["atl"] / (daily["ctl"] + 1e-9)

    return daily
