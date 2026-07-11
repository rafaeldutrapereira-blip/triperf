"""
Mental Performance Routes — Sprint 18
======================================
Mental Fatigue Score, check-in diario, biblioteca de protocolos,
correlaciones HRV × mental × rendimiento, protocolo pre-carrera.

Diferenciador único vs toda la competencia: integración datos fisiológicos
(HRV, Recovery Score, TSB) con estado psicológico en tiempo real.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import (
    User, MentalCheckin, MentalFatigueScore, MentalProtocolSession,
    RecoveryScore, WellnessLog, GarminActivity, GarminTrainingLoad, RaceEvent,
)

router = APIRouter(prefix="/mental", tags=["mental"])


# ─────────────────────────────────────────────────────────────────────────────
# PROTOCOL LIBRARY — 30 técnicas codificadas
# ─────────────────────────────────────────────────────────────────────────────

PROTOCOL_LIBRARY = [
    # RESPIRACIÓN
    {"id": "breath_478",        "category": "breathing",      "name": "Respiración 4-7-8",          "duration_min": 5,  "difficulty": "beginner", "goal": "anxiety",     "description": "Inhala 4s, retén 7s, exhala 8s. Activa el sistema parasimpático en minutos.", "steps": ["Siéntate derecho.", "Inhala por la nariz 4 segundos.", "Retén el aire 7 segundos.", "Exhala lentamente por la boca 8 segundos.", "Repite 4 veces."]},
    {"id": "breath_box",        "category": "breathing",      "name": "Respiración en Caja",         "duration_min": 4,  "difficulty": "beginner", "goal": "focus",       "description": "Técnica usada por Navy SEALs. 4-4-4-4. Calma el sistema nervioso antes de esfuerzo intenso.", "steps": ["Exhala completamente.", "Inhala 4s.", "Retén 4s.", "Exhala 4s.", "Retén 4s.", "Repite 5 ciclos."]},
    {"id": "breath_physiological","category": "breathing",    "name": "Suspiro Fisiológico",          "duration_min": 2,  "difficulty": "beginner", "goal": "stress",      "description": "La técnica más rápida para bajar estrés. Doble inhalación nasal + exhalación larga.", "steps": ["Inhala profundo por la nariz.", "Sin exhalar, inhala un poco más (doble inhalación).", "Exhala lentamente por la boca durante 8-10s.", "Repite 3 veces."]},
    {"id": "breath_resonance",  "category": "breathing",      "name": "Respiración de Resonancia",   "duration_min": 10, "difficulty": "intermediate", "goal": "hrv",    "description": "5.5 respiraciones/minuto. Maximiza HRV y coherencia cardíaca.", "steps": ["Inhala 5.5 segundos.", "Exhala 5.5 segundos.", "Mantén ritmo constante 10 minutos.", "Ideal antes de entrenamientos de calidad."]},
    {"id": "breath_wim_hof",    "category": "breathing",      "name": "Método Wim Hof Básico",       "duration_min": 15, "difficulty": "advanced",     "goal": "energy",  "description": "Hiperventilación controlada + retención. Aumenta oxigenación y alcalinidad. NO usar en agua.", "steps": ["30 respiraciones profundas y rápidas.", "Exhala y retén sin aire.", "Cuando necesites, inhala y retén 15s.", "Exhala. 3 rondas."]},

    # VISUALIZACIÓN
    {"id": "viz_race_day",      "category": "visualization",  "name": "Visualización Día de Carrera","duration_min": 12, "difficulty": "intermediate", "goal": "confidence","description": "Recorre mentalmente toda tu carrera. Activa los mismos circuitos neuronales que el rendimiento real.", "steps": ["Cierra los ojos. Respira profundo.", "Visualiza despertarte el día de carrera. Calmo.", "Recorre la transición T1 con detalle.", "Visualiza el swim fuerte y controlado.", "El bike en tu power target.", "El run: fuerte al final.", "Cruzando la meta. Emoción."]},
    {"id": "viz_interval",      "category": "visualization",  "name": "Visualización Pre-Intervalos","duration_min": 5,  "difficulty": "beginner",     "goal": "focus",   "description": "Programa tu cerebro para la sesión de calidad antes de comenzar.", "steps": ["Cierra los ojos 5 minutos antes.", "Visualiza cada intervalo con perfección técnica.", "Siente el esfuerzo pero también el control.", "Abre los ojos. Listo."]},
    {"id": "viz_body_scan",     "category": "visualization",  "name": "Body Scan Deportivo",          "duration_min": 8,  "difficulty": "beginner",     "goal": "recovery","description": "Recorre mentalmente cada parte del cuerpo enviando relajación. Ideal post-entrenamiento.", "steps": ["Acuéstate.", "Enfoca en los pies. Relaja.", "Sube a las piernas.", "Pelvis, abdomen.", "Pecho, brazos.", "Cuello, cara."]},
    {"id": "viz_confidence",    "category": "visualization",  "name": "Anclaje de Confianza",         "duration_min": 6,  "difficulty": "intermediate", "goal": "confidence","description": "Revive tu mejor entrenamiento para activar el estado de confianza.", "steps": ["Cierra los ojos.", "Recuerda tu mejor entrenamiento.", "Siente las sensaciones físicas y emocionales.", "Asocia ese estado con un gesto físico (puño cerrado).", "Usa el gesto en momentos de duda."]},

    # MINDFULNESS
    {"id": "mind_5min",         "category": "mindfulness",    "name": "Mindfulness 5 Minutos",        "duration_min": 5,  "difficulty": "beginner",     "goal": "focus",   "description": "Presencia plena. Reduce ruido mental antes del entrenamiento.", "steps": ["Siéntate cómodamente.", "Enfoca en tu respiración natural.", "Cuando la mente se vaya, vuelve sin juicio.", "5 minutos de presencia pura."]},
    {"id": "mind_pre_race",     "category": "mindfulness",    "name": "Mindfulness Pre-Carrera",      "duration_min": 10, "difficulty": "intermediate", "goal": "anxiety", "description": "Acepta el nerviosismo sin luchar contra él. El estrés pre-carrera es energía.", "steps": ["Siéntate en transición 10 min antes.", "Observa los nervios sin juzgarlos.", "Respira profundo. Los nervios son energía.", "Enfócate en el proceso, no en el resultado.", "Repite: 'Estoy preparado.'"]},
    {"id": "mind_open_focus",   "category": "mindfulness",    "name": "Foco Abierto",                 "duration_min": 8,  "difficulty": "intermediate", "goal": "focus",   "description": "Expande tu conciencia para incluir todo el entorno. Reduce hiperenfoque en el dolor.", "steps": ["Foco en un punto 1 min.", "Expande lentamente a visión periférica.", "Incluye sonidos.", "Incluye sensaciones corporales.", "Todo a la vez, nada en particular."]},

    # COGNITIVO
    {"id": "cog_self_talk",     "category": "cognitive",      "name": "Auto-Diálogo Positivo",        "duration_min": 3,  "difficulty": "beginner",     "goal": "motivation","description": "Reprograma el diálogo interno. Los atletas de élite usan esto consistentemente.", "steps": ["Identifica tu frase negativa recurrente.", "Crea la versión positiva opuesta.", "Repítela 10 veces en voz alta.", "Úsala durante el entrenamiento cuando la duda aparece."]},
    {"id": "cog_process_goals", "category": "cognitive",      "name": "Objetivos de Proceso",         "duration_min": 5,  "difficulty": "beginner",     "goal": "focus",   "description": "Define 3 cosas que controlas hoy. Elimina la ansiedad del resultado.", "steps": ["Escribe 3 objetivos de proceso para hoy.", "Ej: cadencia 88rpm, ritmo cardiaco Z2, hidratación cada 15min.", "NO escribas objetivos de resultado.", "Evalúa solo estos 3 al terminar."]},
    {"id": "cog_pre_mortem",    "category": "cognitive",      "name": "Pre-Mortem Mental",            "duration_min": 10, "difficulty": "advanced",     "goal": "confidence","description": "Anticipa problemas antes de la carrera para no ser sorprendido. Reduce ansiedad de lo desconocido.", "steps": ["Lista 5 cosas que podrían salir mal.", "Para cada una: ¿cuál es tu plan B?", "Ahora sabes que tienes respuesta para todo.", "La ansiedad baja cuando tienes respuestas."]},
    {"id": "cog_mantras",       "category": "cognitive",      "name": "Mantras de Rendimiento",       "duration_min": 4,  "difficulty": "beginner",     "goal": "motivation","description": "Frases cortas, poderosas, que tu mente puede sostener en los momentos de más esfuerzo.", "steps": ["Elige 1-3 mantras personales.", "Ej: 'Soy fuerte', 'Uno a la vez', 'Proceso'.", "Sincroniza con la respiración durante el esfuerzo.", "Repite automáticamente cuando el dolor aparece."]},

    # ACTIVACIÓN/REGULACIÓN
    {"id": "act_power_pose",    "category": "activation",     "name": "Power Pose 2 minutos",         "duration_min": 2,  "difficulty": "beginner",     "goal": "confidence","description": "Postura expansiva 2 min eleva testosterona ~20%, reduce cortisol ~25% (Harvard). Ideal pre-carrera.", "steps": ["Parado, pies separados.", "Manos en las caderas o brazos arriba (V de la victoria).", "Mantén 2 minutos.", "Respira profundo. Siente el poder."]},
    {"id": "act_cold_water",    "category": "activation",     "name": "Estimulación Nervio Vago",     "duration_min": 3,  "difficulty": "beginner",     "goal": "recovery","description": "Agua fría en cara activa el nervio vago → baja FC y ansiedad en segundos.", "steps": ["Agua fría (no helada) en un recipiente.", "Sumerge la cara 30 segundos.", "Repite 3 veces.", "O hielo en nuca 1 minuto."]},
    {"id": "act_progressive_relax","category": "activation",  "name": "Relajación Muscular Progresiva","duration_min": 15,"difficulty": "beginner",     "goal": "stress",  "description": "Tensión y relajación muscular sistemática. Libera tensión acumulada.", "steps": ["Pies: tensa 5s, relaja.", "Pantorrillas: tensa 5s, relaja.", "Muslos.", "Abdomen.", "Hombros.", "Cara.", "Todo el cuerpo relajado."]},

    # PRE-CARRERA ESPECÍFICO
    {"id": "race_7day",         "category": "pre_race",       "name": "Protocolo −7 días",            "duration_min": 20, "difficulty": "intermediate", "goal": "confidence","description": "Una semana antes: logística, visualización, confianza.", "steps": ["Confirma logística (hotel, número, gear).", "Visualización completa de carrera.", "Revisa tu plan de carrera.", "Duerme 8h+.", "Journaling: lista tus fortalezas."]},
    {"id": "race_3day",         "category": "pre_race",       "name": "Protocolo −3 días",            "duration_min": 15, "difficulty": "intermediate", "goal": "anxiety", "description": "3 días antes: simplifica, descansa, confía en el entrenamiento.", "steps": ["Para de analizar datos. El entrenamiento está hecho.", "Visualización corta (10min).", "Respiración 4-7-8 mañana y noche.", "Sin noticias negativas.", "Prepara gear. Todo listo."]},
    {"id": "race_1day",         "category": "pre_race",       "name": "Protocolo −1 día",             "duration_min": 10, "difficulty": "beginner",     "goal": "confidence","description": "La noche antes: ritual de confianza, no de preparación.", "steps": ["Gear preparado. NO revisar más.", "Cena habitual (nada nuevo).", "Visualización 10min.", "Escribe 3 razones por las que estás listo.", "Duerme temprano."]},
    {"id": "race_morning",      "category": "pre_race",       "name": "Mañana de Carrera",            "duration_min": 8,  "difficulty": "beginner",     "goal": "focus",   "description": "El ritual final. Transforma nerviosismo en energía.", "steps": ["Despierta sin alarma si es posible.", "Respiración en caja 5min.", "Desayuno ritual (siempre el mismo).", "Power Pose 2min en la ducha.", "Mantras mientras preparas el gear.", "Último chequeo. Sale."]},
    {"id": "race_transition",   "category": "pre_race",       "name": "Transición Mental",            "duration_min": 3,  "difficulty": "beginner",     "goal": "focus",   "description": "En transición antes del disparo: 3 minutos de presencia total.", "steps": ["Cierra los ojos.", "3 respiraciones profundas.", "Siente el cuerpo.", "Visualiza los primeros 100m del swim.", "Abre los ojos. Modo carrera activado."]},

    # RECUPERACIÓN MENTAL
    {"id": "rec_debrief",       "category": "recovery_mental","name": "Debrief Post-Carrera",         "duration_min": 20, "difficulty": "beginner",     "goal": "recovery","description": "Procesa la carrera antes de que el ego distorsione la memoria.", "steps": ["24-48h después.", "¿Qué salió bien? (lista exhaustiva).", "¿Qué cambiarías? (sin juicio).", "¿Qué aprendiste?", "Una cosa a mejorar para la próxima."]},
    {"id": "rec_gratitude",     "category": "recovery_mental","name": "Diario de Gratitud Deportivo",  "duration_min": 5,  "difficulty": "beginner",     "goal": "motivation","description": "3 cosas de hoy que agradeces en tu entrenamiento. Recalibra el foco hacia el progreso.", "steps": ["Cada noche, 5 minutos.", "Escribe 3 cosas específicas del entrenamiento de hoy.", "No genéricas — específicas.", "Ej: 'Aguanté el último intervalo', 'La técnica de nado mejoró'."]},
    {"id": "rec_flow_journal",  "category": "recovery_mental","name": "Diario de Estado de Flow",     "duration_min": 10, "difficulty": "intermediate", "goal": "focus",   "description": "Documenta los entrenamientos donde entraste en flow. Identifica las condiciones que lo activan.", "steps": ["¿Cuándo fue tu último flow?", "¿Qué condiciones lo activaron?", "¿Temperatura? ¿Música? ¿Horario? ¿Compañero?", "Replica esas condiciones.", "El flow es reproducible."]},
]

PROTOCOL_BY_ID = {p["id"]: p for p in PROTOCOL_LIBRARY}

GOAL_PROTOCOLS = {}
for p in PROTOCOL_LIBRARY:
    GOAL_PROTOCOLS.setdefault(p["goal"], []).append(p["id"])


# ─────────────────────────────────────────────────────────────────────────────
# MENTAL FATIGUE SCORE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _mfs_from_checkin(checkin: MentalCheckin) -> float:
    """
    0-100 component from check-in.
    anxiety inverted (1=worst, 5=best → low anxiety = good).
    motivation, focus, confidence, mood direct.
    """
    if not checkin:
        return None
    vals = []
    weights = [
        (checkin.anxiety,    0.30, False),  # UI: 5=muy calmo=bueno → direct mapping
        (checkin.motivation, 0.25, False),
        (checkin.focus,      0.25, False),
        (checkin.confidence, 0.15, False),
        (checkin.mood,       0.05, False),
    ]
    total_w = 0.0
    total_v = 0.0
    for val, w, inverted in weights:
        if val is None:
            continue
        normalized = (6 - val) / 4.0 if inverted else (val - 1) / 4.0
        total_v += normalized * w
        total_w += w
    if total_w < 0.25:
        return None
    return round((total_v / total_w) * 100, 1)


def _mfs_level(score: int) -> tuple:
    """Returns (level, color, signal, recommendation, protocol_suggested)."""
    if score >= 85:
        return ("peak",     "#10B981", "train",    "Estado mental óptimo. Excelente día para entrenamiento de calidad o competencia.", "viz_race_day")
    if score >= 70:
        return ("good",     "#0EA5E9", "train",    "Buen estado mental. Entrena con confianza.", "mind_5min")
    if score >= 55:
        return ("moderate", "#F59E0B", "reduce",   "Fatiga mental moderada. Considera reducir la intensidad o acortar la sesión.", "breath_box")
    if score >= 40:
        return ("low",      "#F97316", "rest",     "Fatiga mental alta. Prioriza descanso mental — un entrenamiento suave o día de recuperación.", "breath_478")
    return ("critical",     "#EF4444", "rest",     "Fatiga mental crítica. El rendimiento y la toma de decisiones están comprometidos. Descansa.", "rec_debrief")


def _compute_mfs(
    checkin: Optional[MentalCheckin],
    recovery: Optional[RecoveryScore],
    wellness: Optional[WellnessLog],
    hrv_rmssd: Optional[float] = None,
) -> dict:
    """
    Computes Mental Fatigue Score from all available inputs.
    Returns the full MFS dict ready for DB insertion.
    """
    components = {}
    available = 0

    # 1. Check-in factor (peso 50%)
    checkin_score = _mfs_from_checkin(checkin)
    if checkin_score is not None:
        components["checkin"] = (checkin_score, 0.50)
        available += 1

    # 2. Recovery Score factor (peso 25%)
    if recovery and recovery.score is not None:
        components["recovery"] = (recovery.score, 0.25)
        available += 1

    # 3. HRV factor (peso 15%) — proxy via RecoveryScore.hrv_factor
    if recovery and recovery.hrv_factor is not None:
        # hrv_factor already 0-100
        components["hrv"] = (recovery.hrv_factor, 0.15)

    # 4. Stress factor (peso 10%) — from wellness, inverted
    if wellness and wellness.stress is not None:
        stress_normalized = (6 - wellness.stress) / 4.0 * 100  # 1=bad→100 pts
        components["stress"] = (stress_normalized, 0.10)
        available += 1

    if not components:
        return None

    total_w = sum(w for _, w in components.values())
    total_v = sum(v * w for v, w in components.values())
    score = round(min(100, max(0, total_v / total_w)), 0)
    score = int(score)

    level, color, signal, recommendation, protocol = _mfs_level(score)

    # Adjust protocol based on most pressing issue
    if checkin and checkin.anxiety and checkin.anxiety <= 2:
        protocol = "breath_478"
    elif checkin and checkin.motivation and checkin.motivation <= 2:
        protocol = "cog_mantras"
    elif checkin and checkin.confidence and checkin.confidence <= 2:
        protocol = "viz_confidence"

    return {
        "score":              score,
        "level":              level,
        "color":              color,
        "signal":             signal,
        "recommendation":     recommendation,
        "protocol_suggested": protocol,
        "checkin_factor":     components.get("checkin", (None,))[0],
        "recovery_factor":    components.get("recovery", (None,))[0],
        "hrv_factor":         components.get("hrv", (None,))[0],
        "stress_factor":      components.get("stress", (None,))[0],
        "data_completeness":  round(available / 3.0, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class CheckinCreate(BaseModel):
    date_iso:    Optional[str] = None
    anxiety:     Optional[int] = Field(None, ge=1, le=5)
    motivation:  Optional[int] = Field(None, ge=1, le=5)
    focus:       Optional[int] = Field(None, ge=1, le=5)
    confidence:  Optional[int] = Field(None, ge=1, le=5)
    mood:        Optional[int] = Field(None, ge=1, le=5)
    notes:       Optional[str] = Field(None, max_length=300)


class ProtocolSessionCreate(BaseModel):
    protocol_id:  str
    duration_min: Optional[int] = Field(None, ge=1, le=120)
    rating:       Optional[int] = Field(None, ge=1, le=5)
    notes:        Optional[str] = Field(None, max_length=200)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _uuid_str() -> str:
    return str(uuid.uuid4())


def _today() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()


def _get_or_compute_mfs(user_id: str, date_iso: str, db: Session, force: bool = False) -> Optional[MentalFatigueScore]:
    existing = db.query(MentalFatigueScore).filter_by(
        user_id=user_id, date_iso=date_iso
    ).first()
    if existing and not force:
        age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - existing.calculated_at).total_seconds() / 3600
        if age_h < 6:
            return existing

    checkin  = db.query(MentalCheckin).filter_by(user_id=user_id, date_iso=date_iso).first()
    recovery = db.query(RecoveryScore).filter_by(user_id=user_id, date_iso=date_iso).first()
    wellness = db.query(WellnessLog).filter_by(user_id=user_id, date_iso=date_iso).first()

    data = _compute_mfs(checkin, recovery, wellness)
    if not data:
        return None

    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        existing.calculated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return existing

    mfs = MentalFatigueScore(
        id=_uuid_str(), user_id=user_id, date_iso=date_iso, **data
    )
    db.add(mfs)
    db.commit()
    return mfs


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def mental_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vista maestra — score del día + protocolo + tendencia 7d + próxima carrera."""
    today = _today()
    mfs   = _get_or_compute_mfs(current_user.id, today, db)
    checkin = db.query(MentalCheckin).filter_by(
        user_id=current_user.id, date_iso=today
    ).first()

    # 7-day trend
    trend = []
    for i in range(6, -1, -1):
        d = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=i)).date().isoformat()
        m = db.query(MentalFatigueScore).filter_by(
            user_id=current_user.id, date_iso=d
        ).first()
        trend.append({"date_iso": d, "score": m.score if m else None, "level": m.level if m else None})

    # Next race (for pre-race protocol suggestion)
    next_race = db.query(RaceEvent).filter(
        RaceEvent.user_id == current_user.id,
        RaceEvent.race_date > today,
        RaceEvent.is_goal_race == True,
    ).order_by(RaceEvent.race_date.asc()).first()
    days_to_race = None
    pre_race_protocol = None
    if next_race:
        days_to_race = (
            datetime.strptime(next_race.race_date, "%Y-%m-%d").date() -
            datetime.now(timezone.utc).replace(tzinfo=None).date()
        ).days
        if days_to_race <= 1:
            pre_race_protocol = PROTOCOL_BY_ID.get("race_morning")
        elif days_to_race <= 3:
            pre_race_protocol = PROTOCOL_BY_ID.get("race_3day")
        elif days_to_race <= 7:
            pre_race_protocol = PROTOCOL_BY_ID.get("race_7day")

    # Protocol sessions today
    sessions_today = db.query(MentalProtocolSession).filter_by(
        user_id=current_user.id, date_iso=today
    ).all()
    completed_today = [s.protocol_id for s in sessions_today]

    # Suggested protocol
    suggested_protocol = None
    if mfs and mfs.protocol_suggested:
        suggested_protocol = PROTOCOL_BY_ID.get(mfs.protocol_suggested)

    return {
        "today": {
            "date_iso": today,
            "score":    mfs.score if mfs else None,
            "level":    mfs.level if mfs else None,
            "color":    mfs.color if mfs else None,
            "signal":   mfs.signal if mfs else None,
            "recommendation": mfs.recommendation if mfs else "Completa el check-in para obtener tu Mental Fatigue Score.",
            "data_completeness": mfs.data_completeness if mfs else 0.0,
            "has_checkin": checkin is not None,
        },
        "checkin": {
            "anxiety":    checkin.anxiety    if checkin else None,
            "motivation": checkin.motivation if checkin else None,
            "focus":      checkin.focus      if checkin else None,
            "confidence": checkin.confidence if checkin else None,
            "mood":       checkin.mood       if checkin else None,
            "notes":      checkin.notes      if checkin else None,
        },
        "trend_7d":          trend,
        "suggested_protocol": suggested_protocol,
        "completed_today":   completed_today,
        "race": {
            "days_to_race":       days_to_race,
            "race_name":          next_race.race_name if next_race else None,
            "pre_race_protocol":  pre_race_protocol,
        },
    }


@router.post("/checkin")
def save_checkin(
    body: CheckinCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert check-in mental diario. Recalcula MFS automáticamente."""
    date_iso = body.date_iso or _today()
    existing = db.query(MentalCheckin).filter_by(
        user_id=current_user.id, date_iso=date_iso
    ).first()

    if existing:
        if body.anxiety     is not None: existing.anxiety     = body.anxiety
        if body.motivation  is not None: existing.motivation  = body.motivation
        if body.focus       is not None: existing.focus       = body.focus
        if body.confidence  is not None: existing.confidence  = body.confidence
        if body.mood        is not None: existing.mood        = body.mood
        if body.notes       is not None: existing.notes       = body.notes
        existing.logged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        checkin = existing
    else:
        checkin = MentalCheckin(
            id=_uuid_str(),
            user_id=current_user.id,
            date_iso=date_iso,
            anxiety=body.anxiety,
            motivation=body.motivation,
            focus=body.focus,
            confidence=body.confidence,
            mood=body.mood,
            notes=body.notes,
        )
        db.add(checkin)
        db.commit()

    mfs = _get_or_compute_mfs(current_user.id, date_iso, db, force=True)
    return {
        "message":  "check-in guardado",
        "date_iso": date_iso,
        "mfs_score": mfs.score if mfs else None,
        "mfs_level": mfs.level if mfs else None,
        "mfs_color": mfs.color if mfs else None,
        "recommendation": mfs.recommendation if mfs else None,
        "protocol_suggested": PROTOCOL_BY_ID.get(mfs.protocol_suggested) if mfs and mfs.protocol_suggested else None,
    }


@router.get("/score")
def get_score(
    date_iso: Optional[str] = None,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    d = date_iso or _today()
    mfs = _get_or_compute_mfs(current_user.id, d, db, force=force)
    if not mfs:
        return {"date_iso": d, "score": None, "message": "Completa el check-in diario para calcular tu Mental Fatigue Score."}
    return {
        "date_iso":   d,
        "score":      mfs.score,
        "level":      mfs.level,
        "color":      mfs.color,
        "signal":     mfs.signal,
        "recommendation": mfs.recommendation,
        "factors": {
            "checkin":  mfs.checkin_factor,
            "recovery": mfs.recovery_factor,
            "hrv":      mfs.hrv_factor,
            "stress":   mfs.stress_factor,
        },
        "data_completeness": mfs.data_completeness,
        "protocol_suggested": PROTOCOL_BY_ID.get(mfs.protocol_suggested) if mfs.protocol_suggested else None,
    }


@router.get("/history")
def get_history(
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).date().isoformat()
    scores = db.query(MentalFatigueScore).filter(
        MentalFatigueScore.user_id == current_user.id,
        MentalFatigueScore.date_iso >= start,
    ).order_by(MentalFatigueScore.date_iso.asc()).all()

    history = [{
        "date_iso": s.date_iso,
        "score":    s.score,
        "level":    s.level,
        "color":    s.color,
        "signal":   s.signal,
    } for s in scores]

    avg = round(sum(s.score for s in scores) / len(scores), 1) if scores else None
    best = max((s.score for s in scores), default=None)
    worst = min((s.score for s in scores), default=None)

    # Simple trend: compare last 7 vs previous 7
    recent = [s.score for s in scores[-7:]]
    prev   = [s.score for s in scores[-14:-7]]
    trend = "stable"
    if recent and prev:
        r_avg = sum(recent) / len(recent)
        p_avg = sum(prev) / len(prev)
        if r_avg > p_avg + 3:
            trend = "improving"
        elif r_avg < p_avg - 3:
            trend = "declining"

    return {
        "history": history,
        "stats": {"avg": avg, "best": best, "worst": worst, "trend": trend, "days_tracked": len(scores)},
    }


@router.get("/protocols")
def list_protocols(
    category: Optional[str] = None,
    goal: Optional[str] = None,
    difficulty: Optional[str] = None,
    max_duration: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Biblioteca de protocolos con filtros."""
    protos = PROTOCOL_LIBRARY
    if category:
        protos = [p for p in protos if p["category"] == category]
    if goal:
        protos = [p for p in protos if p["goal"] == goal]
    if difficulty:
        protos = [p for p in protos if p["difficulty"] == difficulty]
    if max_duration:
        protos = [p for p in protos if p["duration_min"] <= max_duration]

    # Mark completed sessions this week
    week_start = (datetime.now(timezone.utc).replace(tzinfo=None).date() - timedelta(days=datetime.now(timezone.utc).replace(tzinfo=None).weekday())).isoformat()
    sessions = db.query(MentalProtocolSession).filter(
        MentalProtocolSession.user_id == current_user.id,
        MentalProtocolSession.date_iso >= week_start,
    ).all()
    completed_this_week = {s.protocol_id for s in sessions}

    result = []
    for p in protos:
        p_copy = dict(p)
        p_copy["completed_this_week"] = p["id"] in completed_this_week
        result.append(p_copy)

    categories = list({p["category"] for p in PROTOCOL_LIBRARY})
    goals = list({p["goal"] for p in PROTOCOL_LIBRARY})

    return {
        "protocols": result,
        "count": len(result),
        "categories": sorted(categories),
        "goals": sorted(goals),
    }


@router.get("/protocols/{protocol_id}")
def get_protocol(
    protocol_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = PROTOCOL_BY_ID.get(protocol_id)
    if not p:
        raise HTTPException(404, "Protocolo no encontrado")

    # Get all sessions for this protocol
    sessions = db.query(MentalProtocolSession).filter_by(
        user_id=current_user.id, protocol_id=protocol_id
    ).order_by(MentalProtocolSession.completed_at.desc()).limit(10).all()

    avg_rating = None
    if sessions:
        rated = [s for s in sessions if s.rating]
        avg_rating = round(sum(s.rating for s in rated) / len(rated), 1) if rated else None

    return {
        **p,
        "times_completed": len(sessions),
        "avg_rating":      avg_rating,
        "last_completed":  sessions[0].completed_at.isoformat() if sessions else None,
    }


@router.post("/protocols/{protocol_id}/complete")
def complete_protocol(
    protocol_id: str,
    body: ProtocolSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if protocol_id not in PROTOCOL_BY_ID:
        raise HTTPException(404, "Protocolo no encontrado")
    session = MentalProtocolSession(
        id=_uuid_str(),
        user_id=current_user.id,
        date_iso=_today(),
        protocol_id=protocol_id,
        duration_min=body.duration_min,
        rating=body.rating,
        notes=body.notes,
    )
    db.add(session)
    db.commit()
    # Recalculate MFS (completing a protocol can improve the score)
    _get_or_compute_mfs(current_user.id, _today(), db, force=True)
    return {"message": "sesión completada", "protocol_id": protocol_id}


@router.get("/correlations")
def mental_correlations(
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Correlaciones Mental Fatigue Score × Performance × HRV.
    El diferenciador científico de LabX.
    """
    start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).date().isoformat()

    scores = db.query(MentalFatigueScore).filter(
        MentalFatigueScore.user_id == current_user.id,
        MentalFatigueScore.date_iso >= start,
    ).all()

    score_by_date = {s.date_iso: s for s in scores}

    acts = db.query(GarminActivity).filter(
        GarminActivity.user_id == current_user.id,
        GarminActivity.start_time >= start + "T00:00:00",
    ).all()

    data_points = []
    for act in acts:
        date_iso = str(act.start_time)[:10] if act.start_time else None
        if not date_iso:
            continue
        mfs = score_by_date.get(date_iso)
        if not mfs or not act.tss:
            continue
        data_points.append({
            "date_iso":   date_iso,
            "mfs_score":  mfs.score,
            "mfs_level":  mfs.level,
            "tss":        act.tss,
            "avg_hr":     act.avg_hr,
            "activity_type": act.activity_type,
        })

    # Compute average TSS by MFS level
    by_level = {}
    for dp in data_points:
        lvl = dp["mfs_level"]
        by_level.setdefault(lvl, []).append(dp["tss"])

    tss_by_level = {
        lvl: round(sum(vals) / len(vals), 1)
        for lvl, vals in by_level.items()
    }

    # Simple correlation: does higher MFS → higher TSS achieved?
    corr_insight = None
    if len(data_points) >= 5:
        mfs_vals = [dp["mfs_score"] for dp in data_points]
        tss_vals = [dp["tss"]       for dp in data_points]
        mfs_avg = sum(mfs_vals) / len(mfs_vals)
        tss_avg = sum(tss_vals) / len(tss_vals)
        num   = sum((m - mfs_avg) * (t - tss_avg) for m, t in zip(mfs_vals, tss_vals))
        denom = (sum((m - mfs_avg) ** 2 for m in mfs_vals) *
                 sum((t - tss_avg) ** 2 for t in tss_vals)) ** 0.5
        corr  = round(num / denom, 2) if denom > 0 else 0
        corr_insight = corr

    return {
        "data_points":    data_points,
        "tss_by_mfs_level": tss_by_level,
        "correlation_mfs_tss": corr_insight,
        "insight": (
            "Mayor Mental Fatigue Score se correlaciona positivamente con mayor TSS alcanzado."
            if corr_insight and corr_insight > 0.3 else
            "Sin correlación significativa todavía — necesitas más datos (mín. 14 días)."
        ),
        "days_analyzed":  days,
        "data_points_count": len(data_points),
    }


@router.get("/pre-race")
def pre_race_protocol(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Protocolo mental personalizado para la próxima carrera objetivo."""
    today = _today()
    race = db.query(RaceEvent).filter(
        RaceEvent.user_id == current_user.id,
        RaceEvent.race_date > today,
        RaceEvent.is_goal_race == True,
    ).order_by(RaceEvent.race_date.asc()).first()

    if not race:
        return {"message": "Sin carrera objetivo registrada. Agrega tu próxima carrera en Perfil.", "protocol": None}

    days_to_race = (
        datetime.strptime(race.race_date, "%Y-%m-%d").date() -
        datetime.now(timezone.utc).replace(tzinfo=None).date()
    ).days

    # Determine which protocols apply today
    applicable = []
    if days_to_race >= 7:
        applicable.append(PROTOCOL_BY_ID["race_7day"])
        applicable.append(PROTOCOL_BY_ID["viz_race_day"])
        applicable.append(PROTOCOL_BY_ID["cog_process_goals"])
    elif days_to_race >= 3:
        applicable.append(PROTOCOL_BY_ID["race_3day"])
        applicable.append(PROTOCOL_BY_ID["breath_478"])
        applicable.append(PROTOCOL_BY_ID["viz_confidence"])
    elif days_to_race >= 1:
        applicable.append(PROTOCOL_BY_ID["race_1day"])
        applicable.append(PROTOCOL_BY_ID["breath_box"])
    elif days_to_race == 0:
        applicable.append(PROTOCOL_BY_ID["race_morning"])
        applicable.append(PROTOCOL_BY_ID["race_transition"])

    # Get MFS for context
    mfs = db.query(MentalFatigueScore).filter_by(
        user_id=current_user.id, date_iso=today
    ).first()

    # Personalize based on anxiety
    checkin = db.query(MentalCheckin).filter_by(
        user_id=current_user.id, date_iso=today
    ).first()
    extra_protocols = []
    if checkin and checkin.anxiety and checkin.anxiety <= 2:
        extra_protocols.append(PROTOCOL_BY_ID["breath_physiological"])
        extra_protocols.append(PROTOCOL_BY_ID["act_power_pose"])

    return {
        "race": {
            "name": race.race_name if hasattr(race, "race_name") else "Tu carrera",
            "date": race.race_date,
            "days_to_race": days_to_race,
            "distance": race.distance if hasattr(race, "distance") else None,
        },
        "protocols_today":    applicable,
        "extra_if_anxious":   extra_protocols,
        "mfs_today":          mfs.score if mfs else None,
        "mfs_level":          mfs.level if mfs else None,
        "message": (
            f"A {days_to_race} días de la carrera. Sigue el protocolo mental del día."
            if days_to_race > 0 else
            "Es el día de carrera. Confía en tu preparación. 🏁"
        ),
    }


@router.get("/coach-view")
def coach_view(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vista coach — estado mental de todos sus atletas."""
    if current_user.rol not in ("coach", "admin"):
        raise HTTPException(403, "Solo coaches y admins")

    from ..models import CoachAthlete
    try:
        athlete_ids = [
            ca.athlete_id for ca in
            db.query(CoachAthlete).filter_by(coach_id=current_user.id).all()
        ]
    except Exception:
        athlete_ids = []

    today = _today()
    result = []
    for aid in athlete_ids:
        u   = db.query(User).filter_by(id=aid).first()
        mfs = db.query(MentalFatigueScore).filter_by(user_id=aid, date_iso=today).first()
        chk = db.query(MentalCheckin).filter_by(user_id=aid, date_iso=today).first()
        result.append({
            "athlete": {
                "id":   aid,
                "name": (u.full_name or u.email.split("@")[0]) if u else "—",
            },
            "mfs_score": mfs.score if mfs else None,
            "mfs_level": mfs.level if mfs else None,
            "mfs_color": mfs.color if mfs else None,
            "has_checkin": chk is not None,
            "anxiety": chk.anxiety if chk else None,
            "motivation": chk.motivation if chk else None,
        })

    result.sort(key=lambda x: (x["mfs_score"] or 999))
    return {"athletes": result, "count": len(result), "date_iso": today}
