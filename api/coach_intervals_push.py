"""PUSH-INTERVALS (BUILD 378): el entreno que asigna el coach se escribe en el
calendario de intervals.icu del atleta (camino automatico unico). intervals lo
reenvia al reloj (Garmin, Wahoo, COROS, Suunto) con su "Upload planned workouts".

Reutiliza `intervals_connector.send_workout_event`. Nunca bloquea la asignacion:
cualquier fallo queda en `assigned_workouts.intervals_push_*` y el coach lo ve.

Deportes: bike/run/swim con bloques (DSL de intervals) y str (fuerza) como evento
WeightTraining con las notas como descripcion. Sin estructura => 'skipped'.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

STRUCTURED_SPORTS = ("bike", "run", "swim")
SUPPORTED_SPORTS = STRUCTURED_SPORTS + ("str",)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _set(row, status, error=None, event_id=None):
    row.intervals_push_status = status
    row.intervals_push_error = error
    row.intervals_push_at = _now()
    if event_id is not None:
        row.intervals_push_event_id = str(event_id)


def push_assignment_to_intervals(db, assignment, athlete, tpl) -> str:
    """Escribe UNA asignacion en intervals.icu y persiste el estado. Devuelve el
    estado ('ok'|'failed'|'pending'|'skipped'). No lanza."""
    from . import intervals_connector as ic
    from .volume_factor import effective_template

    try:
        tpl = effective_template(assignment, tpl)
        sport = tpl.sport
        if sport not in SUPPORTED_SPORTS:
            _set(assignment, "skipped", f"Deporte '{sport}' sin equivalente en intervals.icu")
            db.commit()
            return "skipped"

        blocks: list = []
        if sport in STRUCTURED_SPORTS:
            try:
                blocks = json.loads(tpl.blocks_json) if tpl.blocks_json else []
            except ValueError:
                blocks = []
            if not blocks:
                _set(assignment, "skipped", "La plantilla no tiene bloques estructurados")
                db.commit()
                return "skipped"

        if not ic.read_access_token(athlete):
            _set(assignment, "pending", "El atleta no tiene intervals.icu conectado")
            db.commit()
            return "pending"

        description = (tpl.notas or "") if sport == "str" else ""
        if assignment.notas:
            description = (description + "\n" + assignment.notas).strip()
        try:
            res = asyncio.run(ic.send_workout_event(
                user=athlete, name=tpl.nombre, sport=sport, blocks=blocks,
                date_iso=assignment.date_iso, description=description,
                event_id=assignment.intervals_push_event_id,
            ))
        except ic.IntervalsError as exc:
            _set(assignment, "failed", str(exc))
            db.commit()
            return "failed"
        _set(assignment, "ok", None, res.get("event_id"))
        db.commit()
        return "ok"
    except Exception as exc:  # noqa: BLE001 -- jamas romper la asignacion
        logger.warning("push intervals fallo: asignacion=%s error=%s",
                       getattr(assignment, "id", "?"), exc)
        try:
            db.rollback()
            _set(assignment, "failed", str(exc)[:300])
            db.commit()
        except Exception:  # noqa: BLE001
            pass
        return "failed"


def push_assignments_background(assignment_ids: list) -> None:
    """Corre en un hilo: sesion propia, un push por asignacion."""
    from .database import SessionLocal
    from .models import AssignedWorkout, User, WorkoutTemplate

    db = SessionLocal()
    try:
        for aid in assignment_ids:
            a = db.query(AssignedWorkout).filter(AssignedWorkout.id == aid).first()
            if not a or a.deleted_at is not None:
                continue
            tpl = db.query(WorkoutTemplate).filter(WorkoutTemplate.id == a.template_id).first()
            athlete = db.query(User).filter(User.id == a.athlete_id).first()
            if not tpl or not athlete:
                continue
            push_assignment_to_intervals(db, a, athlete, tpl)
    finally:
        db.close()
