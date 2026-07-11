"""
S1 — Service Layer: Training Load (CTL/ATL/TSB/ACWR/Zonas).
Extrae lógica de negocio de athlete_routes.py — reutilizable desde rutas, tests y tareas.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import GarminActivity, GarminTrainingLoad, User


# ─── Constantes de carga de entrenamiento ─────────────────────
_CTL_TC  = 42   # días — Chronic Training Load time constant (Banister)
_ATL_TC  = 7    # días — Acute Training Load time constant
_ALPHA_CTL = 1 - math.exp(-1 / _CTL_TC)
_ALPHA_ATL = 1 - math.exp(-1 / _ATL_TC)


# ─── Zonas de entrenamiento ───────────────────────────────────

def hr_zones(fcmax: int) -> dict:
    """Zonas FC según modelo 5-zonas (adaptado para triatlón)."""
    return {
        "z1": (round(fcmax * 0.50), round(fcmax * 0.60)),
        "z2": (round(fcmax * 0.60), round(fcmax * 0.70)),
        "z3": (round(fcmax * 0.70), round(fcmax * 0.80)),
        "z4": (round(fcmax * 0.80), round(fcmax * 0.90)),
        "z5": (round(fcmax * 0.90), fcmax),
    }


def ftp_zones(ftp: int) -> dict:
    """Zonas de potencia ciclismo (Coggan 7-zonas)."""
    return {
        "z1_active_recovery":  (0,              round(ftp * 0.55)),
        "z2_endurance":        (round(ftp * 0.55), round(ftp * 0.75)),
        "z3_tempo":            (round(ftp * 0.75), round(ftp * 0.90)),
        "z4_threshold":        (round(ftp * 0.90), round(ftp * 1.05)),
        "z5_vo2max":           (round(ftp * 1.05), round(ftp * 1.20)),
        "z6_anaerobic":        (round(ftp * 1.20), round(ftp * 1.50)),
        "z7_neuromuscular":    (round(ftp * 1.50), 9999),
    }


def run_pace_zones(threshold_pace_str: str) -> dict:
    """
    Zonas de ritmo carrera. threshold_pace_str: "4:52" (min/km).
    Retorna dict zona → (pace_min, pace_max) en segundos/km.
    """
    try:
        parts = threshold_pace_str.split(":")
        pace_sec = int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return {}
    return {
        "z1_easy":     (round(pace_sec * 1.30), 9999),
        "z2_aerobic":  (round(pace_sec * 1.15), round(pace_sec * 1.30)),
        "z3_tempo":    (round(pace_sec * 1.05), round(pace_sec * 1.15)),
        "z4_threshold":(round(pace_sec * 0.97), round(pace_sec * 1.05)),
        "z5_vo2max":   (0, round(pace_sec * 0.97)),
    }


def swim_css_zones(css_str: str) -> dict:
    """Zonas de natación desde CSS (Critical Swim Speed). css_str: '1:48' (min/100m)."""
    try:
        parts = css_str.split(":")
        css_sec = int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return {}
    return {
        "z1_recovery":  (round(css_sec * 1.30), 9999),
        "z2_aerobic":   (round(css_sec * 1.15), round(css_sec * 1.30)),
        "z3_threshold": (round(css_sec * 1.00), round(css_sec * 1.15)),
        "z4_speed":     (0, round(css_sec * 1.00)),
    }


def athlete_zones(user: User) -> dict:
    """Devuelve todas las zonas del atleta según métricas disponibles en su perfil."""
    result: dict = {}
    if user.fcmax:
        result["hr"] = hr_zones(user.fcmax)
    if user.ftp:
        result["power"] = ftp_zones(user.ftp)
    if user.run_pace:
        result["run_pace"] = run_pace_zones(user.run_pace)
    if user.css:
        result["swim"] = swim_css_zones(user.css)
    return result


# ─── Cálculo ACWR mejorado (BP-03) ───────────────────────────

def compute_acwr(load_rows: list, safe_minimum: float = 1.0) -> tuple[float, str]:
    """
    BP-03: ACWR con guardia cuando acute=0 o datos insuficientes.
    Devuelve (acwr_value, zone_string).
    zone: "no_data" | "low" | "optimal" | "warning" | "danger"
    """
    if len(load_rows) < 7:
        return 0.0, "no_data"

    last7  = load_rows[-7:]
    last28 = load_rows[-28:]
    acute   = sum(r.tss for r in last7)  / max(len(last7), 1)
    chronic = sum(r.tss for r in last28) / max(len(last28), 1)

    # BP-03: Si acute o chronic son cero → "no_data" en lugar de 0.0
    if acute < safe_minimum or chronic < safe_minimum:
        return 0.0, "no_data"

    acwr = round(acute / chronic, 2)

    if acwr >= 1.5:    zone = "danger"
    elif acwr >= 1.3:  zone = "warning"
    elif acwr >= 0.8:  zone = "optimal"
    else:              zone = "low"

    return acwr, zone


# ─── Alertas de entrenamiento ─────────────────────────────────

def build_training_alerts(tsb: float, acwr: float, acwr_zone: str, ctl: float) -> list[dict]:
    """
    Genera alertas de sobreentrenamiento / sub-entrenamiento.
    Versión mejorada con soporte a 'no_data' zone.
    """
    alerts: list[dict] = []

    if acwr_zone == "no_data":
        alerts.append({
            "level":   "info",
            "type":    "acwr_no_data",
            "title":   "Sin datos suficientes para ACWR",
            "message": "Necesitas al menos 7 días de actividad para calcular tu ratio de carga.",
            "icon":    "ℹ️",
        })
    elif acwr_zone == "danger":
        alerts.append({
            "level":   "danger",
            "type":    "acwr_danger",
            "title":   "⚠️ Alto riesgo de lesión",
            "message": f"Tu ACWR es {acwr:.2f} — muy por encima del umbral seguro (>1.5). Reduce carga inmediatamente.",
            "icon":    "🚨",
        })
    elif acwr_zone == "warning":
        alerts.append({
            "level":   "warning",
            "type":    "acwr_warning",
            "title":   "Carga elevada",
            "message": f"Tu ACWR ({acwr:.2f}) indica sobrecarga moderada. Prioriza recuperación.",
            "icon":    "⚠️",
        })
    elif acwr_zone == "low" and ctl > 20:
        alerts.append({
            "level":   "info",
            "type":    "acwr_low",
            "title":   "Carga por debajo de lo óptimo",
            "message": "Tu ACWR es bajo. Puedes aumentar volumen o intensidad gradualmente.",
            "icon":    "📉",
        })

    # TSB warnings
    if tsb < -30:
        alerts.append({
            "level":   "danger",
            "type":    "tsb_overreach",
            "title":   "Sobreentrenamiento detectado",
            "message": f"Tu TSB ({tsb:.0f}) indica fatiga acumulada severa. Descanso obligatorio.",
            "icon":    "😴",
        })
    elif tsb < -15:
        alerts.append({
            "level":   "warning",
            "type":    "tsb_fatigue",
            "title":   "Fatiga acumulada",
            "message": f"TSB {tsb:.0f}. Mantén intensidad pero reduce volumen esta semana.",
            "icon":    "🔋",
        })
    elif tsb > 25 and ctl > 30:
        alerts.append({
            "level":   "success",
            "type":    "tsb_peak",
            "title":   "Estado de forma óptimo",
            "message": f"TSB {tsb:.0f} — estás fresco y en buena forma. Ideal para competir o testear.",
            "icon":    "🚀",
        })

    return alerts


# ─── Recálculo completo CTL/ATL/TSB ──────────────────────────

def recalculate_training_load(db: Session, user_id: str) -> int:
    """
    Recalcula CTL/ATL/TSB para todos los días del atleta usando el modelo EWMA de Banister.
    Devuelve el número de filas actualizadas/creadas.
    """
    from sqlalchemy import text

    acts = (
        db.query(GarminActivity)
          .filter(GarminActivity.user_id == user_id)
          .order_by(GarminActivity.date_iso)
          .all()
    )
    if not acts:
        return 0

    # Agrupar TSS por día
    tss_by_day: dict[str, float] = {}
    for a in acts:
        if a.date_iso:
            tss_by_day[a.date_iso] = tss_by_day.get(a.date_iso, 0.0) + (float(a.tss) if a.tss else 0.0)

    # Generar serie diaria continua
    dates = sorted(tss_by_day)
    if not dates:
        return 0

    start = date.fromisoformat(dates[0])
    end   = date.today()
    delta = (end - start).days + 1

    ctl, atl = 0.0, 0.0
    rows_written = 0

    for i in range(delta):
        d = start + timedelta(days=i)
        d_iso = d.isoformat()
        tss = tss_by_day.get(d_iso, 0.0)

        ctl = ctl + _ALPHA_CTL * (tss - ctl)
        atl = atl + _ALPHA_ATL * (tss - atl)
        tsb = round(ctl - atl, 2)

        # Upsert
        existing = db.query(GarminTrainingLoad).filter(
            GarminTrainingLoad.user_id == user_id,
            GarminTrainingLoad.date_iso == d_iso,
        ).first()
        if existing:
            existing.ctl = round(ctl, 2)
            existing.atl = round(atl, 2)
            existing.tsb = tsb
            existing.tss = round(tss, 2)
        else:
            db.add(GarminTrainingLoad(
                user_id  = user_id,
                date_iso = d_iso,
                ctl      = round(ctl, 2),
                atl      = round(atl, 2),
                tsb      = tsb,
                tss      = round(tss, 2),
            ))
        rows_written += 1

    db.commit()
    return rows_written
