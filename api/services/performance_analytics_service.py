"""
LabX Performance Analytics Service
=====================================
Motor de análisis de rendimiento deportivo basado en el historial completo de actividades Garmin.

Módulos:
  1. Critical Power Curve (CP) — mejor potencia promedio en duraciones 1s-3h
  2. VO2max estimado — desde pace + FC de actividades de running
  3. Personal Records — por deporte y distancia
  4. Training Distribution — distribución por zona/sport/hora del día
  5. Zone Auto-calibration — FTP/CSS/pace threshold desde datos reales recientes

Algoritmos:
  - CP curve: ventana deslizante sobre avg_power de actividades de ciclismo, max por duración
  - VO2max: modelo Daniels-Gilbert para running (VO2 = (-4.6 + 0.182258*v + 0.000104*v^2) / (0.8 + 0.1894393*e^(-0.012778*t) + 0.2989558*e^(-0.1932605*t)))
  - PRs: filtrar actividades con distancia >= threshold por disciplina
  - Zones: percentil 95 del esfuerzo reciente como FTP estimado
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import GarminActivity, GarminHealthDaily, GarminTrainingLoad, User

logger = logging.getLogger("labx.performance_analytics")

# ── Duraciones para la curva de potencia (segundos) ──────────────────────────
CP_DURATIONS = [
    5, 10, 15, 20, 30, 60, 90,
    120, 180, 240, 300,          # 2-5 min
    360, 420, 480, 600,          # 6-10 min
    720, 900, 1200, 1800,        # 12-30 min
    2400, 3000, 3600,            # 40-60 min
    4800, 5400, 7200, 10800,     # 80min-3h
]

CP_LABELS = {
    5: "5s", 10: "10s", 15: "15s", 20: "20s", 30: "30s",
    60: "1m", 90: "90s", 120: "2m", 180: "3m", 240: "4m",
    300: "5m", 360: "6m", 420: "7m", 480: "8m", 600: "10m",
    720: "12m", 900: "15m", 1200: "20m", 1800: "30m",
    2400: "40m", 3000: "50m", 3600: "1h", 4800: "80m",
    5400: "90m", 7200: "2h", 10800: "3h",
}

# ── Distancias PR por deporte ─────────────────────────────────────────────────
PR_DISTANCES = {
    "run": [
        {"key": "1k",   "label": "1 km",   "min_km": 0.95,  "max_km": 1.05},
        {"key": "5k",   "label": "5 km",   "min_km": 4.8,   "max_km": 5.2},
        {"key": "10k",  "label": "10 km",  "min_km": 9.7,   "max_km": 10.3},
        {"key": "21k",  "label": "21.1 km","min_km": 20.8,  "max_km": 21.4},
        {"key": "42k",  "label": "Maratón","min_km": 41.8,  "max_km": 42.6},
    ],
    "bike": [
        {"key": "20k",  "label": "20 km",  "min_km": 18,    "max_km": 22},
        {"key": "40k",  "label": "40 km",  "min_km": 38,    "max_km": 42},
        {"key": "80k",  "label": "80 km",  "min_km": 77,    "max_km": 83},
        {"key": "90k",  "label": "90 km",  "min_km": 87,    "max_km": 93},
        {"key": "180k", "label": "180 km", "min_km": 175,   "max_km": 185},
    ],
    "swim": [
        {"key": "400m", "label": "400 m",  "min_km": 0.38,  "max_km": 0.42},
        {"key": "750m", "label": "750 m",  "min_km": 0.72,  "max_km": 0.78},
        {"key": "1500m","label": "1500 m", "min_km": 1.45,  "max_km": 1.55},
        {"key": "1900m","label": "1900 m", "min_km": 1.85,  "max_km": 1.95},
        {"key": "3800m","label": "3800 m", "min_km": 3.70,  "max_km": 3.90},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. CRITICAL POWER CURVE
# ─────────────────────────────────────────────────────────────────────────────

def compute_power_curve(
    user_id:   str,
    db:        Session,
    days_back: int = 365,
    sport:     str = "bike",
) -> dict:
    """
    Calcula la curva de potencia crítica para un atleta.
    Para cada duración en CP_DURATIONS, encuentra la máxima potencia promedio
    sostenida por ese período en las actividades de los últimos N días.

    Nota: GarminActivity almacena avg_power por actividad, no el stream de potencia.
    Aproximamos la curva usando el avg_power de actividades cortas y estimación
    de decaimiento exponencial para duraciones menores.

    Retorna curva con mejor estimado por duración + modelo CP2 (CP, W').
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    activities = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id  == user_id,
            GarminActivity.date_iso >= cutoff,
            GarminActivity.sport    == sport,
            GarminActivity.avg_power.isnot(None),
            GarminActivity.avg_power > 50,   # filtrar datos corruptos
            GarminActivity.dur_min  >= 5,    # mínimo 5 minutos
        )
        .order_by(GarminActivity.date_iso.desc())
        .limit(500)
        .all()
    )

    if not activities:
        return {
            "sport":      sport,
            "curve":      [],
            "cp_model":   None,
            "ftp_est":    None,
            "days_back":  days_back,
            "message":    f"Sin actividades de {sport} con datos de potencia en los últimos {days_back} días.",
        }

    # Índice por duración → mejor potencia encontrada
    best_power: dict[int, float] = {}

    for act in activities:
        dur_sec  = (act.dur_min or 0) * 60
        avg_pwr  = act.avg_power or 0

        if dur_sec <= 0 or avg_pwr <= 0:
            continue

        # Para cada duración del modelo que sea ≤ duración de la actividad:
        # La potencia máxima sostenible por esa duración es mayor que avg_power
        # de una actividad más larga. Usamos escalado exponencial: P(t) = P_avg * (dur/t)^0.07
        for dur_target in CP_DURATIONS:
            if dur_target > dur_sec * 1.05:  # no extrapolar mucho más allá de la actividad
                continue
            # Si la actividad duró exactamente esta duración, su avg_power es válido.
            # Si duró más, la potencia para ese sub-intervalo fue mayor.
            # Aproximación: factor = (dur_sec / dur_target)^0.07
            factor = (dur_sec / dur_target) ** 0.07 if dur_target < dur_sec else 1.0
            estimated = avg_pwr * factor

            if dur_target not in best_power or estimated > best_power[dur_target]:
                best_power[dur_target] = round(estimated, 1)

    if not best_power:
        return {"sport": sport, "curve": [], "cp_model": None, "ftp_est": None, "days_back": days_back}

    # Construir curva ordenada
    curve = []
    prev_pwr = None
    for dur in CP_DURATIONS:
        if dur not in best_power:
            continue
        pwr = best_power[dur]
        # Asegurar monotonía decreciente (más duración → menor potencia)
        if prev_pwr is not None and pwr > prev_pwr:
            pwr = prev_pwr
        prev_pwr = pwr
        curve.append({
            "duration_sec": dur,
            "label":        CP_LABELS.get(dur, f"{dur}s"),
            "power_w":      round(pwr, 1),
            "watts_per_kg": None,  # se llenará si tenemos peso
        })

    # FTP estimado: potencia sostenible 60 min ≈ 95% del mejor esfuerzo de 20 min
    p20 = best_power.get(1200)  # 20 min
    p60 = best_power.get(3600)  # 60 min
    ftp_est = None
    if p60:
        ftp_est = round(p60)
    elif p20:
        ftp_est = round(p20 * 0.95)

    # Modelo CP2: ajuste lineal en coordenadas (1/t, P) → P = CP + W'/t
    cp_model = _fit_cp2_model(best_power)

    # Peso del atleta
    user = db.query(User).filter(User.id == user_id).first()
    weight = getattr(user, "weight_kg", None) if user else None
    if weight:
        for point in curve:
            point["watts_per_kg"] = round(point["power_w"] / weight, 2)
        if ftp_est:
            ftp_wkg = round(ftp_est / weight, 2)
        else:
            ftp_wkg = None
    else:
        ftp_wkg = None

    return {
        "sport":       sport,
        "curve":       curve,
        "cp_model":    cp_model,
        "ftp_est":     ftp_est,
        "ftp_wkg":     ftp_wkg,
        "weight_kg":   weight,
        "n_activities":len(activities),
        "days_back":   days_back,
        "generated_at":date.today().isoformat(),
    }


def _fit_cp2_model(best_power: dict[int, float]) -> Optional[dict]:
    """
    Ajuste del modelo CP2: P = CP + W'/t
    Usando regresión lineal en coordenadas (1/t, P).
    CP = potencia crítica (asintótica a largo plazo)
    W' = capacidad de trabajo anaeróbico (en Joules)
    """
    # Usar duraciones 3-30 min para el ajuste (evitar extremos)
    points = [(dur, pwr) for dur, pwr in best_power.items() if 180 <= dur <= 1800]
    if len(points) < 3:
        return None

    n = len(points)
    inv_t = [1.0 / dur for dur, _ in points]
    P     = [pwr       for _, pwr in points]

    # Regresión lineal: P = a*(1/t) + b → a=W', b=CP
    sum_x  = sum(inv_t)
    sum_y  = sum(P)
    sum_xy = sum(x * y for x, y in zip(inv_t, P))
    sum_x2 = sum(x ** 2 for x in inv_t)
    denom  = n * sum_x2 - sum_x ** 2

    if abs(denom) < 1e-10:
        return None

    W_prime = (n * sum_xy - sum_x * sum_y) / denom
    CP      = (sum_y - W_prime * sum_x) / n

    if CP < 50 or CP > 600 or W_prime < 5000 or W_prime > 50000:
        return None  # valores fuera de rango fisiológico

    return {
        "cp_watts":   round(CP, 1),
        "w_prime_j":  round(W_prime),
        "description":f"Potencia Crítica: {round(CP)}W, W': {round(W_prime/1000,1)}kJ",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. VO2MAX ESTIMADO (Running)
# ─────────────────────────────────────────────────────────────────────────────

def compute_vo2max_history(
    user_id:   str,
    db:        Session,
    days_back: int = 365,
) -> dict:
    """
    Estima el VO2max mensual desde actividades de running usando el modelo
    de velocidad+FC de Daniels adaptado (sin lab).

    VO2 = 0.000104*v^2 + 0.182258*v - 4.6
    %VO2max @ FC/FCmax = 0.8 + 0.1894393*e^(-0.012778*t) + 0.2989558*e^(-0.1932605*t)

    Simplificado con la fórmula de Fick para carrera:
    VO2max = (pace_vo2) / (%VO2max_from_hr)

    También usa el VO2max de Garmin si está disponible en GarminHealthDaily.
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    # VO2max de Garmin Connect (si disponible)
    hrv_days = (
        db.query(GarminHealthDaily)
        .filter(
            GarminHealthDaily.user_id  == user_id,
            GarminHealthDaily.date_iso >= cutoff,
        )
        .order_by(GarminHealthDaily.date_iso)
        .all()
    )

    garmin_vo2max = [
        {"date": r.date_iso, "vo2max": round(r.vo2max, 1)}
        for r in hrv_days
        if r.vo2max and r.vo2max > 20
    ]

    # VO2max estimado desde actividades de running
    user = db.query(User).filter(User.id == user_id).first()
    fcmax = getattr(user, "fcmax", None) or 180

    run_acts = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id  == user_id,
            GarminActivity.date_iso >= cutoff,
            GarminActivity.sport    == "run",
            GarminActivity.avg_hr.isnot(None),
            GarminActivity.dist_km  >= 3.0,
            GarminActivity.dur_min  >= 20,
        )
        .order_by(GarminActivity.date_iso)
        .all()
    )

    estimated_timeline = []
    for act in run_acts:
        if not act.avg_hr or not act.dist_km or not act.dur_min:
            continue
        # Velocidad en m/min
        v_mpm = act.dist_km * 1000 / (act.dur_min * 1)
        # VO2 a esa velocidad (Daniels)
        vo2_at_v = 0.000104 * v_mpm**2 + 0.182258 * v_mpm - 4.6
        if vo2_at_v <= 0:
            continue
        # %VO2max desde FC (aproximación: asumiendo actividad de >20min)
        hr_ratio = min(act.avg_hr / fcmax, 0.99)
        # Relación FC/%VO2max (Swain 1994): %VO2max = 1.5472*(%HRmax) - 0.5472
        pct_vo2max = max(0.3, min(1.0, 1.5472 * hr_ratio - 0.5472))
        vo2max_est = round(vo2_at_v / pct_vo2max, 1)

        if 25 <= vo2max_est <= 90:  # rango fisiológico razonable
            estimated_timeline.append({
                "date":       act.date_iso,
                "vo2max_est": vo2max_est,
                "source":     "estimated",
            })

    # Combinar Garmin + estimado, priorizar Garmin cuando disponible
    all_vo2 = []
    garmin_dates = {r["date"] for r in garmin_vo2max}
    for r in garmin_vo2max:
        all_vo2.append({"date": r["date"], "vo2max": r["vo2max"], "source": "garmin"})
    for r in estimated_timeline:
        # Solo agregar estimado si no hay Garmin para esa semana
        week = r["date"][:8] + "00"   # YYYY-MM (aproximar por mes)
        garmin_week = any(d[:8] + "00" == week for d in garmin_dates)
        if not garmin_week:
            all_vo2.append({"date": r["date"], "vo2max": r["vo2max_est"], "source": "estimated"})

    all_vo2.sort(key=lambda x: x["date"])

    # Tendencia: promedio últimos 90 días vs 90-180 días
    today = date.today().isoformat()
    cutoff_90  = (date.today() - timedelta(days=90)).isoformat()
    cutoff_180 = (date.today() - timedelta(days=180)).isoformat()

    recent = [r["vo2max"] for r in all_vo2 if r["date"] >= cutoff_90]
    prev   = [r["vo2max"] for r in all_vo2 if cutoff_180 <= r["date"] < cutoff_90]

    vo2max_current = round(sum(recent) / len(recent), 1) if recent else None
    vo2max_prev    = round(sum(prev)   / len(prev),   1) if prev   else None
    trend_delta    = round(vo2max_current - vo2max_prev, 1) if (vo2max_current and vo2max_prev) else None

    # Clasificación (hombres entrenados: >55 excelente)
    def _classify_vo2max(v, sex="M"):
        if sex == "F":
            thresholds = [(35,"Bajo"),(42,"Regular"),(49,"Bueno"),(56,"Muy bueno"),(999,"Excelente")]
        else:
            thresholds = [(40,"Bajo"),(48,"Regular"),(56,"Bueno"),(62,"Muy bueno"),(999,"Excelente")]
        for thresh, label in thresholds:
            if v <= thresh:
                return label
        return "Excelente"

    sex = getattr(user, "sexo", "M") if user else "M"
    classification = _classify_vo2max(vo2max_current, sex) if vo2max_current else None

    return {
        "timeline":        all_vo2,
        "vo2max_current":  vo2max_current,
        "vo2max_prev":     vo2max_prev,
        "trend_delta":     trend_delta,
        "classification":  classification,
        "garmin_readings": len(garmin_vo2max),
        "estimated_readings": len(estimated_timeline),
        "n_run_activities": len(run_acts),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. PERSONAL RECORDS
# ─────────────────────────────────────────────────────────────────────────────

def compute_personal_records(
    user_id: str,
    db:      Session,
    sports:  Optional[list[str]] = None,
) -> dict:
    """
    Encuentra los Personal Records del atleta por deporte y distancia.
    Para ciclismo: mejor tiempo, mejor potencia media, mejor velocidad.
    Para running: mejor tiempo, mejor pace.
    Para natación: mejor pace/100m.
    """
    if sports is None:
        sports = ["run", "bike", "swim"]

    all_activities = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id == user_id,
            GarminActivity.sport.in_(sports),
            GarminActivity.dist_km > 0,
            GarminActivity.dur_min > 0,
        )
        .order_by(GarminActivity.date_iso)
        .all()
    )

    records = {}

    for sport in sports:
        sport_acts = [a for a in all_activities if a.sport == sport]
        if not sport_acts:
            continue

        sport_prs = {}
        distances  = PR_DISTANCES.get(sport, [])

        for dist_cfg in distances:
            matching = [
                a for a in sport_acts
                if dist_cfg["min_km"] <= a.dist_km <= dist_cfg["max_km"]
            ]
            if not matching:
                continue

            if sport == "bike":
                # PR ciclismo: mayor avg_power Y menor tiempo
                best_power_act = max(matching, key=lambda a: a.avg_power or 0)
                best_speed_act = min(matching, key=lambda a: a.dur_min / max(a.dist_km, 0.001))
                best_time_act  = min(matching, key=lambda a: a.dur_min)

                sport_prs[dist_cfg["key"]] = {
                    "label":      dist_cfg["label"],
                    "best_time": {
                        "duration_min": best_time_act.dur_min,
                        "date":         best_time_act.date_iso,
                        "activity_id":  best_time_act.activity_id,
                        "formatted":    _fmt_dur(best_time_act.dur_min),
                    },
                    "best_power": {
                        "watts":    best_power_act.avg_power,
                        "date":     best_power_act.date_iso,
                        "activity_id": best_power_act.activity_id,
                    } if best_power_act.avg_power else None,
                    "best_speed_kmh": round(best_speed_act.dist_km / (best_speed_act.dur_min / 60), 1),
                    "n_attempts":  len(matching),
                }

            elif sport == "run":
                best_time_act = min(matching, key=lambda a: a.dur_min)
                pace_min_km   = best_time_act.dur_min / max(best_time_act.dist_km, 0.001)

                sport_prs[dist_cfg["key"]] = {
                    "label":       dist_cfg["label"],
                    "best_time":   {
                        "duration_min": best_time_act.dur_min,
                        "date":         best_time_act.date_iso,
                        "activity_id":  best_time_act.activity_id,
                        "formatted":    _fmt_dur(best_time_act.dur_min),
                    },
                    "pace_min_km": round(pace_min_km, 2),
                    "pace_fmt":    _fmt_pace(pace_min_km),
                    "n_attempts":  len(matching),
                }

            elif sport == "swim":
                best_time_act = min(matching, key=lambda a: a.dur_min)
                pace_100m     = best_time_act.dur_min / max(best_time_act.dist_km * 10, 0.001)

                sport_prs[dist_cfg["key"]] = {
                    "label":    dist_cfg["label"],
                    "best_time":{
                        "duration_min": best_time_act.dur_min,
                        "date":         best_time_act.date_iso,
                        "formatted":    _fmt_dur(best_time_act.dur_min),
                    },
                    "pace_100m_fmt": _fmt_pace(pace_100m),
                    "n_attempts":   len(matching),
                }

        if sport_prs:
            records[sport] = sport_prs

    return {
        "records":       records,
        "total_activities": len(all_activities),
        "generated_at":  date.today().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. TRAINING DISTRIBUTION HEATMAP
# ─────────────────────────────────────────────────────────────────────────────

def compute_training_distribution(
    user_id:   str,
    db:        Session,
    days_back: int = 365,
) -> dict:
    """
    Distribución del entrenamiento por:
    - Deporte (% del TSS total)
    - Día de la semana (qué días entrena más)
    - Hora del día (mañana/tarde/noche)
    - Zona de intensidad (usando avg_hr como proxy)
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    acts = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id  == user_id,
            GarminActivity.date_iso >= cutoff,
        )
        .all()
    )

    if not acts:
        return {"message": "Sin actividades en el período"}

    # Por deporte
    sport_tss: dict[str, float] = {}
    sport_hrs: dict[str, float] = {}
    sport_count: dict[str, int] = {}
    for a in acts:
        sp = a.sport or "other"
        sport_tss[sp]   = sport_tss.get(sp, 0)   + (a.tss or 0)
        sport_hrs[sp]   = sport_hrs.get(sp, 0)   + ((a.dur_min or 0) / 60)
        sport_count[sp] = sport_count.get(sp, 0) + 1

    total_tss = sum(sport_tss.values()) or 1
    total_hrs = sum(sport_hrs.values()) or 1

    by_sport = [
        {
            "sport":    sp,
            "tss":      round(sport_tss[sp], 1),
            "hours":    round(sport_hrs[sp], 1),
            "pct_tss":  round(sport_tss[sp] / total_tss * 100, 1),
            "pct_hrs":  round(sport_hrs[sp] / total_hrs * 100, 1),
            "count":    sport_count[sp],
        }
        for sp in sorted(sport_tss, key=lambda x: -sport_tss[x])
    ]

    # Por día de la semana
    DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    day_load = [0.0] * 7
    day_count= [0]   * 7
    for a in acts:
        try:
            d = date.fromisoformat(a.date_iso)
            dow = d.weekday()  # 0=Lun
            day_load[dow]  += a.tss or 0
            day_count[dow] += 1
        except Exception:
            pass

    by_weekday = [
        {"day": DAY_NAMES[i], "tss_avg": round(day_load[i] / max(day_count[i], 1), 1), "count": day_count[i]}
        for i in range(7)
    ]

    # Por zona de intensidad (proxy desde avg_hr/FCmax)
    user      = db.query(User).filter(User.id == user_id).first()
    fcmax     = getattr(user, "fcmax", None) or 180
    zone_tss  = {"Z1": 0.0, "Z2": 0.0, "Z3": 0.0, "Z4": 0.0, "Z5": 0.0, "no_hr": 0.0}

    for a in acts:
        tss = a.tss or 0
        if not a.avg_hr:
            zone_tss["no_hr"] += tss
            continue
        hr_pct = a.avg_hr / fcmax
        if hr_pct   < 0.60: zone_tss["Z1"] += tss
        elif hr_pct < 0.70: zone_tss["Z2"] += tss
        elif hr_pct < 0.80: zone_tss["Z3"] += tss
        elif hr_pct < 0.90: zone_tss["Z4"] += tss
        else:               zone_tss["Z5"] += tss

    tss_with_hr = sum(v for k, v in zone_tss.items() if k != "no_hr") or 1
    by_zone = [
        {"zone": z, "tss": round(v, 1), "pct": round(v / tss_with_hr * 100, 1)}
        for z, v in zone_tss.items() if z != "no_hr"
    ]

    # Polarization index: %Z1+Z2 vs %Z4+Z5
    lo_pct = sum(z["pct"] for z in by_zone if z["zone"] in ("Z1", "Z2"))
    hi_pct = sum(z["pct"] for z in by_zone if z["zone"] in ("Z4", "Z5"))
    mid_pct= sum(z["pct"] for z in by_zone if z["zone"] == "Z3")
    pol_index = round(lo_pct / max(mid_pct + hi_pct, 1), 2)

    return {
        "by_sport":         by_sport,
        "by_weekday":       by_weekday,
        "by_zone":          by_zone,
        "polarization_index": pol_index,
        "polarization_label": (
            "Polarizado ✅ (óptimo para resistencia)" if pol_index > 2
            else "Piramidal" if pol_index > 1.2
            else "Umbral-dominado ⚠️ (alto riesgo de meseta)"
        ),
        "total_tss":  round(total_tss, 1),
        "total_hours":round(total_hrs, 1),
        "total_acts": len(acts),
        "days_back":  days_back,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. ZONE AUTO-CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_zone_calibration(
    user_id:   str,
    db:        Session,
    days_back: int = 90,
) -> dict:
    """
    Auto-calibra las zonas de entrenamiento desde actividades recientes.

    Para ciclismo: FTP estimado desde potencia máxima de 20min (× 0.95)
    Para running: umbral de pace desde mejor esfuerzo de 30-60min
    Para natación: CSS desde mejor 400m y mejor 200m (test del CSSspeed)

    Busca actividades de alta intensidad recientes y infiere los umbrales.
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    acts = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id  == user_id,
            GarminActivity.date_iso >= cutoff,
        )
        .all()
    )

    user   = db.query(User).filter(User.id == user_id).first()
    weight = getattr(user, "weight_kg", None) if user else None
    fcmax  = getattr(user, "fcmax", None) or 180

    # ── Ciclismo: FTP desde mayor avg_power en 20-60 min ─────────────────
    bike_acts = [a for a in acts if a.sport == "bike" and a.avg_power and 15 <= (a.dur_min or 0) <= 70]
    ftp_result = None
    if bike_acts:
        # Mejor potencia en ventana 20min: usar la actividad de ~20min con mayor potencia
        p20_candidates = [a for a in bike_acts if 18 <= (a.dur_min or 0) <= 25]
        p60_candidates = [a for a in bike_acts if 50 <= (a.dur_min or 0) <= 70]

        ftp_from_20 = None
        ftp_from_60 = None

        if p20_candidates:
            best_20 = max(p20_candidates, key=lambda a: a.avg_power)
            ftp_from_20 = round(best_20.avg_power * 0.95)

        if p60_candidates:
            best_60 = max(p60_candidates, key=lambda a: a.avg_power)
            ftp_from_60 = round(best_60.avg_power)

        # Preferir el de 60 min; si no, usar 95% del de 20 min
        ftp_watts = ftp_from_60 or ftp_from_20
        if ftp_watts:
            ftp_result = {
                "ftp_watts":   ftp_watts,
                "ftp_wkg":     round(ftp_watts / weight, 2) if weight else None,
                "source":      "60min activity" if ftp_from_60 else "20min × 0.95",
                "zones": {
                    "Z1": f"<{round(ftp_watts*0.55)}W (recuperación)",
                    "Z2": f"{round(ftp_watts*0.55)}-{round(ftp_watts*0.74)}W (aeróbico)",
                    "Z3": f"{round(ftp_watts*0.74)}-{round(ftp_watts*0.87)}W (tempo)",
                    "Z4": f"{round(ftp_watts*0.87)}-{round(ftp_watts*1.02)}W (umbral)",
                    "Z5": f">{round(ftp_watts*1.02)}W (VO2max/anaeróbico)",
                },
            }

    # ── Running: pace umbral desde esfuerzo de 30-60 min ─────────────────
    run_acts = [a for a in acts if a.sport == "run" and a.dist_km >= 5 and 25 <= (a.dur_min or 0) <= 65]
    run_threshold = None
    if run_acts:
        # Actividades con FC alta (>85% FCmax) son umbral o mayor
        threshold_acts = [a for a in run_acts if a.avg_hr and a.avg_hr >= fcmax * 0.85]
        if threshold_acts:
            best_thresh = min(threshold_acts, key=lambda a: a.dur_min / max(a.dist_km, 0.001))
            pace_min_km = best_thresh.dur_min / max(best_thresh.dist_km, 0.001)
            run_threshold = {
                "pace_min_km":  round(pace_min_km, 2),
                "pace_fmt":     _fmt_pace(pace_min_km),
                "source":       f"actividad {round(best_thresh.dist_km,1)}km @{best_thresh.avg_hr}bpm",
                "zones": {
                    "Z1": f">{_fmt_pace(pace_min_km * 1.35)}/km (recuperación)",
                    "Z2": f"{_fmt_pace(pace_min_km * 1.20)}-{_fmt_pace(pace_min_km * 1.35)}/km (aeróbico)",
                    "Z3": f"{_fmt_pace(pace_min_km * 1.10)}-{_fmt_pace(pace_min_km * 1.20)}/km (tempo)",
                    "Z4": f"{_fmt_pace(pace_min_km * 1.02)}-{_fmt_pace(pace_min_km * 1.10)}/km (umbral)",
                    "Z5": f"<{_fmt_pace(pace_min_km * 1.02)}/km (VO2max)",
                },
            }

    # ── Natación: CSS desde 400m y 200m (si disponibles) ─────────────────
    swim_acts = [a for a in acts if a.sport == "swim" and a.dist_km > 0]
    css_result = None
    s400 = [a for a in swim_acts if 0.38 <= a.dist_km <= 0.42]
    s200 = [a for a in swim_acts if 0.18 <= a.dist_km <= 0.22]
    if s400 and s200:
        best_400 = min(s400, key=lambda a: a.dur_min)
        best_200 = min(s200, key=lambda a: a.dur_min)
        t400 = best_400.dur_min * 60  # en segundos
        t200 = best_200.dur_min * 60
        # CSS formula: CSS = (400-200) / (t400 - t200)  metros/segundo → convertir a sec/100m
        d_diff = 200  # metros
        t_diff = t400 - t200
        if t_diff > 0:
            css_ms   = d_diff / t_diff   # m/s
            css_s100 = 100 / css_ms      # seg/100m
            css_result = {
                "css_sec_100m": round(css_s100),
                "css_fmt":      _fmt_pace(css_s100 / 60),
                "source":       f"test 200/400m ({_fmt_dur(best_200.dur_min)} / {_fmt_dur(best_400.dur_min)})",
            }

    return {
        "cycling":   ftp_result,
        "running":   run_threshold,
        "swimming":  css_result,
        "period":    f"últimos {days_back} días",
        "generated_at": date.today().isoformat(),
        "note": "Valores estimados desde actividades recientes. Confirmar con test formal para mayor precisión.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. CTL / ATL / TSB PROJECTION (Sprint 25)
# ─────────────────────────────────────────────────────────────────────────────

_CTL_TAU = 42   # días — tiempo de adaptación crónica (Banister)
_ATL_TAU = 7    # días — tiempo de fatiga aguda
_CTL_DECAY = 1 - math.exp(-1 / _CTL_TAU)
_ATL_DECAY = 1 - math.exp(-1 / _ATL_TAU)


def project_ctl_tsb(
    user_id:        str,
    db:             Session,
    planned_tss:    float = 0.0,
    days:           int   = 28,
) -> dict:
    """
    Proyecta CTL, ATL y TSB para los próximos N días asumiendo entrenamiento
    constante de `planned_tss` TSS por día.

    Base: modelo de Banister (1975), implementación estándar de PMC.
    CTL[t+1] = CTL[t] + (TSS - CTL[t]) * (1 - e^(-1/42))
    ATL[t+1] = ATL[t] + (TSS - ATL[t]) * (1 - e^(-1/7))
    TSB[t]   = CTL[t] - ATL[t]

    Returns:
        projection: lista de {day_offset, date_iso, ctl, atl, tsb, form_label}
        peak_form_day: día en que TSB será máximo (ideal para A-race)
    """
    # Cargar valores actuales de CTL/ATL/TSB
    today_iso = date.today().isoformat()
    latest_tl = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso <= today_iso,
        )
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )

    if latest_tl and latest_tl.ctl:
        ctl = float(latest_tl.ctl)
        atl = float(latest_tl.atl or ctl)
    else:
        ctl = 40.0   # default conservative base
        atl = 45.0

    tss = max(0.0, float(planned_tss))
    projection = []
    peak_form_day = None
    peak_tsb = -999.0

    for i in range(1, days + 1):
        ctl = ctl + (tss - ctl) * _CTL_DECAY
        atl = atl + (tss - atl) * _ATL_DECAY
        tsb = ctl - atl

        d_iso = (date.today() + timedelta(days=i)).isoformat()

        if tsb > peak_tsb:
            peak_tsb      = tsb
            peak_form_day = {"day_offset": i, "date_iso": d_iso, "tsb": round(tsb, 1)}

        form_label = _tsb_form_label(tsb)

        projection.append({
            "day_offset": i,
            "date_iso":   d_iso,
            "ctl":        round(ctl, 1),
            "atl":        round(atl, 1),
            "tsb":        round(tsb, 1),
            "form_label": form_label,
        })

    return {
        "planned_tss_per_day": tss,
        "days":                days,
        "current_ctl":         round(float(latest_tl.ctl or 40), 1) if latest_tl else 40.0,
        "current_atl":         round(float(latest_tl.atl or 45), 1) if latest_tl else 45.0,
        "current_tsb":         round(float((latest_tl.tsb or -5)), 1) if latest_tl else -5.0,
        "projection":          projection,
        "peak_form_window":    peak_form_day,
        "generated_at":        today_iso,
    }


def _tsb_form_label(tsb: float) -> str:
    if tsb >= 15:  return "Forma Pico"
    if tsb >= 5:   return "Buena Forma"
    if tsb >= -5:  return "Neutro"
    if tsb >= -15: return "Fatiga Moderada"
    if tsb >= -25: return "Fatiga Alta"
    return "Sobrecarga"


# ─────────────────────────────────────────────────────────────────────────────
# 7. RAMP RATE RISK (Sprint 25)
# ─────────────────────────────────────────────────────────────────────────────

def compute_ramp_rate_risk(
    user_id: str,
    db:      Session,
) -> dict:
    """
    Calcula la tasa de rampa semanal de la carga de entrenamiento y
    estima el riesgo de lesión por sobrecarga.

    Método: ACWR (Acute:Chronic Workload Ratio) de Gabbett (2016).
    - Carga aguda: TSS promedio últimos 7 días
    - Carga crónica: TSS promedio últimos 28 días
    - ACWR = aguda / crónica
    - Riesgo:
        ACWR < 0.8  → Carga insuficiente (desentrenamiento)
        0.8-1.3     → Zona segura
        1.3-1.5     → Zona gris (monitorear)
        > 1.5       → Riesgo elevado de lesión

    También calcula ramp rate % semanal de CTL.
    """
    today = date.today()
    cutoff_7d  = (today - timedelta(days=7)).isoformat()
    cutoff_28d = (today - timedelta(days=28)).isoformat()
    cutoff_35d = (today - timedelta(days=35)).isoformat()

    # TSS diario últimos 35 días desde GarminTrainingLoad
    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso >= cutoff_35d,
        )
        .order_by(GarminTrainingLoad.date_iso)
        .all()
    )

    tss_by_date = {tl.date_iso: (tl.tss_day or 0) for tl in loads}

    # Carga aguda y crónica por TSS
    acute_tss  = sum(tss_by_date.get((today - timedelta(days=i)).isoformat(), 0) for i in range(1, 8))
    chronic_tss = sum(tss_by_date.get((today - timedelta(days=i)).isoformat(), 0) for i in range(1, 29))

    acute_avg   = acute_tss  / 7.0
    chronic_avg = chronic_tss / 28.0

    acwr = round(acute_avg / chronic_avg, 2) if chronic_avg > 0 else 1.0

    if acwr < 0.8:
        risk_level = "Bajo (infracarga)"
        risk_color = "#22d3ee"
        risk_action = "Aumenta la carga gradualmente para mantener adaptación."
    elif acwr <= 1.3:
        risk_level = "Seguro"
        risk_color = "#10b981"
        risk_action = "Zona óptima de carga. Mantén el patrón actual."
    elif acwr <= 1.5:
        risk_level = "Moderado"
        risk_color = "#f59e0b"
        risk_action = "Reduce la intensidad o volumen esta semana para consolidar."
    else:
        risk_level = "Elevado"
        risk_color = "#ef4444"
        risk_action = "Riesgo real de lesión por sobrecarga. Prioriza recuperación."

    # Ramp rate CTL: diferencia CTL últimos 7 días vs CTL hace 7 días
    ctl_recent = next(
        (tl.ctl for tl in reversed(loads) if tl.ctl and tl.date_iso >= cutoff_7d), None
    )
    ctl_prev = next(
        (tl.ctl for tl in loads if tl.ctl and tl.date_iso < cutoff_7d), None
    )
    ctl_ramp_pct = None
    if ctl_recent and ctl_prev and ctl_prev > 0:
        ctl_ramp_pct = round((ctl_recent - ctl_prev) / ctl_prev * 100, 1)

    # 7-day TSS trend
    week_trend = [
        {
            "date_iso":  (today - timedelta(days=6-i)).isoformat(),
            "tss":       tss_by_date.get((today - timedelta(days=6-i)).isoformat(), 0),
        }
        for i in range(7)
    ]

    return {
        "acwr":           acwr,
        "acute_avg_tss":  round(acute_avg, 1),
        "chronic_avg_tss":round(chronic_avg, 1),
        "risk_level":     risk_level,
        "risk_color":     risk_color,
        "risk_action":    risk_action,
        "ctl_ramp_pct":   ctl_ramp_pct,
        "week_trend":     week_trend,
        "generated_at":   today.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. SEASON SUMMARY (Sprint 25)
# ─────────────────────────────────────────────────────────────────────────────

def compute_season_summary(
    user_id:     str,
    db:          Session,
    season_year: int = 0,
) -> dict:
    """
    Resumen anual del atleta: volumen total, CTL máximo, semanas consistentes,
    mejor período de forma, distribución por deporte, actividades destacadas.

    season_year=0 → año actual.
    """
    year = season_year if season_year > 2000 else date.today().year
    cutoff_start = f"{year}-01-01"
    cutoff_end   = f"{year}-12-31"

    activities = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id  == user_id,
            GarminActivity.date_iso >= cutoff_start,
            GarminActivity.date_iso <= cutoff_end,
        )
        .order_by(GarminActivity.date_iso)
        .all()
    )

    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso >= cutoff_start,
            GarminTrainingLoad.date_iso <= cutoff_end,
        )
        .order_by(GarminTrainingLoad.date_iso)
        .all()
    )

    total_activities  = len(activities)
    total_km          = round(sum(a.dist_km  or 0 for a in activities), 1)
    total_duration_h  = round(sum(a.dur_min  or 0 for a in activities) / 60, 1)
    total_tss         = round(sum(a.tss      or 0 for a in activities), 0)
    total_elevation_m = round(sum((a.elevation_gain_m or 0) for a in activities), 0)

    # Distribución por deporte
    sport_summary: dict[str, dict] = {}
    for a in activities:
        sp = a.sport or "other"
        if sp not in sport_summary:
            sport_summary[sp] = {"count": 0, "km": 0.0, "hours": 0.0, "tss": 0.0}
        sport_summary[sp]["count"] += 1
        sport_summary[sp]["km"]    += a.dist_km  or 0
        sport_summary[sp]["hours"] += (a.dur_min or 0) / 60
        sport_summary[sp]["tss"]   += a.tss      or 0

    for sp in sport_summary:
        sport_summary[sp]["km"]    = round(sport_summary[sp]["km"], 1)
        sport_summary[sp]["hours"] = round(sport_summary[sp]["hours"], 1)
        sport_summary[sp]["tss"]   = round(sport_summary[sp]["tss"], 0)

    # CTL máximo y fecha
    peak_ctl = None
    peak_ctl_date = None
    for tl in loads:
        if tl.ctl and (peak_ctl is None or tl.ctl > peak_ctl):
            peak_ctl      = round(tl.ctl, 1)
            peak_ctl_date = tl.date_iso

    # Semanas con al menos 3 actividades (consistency score)
    weeks_with_3plus = set()
    for a in activities:
        try:
            d = date.fromisoformat(a.date_iso)
            # ISO week key
            wk = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
            weeks_with_3plus.add(wk)  # acumular semanas
        except Exception:
            pass

    weekly_act_count: dict[str, int] = {}
    for a in activities:
        try:
            d = date.fromisoformat(a.date_iso)
            wk = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
            weekly_act_count[wk] = weekly_act_count.get(wk, 0) + 1
        except Exception:
            pass

    consistent_weeks = sum(1 for cnt in weekly_act_count.values() if cnt >= 3)
    total_weeks_in_year = max(1, (date.today() - date.fromisoformat(cutoff_start)).days // 7) if date.today().year == year else 52

    consistency_pct = round(consistent_weeks / total_weeks_in_year * 100, 1)

    # Actividad más larga y más dura
    longest_act = max(activities, key=lambda a: a.dur_min or 0, default=None)
    hardest_act = max(activities, key=lambda a: a.tss or 0, default=None)

    return {
        "year":             year,
        "total_activities": total_activities,
        "total_km":         total_km,
        "total_hours":      total_duration_h,
        "total_tss":        total_tss,
        "total_elevation_m":total_elevation_m,
        "sport_breakdown":  sport_summary,
        "peak_ctl":         peak_ctl,
        "peak_ctl_date":    peak_ctl_date,
        "consistent_weeks": consistent_weeks,
        "total_weeks_elapsed": total_weeks_in_year,
        "consistency_pct":  consistency_pct,
        "highlights": {
            "longest_session": {
                "sport":        longest_act.sport,
                "dur_min":      longest_act.dur_min,
                "dur_fmt":      _fmt_dur(longest_act.dur_min),
                "dist_km":      longest_act.dist_km,
                "date":         longest_act.date_iso,
            } if longest_act else None,
            "hardest_session": {
                "sport":    hardest_act.sport,
                "tss":      hardest_act.tss,
                "dur_min":  hardest_act.dur_min,
                "dur_fmt":  _fmt_dur(hardest_act.dur_min),
                "date":     hardest_act.date_iso,
            } if hardest_act else None,
        },
        "generated_at": date.today().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. AUTOMATED CROSS-MODULE INSIGHTS (Sprint 25)
# ─────────────────────────────────────────────────────────────────────────────

def generate_automated_insights(
    user_id: str,
    db:      Session,
) -> dict:
    """
    Genera insights automáticos cruzando todos los módulos de datos:
    Training Load + Blood Labs + Recovery + Mental + Nutrition.

    Reglas deterministas — sin LLM. Cada insight tiene:
      - category: performance | health | nutrition | mental | recovery | risk
      - severity: info | warning | critical
      - title
      - body
      - action
      - data_points: métricas que triggerearon el insight
    """
    from datetime import date, timedelta
    insights = []
    today = date.today()

    # ── Cargar datos ─────────────────────────────────────────────────────────

    # CTL/ATL/TSB últimas 2 semanas
    cutoff_14d = (today - timedelta(days=14)).isoformat()
    recent_loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso >= cutoff_14d,
        )
        .order_by(GarminTrainingLoad.date_iso.desc())
        .all()
    )

    latest_tl  = recent_loads[0]  if recent_loads else None
    ctl        = float(latest_tl.ctl  or 0) if latest_tl else 0
    atl        = float(latest_tl.atl  or 0) if latest_tl else 0
    tsb        = float(latest_tl.tsb  or 0) if latest_tl else 0
    tss_7d_avg = sum(float(tl.tss_day or 0) for tl in recent_loads[:7]) / max(len(recent_loads[:7]), 1)

    # ── INSIGHT: TSB muy negativo (fatiga acumulada) ─────────────────────────
    if tsb <= -20:
        insights.append({
            "category": "risk",
            "severity": "warning" if tsb > -30 else "critical",
            "title":    "Fatiga acumulada elevada",
            "body":     f"Tu TSB actual es {round(tsb, 1)}, indicando carga de fatiga que puede comprometer la calidad del entrenamiento y el riesgo de lesión.",
            "action":   "Considera 3-5 días de carga reducida (Z1-Z2 únicamente) antes de próximas sesiones de calidad.",
            "data":     {"tsb": round(tsb, 1), "ctl": round(ctl, 1), "atl": round(atl, 1)},
        })

    # ── INSIGHT: TSB positivo alto (pérdida de forma) ────────────────────────
    elif tsb >= 20:
        insights.append({
            "category": "performance",
            "severity": "info",
            "title":    "Riesgo de desentrenamiento",
            "body":     f"TSB = {round(tsb, 1)} indica que llevas varios días con carga muy baja. Perder forma ahora afectará la competición.",
            "action":   "Introduce una sesión de activación (85-90% FTP, 45-60min) para mantener el estímulo.",
            "data":     {"tsb": round(tsb, 1)},
        })

    # ── INSIGHT: CTL alto (fitness peak) ────────────────────────────────────
    if ctl >= 80:
        insights.append({
            "category": "performance",
            "severity": "info",
            "title":    f"Fitness histórico: CTL {round(ctl, 1)}",
            "body":     "Tu CTL actual refleja una base aeróbica sólida. Este es un buen momento para ciclos de alta calidad.",
            "action":   "Aprovecha para incorporar un bloque de intensidad (R o SFR) antes de la fase de tapering.",
            "data":     {"ctl": round(ctl, 1)},
        })

    # ── Datos de recuperación (últimos 3 días) ────────────────────────────────
    try:
        from ..models import RecoveryScore
        cutoff_3d = (today - timedelta(days=3)).isoformat()
        recent_recovery = (
            db.query(RecoveryScore)
            .filter(
                RecoveryScore.user_id  == user_id,
                RecoveryScore.date_iso >= cutoff_3d,
            )
            .order_by(RecoveryScore.date_iso.desc())
            .all()
        )
        if recent_recovery:
            avg_recovery = sum(r.score for r in recent_recovery) / len(recent_recovery)
            if avg_recovery < 45 and ctl > 50:
                insights.append({
                    "category": "recovery",
                    "severity": "warning",
                    "title":    "Recuperación insuficiente bajo carga alta",
                    "body":     f"Tu score de recuperación promedio ({round(avg_recovery, 0)}) es bajo mientras mantienes CTL alto ({round(ctl, 1)}). Esto aumenta el riesgo de sobreentrenamiento.",
                    "action":   "Prioriza sueño ≥8h, reduce cafeína vespertina y añade sesión de movilidad.",
                    "data":     {"recovery_avg": round(avg_recovery, 1), "ctl": round(ctl, 1)},
                })
    except Exception:
        pass

    # ── Blood Labs insights ───────────────────────────────────────────────────
    try:
        from ..models import BloodLabExam
        import json
        cutoff_90d = (today - timedelta(days=90)).isoformat()
        latest_exam = (
            db.query(BloodLabExam)
            .filter(
                BloodLabExam.user_id  == user_id,
                BloodLabExam.date_iso >= cutoff_90d,
            )
            .order_by(BloodLabExam.date_iso.desc())
            .first()
        )
        if latest_exam:
            try:
                vals = json.loads(latest_exam.values_json or "{}")
                ferritin = vals.get("ferritin")
                if ferritin is not None and float(ferritin) < 30:
                    insights.append({
                        "category": "health",
                        "severity": "critical" if float(ferritin) < 15 else "warning",
                        "title":    "Ferritina baja detectada en análisis",
                        "body":     f"Ferritina = {ferritin} ng/mL (último análisis: {latest_exam.date_iso}). La deficiencia de hierro reduce la capacidad aeróbica y el rendimiento en resistencia.",
                        "action":   "Consulta con tu médico deportivo. Considera suplementación de hierro con vitamina C en ayunas.",
                        "data":     {"ferritin": ferritin, "exam_date": latest_exam.date_iso},
                    })
                vitamin_d = vals.get("vitamin_d")
                if vitamin_d is not None and float(vitamin_d) < 30:
                    insights.append({
                        "category": "health",
                        "severity": "warning",
                        "title":    "Vitamina D insuficiente",
                        "body":     f"Vitamina D = {vitamin_d} ng/mL. Niveles < 30 se asocian con mayor incidencia de lesiones óseas y deterioro inmune.",
                        "action":   "2000-4000 UI/día de vitamina D3 con K2. Re-analizar en 90 días.",
                        "data":     {"vitamin_d": vitamin_d},
                    })
            except (json.JSONDecodeError, ValueError):
                pass
        else:
            # No hay labs en 90 días
            insights.append({
                "category": "health",
                "severity": "info",
                "title":    "Análisis de sangre pendiente",
                "body":     "No tienes análisis de laboratorio en los últimos 90 días. Para atletas en carga, se recomienda cada trimestre.",
                "action":   "Solicita análisis completo: hemograma, ferritina, vitamina D, cortisol, testosterona, TSH.",
                "data":     {},
            })
    except Exception:
        pass

    # ── Mental insights ───────────────────────────────────────────────────────
    try:
        from ..models import MentalFatigueScore
        cutoff_7d_iso = (today - timedelta(days=7)).isoformat()
        recent_mental = (
            db.query(MentalFatigueScore)
            .filter(
                MentalFatigueScore.user_id  == user_id,
                MentalFatigueScore.date_iso >= cutoff_7d_iso,
            )
            .order_by(MentalFatigueScore.date_iso.desc())
            .all()
        )
        if recent_mental:
            avg_mental = sum(m.score for m in recent_mental) / len(recent_mental)
            if avg_mental < 40:
                insights.append({
                    "category": "mental",
                    "severity": "warning",
                    "title":    "Fatiga mental acumulada",
                    "body":     f"Tu score de fatiga mental promedio esta semana es {round(avg_mental, 0)}/100. La fatiga mental aumenta el esfuerzo percibido y reduce la calidad de la sesión.",
                    "action":   "Reduce la carga cognitiva antes de sesiones clave. Prueba los protocolos de mindfulness en el módulo Mental.",
                    "data":     {"mental_avg": round(avg_mental, 1)},
                })
    except Exception:
        pass

    # ── Consistency insight (si lleva >2 semanas sin consistencia) ──────────
    if tss_7d_avg < 15 and ctl > 40:
        insights.append({
            "category": "performance",
            "severity": "info",
            "title":    "Semana de baja carga",
            "body":     f"TSS promedio esta semana: {round(tss_7d_avg, 0)}. Dado tu fitness base (CTL {round(ctl, 1)}), esta carga no genera adaptación.",
            "action":   "Si es semana de recuperación planificada, continúa. Si no, suma al menos 2 sesiones de calidad.",
            "data":     {"tss_7d_avg": round(tss_7d_avg, 1), "ctl": round(ctl, 1)},
        })

    # Ordenar por severidad: critical → warning → info
    _order = {"critical": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda i: _order.get(i["severity"], 3))

    return {
        "insights":       insights,
        "total_insights": len(insights),
        "critical_count": sum(1 for i in insights if i["severity"] == "critical"),
        "warning_count":  sum(1 for i in insights if i["severity"] == "warning"),
        "info_count":     sum(1 for i in insights if i["severity"] == "info"),
        "generated_at":   today.isoformat(),
    }


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_dur(minutes: float) -> str:
    """Formatea duración en minutos a h:mm:ss o mm:ss."""
    t = int(minutes * 60)
    h = t // 3600
    m = (t % 3600) // 60
    s = t % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace(pace_min_km: float) -> str:
    """Formatea pace en min/km a MM:SS."""
    total_s = int(pace_min_km * 60)
    return f"{total_s // 60}:{total_s % 60:02d}"
