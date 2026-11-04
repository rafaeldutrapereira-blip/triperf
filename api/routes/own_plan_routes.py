"""
Plan PROPIO del atleta (CQ7, "Mi Plan") -- sesiones persistidas en BD.

Antes vivian solo en localStorage.kl_training_plan: al cambiar de dispositivo
el plan desaparecia. Este router NO toca /athlete/plan (plan asignado por el
coach / Garmin); es solo el plan que el atleta arma por su cuenta (Agregar
Sesion, "+ Mi Plan" de Indoor). Acceso a una sesion ajena = 404 (no revela
que el id existe), igual que indoor_workout_routes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import OwnPlanSession, User
from ..plan_features import require_feature

router = APIRouter(
    prefix="/athlete/own-plan",
    tags=["own-plan"],
    dependencies=[Depends(require_feature("training_plan"))],
)

_MAX_PER_USER = 5000
_MAX_IMPORT = 1000
_MAX_EXTRA_BYTES = 16 * 1024
# Claves que el servidor decide: nunca se guardan en data_json.
_RESERVED = {"id", "user_id", "created_at", "updated_at", "api_assignment_id", "duplicate"}
_COLUMNS = {"date_iso", "sport", "name", "dur_min", "dist_km", "tss", "notes",
            "indoor_workout_id"}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _num(v, as_int=False):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return int(round(f)) if as_int else f


def _out(s: OwnPlanSession) -> dict:
    try:
        extra = json.loads(s.data_json or "{}")
    except ValueError:
        extra = {}
    if not isinstance(extra, dict):
        extra = {}
    out = dict(extra)
    out.update({
        "id": s.id,
        "date_iso": s.date_iso,
        "sport": s.sport,
        "name": s.name,
        "dur_min": s.dur_min,
        "dist_km": s.dist_km,
        "tss": s.tss,
        "notes": s.notes,
        "indoor_workout_id": s.indoor_workout_id,
        "legacy_id": s.legacy_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    })
    return out


def _check_date(d) -> str:
    try:
        datetime.strptime(str(d), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date_iso debe ser YYYY-MM-DD")
    return str(d)


def _split(body: dict, partial: bool, current_extra: Optional[dict] = None):
    """Devuelve (columnas, extras). Lo que no es columna se conserva en extras."""
    if not isinstance(body, dict):
        raise HTTPException(400, "Cuerpo invalido")
    cols: dict = {}
    if "date_iso" in body or not partial:
        cols["date_iso"] = _check_date(body.get("date_iso"))
    if "name" in body or not partial:
        name = str(body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "La sesion necesita un nombre")
        cols["name"] = name[:200]
    if "sport" in body or not partial:
        cols["sport"] = str(body.get("sport") or "run")[:20]
    if "dur_min" in body:
        cols["dur_min"] = _num(body.get("dur_min"), as_int=True)
    if "dist_km" in body:
        cols["dist_km"] = _num(body.get("dist_km"))
    if "tss" in body:
        cols["tss"] = _num(body.get("tss"))
    if "notes" in body:
        n = body.get("notes")
        cols["notes"] = None if n is None else str(n)[:4000]
    if "indoor_workout_id" in body:
        i = body.get("indoor_workout_id")
        cols["indoor_workout_id"] = None if i in (None, "") else str(i)[:64]
    extra = dict(current_extra or {})
    for k, v in body.items():
        if k in _COLUMNS or k in _RESERVED or k == "legacy_id":
            continue
        if not isinstance(k, str) or len(k) > 60:
            continue
        extra[k] = v
    if len(json.dumps(extra, default=str)) > _MAX_EXTRA_BYTES:
        raise HTTPException(400, "La sesion trae demasiados datos adicionales")
    return cols, extra


def _owned(db: Session, me: User, sid: str) -> OwnPlanSession:
    s = db.query(OwnPlanSession).filter(
        OwnPlanSession.id == sid, OwnPlanSession.user_id == me.id
    ).first()
    if not s:
        raise HTTPException(404, "Sesion no encontrada")
    return s


def _create(db: Session, me: User, body: dict):
    """Crea una sesion; devuelve (sesion, creada). Idempotente por legacy_id y
    por (indoor_workout_id, date_iso) para no duplicar '+ Mi Plan'."""
    legacy_id = body.get("legacy_id")
    legacy_id = str(legacy_id)[:64] if legacy_id else None
    q = db.query(OwnPlanSession).filter(OwnPlanSession.user_id == me.id)
    if legacy_id:
        existing = q.filter(OwnPlanSession.legacy_id == legacy_id).first()
        if existing:
            return existing, False
    cols, extra = _split(body, partial=False)
    if cols.get("indoor_workout_id"):
        dup = q.filter(
            OwnPlanSession.indoor_workout_id == cols["indoor_workout_id"],
            OwnPlanSession.date_iso == cols["date_iso"],
        ).first()
        if dup:
            return dup, False
    s = OwnPlanSession(user_id=me.id, legacy_id=legacy_id,
                       data_json=json.dumps(extra, default=str), **cols)
    db.add(s)
    return s, True


@router.get("")
def list_sessions(start: Optional[str] = None, end: Optional[str] = None,
                  db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    q = db.query(OwnPlanSession).filter(OwnPlanSession.user_id == me.id)
    if start:
        q = q.filter(OwnPlanSession.date_iso >= _check_date(start))
    if end:
        q = q.filter(OwnPlanSession.date_iso <= _check_date(end))
    rows = q.order_by(OwnPlanSession.date_iso, OwnPlanSession.created_at).all()
    return {"sessions": [_out(s) for s in rows]}


@router.post("")
def create_session(body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    if db.query(OwnPlanSession).filter(OwnPlanSession.user_id == me.id).count() >= _MAX_PER_USER:
        raise HTTPException(400, "Alcanzaste el maximo de sesiones en Mi Plan")
    s, created = _create(db, me, body)
    db.commit()
    db.refresh(s)
    out = _out(s)
    out["duplicate"] = not created
    return out


@router.post("/import")
def import_sessions(body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Migracion unica desde localStorage: sube las sesiones locales. Idempotente
    (legacy_id): repetir la llamada no duplica. Devuelve cuantas se crearon."""
    items = body.get("sessions")
    if not isinstance(items, list):
        raise HTTPException(400, "sessions debe ser una lista")
    if len(items) > _MAX_IMPORT:
        raise HTTPException(400, f"Maximo {_MAX_IMPORT} sesiones por importacion")
    created = skipped = invalid = 0
    for it in items:
        if not isinstance(it, dict) or it.get("api_assignment_id"):
            invalid += 1  # las del coach (cache) no son plan propio
            continue
        it = dict(it)
        if it.get("id") and not it.get("legacy_id"):
            it["legacy_id"] = it["id"]
        try:
            _, was_created = _create(db, me, it)
            db.flush()
        except HTTPException:
            invalid += 1
            continue
        if was_created:
            created += 1
        else:
            skipped += 1
    db.commit()
    rows = (db.query(OwnPlanSession).filter(OwnPlanSession.user_id == me.id)
            .order_by(OwnPlanSession.date_iso, OwnPlanSession.created_at).all())
    return {"created": created, "skipped": skipped, "invalid": invalid,
            "sessions": [_out(s) for s in rows]}


@router.put("/{session_id}")
def update_session(session_id: str, body: dict, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)):
    s = _owned(db, me, session_id)
    try:
        cur = json.loads(s.data_json or "{}")
    except ValueError:
        cur = {}
    cols, extra = _split(body, partial=True, current_extra=cur if isinstance(cur, dict) else {})
    for k, v in cols.items():
        setattr(s, k, v)
    s.data_json = json.dumps(extra, default=str)
    s.updated_at = _now()
    db.commit()
    db.refresh(s)
    return _out(s)


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)):
    s = _owned(db, me, session_id)
    db.delete(s)
    db.commit()
    return {"ok": True}
