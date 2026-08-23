"""
Gestión de Equipamiento y Mantenimiento — CRUD de zapatillas, bicicletas y
componentes. Ver propuesta de diseño completa (artifact publicado
2026-08-22, memoria project-labx-gear-module-design).

La lógica de asignación automática (assign_gear) vive en
api/services/gear_service.py (Sprint 3) -- este archivo es solo CRUD +
lectura agregada para dashboards.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    User, CoachAthlete, RunningShoe, Bike, BikeComponent, MaintenanceLog,
    GarminActivity, ShoeActivityLink,
)
from ..services.gear_service import life_pct as _life_pct, reassign_shoe, backfill_shoe

router = APIRouter(prefix="/gear", tags=["gear"])

_SHOE_TYPES = {"rodaje", "series", "competicion", "trail", "otro"}
_BIKE_TYPES = {"ruta", "tt_triatlon", "mtb", "gravel"}
_COMPONENT_TYPES = {
    "cadena", "cubiertas", "pastillas_freno", "discos_freno",
    "bateria_grupo", "suspension", "sellante_tubeless", "otro",
}
_TRACKING_UNITS = {"km", "horas", "meses", "carga_pct"}
_DEFAULT_TARGET_KM = {"rodaje": 700.0, "series": 500.0, "competicion": 300.0, "trail": 600.0, "otro": 700.0}
_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _shoe_out(s: RunningShoe) -> dict:
    return {
        "id": s.id, "brand": s.brand, "model": s.model, "nickname": s.nickname,
        "shoe_type": s.shoe_type, "purchase_date": s.purchase_date.isoformat() if s.purchase_date else None,
        "target_km": s.target_km, "accumulated_km": round(s.accumulated_km, 1),
        "life_pct": _life_pct(s.accumulated_km, s.target_km),
        "default_for": json.loads(s.default_for_json) if s.default_for_json else [],
        "schedule_days": json.loads(s.schedule_days_json) if s.schedule_days_json else [],
        "tracking_start_date": s.tracking_start_date.isoformat() if s.tracking_start_date else None,
        "status": s.status,
    }


def _component_out(c: BikeComponent) -> dict:
    return {
        "id": c.id, "component_type": c.component_type, "label": c.label,
        "tracking_unit": c.tracking_unit, "target_value": c.target_value,
        "accumulated_value": round(c.accumulated_value, 1),
        "life_pct": None if c.tracking_unit == "carga_pct" else _life_pct(c.accumulated_value, c.target_value),
        "charge_pct": c.charge_pct,
        "installed_date": c.installed_date.isoformat() if c.installed_date else None,
        "last_service_date": c.last_service_date.isoformat() if c.last_service_date else None,
        "status": c.status,
    }


def _bike_out(b: Bike, db: Session) -> dict:
    components = db.query(BikeComponent).filter(BikeComponent.bike_id == b.id, BikeComponent.status == "active").all()
    return {
        "id": b.id, "brand": b.brand, "model": b.model, "bike_type": b.bike_type,
        "is_default": b.is_default, "status": b.status,
        "components": [_component_out(c) for c in components],
    }


# ── Zapatillas ────────────────────────────────────────────────────────────

@router.get("/shoes")
def list_shoes(status: str = "active", db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    q = db.query(RunningShoe).filter(RunningShoe.user_id == me.id)
    if status in ("active", "retired"):
        q = q.filter(RunningShoe.status == status)
    shoes = q.order_by(RunningShoe.created_at.desc()).all()
    return {"shoes": [_shoe_out(s) for s in shoes]}


@router.post("/shoes")
def create_shoe(body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    brand = (body.get("brand") or "").strip()
    model = (body.get("model") or "").strip()
    if not brand or not model:
        raise HTTPException(400, "brand y model son obligatorios")
    shoe_type = body.get("shoe_type") or "rodaje"
    if shoe_type not in _SHOE_TYPES:
        raise HTTPException(400, f"shoe_type inválido, debe ser uno de: {sorted(_SHOE_TYPES)}")
    purchase_date = None
    if body.get("purchase_date"):
        try:
            purchase_date = date.fromisoformat(body["purchase_date"])
        except ValueError:
            raise HTTPException(400, "purchase_date debe ser YYYY-MM-DD")
    target_km = body.get("target_km")
    if target_km is not None:
        try:
            target_km = float(target_km)
        except (TypeError, ValueError):
            raise HTTPException(400, "target_km debe ser numérico")
    tracking_start_date = None
    if body.get("tracking_start_date"):
        try:
            tracking_start_date = date.fromisoformat(body["tracking_start_date"])
        except ValueError:
            raise HTTPException(400, "tracking_start_date debe ser YYYY-MM-DD")
    shoe = RunningShoe(
        user_id=me.id, brand=brand, model=model, nickname=body.get("nickname"),
        purchase_date=purchase_date, shoe_type=shoe_type,
        target_km=target_km if target_km else _DEFAULT_TARGET_KM.get(shoe_type, 700.0),
        tracking_start_date=tracking_start_date,
    )
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    return _shoe_out(shoe)


@router.patch("/shoes/{shoe_id}")
def update_shoe(shoe_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    shoe = db.query(RunningShoe).filter(RunningShoe.id == shoe_id, RunningShoe.user_id == me.id).first()
    if not shoe:
        raise HTTPException(404, "Zapatilla no encontrada")
    for field in ("brand", "model", "nickname"):
        if field in body:
            setattr(shoe, field, body[field])
    if "shoe_type" in body:
        if body["shoe_type"] not in _SHOE_TYPES:
            raise HTTPException(400, f"shoe_type inválido, debe ser uno de: {sorted(_SHOE_TYPES)}")
        shoe.shoe_type = body["shoe_type"]
    if "target_km" in body:
        try:
            shoe.target_km = float(body["target_km"])
        except (TypeError, ValueError):
            raise HTTPException(400, "target_km debe ser numérico")
    if "tracking_start_date" in body:
        if body["tracking_start_date"]:
            try:
                shoe.tracking_start_date = date.fromisoformat(body["tracking_start_date"])
            except ValueError:
                raise HTTPException(400, "tracking_start_date debe ser YYYY-MM-DD")
        else:
            shoe.tracking_start_date = None
    if "status" in body:
        if body["status"] not in ("active", "retired"):
            raise HTTPException(400, "status debe ser active|retired")
        shoe.status = body["status"]
    shoe.updated_at = _now()
    db.commit()
    db.refresh(shoe)
    return _shoe_out(shoe)


@router.delete("/shoes/{shoe_id}")
def retire_shoe(shoe_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Soft-delete: marca como retirada, nunca borra el historial real de km."""
    shoe = db.query(RunningShoe).filter(RunningShoe.id == shoe_id, RunningShoe.user_id == me.id).first()
    if not shoe:
        raise HTTPException(404, "Zapatilla no encontrada")
    shoe.status = "retired"
    shoe.updated_at = _now()
    db.commit()
    return {"ok": True}


@router.post("/shoes/{shoe_id}/set-default")
def set_default_shoe(shoe_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Marca esta zapatilla como predeterminada para un shoe_type -- le
    quita esa marca a cualquier otra zapatilla del usuario que la tuviera
    (solo UNA zapatilla puede ser default por tipo)."""
    workout_subtype = body.get("workout_subtype")
    if workout_subtype not in _SHOE_TYPES:
        raise HTTPException(400, f"workout_subtype inválido, debe ser uno de: {sorted(_SHOE_TYPES)}")
    shoe = db.query(RunningShoe).filter(RunningShoe.id == shoe_id, RunningShoe.user_id == me.id).first()
    if not shoe:
        raise HTTPException(404, "Zapatilla no encontrada")

    others = db.query(RunningShoe).filter(
        RunningShoe.user_id == me.id, RunningShoe.id != shoe_id,
    ).all()
    for other in others:
        types = json.loads(other.default_for_json) if other.default_for_json else []
        if workout_subtype in types:
            types.remove(workout_subtype)
            other.default_for_json = json.dumps(types)

    my_types = json.loads(shoe.default_for_json) if shoe.default_for_json else []
    if workout_subtype not in my_types:
        my_types.append(workout_subtype)
    shoe.default_for_json = json.dumps(my_types)
    db.commit()
    db.refresh(shoe)
    return _shoe_out(shoe)


@router.patch("/shoes/{shoe_id}/schedule")
def set_shoe_schedule(shoe_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Define qué días de semana se corre con esta zapatilla (ej. lunes/
    miércoles/viernes) -- tiene prioridad sobre el default por tipo al
    sincronizar. Un día solo puede pertenecer a UNA zapatilla: se lo quita
    a cualquier otra que lo tuviera."""
    days = body.get("days")
    if not isinstance(days, list) or any(d not in _WEEKDAYS for d in days):
        raise HTTPException(400, f"days debe ser una lista de: {sorted(_WEEKDAYS)}")
    shoe = db.query(RunningShoe).filter(RunningShoe.id == shoe_id, RunningShoe.user_id == me.id).first()
    if not shoe:
        raise HTTPException(404, "Zapatilla no encontrada")

    others = db.query(RunningShoe).filter(
        RunningShoe.user_id == me.id, RunningShoe.id != shoe_id,
    ).all()
    for other in others:
        other_days = json.loads(other.schedule_days_json) if other.schedule_days_json else []
        remaining = [d for d in other_days if d not in days]
        if remaining != other_days:
            other.schedule_days_json = json.dumps(remaining)

    shoe.schedule_days_json = json.dumps(days)
    db.commit()
    db.refresh(shoe)
    return _shoe_out(shoe)


@router.post("/shoes/{shoe_id}/backfill")
def backfill_shoe_km(shoe_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Recalcula retroactivamente el km de esta zapatilla desde una fecha
    de inicio (parámetro o shoe.tracking_start_date) -- solo llena
    actividades SIN zapatilla asignada todavía, nunca sobrescribe una
    asignación (automática o manual) previa."""
    shoe = db.query(RunningShoe).filter(RunningShoe.id == shoe_id, RunningShoe.user_id == me.id).first()
    if not shoe:
        raise HTTPException(404, "Zapatilla no encontrada")

    start_date_raw = body.get("start_date")
    if start_date_raw:
        try:
            date.fromisoformat(start_date_raw)
        except ValueError:
            raise HTTPException(400, "start_date debe ser YYYY-MM-DD")
        shoe.tracking_start_date = date.fromisoformat(start_date_raw)
    elif shoe.tracking_start_date:
        start_date_raw = shoe.tracking_start_date.isoformat()
    else:
        raise HTTPException(400, "Debes indicar start_date o definir una fecha de inicio en la zapatilla")

    added_count, added_km = backfill_shoe(db, shoe, start_date_raw)
    db.commit()
    db.refresh(shoe)
    return {"added_count": added_count, "added_km": round(added_km, 1), "shoe": _shoe_out(shoe)}


# ── Bicicletas ────────────────────────────────────────────────────────────

@router.get("/bikes")
def list_bikes(status: str = "active", db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    q = db.query(Bike).filter(Bike.user_id == me.id)
    if status in ("active", "retired"):
        q = q.filter(Bike.status == status)
    bikes = q.order_by(Bike.created_at.desc()).all()
    return {"bikes": [_bike_out(b, db) for b in bikes]}


@router.post("/bikes")
def create_bike(body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    brand = (body.get("brand") or "").strip()
    model = (body.get("model") or "").strip()
    if not brand or not model:
        raise HTTPException(400, "brand y model son obligatorios")
    bike_type = body.get("bike_type") or "ruta"
    if bike_type not in _BIKE_TYPES:
        raise HTTPException(400, f"bike_type inválido, debe ser uno de: {sorted(_BIKE_TYPES)}")

    is_default = bool(body.get("is_default"))
    if is_default:
        db.query(Bike).filter(Bike.user_id == me.id, Bike.is_default == True).update({"is_default": False})  # noqa: E712

    bike = Bike(user_id=me.id, brand=brand, model=model, bike_type=bike_type, is_default=is_default)
    db.add(bike)
    db.commit()
    db.refresh(bike)
    return _bike_out(bike, db)


@router.patch("/bikes/{bike_id}")
def update_bike(bike_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    bike = db.query(Bike).filter(Bike.id == bike_id, Bike.user_id == me.id).first()
    if not bike:
        raise HTTPException(404, "Bicicleta no encontrada")
    for field in ("brand", "model"):
        if field in body:
            setattr(bike, field, body[field])
    if "bike_type" in body:
        if body["bike_type"] not in _BIKE_TYPES:
            raise HTTPException(400, f"bike_type inválido, debe ser uno de: {sorted(_BIKE_TYPES)}")
        bike.bike_type = body["bike_type"]
    if "is_default" in body and body["is_default"]:
        db.query(Bike).filter(Bike.user_id == me.id, Bike.id != bike_id).update({"is_default": False})
        bike.is_default = True
    if "status" in body:
        if body["status"] not in ("active", "retired"):
            raise HTTPException(400, "status debe ser active|retired")
        bike.status = body["status"]
    db.commit()
    db.refresh(bike)
    return _bike_out(bike, db)


@router.delete("/bikes/{bike_id}")
def retire_bike(bike_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    bike = db.query(Bike).filter(Bike.id == bike_id, Bike.user_id == me.id).first()
    if not bike:
        raise HTTPException(404, "Bicicleta no encontrada")
    bike.status = "retired"
    db.commit()
    return {"ok": True}


# ── Componentes de bicicleta ──────────────────────────────────────────────

@router.post("/bikes/{bike_id}/components")
def create_component(bike_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    bike = db.query(Bike).filter(Bike.id == bike_id, Bike.user_id == me.id).first()
    if not bike:
        raise HTTPException(404, "Bicicleta no encontrada")
    component_type = body.get("component_type")
    if component_type not in _COMPONENT_TYPES:
        raise HTTPException(400, f"component_type inválido, debe ser uno de: {sorted(_COMPONENT_TYPES)}")
    tracking_unit = body.get("tracking_unit") or "km"
    if tracking_unit not in _TRACKING_UNITS:
        raise HTTPException(400, f"tracking_unit inválido, debe ser uno de: {sorted(_TRACKING_UNITS)}")
    target_value = body.get("target_value")
    try:
        target_value = float(target_value)
    except (TypeError, ValueError):
        raise HTTPException(400, "target_value es obligatorio y debe ser numérico")

    installed_date = None
    if body.get("installed_date"):
        try:
            installed_date = date.fromisoformat(body["installed_date"])
        except ValueError:
            raise HTTPException(400, "installed_date debe ser YYYY-MM-DD")

    component = BikeComponent(
        bike_id=bike_id, component_type=component_type, label=body.get("label"),
        tracking_unit=tracking_unit, target_value=target_value,
        charge_pct=body.get("charge_pct") if tracking_unit == "carga_pct" else None,
        installed_date=installed_date or date.today(),
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return _component_out(component)


@router.patch("/bikes/{bike_id}/components/{component_id}")
def update_component(bike_id: str, component_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    bike = db.query(Bike).filter(Bike.id == bike_id, Bike.user_id == me.id).first()
    if not bike:
        raise HTTPException(404, "Bicicleta no encontrada")
    component = db.query(BikeComponent).filter(BikeComponent.id == component_id, BikeComponent.bike_id == bike_id).first()
    if not component:
        raise HTTPException(404, "Componente no encontrado")
    if "label" in body:
        component.label = body["label"]
    if "target_value" in body:
        try:
            component.target_value = float(body["target_value"])
        except (TypeError, ValueError):
            raise HTTPException(400, "target_value debe ser numérico")
    if "charge_pct" in body and component.tracking_unit == "carga_pct":
        component.charge_pct = body["charge_pct"]
        component.last_service_date = date.today()
    if "status" in body:
        if body["status"] not in ("active", "replaced"):
            raise HTTPException(400, "status debe ser active|replaced")
        component.status = body["status"]
    db.commit()
    db.refresh(component)
    return _component_out(component)


@router.delete("/bikes/{bike_id}/components/{component_id}")
def remove_component(bike_id: str, component_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    bike = db.query(Bike).filter(Bike.id == bike_id, Bike.user_id == me.id).first()
    if not bike:
        raise HTTPException(404, "Bicicleta no encontrada")
    component = db.query(BikeComponent).filter(BikeComponent.id == component_id, BikeComponent.bike_id == bike_id).first()
    if not component:
        raise HTTPException(404, "Componente no encontrado")
    component.status = "replaced"
    db.commit()
    return {"ok": True}


# ── Asignación manual por actividad ────────────────────────────────────────

@router.get("/activities/{activity_id}/shoe")
def get_activity_shoe(activity_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """activity_id acá es el id INTERNO de garmin_activities (campo `id`
    devuelto por /athlete/activities/{activity_id} como "id"), no el
    activity_id nativo de Garmin/Strava."""
    act = db.query(GarminActivity).filter(GarminActivity.id == activity_id, GarminActivity.user_id == me.id).first()
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == activity_id).first()
    shoe = db.query(RunningShoe).filter(RunningShoe.id == link.shoe_id).first() if link else None
    return {
        "shoe_id": shoe.id if shoe else None,
        "shoe_label": f"{shoe.brand} {shoe.model}" if shoe else None,
        "distance_km": act.dist_km,
    }


@router.post("/activities/{activity_id}/shoe")
def set_activity_shoe(activity_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Reasigna manualmente qué zapatilla se usó en esta actividad puntual
    -- distinto del default automático de assign_gear(). shoe_id=null quita
    la asignación (la actividad queda sin zapatilla)."""
    act = db.query(GarminActivity).filter(GarminActivity.id == activity_id, GarminActivity.user_id == me.id).first()
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    if act.sport != "run":
        raise HTTPException(400, "Solo actividades de carrera pueden tener zapatilla asignada")
    try:
        reassign_shoe(db, act, body.get("shoe_id"))
    except ValueError as e:
        raise HTTPException(404, str(e))
    db.commit()
    link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == activity_id).first()
    shoe = db.query(RunningShoe).filter(RunningShoe.id == link.shoe_id).first() if link else None
    return {
        "shoe_id": shoe.id if shoe else None,
        "shoe_label": f"{shoe.brand} {shoe.model}" if shoe else None,
    }


@router.post("/bikes/{bike_id}/components/{component_id}/service")
def log_service(bike_id: str, component_id: str, body: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Registra un mantenimiento real. Si resets_accumulated=True (ej. "cambié
    la cadena"), reinicia el acumulado del componente a 0 -- el kilometraje
    ya recorrido con la pieza vieja no debe seguir contando para la nueva."""
    bike = db.query(Bike).filter(Bike.id == bike_id, Bike.user_id == me.id).first()
    if not bike:
        raise HTTPException(404, "Bicicleta no encontrada")
    component = db.query(BikeComponent).filter(BikeComponent.id == component_id, BikeComponent.bike_id == bike_id).first()
    if not component:
        raise HTTPException(404, "Componente no encontrado")
    description = (body.get("description") or "").strip()
    if not description:
        raise HTTPException(400, "description es obligatoria")
    resets = bool(body.get("resets_accumulated"))

    log = MaintenanceLog(
        bike_id=bike_id, component_id=component_id,
        date_iso=body.get("date_iso") or date.today().isoformat(),
        description=description, cost=body.get("cost"), resets_accumulated=resets,
    )
    db.add(log)
    if resets:
        component.accumulated_value = 0.0
        component.last_alert_pct = None
        component.installed_date = date.today()
    component.last_service_date = date.today()
    db.commit()
    return {"ok": True, "log_id": log.id}


# ── Dashboards agregados ──────────────────────────────────────────────────

@router.get("/summary")
def gear_summary(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    shoes = db.query(RunningShoe).filter(RunningShoe.user_id == me.id, RunningShoe.status == "active").all()
    bikes = db.query(Bike).filter(Bike.user_id == me.id, Bike.status == "active").all()
    shoes_out = [_shoe_out(s) for s in shoes]
    bikes_out = [_bike_out(b, db) for b in bikes]
    alerts = [s for s in shoes_out if s["life_pct"] >= 80]
    for b in bikes_out:
        alerts += [c for c in b["components"] if c["life_pct"] is not None and c["life_pct"] >= 80]
    return {"shoes": shoes_out, "bikes": bikes_out, "alerts_count": len(alerts)}


coach_router = APIRouter(prefix="/coach", tags=["gear"])


@coach_router.get("/athletes/{athlete_id}/gear")
def coach_athlete_gear(athlete_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Vista de solo lectura del equipo de un atleta, para su coach --
    requiere una relacion CoachAthlete activa (mismo patron que el resto
    de las vistas de coach sobre atletas)."""
    rel = db.query(CoachAthlete).filter(
        CoachAthlete.coach_id == me.id, CoachAthlete.athlete_id == athlete_id, CoachAthlete.activo == True,  # noqa: E712
    ).first()
    if not rel:
        raise HTTPException(403, "No tenés una relación de coach activa con este atleta")
    shoes = db.query(RunningShoe).filter(RunningShoe.user_id == athlete_id, RunningShoe.status == "active").all()
    bikes = db.query(Bike).filter(Bike.user_id == athlete_id, Bike.status == "active").all()
    return {"shoes": [_shoe_out(s) for s in shoes], "bikes": [_bike_out(b, db) for b in bikes]}
