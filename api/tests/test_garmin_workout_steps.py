"""
Tests para la traducción de blocks_json a workoutSteps reales de Garmin
(Sprint C de la auditoría 2026-07-28) — garmin_connector.py.

Nota importante: estos tests verifican que el DICCIONARIO construido tiene
la forma que el esquema documentado de garminconnect.workout espera (targets
como watts absolutos, sibling de targetType, RepeatGroup para series). NO
verifican que Garmin Connect efectivamente acepte y muestre bien este
payload — eso requiere un push real contra una cuenta real, pendiente de
autorización explícita del usuario antes de ejecutarlo (afecta una cuenta
externa de verdad, no es un test que se pueda "deshacer").
"""
import json
import pytest

from garmin_connector import (
    _build_workout_body, _bike_blocks_to_garmin_steps,
    _run_blocks_to_garmin_steps, _pace_str_to_speed_range_mps,
)


FTP = 250
FCMAX = 190


class TestBikeBlocksToGarminSteps:
    def test_warmup_step_power_range_in_watts(self):
        blocks = [{"type": "warmup", "duration": 600, "power_low": 0.5, "power_high": 0.75}]
        steps = _bike_blocks_to_garmin_steps(blocks, FTP)
        d = steps[0].model_dump(exclude_none=True, mode="json")
        assert d["stepType"]["stepTypeKey"] == "warmup"
        assert d["endConditionValue"] == 600
        assert d["targetType"]["workoutTargetTypeKey"] == "power.zone"
        assert d["targetValueOne"] == 125  # 0.5 * 250
        assert d["targetValueTwo"] == 188  # round(0.75*250)
        assert "targetType" not in d["targetType"]  # no debe quedar doblemente anidado

    def test_cooldown_step_reverses_low_high(self):
        blocks = [{"type": "cooldown", "duration": 300, "power_low": 0.5, "power_high": 0.75}]
        d = _bike_blocks_to_garmin_steps(blocks, FTP)[0].model_dump(exclude_none=True, mode="json")
        assert d["stepType"]["stepTypeKey"] == "cooldown"
        assert d["targetValueOne"] == 188
        assert d["targetValueTwo"] == 125

    def test_steady_step_same_low_high(self):
        blocks = [{"type": "steady", "duration": 300, "power": 0.75}]
        d = _bike_blocks_to_garmin_steps(blocks, FTP)[0].model_dump(exclude_none=True, mode="json")
        assert d["targetValueOne"] == d["targetValueTwo"] == 188

    def test_ramp_step_uses_interval_type(self):
        blocks = [{"type": "ramp", "duration": 300, "power_low": 0.6, "power_high": 1.0}]
        d = _bike_blocks_to_garmin_steps(blocks, FTP)[0].model_dump(exclude_none=True, mode="json")
        assert d["stepType"]["stepTypeKey"] == "interval"
        assert d["targetValueOne"] == 150
        assert d["targetValueTwo"] == 250

    def test_freeride_step_has_no_target(self):
        blocks = [{"type": "freeride", "duration": 300}]
        d = _bike_blocks_to_garmin_steps(blocks, FTP)[0].model_dump(exclude_none=True, mode="json")
        assert d["targetType"]["workoutTargetTypeKey"] == "no.target"
        assert "targetValueOne" not in d

    def test_intervals_produces_repeat_group(self):
        blocks = [{"type": "intervals", "repeat": 4, "on_duration": 240, "on_power": 0.95,
                   "off_duration": 120, "off_power": 0.55}]
        steps = _bike_blocks_to_garmin_steps(blocks, FTP)
        assert len(steps) == 1
        d = steps[0].model_dump(exclude_none=True, mode="json")
        assert d["type"] == "RepeatGroupDTO"
        assert d["numberOfIterations"] == 4
        assert len(d["workoutSteps"]) == 2
        on, off = d["workoutSteps"]
        assert on["stepType"]["stepTypeKey"] == "interval"
        assert on["targetValueOne"] == on["targetValueTwo"] == round(0.95 * FTP)
        assert off["stepType"]["stepTypeKey"] == "recovery"
        assert off["targetValueOne"] == off["targetValueTwo"] == round(0.55 * FTP)

    def test_multiple_blocks_step_order_increments(self):
        blocks = [
            {"type": "warmup", "duration": 600, "power_low": 0.5, "power_high": 0.75},
            {"type": "steady", "duration": 300, "power": 0.75},
            {"type": "cooldown", "duration": 300, "power_low": 0.5, "power_high": 0.75},
        ]
        steps = _bike_blocks_to_garmin_steps(blocks, FTP)
        orders = [s.model_dump(exclude_none=True, mode="json")["stepOrder"] for s in steps]
        assert orders == [1, 2, 3]

    def test_unknown_block_type_is_skipped(self):
        blocks = [{"type": "not_a_real_type", "duration": 100}]
        assert _bike_blocks_to_garmin_steps(blocks, FTP) == []


class TestBuildWorkoutBodyStructured:
    def test_bike_with_blocks_and_ftp_uses_structured_steps(self):
        blocks = [{"type": "steady", "duration": 300, "power": 0.75}]
        session = {"name": "T", "sport": "bike", "dur_min": 5, "dist_km": 0,
                   "blocks_json": json.dumps(blocks), "ftp": FTP}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "power.zone"

    def test_bike_without_ftp_falls_back_to_generic_step(self):
        blocks = [{"type": "steady", "duration": 300, "power": 0.75}]
        session = {"name": "T", "sport": "bike", "dur_min": 5, "dist_km": 0,
                   "blocks_json": json.dumps(blocks), "ftp": None}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"

    def test_bike_without_blocks_falls_back_to_generic_step(self):
        session = {"name": "T", "sport": "bike", "dur_min": 45, "dist_km": 0, "ftp": FTP}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        assert steps[0]["endConditionValue"] == 45 * 60
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"

    def test_non_bike_sport_ignores_blocks_json(self):
        """Sprint D extendió a run (ver TestRunBlocksToGarminSteps), pero
        swim/fuerza siguen sin steps estructurados — usan el step genérico."""
        blocks = [{"type": "steady", "duration": 300, "power": 0.75}]
        session = {"name": "T", "sport": "swim", "dur_min": 30, "dist_km": 1,
                   "blocks_json": json.dumps(blocks), "ftp": FTP}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"

    def test_malformed_blocks_json_falls_back_gracefully(self):
        session = {"name": "T", "sport": "bike", "dur_min": 30, "dist_km": 0,
                   "blocks_json": "{not valid json", "ftp": FTP}
        body = _build_workout_body(session)  # no debe lanzar excepción
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"


class TestPaceStrToSpeedRange:
    def test_valid_pace_converts_to_speed_range(self):
        rng = _pace_str_to_speed_range_mps("4:00")
        assert rng is not None
        slow, fast = rng
        assert slow < fast  # más lento = menos m/s

    def test_none_or_empty_pace_returns_none(self):
        assert _pace_str_to_speed_range_mps(None) is None
        assert _pace_str_to_speed_range_mps("") is None

    def test_malformed_pace_returns_none(self):
        assert _pace_str_to_speed_range_mps("not-a-pace") is None


class TestRunBlocksToGarminSteps:
    def test_warmup_uses_hr_zone_target(self):
        blocks = [{"type": "warmup", "dur_min": 10, "zone": "Z2"}]
        steps = _run_blocks_to_garmin_steps(blocks, FCMAX)
        d = steps[0].model_dump(exclude_none=True, mode="json")
        assert d["stepType"]["stepTypeKey"] == "warmup"
        assert d["endCondition"]["conditionTypeKey"] == "time"
        assert d["endConditionValue"] == 600
        assert d["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
        assert d["targetValueOne"] < d["targetValueTwo"]

    def test_steady_with_pace_uses_pace_target(self):
        blocks = [{"type": "steady", "dur_min": 20, "pace": "5:00", "zone": "Z3"}]
        d = _run_blocks_to_garmin_steps(blocks, FCMAX)[0].model_dump(exclude_none=True, mode="json")
        assert d["targetType"]["workoutTargetTypeKey"] == "pace.zone"

    def test_steady_without_pace_falls_back_to_hr_zone(self):
        blocks = [{"type": "steady", "dur_min": 20, "pace": "", "zone": "Z3"}]
        d = _run_blocks_to_garmin_steps(blocks, FCMAX)[0].model_dump(exclude_none=True, mode="json")
        assert d["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"

    def test_intervals_produce_repeat_group_with_distance_and_recovery(self):
        blocks = [{"type": "intervals", "repeat": 6, "dist_m": 400, "pace": "3:50",
                   "rec_sec": 60, "rec_zone": "Z1"}]
        steps = _run_blocks_to_garmin_steps(blocks, FCMAX)
        assert len(steps) == 1
        d = steps[0].model_dump(exclude_none=True, mode="json")
        assert d["type"] == "RepeatGroupDTO"
        assert d["numberOfIterations"] == 6
        on, off = d["workoutSteps"]
        assert on["endCondition"]["conditionTypeKey"] == "distance"
        assert on["endConditionValue"] == 400
        assert on["targetType"]["workoutTargetTypeKey"] == "pace.zone"
        assert off["endCondition"]["conditionTypeKey"] == "time"
        assert off["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"

    def test_no_fcmax_and_no_pace_yields_no_target(self):
        blocks = [{"type": "warmup", "dur_min": 10, "zone": "Z2"}]
        d = _run_blocks_to_garmin_steps(blocks, None)[0].model_dump(exclude_none=True, mode="json")
        assert d["targetType"]["workoutTargetTypeKey"] == "no.target"


class TestBuildWorkoutBodyRun:
    def test_run_with_blocks_uses_structured_steps(self):
        blocks = [{"type": "warmup", "dur_min": 10, "zone": "Z2"}]
        session = {"name": "T", "sport": "run", "dur_min": 30, "dist_km": 5,
                   "blocks_json": json.dumps(blocks), "fcmax": FCMAX}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"

    def test_run_without_blocks_falls_back_to_generic_step(self):
        session = {"name": "T", "sport": "run", "dur_min": 30, "dist_km": 5, "fcmax": FCMAX}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"

    def test_run_malformed_blocks_json_falls_back_gracefully(self):
        session = {"name": "T", "sport": "run", "dur_min": 30, "dist_km": 5,
                   "blocks_json": "{not valid", "fcmax": FCMAX}
        body = _build_workout_body(session)
        steps = body["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"
