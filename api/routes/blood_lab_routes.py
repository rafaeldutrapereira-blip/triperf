"""
LabX Blood Labs Intelligence
============================
Motor de inteligencia para análisis de sangre en deportistas de resistencia.

Endpoints:
  POST   /labs/exams              — Crear nuevo examen
  GET    /labs/exams              — Listar exámenes del atleta
  GET    /labs/exams/{id}         — Detalle + interpretación IA
  DELETE /labs/exams/{id}         — Eliminar examen
  POST   /labs/exams/{id}/analyze — Disparar interpretación IA (Claude)
  GET    /labs/alerts             — Alertas activas del atleta
  PATCH  /labs/alerts/{id}/dismiss
  GET    /labs/correlation        — Correlación Labs ↔ Carga de entrenamiento
  GET    /labs/markers            — Catálogo de marcadores con rangos deportivos

Rangos de referencia deportivos (NO clínicos):
  Ferritina: <30 bajo, 30-50 subóptimo, 50-150 óptimo
  Hb:        <13.5/12.5 (M/F) bajo, ≥14.5/13.5 óptimo para rendimiento
  Vitamina D: <20 déficit, 20-30 insuficiente, 30-80 óptimo atleta
  Cortisol:   >25 μg/dL en mañana = señal overreaching si coincide con carga alta
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import re

from ..database import get_db
from ..models import BloodLabAlert, BloodLabExam, GarminTrainingLoad, User, AuditLog
from ..auth import get_current_user
from ..redis_client import check_rate_limit_redis
from ..plan_features import require_feature

logger = logging.getLogger("labx.blood_labs")
router = APIRouter(prefix="/labs", tags=["blood_labs"])

# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de marcadores: rangos deportivos, unidades, categoría, display name
# ─────────────────────────────────────────────────────────────────────────────

MARKERS: dict[str, dict] = {
    # ── Hematológico ──────────────────────────────────────────────────────────
    "hb": {
        "name": "Hemoglobina", "unit": "g/dL", "cat": "hematologico",
        "low_m": 13.5, "low_f": 12.5, "opt_low_m": 14.5, "opt_low_f": 13.5,
        "opt_high_m": 17.5, "opt_high_f": 16.0, "high_m": 19.0, "high_f": 18.0,
        "tip_low": "Hemoglobina baja reduce el transporte de O₂ y el VO₂max. Revisar ferritina e ingesta de hierro.",
        "tip_opt": "Hemoglobina en rango óptimo para rendimiento aeróbico.",
        "tip_high": "Hemoglobina muy elevada puede indicar deshidratación. Monitorear.",
    },
    "hct": {
        "name": "Hematocrito", "unit": "%", "cat": "hematologico",
        "low_m": 39.0, "low_f": 36.0, "opt_low_m": 42.0, "opt_low_f": 38.0,
        "opt_high_m": 52.0, "opt_high_f": 47.0, "high_m": 56.0, "high_f": 52.0,
        "tip_low": "Hematocrito bajo: posible anemia o hemodilusión por entrenamiento intenso.",
        "tip_opt": "Hematocrito óptimo para transporte de oxígeno.",
        "tip_high": "Hematocrito >52% (hombres): potencial riesgo cardiovascular. Consultar médico.",
    },
    "ferritin": {
        "name": "Ferritina", "unit": "ng/mL", "cat": "hematologico",
        "low": 0, "subopt_low": 30, "opt_low": 50, "opt_high": 150, "high": 300,
        "tip_low": "Ferritina <30 ng/mL → deplección de reservas de hierro. Fatiga crónica y reducción de VO₂max inminentes. Suplementar con supervisión médica.",
        "tip_subopt": "Ferritina entre 30-50: subóptima para atletas de resistencia. Revisar dieta (carnes rojas, legumbres + vitamina C).",
        "tip_opt": "Ferritina óptima para rendimiento endurance.",
        "tip_high": "Ferritina elevada puede indicar inflamación o hemocromatosis. Consultar médico.",
    },
    "serum_iron": {
        "name": "Hierro sérico", "unit": "μg/dL", "cat": "hematologico",
        "low": 60, "opt_low": 80, "opt_high": 170, "high": 200,
        "tip_low": "Hierro sérico bajo. Considerar suplementación con guía médica.",
        "tip_opt": "Hierro sérico en rango normal.",
        "tip_high": "Hierro sérico elevado. Puede indicar suplementación excesiva.",
    },
    "transferrin_sat": {
        "name": "Saturación de transferrina", "unit": "%", "cat": "hematologico",
        "low": 15, "opt_low": 20, "opt_high": 50, "high": 60,
        "tip_low": "Saturación baja indica deficiencia funcional de hierro.",
        "tip_opt": "Saturación de transferrina en rango normal.",
        "tip_high": "Saturación elevada: posible sobrecarga de hierro.",
    },
    "rbc": {
        "name": "Eritrocitos (GR)", "unit": "M/μL", "cat": "hematologico",
        "low_m": 4.2, "low_f": 3.8, "opt_low_m": 4.6, "opt_low_f": 4.2,
        "opt_high_m": 6.0, "opt_high_f": 5.4, "high_m": 6.5, "high_f": 6.0,
        "tip_low": "Recuento eritrocitario bajo. Puede acompañar anemia.",
        "tip_opt": "Recuento de glóbulos rojos normal.",
        "tip_high": "Policitemia: consultar médico.",
    },
    "reticulocytes": {
        "name": "Reticulocitos", "unit": "%", "cat": "hematologico",
        "low": 0.5, "opt_low": 0.8, "opt_high": 2.5, "high": 3.5,
        "tip_low": "Reticulocitos bajos: médula ósea sin respuesta adecuada. Investigar causa.",
        "tip_opt": "Eritropoyesis activa normal.",
        "tip_high": "Reticulocitos altos: puede indicar hemólisis o respuesta a anemia.",
    },
    # ── Vitaminas y Minerales ─────────────────────────────────────────────────
    "vitamin_d": {
        "name": "Vitamina D (25-OH)", "unit": "ng/mL", "cat": "vitaminas",
        "low": 0, "subopt_low": 20, "opt_low": 30, "opt_high": 80, "high": 100,
        "tip_low": "Déficit severo de Vitamina D (<20 ng/mL). Aumenta riesgo de lesiones óseas y musculares. Suplementar 2000-4000 UI/día bajo supervisión.",
        "tip_subopt": "Vitamina D insuficiente (20-30 ng/mL). Suplementar y maximizar exposición solar.",
        "tip_opt": "Vitamina D óptima. Mantener con exposición solar y/o suplementación.",
        "tip_high": "Vitamina D muy elevada. Pausar suplementación y consultar médico.",
    },
    "b12": {
        "name": "Vitamina B12", "unit": "pg/mL", "cat": "vitaminas",
        "low": 200, "opt_low": 400, "opt_high": 900, "high": 1200,
        "tip_low": "B12 baja: fatiga, anemia megaloblástica. Suplementar, especialmente atletas vegetarianos.",
        "tip_opt": "Vitamina B12 en rango normal.",
        "tip_high": "B12 muy elevada: puede indicar suplementación excesiva o patología hepática.",
    },
    "folate": {
        "name": "Ácido Fólico (B9)", "unit": "ng/mL", "cat": "vitaminas",
        "low": 2.0, "opt_low": 5.0, "opt_high": 20.0, "high": 25.0,
        "tip_low": "Folato bajo: riesgo de anemia megaloblástica. Aumentar vegetales de hoja verde.",
        "tip_opt": "Ácido fólico en rango óptimo.",
        "tip_high": "Folato muy elevado: generalmente inofensivo, pero revisar suplementación.",
    },
    "magnesium": {
        "name": "Magnesio", "unit": "mg/dL", "cat": "minerales",
        "low": 1.5, "opt_low": 1.9, "opt_high": 2.5, "high": 2.8,
        "tip_low": "Magnesio bajo: calambres, mala recuperación muscular, alteraciones del sueño. Aumentar ingesta (frutos secos, legumbres) o suplementar 300-400 mg/día.",
        "tip_opt": "Magnesio en rango óptimo para función muscular y neurológica.",
        "tip_high": "Magnesio elevado: generalmente por suplementación excesiva.",
    },
    "zinc": {
        "name": "Zinc", "unit": "μg/dL", "cat": "minerales",
        "low": 60, "opt_low": 80, "opt_high": 120, "high": 150,
        "tip_low": "Déficit de zinc: inmunodeficiencia, lenta cicatrización, mayor tiempo de recuperación.",
        "tip_opt": "Zinc en rango óptimo.",
        "tip_high": "Zinc muy elevado: revisar suplementación.",
    },
    # ── Hormonal ─────────────────────────────────────────────────────────────
    "cortisol": {
        "name": "Cortisol (mañana)", "unit": "μg/dL", "cat": "hormonal",
        "low": 5, "opt_low": 10, "opt_high": 20, "high": 25,
        "tip_low": "Cortisol muy bajo por la mañana puede indicar insuficiencia suprarrenal o adaptación al estrés crónico. Consultar médico.",
        "tip_opt": "Cortisol matutino en rango normal.",
        "tip_high": "Cortisol elevado + carga alta de entrenamiento = señal de overreaching. Reducir volumen e intensidad esta semana.",
    },
    "testosterone": {
        "name": "Testosterona total", "unit": "ng/dL", "cat": "hormonal",
        "low_m": 300, "opt_low_m": 500, "opt_high_m": 1000, "high_m": 1200,
        "low_f": 10, "opt_low_f": 20, "opt_high_f": 80, "high_f": 100,
        "tip_low": "Testosterona baja: mayor fatiga, menor recuperación muscular, libido reducida. Revisar carga de entrenamiento y calidad de sueño.",
        "tip_opt": "Testosterona en rango óptimo para atletas.",
        "tip_high": "Testosterona muy elevada. Consultar médico endocrinólogo.",
    },
    "t_c_ratio": {
        "name": "Ratio Testosterona/Cortisol", "unit": "ratio", "cat": "hormonal",
        "low": 0.01, "opt_low": 0.02, "opt_high": 0.06, "high": 0.10,
        "tip_low": "Ratio T/C bajo: marcador de overreaching. El atleta puede estar en estado catabólico. Priorizar recuperación.",
        "tip_opt": "Ratio T/C óptimo: balance anabolismo/catabolismo favorable.",
        "tip_high": "Ratio T/C muy alto: monitorear.",
    },
    "tsh": {
        "name": "TSH (Tiroides)", "unit": "mIU/L", "cat": "hormonal",
        "low": 0.1, "opt_low": 0.5, "opt_high": 2.5, "high": 4.5,
        "tip_low": "TSH bajo: posible hipertiroidismo. Puede causar pérdida de peso y taquicardia.",
        "tip_opt": "TSH en rango óptimo para atletas.",
        "tip_high": "TSH elevado: posible hipotiroidismo. Fatiga crónica y dificultad para bajar de peso.",
    },
    "igf1": {
        "name": "IGF-1 (Hormona crecimiento)", "unit": "ng/mL", "cat": "hormonal",
        "low": 100, "opt_low": 150, "opt_high": 300, "high": 400,
        "tip_low": "IGF-1 bajo: menor anabolismo, recuperación muscular más lenta.",
        "tip_opt": "IGF-1 en rango óptimo para recuperación y adaptación al entrenamiento.",
        "tip_high": "IGF-1 elevado. Consultar médico.",
    },
    # ── Inflamación y Daño Muscular ────────────────────────────────────────────
    "crp": {
        "name": "Proteína C Reactiva (PCR)", "unit": "mg/L", "cat": "inflamacion",
        "low": 0, "opt_low": 0, "opt_high": 1.0, "high": 3.0,
        "tip_opt": "PCR en rango óptimo. Inflamación sistémica bajo control.",
        "tip_high": "PCR entre 1-3 mg/L: riesgo cardiovascular moderado. Revisar entrenamiento y dieta.",
        "tip_very_high": "PCR >3 mg/L: inflamación significativa. Descartar infección o patología antes de entrenar intenso.",
    },
    "ck": {
        "name": "Creatinkinasa (CK)", "unit": "U/L", "cat": "inflamacion",
        "low": 0, "opt_low": 0, "opt_high": 200, "high": 500,
        "tip_opt": "CK en reposo normal. Sin daño muscular residual.",
        "tip_high": "CK elevada en reposo: daño muscular activo. Reducir carga de entrenamiento hasta normalizar.",
        "tip_very_high": "CK >1000 U/L en reposo: riesgo de rabdomiólisis. Reposo obligatorio y consulta médica.",
    },
    # ── Metabólico ────────────────────────────────────────────────────────────
    "glucose": {
        "name": "Glucosa en ayunas", "unit": "mg/dL", "cat": "metabolico",
        "low": 60, "opt_low": 70, "opt_high": 99, "high": 125,
        "tip_low": "Hipoglucemia en ayunas: revisar alimentación pre-análisis y buscar causas metabólicas.",
        "tip_opt": "Glucemia en ayunas óptima.",
        "tip_high": "Glucemia alterada en ayunas (100-125 mg/dL): riesgo de prediabetes. Optimizar dieta y consultar médico.",
    },
    "hba1c": {
        "name": "Hemoglobina Glicosilada (HbA1c)", "unit": "%", "cat": "metabolico",
        "low": 0, "opt_low": 0, "opt_high": 5.6, "high": 6.4,
        "tip_opt": "HbA1c óptima: buen control glucémico a largo plazo.",
        "tip_high": "HbA1c entre 5.7-6.4%: prediabetes. Ajustar dieta y consultar médico.",
    },
    "cholesterol": {
        "name": "Colesterol total", "unit": "mg/dL", "cat": "metabolico",
        "low": 100, "opt_low": 100, "opt_high": 200, "high": 240,
        "tip_opt": "Colesterol total en rango óptimo.",
        "tip_high": "Colesterol limítrofe (200-239 mg/dL): revisar LDL/HDL y dieta.",
    },
    "ldl": {
        "name": "LDL (colesterol malo)", "unit": "mg/dL", "cat": "metabolico",
        "low": 0, "opt_low": 0, "opt_high": 100, "high": 130,
        "tip_opt": "LDL en rango óptimo para atletas de resistencia.",
        "tip_high": "LDL elevado: reducir grasas saturadas y trans. Consultar médico.",
    },
    "hdl": {
        "name": "HDL (colesterol bueno)", "unit": "mg/dL", "cat": "metabolico",
        "low_m": 40, "low_f": 50, "opt_low_m": 60, "opt_low_f": 65, "opt_high": 100, "high": 120,
        "tip_low": "HDL bajo: factor de riesgo cardiovascular. El entrenamiento aeróbico debería subirlo.",
        "tip_opt": "HDL alto: protector cardiovascular. Buen indicador de actividad aeróbica regular.",
        "tip_high": "HDL muy elevado: generalmente beneficioso en atletas. Monitorear.",
    },
    "triglycerides": {
        "name": "Triglicéridos", "unit": "mg/dL", "cat": "metabolico",
        "low": 0, "opt_low": 0, "opt_high": 100, "high": 150,
        "tip_opt": "Triglicéridos en rango óptimo.",
        "tip_high": "Triglicéridos elevados: reducir azúcares simples y alcohol. El entrenamiento aeróbico los baja.",
    },
    # ── Función Renal/Hepática ────────────────────────────────────────────────
    "creatinine": {
        "name": "Creatinina sérica", "unit": "mg/dL", "cat": "renal",
        "low_m": 0.7, "low_f": 0.5, "opt_low_m": 0.9, "opt_low_f": 0.7,
        "opt_high_m": 1.3, "opt_high_f": 1.1, "high_m": 1.5, "high_f": 1.3,
        "tip_opt": "Creatinina sérica normal. Función renal adecuada.",
        "tip_high": "Creatinina elevada: puede indicar estrés renal por deshidratación o sobreentrenamiento. Aumentar hidratación.",
    },
    "urea": {
        "name": "Urea (BUN)", "unit": "mg/dL", "cat": "renal",
        "low": 7, "opt_low": 10, "opt_high": 45, "high": 50,
        "tip_low": "Urea muy baja: posible dieta hiperproteica insuficiente.",
        "tip_opt": "Urea en rango normal.",
        "tip_high": "Urea elevada post-entrenamiento: normal si transitoria. Persistente = estrés renal.",
    },
    "alt": {
        "name": "ALT (Transaminasa)", "unit": "U/L", "cat": "hepatico",
        "low": 0, "opt_low": 0, "opt_high": 40, "high": 80,
        "tip_opt": "ALT en rango normal. Sin daño hepático.",
        "tip_high": "ALT elevada: puede indicar daño hepático o muscular severo. Descartar esfuerzo extremo reciente.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de análisis de marcadores
# ─────────────────────────────────────────────────────────────────────────────

def _sex(user: User) -> str:
    """Retorna 'm' o 'f' según el sexo del usuario."""
    if hasattr(user, "sexo") and user.sexo:
        return "f" if user.sexo.lower() in ("f", "female", "femenino", "mujer") else "m"
    return "m"


def _analyze_marker(key: str, value: float, sex: str) -> dict:
    """
    Evalúa un marcador y retorna su status, color y tip.
    Returns: {status, zone, color, tip, pct_of_range}
    """
    m = MARKERS.get(key)
    if not m:
        return {"status": "unknown", "zone": "unknown", "color": "dim", "tip": "", "pct": 50}

    # Rangos con diferenciación por sexo si existen
    low      = m.get(f"low_{sex}",      m.get("low",      None))
    subopt_l = m.get(f"subopt_low_{sex}", m.get("subopt_low", None))
    opt_low  = m.get(f"opt_low_{sex}",  m.get("opt_low",  None))
    opt_high = m.get(f"opt_high_{sex}", m.get("opt_high", None))
    high     = m.get(f"high_{sex}",     m.get("high",     None))

    if opt_low is None or opt_high is None:
        return {"status": "unknown", "zone": "unknown", "color": "dim", "tip": "", "pct": 50}

    # Calcular porcentaje en rango para la barra visual
    range_total = (opt_high - (low or opt_low * 0.5))
    pct = max(0, min(100, int((value - (low or 0)) / max(range_total, 1) * 100)))

    if high is not None and value > high:
        return {"status": "critical", "zone": "very_high", "color": "red",
                "tip": m.get("tip_very_high", m.get("tip_high", "")), "pct": pct}
    if value > opt_high:
        return {"status": "warning", "zone": "high", "color": "amber",
                "tip": m.get("tip_high", ""), "pct": pct}
    if value >= opt_low:
        return {"status": "ok", "zone": "optimal", "color": "green",
                "tip": m.get("tip_opt", ""), "pct": pct}
    if subopt_l is not None and value >= subopt_l:
        return {"status": "warning", "zone": "suboptimal", "color": "amber",
                "tip": m.get("tip_subopt", m.get("tip_low", "")), "pct": pct}
    if low is not None and value >= low:
        return {"status": "critical", "zone": "low", "color": "red",
                "tip": m.get("tip_low", ""), "pct": pct}

    return {"status": "critical", "zone": "very_low", "color": "red",
            "tip": m.get("tip_low", ""), "pct": pct}


def _generate_alerts(exam: BloodLabExam, values: dict, sex: str,
                     recent_ctl: float | None, db: Session) -> list[BloodLabAlert]:
    """Genera alertas automáticas a partir de los valores del examen."""
    alerts = []
    for key, value in values.items():
        if not isinstance(value, (int, float)):
            continue
        analysis = _analyze_marker(key, float(value), sex)
        if analysis["status"] in ("warning", "critical"):
            marker_def = MARKERS.get(key, {})
            severity = "critical" if analysis["status"] == "critical" else "warning"

            # Correlación con carga de entrenamiento
            corr = None
            if key == "ferritin" and recent_ctl and recent_ctl > 60:
                corr = f"CTL actual de {recent_ctl:.0f}: la carga alta pudo acelerar el consumo de reservas de hierro."
            elif key == "cortisol" and analysis["zone"] in ("high", "very_high") and recent_ctl and recent_ctl > 50:
                corr = f"CTL {recent_ctl:.0f}: cortisol elevado + carga alta = riesgo de overreaching."
            elif key == "ck" and analysis["zone"] in ("high", "very_high") and recent_ctl and recent_ctl > 40:
                corr = f"CK elevada con CTL {recent_ctl:.0f}: el plan de esta semana debería ser de recuperación activa."

            alert = BloodLabAlert(
                user_id          = exam.user_id,
                exam_id          = exam.id,
                marker_key       = key,
                severity         = severity,
                title            = f"{marker_def.get('name', key)} fuera de rango óptimo",
                body             = analysis["tip"],
                correlation_note = corr,
            )
            alerts.append(alert)
    return alerts


def _get_recent_ctl(user_id: str, db: Session) -> float | None:
    """Retorna el CTL más reciente del atleta para correlaciones."""
    row = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    return round(row.ctl, 1) if row and row.ctl else None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _audit_lab_access(user_id: str, action: str, exam_id: str | None, db: Session) -> None:
    """GDPR Art.9: registra todos los accesos a datos de salud de categoría especial."""
    try:
        db.add(AuditLog(
            user_id=user_id,
            action=action,
            resource="blood_lab_exam",
            resource_id=exam_id or "",
            details=json.dumps({"category": "special_health_data"}),
        ))
        db.flush()
    except Exception:
        pass  # no bloquear el endpoint si el audit falla


@router.get("/markers")
def get_markers_catalog():
    """
    Retorna el catálogo completo de marcadores con rangos deportivos.
    Útil para renderizar el formulario de ingreso y la leyenda del dashboard.
    """
    result = {}
    for key, m in MARKERS.items():
        result[key] = {
            "key":  key,
            "name": m["name"],
            "unit": m["unit"],
            "cat":  m["cat"],
        }
    return result


@router.post("/exams")
def create_exam(
    body: dict,
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("blood_labs")),
):
    """
    Crea un nuevo examen de sangre.

    Body:
      date_iso:  YYYY-MM-DD  (requerido)
      values:    dict[str, float] — clave = marcador, valor = número
      lab_name:  str  (opcional)
      context:   str  (opcional — "Pre-temporada", "Post-bloque", etc.)
      notes:     str  (opcional)
    """
    date_iso  = body.get("date_iso", "").strip()
    values    = body.get("values", {})
    lab_name  = (body.get("lab_name") or "").strip() or None
    context   = (body.get("context") or "").strip() or None
    notes     = (body.get("notes") or "").strip() or None

    if not date_iso:
        raise HTTPException(422, "date_iso es requerido (YYYY-MM-DD)")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
        raise HTTPException(422, "date_iso debe tener formato YYYY-MM-DD")
    try:
        parsed_date = date.fromisoformat(date_iso)
        if parsed_date > date.today():
            raise HTTPException(422, "date_iso no puede ser una fecha futura")
    except ValueError:
        raise HTTPException(422, "date_iso inválida")
    if not values or not isinstance(values, dict):
        raise HTTPException(422, "values debe ser un objeto con al menos un marcador")
    if len(values) > 60:
        raise HTTPException(422, "Máximo 60 marcadores por examen")

    # Sanitizar valores: solo floats, claves de longitud razonable
    clean_values: dict[str, float] = {}
    for k, v in values.items():
        k = str(k)[:40]
        try:
            clean_values[k] = float(v)
        except (TypeError, ValueError):
            pass
    if not clean_values:
        raise HTTPException(422, "No se encontraron valores numéricos válidos")

    exam = BloodLabExam(
        user_id     = me.id,
        date_iso    = date_iso,
        lab_name    = lab_name,
        context     = context,
        notes       = notes,
        values_json = json.dumps(clean_values, default=float),
    )
    db.add(exam)
    db.flush()  # obtener ID
    _audit_lab_access(me.id, "blood_lab_create", exam.id, db)

    # Generar alertas automáticas
    sex = _sex(me)
    recent_ctl = _get_recent_ctl(me.id, db)
    alerts = _generate_alerts(exam, clean_values, sex, recent_ctl, db)
    for a in alerts:
        db.add(a)

    db.commit()
    logger.info("BloodLabExam creado user=%s exam=%s marcadores=%d alertas=%d",
                me.id, exam.id, len(clean_values), len(alerts))

    return {
        "ok":       True,
        "exam_id":  exam.id,
        "markers":  len(clean_values),
        "alerts":   len(alerts),
    }


@router.get("/exams")
def list_exams(
    limit: int = Query(20, ge=1, le=100),
    db:    Session = Depends(get_db),
    me:    User    = Depends(require_feature("blood_labs")),
):
    """Lista los exámenes del atleta, más recientes primero."""
    exams = (
        db.query(BloodLabExam)
        .filter(BloodLabExam.user_id == me.id)
        .order_by(BloodLabExam.date_iso.desc())
        .limit(limit)
        .all()
    )
    sex = _sex(me)
    result = []
    for e in exams:
        try:
            values = json.loads(e.values_json)
        except Exception:
            values = {}
        n_alerts = sum(
            1 for a in (e.alerts or []) if not a.dismissed_at
        )
        n_critical = sum(
            1 for a in (e.alerts or [])
            if a.severity == "critical" and not a.dismissed_at
        )
        result.append({
            "id":         e.id,
            "date_iso":   e.date_iso,
            "lab_name":   e.lab_name,
            "context":    e.context,
            "markers":    len(values),
            "n_alerts":   n_alerts,
            "n_critical": n_critical,
            "has_ai":     bool(e.ai_interpretation),
        })
    return result


@router.get("/exams/{exam_id}")
def get_exam(
    exam_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(require_feature("blood_labs")),
):
    """
    Detalle completo de un examen con análisis de cada marcador.
    Incluye interpretación IA si disponible.
    """
    exam = db.query(BloodLabExam).filter(
        BloodLabExam.id      == exam_id,
        BloodLabExam.user_id == me.id,
    ).first()
    if not exam:
        raise HTTPException(404, "Examen no encontrado")

    _audit_lab_access(me.id, "blood_lab_read", exam_id, db)

    try:
        values = json.loads(exam.values_json)
    except Exception:
        values = {}

    sex = _sex(me)
    analyzed: dict[str, dict] = {}
    for key, val in values.items():
        if not isinstance(val, (int, float)):
            continue
        marker_def = MARKERS.get(key, {})
        analysis   = _analyze_marker(key, float(val), sex)
        analyzed[key] = {
            "key":    key,
            "name":   marker_def.get("name", key),
            "unit":   marker_def.get("unit", ""),
            "cat":    marker_def.get("cat", "otros"),
            "value":  val,
            **analysis,
        }

    # Alertas activas de este examen
    exam_alerts = [
        {
            "id":               a.id,
            "marker_key":       a.marker_key,
            "severity":         a.severity,
            "title":            a.title,
            "body":             a.body,
            "correlation_note": a.correlation_note,
            "dismissed":        bool(a.dismissed_at),
        }
        for a in (exam.alerts or [])
    ]

    # Interpretación IA
    ai_interpretation = None
    if exam.ai_interpretation:
        try:
            ai_interpretation = json.loads(exam.ai_interpretation)
        except Exception:
            ai_interpretation = {"text": exam.ai_interpretation}

    return {
        "id":               exam.id,
        "date_iso":         exam.date_iso,
        "lab_name":         exam.lab_name,
        "context":          exam.context,
        "notes":            exam.notes,
        "markers":          analyzed,
        "alerts":           exam_alerts,
        "ai_interpretation": ai_interpretation,
        "ai_interpreted_at": exam.ai_interpreted_at.isoformat() if exam.ai_interpreted_at else None,
    }


@router.delete("/exams/{exam_id}")
def delete_exam(
    exam_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(require_feature("blood_labs")),
):
    exam = db.query(BloodLabExam).filter(
        BloodLabExam.id      == exam_id,
        BloodLabExam.user_id == me.id,
    ).first()
    if not exam:
        raise HTTPException(404, "Examen no encontrado")
    db.delete(exam)
    db.commit()
    return {"ok": True}


@router.post("/exams/{exam_id}/analyze")
def analyze_exam_with_ai(
    exam_id: str,
    request: Request,
    db:      Session = Depends(get_db),
    me:      User    = Depends(require_feature("blood_labs")),
):
    """
    Dispara la interpretación IA del examen con Claude.
    Usa el contexto fisiológico completo del atleta (CTL/ATL/TSB/HRV/readiness)
    para generar una interpretación personalizada y con correlaciones reales.
    """
    # Rate limit: 10 análisis IA por usuario por hora (endpoint costoso)
    allowed, _ = check_rate_limit_redis(f"rl:lab_ai:{me.id}", max_count=10, window_seconds=3600, strict=True)
    if not allowed:
        raise HTTPException(429, "Límite de análisis IA alcanzado. Máximo 10 por hora.")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY no configurada")

    exam = db.query(BloodLabExam).filter(
        BloodLabExam.id      == exam_id,
        BloodLabExam.user_id == me.id,
    ).first()
    if not exam:
        raise HTTPException(404, "Examen no encontrado")

    try:
        values = json.loads(exam.values_json)
    except Exception:
        raise HTTPException(400, "Examen con datos inválidos")

    sex = _sex(me)
    analyzed_markers = []
    for key, val in values.items():
        if not isinstance(val, (int, float)):
            continue
        m      = MARKERS.get(key, {})
        status = _analyze_marker(key, float(val), sex)
        analyzed_markers.append(
            f"- {m.get('name', key)}: {val} {m.get('unit', '')} → {status['zone']} [{status['tip']}]"
        )

    # Contexto de entrenamiento del atleta
    from ..services.context_engine import get_context_for_prompt
    athlete_context = get_context_for_prompt(me.id, db)

    prompt = f"""Eres el especialista en medicina deportiva de LabX.
Analiza el siguiente examen de sangre de un atleta de triatlón/resistencia.

CONTEXTO DE ENTRENAMIENTO DEL ATLETA:
{athlete_context}

EXAMEN DE SANGRE — {exam.date_iso} ({exam.context or 'Sin contexto específico'}):
{chr(10).join(analyzed_markers)}

TAREA:
1. Da un resumen ejecutivo (3-4 líneas) del estado general basado en estos Labs.
2. Identifica los 2-3 hallazgos más importantes y su impacto directo en el rendimiento.
3. Correlaciona los marcadores alterados con la carga de entrenamiento del atleta (usa los datos de CTL/ATL/TSB/HRV que tienes).
4. Propón 3 acciones concretas y priorizadas (suplementación, cambios en dieta, ajuste de carga).
5. Indica cuándo debería repetir el análisis.

FORMATO: Responde en español. Usa bullets cortos. Sé específico con los números del atleta. No uses jerga médica innecesaria.
"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp   = client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 1200,
            messages   = [{"role": "user", "content": prompt}],
        )
        interpretation_text = resp.content[0].text if resp.content else ""
    except Exception as e:
        logger.error("AI blood lab analysis error user=%s exam=%s: %s", me.id, exam_id, e)
        raise HTTPException(502, "Error al generar interpretación IA")

    # Persistir
    exam.ai_interpretation  = json.dumps({"text": interpretation_text}, ensure_ascii=False)
    exam.ai_interpreted_at  = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    logger.info("AI blood lab analysis completado user=%s exam=%s tokens=%d",
                me.id, exam_id, resp.usage.input_tokens + resp.usage.output_tokens)

    return {
        "ok":             True,
        "interpretation": interpretation_text,
    }


@router.get("/alerts")
def get_active_alerts(
    limit:             int  = Query(20, ge=1, le=100),
    include_dismissed: bool = Query(False),
    db:    Session = Depends(get_db),
    me:    User    = Depends(require_feature("blood_labs")),
):
    """Retorna las alertas activas de labs del atleta, ordenadas por severidad."""
    q = (
        db.query(BloodLabAlert)
        .filter(BloodLabAlert.user_id == me.id)
        .join(BloodLabExam)
    )
    if not include_dismissed:
        q = q.filter(BloodLabAlert.dismissed_at.is_(None))

    alerts = (
        q.order_by(BloodLabAlert.severity.desc(), BloodLabAlert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":               a.id,
            "marker_key":       a.marker_key,
            "severity":         a.severity,
            "title":            a.title,
            "body":             a.body,
            "correlation_note": a.correlation_note,
            "exam_id":          a.exam_id,
            "exam_date":        a.exam.date_iso if a.exam else None,
            "dismissed":        bool(a.dismissed_at),
        }
        for a in alerts
    ]


@router.patch("/alerts/{alert_id}/dismiss")
def dismiss_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    alert = db.query(BloodLabAlert).filter(
        BloodLabAlert.id      == alert_id,
        BloodLabAlert.user_id == me.id,
    ).first()
    if not alert:
        raise HTTPException(404, "Alerta no encontrada")
    alert.dismissed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


@router.get("/correlation")
def get_labs_correlation(
    days: int = Query(120, ge=30, le=365),
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("blood_labs")),
):
    """
    Correlación temporal entre Labs y Carga de Entrenamiento.
    Para cada examen, retorna el CTL/ATL/TSB del día del examen.
    Útil para el gráfico superpuesto Labs + carga.
    """
    since = (date.today() - timedelta(days=days)).isoformat()

    exams = (
        db.query(BloodLabExam)
        .filter(
            BloodLabExam.user_id == me.id,
            BloodLabExam.date_iso >= since,
        )
        .order_by(BloodLabExam.date_iso)
        .all()
    )

    # Carga de entrenamiento en las fechas de los exámenes
    exam_dates = {e.date_iso for e in exams}
    loads = {
        row.date_iso: row
        for row in db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id == me.id,
            GarminTrainingLoad.date_iso.in_(list(exam_dates)),
        )
        .all()
    }

    # Carga promedio en los 30 días previos a cada examen
    result = []
    for e in exams:
        try:
            values = json.loads(e.values_json)
        except Exception:
            values = {}

        load_on_day = loads.get(e.date_iso)

        # Calcular CTL promedio 30d previos al examen
        prev_since = (
            datetime.fromisoformat(e.date_iso) - timedelta(days=30)
        ).strftime("%Y-%m-%d")
        prev_loads = db.query(GarminTrainingLoad).filter(
            GarminTrainingLoad.user_id  == me.id,
            GarminTrainingLoad.date_iso >= prev_since,
            GarminTrainingLoad.date_iso <  e.date_iso,
        ).all()
        avg_ctl_30d = (
            round(sum(r.ctl for r in prev_loads if r.ctl) / len(prev_loads), 1)
            if prev_loads else None
        )

        # Valores clave para el gráfico
        key_values = {
            k: values.get(k) for k in
            ["hb", "ferritin", "vitamin_d", "cortisol", "testosterone",
             "crp", "ck", "hba1c"]
            if k in values
        }

        result.append({
            "exam_id":    e.id,
            "date_iso":   e.date_iso,
            "context":    e.context,
            "lab_name":   e.lab_name,
            "ctl":        round(load_on_day.ctl, 1) if load_on_day and load_on_day.ctl else None,
            "atl":        round(load_on_day.atl, 1) if load_on_day and load_on_day.atl else None,
            "tsb":        round(load_on_day.tsb, 1) if load_on_day and load_on_day.tsb else None,
            "avg_ctl_30d": avg_ctl_30d,
            "values":     key_values,
            "n_alerts":   sum(1 for a in (e.alerts or []) if not a.dismissed_at),
        })

    return result


@router.get("/summary")
def get_labs_summary(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    """
    Resumen del estado actual de Labs del atleta:
    - Examen más reciente
    - Marcadores en rojo/amarillo/verde
    - Alertas activas por severidad
    - Próxima fecha recomendada de análisis
    """
    latest = (
        db.query(BloodLabExam)
        .filter(BloodLabExam.user_id == me.id)
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )
    if not latest:
        return {
            "has_labs":    False,
            "message":     "Sin análisis de sangre registrados. Sube tu primer examen para activar Blood Labs Intelligence.",
        }

    try:
        values = json.loads(latest.values_json)
    except Exception:
        values = {}

    sex = _sex(me)
    counts = {"ok": 0, "warning": 0, "critical": 0}
    for key, val in values.items():
        if not isinstance(val, (int, float)):
            continue
        analysis = _analyze_marker(key, float(val), sex)
        if analysis["status"] == "ok":
            counts["ok"] += 1
        elif analysis["status"] == "warning":
            counts["warning"] += 1
        elif analysis["status"] == "critical":
            counts["critical"] += 1

    active_alerts = (
        db.query(BloodLabAlert)
        .filter(
            BloodLabAlert.user_id    == me.id,
            BloodLabAlert.dismissed_at.is_(None),
        )
        .count()
    )

    # Días desde el último examen
    try:
        last_date = date.fromisoformat(latest.date_iso)
        days_since = (date.today() - last_date).days
    except Exception:
        days_since = None

    # Recomendación: cada 3 meses para atletas de resistencia
    next_recommended = None
    if days_since is not None:
        remaining = 90 - days_since
        next_recommended = remaining if remaining > 0 else 0

    return {
        "has_labs":          True,
        "latest_date":       latest.date_iso,
        "latest_context":    latest.context,
        "days_since":        days_since,
        "next_recommended_in_days": next_recommended,
        "total_markers":     len(values),
        "markers_ok":        counts["ok"],
        "markers_warning":   counts["warning"],
        "markers_critical":  counts["critical"],
        "active_alerts":     active_alerts,
        "total_exams":       db.query(BloodLabExam).filter(BloodLabExam.user_id == me.id).count(),
    }


@router.get("/correlations")
def get_labs_correlations(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    """
    Correlaciones estadísticas entre marcadores de labs y métricas de rendimiento.
    Identifica qué marcadores están limitando el rendimiento con evidencia cuantitativa.
    Solo muestra correlaciones con |r| >= 0.4 y validez fisiológica.
    Requiere al menos 3 exámenes históricos para ser significativo.
    """
    from ..services.blood_labs_correlation_service import compute_correlations
    return compute_correlations(me.id, db)


@router.post("/correlations/ai-interpretation")
async def get_labs_ai_interpretation(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    """
    Genera interpretación narrativa IA de las correlaciones labs↔rendimiento.
    Identifica los protocolos más importantes para optimizar la fisiología del atleta.
    """
    from ..services.blood_labs_correlation_service import (
        compute_correlations,
        generate_labs_ai_interpretation,
    )
    data      = compute_correlations(me.id, db)
    narrative = await generate_labs_ai_interpretation(data, me)
    data["ai_narrative"] = narrative
    return data


@router.get("/timeline")
def get_labs_timeline(
    months: int = 12,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    """
    Timeline de todos los marcadores de labs en los últimos N meses,
    alineado con métricas de rendimiento (CTL, TSS, HRV).
    Útil para visualizar cómo cambian los labs a lo largo del ciclo de entrenamiento.
    """
    if months < 1 or months > 36:
        months = 12
    from ..services.blood_labs_correlation_service import compute_correlations
    data = compute_correlations(me.id, db)
    return {
        "timeline":     data.get("timeline", []),
        "date_range":   data.get("date_range", {}),
        "exam_count":   data.get("exam_count", 0),
    }


@router.get("/training-impact")
def get_labs_training_impact(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    """
    Training Restriction Score (TRS) — impacto de los biomarcadores actuales
    sobre la capacidad de entrenamiento.

    Motor determinista (sin LLM): traduce resultados de labs a:
    - TRS 0-100 (100 = sin restricciones)
    - Restricciones por disciplina (natación, ciclismo, carrera, fuerza)
    - Protocolo de suplementación priorizado
    - Acciones clave ordenadas por urgencia
    - Modificador de volumen CTL
    """
    latest = (
        db.query(BloodLabExam)
        .filter(BloodLabExam.user_id == me.id)
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )
    if not latest:
        return {
            "has_labs": False,
            "message":  "Sin análisis de sangre registrados. Sube tu primer examen para activar esta función.",
        }

    try:
        values = json.loads(latest.values_json)
    except Exception:
        values = {}

    # Obtener CTL actual
    from ..models import GarminTrainingLoad
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == me.id)
        .order_by(GarminTrainingLoad.date.desc())
        .first()
    )
    ctl = float(load.ctl) if load and load.ctl else None

    sex = _sex(me)

    from ..services.blood_labs_impact_service import compute_training_impact

    report = compute_training_impact(
        values=values,
        sex=sex,
        ctl=ctl,
        exam_date=latest.date_iso,
    )

    return {
        "has_labs":         True,
        "exam_date":        report.exam_date,
        "trs":              report.trs,
        "trs_label":        report.trs_label,
        "trs_color":        report.trs_color,
        "primary_limiters": report.primary_limiters,
        "ctl_volume_modifier": report.ctl_volume_modifier,
        "disciplines":      [
            {
                "discipline":       d.discipline,
                "allowed":          d.allowed,
                "max_intensity":    d.max_intensity,
                "volume_modifier":  round(d.volume_modifier, 2),
                "notes":            d.notes,
            }
            for d in report.disciplines
        ],
        "supplements":      report.supplements,
        "medical_referral": report.medical_referral,
        "medical_reason":   report.medical_reason,
        "next_labs_in_days": report.next_labs_in_days,
        "key_actions":      report.key_actions,
        "markers_detail":   [
            {
                "key":               m.key,
                "name":              m.name,
                "value":             m.value,
                "unit":              m.unit,
                "status":            m.status,
                "restriction_score": m.restriction_score,
                "intensity_cap":     m.intensity_cap,
                "volume_modifier":   m.volume_modifier,
                "supplement":        m.supplement_hint,
            }
            for m in report.markers_evaluated
        ],
        "warnings": report.warnings,
    }


@router.get("/team")
def get_team_labs_status(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("blood_labs")),
):
    """
    Vista de equipo (solo coaches y admins): estado de labs de todos los atletas asignados.
    Permite al coach identificar atletas con limitaciones fisiológicas que requieren
    ajuste de plan o derivación médica.
    """
    if me.rol not in ("coach", "admin"):
        raise HTTPException(403, "Solo disponible para coaches y administradores")

    from ..models import CoachAthlete

    # Obtener atletas asignados al coach
    assignments = (
        db.query(CoachAthlete)
        .filter(CoachAthlete.coach_id == me.id, CoachAthlete.active == True)
        .all()
    )
    athlete_ids = [a.athlete_id for a in assignments]

    if not athlete_ids:
        return {
            "team_avg_trs":      100,
            "athletes_count":    0,
            "critical_athletes": [],
            "warning_athletes":  [],
            "ok_athletes":       [],
            "alerts":            [],
            "message":           "Sin atletas asignados",
        }

    from ..models import GarminTrainingLoad

    athletes_data = []
    for aid in athlete_ids:
        athlete = db.query(User).filter(User.id == aid).first()
        if not athlete:
            continue

        latest_exam = (
            db.query(BloodLabExam)
            .filter(BloodLabExam.user_id == aid)
            .order_by(BloodLabExam.date_iso.desc())
            .first()
        )
        if not latest_exam:
            continue

        load = (
            db.query(GarminTrainingLoad)
            .filter(GarminTrainingLoad.user_id == aid)
            .order_by(GarminTrainingLoad.date.desc())
            .first()
        )

        athletes_data.append({
            "user_id":    aid,
            "name":       f"{getattr(athlete, 'nombre', '') or ''} {getattr(athlete, 'apellido', '') or ''}".strip() or athlete.email,
            "sex":        _sex(athlete),
            "values_json": latest_exam.values_json,
            "exam_date":  latest_exam.date_iso,
            "ctl":        float(load.ctl) if load and load.ctl else None,
        })

    if not athletes_data:
        return {
            "team_avg_trs":      100,
            "athletes_count":    len(athlete_ids),
            "critical_athletes": [],
            "warning_athletes":  [],
            "ok_athletes":       [],
            "alerts":            [],
            "message":           "Ningún atleta tiene análisis de sangre registrados",
        }

    from ..services.blood_labs_impact_service import compute_team_labs_status
    return compute_team_labs_status(athletes_data)
