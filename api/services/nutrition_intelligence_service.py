"""
LabX — Nutrition Intelligence Service (Sprint 24)
==================================================
Motor determinista (sin LLM) para inteligencia nutricional avanzada.

Módulos:
  1. Compliance Engine — % de cumplimiento de macros diarios
  2. Lab-Nutrition Bridge — cruza marcadores de sangre con suplementación activa
  3. Pre-Race Carb Loading Protocol — carbohidrato en los 3 días previos a la competición
  4. Training-Synced Macro Targets — ajuste de CHO/proteína según carga del día

Diferenciador:
  Ningún competidor (TP, MacroFactor, Cronometer) cruza resultados de análisis
  de sangre con el diario de suplementación. LabX detecta si el atleta tiene
  ferritina baja en labs pero no registra hierro en suplementos → alerta proactiva.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("labx.nutrition_intelligence")


# ─────────────────────────────────────────────────────────────────────────────
# 1. COMPLIANCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MacroCompliance:
    kcal_target: float
    kcal_actual: float
    carbs_target_g: float
    carbs_actual_g: float
    protein_target_g: float
    protein_actual_g: float
    fat_target_g: float
    fat_actual_g: float
    fiber_target_g: float
    fiber_actual_g: float
    compliance_score: int         # 0-100
    compliance_label: str         # "Óptimo" | "Bueno" | "Insuficiente" | "Deficiente"
    compliance_color: str
    gaps: list[str]               # qué macro falla y cuánto falta
    excesses: list[str]           # qué macro está en exceso
    hydration_ok: Optional[bool]  # si hay datos de hidratación


def _pct_score(actual: float, target: float, tolerance: float = 0.10) -> float:
    """Score 0-1 para un macro dado. Penaliza defecto más que exceso."""
    if target <= 0:
        return 1.0
    ratio = actual / target
    if ratio < (1 - tolerance):
        # Defecto — penalización progresiva
        return max(0.0, ratio / (1 - tolerance))
    if ratio > (1 + tolerance * 2):
        # Exceso moderado — penalización suave
        excess = ratio - (1 + tolerance * 2)
        return max(0.6, 1.0 - excess * 0.2)
    return 1.0


def compute_macro_compliance(
    kcal_target: float,
    kcal_actual: float,
    carbs_target_g: float,
    carbs_actual_g: float,
    protein_target_g: float,
    protein_actual_g: float,
    fat_target_g: float,
    fat_actual_g: float,
    fiber_target_g: float = 30.0,
    fiber_actual_g: float = 0.0,
    hydration_ml: Optional[float] = None,
    hydration_target_ml: Optional[float] = 2500.0,
) -> MacroCompliance:
    """
    Calcula compliance score 0-100 para los macros del día.
    Pesos fisiológicos: CHO 40%, proteína 35%, kcal 15%, fibra 5%, grasa 5%
    """
    w_kcal    = 0.15
    w_carbs   = 0.40
    w_protein = 0.35
    w_fat     = 0.05
    w_fiber   = 0.05

    s_kcal    = _pct_score(kcal_actual,     kcal_target,    tolerance=0.12)
    s_carbs   = _pct_score(carbs_actual_g,  carbs_target_g, tolerance=0.10)
    s_protein = _pct_score(protein_actual_g, protein_target_g, tolerance=0.08)
    s_fat     = _pct_score(fat_actual_g,    fat_target_g,   tolerance=0.15)
    s_fiber   = _pct_score(fiber_actual_g,  fiber_target_g, tolerance=0.20)

    raw_score = (
        s_kcal    * w_kcal +
        s_carbs   * w_carbs +
        s_protein * w_protein +
        s_fat     * w_fat +
        s_fiber   * w_fiber
    ) * 100

    score = int(round(min(100.0, raw_score)))

    if score >= 85:
        label, color = "Óptimo",      "#10b981"
    elif score >= 70:
        label, color = "Bueno",       "#22d3ee"
    elif score >= 50:
        label, color = "Insuficiente","#f59e0b"
    else:
        label, color = "Deficiente",  "#ef4444"

    gaps = []
    excesses = []

    def _check(name: str, actual: float, target: float, unit: str = "g"):
        ratio = actual / target if target > 0 else 1.0
        if ratio < 0.90:
            missing = round(target - actual, 1)
            gaps.append(f"{name}: faltan {missing}{unit} ({int(ratio*100)}% del objetivo)")
        elif ratio > 1.25:
            excess = round(actual - target, 1)
            excesses.append(f"{name}: +{excess}{unit} sobre objetivo")

    _check("Energía",  kcal_actual,    kcal_target,    "kcal")
    _check("Carbohidratos", carbs_actual_g, carbs_target_g)
    _check("Proteína", protein_actual_g, protein_target_g)
    _check("Fibra",    fiber_actual_g,  fiber_target_g)

    hydration_ok = None
    if hydration_ml is not None and hydration_target_ml:
        hydration_ok = hydration_ml >= hydration_target_ml * 0.85

    return MacroCompliance(
        kcal_target=kcal_target, kcal_actual=kcal_actual,
        carbs_target_g=carbs_target_g, carbs_actual_g=carbs_actual_g,
        protein_target_g=protein_target_g, protein_actual_g=protein_actual_g,
        fat_target_g=fat_target_g, fat_actual_g=fat_actual_g,
        fiber_target_g=fiber_target_g, fiber_actual_g=fiber_actual_g,
        compliance_score=score, compliance_label=label, compliance_color=color,
        gaps=gaps, excesses=excesses, hydration_ok=hydration_ok,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. LAB-NUTRITION BRIDGE
# ─────────────────────────────────────────────────────────────────────────────

# Mapa: marcador de labs → suplemento(s) que lo corrige
_LAB_TO_SUPPLEMENT = {
    "ferritin":    ["hierro", "iron"],
    "hb":          ["hierro", "iron", "vitamina_b12", "folato"],
    "hemoglobin":  ["hierro", "iron", "vitamina_b12", "folato"],
    "vitamin_d":   ["vitamina_d", "vit_d", "vitamin_d"],
    "vitamin_b12": ["vitamina_b12", "b12", "cobalamina"],
    "testosterone":["zinc", "magnesio", "magnesium"],
    "tsh":         ["yodo", "selenio"],
    "cortisol":    ["magnesio", "magnesium", "ashwagandha"],
    "ck":          ["creatina", "creatine", "proteina"],
}

@dataclass
class LabNutritionGap:
    marker_key: str
    marker_name: str
    marker_status: str         # "warning" | "critical"
    recommended_supplements: list[str]
    is_being_supplemented: bool
    days_logged_supplement: int
    action: str


@dataclass
class LabNutritionBridgeReport:
    gaps: list[LabNutritionGap]     # marcadores que necesitan suplemento y no lo reciben
    covered: list[LabNutritionGap]  # marcadores con suplemento activo
    compliance_rate: float           # % de deficiencias cubiertas
    alert_count: int
    top_action: Optional[str]


def compute_lab_nutrition_bridge(
    markers_evaluated: list[dict],   # [{key, name, status, supplement_hint}, ...]
    supplement_logs_last_30d: list[dict],  # [{supplement, dose_mg, date_iso}, ...]
) -> LabNutritionBridgeReport:
    """
    Cruza marcadores de labs alterados con el registro de suplementación.
    Identifica brechas: marcador deficiente pero sin suplemento activo.

    Args:
        markers_evaluated: salida de blood_labs_impact_service.compute_training_impact
        supplement_logs_last_30d: suplementos logueados en los últimos 30 días

    Returns:
        LabNutritionBridgeReport
    """
    # Normalizar nombres de suplementos en logs
    logged_supps = set()
    supp_count: dict[str, int] = {}
    for log in supplement_logs_last_30d:
        s = (log.get("supplement") or "").lower().replace("-", "_").replace(" ", "_")
        logged_supps.add(s)
        supp_count[s] = supp_count.get(s, 0) + 1

    gaps = []
    covered = []

    problematic = [m for m in markers_evaluated if m.get("status") in ("warning", "critical")]

    for m in problematic:
        key = m.get("key", "")
        expected_supps = _LAB_TO_SUPPLEMENT.get(key, [])
        if not expected_supps:
            continue

        # Check if any relevant supplement is being logged
        is_covered = any(
            any(exp in logged for logged in logged_supps)
            for exp in expected_supps
        )

        days_logged = max(
            supp_count.get(s, 0) for exp in expected_supps
            for s in logged_supps if exp in s
        ) if is_covered else 0

        gap = LabNutritionGap(
            marker_key=key,
            marker_name=m.get("name", key),
            marker_status=m.get("status", "warning"),
            recommended_supplements=expected_supps,
            is_being_supplemented=is_covered,
            days_logged_supplement=days_logged,
            action=(
                f"Continúa con {expected_supps[0]} — llevas {days_logged} días registrados"
                if is_covered else
                f"Iniciar {expected_supps[0]} para corregir {m.get('name', key)} bajo"
            ),
        )
        if is_covered:
            covered.append(gap)
        else:
            gaps.append(gap)

    total = len(gaps) + len(covered)
    compliance_rate = len(covered) / total if total > 0 else 1.0

    alert_count = len([g for g in gaps if g.marker_status == "critical"])

    top_action = None
    critical_gaps = [g for g in gaps if g.marker_status == "critical"]
    if critical_gaps:
        top_action = critical_gaps[0].action
    elif gaps:
        top_action = gaps[0].action

    return LabNutritionBridgeReport(
        gaps=gaps,
        covered=covered,
        compliance_rate=round(compliance_rate, 2),
        alert_count=alert_count,
        top_action=top_action,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRE-RACE CARB LOADING PROTOCOL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CarbLoadingDay:
    day_offset: int        # -3, -2, -1, 0 (race day)
    label: str
    kcal_target: int
    carbs_g: int
    carbs_g_per_kg: float
    protein_g: int
    fat_g: int
    hydration_ml: int
    sodium_mg: int
    notes: str


@dataclass
class CarbLoadingProtocol:
    race_name: str
    race_dist: str
    weight_kg: float
    days: list[CarbLoadingDay]
    key_rules: list[str]


# g/kg CHO por día según días a la carrera y distancia
_CHO_TARGETS = {
    # (days_to_race, race_dist): g/kg/day
    (-3, "sprint"):   5.5,  (-3, "olympic"): 7.0,  (-3, "half"):  8.0,  (-3, "full"):  10.0,
    (-2, "sprint"):   5.5,  (-2, "olympic"): 7.5,  (-2, "half"):  9.0,  (-2, "full"):  11.0,
    (-1, "sprint"):   5.0,  (-1, "olympic"): 6.5,  (-1, "half"):  8.0,  (-1, "full"):   9.0,
    (0,  "sprint"):   2.0,  (0,  "olympic"): 2.5,  (0,  "half"):  2.5,  (0,  "full"):   3.0,
}

def _race_category(race_dist: str) -> str:
    dist = race_dist.lower()
    if "sprint"  in dist: return "sprint"
    if "olympic" in dist or "olímpico" in dist: return "olympic"
    if "half"    in dist or "70.3"    in dist or "media" in dist: return "half"
    if "full"    in dist or "ironman" in dist or "140.6" in dist: return "full"
    return "olympic"  # default

def compute_carb_loading_protocol(
    race_name: str,
    race_dist: str,
    weight_kg: float,
    ctl: Optional[float] = None,
) -> CarbLoadingProtocol:
    """
    Protocolo de carga de carbohidratos para los 3 días previos a la carrera.

    Science base:
    - Ironman: 10-12 g/kg/día en D-3 y D-2 (Sherman et al., 1981; Burke et al., 2011)
    - Olympic: 7-8 g/kg/día
    - Sprint: 5-6 g/kg/día
    - Día de carrera: 2-3 g/kg en las 4h previas al inicio
    """
    cat = _race_category(race_dist)
    days_list = []

    day_labels = {-3: "3 días antes", -2: "2 días antes", -1: "Víspera", 0: "Día de carrera"}

    for offset in [-3, -2, -1, 0]:
        cho_per_kg = _CHO_TARGETS.get((offset, cat), 6.0)

        # CTL boost: atletas con CTL alto necesitan algo más de CHO
        if ctl and ctl > 80 and offset < 0:
            cho_per_kg = min(cho_per_kg * 1.05, cho_per_kg + 0.5)

        carbs_g = round(cho_per_kg * weight_kg)

        if offset == 0:
            # Día de carrera: proteína mínima, grasas mínimas
            protein_g = round(1.2 * weight_kg)
            fat_g     = round(0.8 * weight_kg)
            kcal      = carbs_g * 4 + protein_g * 4 + fat_g * 9
            hydration = 2000
            sodium    = 1500
            notes     = "Solo si hay tiempo antes del start. Evitar fibra. Alimentos familiares."
        elif offset == -1:
            protein_g = round(1.6 * weight_kg)
            fat_g     = round(1.0 * weight_kg)
            kcal      = carbs_g * 4 + protein_g * 4 + fat_g * 9
            hydration = round(35 * weight_kg)
            sodium    = 2000
            notes     = "Cenar temprano (antes de 20h). Nada nuevo. Alta densidad calórica."
        else:
            protein_g = round(1.8 * weight_kg)
            fat_g     = round(1.2 * weight_kg)
            kcal      = carbs_g * 4 + protein_g * 4 + fat_g * 9
            hydration = round(40 * weight_kg)
            sodium    = 2500
            notes     = "Aumentar CHO, reducir fibra. Entrenamiento suave o descanso."

        days_list.append(CarbLoadingDay(
            day_offset=offset,
            label=day_labels[offset],
            kcal_target=kcal,
            carbs_g=carbs_g,
            carbs_g_per_kg=round(cho_per_kg, 1),
            protein_g=protein_g,
            fat_g=fat_g,
            hydration_ml=hydration,
            sodium_mg=sodium,
            notes=notes,
        ))

    key_rules = [
        "Priorizar alimentos conocidos — no probar nada nuevo en los 3 días previos",
        "Aumentar sodio (pasta, arroz con sal, electrolitos) especialmente en D-2 y D-1",
        f"Objetivo de hidratación: orina de color amarillo claro (urocromía ≤3)",
    ]
    if cat in ("half", "full"):
        key_rules.append("Reducir fibra: evitar legumbres, vegetales crudos y salvado en D-1")
    if cat == "full":
        key_rules.append("Ironman: considerar 1-2 dosis de cafeína (3-6mg/kg) 45min antes del start")

    return CarbLoadingProtocol(
        race_name=race_name,
        race_dist=race_dist,
        weight_kg=weight_kg,
        days=days_list,
        key_rules=key_rules,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. TRAINING-SYNCED MACRO TARGETS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DailyMacroTargets:
    kcal: int
    carbs_g: int
    protein_g: int
    fat_g: int
    fiber_g: int
    hydration_ml: int
    sodium_mg: int
    day_type: str           # "rest" | "easy" | "moderate" | "intense" | "pre-race" | "race"
    rationale: str


def compute_daily_macro_targets(
    weight_kg: float,
    tss_today: Optional[float] = None,
    days_to_race: Optional[int] = None,
    race_dist: Optional[str] = None,
    ctl: Optional[float] = None,
    sex: str = "M",
) -> DailyMacroTargets:
    """
    Calcula targets de macros para el día según carga de entrenamiento,
    días a la carrera, y perfil del atleta.

    Base fisiológica (Burke et al., 2011; Thomas et al., 2016):
    - Proteína: 1.6-2.2 g/kg (atletas de resistencia en carga)
    - CHO: 3-12 g/kg (varía con TSS y distancia de carrera)
    - Grasas: 0.8-1.5 g/kg
    - Fibra: 25-38g (hombre) / 21-25g (mujer)
    """
    tss = tss_today or 0.0

    # Clasificar el día por TSS
    if days_to_race is not None and days_to_race == 0:
        day_type = "race"
    elif days_to_race is not None and days_to_race <= 3:
        day_type = "pre-race"
    elif tss >= 130:
        day_type = "intense"
    elif tss >= 70:
        day_type = "moderate"
    elif tss >= 30:
        day_type = "easy"
    else:
        day_type = "rest"

    # CHO targets (g/kg)
    cho_per_kg = {
        "rest":     3.5,
        "easy":     5.0,
        "moderate": 6.5,
        "intense":  8.0,
        "pre-race": 9.0 if race_dist and _race_category(race_dist) in ("half", "full") else 7.0,
        "race":     2.5,
    }[day_type]

    # Proteína (g/kg)
    protein_per_kg = {
        "rest":     1.6,
        "easy":     1.8,
        "moderate": 2.0,
        "intense":  2.2,
        "pre-race": 1.8,
        "race":     1.2,
    }[day_type]

    # Grasa (g/kg)
    fat_per_kg = {
        "rest":     1.2,
        "easy":     1.0,
        "moderate": 0.9,
        "intense":  0.8,
        "pre-race": 0.9,
        "race":     0.6,
    }[day_type]

    carbs_g   = round(cho_per_kg * weight_kg)
    protein_g = round(protein_per_kg * weight_kg)
    fat_g     = round(fat_per_kg * weight_kg)
    kcal      = carbs_g * 4 + protein_g * 4 + fat_g * 9

    # Fibra
    fiber_g = 30 if sex == "M" else 25
    if day_type in ("pre-race", "race"):
        fiber_g = 15  # reducir fibra antes de carrera

    # Hidratación: base 35ml/kg + 500-1000ml por entrenamientos
    hydration_base = round(35 * weight_kg)
    hydration_extra = {
        "rest": 0, "easy": 500, "moderate": 750, "intense": 1000, "pre-race": 1000, "race": 0,
    }[day_type]
    hydration_ml = hydration_base + hydration_extra

    # Sodio
    sodium_mg = {
        "rest": 1500, "easy": 1800, "moderate": 2000, "intense": 2500, "pre-race": 2500, "race": 3000,
    }[day_type]

    rationale = {
        "rest":     f"Día de descanso — CHO reducido ({cho_per_kg}g/kg), proteína moderada para reparación",
        "easy":     f"Sesión suave — CHO de mantenimiento ({cho_per_kg}g/kg), proteína normal",
        "moderate": f"Sesión moderada — CHO aumentado ({cho_per_kg}g/kg) para mantener glucógeno",
        "intense":  f"Sesión intensa — CHO alto ({cho_per_kg}g/kg) para máxima reposición glucogénica",
        "pre-race": f"Carga pre-carrera — CHO muy alto ({cho_per_kg}g/kg), reducir fibra",
        "race":     f"Día de carrera — CHO accesible {carbs_g}g (pre-start), sodio elevado",
    }[day_type]

    return DailyMacroTargets(
        kcal=kcal, carbs_g=carbs_g, protein_g=protein_g,
        fat_g=fat_g, fiber_g=fiber_g, hydration_ml=hydration_ml,
        sodium_mg=sodium_mg, day_type=day_type, rationale=rationale,
    )
