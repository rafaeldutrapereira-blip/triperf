"""
Workouts indoor propios del atleta (S4) -- CRUD persistido en BD.

Antes vivian solo en localStorage de indoor_workout.html. Cada workout
pertenece a un atleta; cualquier acceso a un workout ajeno responde 404
(mismo patron que gear_routes: no revela que el id existe).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import intervals_connector as ic
from ..auth import get_current_user
from ..database import get_db
from ..models import IndoorWorkout, User
from ..plan_features import require_feature

router = APIRouter(
    prefix="/athlete/indoor-workouts",
    tags=["indoor"],
    dependencies=[Depends(require_feature("indoor_workout"))],
)

_SPORTS = {"bike", "run"}  # S5: ciclismo + running (natación queda fuera de v1)
_RUN_MODES = {"pace", "hr"}
_MAX_BLOCKS = 300
_MAX_BLOCKS_BYTES = 256 * 1024
_MAX_PER_USER = 500


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _out(w: IndoorWorkout) -> dict:
    try:
        blocks = json.loads(w.blocks_json or "[]")
    except ValueError:
        blocks = []
    return {
        "id": w.id,
        "name": w.name,
        "sport": w.sport,
        "description": w.description or "",
        "planned_date": w.planned_date,
        "blocks": blocks,
        "legacy_id": w.legacy_id,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


def _clean(body: dict, partial: bool = False) -> dict:
    """Valida y normaliza el payload. Devuelve solo las claves presentes."""
    out: dict = {}
    if "name" in body or not partial:
        name = str(body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "El workout necesita un nombre")
        out["name"] = name[:120]
    if "sport" in body or not partial:
        sport = body.get("sport") or "bike"
        if sport not in _SPORTS:
            raise HTTPException(400, f"sport inválido, debe ser uno de: {sorted(_SPORTS)}")
        out["sport"] = sport
    if "description" in body:
        out["description"] = str(body.get("description") or "").strip()[:2000]
    if "planned_date" in body:
        d = body.get("planned_date") or None
        if d is not None:
            try:
                datetime.strptime(str(d), "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "planned_date debe ser YYYY-MM-DD")
            d = str(d)
        out["planned_date"] = d
    if "blocks" in body or not partial:
        blocks = body.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise HTTPException(400, "El workout necesita al menos un bloque")
        if len(blocks) > _MAX_BLOCKS or any(not isinstance(b, dict) for b in blocks):
            raise HTTPException(400, "Estructura de bloques inválida")
        raw = json.dumps(blocks, ensure_ascii=False)
        if len(raw.encode("utf-8")) > _MAX_BLOCKS_BYTES:
            raise HTTPException(400, "El workout es demasiado grande")
        out["blocks_json"] = raw
    # Running: cada bloque declara su objetivo (ritmo o FC). Se valida cuando
    # se conoce el deporte en el mismo payload (alta o PUT con sport+blocks).
    if out.get("sport") == "run" and "blocks_json" in out:
        if any(b.get("mode") not in _RUN_MODES for b in blocks):
            raise HTTPException(400, "Los bloques de running necesitan mode: 'pace' o 'hr'")
    return out


def _owned(db: Session, me: User, wid: str) -> IndoorWorkout:
    w = db.query(IndoorWorkout).filter(
        IndoorWorkout.id == wid, IndoorWorkout.user_id == me.id
    ).first()
    if not w:
        raise HTTPException(404, "Workout no encontrado")
    return w


@router.get("")
def list_workouts(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    rows = (
        db.query(IndoorWorkout)
        .filter(IndoorWorkout.user_id == me.id)
        .order_by(IndoorWorkout.updated_at.desc())
        .all()
    )
    return {"workouts": [_out(w) for w in rows]}


@router.post("")
def create_workout(body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    legacy_id: Optional[str] = body.get("legacy_id")
    if legacy_id:
        legacy_id = str(legacy_id)[:64]
        existing = db.query(IndoorWorkout).filter(
            IndoorWorkout.user_id == me.id, IndoorWorkout.legacy_id == legacy_id
        ).first()
        if existing:  # migración idempotente: repetir la carga no duplica
            return _out(existing)
    data = _clean(body)
    if db.query(IndoorWorkout).filter(IndoorWorkout.user_id == me.id).count() >= _MAX_PER_USER:
        raise HTTPException(400, "Alcanzaste el máximo de workouts guardados")
    w = IndoorWorkout(user_id=me.id, legacy_id=legacy_id or None, **data)
    db.add(w)
    db.commit()
    db.refresh(w)
    return _out(w)


@router.get("/{workout_id}")
def get_workout(workout_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return _out(_owned(db, me, workout_id))


@router.put("/{workout_id}")
def update_workout(workout_id: str, body: dict, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)):
    w = _owned(db, me, workout_id)
    for k, v in _clean(body, partial=True).items():
        setattr(w, k, v)
    w.updated_at = _now()
    db.commit()
    db.refresh(w)
    return _out(w)


@router.delete("/{workout_id}")
async def delete_workout(workout_id: str, db: Session = Depends(get_db),
                         me: User = Depends(get_current_user)):
    w = _owned(db, me, workout_id)
    event_id = w.intervals_event_id
    db.delete(w)
    db.commit()
    if event_id:  # S15: best-effort, la baja local ya esta hecha
        await ic.delete_workout_event(me, event_id)
    return {"ok": True}


@router.post("/{workout_id}/send-to-watch")
async def send_workout_to_watch(workout_id: str, body: dict | None = None,
                                db: Session = Depends(get_db),
                                me: User = Depends(get_current_user)):
    """Envia el workout al calendario del atleta en intervals.icu (S6).
    Nunca marca exito si la API externa falla; el workout local no se altera."""
    w = _owned(db, me, workout_id)
    date_iso = (body or {}).get("date") or w.planned_date
    if not date_iso:
        raise HTTPException(400, "El workout necesita una fecha planificada para enviarlo")
    try:
        blocks = json.loads(w.blocks_json or "[]")
    except ValueError:
        blocks = []
    try:
        result = await ic.send_workout_event(
            user=me, name=w.name, sport=w.sport, blocks=blocks,
            date_iso=str(date_iso), description=w.description or "",
            event_id=w.intervals_event_id,
        )
    except ic.IntervalsError as exc:
        raise HTTPException(502, str(exc))
    new_id = result.get("event_id")
    if new_id is not None and str(new_id) != (w.intervals_event_id or ""):
        w.intervals_event_id = str(new_id)
        db.commit()
    return {"ok": True, "event_id": result.get("event_id")}
