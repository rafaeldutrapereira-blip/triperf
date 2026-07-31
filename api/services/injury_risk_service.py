"""
LabX Injury Risk Prediction Engine
====================================
Motor multifactorial de predicción de riesgo de lesión.

Factores y pesos:
  ACWR (35%)   — Acute:Chronic Workload Ratio
                  <0.8 = desentrenamiento; 0.8-1.3 = zona segura; >1.5 = zona peligrosa
  HRV  (30%)   — Caída vs baseline personal 7 días
                  Caída >8% sostenida 3d = fatiga sistémica (Flatt & Esco 2016)
  Monotonía (20%) — Índice de Foster: carga_media / σ_carga
                  >2.0 = monotonía alta → acumulación silenciosa de fatiga
  Blood Labs (15%) — Ferritina baja + cortisol alto + Hb baja

Referencias:
  Gabbett (2016) BJSports: ACWR y riesgo de lesión
  Foster (1998): Training Monotony Score
  Flatt & Esco (2016): HRV como marcador de readiness
  Halson (2014): Marcadores bioquímicos de sobreentrenamiento
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("labx.injury_risk")

# ── Pesos de cada factor en el score compuesto ──────────────────────────────
W_ACWR     = 0.35
W_HRV      = 0.30
W_MONOTONY = 0.20
W_LABS     = 0.15


# ── Clasificación del score ─────────────────────────────────────────────────
def _classify(score: float) -> tuple[str, str]:
    """(level, color) desde score 0-100."""
    if score >= 75:
        return "critical", "#EF4444"   # rojo vivo
    if score >= 55:
        return "high",     "#F97316"   # naranja
    if score >= 30:
        return "moderate", "#EAB308"   # ámbar
    return "low",          "#10B981"   # verde


# ── Factor ACWR ─────────────────────────────────────────────────────────────

def _acwr_risk_score(acwr: Optional[float]) -> float:
    """
    Convierte ACWR en componente de riesgo 0-100.
    Zona óptima: 0.8-1.3 → 0 riesgo.
    >1.5: riesgo exponencial.
    <0.6: desentrenamiento, riesgo moderado por pérdida de tolerancia.
    """
    if acwr is None:
        return 20.0   # sin datos = riesgo base bajo

    if 0.8 <= acwr <= 1.3:
        return 0.0
    if acwr > 1.3:
        if acwr >= 1.8:
            return 100.0
        # Interpolación lineal 1.3→1.8 :: 0→100
        return min(100.0, (acwr - 1.3) / 0.5 * 100)
    # acwr < 0.8 (desentrenamiento)
    if acwr <= 0.4:
        return 40.0
    return (0.8 - acwr) / 0.4 * 40


# ── Factor HRV ──────────────────────────────────────────────────────────────

def _hrv_risk_score(
    hrv_today: Optional[float],
    hrv_7d_avg: Optional[float],
) -> float:
    """
    Riesgo 0-100 basado en la caída del HRV vs promedio 7 días.
    Caída <5%: sin riesgo.
    Caída 5-8%: moderado.
    Caída >8% sostenida: alto.
    """
    if hrv_today is None or hrv_7d_avg is None or hrv_7d_avg == 0:
        return 15.0   # sin datos HRV = riesgo base bajo

    drop_pct = (hrv_7d_avg - hrv_today) / hrv_7d_avg * 100

    if drop_pct <= 5:
        return max(0.0, drop_pct * 2)     # 0-10 para caídas pequeñas
    if drop_pct <= 8:
        return 10 + (drop_pct - 5) / 3 * 30   # 10-40
    if drop_pct <= 15:
        return 40 + (drop_pct - 8) / 7 * 40   # 40-80
    return min(100.0, 80 + (drop_pct - 15) * 2)


# ── Factor Monotonía de Foster ───────────────────────────────────────────────

def _monotony_risk_score(
    daily_loads: list[float],   # cargas de los últimos 7 días (TSS o impulse)
) -> tuple[float, float, float]:
    """
    Calcula monotonía y strain de Foster, devuelve (risk_score, monotony, strain).
    Monotonía = media / σ
    Strain = suma_cargas × monotonía
    Riesgo alto si monotonía > 2.0 o strain > 4000 (para atletas con CTL~80).
    """
    if not daily_loads or len(daily_loads) < 3:
        return 10.0, 0.0, 0.0

    loads = [l for l in daily_loads if l > 0]
    if len(loads) < 3:
        return 5.0, 0.0, 0.0

    mean_load = statistics.mean(loads)
    try:
        sd_load = statistics.stdev(loads)
    except statistics.StatisticsError:
        sd_load = 0.0

    # sd=0 means perfectly identical loads → extreme monotony (worst case = score 100)
    monotony = mean_load / sd_load if sd_load > 0 else 10.0
    strain   = sum(loads) * monotony

    # Score de riesgo por monotonía
    if monotony <= 1.0:
        mono_risk = 0.0
    elif monotony <= 2.0:
        mono_risk = (monotony - 1.0) * 30   # 0-30
    elif monotony <= 3.0:
        mono_risk = 30 + (monotony - 2.0) * 50  # 30-80
    else:
        mono_risk = min(100.0, 80 + (monotony - 3.0) * 20)

    # Score de riesgo por strain (relativo a CTL de ~80 = base 4000 de strain)
    strain_risk = min(100.0, strain / 4000 * 100) if strain > 0 else 0.0

    # Combinación: el peor de los dos, ponderado
    risk_score = max(mono_risk, strain_risk * 0.7)

    return round(risk_score, 1), round(monotony, 2), round(strain, 1)


# ── Factor Blood Labs ────────────────────────────────────────────────────────

def _labs_risk_score(labs_values: dict) -> float:
    """
    Convierte marcadores de Blood Labs en componente de riesgo.
    Factores que aumentan el riesgo de lesión/sobreentrenamiento:
    - Ferritina <30 (depleción de hierro → micro-lesiones musculares más frecuentes)
    - Cortisol >22 (sobreentrenamiento → catabolismo)
    - Hemoglobina baja (menos transporte O₂ → fatiga prematura)
    - CK elevada (daño muscular activo)
    """
    if not labs_values:
        return 0.0   # sin labs = no penalizar (beneficio de la duda)

    score = 0.0

    ferritin = labs_values.get("ferritin")
    if ferritin is not None:
        if ferritin < 20:
            score += 40
        elif ferritin < 30:
            score += 25
        elif ferritin < 50:
            score += 10

    cortisol = labs_values.get("cortisol")
    if cortisol is not None:
        if cortisol > 28:
            score += 30
        elif cortisol > 22:
            score += 15

    hb = labs_values.get("hb")
    if hb is not None:
        if hb < 13.0:
            score += 25
        elif hb < 14.0:
            score += 10

    ck = labs_values.get("ck")
    if ck is not None:
        if ck > 1000:
            score += 30   # daño muscular severo activo
        elif ck > 500:
            score += 15
        elif ck > 300:
            score += 5

    urea = labs_values.get("urea")
    if urea is not None and urea > 7.5:   # mmol/L
        score += 10   # catabolismo elevado

    return min(100.0, score)


# ── Generación de alertas y recomendaciones ──────────────────────────────────

def _generate_alerts_and_recs(
    acwr:          Optional[float],
    hrv_drop_pct:  float,
    monotony:      float,
    strain:        float,
    labs:          dict,
    risk_score:    float,
    risk_level:    str,
    tsb:           Optional[float],
) -> tuple[list[dict], list[str]]:
    alerts = []
    recs   = []

    # ── ACWR alerts
    if acwr is not None:
        if acwr > 1.5:
            alerts.append({"level": "critical", "factor": "ACWR",
                           "msg": f"ACWR {acwr:.2f} — carga aguda muy elevada vs crónica. Zona de alto riesgo de lesión."})
            recs.append("Reduce el volumen de entrenamiento los próximos 3-5 días al 60-70% del habitual.")
        elif acwr > 1.3:
            alerts.append({"level": "high", "factor": "ACWR",
                           "msg": f"ACWR {acwr:.2f} — zona de riesgo elevado. No aumentes carga esta semana."})
            recs.append("Mantén la carga estable esta semana. Evita sesiones de volumen alto.")
        elif acwr < 0.6:
            alerts.append({"level": "moderate", "factor": "ACWR",
                           "msg": f"ACWR {acwr:.2f} — desentrenamiento. La tolerancia a la carga puede caer."})

    # ── HRV alerts
    if hrv_drop_pct > 8:
        alerts.append({"level": "high" if hrv_drop_pct < 15 else "critical", "factor": "HRV",
                       "msg": f"HRV {hrv_drop_pct:.0f}% por debajo del promedio 7 días. Señal de fatiga sistémica."})
        recs.append("Prioriza recuperación hoy: sueño 8h+, hidratación, sesión suave máximo Z2.")
    elif hrv_drop_pct > 5:
        alerts.append({"level": "moderate", "factor": "HRV",
                       "msg": f"HRV levemente deprimido ({hrv_drop_pct:.0f}% bajo promedio). Monitorear mañana."})

    # ── Monotonía
    if monotony > 2.5:
        alerts.append({"level": "high", "factor": "MONOTONY",
                       "msg": f"Monotonía de entrenamiento {monotony:.1f} (>2.5 = sobreentrenamiento silencioso)."})
        recs.append("Varía el tipo y duración de sesiones. Incluye 1 día de descanso completo esta semana.")
    elif monotony > 2.0:
        alerts.append({"level": "moderate", "factor": "MONOTONY",
                       "msg": f"Monotonía {monotony:.1f} — las sesiones son muy similares entre sí. Agrega variedad."})

    # ── Blood Labs
    ferritin = labs.get("ferritin")
    if ferritin is not None and ferritin < 30:
        alerts.append({"level": "critical" if ferritin < 20 else "high", "factor": "LABS",
                       "msg": f"Ferritina {ferritin:.0f} ng/mL — deplección de hierro. Riesgo de micro-lesiones musculares ↑."})
        recs.append(f"Ferritina {ferritin:.0f} ng/mL: reduce impacto en entrenamientos hasta suplementar y reevaluar.")

    cortisol = labs.get("cortisol")
    if cortisol is not None and cortisol > 22:
        alerts.append({"level": "high", "factor": "LABS",
                       "msg": f"Cortisol {cortisol:.0f} μg/dL elevado — señal de sobreentrenamiento crónico."})
        recs.append("Considera una semana de descarga estructurada. El cortisol elevado crónico → lesiones por estrés.")

    ck = labs.get("ck")
    if ck is not None and ck > 500:
        alerts.append({"level": "high" if ck < 1000 else "critical", "factor": "LABS",
                       "msg": f"CK {ck:.0f} U/L — daño muscular activo. Evita entrenamientos de alta intensidad."})
        recs.append(f"CK {ck:.0f} — espera que baje a <300 antes de reanudar sesiones de calidad.")

    # ── TSB
    if tsb is not None and tsb < -25:
        alerts.append({"level": "high", "factor": "TSB",
                       "msg": f"TSB {tsb:+.0f} — fatiga acumulada muy alta. Riesgo de sobreentrenamiento activo."})
        recs.append(f"TSB {tsb:+.0f}: programa al menos 4-5 días de taper antes del próximo estímulo duro.")

    # ── Recomendación general según nivel de riesgo
    if risk_level == "critical" and not any("CRÍTICO" in r or "Descansa" in r for r in recs):
        recs.insert(0, "⛔ RIESGO CRÍTICO: Descansa hoy. Consulta con tu coach antes de entrenar mañana.")
    elif risk_level == "high" and not recs:
        recs.append("Reduce intensidad y volumen al 70% esta semana. Prioriza sueño y nutrición.")
    elif risk_level == "low" and not alerts:
        recs.append("✓ Carga bien gestionada. Puedes continuar con el plan habitual.")

    return alerts, recs


# ── Función principal ────────────────────────────────────────────────────────

def compute_injury_risk(user_id: str, db: Session, target_date: str = None) -> dict:
    """
    Calcula el riesgo de lesión para un atleta en una fecha dada.
    Retorna el snapshot completo con score, factores, alertas y recomendaciones.
    """
    from ..models import (
        GarminTrainingLoad, GarminHealthDaily, BloodLabExam,
        InjuryRiskSnapshot,
    )

    target_date = target_date or date.today().isoformat()
    week_ago    = (date.fromisoformat(target_date) - timedelta(days=7)).isoformat()

    # ── 1. Carga de entrenamiento ─────────────────────────────────────────────
    load_today = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso <= target_date,
        )
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )

    acwr = None
    ctl  = None
    atl  = None
    tsb  = None
    if load_today:
        ctl  = round(load_today.ctl, 1)  if load_today.ctl  else None
        atl  = round(load_today.atl, 1)  if load_today.atl  else None
        tsb  = round(load_today.tsb, 1)  if load_today.tsb  else None
        if ctl and atl and ctl > 0:
            acwr = round(atl / ctl, 3)

    # Cargas diarias 7 días para monotonía
    load_rows = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso >= week_ago,
            GarminTrainingLoad.date_iso <= target_date,
        )
        .order_by(GarminTrainingLoad.date_iso)
        .all()
    )
    # Cargas diarias = TSS real del día (misma fuente que Foster Monotony canónico
    # en garmin_pull_service.py). ATL es un promedio móvil suavizado y subestima
    # la variabilidad día a día, lo que sobreestimaba la monotonía sistemáticamente.
    daily_loads = [r.tss for r in load_rows if r.tss is not None]

    # ── 2. HRV ───────────────────────────────────────────────────────────────
    health_rows = (
        db.query(GarminHealthDaily)
        .filter(
            GarminHealthDaily.user_id  == user_id,
            GarminHealthDaily.date_iso >= week_ago,
            GarminHealthDaily.date_iso <= target_date,
        )
        .order_by(GarminHealthDaily.date_iso.desc())
        .all()
    )

    hrv_today   = None
    hrv_7d_avg  = None
    hrv_values  = []
    for h in health_rows:
        v = h.hrv_last_night
        if v:
            hrv_values.append(float(v))

    if hrv_values:
        hrv_today  = hrv_values[0]   # más reciente primero
        if len(hrv_values) >= 3:
            hrv_7d_avg = round(statistics.mean(hrv_values[1:min(8, len(hrv_values))]), 1)

    hrv_drop_pct = 0.0
    if hrv_today and hrv_7d_avg and hrv_7d_avg > 0:
        hrv_drop_pct = (hrv_7d_avg - hrv_today) / hrv_7d_avg * 100

    # ── 3. Blood Labs (últimos 90 días) ───────────────────────────────────────
    cutoff_90 = (date.fromisoformat(target_date) - timedelta(days=90)).isoformat()
    latest_labs = (
        db.query(BloodLabExam)
        .filter(
            BloodLabExam.user_id  == user_id,
            BloodLabExam.date_iso >= cutoff_90,
        )
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )
    labs_values: dict = {}
    labs_date = None
    if latest_labs:
        try:
            raw = json.loads(latest_labs.values_json)
            for k in ["ferritin", "cortisol", "hb", "ck", "urea", "vitamin_d"]:
                if k in raw and raw[k] is not None:
                    labs_values[k] = float(raw[k])
        except Exception:
            pass
        labs_date = latest_labs.date_iso

    # ── 4. Calcular factores ─────────────────────────────────────────────────
    acwr_score  = _acwr_risk_score(acwr)
    hrv_score   = _hrv_risk_score(hrv_today, hrv_7d_avg)
    mono_score, monotony, strain = _monotony_risk_score(daily_loads)
    labs_score  = _labs_risk_score(labs_values)

    # ── 5. Score compuesto ────────────────────────────────────────────────────
    risk_score = round(
        acwr_score  * W_ACWR    +
        hrv_score   * W_HRV     +
        mono_score  * W_MONOTONY+
        labs_score  * W_LABS,
        1
    )
    risk_level, risk_color = _classify(risk_score)

    # ── 6. Alertas y recomendaciones ─────────────────────────────────────────
    alerts, recs = _generate_alerts_and_recs(
        acwr         = acwr,
        hrv_drop_pct = hrv_drop_pct,
        monotony     = monotony,
        strain       = strain,
        labs         = labs_values,
        risk_score   = risk_score,
        risk_level   = risk_level,
        tsb          = tsb,
    )

    # ── 7. Delta vs ayer ─────────────────────────────────────────────────────
    yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    prev = (
        db.query(InjuryRiskSnapshot)
        .filter(
            InjuryRiskSnapshot.user_id  == user_id,
            InjuryRiskSnapshot.date_iso == yesterday,
        )
        .first()
    )
    risk_delta = round(risk_score - prev.risk_score, 1) if prev and prev.risk_score is not None else None

    # ── 8. Persistir snapshot ────────────────────────────────────────────────
    existing = (
        db.query(InjuryRiskSnapshot)
        .filter(
            InjuryRiskSnapshot.user_id  == user_id,
            InjuryRiskSnapshot.date_iso == target_date,
        )
        .first()
    )
    if existing:
        snap = existing
    else:
        snap = InjuryRiskSnapshot(user_id=user_id, date_iso=target_date)
        db.add(snap)

    snap.risk_score  = risk_score
    snap.risk_level  = risk_level
    snap.risk_color  = risk_color
    snap.acwr_score  = round(acwr_score, 1)
    snap.hrv_score   = round(hrv_score, 1)
    snap.monotony_score = round(mono_score, 1)
    snap.strain_score   = round(labs_score, 1)
    snap.labs_score  = round(labs_score, 1)
    snap.acwr        = acwr
    snap.hrv_last_night = hrv_today
    snap.hrv_7d_avg  = hrv_7d_avg
    snap.monotony    = monotony
    snap.strain      = strain
    snap.ctl         = ctl
    snap.atl         = atl
    snap.tsb         = tsb
    snap.alerts_json          = json.dumps(alerts, ensure_ascii=False)
    snap.recommendations_json = json.dumps(recs,   ensure_ascii=False)
    snap.risk_delta  = risk_delta

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("InjuryRisk persist error user=%s: %s", user_id, e)

    return {
        "date_iso":    target_date,
        "risk_score":  risk_score,
        "risk_level":  risk_level,
        "risk_color":  risk_color,
        "risk_delta":  risk_delta,
        "factors": {
            "acwr":     {"score": round(acwr_score, 1), "value": acwr,      "weight": W_ACWR},
            "hrv":      {"score": round(hrv_score, 1),  "value": hrv_today, "weight": W_HRV,
                         "avg_7d": hrv_7d_avg, "drop_pct": round(hrv_drop_pct, 1)},
            "monotony": {"score": round(mono_score, 1), "value": monotony,  "weight": W_MONOTONY,
                         "strain": strain},
            "labs":     {"score": round(labs_score, 1), "date": labs_date,  "weight": W_LABS,
                         "values": labs_values},
        },
        "training": {"ctl": ctl, "atl": atl, "tsb": tsb},
        "alerts":          alerts,
        "recommendations": recs,
    }
