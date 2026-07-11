"""
LabX — Blood Labs Training Impact Service (Sprint 22)
=======================================================
Motor determinista (sin LLM) que traduce biomarcadores a restricciones
y recomendaciones de entrenamiento concretas.

Lógica central:
  1. Leer el examen de labs más reciente del atleta
  2. Evaluar cada marcador vs umbrales deportivos
  3. Calcular un "Training Restriction Score" (TRS) 0-100
  4. Generar restricciones por disciplina (natación, ciclismo, carrera)
  5. Generar protocolo de recuperación/suplementación
  6. Cross-correlate con CTL actual para ajustar volumen recomendado

Diferenciador:
  Ningún competidor (TP, Intervals.icu, Garmin Connect, Strava) integra
  resultados de análisis de sangre con la carga de entrenamiento actual.
  Este módulo es exclusivo de LabX.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("labx.blood_labs_impact")


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarkerImpact:
    key: str
    name: str
    value: float
    unit: str
    status: str          # "ok" | "suboptimal" | "warning" | "critical"
    restriction_score: float   # 0-40 impacto en score total
    intensity_cap: Optional[str]   # None | "zone3" | "zone2" | "zone1"
    volume_modifier: float     # 1.0 = normal; 0.8 = reducir 20%; 0.5 = reducir 50%
    supplement_hint: Optional[str]
    recovery_days_needed: int  # días hasta re-evaluar entrenamiento


@dataclass
class DisciplineRestriction:
    discipline: str        # "swim" | "bike" | "run" | "strength"
    allowed: bool
    max_intensity: str     # "any" | "zone2" | "zone1" | "rest"
    volume_modifier: float
    notes: list[str]


@dataclass
class TrainingImpactReport:
    trs: int                           # Training Restriction Score 0-100 (100 = sin restricciones)
    trs_label: str                     # "verde" | "amarillo" | "naranja" | "rojo"
    trs_color: str
    primary_limiters: list[str]        # Marcadores que más limitan
    disciplines: list[DisciplineRestriction]
    ctl_volume_modifier: float         # Cuánto % del CTL actual es alcanzable
    supplements: list[dict]            # {name, dose, timing, duration_weeks, evidence}
    medical_referral: bool
    medical_reason: Optional[str]
    next_labs_in_days: int             # Cuándo repetir análisis
    key_actions: list[str]             # 3-5 acciones prioritarias
    markers_evaluated: list[MarkerImpact]
    exam_date: str
    warnings: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Marker evaluation rules (sport-science based, sex-aware)
# ─────────────────────────────────────────────────────────────────────────────

def _eval_ferritin(val: float, sex: str) -> MarkerImpact:
    if val < 15:
        return MarkerImpact("ferritin", "Ferritina", val, "ng/mL", "critical",
            restriction_score=35, intensity_cap="zone1", volume_modifier=0.4,
            supplement_hint="Hierro bisglicinate 25-50mg/día en ayunas + vitamina C",
            recovery_days_needed=30)
    if val < 30:
        return MarkerImpact("ferritin", "Ferritina", val, "ng/mL", "warning",
            restriction_score=22, intensity_cap="zone2", volume_modifier=0.65,
            supplement_hint="Hierro bisglicinate 25mg/día con vitamina C",
            recovery_days_needed=21)
    if val < 50:
        return MarkerImpact("ferritin", "Ferritina", val, "ng/mL", "suboptimal",
            restriction_score=10, intensity_cap="zone3", volume_modifier=0.85,
            supplement_hint="Revisión dietética — aumentar hierro hemo (carnes rojas 2×/sem)",
            recovery_days_needed=14)
    return MarkerImpact("ferritin", "Ferritina", val, "ng/mL", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_hemoglobin(val: float, sex: str) -> MarkerImpact:
    low_thresh = 12.5 if sex == "F" else 13.5
    warn_thresh = 13.0 if sex == "F" else 14.0
    if val < low_thresh:
        return MarkerImpact("hemoglobin", "Hemoglobina", val, "g/dL", "critical",
            restriction_score=38, intensity_cap="zone1", volume_modifier=0.35,
            supplement_hint="Descartar anemia ferropénica con médico — posible suplementación IV",
            recovery_days_needed=45)
    if val < warn_thresh:
        return MarkerImpact("hemoglobin", "Hemoglobina", val, "g/dL", "warning",
            restriction_score=20, intensity_cap="zone2", volume_modifier=0.70,
            supplement_hint="Hierro + vitamina B12 + ácido fólico — revisar absorción GI",
            recovery_days_needed=21)
    return MarkerImpact("hemoglobin", "Hemoglobina", val, "g/dL", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_vitamin_d(val: float, sex: str) -> MarkerImpact:
    if val < 20:
        return MarkerImpact("vitamin_d", "Vitamina D", val, "ng/mL", "critical",
            restriction_score=18, intensity_cap="zone2", volume_modifier=0.75,
            supplement_hint="Vitamina D3 4000-6000 UI/día × 8-12 semanas + control analítico",
            recovery_days_needed=30)
    if val < 30:
        return MarkerImpact("vitamin_d", "Vitamina D", val, "ng/mL", "warning",
            restriction_score=8, intensity_cap=None, volume_modifier=0.90,
            supplement_hint="Vitamina D3 2000 UI/día + exposición solar 15min/día",
            recovery_days_needed=21)
    if val < 40:
        return MarkerImpact("vitamin_d", "Vitamina D", val, "ng/mL", "suboptimal",
            restriction_score=3, intensity_cap=None, volume_modifier=0.95,
            supplement_hint="Vitamina D3 1000 UI/día mantenimiento",
            recovery_days_needed=60)
    return MarkerImpact("vitamin_d", "Vitamina D", val, "ng/mL", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_cortisol(val: float, sex: str) -> MarkerImpact:
    if val > 30:
        return MarkerImpact("cortisol", "Cortisol matutino", val, "μg/dL", "critical",
            restriction_score=30, intensity_cap="zone1", volume_modifier=0.40,
            supplement_hint="Ashwagandha 600mg/día + magnesio glicinato 400mg noche",
            recovery_days_needed=21)
    if val > 22:
        return MarkerImpact("cortisol", "Cortisol matutino", val, "μg/dL", "warning",
            restriction_score=15, intensity_cap="zone2", volume_modifier=0.65,
            supplement_hint="Reducir estresores externos + adaptógenos (rhodiola 200mg)",
            recovery_days_needed=14)
    return MarkerImpact("cortisol", "Cortisol matutino", val, "μg/dL", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_ck(val: float, sex: str) -> MarkerImpact:
    # Creatina Quinasa — daño muscular agudo
    if val > 1000:
        return MarkerImpact("ck", "Creatina Quinasa", val, "U/L", "critical",
            restriction_score=32, intensity_cap="zone1", volume_modifier=0.30,
            supplement_hint="Creatina monohidrato 5g/día + proteína 2g/kg/día",
            recovery_days_needed=7)
    if val > 500:
        return MarkerImpact("ck", "Creatina Quinasa", val, "U/L", "warning",
            restriction_score=14, intensity_cap="zone2", volume_modifier=0.60,
            supplement_hint="Reducir eccéntricos — priorizar natación y ciclismo",
            recovery_days_needed=5)
    if val > 300:
        return MarkerImpact("ck", "Creatina Quinasa", val, "U/L", "suboptimal",
            restriction_score=5, intensity_cap=None, volume_modifier=0.85,
            supplement_hint=None, recovery_days_needed=3)
    return MarkerImpact("ck", "Creatina Quinasa", val, "U/L", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_testosterone(val: float, sex: str) -> MarkerImpact:
    if sex == "M":
        if val < 200:
            return MarkerImpact("testosterone", "Testosterona", val, "ng/dL", "critical",
                restriction_score=25, intensity_cap="zone2", volume_modifier=0.55,
                supplement_hint="Evaluación endocrinológica urgente — señal overtraining severo",
                recovery_days_needed=30)
        if val < 350:
            return MarkerImpact("testosterone", "Testosterona", val, "ng/dL", "warning",
                restriction_score=12, intensity_cap="zone2", volume_modifier=0.70,
                supplement_hint="Reducir volumen 30% + priorizar sueño 8-9h + Zinc 15mg/día",
                recovery_days_needed=21)
    else:  # F
        if val < 15:
            return MarkerImpact("testosterone", "Testosterona", val, "ng/dL", "warning",
                restriction_score=10, intensity_cap=None, volume_modifier=0.80,
                supplement_hint="Revisión ginecológica si síntomas. Zinc 8mg + D-AA opcional.",
                recovery_days_needed=21)
    return MarkerImpact("testosterone", "Testosterona", val, "ng/dL", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_tsh(val: float, sex: str) -> MarkerImpact:
    if val > 5.0 or val < 0.3:
        return MarkerImpact("tsh", "TSH (Tiroides)", val, "mUI/L", "critical",
            restriction_score=28, intensity_cap="zone2", volume_modifier=0.50,
            supplement_hint=None,
            recovery_days_needed=30)
    if val > 3.5 or val < 0.5:
        return MarkerImpact("tsh", "TSH (Tiroides)", val, "mUI/L", "warning",
            restriction_score=12, intensity_cap=None, volume_modifier=0.80,
            supplement_hint="Revisión endocrina. Asegurar ingesta de yodo y selenio.",
            recovery_days_needed=21)
    return MarkerImpact("tsh", "TSH (Tiroides)", val, "mUI/L", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_vitamin_b12(val: float, sex: str) -> MarkerImpact:
    if val < 200:
        return MarkerImpact("vitamin_b12", "Vitamina B12", val, "pg/mL", "critical",
            restriction_score=18, intensity_cap="zone2", volume_modifier=0.70,
            supplement_hint="B12 metilcobalamina 1000μg/día sublingual × 4 semanas",
            recovery_days_needed=21)
    if val < 300:
        return MarkerImpact("vitamin_b12", "Vitamina B12", val, "pg/mL", "warning",
            restriction_score=8, intensity_cap=None, volume_modifier=0.88,
            supplement_hint="B12 metilcobalamina 500μg/día",
            recovery_days_needed=14)
    return MarkerImpact("vitamin_b12", "Vitamina B12", val, "pg/mL", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


def _eval_urea(val: float, sex: str) -> MarkerImpact:
    # Urea alta = catabolismo proteico excesivo
    if val > 9.0:
        return MarkerImpact("urea", "Urea", val, "mmol/L", "warning",
            restriction_score=10, intensity_cap="zone2", volume_modifier=0.75,
            supplement_hint="Aumentar ingesta proteica a 2-2.5g/kg. BCAAs intra-entrenamiento.",
            recovery_days_needed=7)
    if val > 7.0:
        return MarkerImpact("urea", "Urea", val, "mmol/L", "suboptimal",
            restriction_score=4, intensity_cap=None, volume_modifier=0.90,
            supplement_hint="Proteína post-entreno dentro de 30 min. 30-40g por sesión.",
            recovery_days_needed=5)
    return MarkerImpact("urea", "Urea", val, "mmol/L", "ok",
        restriction_score=0, intensity_cap=None, volume_modifier=1.0,
        supplement_hint=None, recovery_days_needed=90)


# Dispatcher
_MARKER_EVAL_FNS = {
    "ferritin":    _eval_ferritin,
    "hb":          _eval_hemoglobin,
    "hemoglobin":  _eval_hemoglobin,
    "vitamin_d":   _eval_vitamin_d,
    "cortisol":    _eval_cortisol,
    "ck":          _eval_ck,
    "testosterone": _eval_testosterone,
    "tsh":         _eval_tsh,
    "vitamin_b12": _eval_vitamin_b12,
    "urea":        _eval_urea,
}


# ─────────────────────────────────────────────────────────────────────────────
# Discipline restrictions from marker impacts
# ─────────────────────────────────────────────────────────────────────────────

def _compute_disciplines(markers: list[MarkerImpact]) -> list[DisciplineRestriction]:
    """
    Traduce el conjunto de marcadores alterados a restricciones por disciplina.
    Reglas fisiológicas:
    - CK alto → limitar carrera (alto impacto excéntrico) primero
    - Ferritina/Hb bajos → limitar todas las intensidades altas
    - Cortisol alto → limitar entrenamientos largos (duración > 90min)
    """
    worst_cap = None
    worst_vol = 1.0
    markers_warning = [m for m in markers if m.status in ("warning", "critical")]
    markers_critical = [m for m in markers if m.status == "critical"]

    # Peor cap de intensidad
    cap_order = [None, "zone3", "zone2", "zone1"]
    for m in markers:
        if m.intensity_cap and cap_order.index(m.intensity_cap) > cap_order.index(worst_cap):
            worst_cap = m.intensity_cap
        worst_vol = min(worst_vol, m.volume_modifier)

    # CK específicamente limita running más que natación/ciclismo
    ck_marker = next((m for m in markers if m.key == "ck"), None)
    cortisol_marker = next((m for m in markers if m.key == "cortisol"), None)

    def _notes(discipline: str) -> list[str]:
        notes = []
        for m in markers_warning:
            if discipline == "run" and m.key == "ck":
                notes.append(f"CK {m.value} U/L → reducir sesiones de carrera con cuestas y eccéntricos")
            elif discipline == "strength" and m.key in ("ck", "testosterone"):
                notes.append(f"{m.name} alterada → priorizar fuerza resistencia sobre hipertrofia")
            elif m.key in ("ferritin", "hemoglobin", "hb"):
                notes.append(f"{m.name} baja → zonas altas limitadas en todos los deportes")
            elif m.key == "cortisol" and discipline in ("bike", "run"):
                notes.append("Cortisol elevado → limitar sesiones >90min hasta normalización")
        return notes

    # Run: más impacto excéntrico — si CK critico, limitar más
    run_vol = worst_vol
    run_cap = worst_cap
    if ck_marker and ck_marker.status == "critical":
        run_cap = "zone1"
        run_vol = min(run_vol, 0.30)
    elif ck_marker and ck_marker.status == "warning":
        run_vol = min(run_vol, 0.55)

    # Strength: afectada por CK y testosterona
    str_vol = worst_vol * 0.9 if markers_warning else 1.0
    str_allowed = not (markers_critical and any(m.key in ("ck", "testosterone") for m in markers_critical))

    # Cortisol alto → limitar duración bike/run (no intensidad directamente)
    bike_vol = worst_vol
    if cortisol_marker and cortisol_marker.status in ("warning", "critical"):
        bike_vol = min(bike_vol, 0.70)

    def _cap_to_intensity(cap: Optional[str]) -> str:
        if cap == "zone1": return "zone1"
        if cap == "zone2": return "zone2"
        if cap == "zone3": return "zone3"
        return "any"

    return [
        DisciplineRestriction(
            discipline="swim",
            allowed=True,
            max_intensity=_cap_to_intensity(worst_cap),
            volume_modifier=min(1.0, worst_vol + 0.10),  # natación tolera mejor la fatiga hematológica
            notes=_notes("swim"),
        ),
        DisciplineRestriction(
            discipline="bike",
            allowed=True,
            max_intensity=_cap_to_intensity(worst_cap),
            volume_modifier=bike_vol,
            notes=_notes("bike"),
        ),
        DisciplineRestriction(
            discipline="run",
            allowed=run_cap != "zone1" or run_vol > 0.25,
            max_intensity=_cap_to_intensity(run_cap),
            volume_modifier=run_vol,
            notes=_notes("run"),
        ),
        DisciplineRestriction(
            discipline="strength",
            allowed=str_allowed,
            max_intensity="zone2" if markers_warning else "any",
            volume_modifier=str_vol,
            notes=_notes("strength"),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# TRS computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_trs(markers: list[MarkerImpact]) -> tuple[int, str, str]:
    """Calcula Training Restriction Score y su etiqueta."""
    total_restriction = sum(m.restriction_score for m in markers)
    total_restriction = min(total_restriction, 100)
    trs = max(0, 100 - int(total_restriction))

    if trs >= 85:
        return trs, "verde", "#10b981"
    if trs >= 65:
        return trs, "amarillo", "#f59e0b"
    if trs >= 40:
        return trs, "naranja", "#f97316"
    return trs, "rojo", "#ef4444"


# ─────────────────────────────────────────────────────────────────────────────
# Supplement plan builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_supplements(markers: list[MarkerImpact]) -> list[dict]:
    seen = set()
    supplements = []
    for m in markers:
        if m.supplement_hint and m.supplement_hint not in seen:
            seen.add(m.supplement_hint)
            supplements.append({
                "marker": m.name,
                "severity": m.status,
                "recommendation": m.supplement_hint,
                "priority": "urgente" if m.status == "critical" else "recomendado",
            })
    return supplements


# ─────────────────────────────────────────────────────────────────────────────
# Key actions generator
# ─────────────────────────────────────────────────────────────────────────────

def _build_key_actions(markers: list[MarkerImpact], trs: int, ctl: Optional[float]) -> list[str]:
    actions = []
    critical_markers = [m for m in markers if m.status == "critical"]
    warning_markers  = [m for m in markers if m.status == "warning"]

    if critical_markers:
        actions.append(f"URGENTE: consultar médico por {', '.join(m.name for m in critical_markers[:2])}")

    if any(m.key in ("ferritin", "hemoglobin", "hb") for m in warning_markers + critical_markers):
        actions.append("Iniciar suplementación de hierro; repetir labs en 3-4 semanas")

    if ctl and trs < 65:
        target_ctl = round(ctl * 0.70)
        actions.append(f"Reducir CTL objetivo a ~{target_ctl} (desde {round(ctl)}) hasta normalizar biomarcadores")

    if trs < 40:
        actions.append("Semana de recuperación activa: máx. 60% del volumen habitual, solo Z1-Z2")

    if any(m.key == "cortisol" for m in warning_markers + critical_markers):
        actions.append("Priorizar sueño 8-9h, reducir estresores externos, mindfulness 10min/día")

    if not actions:
        actions.append("Labs en rango óptimo — continuar planificación normal")
        if ctl:
            actions.append(f"CTL actual {round(ctl)} — puedes progresar +5-8% CTL en las próximas 4 semanas")

    # Recomendar siguiente análisis
    next_labs = min(m.recovery_days_needed for m in markers) if markers else 90
    if next_labs < 90:
        actions.append(f"Repetir análisis de sangre en ~{next_labs} días para confirmar respuesta")

    return actions[:6]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_training_impact(
    values: dict,
    sex: str = "M",
    ctl: Optional[float] = None,
    exam_date: str = "",
) -> TrainingImpactReport:
    """
    Compute punto central: evalúa todos los marcadores del examen y genera
    el Training Impact Report.

    Args:
        values: Dict de marcadores {key: value} del examen
        sex: "M" o "F"
        ctl: CTL actual del atleta (para ajuste de volumen)
        exam_date: Fecha del examen YYYY-MM-DD

    Returns:
        TrainingImpactReport completo
    """
    markers_evaluated: list[MarkerImpact] = []
    warnings: list[str] = []

    for key, val in values.items():
        if not isinstance(val, (int, float)):
            continue
        fn = _MARKER_EVAL_FNS.get(key)
        if fn:
            try:
                impact = fn(float(val), sex)
                markers_evaluated.append(impact)
            except Exception as e:
                warnings.append(f"No se pudo evaluar {key}: {e}")

    if not markers_evaluated:
        return TrainingImpactReport(
            trs=100, trs_label="verde", trs_color="#10b981",
            primary_limiters=[], disciplines=[], ctl_volume_modifier=1.0,
            supplements=[], medical_referral=False, medical_reason=None,
            next_labs_in_days=90, key_actions=["Sin marcadores reconocidos en el examen"],
            markers_evaluated=[], exam_date=exam_date, warnings=warnings,
        )

    trs, trs_label, trs_color = _compute_trs(markers_evaluated)

    critical = [m for m in markers_evaluated if m.status == "critical"]
    warning  = [m for m in markers_evaluated if m.status == "warning"]
    primary_limiters = [m.name for m in sorted(
        critical + warning, key=lambda m: m.restriction_score, reverse=True
    )[:3]]

    disciplines = _compute_disciplines(markers_evaluated)

    worst_vol = min((m.volume_modifier for m in markers_evaluated), default=1.0)
    ctl_volume_modifier = round(worst_vol, 2)

    supplements = _build_supplements(markers_evaluated)

    # Derivar necesidad de derivación médica
    medical_referral = bool(critical) or any(
        m.key in ("tsh", "testosterone") and m.status == "warning"
        for m in markers_evaluated
    )
    medical_reason = (
        f"Biomarcadores críticos: {', '.join(m.name for m in critical)}"
        if critical else None
    )

    next_labs = min((m.recovery_days_needed for m in markers_evaluated if m.status != "ok"), default=90)

    key_actions = _build_key_actions(markers_evaluated, trs, ctl)

    return TrainingImpactReport(
        trs=trs,
        trs_label=trs_label,
        trs_color=trs_color,
        primary_limiters=primary_limiters,
        disciplines=disciplines,
        ctl_volume_modifier=ctl_volume_modifier,
        supplements=supplements,
        medical_referral=medical_referral,
        medical_reason=medical_reason,
        next_labs_in_days=next_labs,
        key_actions=key_actions,
        markers_evaluated=markers_evaluated,
        exam_date=exam_date,
        warnings=warnings,
    )


def compute_team_labs_status(athletes_data: list[dict]) -> dict:
    """
    Vista de equipo para coaches: estado de labs de todos los atletas.

    Args:
        athletes_data: list of {
            user_id, name, sex, values_json_str, exam_date, ctl
        }

    Returns:
        {critical_athletes, warning_athletes, ok_athletes, team_avg_trs, alerts}
    """
    results = []
    for a in athletes_data:
        try:
            import json
            values = json.loads(a.get("values_json", "{}"))
        except Exception:
            values = {}

        report = compute_training_impact(
            values=values,
            sex=a.get("sex", "M"),
            ctl=a.get("ctl"),
            exam_date=a.get("exam_date", ""),
        )
        results.append({
            "user_id":   a["user_id"],
            "name":      a.get("name", "Atleta"),
            "trs":       report.trs,
            "trs_label": report.trs_label,
            "trs_color": report.trs_color,
            "limiters":  report.primary_limiters,
            "medical_referral": report.medical_referral,
            "exam_date": report.exam_date,
            "supplement_count": len(report.supplements),
            "critical_markers": [
                m.name for m in report.markers_evaluated if m.status == "critical"
            ],
        })

    critical = sorted([r for r in results if r["trs"] < 40], key=lambda r: r["trs"])
    warning  = sorted([r for r in results if 40 <= r["trs"] < 70], key=lambda r: r["trs"])
    ok       = sorted([r for r in results if r["trs"] >= 70], key=lambda r: -r["trs"])

    avg_trs = round(sum(r["trs"] for r in results) / len(results)) if results else 100

    alerts = []
    for r in critical:
        alerts.append({
            "severity": "critical",
            "athlete":  r["name"],
            "user_id":  r["user_id"],
            "message":  f"TRS {r['trs']}/100 — {', '.join(r['limiters'][:2]) or 'marcadores críticos'}",
        })
    for r in warning:
        if r.get("medical_referral"):
            alerts.append({
                "severity": "warning",
                "athlete":  r["name"],
                "user_id":  r["user_id"],
                "message":  f"Derivación médica recomendada — TRS {r['trs']}/100",
            })

    return {
        "critical_athletes": critical,
        "warning_athletes":  warning,
        "ok_athletes":       ok,
        "team_avg_trs":      avg_trs,
        "athletes_count":    len(results),
        "alerts":            alerts,
    }
