"""
LabX AI Intelligence Engine v2
================================
Motor de inteligencia determinista que NO requiere LLM externo.
Todos los resultados son calculables offline y auditables.
El LLM (Anthropic) es una capa opcional de mejora de texto.

Capacidades:
  1. Workout Generator      — Genera estructura de entrenamiento basada en CTL/TSB/sport
  2. Weekly Report          — Informe semanal estructurado de carga y forma
  3. CTL Forecast           — Proyección de forma 8 semanas (modelo exponential smoothing)
  4. Injury Risk Forecast   — Ventana de riesgo con recomendaciones de acción
  5. Coach Team Insights    — Análisis del equipo: clusters, alertas, prioridades
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# DATOS Y CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

_SPORT_ZONES = {
    "run":  {"Z1": "< 70% FC", "Z2": "70-80% FC", "Z3": "80-87% FC", "Z4": "87-93% FC", "Z5": "> 93% FC"},
    "bike": {"Z1": "< 55% FTP", "Z2": "55-75% FTP", "Z3": "75-87% FTP", "Z4": "87-95% FTP", "Z5": "> 95% FTP"},
    "swim": {"Z1": "Rec",       "Z2": "Base",       "Z3": "Umbral",    "Z4": "Lactato",    "Z5": "VO2max"},
    "gym":  {"Z1": "Movilidad", "Z2": "Fuerza base","Z3": "Hipertrofia","Z4": "Potencia",   "Z5": "Fuerza máx"},
}

_SPORT_TSS_PER_HOUR = {
    "run": 65, "bike": 60, "swim": 55, "gym": 40, "brick": 75,
}

# Zone distribution by focus and form
_ZONE_DIST: dict[str, dict[str, dict[str, float]]] = {
    "endurance": {
        "fresh":   {"Z1": 0.15, "Z2": 0.70, "Z3": 0.15, "Z4": 0.00, "Z5": 0.00},
        "normal":  {"Z1": 0.15, "Z2": 0.70, "Z3": 0.15, "Z4": 0.00, "Z5": 0.00},
        "fatigued":{"Z1": 0.30, "Z2": 0.60, "Z3": 0.10, "Z4": 0.00, "Z5": 0.00},
    },
    "threshold": {
        "fresh":   {"Z1": 0.15, "Z2": 0.30, "Z3": 0.10, "Z4": 0.45, "Z5": 0.00},
        "normal":  {"Z1": 0.20, "Z2": 0.35, "Z3": 0.10, "Z4": 0.35, "Z5": 0.00},
        "fatigued":{"Z1": 0.30, "Z2": 0.50, "Z3": 0.10, "Z4": 0.10, "Z5": 0.00},
    },
    "vo2":  {
        "fresh":   {"Z1": 0.20, "Z2": 0.20, "Z3": 0.10, "Z4": 0.10, "Z5": 0.40},
        "normal":  {"Z1": 0.25, "Z2": 0.25, "Z3": 0.10, "Z4": 0.10, "Z5": 0.30},
        "fatigued":{"Z1": 0.40, "Z2": 0.40, "Z3": 0.10, "Z4": 0.10, "Z5": 0.00},
    },
    "recovery": {
        "fresh":   {"Z1": 0.80, "Z2": 0.20, "Z3": 0.00, "Z4": 0.00, "Z5": 0.00},
        "normal":  {"Z1": 0.80, "Z2": 0.20, "Z3": 0.00, "Z4": 0.00, "Z5": 0.00},
        "fatigued":{"Z1": 1.00, "Z2": 0.00, "Z3": 0.00, "Z4": 0.00, "Z5": 0.00},
    },
    "strength": {
        "fresh":   {"Z1": 0.20, "Z2": 0.30, "Z3": 0.20, "Z4": 0.30, "Z5": 0.00},
        "normal":  {"Z1": 0.25, "Z2": 0.35, "Z3": 0.20, "Z4": 0.20, "Z5": 0.00},
        "fatigued":{"Z1": 0.40, "Z2": 0.40, "Z3": 0.20, "Z4": 0.00, "Z5": 0.00},
    },
}

_FOCUS_NAMES_ES = {
    "endurance": "Resistencia", "threshold": "Umbral",
    "vo2": "VO₂max", "recovery": "Recuperación", "strength": "Fuerza",
}

_SPORT_NAMES_ES = {
    "run": "Carrera", "bike": "Ciclismo", "swim": "Natación",
    "gym": "Gimnasio", "brick": "Brick",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. WORKOUT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WorkoutPhase:
    name: str
    duration_min: int
    zone: str
    zone_range: str
    description: str
    rpe: int  # 1-10


@dataclass
class GeneratedWorkout:
    title: str
    sport: str
    focus: str
    total_duration_min: int
    estimated_tss: int
    form_state: str
    override_reason: Optional[str]
    phases: list[WorkoutPhase]
    key_points: list[str]
    warnings: list[str]


def _form_state(tsb: Optional[float], recovery_score: Optional[int]) -> str:
    tsb = tsb or 0.0
    rec = recovery_score or 70
    if tsb <= -25 or rec < 35:
        return "fatigued"
    if tsb >= 5 and rec >= 70:
        return "fresh"
    return "normal"


def generate_workout(
    sport: str,
    focus: str,
    duration_min: int,
    ctl: Optional[float] = None,
    tsb: Optional[float] = None,
    recovery_score: Optional[int] = None,
    days_to_race: Optional[int] = None,
) -> GeneratedWorkout:
    sport     = sport.lower() if sport else "run"
    focus     = focus.lower() if focus else "endurance"
    sport     = sport if sport in _SPORT_TSS_PER_HOUR else "run"
    focus     = focus if focus in _ZONE_DIST else "endurance"
    duration  = max(20, min(360, duration_min))
    ctl_val   = ctl or 50.0
    form      = _form_state(tsb, recovery_score)
    tsb_v     = tsb or 0.0
    rec_v     = recovery_score or 70

    override  = None

    # CTO decision: fatigue overrides requested focus
    if tsb_v <= -30 or rec_v < 30:
        focus   = "recovery"
        override = f"Foco cambiado a Recuperación: TSB={tsb_v:.0f}, Recovery={rec_v}"
    elif days_to_race is not None and days_to_race <= 3:
        focus   = "recovery"
        override = f"Tapering: {days_to_race}d para carrera → protocolo de recuperación activo"
    elif days_to_race is not None and days_to_race <= 7 and focus == "vo2":
        focus   = "threshold"
        override = f"Pre-carrera ({days_to_race}d): VO₂max → Umbral para preservar forma"

    dist = _ZONE_DIST[focus][form]
    zones = _SPORT_ZONES.get(sport, _SPORT_ZONES["run"])

    # Warmup always 10-15 min
    warmup_min = min(15, max(10, duration // 8))
    cooldown_min = min(10, max(8, duration // 10))
    main_min = duration - warmup_min - cooldown_min

    phases: list[WorkoutPhase] = [
        WorkoutPhase(
            name="Calentamiento",
            duration_min=warmup_min,
            zone="Z1",
            zone_range=zones["Z1"],
            description="Activación progresiva: 5 min muy suave, luego 3×20s acelerones.",
            rpe=3,
        )
    ]

    # Build main phases from zone distribution
    active_zones = {z: p for z, p in dist.items() if p > 0.0}
    if not active_zones:
        active_zones = {"Z2": 1.0}

    for zone, proportion in sorted(active_zones.items()):
        zone_min = max(5, round(main_min * proportion))
        desc_map = {
            "Z1": "Ritmo muy suave, conversación fácil.",
            "Z2": "Ritmo aeróbico base — el caballo de trabajo del resistencista.",
            "Z3": "Ritmo 'moderado duro' — solo hablar frases cortas.",
            "Z4": f"Intervalos de umbral. Ejemplo: 4×8 min con 2 min recuperación.",
            "Z5": f"Intervalos cortos máximos. Ejemplo: 6×3 min al límite con 3 min rec.",
        }
        phases.append(WorkoutPhase(
            name=f"Principal — {zone}",
            duration_min=zone_min,
            zone=zone,
            zone_range=zones[zone],
            description=desc_map.get(zone, "Mantén el ritmo de zona."),
            rpe={"Z1": 3, "Z2": 5, "Z3": 6, "Z4": 8, "Z5": 10}.get(zone, 5),
        ))

    phases.append(WorkoutPhase(
        name="Enfriamiento",
        duration_min=cooldown_min,
        zone="Z1",
        zone_range=zones["Z1"],
        description="Reducción progresiva. 5 min de estiramientos dinámicos al final.",
        rpe=2,
    ))

    # Estimated TSS
    avg_intensity = sum(
        {"Z1": 0.45, "Z2": 0.65, "Z3": 0.78, "Z4": 0.90, "Z5": 1.0}.get(z, 0.65) *
        p.duration_min
        for z, p in [(ph.zone, ph) for ph in phases]
    ) / duration
    tss_per_h = _SPORT_TSS_PER_HOUR.get(sport, 60)
    estimated_tss = round(tss_per_h * (duration / 60) * avg_intensity)

    # Key points
    key_points = [
        f"CTL actual: {ctl_val:.0f} → adapta las zonas a tu percepción real.",
        f"Foco: {_FOCUS_NAMES_ES[focus]} · TSS estimado: {estimated_tss}",
        "Hidratación: 500ml/h mínimo. Carbohidratos si duración > 75 min.",
    ]
    if focus == "threshold":
        key_points.append("Umbral: usa RPE — debes poder mantener el ritmo sin empeorar.")
    if focus == "vo2":
        key_points.append("VO₂max: los intervalos deben doler igual en la primera y la última rep.")

    warnings = []
    if form == "fatigued":
        warnings.append("Estás fatigado — no te sobre-exijas. Si el RPE sube, reduce.")
    if focus == "recovery" and override:
        warnings.append(override)
    if ctl_val < 30 and focus in ("threshold", "vo2"):
        warnings.append("CTL bajo — construye base aeróbica primero antes de trabajo intenso.")

    return GeneratedWorkout(
        title=f"{_SPORT_NAMES_ES.get(sport, sport.title())} — {_FOCUS_NAMES_ES[focus]}",
        sport=sport,
        focus=focus,
        total_duration_min=duration,
        estimated_tss=estimated_tss,
        form_state=form,
        override_reason=override,
        phases=phases,
        key_points=key_points,
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. CTL FORECAST (Exponential Smoothing — Banister Model)
# ─────────────────────────────────────────────────────────────────────────────

_CTL_TAU = 42  # days
_ATL_TAU = 7   # days

_CTL_DECAY  = 1 - math.exp(-1 / _CTL_TAU)
_ATL_DECAY  = 1 - math.exp(-1 / _ATL_TAU)


@dataclass
class ForecastWeek:
    week: int
    ctl: float
    atl: float
    tsb: float
    form_label: str
    planned_tss: int
    notes: list[str]


def _form_label(tsb: float) -> str:
    if tsb >= 15:  return "peak"
    if tsb >= 5:   return "fresh"
    if tsb >= -10: return "normal"
    if tsb >= -25: return "fatigued"
    return "overtrained"


def forecast_ctl(
    current_ctl: float,
    current_atl: float,
    weekly_tss_plan: list[int],
    weeks: int = 8,
) -> list[ForecastWeek]:
    """
    Simulate CTL/ATL/TSB evolution for `weeks` weeks.
    weekly_tss_plan: list of planned TSS per week (len ≤ weeks; cycles if shorter).
    """
    plan = list(weekly_tss_plan) if weekly_tss_plan else [400] * weeks
    ctl  = float(current_ctl or 50)
    atl  = float(current_atl or 50)
    result = []

    for w in range(1, weeks + 1):
        weekly_tss = plan[(w - 1) % len(plan)]
        daily_tss  = weekly_tss / 7

        # Banister model: 7 daily steps
        for _ in range(7):
            ctl = ctl + (daily_tss - ctl) * _CTL_DECAY
            atl = atl + (daily_tss - atl) * _ATL_DECAY

        tsb    = ctl - atl
        label  = _form_label(tsb)
        notes  = []

        if atl > ctl * 1.5:
            notes.append("ACWR crítico — reduce carga esta semana")
        if weekly_tss > ctl * 0.9 * 7:
            notes.append("Carga alta para el nivel actual de fitness")
        if w == weeks:
            notes.append(f"Fitness proyectado: CTL {ctl:.0f} (actual + {ctl - current_ctl:.0f})")

        result.append(ForecastWeek(
            week=w,
            ctl=round(ctl, 1),
            atl=round(atl, 1),
            tsb=round(tsb, 1),
            form_label=label,
            planned_tss=weekly_tss,
            notes=notes,
        ))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. INJURY RISK FORECAST
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InjuryRiskReport:
    current_risk_score: float    # 0.0 → 1.0
    risk_level: str              # low / caution / high / critical
    primary_driver: str          # main risk factor
    time_at_risk_days: int       # how many days at elevated risk if continuing
    recovery_days_needed: int    # to return to safe zone
    action_plan: list[str]
    warning_signs: list[str]


def assess_injury_risk(
    acwr: Optional[float],
    monotony: Optional[float],
    strain: Optional[float],
    hrv_trend: Optional[str],       # "improving" | "stable" | "declining"
    consecutive_hard_days: Optional[int] = None,
    days_to_race: Optional[int] = None,
) -> InjuryRiskReport:
    """
    Multi-factor injury risk assessment.
    Returns actionable risk report with recovery timeline.
    """
    acwr_v  = acwr or 1.0
    mono_v  = monotony or 1.5
    strain_v= strain or 0.0
    risk    = 0.0

    drivers = []

    # ACWR risk (exponential — sweet spot 0.8-1.3)
    if acwr_v > 1.5:
        r = min(0.40, (acwr_v - 1.5) * 0.80)
        risk += r
        drivers.append(("ACWR crítico", r))
    elif acwr_v > 1.3:
        r = (acwr_v - 1.3) * 0.30
        risk += r
        drivers.append(("ACWR elevado", r))
    elif acwr_v < 0.7:
        risk += 0.05
        drivers.append(("Desentrenamiento", 0.05))

    # Monotony risk (>2.0 = danger zone)
    if mono_v > 2.0:
        r = min(0.25, (mono_v - 2.0) * 0.30)
        risk += r
        drivers.append(("Monotonía alta", r))

    # Strain
    strain_baseline = 3500  # arbitrary TSS unit
    if strain_v > strain_baseline * 1.5:
        risk += 0.15
        drivers.append(("Strain acumulado", 0.15))

    # HRV trend
    if hrv_trend == "declining":
        risk += 0.15
        drivers.append(("HRV en descenso", 0.15))

    # Consecutive hard days
    if consecutive_hard_days and consecutive_hard_days >= 4:
        r = min(0.20, (consecutive_hard_days - 3) * 0.07)
        risk += r
        drivers.append(("Días duros consecutivos", r))

    risk = min(1.0, risk)

    # Risk level
    if risk >= 0.6:   level = "critical"
    elif risk >= 0.4: level = "high"
    elif risk >= 0.2: level = "caution"
    else:             level = "low"

    # Primary driver
    primary = max(drivers, key=lambda x: x[1])[0] if drivers else "Sin factores de riesgo"

    # Time at risk / recovery days
    time_at_risk = 0
    recovery_days = 0
    if level == "critical":
        time_at_risk  = 14
        recovery_days = 7
    elif level == "high":
        time_at_risk  = 7
        recovery_days = 4
    elif level == "caution":
        time_at_risk  = 5
        recovery_days = 2

    # Action plan
    plan = []
    if level == "critical":
        plan = [
            "Para toda sesión de alta intensidad esta semana.",
            "48h de recuperación activa (caminata, movilidad).",
            "Duerme 8h+ por noche.",
            "Visita a fisioterapeuta si hay molestias musculares.",
            "Reintegra intensidad solo con TSB > 0.",
        ]
    elif level == "high":
        plan = [
            "Elimina sesiones Z4/Z5 los próximos 4 días.",
            "Prioriza sueño y nutrición de recuperación.",
            "Mantén volumen al 60% del planificado.",
            "Monitorea HRV cada mañana.",
        ]
    elif level == "caution":
        plan = [
            "Reduce intensidad en la próxima sesión.",
            "Verifica que el sueño sea ≥ 7.5h.",
            "Agrega 1 día de recuperación activa esta semana.",
        ]
    else:
        plan = [
            "Mantienes un perfil de carga saludable.",
            "Continúa con el plan actual.",
        ]

    # Pre-race override
    if days_to_race is not None and days_to_race <= 14 and level in ("high", "critical"):
        plan.insert(0, f"⚠ {days_to_race}d para carrera: el riesgo es alto. Tapering obligatorio.")

    warnings = []
    if acwr_v > 1.5:
        warnings.append(f"ACWR = {acwr_v:.2f} — estudios muestran 2-6× más lesiones sobre 1.5")
    if mono_v > 2.0:
        warnings.append(f"Monotonía = {mono_v:.1f} — varía los estímulos de entrenamiento")
    if hrv_trend == "declining":
        warnings.append("HRV en descenso sostenido — señal temprana de sobreentrenamiento")

    return InjuryRiskReport(
        current_risk_score=round(risk, 3),
        risk_level=level,
        primary_driver=primary,
        time_at_risk_days=time_at_risk,
        recovery_days_needed=recovery_days,
        action_plan=plan,
        warning_signs=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. WEEKLY REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeeklyReport:
    week_label: str
    load_summary: str
    form_assessment: str
    key_achievements: list[str]
    concerns: list[str]
    next_week_recommendations: list[str]
    suggested_tss_range: tuple[int, int]
    suggested_focus: str
    score: int  # 0-100 week quality score


def generate_weekly_report(
    ctl: Optional[float],
    atl: Optional[float],
    tsb: Optional[float],
    week_tss: Optional[int],
    week_hours: Optional[float],
    injury_risk: Optional[float],
    days_to_race: Optional[int] = None,
    hrv_trend: Optional[str] = None,
) -> WeeklyReport:
    ctl_v   = ctl or 50.0
    atl_v   = atl or 50.0
    tsb_v   = tsb or 0.0
    tss_v   = week_tss or 0
    hours_v = week_hours or 0.0
    risk_v  = injury_risk or 0.0
    label   = _form_label(tsb_v)

    # Load quality
    expected_tss = ctl_v * 7 * 0.8
    load_ratio   = tss_v / expected_tss if expected_tss > 0 else 0.5

    if load_ratio >= 1.1:
        load_summary = f"Semana alta ({tss_v} TSS / {hours_v:.1f}h). Carga superior al nivel base."
    elif load_ratio >= 0.75:
        load_summary = f"Semana moderada ({tss_v} TSS / {hours_v:.1f}h). Dentro del rango planificado."
    else:
        load_summary = f"Semana ligera ({tss_v} TSS / {hours_v:.1f}h). Bajo el objetivo semanal."

    # Form assessment
    form_texts = {
        "peak":        "Forma excelente — TSB positivo alto. Momento ideal para competir o testear.",
        "fresh":       "Forma buena — bien descansado. Capacidad de asimilar carga de calidad.",
        "normal":      "Forma normal — equilibrio entre carga y recuperación.",
        "fatigued":    "Algo fatigado — TSB negativo. Asimila bien si el sueño y nutrición son adecuados.",
        "overtrained": "Fatiga acumulada alta — el cuerpo necesita un ciclo de recuperación esta semana.",
    }
    form_assessment = form_texts.get(label, "Forma dentro de rangos normales.")

    # Achievements
    achievements: list[str] = []
    if tss_v >= expected_tss:
        achievements.append(f"Cumpliste el objetivo de carga semanal ({tss_v} TSS).")
    if ctl_v > 60:
        achievements.append(f"CTL {ctl_v:.0f} — nivel de fitness sólido para competir.")
    if risk_v < 0.2:
        achievements.append("Perfil de carga seguro — sin señales de sobreentrenamiento.")
    if not achievements:
        achievements.append("Semana completada. Cada sesión construye tu base aeróbica.")

    # Concerns
    concerns: list[str] = []
    if risk_v >= 0.4:
        concerns.append("Riesgo de lesión elevado — necesitas reducir carga o intensidad.")
    if tsb_v <= -25:
        concerns.append("TSB muy negativo — considera una semana de recuperación.")
    if load_ratio < 0.5 and tss_v > 0:
        concerns.append("Carga baja — si fue intencional está bien; si no, revisa adherencia.")
    if hrv_trend == "declining":
        concerns.append("HRV en descenso — monitorea señales de fatiga sistémica.")
    if days_to_race and days_to_race <= 14:
        concerns.append(f"Faltan {days_to_race}d para la carrera — tapering es prioritario.")

    # Next week recommendations
    next_focus = "endurance"
    if label == "overtrained" or risk_v >= 0.5:
        recs = [
            "Semana de recuperación: reduce volumen al 50%.",
            "Solo sesiones Z1/Z2.",
            "Prioriza sueño, nutrición y movilidad.",
        ]
        next_focus = "recovery"
        tss_range = (max(100, int(ctl_v * 3)), int(ctl_v * 4))
    elif label in ("fatigued",) and risk_v >= 0.3:
        recs = [
            "Semana de carga controlada: 80% del volumen habitual.",
            "Limita sesiones Z4/Z5 a 1 como máximo.",
            "Agrega 1 sesión corta de recuperación activa.",
        ]
        next_focus = "endurance"
        tss_range = (int(ctl_v * 5), int(ctl_v * 6))
    elif label in ("fresh", "peak") and days_to_race and days_to_race <= 10:
        recs = [
            "Tapering final: mantén intensidad, reduce volumen 30%.",
            "1 sesión de activación corta con esfuerzos a ritmo de carrera.",
            "Descanso el día anterior — solo movilidad.",
        ]
        next_focus = "recovery"
        tss_range = (int(ctl_v * 4), int(ctl_v * 5))
    else:
        recs = [
            f"Mantén carga entre {int(ctl_v * 5.5)}-{int(ctl_v * 7)} TSS.",
            "Incluye 2 sesiones de calidad (umbral o VO₂max).",
            "Al menos 1 sesión de recuperación activa.",
        ]
        next_focus = "threshold" if ctl_v >= 60 else "endurance"
        tss_range  = (int(ctl_v * 5.5), int(ctl_v * 7.5))

    # Week score (0-100)
    score = 50
    score += min(20, load_ratio * 20)
    score += 10 if risk_v < 0.2 else (-10 if risk_v >= 0.4 else 0)
    score += 10 if hrv_trend == "improving" else (-5 if hrv_trend == "declining" else 0)
    score += 10 if label in ("fresh", "normal") else (-5 if label == "overtrained" else 0)
    score = max(0, min(100, int(score)))

    return WeeklyReport(
        week_label="Esta semana",
        load_summary=load_summary,
        form_assessment=form_assessment,
        key_achievements=achievements,
        concerns=concerns,
        next_week_recommendations=recs,
        suggested_tss_range=tss_range,
        suggested_focus=next_focus,
        score=score,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. COACH TEAM INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AthleteAlert:
    user_id: str
    name: str
    severity: str          # info / warning / critical
    message: str
    action: str


@dataclass
class TeamCluster:
    label: str             # "Pico de forma" / "En construcción" / "Recuperando" / "En riesgo"
    athlete_ids: list[str]
    recommendation: str


@dataclass
class CoachInsightsReport:
    total_athletes: int
    alerts: list[AthleteAlert]
    clusters: list[TeamCluster]
    team_avg_ctl: float
    team_avg_tsb: float
    summary: str


def generate_coach_insights(athletes: list[dict]) -> CoachInsightsReport:
    """
    athletes: list of dicts with keys:
      user_id, name, ctl, atl, tsb, recovery_score, injury_risk, days_to_race
    """
    if not athletes:
        return CoachInsightsReport(
            total_athletes=0, alerts=[], clusters=[],
            team_avg_ctl=0, team_avg_tsb=0, summary="Sin atletas en el equipo."
        )

    alerts: list[AthleteAlert] = []
    clusters_map: dict[str, list[str]] = {
        "Pico de forma": [], "En construcción": [],
        "Recuperando": [], "En riesgo": [],
    }

    ctls = []
    tsbs = []

    for a in athletes:
        uid   = a.get("user_id", "")
        name  = a.get("name", "Atleta")
        ctl   = a.get("ctl") or 0.0
        atl   = a.get("atl") or 0.0
        tsb   = a.get("tsb") or 0.0
        rec   = a.get("recovery_score") or 70
        risk  = a.get("injury_risk") or 0.0
        dtr   = a.get("days_to_race")
        ctls.append(ctl)
        tsbs.append(tsb)

        # Alerts
        if risk >= 0.5:
            alerts.append(AthleteAlert(uid, name, "critical",
                f"Riesgo de lesión crítico ({risk:.0%})",
                "Revisa carga y programa recuperación activa."))
        elif risk >= 0.35:
            alerts.append(AthleteAlert(uid, name, "warning",
                f"Riesgo elevado ({risk:.0%})",
                "Reduce intensidad próximos 3 días."))

        if tsb <= -30:
            alerts.append(AthleteAlert(uid, name, "critical",
                f"TSB muy negativo ({tsb:.0f}) — sobreentrenamiento",
                "Semana de recuperación inmediata."))

        if dtr and dtr <= 7 and tsb < -10:
            alerts.append(AthleteAlert(uid, name, "warning",
                f"{dtr}d para carrera pero TSB={tsb:.0f} — todavía fatigado",
                "Ajusta tapering — prioriza recuperación sobre volumen."))

        if rec < 30:
            alerts.append(AthleteAlert(uid, name, "warning",
                f"Recovery Score muy bajo ({rec})",
                "Verifica sueño, hidratación y estrés."))

        # Clustering
        form = _form_label(tsb)
        if form in ("peak", "fresh"):
            clusters_map["Pico de forma"].append(uid)
        elif risk >= 0.4 or form == "overtrained":
            clusters_map["En riesgo"].append(uid)
        elif form == "fatigued":
            clusters_map["Recuperando"].append(uid)
        else:
            clusters_map["En construcción"].append(uid)

    avg_ctl = sum(ctls) / len(ctls) if ctls else 0
    avg_tsb = sum(tsbs) / len(tsbs) if tsbs else 0

    clusters = [
        TeamCluster(
            label=lbl,
            athlete_ids=ids,
            recommendation={
                "Pico de forma":   "Programar tests o competencias en las próximas 2-3 semanas.",
                "En construcción": "Mantener carga progresiva. Revisar adherencia al plan.",
                "Recuperando":     "No agregar carga nueva. Confirmar sueño y nutrición.",
                "En riesgo":       "Contactar atletas individualmente. Considerar semana de descarga.",
            }[lbl]
        )
        for lbl, ids in clusters_map.items() if ids
    ]

    critical_count = len([a for a in alerts if a.severity == "critical"])
    warning_count  = len([a for a in alerts if a.severity == "warning"])
    summary = (
        f"Equipo: {len(athletes)} atletas · "
        f"CTL promedio: {avg_ctl:.0f} · "
        f"TSB promedio: {avg_tsb:.0f} · "
        f"{critical_count} alertas críticas · {warning_count} advertencias."
    )

    return CoachInsightsReport(
        total_athletes=len(athletes),
        alerts=sorted(alerts, key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x.severity]),
        clusters=clusters,
        team_avg_ctl=round(avg_ctl, 1),
        team_avg_tsb=round(avg_tsb, 1),
        summary=summary,
    )
