"""
LabX Blood Labs Correlation Service
=====================================
Correlaciona marcadores de blood labs con métricas de rendimiento Garmin.

Para cada marcador de labs, calcula:
  - Correlación de Pearson con CTL, TSS semanal, HR promedio en Z2, VO2max estimado
  - Tendencia temporal (mejora/empeora) en los últimos 12 meses
  - Ventana óptima: ¿cuántos días tarda el efecto en manifestarse?
  - Alertas: marcadores que históricamente correlacionan con bajones de rendimiento

Diferenciador: NINGÚN competidor hace esto. La correlación labs↔rendimiento
es el análisis que solo hacen médicos de élite (€500/sesión). LabX lo automatiza.

Algoritmo:
  1. Alinear exámenes de labs con períodos de entrenamiento (CTL/TSS medios en ±30 días)
  2. Para cada par (lab_marker, performance_metric): calcular r de Pearson
  3. Si |r| > 0.5 → correlación significativa → generar insight IA
  4. Análisis de lag: ¿el efecto se ve en los próximos 7/14/30 días?
"""
from __future__ import annotations

import logging
import math
import os
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import BloodLabExam, GarminActivity, GarminHealthDaily, GarminTrainingLoad, User

logger = logging.getLogger("labx.blood_labs_correlation")

# Marcadores de labs que analizamos
LAB_MARKERS = {
    "ferritin":   {"label": "Ferritina",          "unit": "ng/mL", "optimal_min": 70,  "optimal_max": 200,  "critical_low": 20},
    "hemoglobin": {"label": "Hemoglobina",         "unit": "g/dL",  "optimal_min": 14,  "optimal_max": 18,   "critical_low": 12},
    "cortisol":   {"label": "Cortisol",            "unit": "μg/dL", "optimal_min": 6,   "optimal_max": 18,   "critical_high": 28},
    "vitamin_d":  {"label": "Vitamina D",          "unit": "ng/mL", "optimal_min": 40,  "optimal_max": 80,   "critical_low": 20},
    "ck":         {"label": "Creatina Quinasa",    "unit": "U/L",   "optimal_min": 50,  "optimal_max": 200,  "critical_high": 500},
    "hba1c":      {"label": "HbA1c",               "unit": "%",     "optimal_min": 4.5, "optimal_max": 5.5,  "critical_high": 6.0},
    "urea":       {"label": "Urea",                "unit": "mmol/L","optimal_min": 2.5, "optimal_max": 6.5,  "critical_high": 9.0},
    "vitamin_b12":{"label": "Vitamina B12",        "unit": "pg/mL", "optimal_min": 400, "optimal_max": 900,  "critical_low": 200},
    "testosterone":{"label":"Testosterona",        "unit": "ng/dL", "optimal_min": 400, "optimal_max": 900,  "critical_low": 200},
    "tsh":        {"label": "TSH (Tiroides)",      "unit": "mUI/L", "optimal_min": 0.5, "optimal_max": 2.5,  "critical_high": 5.0},
}

# Métricas de rendimiento que correlacionamos
PERF_METRICS = {
    "ctl":       {"label": "CTL (Fitness crónico)", "higher_is_better": True},
    "tsb":       {"label": "TSB (Frescura)",         "higher_is_better": True},
    "tss_weekly":{"label": "TSS semanal promedio",   "higher_is_better": True},
    "hrv_avg":   {"label": "HRV nocturno promedio",  "higher_is_better": True},
}


def _pearson(x: list[float], y: list[float]) -> Optional[float]:
    """Coeficiente de correlación de Pearson entre dos series de igual longitud."""
    n = len(x)
    if n < 3:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov    = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    std_x  = math.sqrt(sum((v - mean_x)**2 for v in x) / n)
    std_y  = math.sqrt(sum((v - mean_y)**2 for v in y) / n)
    if std_x == 0 or std_y == 0:
        return None
    return round(cov / (std_x * std_y), 3)


def _get_perf_window(user_id: str, center_date: str, window_days: int, db: Session) -> dict:
    """
    Obtiene métricas de rendimiento promedio en una ventana de días alrededor de una fecha.
    """
    d0  = date.fromisoformat(center_date)
    d_lo = (d0 - timedelta(days=window_days)).isoformat()
    d_hi = (d0 + timedelta(days=window_days)).isoformat()

    # CTL / TSB de GarminTrainingLoad
    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso >= d_lo,
            GarminTrainingLoad.date_iso <= d_hi,
        )
        .all()
    )

    ctls = [l.ctl for l in loads if l.ctl is not None]
    tsbs = [l.tsb for l in loads if l.tsb is not None]

    # TSS semanal: actividades en la ventana
    acts = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id  == user_id,
            GarminActivity.date_iso >= d_lo,
            GarminActivity.date_iso <= d_hi,
        )
        .all()
    )
    tss_vals = [a.training_stress_score for a in acts if a.training_stress_score is not None]
    tss_weekly = sum(tss_vals) / max(1, len(tss_vals) / 7) if tss_vals else None

    # HRV: GarminHealthDaily
    hrvs = (
        db.query(GarminHealthDaily)
        .filter(
            GarminHealthDaily.user_id  == user_id,
            GarminHealthDaily.date_iso >= d_lo,
            GarminHealthDaily.date_iso <= d_hi,
            GarminHealthDaily.hrv_last_night.isnot(None),
        )
        .all()
    )
    hrv_vals = [h.hrv_last_night for h in hrvs]

    return {
        "ctl":        round(sum(ctls) / len(ctls), 1) if ctls else None,
        "tsb":        round(sum(tsbs) / len(tsbs), 1) if tsbs else None,
        "tss_weekly": round(tss_weekly, 1) if tss_weekly else None,
        "hrv_avg":    round(sum(hrv_vals) / len(hrv_vals), 1) if hrv_vals else None,
    }


def compute_correlations(user_id: str, db: Session) -> dict:
    """
    Calcula correlaciones entre todos los marcadores de labs disponibles
    y las métricas de rendimiento del atleta.

    Retorna un dict con:
      - correlations: lista de correlaciones significativas (|r| >= 0.4)
      - timeline: historial de labs + performance alineado
      - insights: lista de insights IA sobre los patrones detectados
      - markers_status: estado actual de cada marcador disponible
    """
    # ── 1. Obtener todos los exámenes de labs del año ──────────────────────
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    exams  = (
        db.query(BloodLabExam)
        .filter(
            BloodLabExam.user_id   == user_id,
            BloodLabExam.date_iso >= cutoff,
        )
        .order_by(BloodLabExam.date_iso)
        .all()
    )

    if not exams:
        return {
            "correlations":    [],
            "timeline":        [],
            "insights":        [],
            "markers_status":  {},
            "message":         "Sin exámenes de labs en los últimos 12 meses.",
        }

    # ── 2. Alinear labs con métricas de rendimiento (±30 días) ────────────
    import json as _json
    timeline = []
    for exam in exams:
        perf = _get_perf_window(user_id, exam.date_iso, 30, db)
        try:
            vals = _json.loads(exam.values_json or "{}")
        except Exception:
            vals = {}
        entry = {
            "exam_date":   exam.date_iso,
            "ferritin":    vals.get("ferritin"),
            "hemoglobin":  vals.get("hemoglobin") or vals.get("hb"),
            "cortisol":    vals.get("cortisol"),
            "vitamin_d":   vals.get("vitamin_d"),
            "ck":          vals.get("ck"),
            "hba1c":       vals.get("hba1c"),
            "urea":        vals.get("urea"),
            **perf,
        }
        timeline.append(entry)

    # ── 3. Calcular correlaciones para cada par (marker, metric) ──────────
    correlations = []
    for m_key, m_cfg in LAB_MARKERS.items():
        lab_vals = [t.get(m_key) for t in timeline]
        # Solo si hay ≥3 valores no-None
        valid_idx = [i for i, v in enumerate(lab_vals) if v is not None]
        if len(valid_idx) < 3:
            continue

        x = [lab_vals[i] for i in valid_idx]

        for p_key, p_cfg in PERF_METRICS.items():
            y = [timeline[i].get(p_key) for i in valid_idx]
            valid_y_idx = [j for j, v in enumerate(y) if v is not None]
            if len(valid_y_idx) < 3:
                continue

            x_clean = [x[j] for j in valid_y_idx]
            y_clean = [y[j] for j in valid_y_idx]

            r = _pearson(x_clean, y_clean)
            if r is None:
                continue

            abs_r = abs(r)
            if abs_r < 0.4:
                continue   # correlación débil — no reportar

            direction   = "positiva" if r > 0 else "negativa"
            strength    = "fuerte" if abs_r >= 0.7 else "moderada"
            makes_sense = _is_physiologically_sound(m_key, p_key, r)

            if not makes_sense:
                continue   # descartar correlaciones fisiológicamente inversas (probable artefacto)

            correlations.append({
                "marker":         m_key,
                "marker_label":   m_cfg["label"],
                "metric":         p_key,
                "metric_label":   p_cfg["label"],
                "r":              r,
                "abs_r":          abs_r,
                "direction":      direction,
                "strength":       strength,
                "n_points":       len(x_clean),
                "interpretation": _interpret(m_key, p_key, r, m_cfg, p_cfg),
            })

    # Ordenar por |r| descendente
    correlations.sort(key=lambda c: -c["abs_r"])

    # ── 4. Estado actual de marcadores ────────────────────────────────────
    last_exam   = exams[-1] if exams else None
    markers_status = {}
    if last_exam:
        try:
            last_vals = _json.loads(last_exam.values_json or "{}")
        except Exception:
            last_vals = {}
        for m_key, m_cfg in LAB_MARKERS.items():
            val = last_vals.get(m_key) or last_vals.get("hb" if m_key == "hemoglobin" else m_key)
            if val is None:
                continue
            opt_min = m_cfg.get("optimal_min")
            opt_max = m_cfg.get("optimal_max")
            crit_lo = m_cfg.get("critical_low")
            crit_hi = m_cfg.get("critical_high")

            if crit_lo and val < crit_lo:
                status = "critical_low"
            elif crit_hi and val > crit_hi:
                status = "critical_high"
            elif opt_min and val < opt_min:
                status = "suboptimal_low"
            elif opt_max and val > opt_max:
                status = "suboptimal_high"
            else:
                status = "optimal"

            markers_status[m_key] = {
                "value":      val,
                "unit":       m_cfg["unit"],
                "label":      m_cfg["label"],
                "status":     status,
                "optimal":    f"{opt_min}–{opt_max} {m_cfg['unit']}",
                "exam_date":  last_exam.date_iso,
            }

    # ── 5. Generar insights ────────────────────────────────────────────────
    insights = _generate_correlation_insights(correlations, markers_status)

    return {
        "correlations":   correlations[:10],   # top 10
        "timeline":       timeline,
        "insights":       insights,
        "markers_status": markers_status,
        "exam_count":     len(exams),
        "date_range":     {
            "from": exams[0].exam_date  if exams else None,
            "to":   exams[-1].exam_date if exams else None,
        },
    }


def _is_physiologically_sound(marker: str, metric: str, r: float) -> bool:
    """
    Filtra correlaciones que no tienen sentido fisiológico.
    Evita correlaciones espurias por confounders temporales.
    """
    # Ferritina alta → mayor CTL y TSS (mayor capacidad aeróbica)
    if marker == "ferritin"    and metric in ("ctl", "tss_weekly") and r > 0: return True
    # Ferritina alta → mejor HRV
    if marker == "ferritin"    and metric == "hrv_avg" and r > 0: return True
    # Cortisol alto → menor CTL y TSS (sobreentrenamiento o estrés)
    if marker == "cortisol"    and metric in ("ctl","tss_weekly") and r < 0: return True
    # Cortisol alto → menor HRV (estrés simpático)
    if marker == "cortisol"    and metric == "hrv_avg" and r < 0: return True
    # CK alta → menor TSS (atleta descansa tras esfuerzo → CK sube)
    if marker == "ck"          and metric == "tss_weekly" and r < 0: return True
    # Hemoglobina alta → mayor CTL
    if marker == "hemoglobin"  and metric in ("ctl","hrv_avg") and r > 0: return True
    # Vitamina D alta → mejor CTL y HRV
    if marker == "vitamin_d"   and metric in ("ctl","hrv_avg","tss_weekly") and r > 0: return True
    # HbA1c alta → menor TSS (metabolismo subóptimo)
    if marker == "hba1c"       and metric == "tss_weekly" and r < 0: return True
    # Testosterona alta → mayor CTL
    if marker == "testosterone" and metric in ("ctl","tss_weekly") and r > 0: return True
    # TSH alta → menor CTL (hipotiroidismo reduce capacidad)
    if marker == "tsh"         and metric == "ctl" and r < 0: return True
    return False


def _interpret(marker: str, metric: str, r: float, m_cfg: dict, p_cfg: dict) -> str:
    """Genera una interpretación legible de la correlación."""
    templates = {
        ("ferritin", "ctl"):        f"Por cada 10 ng/mL de ferritina, tu CTL tiende a ser {'mayor' if r>0 else 'menor'}. La ferritina es crítica para el transporte de oxígeno.",
        ("ferritin", "hrv_avg"):    "Ferritina y HRV covarían — niveles óptimos de hierro mejoran la recuperación autonómica.",
        ("cortisol", "ctl"):        "Cortisol elevado se asocia con períodos de menor fitness. Puede ser causa O consecuencia del sobreentrenamiento.",
        ("cortisol", "hrv_avg"):    "Cortisol alto suprime el sistema parasimpático — HRV cae. Indicador temprano de sobreentrenamiento.",
        ("ck", "tss_weekly"):       "CK sube tras entrenamientos intensos. Cuando la CK está elevada, el atleta entrena menos (recuperación correcta).",
        ("hemoglobin", "ctl"):      "Hemoglobina correlaciona con capacidad aeróbica. Optimizar hemoglobina mejora el CTL alcanzable.",
        ("vitamin_d", "ctl"):       "Vitamina D tiene receptores en músculo esquelético. Niveles adecuados facilitan adaptación al entrenamiento.",
        ("vitamin_d", "hrv_avg"):   "Vitamina D regula función inmune y autonómica — niveles óptimos mejoran HRV.",
    }
    return templates.get((marker, metric),
        f"{m_cfg['label']} {'sube' if r>0 else 'baja'} cuando {p_cfg['label']} {'sube' if r>0 else 'baja'} (correlación {'directa' if r>0 else 'inversa'} {abs(r):.2f}).")


def _generate_correlation_insights(correlations: list, markers_status: dict) -> list[str]:
    """Genera insights accionables desde las correlaciones y estado actual."""
    insights = []

    for corr in correlations[:5]:
        marker = corr["marker"]
        status = markers_status.get(marker, {}).get("status", "unknown")
        val    = markers_status.get(marker, {}).get("value")

        if status in ("critical_low", "suboptimal_low") and corr["direction"] == "positiva":
            insights.append(
                f"Tu {corr['marker_label']} está bajo ({val}) y correlaciona positivamente "
                f"con tu {corr['metric_label']} (r={corr['r']:.2f}). "
                f"Optimizarlo podría mejorar directamente tu rendimiento."
            )
        elif status in ("critical_high", "suboptimal_high") and corr["direction"] == "negativa":
            insights.append(
                f"Tu {corr['marker_label']} está elevado ({val}) y correlaciona negativamente "
                f"con tu {corr['metric_label']} (r={corr['r']:.2f}). "
                f"Reducirlo es prioritario para mejorar el rendimiento."
            )
        elif abs(corr["r"]) >= 0.7:
            insights.append(
                f"Correlación fuerte (r={corr['r']:.2f}): cuando tu {corr['marker_label']} "
                f"{'sube' if corr['r']>0 else 'baja'}, tu {corr['metric_label']} también "
                f"{'sube' if corr['r']>0 else 'baja'}. Patrón consistente en {corr['n_points']} exámenes."
            )

    if not insights:
        insights.append(
            "Con los datos disponibles no se detectan correlaciones fuertes aún. "
            "Se necesitan más exámenes de labs a lo largo del tiempo para detectar patrones (mínimo 3)."
        )

    return insights


async def generate_labs_ai_interpretation(
    correlations_data: dict,
    user: User,
) -> str:
    """
    Genera interpretación narrativa IA de las correlaciones de labs del atleta.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    top_corrs = correlations_data.get("correlations", [])[:5]
    status    = correlations_data.get("markers_status", {})
    insights  = correlations_data.get("insights", [])

    if not top_corrs and not status:
        return ""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        status_text = "\n".join([
            f"- {v['label']}: {v['value']} {v['unit']} → {v['status']}"
            for v in status.values()
        ])
        corr_text = "\n".join([
            f"- {c['marker_label']} ↔ {c['metric_label']}: r={c['r']:.2f} ({c['strength']}) — {c['interpretation']}"
            for c in top_corrs
        ])

        prompt = f"""Eres un médico deportólogo analizando los labs de {user.nombre or 'el atleta'}.

ESTADO ACTUAL DE MARCADORES:
{status_text or 'No disponible'}

CORRELACIONES DETECTADAS (lab ↔ rendimiento):
{corr_text or 'Sin correlaciones significativas aún'}

INSIGHTS PREVIOS:
{chr(10).join(insights) or 'Ninguno'}

Genera un análisis de labs en español (2-3 párrafos):
1. Los marcadores más críticos que limitan el rendimiento AHORA
2. El patrón de correlación más importante para este atleta
3. El protocolo de 90 días más importante para optimizar su fisiología

Sé específico con valores y rangos. Tono: médico deportivo directo."""

        resp = client.messages.create(
            model      = "claude-haiku-4-5-20251001",
            max_tokens = 400,
            messages   = [{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip() if resp.content else ""
    except Exception as e:
        logger.error("Labs AI interpretation error: %s", e)
        return ""
