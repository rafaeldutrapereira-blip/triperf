"""
LabX — Garmin Workout Converter
====================================
Convierte un workout estructurado de nuestra DB al JSON
exacto que exige la Garmin Training API v2.

Garmin API reference:
  POST https://apis.garmin.com/training-api/workout
  POST https://apis.garmin.com/training-api/workout/{id}/schedule/{YYYY-MM-DD}

Spec: https://developer.garmin.com/gc-developer-program/workout-api/
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# ENUMS — exactamente como los acepta la API de Garmin
# ─────────────────────────────────────────────────────────────────────────────

class GarminSport(str, Enum):
    RUNNING          = "RUNNING"
    CYCLING          = "CYCLING"
    LAP_SWIMMING     = "LAP_SWIMMING"
    OPEN_WATER_SWIM  = "OPEN_WATER_SWIMMING"
    STRENGTH         = "STRENGTH_TRAINING"
    CARDIO           = "CARDIO"

class GarminStepType(str, Enum):
    WARMUP   = "WarmUp"
    COOLDOWN = "CoolDown"
    INTERVAL = "Interval"
    RECOVERY = "Recovery"
    REST     = "Rest"
    REPEAT   = "Repeat"
    OTHER    = "Other"

class GarminDurationType(str, Enum):
    TIME              = "Time"             # durationValue = segundos
    DISTANCE          = "Distance"         # durationValue = metros
    REPS              = "Reps"             # durationValue = repeticiones
    OPEN              = "Open"             # sin límite
    FIXED_REST        = "Fixed_Rest"       # descanso con duración fija (seg)
    HR_LESS_THAN      = "HrLessThan"       # durationValue = bpm
    HR_GREATER_THAN   = "HrGreaterThan"    # durationValue = bpm
    POWER_LESS_THAN   = "PowerLessThan"    # durationValue = vatios
    POWER_GREATER_THAN = "PowerGreaterThan" # durationValue = vatios

class GarminTargetType(str, Enum):
    OPEN        = "Open"
    SPEED       = "Speed"         # m/s — para pace running y natación
    HEART_RATE  = "HeartRate"     # bpm absoluto
    CADENCE     = "Cadence"       # rpm
    POWER       = "Power"         # vatios absolutos
    SWIM_STROKE = "SwimStroke"    # tipo de brazada


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES — nuestra representación interna (desde la DB)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AthleteProfile:
    """Perfil del atleta necesario para resolver targets relativos."""
    ftp_watts:     int   = 240    # FTP en vatios (ciclismo)
    lthr_bpm:      int   = 168    # Lactate Threshold HR en bpm
    css_sec_100m:  int   = 110    # Critical Swim Speed en seg/100m
    threshold_run_sec_km: int = 260  # Ritmo umbral run en seg/km (4:20/km)
    weight_kg:     float = 72.0


@dataclass
class WorkoutStep:
    """Un bloque/step del entrenamiento tal como está en nuestra DB."""
    step_order:      int
    step_type:       str          # WARMUP, COOLDOWN, INTERVAL, RECOVERY, REST, REPEAT, OTHER
    duration_type:   str          # TIME, DISTANCE, REPS, OPEN, HR_LESS_THAN, ...
    duration_value:  float | None = None

    target_type:     str          = "OPEN"
    target_low:      float | None = None
    target_high:     float | None = None

    repeat_count:    int | None   = None
    child_steps:     list["WorkoutStep"] = field(default_factory=list)
    description:     str          = ""
    swim_stroke:     str | None   = None

    label:           str          = ""


@dataclass
class StructuredWorkout:
    """Entrenamiento estructurado tal como sale de nuestra DB."""
    id:            str
    name:          str
    sport:         str             # SWIMMING, CYCLING, RUNNING, STRENGTH
    description:   str             = ""
    steps:         list[WorkoutStep] = field(default_factory=list)
    estimated_duration_sec: int | None = None
    estimated_distance_m:   float | None = None
    estimated_tss:          float | None = None


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSORES DE UNIDADES
# ─────────────────────────────────────────────────────────────────────────────

class UnitConverter:
    """
    Garmin API usa SIEMPRE unidades SI:
      Speed/Pace → m/s
      Distance   → metros
      Duration   → segundos
      Power      → vatios (absolutos)
      HR         → bpm (absolutos)
    """

    @staticmethod
    def pace_per_km_to_ms(sec_per_km: float) -> float:
        """4:20/km (260 seg/km) → 1000/260 = 3.846 m/s"""
        if sec_per_km <= 0:
            raise ValueError(f"sec_per_km debe ser positivo, recibido: {sec_per_km}")
        return round(1000.0 / sec_per_km, 4)

    @staticmethod
    def pace_per_100m_to_ms(sec_per_100m: float) -> float:
        """1:50/100m (110 seg) → 100/110 = 0.9090 m/s"""
        if sec_per_100m <= 0:
            raise ValueError(f"sec_per_100m debe ser positivo, recibido: {sec_per_100m}")
        return round(100.0 / sec_per_100m, 4)

    @staticmethod
    def pct_ftp_to_watts(pct: float, ftp: int) -> float:
        """75% FTP con FTP=240 → 180 vatios"""
        return round(pct / 100.0 * ftp, 1)

    @staticmethod
    def pct_lthr_to_bpm(pct: float, lthr: int) -> float:
        """80% LTHR con LTHR=168 → 134.4 bpm"""
        return round(pct / 100.0 * lthr, 1)

    @staticmethod
    def pct_css_to_ms(pct: float, css_sec_100m: int) -> float:
        """95% CSS con CSS=110 seg/100m → pace ajustado → m/s"""
        adjusted = css_sec_100m / (pct / 100.0)
        return UnitConverter.pace_per_100m_to_ms(adjusted)

    @staticmethod
    def pct_run_threshold_to_ms(pct: float, thresh_sec_km: int) -> float:
        """95% pace umbral con umbral=260 seg/km → adjusted pace → m/s"""
        adjusted = thresh_sec_km / (pct / 100.0)
        return UnitConverter.pace_per_km_to_ms(adjusted)


# ─────────────────────────────────────────────────────────────────────────────
# MAPEADORES
# ─────────────────────────────────────────────────────────────────────────────

SPORT_MAP: dict[str, GarminSport] = {
    "SWIMMING":  GarminSport.LAP_SWIMMING,
    "CYCLING":   GarminSport.CYCLING,
    "RUNNING":   GarminSport.RUNNING,
    "STRENGTH":  GarminSport.STRENGTH,
}

STEP_TYPE_MAP: dict[str, GarminStepType] = {
    "WARMUP":   GarminStepType.WARMUP,
    "COOLDOWN": GarminStepType.COOLDOWN,
    "INTERVAL": GarminStepType.INTERVAL,
    "RECOVERY": GarminStepType.RECOVERY,
    "REST":     GarminStepType.REST,
    "REPEAT":   GarminStepType.REPEAT,
    "OTHER":    GarminStepType.OTHER,
}

DURATION_TYPE_MAP: dict[str, GarminDurationType] = {
    "TIME":               GarminDurationType.TIME,
    "DISTANCE":           GarminDurationType.DISTANCE,
    "REPS":               GarminDurationType.REPS,
    "OPEN":               GarminDurationType.OPEN,
    "FIXED_REST":         GarminDurationType.FIXED_REST,
    "HR_LESS_THAN":       GarminDurationType.HR_LESS_THAN,
    "HR_GREATER_THAN":    GarminDurationType.HR_GREATER_THAN,
    "POWER_LESS_THAN":    GarminDurationType.POWER_LESS_THAN,
    "POWER_GREATER_THAN": GarminDurationType.POWER_GREATER_THAN,
}


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSOR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class GarminWorkoutConverter:
    """
    Convierte un StructuredWorkout (nuestra DB) al JSON de la Garmin Training API.

    Uso:
        converter = GarminWorkoutConverter(athlete_profile)
        garmin_json = converter.convert(workout)
    """

    def __init__(self, athlete: AthleteProfile):
        self.athlete = athlete
        self._uc = UnitConverter()

    # ──────────────────────────────────────────
    # PUNTO DE ENTRADA PRINCIPAL
    # ──────────────────────────────────────────

    def convert(self, workout: StructuredWorkout) -> dict[str, Any]:
        """
        Retorna el dict listo para serializar a JSON y enviar a Garmin API.
        """
        garmin_sport = SPORT_MAP.get(workout.sport)
        if not garmin_sport:
            raise ConversionError(f"Deporte no soportado: '{workout.sport}'")

        garmin_steps = self._convert_steps(workout.steps, garmin_sport)

        payload: dict[str, Any] = {
            "workoutName":  workout.name[:100],        # Garmin max 100 chars
            "description":  workout.description[:1000] if workout.description else "",
            "sport":        garmin_sport.value,
            "workoutProvider": "KONA_LABS",
            "workoutSourceId": str(workout.id),        # nuestro ID interno
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sport": garmin_sport.value,
                    "workoutSteps": garmin_steps,
                }
            ],
        }

        # Estimaciones opcionales (mejora la UX en el reloj Garmin)
        if workout.estimated_duration_sec:
            payload["estimatedDurationInSecs"] = int(workout.estimated_duration_sec)
        if workout.estimated_distance_m:
            payload["estimatedDistanceInMeters"] = round(workout.estimated_distance_m)

        return payload

    # ──────────────────────────────────────────
    # CONVERSIÓN DE STEPS (recursiva para REPEAT)
    # ──────────────────────────────────────────

    def _convert_steps(
        self,
        steps: list[WorkoutStep],
        sport: GarminSport,
        order_offset: int = 1,
    ) -> list[dict[str, Any]]:
        garmin_steps = []
        current_order = order_offset

        for step in sorted(steps, key=lambda s: s.step_order):
            if step.step_type == "REPEAT":
                garmin_step = self._convert_repeat_step(step, sport, current_order)
            else:
                garmin_step = self._convert_single_step(step, sport, current_order)

            garmin_steps.append(garmin_step)
            # REPEAT cuenta como 1 step en la secuencia de Garmin
            current_order += 1

        return garmin_steps

    def _convert_single_step(
        self,
        step: WorkoutStep,
        sport: GarminSport,
        order: int,
    ) -> dict[str, Any]:

        garmin_step: dict[str, Any] = {
            "stepOrder": order,
            "stepType":  STEP_TYPE_MAP.get(step.step_type, GarminStepType.OTHER).value,
            "description": (step.description or step.label or "")[:512],
        }

        # — DURACIÓN —
        self._fill_duration(garmin_step, step)

        # — TARGET DE INTENSIDAD —
        self._fill_target(garmin_step, step, sport)

        # — NATACIÓN: tipo de brazada —
        if sport == GarminSport.LAP_SWIMMING and step.swim_stroke:
            garmin_step["swimStroke"] = step.swim_stroke.upper()

        return garmin_step

    def _convert_repeat_step(
        self,
        step: WorkoutStep,
        sport: GarminSport,
        order: int,
    ) -> dict[str, Any]:
        """
        Un REPEAT en Garmin es un step especial con repeatValue
        y una lista anidada de workoutSteps hijo.
        """
        if not step.child_steps:
            raise ConversionError(
                f"Step REPEAT (orden {step.step_order}) no tiene steps hijo."
            )
        if not step.repeat_count or step.repeat_count < 1:
            raise ConversionError(
                f"Step REPEAT (orden {step.step_order}) sin repeat_count válido."
            )

        garmin_children = self._convert_steps(
            step.child_steps, sport, order_offset=1
        )

        return {
            "stepOrder":    order,
            "stepType":     GarminStepType.REPEAT.value,
            "repeatValue":  step.repeat_count,
            "description":  (step.description or step.label or f"Serie ×{step.repeat_count}")[:512],
            "workoutSteps": garmin_children,     # steps anidados
        }

    # ──────────────────────────────────────────
    # FILL DURATION
    # ──────────────────────────────────────────

    def _fill_duration(self, out: dict, step: WorkoutStep) -> None:
        dtype = DURATION_TYPE_MAP.get(step.duration_type)
        if not dtype:
            raise ConversionError(
                f"duration_type '{step.duration_type}' no reconocido."
            )

        out["durationType"] = dtype.value

        if dtype == GarminDurationType.OPEN:
            return  # sin durationValue

        if step.duration_value is None:
            raise ConversionError(
                f"Step con durationType '{dtype.value}' requiere duration_value."
            )

        # Garmin espera enteros para TIME y DISTANCE
        if dtype in (GarminDurationType.TIME, GarminDurationType.FIXED_REST):
            out["durationValue"] = int(round(step.duration_value))      # segundos
        elif dtype == GarminDurationType.DISTANCE:
            out["durationValue"] = int(round(step.duration_value))      # metros
        elif dtype == GarminDurationType.REPS:
            out["durationValue"] = int(round(step.duration_value))      # repeticiones
        else:
            # HR_LESS_THAN, HR_GREATER_THAN, POWER_*
            out["durationValue"] = round(step.duration_value, 1)

    # ──────────────────────────────────────────
    # FILL TARGET (el núcleo de la conversión)
    # ──────────────────────────────────────────

    def _fill_target(self, out: dict, step: WorkoutStep, sport: GarminSport) -> None:
        """
        Mapea nuestros targets (que pueden ser relativos: %FTP, min/km, %LTHR)
        al formato absoluto SI que exige Garmin.
        """
        ttype = step.target_type

        if ttype == "OPEN" or step.target_low is None:
            out["targetType"] = GarminTargetType.OPEN.value
            return

        lo, hi = step.target_low, (step.target_high or step.target_low)

        # ── Potencia ciclismo ──
        if ttype == "POWER":
            out["targetType"]     = GarminTargetType.POWER.value
            out["targetValueLow"] = round(lo)
            out["targetValueHigh"]= round(hi)

        elif ttype == "POWER_PCT_FTP":
            lo_w = self._uc.pct_ftp_to_watts(lo, self.athlete.ftp_watts)
            hi_w = self._uc.pct_ftp_to_watts(hi, self.athlete.ftp_watts)
            out["targetType"]     = GarminTargetType.POWER.value
            out["targetValueLow"] = round(lo_w)
            out["targetValueHigh"]= round(hi_w)

        # ── Frecuencia Cardíaca ──
        elif ttype == "HEART_RATE":
            out["targetType"]     = GarminTargetType.HEART_RATE.value
            out["targetValueLow"] = round(lo)
            out["targetValueHigh"]= round(hi)

        elif ttype == "HEART_RATE_PCT":
            lo_bpm = self._uc.pct_lthr_to_bpm(lo, self.athlete.lthr_bpm)
            hi_bpm = self._uc.pct_lthr_to_bpm(hi, self.athlete.lthr_bpm)
            out["targetType"]     = GarminTargetType.HEART_RATE.value
            out["targetValueLow"] = round(lo_bpm)
            out["targetValueHigh"]= round(hi_bpm)

        # ── Ritmo running (min/km → m/s) ──
        elif ttype == "PACE_PER_KM":
            # target_low/high en seg/km; low es el más LENTO (más seg = menor velocidad)
            # Garmin: targetValueLow < targetValueHigh en m/s → low es el más RÁPIDO
            lo_ms = self._uc.pace_per_km_to_ms(lo)
            hi_ms = self._uc.pace_per_km_to_ms(hi)
            out["targetType"]     = GarminTargetType.SPEED.value
            out["targetValueLow"] = min(lo_ms, hi_ms)   # más lento (menor m/s)
            out["targetValueHigh"]= max(lo_ms, hi_ms)   # más rápido (mayor m/s)

        # ── Ritmo natación (seg/100m → m/s) ──
        elif ttype == "PACE_PER_100M":
            lo_ms = self._uc.pace_per_100m_to_ms(lo)
            hi_ms = self._uc.pace_per_100m_to_ms(hi)
            out["targetType"]     = GarminTargetType.SPEED.value
            out["targetValueLow"] = min(lo_ms, hi_ms)
            out["targetValueHigh"]= max(lo_ms, hi_ms)

        # ── Velocidad directa ──
        elif ttype == "SPEED":
            out["targetType"]     = GarminTargetType.SPEED.value
            out["targetValueLow"] = round(lo, 4)
            out["targetValueHigh"]= round(hi, 4)

        # ── Cadencia ──
        elif ttype == "CADENCE":
            out["targetType"]     = GarminTargetType.CADENCE.value
            out["targetValueLow"] = round(lo)
            out["targetValueHigh"]= round(hi)

        # ── Brazada natación ──
        elif ttype == "SWIM_STROKE":
            out["targetType"]     = GarminTargetType.SWIM_STROKE.value
            # No hay rango para brazada; targetValueLow lleva el código de brazada
            # (0=FREESTYLE, 1=BACKSTROKE, 2=BREASTSTROKE, 3=BUTTERFLY, 4=DRILL)
            stroke_code = {"FREESTYLE":0,"BACKSTROKE":1,"BREASTSTROKE":2,
                           "BUTTERFLY":3,"DRILL":4}.get(step.swim_stroke or "FREESTYLE", 0)
            out["targetValueLow"] = stroke_code
            out["targetValueHigh"]= stroke_code

        else:
            out["targetType"] = GarminTargetType.OPEN.value


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPCIÓN PROPIA
# ─────────────────────────────────────────────────────────────────────────────

class ConversionError(ValueError):
    """Se lanza cuando los datos del workout no se pueden convertir."""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — ESTIMACIÓN TSS (para el dashboard del atleta)
# ─────────────────────────────────────────────────────────────────────────────

def estimate_training_metrics(
    workout: StructuredWorkout,
    athlete: AthleteProfile,
) -> tuple[int, float, int]:
    """
    Estima (duration_sec, tss, kcal) de un workout estructurado.
    Retorna (dur_sec, tss, kcal).
    """
    dur_sec = 0.0
    tss     = 0.0
    kcal    = 0

    def _process(steps: list[WorkoutStep], repeat: int = 1) -> None:
        nonlocal dur_sec, tss, kcal

        for s in steps:
            if s.step_type == "REPEAT" and s.child_steps:
                _process(s.child_steps, repeat=(s.repeat_count or 1))
                continue

            step_sec = 0.0
            if s.duration_type == "TIME" and s.duration_value:
                step_sec = s.duration_value
            elif s.duration_type == "DISTANCE" and s.duration_value:
                # Estimate time from target pace
                target_ms = 1.0  # default 1 m/s si no hay target
                if s.target_type == "PACE_PER_KM" and s.target_low:
                    target_ms = 1000.0 / s.target_low
                elif s.target_type == "PACE_PER_100M" and s.target_low:
                    target_ms = 100.0 / s.target_low
                elif s.target_type == "SPEED" and s.target_low:
                    target_ms = s.target_low
                step_sec = s.duration_value / target_ms if target_ms > 0 else 0

            step_sec_total = step_sec * repeat
            dur_sec += step_sec_total

            # TSS por step: (seg * NP / FTP)^2 / 3600 * 100
            avg_power = 0.0
            if s.target_type in ("POWER",) and s.target_low:
                avg_power = (s.target_low + (s.target_high or s.target_low)) / 2
            elif s.target_type == "POWER_PCT_FTP" and s.target_low:
                avg_pct = (s.target_low + (s.target_high or s.target_low)) / 2
                avg_power = avg_pct / 100.0 * athlete.ftp_watts

            if avg_power > 0 and athlete.ftp_watts > 0:
                intensity_factor = avg_power / athlete.ftp_watts
                step_tss = (step_sec_total * avg_power * intensity_factor) \
                           / (athlete.ftp_watts * 3600) * 100
                tss += step_tss

            # kcal aproximado (Mifflin-based: ~1 kcal/kg/km para run,
            # potencia efectiva para bike)
            if workout.sport == "RUNNING":
                dist_km = (step_sec_total * (s.target_low or 0)
                           if s.target_type == "PACE_PER_KM" else 0) / 1000
                kcal += int(dist_km * athlete.weight_kg * 1.04)
            elif workout.sport == "CYCLING" and avg_power > 0:
                kcal += int((avg_power * step_sec_total) / (0.23 * 4184))

    _process(workout.steps)
    return int(dur_sec), round(tss, 1), kcal
