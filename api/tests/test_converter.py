"""
Tests del módulo de conversión Garmin — sin dependencias externas.
Ejecutar: python -m pytest api/tests/test_converter.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from api.garmin_converter import (
    GarminWorkoutConverter, AthleteProfile,
    StructuredWorkout, WorkoutStep, ConversionError, UnitConverter,
)


PROFILE = AthleteProfile(
    ftp_watts=250, lthr_bpm=170, css_sec_100m=108, threshold_run_sec_km=255
)
CONV = GarminWorkoutConverter(PROFILE)


# ─────────────────────────────────────────────────────────────────────────────
# UNIT CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitConverter:
    def test_pace_per_km(self):
        # 4:15/km = 255 seg/km → 1000/255 ≈ 3.9216 m/s
        ms = UnitConverter.pace_per_km_to_ms(255)
        assert abs(ms - 3.9216) < 0.001

    def test_pace_per_100m(self):
        # 1:48/100m = 108 seg → 100/108 ≈ 0.9259 m/s
        ms = UnitConverter.pace_per_100m_to_ms(108)
        assert abs(ms - 0.9259) < 0.001

    def test_pct_ftp(self):
        assert UnitConverter.pct_ftp_to_watts(80, 250) == 200.0
        assert UnitConverter.pct_ftp_to_watts(105, 250) == 262.5

    def test_pct_lthr(self):
        assert UnitConverter.pct_lthr_to_bpm(90, 170) == 153.0

    def test_invalid_pace(self):
        with pytest.raises(ValueError):
            UnitConverter.pace_per_km_to_ms(0)


# ─────────────────────────────────────────────────────────────────────────────
# WORKOUT CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

def make_workout(sport: str, steps: list[WorkoutStep]) -> StructuredWorkout:
    return StructuredWorkout(id="test-id", name="Test WO", sport=sport, steps=steps)


class TestRunningConversion:
    def test_basic_run_with_pace_target(self):
        wo = make_workout("RUNNING", [
            WorkoutStep(1, "WARMUP",   "TIME", 600,  "OPEN"),
            WorkoutStep(2, "INTERVAL", "DISTANCE", 1000, "PACE_PER_KM", 240, 260),
            WorkoutStep(3, "COOLDOWN", "TIME", 600,  "OPEN"),
        ])
        result = CONV.convert(wo)
        assert result["sport"] == "RUNNING"
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 3
        assert steps[0]["stepType"] == "WarmUp"
        assert steps[0]["durationType"] == "Time"
        assert steps[0]["durationValue"] == 600

        # Interval: PACE_PER_KM → Speed target
        iv = steps[1]
        assert iv["targetType"] == "Speed"
        # 260 seg/km → 3.846 m/s (slow end); 240 → 4.167 m/s (fast end)
        assert abs(iv["targetValueLow"]  - 3.846) < 0.01   # más lento
        assert abs(iv["targetValueHigh"] - 4.167) < 0.01   # más rápido

    def test_repeat_block(self):
        wo = make_workout("RUNNING", [
            WorkoutStep(1, "WARMUP", "TIME", 600, "OPEN"),
            WorkoutStep(2, "REPEAT", "OPEN", None, "OPEN",
                        repeat_count=5,
                        child_steps=[
                            WorkoutStep(1, "INTERVAL", "DISTANCE", 1000, "PACE_PER_KM", 235, 245),
                            WorkoutStep(2, "RECOVERY", "TIME", 90, "OPEN"),
                        ]),
            WorkoutStep(3, "COOLDOWN", "TIME", 300, "OPEN"),
        ])
        result = CONV.convert(wo)
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert steps[1]["stepType"] == "Repeat"
        assert steps[1]["repeatValue"] == 5
        assert len(steps[1]["workoutSteps"]) == 2


class TestCyclingConversion:
    def test_power_pct_ftp(self):
        wo = make_workout("CYCLING", [
            WorkoutStep(1, "WARMUP",   "TIME", 900, "OPEN"),
            WorkoutStep(2, "INTERVAL", "TIME", 300, "POWER_PCT_FTP", 90, 100),
            WorkoutStep(3, "RECOVERY", "TIME", 120, "POWER_PCT_FTP", 45, 55),
            WorkoutStep(4, "COOLDOWN", "TIME", 600, "OPEN"),
        ])
        result = CONV.convert(wo)
        iv = result["workoutSegments"][0]["workoutSteps"][1]
        assert iv["targetType"] == "Power"
        # 90%FTP=225W, 100%FTP=250W
        assert iv["targetValueLow"]  == 225
        assert iv["targetValueHigh"] == 250

    def test_absolute_power(self):
        wo = make_workout("CYCLING", [
            WorkoutStep(1, "INTERVAL", "TIME", 600, "POWER", 180, 220),
        ])
        result = CONV.convert(wo)
        iv = result["workoutSegments"][0]["workoutSteps"][0]
        assert iv["targetType"] == "Power"
        assert iv["targetValueLow"]  == 180
        assert iv["targetValueHigh"] == 220

    def test_heart_rate_target(self):
        wo = make_workout("CYCLING", [
            WorkoutStep(1, "ACTIVE", "TIME", 1800, "HEART_RATE", 130, 145),
        ])
        result = CONV.convert(wo)
        iv = result["workoutSegments"][0]["workoutSteps"][0]
        assert iv["targetType"] == "HeartRate"
        assert iv["targetValueLow"]  == 130
        assert iv["targetValueHigh"] == 145


class TestSwimmingConversion:
    def test_css_based_pace(self):
        # CSS = 108 seg/100m; objetivo 95-105% CSS
        wo = make_workout("SWIMMING", [
            WorkoutStep(1, "WARMUP",   "DISTANCE", 400, "OPEN"),
            WorkoutStep(2, "INTERVAL", "DISTANCE", 200, "PACE_PER_100M", 100, 115),
            WorkoutStep(3, "COOLDOWN", "DISTANCE", 200, "OPEN"),
        ])
        result = CONV.convert(wo)
        assert result["sport"] == "LAP_SWIMMING"
        iv = result["workoutSegments"][0]["workoutSteps"][1]
        assert iv["targetType"] == "Speed"
        # 100 seg/100m = 1.0 m/s; 115 seg/100m ≈ 0.8696 m/s
        assert abs(iv["targetValueLow"]  - 0.8696) < 0.01   # más lento
        assert abs(iv["targetValueHigh"] - 1.0)    < 0.01   # más rápido


class TestValidation:
    def test_invalid_sport(self):
        wo = make_workout("TRIATHLON", [WorkoutStep(1, "WARMUP", "TIME", 600, "OPEN")])
        with pytest.raises(ConversionError, match="Deporte no soportado"):
            CONV.convert(wo)

    def test_repeat_without_children(self):
        wo = make_workout("RUNNING", [
            WorkoutStep(1, "REPEAT", "OPEN", None, "OPEN", repeat_count=4),
        ])
        with pytest.raises(ConversionError):
            CONV.convert(wo)

    def test_repeat_without_count(self):
        wo = make_workout("RUNNING", [
            WorkoutStep(1, "REPEAT", "OPEN", None, "OPEN",
                        child_steps=[WorkoutStep(1, "INTERVAL", "TIME", 60, "OPEN")]),
        ])
        with pytest.raises(ConversionError):
            CONV.convert(wo)

    def test_duration_requires_value(self):
        wo = make_workout("RUNNING", [
            WorkoutStep(1, "WARMUP", "TIME", None, "OPEN"),  # duration_value=None
        ])
        with pytest.raises(ConversionError):
            CONV.convert(wo)


class TestWorkoutMeta:
    def test_name_truncated_at_100_chars(self):
        wo = make_workout("RUNNING", [WorkoutStep(1, "WARMUP", "TIME", 300, "OPEN")])
        wo.name = "A" * 150
        result = CONV.convert(wo)
        assert len(result["workoutName"]) == 100

    def test_estimated_duration_included(self):
        wo = make_workout("CYCLING", [WorkoutStep(1, "ACTIVE", "TIME", 3600, "POWER", 180, 220)])
        wo.estimated_duration_sec = 3600
        result = CONV.convert(wo)
        assert result["estimatedDurationInSecs"] == 3600

    def test_source_id_matches_workout_id(self):
        wo = make_workout("RUNNING", [WorkoutStep(1, "WARMUP", "TIME", 300, "OPEN")])
        result = CONV.convert(wo)
        assert result["workoutSourceId"] == wo.id
