"""
LabX Race Intelligence
======================
Motor de predicciÃ³n y estrategia de carrera para triatletas de resistencia.

Endpoints:
  GET    /races                        â€” Historial de carreras
  POST   /races                        â€” Registrar carrera
  GET    /races/{id}                   â€” Detalle + predicciÃ³n actual
  DELETE /races/{id}                   â€” Eliminar carrera
  PATCH  /races/{id}/result            â€” Registrar resultado real
  POST   /races/{id}/ai-briefing       â€” Generar briefing IA pre-carrera
  GET    /races/upcoming/taper-check   â€” SemÃ¡foro readiness 7 dÃ­as
  POST   /races/predict                â€” Calcular predicciÃ³n stateless (sin guardar)

Motor de predicciÃ³n:
  Swim: CSS pace / 100m Ã— distancia, ajustado por condiciones agua
  Bike: FÃ­sica potencia-aerodinÃ¡mica (Newton-Raphson) con IF por distancia
  Run:  Pace umbral ajustado por fatiga acumulada de la carrera
  Penalizaciones Labs:
    Ferritina < 30 ng/mL: -3 min/h de carrera
    Ferritina 30-50 ng/mL: -1 min/h de carrera
    Vitamina D < 20 ng/mL: -1.5% en potencia bike
    Cortisol > 22 Î¼g/dL: -2% global (seÃ±al overreaching)
    HbA1c > 5.7%: -0.5% global
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    BloodLabExam, GarminHealthDaily, GarminTrainingLoad,
    RaceEvent, User,
)
from ..auth import get_current_user

logger = logging.getLogger("labx.race")
router = APIRouter(prefix="/races", tags=["race_intelligence"])

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ConfiguraciÃ³n de distancias
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DIST_CONFIG = {
    "sprint":  {"label": "Sprint (750m/20km/5km)",     "swim_km": 0.75, "bike_km": 20,  "run_km": 5,    "t1_min": 1.5, "t2_min": 1.0, "bike_if": 0.88, "run_fatigue": 1.10},
    "olympic": {"label": "OlÃ­mpico (1.5km/40km/10km)", "swim_km": 1.5,  "bike_km": 40,  "run_km": 10,   "t1_min": 2.0, "t2_min": 1.5, "bike_if": 0.85, "run_fatigue": 1.05},
    "703":     {"label": "Ironman 70.3",                "swim_km": 1.9,  "bike_km": 90,  "run_km": 21.1, "t1_min": 3.5, "t2_min": 2.5, "bike_if": 0.80, "run_fatigue": 0.97},
    "full":    {"label": "Ironman 140.6",               "swim_km": 3.8,  "bike_km": 180, "run_km": 42.2, "t1_min": 5.0, "t2_min": 4.0, "bike_if": 0.73, "run_fatigue": 0.88},
    "21k":     {"label": "Media MaratÃ³n (21km)",        "swim_km": 0,    "bike_km": 0,   "run_km": 21.1, "t1_min": 0,   "t2_min": 0,   "bike_if": 0,    "run_fatigue": 0.95},
    "42k":     {"label": "MaratÃ³n (42km)",              "swim_km": 0,    "bike_km": 0,   "run_km": 42.2, "t1_min": 0,   "t2_min": 0,   "bike_if": 0,    "run_fatigue": 0.88},
}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Motor de predicciÃ³n
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _predict(
    dist:         str,
    ftp:          float,
    css_sec:      float,     # CSS en segundos/100m
    run_pace_sec: float,     # Pace umbral en segundos/km
    weight_kg:    float,
    tsb:          float,
    readiness:    int,
    labs_factors: dict,      # penalizaciones de Blood Labs
    cond_mult:    float = 1.0,
    temp_mult:    float = 1.0,
    wind_mult:    float = 1.0,
    elev_mult:    float = 1.0,
    water_mult:   float = 1.0,
) -> dict:
    """
    Calcula la predicciÃ³n completa de tiempo para una distancia de triatlÃ³n.
    Retorna dict con tiempos por disciplina, pacing targets y factores de ajuste.
    """
    cfg = DIST_CONFIG.get(dist)
    if not cfg:
        raise ValueError(f"Distancia desconocida: {dist}")

    # â”€â”€ Forma â†’ multiplicador global â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TSB entre -5 y +20 es el rango Ã³ptimo; fuera de ese rango penaliza
    tsb_mult = 1.0
    if tsb > 20:
        tsb_mult = 0.995   # muy fresco: rendimiento mÃ¡ximo
    elif tsb >= -5:
        tsb_mult = 1.0
    elif tsb >= -15:
        tsb_mult = 0.985   # algo de fatiga acumulada
    elif tsb >= -25:
        tsb_mult = 0.97    # fatigado
    else:
        tsb_mult = 0.95    # muy fatigado

    readiness_mult = 0.93 + (readiness / 100) * 0.07  # 0.93 (readiness=0) a 1.0 (readiness=100)

    # â”€â”€ Penalizaciones Blood Labs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    labs_mult = 1.0
    labs_notes = []

    ferritin = labs_factors.get("ferritin")
    if ferritin is not None:
        if ferritin < 30:
            # -3 min por hora de carrera â†’ aprox -5% tiempo total (en carreras largas)
            labs_mult *= 0.95
            labs_notes.append(f"Ferritina {ferritin:.0f} ng/mL (<30): -3 min/h estimados")
        elif ferritin < 50:
            labs_mult *= 0.98
            labs_notes.append(f"Ferritina {ferritin:.0f} ng/mL (30-50): -1 min/h estimados")

    vitamin_d = labs_factors.get("vitamin_d")
    if vitamin_d is not None and vitamin_d < 20:
        labs_mult *= 0.985
        labs_notes.append(f"Vitamina D {vitamin_d:.0f} ng/mL: -1.5% potencia bike")

    cortisol = labs_factors.get("cortisol")
    if cortisol is not None and cortisol > 22:
        labs_mult *= 0.98
        labs_notes.append(f"Cortisol {cortisol:.0f} Î¼g/dL (elevado): -2% global (overreaching)")

    hba1c = labs_factors.get("hba1c")
    if hba1c is not None and hba1c > 5.7:
        labs_mult *= 0.995
        labs_notes.append(f"HbA1c {hba1c:.1f}%: -0.5% eficiencia metabÃ³lica")

    hb = labs_factors.get("hb")
    if hb is not None:
        # Rangos: hombre >14.5 Ã³ptimo, <13.5 crÃ­tico
        if hb < 13.0:
            labs_mult *= 0.92
            labs_notes.append(f"Hemoglobina {hb:.1f} g/dL: reducciÃ³n severa transporte Oâ‚‚")
        elif hb < 14.0:
            labs_mult *= 0.97
            labs_notes.append(f"Hemoglobina {hb:.1f} g/dL: reducciÃ³n leve transporte Oâ‚‚")

    # â”€â”€ SWIM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    swim_sec = 0
    swim_pace_100m = None
    if cfg["swim_km"] > 0:
        swim_pace_s = css_sec / (water_mult * cond_mult * labs_mult)
        swim_sec    = round(cfg["swim_km"] * 10 * swim_pace_s)
        swim_pace_100m = swim_pace_s

    # â”€â”€ BIKE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    bike_sec = 0
    bike_np  = None
    bike_kmh = None
    if cfg["bike_km"] > 0:
        bike_cond = cond_mult * temp_mult * wind_mult * elev_mult * tsb_mult * readiness_mult * labs_mult
        np = ftp * cfg["bike_if"] * bike_cond

        # FÃ­sica aÃ©rodinÃ¡mica (Newton-Raphson)
        CdA  = 0.32   # posiciÃ³n TT mÂ²
        Crr  = 0.003
        rho  = 1.2
        mass = weight_kg + 8
        A    = Crr * mass * 9.81
        B    = 0.5 * rho * CdA
        v    = 8.5  # m/s initial guess
        for _ in range(60):
            F  = B * v**3 + A * v - np
            dF = 3 * B * v**2 + A
            v  = max(0.5, v - F / dF)

        bike_kmh = v * 3.6
        bike_sec = round(cfg["bike_km"] / bike_kmh * 3600)
        bike_np  = round(np)

    # â”€â”€ RUN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    run_pace_s = run_pace_sec / (cfg["run_fatigue"] * cond_mult * temp_mult * labs_mult)
    run_sec    = round(cfg["run_km"] * run_pace_s)

    # â”€â”€ TRANSITIONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    t1_sec = round(cfg["t1_min"] * 60)
    t2_sec = round(cfg["t2_min"] * 60)

    total_sec = swim_sec + t1_sec + bike_sec + t2_sec + run_sec

    # â”€â”€ Banda de confianza â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    uncertainty = 0.02 + (1.0 - readiness / 100) * 0.04 + (len(labs_notes) * 0.005)
    conf_pct    = max(55, min(95, round(70 + readiness * 0.25 - len(labs_notes) * 3)))

    return {
        "swim_sec":        swim_sec,
        "t1_sec":          t1_sec,
        "bike_sec":        bike_sec,
        "t2_sec":          t2_sec,
        "run_sec":         run_sec,
        "total_sec":       total_sec,
        "swim_pace_100m":  swim_pace_100m,
        "bike_np_watts":   bike_np,
        "bike_kmh":        round(bike_kmh, 1) if bike_kmh else None,
        "run_pace_per_km": run_pace_s,
        "bike_if":         cfg["bike_if"],
        "uncertainty_pct": round(uncertainty * 100, 1),
        "confidence_pct":  conf_pct,
        "tsb_mult":        round(tsb_mult, 3),
        "readiness_mult":  round(readiness_mult, 3),
        "labs_mult":       round(labs_mult, 3),
        "labs_notes":      labs_notes,
        "range_low_sec":   round(total_sec * (1 - uncertainty)),
        "range_high_sec":  round(total_sec * (1 + uncertainty)),
    }


def _fmt_hms(seconds: int) -> str:
    """Formatea segundos como H:MM:SS."""
    if not seconds:
        return "0:00:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"


def _fmt_ms(seconds: float) -> str:
    """Formatea segundos como MM:SS."""
    if not seconds:
        return "0:00"
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _get_athlete_params(user: User, db: Session) -> dict:
    """
    Extrae los parÃ¡metros de predicciÃ³n del atleta:
    FTP, CSS, run_pace, weight, CTL actual, TSB actual, readiness, Blood Labs.
    """
    params: dict = {}

    # Perfil base
    params["ftp"]    = user.ftp    or 200
    params["weight"] = user.weight_kg or 70
    params["fcmax"]  = user.fcmax  or 170

    # CSS: convertir de string "1:30" a segundos
    css_sec = 90.0  # default 1:30/100m
    if user.css:
        parts = str(user.css).split(":")
        try:
            if len(parts) == 2:
                css_sec = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 1:
                css_sec = float(parts[0])
        except (ValueError, IndexError):
            pass
    params["css_sec"] = css_sec

    # Run pace umbral (en segundos/km)
    run_pace_sec = 300.0  # default 5:00/km
    if user.run_pace:
        parts = str(user.run_pace).split(":")
        try:
            if len(parts) == 2:
                run_pace_sec = int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            pass
    params["run_pace_sec"] = run_pace_sec

    # CTL/TSB actual
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user.id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    params["ctl"]      = round(load.ctl, 1) if load and load.ctl else 50.0
    params["atl"]      = round(load.atl, 1) if load and load.atl else 50.0
    params["tsb"]      = round(load.tsb, 1) if load and load.tsb else 0.0

    # Readiness desde context
    from ..models import AIAthleteContext
    ctx = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == user.id).first()
    params["readiness"] = ctx.current_readiness or 70 if ctx else 70

    # Blood Labs mÃ¡s reciente (Ãºltimos 90 dÃ­as)
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    latest_labs = (
        db.query(BloodLabExam)
        .filter(
            BloodLabExam.user_id == user.id,
            BloodLabExam.date_iso >= cutoff,
        )
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )
    labs_factors: dict = {}
    labs_date = None
    if latest_labs:
        try:
            vals = json.loads(latest_labs.values_json)
            for key in ["ferritin", "vitamin_d", "cortisol", "hba1c", "hb", "hct"]:
                if key in vals and vals[key] is not None:
                    labs_factors[key] = float(vals[key])
        except Exception:
            pass
        labs_date = latest_labs.date_iso
    params["labs_factors"] = labs_factors
    params["labs_date"]    = labs_date

    return params


def _tsb_on_date(user_id: str, target_date: str, db: Session) -> Optional[float]:
    """
    Proyecta el TSB en una fecha futura basÃ¡ndose en la tendencia del CTL.
    Modelo simple: TSB â‰ˆ CTL actual Ã— 0.15 por semana de taper.
    """
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    if not load:
        return None

    try:
        days_to_race = (date.fromisoformat(target_date) - date.today()).days
    except Exception:
        return None

    if days_to_race <= 0:
        return round(load.tsb, 1) if load.tsb else None

    # En taper: CTL baja lentamente, ATL baja mÃ¡s rÃ¡pido â†’ TSB sube
    # SimplificaciÃ³n: TSB proyectado â‰ˆ TSB_actual + (CTL Ã— 0.04 Ã— semanas_taper)
    taper_weeks = min(days_to_race / 7, 3)  # max 3 semanas de taper en el modelo
    tsb_proj    = (load.tsb or 0) + (load.ctl or 50) * 0.04 * taper_weeks
    return round(tsb_proj, 1)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Endpoints
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/predict")
def predict_stateless(
    body: dict,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Calcula una predicciÃ³n on-the-fly sin persistir.
    Ãštil para el predictor interactivo mientras el usuario ajusta condiciones.

    Body: {
      distance: str,
      cond_mult?: float,   temp_mult?, wind_mult?, elev_mult?, water_mult?
      tsb_override?: float  (para simular condiciones de llegada)
    }
    """
    dist = body.get("distance", "703")
    if dist not in DIST_CONFIG:
        raise HTTPException(422, f"Distancia invÃ¡lida. Opciones: {list(DIST_CONFIG.keys())}")

    params = _get_athlete_params(me, db)

    result = _predict(
        dist         = dist,
        ftp          = params["ftp"],
        css_sec      = params["css_sec"],
        run_pace_sec = params["run_pace_sec"],
        weight_kg    = params["weight"],
        tsb          = body.get("tsb_override", params["tsb"]),
        readiness    = params["readiness"],
        labs_factors = params["labs_factors"],
        cond_mult    = body.get("cond_mult", 1.0),
        temp_mult    = body.get("temp_mult", 1.0),
        wind_mult    = body.get("wind_mult", 1.0),
        elev_mult    = body.get("elev_mult", 1.0),
        water_mult   = body.get("water_mult", 1.0),
    )

    return {
        "distance":      dist,
        "distance_label": DIST_CONFIG[dist]["label"],
        "total_sec":     result["total_sec"],
        "total_fmt":     _fmt_hms(result["total_sec"]),
        "splits": {
            "swim": {"sec": result["swim_sec"], "fmt": _fmt_ms(result["swim_sec"]),
                     "pace_100m": _fmt_ms(result["swim_pace_100m"]) if result.get("swim_pace_100m") else None},
            "t1":   {"sec": result["t1_sec"],   "fmt": _fmt_ms(result["t1_sec"])},
            "bike": {"sec": result["bike_sec"], "fmt": _fmt_hms(result["bike_sec"]),
                     "np_watts": result.get("bike_np_watts"), "kmh": result.get("bike_kmh")},
            "t2":   {"sec": result["t2_sec"],   "fmt": _fmt_ms(result["t2_sec"])},
            "run":  {"sec": result["run_sec"],  "fmt": _fmt_hms(result["run_sec"]),
                     "pace_km": _fmt_ms(result["run_pace_per_km"]) if result.get("run_pace_per_km") else None},
        },
        "confidence_pct":  result["confidence_pct"],
        "uncertainty_pct": result["uncertainty_pct"],
        "range_low":       _fmt_hms(result["range_low_sec"]),
        "range_high":      _fmt_hms(result["range_high_sec"]),
        "labs_notes":      result["labs_notes"],
        "labs_date":       params["labs_date"],
        "athlete": {
            "ftp":      params["ftp"],
            "ctl":      params["ctl"],
            "tsb":      params["tsb"],
            "readiness": params["readiness"],
        }
    }


@router.post("")
def create_race(
    body: dict,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Registra una carrera y guarda la predicciÃ³n actual como snapshot.

    Body:
      name:         str  (requerido)
      date_iso:     YYYY-MM-DD (requerido)
      distance:     sprint|olympic|703|full|21k|42k
      location:     str (opcional)
      is_goal_race: bool
      distance_custom: dict con swim_km, bike_km, run_km (si distance='custom')
    """
    name         = (body.get("name") or "").strip()
    date_iso     = (body.get("date_iso") or "").strip()
    distance     = body.get("distance", "703")
    location     = (body.get("location") or "").strip() or None
    is_goal_race = bool(body.get("is_goal_race", False))

    if not name:
        raise HTTPException(422, "name es requerido")
    if not date_iso:
        raise HTTPException(422, "date_iso es requerido")
    if distance not in DIST_CONFIG:
        raise HTTPException(422, f"Distancia invÃ¡lida. Opciones: {list(DIST_CONFIG.keys())}")

    # Calcular predicciÃ³n actual como snapshot
    params = _get_athlete_params(me, db)

    # TSB proyectado para el dÃ­a de carrera
    tsb_proj = _tsb_on_date(me.id, date_iso, db) or params["tsb"]

    try:
        pred = _predict(
            dist         = distance,
            ftp          = params["ftp"],
            css_sec      = params["css_sec"],
            run_pace_sec = params["run_pace_sec"],
            weight_kg    = params["weight"],
            tsb          = tsb_proj,
            readiness    = params["readiness"],
            labs_factors = params["labs_factors"],
        )
    except Exception as e:
        logger.warning("Prediction error user=%s: %s", me.id, e)
        pred = None

    race = RaceEvent(
        user_id          = me.id,
        name             = name,
        date_iso         = date_iso,
        distance         = distance,
        location         = location,
        is_goal_race     = is_goal_race,
        pred_swim_sec    = pred["swim_sec"]    if pred else None,
        pred_bike_sec    = pred["bike_sec"]    if pred else None,
        pred_run_sec     = pred["run_sec"]     if pred else None,
        pred_t1_sec      = pred["t1_sec"]      if pred else None,
        pred_t2_sec      = pred["t2_sec"]      if pred else None,
        pred_total_sec   = pred["total_sec"]   if pred else None,
        pred_ctl_snapshot= params["ctl"],
        pred_tsb_projected= tsb_proj,
        pred_factors_json = json.dumps({
            "labs_notes":   pred["labs_notes"]   if pred else [],
            "labs_date":    params["labs_date"],
            "labs_factors": params["labs_factors"],
            "confidence":   pred["confidence_pct"] if pred else None,
        }, ensure_ascii=False) if pred else None,
    )
    db.add(race)

    # Si es meta A, actualizar race_goal en el perfil del usuario
    if is_goal_race:
        me.race_goal_name = name
        me.race_goal_date = date_iso
        me.race_goal_dist = distance

    db.commit()
    logger.info("RaceEvent creado user=%s race=%s dist=%s date=%s", me.id, race.id, distance, date_iso)

    return {
        "ok":        True,
        "race_id":   race.id,
        "pred_total": _fmt_hms(pred["total_sec"]) if pred else None,
        "labs_notes": pred["labs_notes"] if pred else [],
    }


@router.get("")
def list_races(
    include_past: bool = Query(True),
    limit:        int  = Query(30, ge=1, le=100),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Lista las carreras del atleta, mÃ¡s recientes primero."""
    q = db.query(RaceEvent).filter(RaceEvent.user_id == me.id)
    if not include_past:
        q = q.filter(RaceEvent.date_iso >= date.today().isoformat())
    races = q.order_by(RaceEvent.date_iso.desc()).limit(limit).all()

    result = []
    for r in races:
        days_to = None
        try:
            days_to = (date.fromisoformat(r.date_iso) - date.today()).days
        except Exception:
            pass

        result.append({
            "id":            r.id,
            "name":          r.name,
            "date_iso":      r.date_iso,
            "distance":      r.distance,
            "distance_label": DIST_CONFIG.get(r.distance, {}).get("label", r.distance),
            "location":      r.location,
            "is_goal_race":  r.is_goal_race,
            "days_to_race":  days_to,
            "pred_total":    _fmt_hms(r.pred_total_sec) if r.pred_total_sec else None,
            "actual_total":  _fmt_hms(r.actual_total_sec) if r.actual_total_sec else None,
            "is_pr":         r.is_pr,
            "has_briefing":  bool(r.ai_briefing_text),
            "completed":     r.actual_total_sec is not None,
        })
    return result


@router.get("/upcoming/taper-check")
def taper_check(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    SemÃ¡foro de readiness para la prÃ³xima carrera (D-7 a D-0).
    Muestra el estado de forma + HRV + readiness para cada uno de los
    7 dÃ­as previos a la carrera mÃ¡s prÃ³xima.
    """
    today = date.today()

    # Carrera mÃ¡s prÃ³xima en el futuro
    next_race = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == me.id,
            RaceEvent.date_iso >= today.isoformat(),
            RaceEvent.actual_total_sec.is_(None),   # no completada
        )
        .order_by(RaceEvent.date_iso)
        .first()
    )

    if not next_race:
        return {"has_race": False}

    try:
        race_date  = date.fromisoformat(next_race.date_iso)
        days_to    = (race_date - today).days
    except Exception:
        return {"has_race": False}

    # Ãšltimos 7 dÃ­as de HRV y readiness
    week_ago = (today - timedelta(days=7)).isoformat()
    health_rows = {
        h.date_iso: h
        for h in db.query(GarminHealthDaily).filter(
            GarminHealthDaily.user_id  == me.id,
            GarminHealthDaily.date_iso >= week_ago,
        ).all()
    }

    # CTL/TSB actuales
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == me.id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    ctl = round(load.ctl, 1) if load and load.ctl else None
    tsb = round(load.tsb, 1) if load and load.tsb else None
    tsb_proj = _tsb_on_date(me.id, next_race.date_iso, db)

    # SemÃ¡foro: evaluar readiness de los Ãºltimos 7 dÃ­as
    semaphore = []
    for i in range(7, -1, -1):
        d     = today - timedelta(days=i)
        d_iso = d.isoformat()
        h     = health_rows.get(d_iso)

        hrv       = h.hrv_last_night   if h else None
        bb        = h.body_battery_end  if h else None
        sleep_s   = h.sleep_score       if h else None
        readiness = h.labx_readiness_score if h else None

        # Status: verde si readiness > 70, amarillo 50-70, rojo < 50
        if readiness is not None:
            status = "optimal" if readiness >= 70 else "caution" if readiness >= 50 else "critical"
        elif hrv is not None and bb is not None:
            score = (hrv / 60 * 50) + (bb / 100 * 50)  # proxy score
            status = "optimal" if score >= 60 else "caution" if score >= 40 else "critical"
        else:
            status = "unknown"

        semaphore.append({
            "date_iso":  d_iso,
            "is_today":  d == today,
            "day_label": ["Lun","Mar","MiÃ©","Jue","Vie","SÃ¡b","Dom"][d.weekday()],
            "hrv":       round(hrv, 1) if hrv else None,
            "body_battery": bb,
            "sleep_score":  sleep_s,
            "readiness":    readiness,
            "status":       status,
        })

    # RecomendaciÃ³n global para el taper
    recent_scores = [s["readiness"] for s in semaphore[-3:] if s["readiness"] is not None]
    avg_readiness = sum(recent_scores) / len(recent_scores) if recent_scores else None

    rec = "Sin datos suficientes para recomendaciÃ³n"
    if avg_readiness is not None:
        if avg_readiness >= 70:
            rec = f"Readiness promedio {avg_readiness:.0f}/100. Forma excelente para la carrera. MantÃ©n el taper ligero."
        elif avg_readiness >= 55:
            rec = f"Readiness promedio {avg_readiness:.0f}/100. Forma moderada. Prioriza sueÃ±o y evita estrÃ©s esta semana."
        else:
            rec = f"Readiness promedio {avg_readiness:.0f}/100. Forma baja. Considera ajustar el taper y consultar con tu coach."

    return {
        "has_race":       True,
        "race_id":        next_race.id,
        "race_name":      next_race.name,
        "race_date":      next_race.date_iso,
        "days_to_race":   days_to,
        "distance":       next_race.distance,
        "ctl":            ctl,
        "tsb_current":    tsb,
        "tsb_projected":  tsb_proj,
        "semaphore":      semaphore,
        "recommendation": rec,
        "avg_readiness":  round(avg_readiness, 1) if avg_readiness else None,
    }


@router.get("/dashboard-s19")
def race_dashboard_s19(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Sprint 19 — Race Day Dashboard: next race + fitness + plan + history.

    Registrado antes de /{race_id} a propósito: si va después, FastAPI
    matchea "dashboard-s19" como race_id y este endpoint nunca es alcanzable.
    """
    from ..models import RecoveryScore, RacePlan, RaceResult as _RR
    today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()

    next_race = (
        db.query(RaceEvent)
        .filter(RaceEvent.user_id == me.id, RaceEvent.date_iso >= today)
        .order_by(RaceEvent.date_iso.asc()).first()
    )
    days_to_race = None
    if next_race:
        days_to_race = (datetime.strptime(next_race.date_iso, "%Y-%m-%d").date()
                        - datetime.now(timezone.utc).replace(tzinfo=None).date()).days

    load = (db.query(GarminTrainingLoad)
            .filter_by(user_id=me.id)
            .order_by(GarminTrainingLoad.date_iso.desc()).first())
    rec  = db.query(RecoveryScore).filter_by(user_id=me.id, date_iso=today).first()

    plan = None
    if next_race:
        try:
            plan = (db.query(RacePlan)
                    .filter_by(user_id=me.id, race_event_id=next_race.id)
                    .order_by(RacePlan.generated_at.desc()).first())
        except Exception:
            pass

    history = []
    try:
        results = (db.query(_RR).filter_by(user_id=me.id)
                   .order_by(_RR.created_at.desc()).limit(5).all())
        for r in results:
            evt = db.query(RaceEvent).filter_by(id=r.race_event_id).first() if r.race_event_id else None
            history.append({
                "race_name": evt.name if evt else "Carrera",
                "total_fmt": _fmt_t(r.total_time_s),
                "total_time_s": r.total_time_s,
                "distance": evt.distance if evt else None,
                "pacing_score": r.pacing_score,
                "dnf": r.dnf,
            })
    except Exception:
        pass

    return {
        "next_race": {
            "id": next_race.id if next_race else None,
            "name": next_race.name if next_race else None,
            "date": next_race.date_iso if next_race else None,
            "distance": next_race.distance if next_race else None,
            "days_to_race": days_to_race,
            "has_plan": plan is not None,
        },
        "fitness": {
            "ctl": round(load.ctl, 1) if load and load.ctl else None,
            "tsb": round(load.tsb, 1) if load and load.tsb else None,
            "atl": round(load.atl, 1) if load and load.atl else None,
            "recovery_score": rec.score if rec else None,
        },
        "plan": {
            "total_fmt": _fmt_t(plan.total_pred_s) if plan else None,
            "bike_power": plan.bike_target_power if plan else None,
            "run_pace": _fmt_pace(plan.run_target_pace) if plan else None,
        },
        "history": history,
    }


@router.get("/{race_id}")
def get_race(
    race_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    """Detalle completo de una carrera con predicciÃ³n actualizada."""
    race = db.query(RaceEvent).filter(
        RaceEvent.id      == race_id,
        RaceEvent.user_id == me.id,
    ).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")

    # PredicciÃ³n ACTUAL (puede diferir del snapshot si el atleta mejorÃ³)
    params   = _get_athlete_params(me, db)
    tsb_proj = _tsb_on_date(me.id, race.date_iso, db) or params["tsb"]

    try:
        pred_now = _predict(
            dist         = race.distance or "703",
            ftp          = params["ftp"],
            css_sec      = params["css_sec"],
            run_pace_sec = params["run_pace_sec"],
            weight_kg    = params["weight"],
            tsb          = tsb_proj,
            readiness    = params["readiness"],
            labs_factors = params["labs_factors"],
        )
    except Exception:
        pred_now = None

    days_to = None
    try:
        days_to = (date.fromisoformat(race.date_iso) - date.today()).days
    except Exception:
        pass

    factors_saved = {}
    if race.pred_factors_json:
        try:
            factors_saved = json.loads(race.pred_factors_json)
        except Exception:
            pass

    # AnÃ¡lisis post-carrera si hay resultado real
    post_race = None
    if race.actual_total_sec and race.pred_total_sec:
        diff_sec = race.actual_total_sec - race.pred_total_sec
        post_race = {
            "diff_sec":  diff_sec,
            "diff_fmt":  ("+" if diff_sec >= 0 else "") + _fmt_hms(abs(diff_sec)),
            "faster":    diff_sec < 0,
            "accuracy_pct": round(abs(diff_sec) / race.pred_total_sec * 100, 1),
        }

    return {
        "id":            race.id,
        "name":          race.name,
        "date_iso":      race.date_iso,
        "distance":      race.distance,
        "distance_label": DIST_CONFIG.get(race.distance, {}).get("label", race.distance),
        "location":      race.location,
        "is_goal_race":  race.is_goal_race,
        "days_to_race":  days_to,

        "prediction_now": {
            "total_sec":   pred_now["total_sec"]     if pred_now else None,
            "total_fmt":   _fmt_hms(pred_now["total_sec"]) if pred_now else None,
            "swim_sec":    pred_now["swim_sec"]       if pred_now else None,
            "bike_sec":    pred_now["bike_sec"]       if pred_now else None,
            "run_sec":     pred_now["run_sec"]        if pred_now else None,
            "bike_np":     pred_now["bike_np_watts"]  if pred_now else None,
            "bike_kmh":    pred_now["bike_kmh"]       if pred_now else None,
            "swim_pace":   _fmt_ms(pred_now["swim_pace_100m"]) if pred_now and pred_now.get("swim_pace_100m") else None,
            "run_pace":    _fmt_ms(pred_now["run_pace_per_km"]) if pred_now and pred_now.get("run_pace_per_km") else None,
            "confidence":  pred_now["confidence_pct"] if pred_now else None,
            "labs_notes":  pred_now["labs_notes"]     if pred_now else [],
            "tsb_used":    tsb_proj,
        } if pred_now else None,

        "prediction_snapshot": {
            "total_sec":  race.pred_total_sec,
            "total_fmt":  _fmt_hms(race.pred_total_sec) if race.pred_total_sec else None,
            "ctl":        race.pred_ctl_snapshot,
            "tsb_proj":   race.pred_tsb_projected,
            "factors":    factors_saved,
        },

        "actual": {
            "swim_sec":   race.actual_swim_sec,
            "bike_sec":   race.actual_bike_sec,
            "run_sec":    race.actual_run_sec,
            "t1_sec":     race.actual_t1_sec,
            "t2_sec":     race.actual_t2_sec,
            "total_sec":  race.actual_total_sec,
            "total_fmt":  _fmt_hms(race.actual_total_sec) if race.actual_total_sec else None,
            "notes":      race.actual_notes,
            "is_pr":      race.is_pr,
        } if race.actual_total_sec else None,

        "post_race_analysis": post_race,
        "ai_briefing":        race.ai_briefing_text,
        "ai_briefing_at":     race.ai_briefing_at.isoformat() if race.ai_briefing_at else None,
    }


@router.patch("/{race_id}/result")
def save_race_result(
    race_id: str,
    body:    dict,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    """
    Guarda el resultado real de una carrera completada.

    Body:
      swim_sec, bike_sec, run_sec, t1_sec, t2_sec (alguno o todos)
      notes: str
      is_pr: bool
    """
    race = db.query(RaceEvent).filter(
        RaceEvent.id      == race_id,
        RaceEvent.user_id == me.id,
    ).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")

    race.actual_swim_sec = body.get("swim_sec")
    race.actual_bike_sec = body.get("bike_sec")
    race.actual_run_sec  = body.get("run_sec")
    race.actual_t1_sec   = body.get("t1_sec")
    race.actual_t2_sec   = body.get("t2_sec")

    # Total calculado de los splits si no viene explÃ­cito
    provided_total = body.get("total_sec")
    if provided_total:
        race.actual_total_sec = provided_total
    else:
        parts = [
            race.actual_swim_sec or 0,
            race.actual_t1_sec   or 0,
            race.actual_bike_sec or 0,
            race.actual_t2_sec   or 0,
            race.actual_run_sec  or 0,
        ]
        race.actual_total_sec = sum(parts) if any(parts) else None

    race.actual_notes = (body.get("notes") or "").strip() or None
    race.is_pr        = bool(body.get("is_pr", False))

    db.commit()

    diff_sec = None
    if race.actual_total_sec and race.pred_total_sec:
        diff_sec = race.actual_total_sec - race.pred_total_sec

    logger.info("RaceResult guardado user=%s race=%s total=%s", me.id, race_id, race.actual_total_sec)

    return {
        "ok":           True,
        "actual_total": _fmt_hms(race.actual_total_sec) if race.actual_total_sec else None,
        "pred_total":   _fmt_hms(race.pred_total_sec)   if race.pred_total_sec   else None,
        "diff_sec":     diff_sec,
        "diff_fmt":     (("+" if diff_sec >= 0 else "") + _fmt_hms(abs(diff_sec))) if diff_sec is not None else None,
        "is_pr":        race.is_pr,
    }


@router.post("/{race_id}/ai-briefing")
def generate_ai_briefing(
    race_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    """
    Genera un briefing completo pre-carrera con el Coach IA de LabX.
    Incluye:
    - EvaluaciÃ³n de la preparaciÃ³n actual (CTL/TSB/HRV/Labs)
    - Estrategia de pacing por disciplina
    - Plan de nutriciÃ³n de carrera
    - Puntos clave de ejecuciÃ³n
    - Riesgos identificados y cÃ³mo mitigarlos
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY no configurada")

    race = db.query(RaceEvent).filter(
        RaceEvent.id      == race_id,
        RaceEvent.user_id == me.id,
    ).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")

    params   = _get_athlete_params(me, db)
    tsb_proj = _tsb_on_date(me.id, race.date_iso, db) or params["tsb"]
    cfg      = DIST_CONFIG.get(race.distance or "703", DIST_CONFIG["703"])

    # Calcular predicciÃ³n para el briefing
    try:
        pred = _predict(
            dist         = race.distance or "703",
            ftp          = params["ftp"],
            css_sec      = params["css_sec"],
            run_pace_sec = params["run_pace_sec"],
            weight_kg    = params["weight"],
            tsb          = tsb_proj,
            readiness    = params["readiness"],
            labs_factors = params["labs_factors"],
        )
    except Exception:
        pred = None

    # Contexto completo del atleta
    from ..services.context_engine import get_context_for_prompt
    athlete_context = get_context_for_prompt(me.id, db)

    days_to = None
    try:
        days_to = (date.fromisoformat(race.date_iso) - date.today()).days
    except Exception:
        pass

    pred_total  = _fmt_hms(pred["total_sec"]) if pred else "No disponible"
    swim_target = _fmt_ms(pred["swim_pace_100m"]) if pred and pred.get("swim_pace_100m") else "â€”"
    bike_target = f"{pred['bike_np_watts']}W NP ({pred['bike_kmh']} km/h)" if pred and pred.get("bike_np_watts") else "â€”"
    run_target  = _fmt_ms(pred["run_pace_per_km"]) + "/km" if pred and pred.get("run_pace_per_km") else "â€”"
    labs_notes  = "\n".join(f"  âš  {n}" for n in (pred["labs_notes"] if pred else [])) or "  Sin penalizaciones de laboratorio"

    prompt = f"""Eres el Director TÃ©cnico de LabX â€” el coach mÃ¡s avanzado de triatlÃ³n que existe.
Tienes acceso completo al perfil fisiolÃ³gico, historial de entrenamiento y anÃ¡lisis de sangre del atleta.

CONTEXTO DEL ATLETA:
{athlete_context}

CARRERA:
  Nombre: {race.name}
  Fecha: {race.date_iso} (D-{days_to if days_to is not None else '?'})
  Distancia: {cfg['label']}
  Lugar: {race.location or 'No especificado'}

PREDICCIÃ“N ACTUAL:
  Tiempo total estimado: {pred_total}
  ðŸŠ NataciÃ³n: {swim_target}/100m
  ðŸš´ Bike: {bike_target}
  ðŸƒ Run: {run_target}/km
  Confianza: {pred['confidence_pct']}% Â± {pred['uncertainty_pct']}%

FACTORES QUE AFECTAN LA PREDICCIÃ“N:
{labs_notes}

GENERA UN BRIEFING PRE-CARRERA COMPLETO EN ESPAÃ‘OL que incluya:

**1. EVALUACIÃ“N DE LA PREPARACIÃ“N** (Â¿El atleta estÃ¡ listo? Â¿QuÃ© seÃ±ales positivas y negativas hay?)

**2. ESTRATEGIA DE CARRERA** (pacing especÃ­fico con los nÃºmeros de este atleta â€” no genÃ©rico)
   - NataciÃ³n: pace objetivo, estrategia de posicionamiento
   - Bike: watts objetivo, zonas, cuÃ¡ndo presionar y cuÃ¡ndo conservar
   - Run: pace objetivo por segmentos (primera mitad mÃ¡s conservador)
   - Transiciones: quÃ© priorizar

**3. PLAN DE NUTRICIÃ“N** (calculado para el tiempo estimado de carrera)
   - Carbohidratos/hora
   - Sodio/hora
   - HidrataciÃ³n (ml/h)
   - Timing: primeros 30 min, cada hora, Ãºltimos 30 min

**4. RIESGOS Y MITIGACIONES** (especÃ­ficos a los datos de este atleta)

**5. MENTAL Y EJECUCIÃ“N** (3 puntos clave para el dÃ­a de carrera)

**6. OBJETIVO REALISTA** (rango A/B/C de tiempos)

SÃ© especÃ­fico, usa los nÃºmeros del atleta, sÃ© directo. Sin rodeos. El atleta confÃ­a en tu criterio tÃ©cnico.
"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp   = client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 2000,
            messages   = [{"role": "user", "content": prompt}],
        )
        briefing = resp.content[0].text if resp.content else ""
    except Exception as e:
        logger.error("AI briefing error user=%s race=%s: %s", me.id, race_id, e)
        raise HTTPException(502, "Error al generar briefing IA")

    race.ai_briefing_text = briefing
    race.ai_briefing_at   = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    logger.info("AI briefing generado user=%s race=%s tokens=%d",
                me.id, race_id, resp.usage.input_tokens + resp.usage.output_tokens)

    return {"ok": True, "briefing": briefing}


@router.get("/{race_id}/post-race-analysis")
def get_post_race_analysis(
    race_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    AnÃ¡lisis post-carrera: gap por disciplina, factores limitantes fisiolÃ³gicos,
    performance index y recomendaciones para prÃ³xima carrera.
    Requiere que el resultado real haya sido guardado via PATCH /races/{id}/result.
    """
    race = db.query(RaceEvent).filter(
        RaceEvent.id      == race_id,
        RaceEvent.user_id == me.id,
    ).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")
    if not race.actual_total_sec:
        raise HTTPException(400, "No hay resultado real registrado para esta carrera. "
                                 "Guarda el tiempo real con PATCH /races/{id}/result primero.")

    from ..services.post_race_service import analyze_race
    analysis = analyze_race(race, db)
    return analysis


@router.post("/{race_id}/post-race-ai")
async def post_race_ai_analysis(
    race_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Genera el anÃ¡lisis narrativo post-carrera con IA.
    Usa Claude Sonnet para carreras A (is_goal_race=True), Haiku para el resto.
    Guarda el texto en race_events.ai_post_race_text.
    """
    race = db.query(RaceEvent).filter(
        RaceEvent.id      == race_id,
        RaceEvent.user_id == me.id,
    ).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")
    if not race.actual_total_sec:
        raise HTTPException(400, "Guarda el resultado real primero (PATCH /races/{id}/result).")

    from ..services.post_race_service import analyze_race, generate_post_race_ai_analysis
    analysis = analyze_race(race, db)
    narrative = await generate_post_race_ai_analysis(
        race         = race,
        analysis     = analysis,
        user         = me,
        is_goal_race = bool(race.is_goal_race),
    )

    # Guardar en race_events
    try:
        from sqlalchemy import text as _text
        with db.get_bind().connect() as conn:
            conn.execute(_text(
                "ALTER TABLE race_events ADD COLUMN ai_post_race_text TEXT"
            ))
            conn.commit()
    except Exception:
        pass   # columna ya existe

    try:
        from sqlalchemy import text as _text
        db.execute(_text(
            "UPDATE race_events SET ai_post_race_text=:txt WHERE id=:id"
        ), {"txt": narrative, "id": race_id})
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("ai_post_race_text commit falló race_id=%s: %s", race_id, exc)

    analysis["ai_narrative"] = narrative
    return analysis


@router.delete("/{race_id}")
def delete_race(
    race_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    race = db.query(RaceEvent).filter(
        RaceEvent.id      == race_id,
        RaceEvent.user_id == me.id,
    ).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")
    db.delete(race)
    db.commit()
    return {"ok": True}


# =============================================================================
# SPRINT 19 â€” RACE DAY INTELLIGENCE ADDITIONS
# =============================================================================
import uuid as _uuid_mod


# â”€â”€â”€ CTL-band baseline (used when FTP/CSS not available) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_CTL_BANDS = [
    # (min_ctl, swim_s100m, bike_kmh, run_s_km)
    (0,   130, 24.0, 400),
    (20,  120, 26.0, 380),
    (40,  110, 28.5, 360),
    (60,  105, 31.0, 340),
    (80,  100, 33.5, 320),
    (100, 97,  36.0, 300),
    (120, 95,  38.0, 285),
    (150, 90,  40.0, 270),
]

def _ctl_base_paces(ctl):
    band = _CTL_BANDS[0]
    for b in _CTL_BANDS:
        if ctl >= b[0]:
            band = b
        else:
            break
    return {"swim_s100m": band[1], "bike_kmh": band[2], "run_s_km": band[3]}

def _tsb_perf_mod(tsb):
    if tsb is None: return 1.0
    if tsb <= -30:  return 0.94
    if tsb <= -20:  return 0.96
    if tsb <= -10:  return 0.98
    if tsb <= 0:    return 1.00
    if tsb <= 10:   return 1.01
    if tsb <= 20:   return 1.02
    return 1.025

def _rec_perf_mod(rec):
    if rec is None: return 1.0
    if rec >= 85:   return 1.02
    if rec >= 70:   return 1.01
    if rec >= 55:   return 1.00
    if rec >= 40:   return 0.98
    return 0.96

def _ctl_predict_splits(race_dist_key, ctl, tsb, recovery_score, ftp_w=None, water_mult=1.0):
    dist_map = {
        "sprint": {"swim_m":750,   "bike_km":20,   "run_km":5,   "brick":1.03},
        "olympic":{"swim_m":1500,  "bike_km":40,   "run_km":10,  "brick":1.05},
        "703":    {"swim_m":1900,  "bike_km":90,   "run_km":21.1,"brick":1.08},
        "full":   {"swim_m":3800,  "bike_km":180,  "run_km":42.2,"brick":1.12},
        "21k":    {"swim_m":0,     "bike_km":0,    "run_km":21.1,"brick":1.0},
        "42k":    {"swim_m":0,     "bike_km":0,    "run_km":42.2,"brick":1.0},
    }
    trans = {
        "sprint":{"t1":120,"t2":60}, "olympic":{"t1":150,"t2":75},
        "703":{"t1":180,"t2":90},    "full":{"t1":240,"t2":120},
        "21k":{"t1":0,"t2":0},       "42k":{"t1":0,"t2":0},
    }
    dist = dist_map.get(race_dist_key, dist_map["olympic"])
    tn   = trans.get(race_dist_key, trans["olympic"])
    base = _ctl_base_paces(ctl or 50)
    mod  = (_tsb_perf_mod(tsb) + _rec_perf_mod(recovery_score)) / 2.0

    swim_s = int((dist["swim_m"]/100) * base["swim_s100m"] / mod / (water_mult or 1.0)) if dist["swim_m"] else 0
    t1_s   = tn["t1"] if dist["swim_m"] and dist["bike_km"] else 0
    t2_s   = tn["t2"] if dist["bike_km"] and dist["run_km"] else 0

    bike_if = None
    bike_pw = None
    if dist["bike_km"] and ftp_w:
        if_map = {"sprint":0.90, "olympic":0.82, "703":0.75, "full":0.70}
        bike_if = round(min(0.95, if_map.get(race_dist_key, 0.78) * mod), 3)
        bike_pw = int(ftp_w * bike_if)
        ref_p, ref_s = 200, 32.0
        bike_kmh = ref_s * (bike_pw / ref_p) ** (1/2.8)
        bike_s   = int(dist["bike_km"] / bike_kmh * 3600)
    elif dist["bike_km"]:
        bike_s = int(dist["bike_km"] / (base["bike_kmh"] * mod) * 3600)
    else:
        bike_s = 0

    run_pace = int(base["run_s_km"] * dist["brick"] / mod) if dist["run_km"] else None
    run_s    = int(dist["run_km"] * run_pace) if (dist["run_km"] and run_pace) else 0

    total = swim_s + t1_s + bike_s + t2_s + run_s
    return {
        "swim_s": swim_s, "t1_s": t1_s, "bike_s": bike_s,
        "t2_s": t2_s, "run_s": run_s, "total_s": total,
        "bike_if": bike_if, "bike_pw": bike_pw, "run_pace_s_km": run_pace,
        "mod": round(mod, 3),
    }


def _physics_predict_splits(race_dist_key, ctl, tsb, recovery_score, ftp_w, weight_kg,
                             bike_profile=None, bike_distance_km=None,
                             bike_elevation_gain_m=0.0, bike_elevation_loss_m=None,
                             run_distance_km=None, run_elevation_gain_m=0.0,
                             run_elevation_loss_m=None, run_surface="asfalto",
                             wind_ms=0.0, altitude_m=0.0, temperature_c=22.0,
                             bike_if_override=None, run_fraction_override=None,
                             water_mult=1.0):
    """
    Igual que _ctl_predict_splits pero reemplaza bici y run por el motor de
    física real (Newton-Raphson + Minetti, ver models/bike_physics.py y
    models/run_physics.py) cuando hay ruta GPX y/o condiciones del día.
    El nado sigue el mismo modelo CTL de siempre (no hay ruta de nado).
    """
    from models.bike_physics import predict_bike, BikePhysicsParams
    from models.run_physics import predict_run, RunPhysicsParams

    dist_map = {
        "sprint": {"swim_m":750,   "bike_km":20,   "run_km":5},
        "olympic":{"swim_m":1500,  "bike_km":40,   "run_km":10},
        "703":    {"swim_m":1900,  "bike_km":90,   "run_km":21.1},
        "full":   {"swim_m":3800,  "bike_km":180,  "run_km":42.2},
        "21k":    {"swim_m":0,     "bike_km":0,    "run_km":21.1},
        "42k":    {"swim_m":0,     "bike_km":0,    "run_km":42.2},
    }
    trans = {
        "sprint":{"t1":120,"t2":60}, "olympic":{"t1":150,"t2":75},
        "703":{"t1":180,"t2":90},    "full":{"t1":240,"t2":120},
        "21k":{"t1":0,"t2":0},       "42k":{"t1":0,"t2":0},
    }
    dist = dist_map.get(race_dist_key, dist_map["olympic"])
    tn   = trans.get(race_dist_key, trans["olympic"])
    base = _ctl_base_paces(ctl or 50)
    mod  = (_tsb_perf_mod(tsb) + _rec_perf_mod(recovery_score)) / 2.0
    wind_ms = wind_ms or 0.0
    altitude_m = altitude_m or 0.0
    temperature_c = temperature_c if temperature_c is not None else 22.0

    # Swim: sin ruta disponible, se mantiene el modelo CTL de siempre + condición de agua
    swim_s = int((dist["swim_m"]/100) * base["swim_s100m"] / mod / (water_mult or 1.0)) if dist["swim_m"] else 0
    t1_s   = tn["t1"] if dist["swim_m"] and dist["bike_km"] else 0
    t2_s   = tn["t2"] if dist["bike_km"] and dist["run_km"] else 0

    bike_s, bike_if, bike_pw, bike_speed = 0, None, None, None
    if dist["bike_km"] and ftp_w:
        if bike_if_override is not None:
            bike_if = round(min(1.05, max(0.4, bike_if_override)), 3)
        else:
            if_map = {"sprint":0.90, "olympic":0.82, "703":0.75, "full":0.70}
            bike_if = round(min(0.95, if_map.get(race_dist_key, 0.78) * mod), 3)
        bkm = bike_distance_km or dist["bike_km"]
        bgain = bike_elevation_gain_m or 0.0
        bloss = bike_elevation_loss_m if bike_elevation_loss_m is not None else bgain
        bike_params = BikePhysicsParams(
            weight_kg=weight_kg or 70.0, ftp_w=ftp_w, distance_km=bkm,
            elevation_gain_m=bgain, elevation_loss_m=bloss,
            altitude_m=altitude_m, temperature_c=temperature_c, wind_ms=wind_ms,
            if_factor=bike_if,
            profile=[tuple(p) for p in bike_profile] if bike_profile else None,
        )
        bike_result = predict_bike(bike_params)
        bike_s     = round(bike_result["time_s"])
        bike_pw    = round(bike_result["avg_power_w"])
        bike_speed = bike_result["avg_speed_kmh"]
    elif dist["bike_km"]:
        bike_s = int(dist["bike_km"] / (base["bike_kmh"] * mod) * 3600)

    run_s, run_pace = 0, None
    if dist["run_km"]:
        rk = run_distance_km or dist["run_km"]
        rgain = run_elevation_gain_m or 0.0
        rloss = run_elevation_loss_m if run_elevation_loss_m is not None else rgain
        if run_fraction_override is not None:
            run_fraction = min(1.20, max(0.4, run_fraction_override))
        else:
            rec_if_run   = {"sprint":1.10, "olympic":1.05, "703":0.97, "full":0.88, "21k":0.95, "42k":0.88}
            run_fraction = min(1.15, rec_if_run.get(race_dist_key, 0.95) * mod)
        bike_if_for_run = bike_if if bike_if is not None else (0.75 if dist["bike_km"] else 0.0)
        run_params = RunPhysicsParams(
            threshold_pace_s_km=base["run_s_km"], weight_kg=weight_kg or 70.0,
            distance_km=rk, elevation_gain_m=rgain, elevation_loss_m=rloss,
            surface=run_surface or "asfalto",
            altitude_m=altitude_m, temperature_c=temperature_c,
            race_fraction=run_fraction, bike_if=bike_if_for_run,
        )
        run_result = predict_run(run_params)
        run_s    = round(run_result["time_s"])
        run_pace = round(run_result["effective_pace_s_km"])

    total = swim_s + t1_s + bike_s + t2_s + run_s
    return {
        "swim_s": swim_s, "t1_s": t1_s, "bike_s": bike_s, "t2_s": t2_s, "run_s": run_s,
        "total_s": total, "bike_if": bike_if, "bike_pw": bike_pw,
        "bike_avg_speed_kmh": bike_speed, "run_pace_s_km": run_pace,
        "mod": round(mod, 3), "method": "physics",
    }


def _fmt_t(s):
    if not s: return "â€”"
    h,rem = divmod(int(s), 3600)
    m,sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def _fmt_pace(s_km):
    if not s_km: return "â€”"
    return f"{s_km//60}:{s_km%60:02d} /km"

def _gen_nutrition(total_s, race_dist_key, weight_kg=70.0, sweat_l_h=0.8):
    dur_h = total_s / 3600
    total_min = total_s / 60
    if total_min < 60:    carb_g_h = 30
    elif total_min < 90:  carb_g_h = 45
    elif total_min < 150: carb_g_h = 60
    elif total_min < 240: carb_g_h = 75
    elif total_min < 360: carb_g_h = 90
    else:                 carb_g_h = 90

    return {
        "strategy": {
            "carb_g_h":          carb_g_h,
            "total_carb_g":      int(carb_g_h * dur_h),
            "total_fluid_l":     round(sweat_l_h * dur_h, 1),
            "sodium_mg_h":       int(weight_kg * 10),
            "calories_estimate": int(carb_g_h * dur_h * 4 + weight_kg * 5),
        },
        "key_rules": [
            f"Objetivo: {carb_g_h}g carbohidratos/hora durante las partes activas.",
            "Nunca experimentes el dÃ­a de carrera â€” todo probado en training.",
            "Si el estÃ³mago falla: agua sola 10 min, luego retoma geles.",
            f"HidrataciÃ³n: ~{int(sweat_l_h*500)}ml por hora en condiciones normales.",
            "Calor > 28Â°C: +20% fluidos, switch a geles lÃ­quidos.",
        ],
    }

def _pacing_score(pred_total, actual_total, pred_power, actual_power,
                  pred_pace, actual_pace, dnf):
    if dnf: return 0
    scores = []
    if pred_total and actual_total:
        err = abs(actual_total - pred_total) / pred_total
        scores.append(max(0, 100 - err * 500))
    if pred_power and actual_power:
        err = abs(actual_power - pred_power) / pred_power
        scores.append(max(0, 100 - err * 500))
    if pred_pace and actual_pace:
        err = abs(actual_pace - pred_pace) / pred_pace
        scores.append(max(0, 100 - err * 500))
    return int(sum(scores)/len(scores)) if scores else None


# â”€â”€â”€ Sprint 19 endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

from pydantic import BaseModel as _BM, Field as _F
from typing import Optional as _Opt, List as _List


@router.post("/parse-gpx")
def parse_gpx_route(
    file: UploadFile = File(...),
    me:   User        = Depends(get_current_user),
):
    """
    Sube un archivo GPX (ruta real de bici o de trote) y devuelve su perfil
    de elevación real: distancia, desnivel acumulado y el perfil km→altitud
    que usa el motor de física (Newton-Raphson bici / Minetti run) para
    predecir splits precisos en vez del modelo genérico CTL/TSB plano.
    """
    if not file.filename or not file.filename.lower().endswith(".gpx"):
        raise HTTPException(422, "El archivo debe tener extensión .gpx")
    raw = file.file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "Archivo GPX demasiado grande (máx 15MB)")
    try:
        from data.gpx_parser import parse_gpx_bytes
        parsed = parse_gpx_bytes(raw)
    except ValueError as e:
        raise HTTPException(422, f"No se pudo leer el GPX: {e}")
    return {
        "filename":          file.filename,
        "distance_km":       parsed["distance_km"],
        "elevation_gain_m":  parsed["elevation_gain_m"],
        "elevation_loss_m":  parsed["elevation_loss_m"],
        "avg_gradient_pct":  parsed["avg_gradient_pct"],
        "profile":           parsed["profile"],
        "stats":             parsed["stats"],
    }


class _AutoPlanRequest(_BM):
    race_id:    _Opt[str] = None
    ftp_w:      _Opt[int] = _F(None, ge=50, le=500)
    weight_kg:  _Opt[float] = _F(None, ge=30, le=150)
    sweat_l_h:  _Opt[float] = _F(None, ge=0.3, le=2.5)

    race_type:  _Opt[str] = None  # override manual del selector (sprint|olympic|703|full|21k|42k)

    # Ruta real (GPX) — opcional. Si se manda, el motor usa física real
    # (Newton-Raphson bici + Minetti run) en vez del modelo CTL/TSB genérico.
    bike_profile:          _Opt[_List[_List[float]]] = None  # [[km, elev_m], ...]
    bike_distance_km:      _Opt[float] = _F(None, gt=0, le=400)
    bike_elevation_gain_m: _Opt[float] = _F(None, ge=0, le=10000)
    bike_elevation_loss_m: _Opt[float] = _F(None, ge=0, le=10000)
    run_distance_km:       _Opt[float] = _F(None, gt=0, le=250)
    run_elevation_gain_m:  _Opt[float] = _F(None, ge=0, le=10000)
    run_elevation_loss_m:  _Opt[float] = _F(None, ge=0, le=10000)
    run_surface:           _Opt[str]   = "asfalto"

    # Condiciones del día — opcionales
    wind_ms:        _Opt[float] = _F(None, ge=-30, le=30)   # positivo = en contra
    altitude_m:      _Opt[float] = _F(None, ge=0, le=6000)
    temperature_c:   _Opt[float] = _F(None, ge=-10, le=50)

    # Intensidad — override manual del % de FTP (bici) y % de ritmo umbral (run),
    # mismo concepto que el panel "Intensidad" de nutrition.html
    bike_if_override:      _Opt[float] = _F(None, ge=0.4, le=1.05)
    run_fraction_override: _Opt[float] = _F(None, ge=0.4, le=1.20)

    # Condición de agua (nado) — rescatado de race_predictor.html
    water_mult: _Opt[float] = _F(None, ge=0.8, le=1.0)


class _RaceResultIn(_BM):
    race_id:           _Opt[str] = None
    swim_s:            _Opt[int] = _F(None, ge=0)
    t1_s:              _Opt[int] = _F(None, ge=0)
    bike_s:            _Opt[int] = _F(None, ge=0)
    t2_s:              _Opt[int] = _F(None, ge=0)
    run_s:             _Opt[int] = _F(None, ge=0)
    avg_power_bike_w:  _Opt[int] = _F(None, ge=50, le=600)
    avg_hr_run:        _Opt[int] = _F(None, ge=60, le=220)
    avg_pace_run_s_km: _Opt[int] = _F(None, ge=180, le=700)
    overall_feeling:   _Opt[int] = _F(None, ge=1, le=5)
    dnf:               bool = False
    dnf_reason:        _Opt[str] = _F(None, max_length=200)
    notes:             _Opt[str] = _F(None, max_length=500)


@router.post("/auto-plan")
def auto_race_plan(
    body: _AutoPlanRequest,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Genera plan automático basado en CTL/TSB sin inputs manuales."""
    from ..models import RecoveryScore, RacePlan
    today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()

    load = (db.query(GarminTrainingLoad)
            .filter_by(user_id=me.id)
            .order_by(GarminTrainingLoad.date_iso.desc()).first())
    rec  = db.query(RecoveryScore).filter_by(user_id=me.id, date_iso=today).first()

    ctl = load.ctl if load else 50
    tsb = load.tsb if load else None
    recovery_score = rec.score if rec else None

    ftp_w     = body.ftp_w or me.ftp
    weight_kg = body.weight_kg or me.weight_kg or 70.0

    # Determine race type from next race (o del selector si el usuario lo eligió a mano)
    race_id = body.race_id
    race_type = "olympic"
    race = None
    if not race_id:
        race = (db.query(RaceEvent)
                .filter(RaceEvent.user_id == me.id, RaceEvent.date_iso >= today)
                .order_by(RaceEvent.date_iso.asc()).first())
        if race:
            race_id   = race.id
            race_type = race.distance or "olympic"
    else:
        race = db.query(RaceEvent).filter_by(id=race_id).first()
        if race:
            race_type = race.distance or "olympic"

    _VALID_RACE_TYPES = ("sprint", "olympic", "703", "full", "21k", "42k")
    if body.race_type and body.race_type in _VALID_RACE_TYPES:
        race_type = body.race_type

    has_route_data = bool(
        body.bike_profile or body.bike_elevation_gain_m or body.run_elevation_gain_m
        or body.wind_ms or body.altitude_m or body.temperature_c is not None
        or body.bike_if_override is not None or body.run_fraction_override is not None
        or body.water_mult is not None
    )
    if has_route_data:
        splits = _physics_predict_splits(
            race_type, ctl, tsb, recovery_score, ftp_w, weight_kg,
            bike_profile=body.bike_profile,
            bike_distance_km=body.bike_distance_km,
            bike_elevation_gain_m=body.bike_elevation_gain_m,
            bike_elevation_loss_m=body.bike_elevation_loss_m,
            run_distance_km=body.run_distance_km,
            run_elevation_gain_m=body.run_elevation_gain_m,
            run_elevation_loss_m=body.run_elevation_loss_m,
            run_surface=body.run_surface,
            wind_ms=body.wind_ms, altitude_m=body.altitude_m, temperature_c=body.temperature_c,
            bike_if_override=body.bike_if_override, run_fraction_override=body.run_fraction_override,
            water_mult=body.water_mult or 1.0,
        )
    else:
        splits = _ctl_predict_splits(race_type, ctl, tsb, recovery_score, ftp_w, water_mult=body.water_mult or 1.0)
        splits["method"] = "simple"

    # Banda de confianza — rescatada de race_predictor.html, misma fórmula,
    # usando recovery_score (0-100) en vez de "readiness" (mismo concepto).
    _rec_for_conf = recovery_score if recovery_score is not None else 70
    _uncertainty  = 0.02 + (1.0 - _rec_for_conf/100) * 0.04
    _confidence   = max(55, min(95, round(70 + _rec_for_conf * 0.25)))
    nutrition = _gen_nutrition(
        splits["total_s"], race_type,
        weight_kg=weight_kg or 70.0,
        sweat_l_h=body.sweat_l_h or 0.8,
    )

    # Upsert RacePlan
    existing_plan = None
    if race_id:
        try:
            existing_plan = (db.query(RacePlan)
                             .filter_by(user_id=me.id, race_event_id=race_id).first())
        except Exception:
            pass

    plan_kwargs = {
        "ctl_at_generation":  round(float(ctl), 1) if ctl else None,
        "tsb_at_generation":  round(float(tsb), 1) if tsb else None,
        "recovery_score":     recovery_score,
        "swim_pred_s":        splits["swim_s"],
        "t1_pred_s":          splits["t1_s"],
        "bike_pred_s":        splits["bike_s"],
        "t2_pred_s":          splits["t2_s"],
        "run_pred_s":         splits["run_s"],
        "total_pred_s":       splits["total_s"],
        "bike_target_if":     splits["bike_if"],
        "bike_target_power":  splits["bike_pw"],
        "run_target_pace":    splits["run_pace_s_km"],
        "nutrition_plan_json": json.dumps(nutrition),
        "generated_at":       datetime.now(timezone.utc).replace(tzinfo=None),
        "race_date":          race.date_iso if race else None,
    }

    if existing_plan:
        for k, v in plan_kwargs.items():
            setattr(existing_plan, k, v)
        db.commit()
    else:
        try:
            from ..models import RacePlan as _RP
            plan_obj = _RP(id=str(_uuid_mod.uuid4()), user_id=me.id,
                           race_event_id=race_id, **plan_kwargs)
            db.add(plan_obj)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("race_plan commit falló user=%s race_id=%s: %s", me.id, race_id, exc)

    return {
        "race_type":  race_type,
        "ctl_used":   round(float(ctl), 1) if ctl else None,
        "tsb_used":   round(float(tsb), 1) if tsb else None,
        "recovery":   recovery_score,
        "perf_mod":   splits["mod"],
        "method":     splits.get("method", "simple"),
        "splits": {
            "swim_fmt":  _fmt_t(splits["swim_s"]),
            "t1_fmt":    _fmt_t(splits["t1_s"]),
            "bike_fmt":  _fmt_t(splits["bike_s"]),
            "t2_fmt":    _fmt_t(splits["t2_s"]),
            "run_fmt":   _fmt_t(splits["run_s"]),
            "total_fmt": _fmt_t(splits["total_s"]),
            "swim_s":    splits["swim_s"],
            "bike_s":    splits["bike_s"],
            "run_s":     splits["run_s"],
            "total_s":   splits["total_s"],
        },
        "pacing": {
            "bike_if":    splits["bike_if"],
            "bike_power": splits["bike_pw"],
            "bike_avg_speed_kmh": splits.get("bike_avg_speed_kmh"),
            "run_pace":   _fmt_pace(splits["run_pace_s_km"]),
            "run_pace_s": splits["run_pace_s_km"],
        },
        "confidence": {
            "confidence_pct":  _confidence,
            "uncertainty_pct": round(_uncertainty * 100, 1),
            "range_low_fmt":   _fmt_t(round(splits["total_s"] * (1 - _uncertainty))),
            "range_high_fmt":  _fmt_t(round(splits["total_s"] * (1 + _uncertainty))),
        },
        "nutrition": nutrition,
    }


@router.post("/record-result")
def record_race_result(
    body: _RaceResultIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Registra resultado real y calcula pacing score vs plan."""
    from ..models import RacePlan, RaceResult as _RR
    total_s = sum(filter(None, [body.swim_s, body.t1_s, body.bike_s, body.t2_s, body.run_s]))

    plan = None
    if body.race_id:
        try:
            plan = (db.query(RacePlan)
                    .filter_by(user_id=me.id, race_event_id=body.race_id)
                    .order_by(RacePlan.generated_at.desc()).first())
        except Exception:
            pass

    pred_err = (total_s - plan.total_pred_s) if (plan and plan.total_pred_s and total_s) else None
    p_score  = _pacing_score(
        plan.total_pred_s if plan else None, total_s,
        plan.bike_target_power if plan else None, body.avg_power_bike_w,
        plan.run_target_pace if plan else None, body.avg_pace_run_s_km,
        body.dnf,
    )

    existing = None
    if body.race_id:
        try:
            existing = (db.query(_RR)
                        .filter_by(user_id=me.id, race_event_id=body.race_id).first())
        except Exception:
            pass

    rdata = {
        "swim_time_s":       body.swim_s,
        "t1_time_s":         body.t1_s,
        "bike_time_s":       body.bike_s,
        "t2_time_s":         body.t2_s,
        "run_time_s":        body.run_s,
        "total_time_s":      total_s or None,
        "avg_power_bike_w":  body.avg_power_bike_w,
        "avg_hr_run":        body.avg_hr_run,
        "avg_pace_run_s_km": body.avg_pace_run_s_km,
        "overall_feeling":   body.overall_feeling,
        "dnf":               body.dnf,
        "dnf_reason":        body.dnf_reason,
        "notes":             body.notes,
        "predicted_total_s": plan.total_pred_s if plan else None,
        "prediction_error_s": pred_err,
        "pacing_score":      p_score,
    }

    if existing:
        for k, v in rdata.items():
            setattr(existing, k, v)
        db.commit()
        rid = existing.id
    else:
        try:
            r = _RR(id=str(_uuid_mod.uuid4()), user_id=me.id,
                    race_event_id=body.race_id, **rdata)
            db.add(r)
            db.commit()
            rid = r.id
        except Exception:
            db.rollback()
            rid = None

    return {
        "result_id":      rid,
        "total_fmt":      _fmt_t(total_s),
        "pacing_score":   p_score,
        "pred_error_s":   pred_err,
        "pred_error_fmt": (_fmt_t(abs(pred_err)) + (" mÃ¡s rÃ¡pido" if pred_err < 0 else " mÃ¡s lento")) if pred_err else None,
    }


@router.get("/nutrition/{race_id}")
def get_nutrition_plan(
    race_id: str,
    weight_kg: float = Query(70.0, ge=30, le=150),
    sweat_l_h: float = Query(0.8, ge=0.3, le=2.5),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Genera plan de nutriciÃ³n para una carrera registrada."""
    from ..models import RacePlan
    race = db.query(RaceEvent).filter_by(id=race_id, user_id=me.id).first()
    if not race:
        raise HTTPException(404, "Carrera no encontrada")

    plan = None
    try:
        plan = (db.query(RacePlan)
                .filter_by(user_id=me.id, race_event_id=race_id)
                .order_by(RacePlan.generated_at.desc()).first())
    except Exception:
        pass

    if plan and plan.nutrition_plan_json:
        try:
            return {"source": "plan", "nutrition": json.loads(plan.nutrition_plan_json)}
        except Exception:
            pass

    # Generate on the fly
    total_s = (plan.total_pred_s if plan and plan.total_pred_s else 7200)
    nutrition = _gen_nutrition(total_s, race.distance or "olympic", weight_kg, sweat_l_h)
    return {"source": "estimated", "nutrition": nutrition}


# ── Sprint 29: Goal Race CTL Countdown ───────────────────────────────────────

@router.get("/goal-countdown")
def goal_race_countdown(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Strategic race intelligence: current CTL → target CTL → race day.
    Returns required weekly TSS, Banister projection, peak form window.
    Prioritizes goal races (is_goal_race=True); falls back to next upcoming.
    """
    from ..services.goal_race_service import compute_race_countdown
    return compute_race_countdown(me.id, db)
