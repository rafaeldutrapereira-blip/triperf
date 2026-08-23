"""
Asignación automática de equipamiento (Sprint 3 del módulo "Gestión de
Equipamiento y Mantenimiento" — ver memoria project-labx-gear-module-design).

Punto de enganche ÚNICO: assign_gear() se llama después de que una
actividad de CUALQUIER marca (Garmin nativo, Strava, y a futuro Wahoo/
Polar/HealthKit) ya se normalizó a la tabla garmin_activities existente.
No conoce ni le importa el origen del dato -- solo opera sobre la fila ya
escrita, así que funciona igual para todas las marcas sin tocar cada
conector por separado.

Nunca inventa un default: si el atleta no marcó una zapatilla/bici como
predeterminada, la actividad queda sin asignar (visible luego en el
resumen de equipamiento como "sin asignar" -- no se le adivina un equipo).
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from ..models import (
    GarminActivity, RunningShoe, ShoeActivityLink,
    Bike, BikeComponent, BikeActivityLink, User,
)

logger = logging.getLogger(__name__)

_WEEKDAY_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def life_pct(accumulated: float, target: float) -> float:
    if not target:
        return 0.0
    return round(min(200.0, (accumulated / target) * 100), 1)


def _check_and_alert(db: Session, user_id: str, gear_kind: str, label: str,
                      accumulated: float, target: float, last_alert_pct: int | None,
                      mark_fn) -> None:
    """Dispara alerta (email + push) la PRIMERA vez que el equipo cruza 80%
    o 100% de vida útil -- usa last_alert_pct para no reenviar en cada
    sync. mark_fn(threshold) persiste el nuevo umbral en la fila real."""
    pct = life_pct(accumulated, target)
    threshold = None
    if pct >= 100 and (last_alert_pct or 0) < 100:
        threshold = 100
    elif pct >= 80 and (last_alert_pct or 0) < 80:
        threshold = 80
    if threshold is None:
        return

    mark_fn(threshold)
    try:
        _notify_gear_threshold(db, user_id, gear_kind, label, pct, threshold)
    except Exception as exc:
        logger.warning("Alerta de equipamiento falló (no bloqueante) user=%s gear=%s: %s", user_id, label, exc)


def _notify_gear_threshold(db: Session, user_id: str, gear_kind: str, label: str,
                            pct: float, threshold: int) -> None:
    from .. import mailer
    from ..routes.notification_routes import send_push_to_user

    user = db.query(User).filter(User.id == user_id).first()
    if user and user.email:
        mailer.send_gear_alert(user.email, user.nombre or "", label, gear_kind, pct, threshold)
    send_push_to_user(user_id, push_gear_alert_payload(label, gear_kind, pct, threshold), db)


def push_gear_alert_payload(label: str, gear_kind: str, pct: float, threshold: int) -> dict:
    from .notification_service import push_gear_alert
    return push_gear_alert(label, gear_kind, pct, threshold)


def assign_gear(db: Session, activity: GarminActivity) -> None:
    """Asigna la actividad al equipo por defecto del atleta y acumula su
    distancia/tiempo. Idempotente: si la actividad ya tiene un link de
    equipamiento, no hace nada (evita doble conteo en re-syncs)."""
    if activity is None or not activity.sport:
        return
    if activity.sport == "run":
        _assign_shoe(db, activity)
    elif activity.sport == "bike":
        _assign_bike(db, activity)


def _resolve_shoe_for_date(db: Session, user_id: str, date_iso: str | None) -> RunningShoe | None:
    """Resuelve qué zapatilla le corresponde a una actividad de carrera de
    ESE día, para el sync automático y para el backfill retroactivo (ambos
    usan esta misma lógica, para no divergir):
    1. Prioridad: zapatilla con ese día de semana en su horario
       (schedule_days_json) -- ej. "corro con las azules lunes/miércoles/viernes".
    2. Fallback: zapatilla marcada default para "rodaje" (bucket general,
       para atletas que no configuraron un horario)."""
    shoes = db.query(RunningShoe).filter(
        RunningShoe.user_id == user_id,
        RunningShoe.status == "active",
    ).all()

    if date_iso:
        try:
            weekday = _WEEKDAY_ABBR[date.fromisoformat(date_iso).weekday()]
        except ValueError:
            weekday = None
        if weekday:
            for s in shoes:
                days = json.loads(s.schedule_days_json) if s.schedule_days_json else []
                if weekday in days:
                    return s

    for s in shoes:
        types = json.loads(s.default_for_json) if s.default_for_json else []
        if "rodaje" in types:
            return s
    return None


def _assign_shoe(db: Session, activity: GarminActivity) -> None:
    already = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == activity.id).first()
    if already:
        return

    dist_km = activity.dist_km or 0.0
    if dist_km <= 0:
        return

    shoe = _resolve_shoe_for_date(db, activity.user_id, activity.date_iso)
    if not shoe:
        return

    db.add(ShoeActivityLink(shoe_id=shoe.id, activity_id=activity.id, distance_km=dist_km))
    shoe.accumulated_km = (shoe.accumulated_km or 0.0) + dist_km

    def _mark(threshold: int) -> None:
        shoe.last_alert_pct = threshold

    label = f"{shoe.brand} {shoe.model}" + (f" ({shoe.nickname})" if shoe.nickname else "")
    _check_and_alert(
        db, activity.user_id, "shoe", label,
        shoe.accumulated_km, shoe.target_km, shoe.last_alert_pct, _mark,
    )


def backfill_shoe(db: Session, shoe: RunningShoe, start_date_iso: str, force: bool = False) -> dict:
    """Recalcula retroactivamente el km de ESTA zapatilla desde start_date_iso,
    para las actividades donde la resolución día-de-semana/default (misma
    lógica que el sync en vivo) elige a esta zapatilla:
    - force=False (default): solo llena huecos -- actividades SIN zapatilla
      asignada todavía. Nunca toca una asignación previa (automática o manual).
    - force=True: además REASIGNA actividades que ya tenían OTRA zapatilla
      asignada por el sync automático (típicamente el default "rodaje"
      genérico, asignado antes de configurar este horario) -- mueve el km
      del par viejo al nuevo. Sigue sin tocar asignaciones que YA son de
      esta misma zapatilla (no-op) y sigue sin adivinar: solo actúa donde
      la resolución actual elegiría a esta zapatilla.
    Devuelve {"added_count", "added_km", "moved_count", "moved_km"}."""
    activities = db.query(GarminActivity).filter(
        GarminActivity.user_id == shoe.user_id,
        GarminActivity.sport == "run",
        GarminActivity.date_iso >= start_date_iso,
    ).all()

    added_count = 0
    added_km = 0.0
    moved_count = 0
    moved_km = 0.0

    for act in activities:
        dist_km = act.dist_km or 0.0
        if dist_km <= 0:
            continue
        resolved = _resolve_shoe_for_date(db, shoe.user_id, act.date_iso)
        if not resolved or resolved.id != shoe.id:
            continue

        link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == act.id).first()
        if link:
            if link.shoe_id == shoe.id:
                continue  # ya asignada a esta zapatilla
            if not force:
                continue  # asignada a otra, y no se pidió forzar
            old_shoe = db.query(RunningShoe).filter(RunningShoe.id == link.shoe_id).first()
            if old_shoe:
                old_shoe.accumulated_km = max(0.0, (old_shoe.accumulated_km or 0.0) - link.distance_km)
            link.shoe_id = shoe.id
            link.distance_km = dist_km
            shoe.accumulated_km = (shoe.accumulated_km or 0.0) + dist_km
            moved_km += dist_km
            moved_count += 1
        else:
            db.add(ShoeActivityLink(shoe_id=shoe.id, activity_id=act.id, distance_km=dist_km))
            shoe.accumulated_km = (shoe.accumulated_km or 0.0) + dist_km
            added_km += dist_km
            added_count += 1

    if added_count or moved_count:
        def _mark(threshold: int) -> None:
            shoe.last_alert_pct = threshold

        label = f"{shoe.brand} {shoe.model}" + (f" ({shoe.nickname})" if shoe.nickname else "")
        _check_and_alert(
            db, shoe.user_id, "shoe", label,
            shoe.accumulated_km, shoe.target_km, shoe.last_alert_pct, _mark,
        )

    return {"added_count": added_count, "added_km": added_km, "moved_count": moved_count, "moved_km": moved_km}


def reassign_shoe(db: Session, activity: GarminActivity, new_shoe_id: str | None) -> None:
    """Reasignación MANUAL de una actividad a otra zapatilla (o a ninguna),
    disparada desde la UI de detalle de sesión -- distinto de assign_gear()
    (que solo asigna al default en el sync). Mueve el km acumulado del par
    viejo al nuevo, sin doble conteo."""
    dist_km = activity.dist_km or 0.0
    link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == activity.id).first()

    old_shoe = None
    if link:
        old_shoe = db.query(RunningShoe).filter(RunningShoe.id == link.shoe_id).first()

    if new_shoe_id is None:
        if link:
            if old_shoe:
                old_shoe.accumulated_km = max(0.0, (old_shoe.accumulated_km or 0.0) - link.distance_km)
            db.delete(link)
        return

    new_shoe = db.query(RunningShoe).filter(
        RunningShoe.id == new_shoe_id, RunningShoe.user_id == activity.user_id,
    ).first()
    if not new_shoe:
        raise ValueError("Zapatilla no encontrada")

    if link and link.shoe_id == new_shoe_id:
        return  # ya asignada a esta zapatilla, nada que hacer

    if link:
        if old_shoe:
            old_shoe.accumulated_km = max(0.0, (old_shoe.accumulated_km or 0.0) - link.distance_km)
        link.shoe_id = new_shoe_id
        link.distance_km = dist_km
    else:
        db.add(ShoeActivityLink(shoe_id=new_shoe_id, activity_id=activity.id, distance_km=dist_km))

    new_shoe.accumulated_km = (new_shoe.accumulated_km or 0.0) + dist_km

    def _mark(threshold: int) -> None:
        new_shoe.last_alert_pct = threshold

    label = f"{new_shoe.brand} {new_shoe.model}" + (f" ({new_shoe.nickname})" if new_shoe.nickname else "")
    _check_and_alert(
        db, activity.user_id, "shoe", label,
        new_shoe.accumulated_km, new_shoe.target_km, new_shoe.last_alert_pct, _mark,
    )


def _assign_bike(db: Session, activity: GarminActivity) -> None:
    already = db.query(BikeActivityLink).filter(BikeActivityLink.activity_id == activity.id).first()
    if already:
        return

    dist_km = activity.dist_km or 0.0
    dur_min = activity.dur_min or 0.0
    if dist_km <= 0 and dur_min <= 0:
        return

    bike = db.query(Bike).filter(
        Bike.user_id == activity.user_id,
        Bike.status == "active",
        Bike.is_default == True,  # noqa: E712
    ).first()
    if not bike:
        return

    db.add(BikeActivityLink(
        bike_id=bike.id, activity_id=activity.id,
        distance_km=dist_km, duration_s=dur_min * 60.0,
    ))

    # Abanica el incremento a todos los componentes activos de la bici en
    # una sola pasada -- la batería del grupo electrónico (tracking_unit=
    # "carga_pct") se salta explícitamente: no se mide por acumulado de
    # km/horas, sino por % de carga que el atleta reporta a mano al cargarla.
    components = db.query(BikeComponent).filter(
        BikeComponent.bike_id == bike.id,
        BikeComponent.status == "active",
        BikeComponent.tracking_unit != "carga_pct",
    ).all()
    for c in components:
        if c.tracking_unit == "km":
            c.accumulated_value = (c.accumulated_value or 0.0) + dist_km
        elif c.tracking_unit == "horas":
            c.accumulated_value = (c.accumulated_value or 0.0) + (dur_min / 60.0)
        else:
            # tracking_unit == "meses": se mide por tiempo calendario desde
            # installed_date/last_service_date, no por acumulado de actividad
            # -- no participa de la alerta por acumulado.
            continue

        def _mark(threshold: int, comp=c) -> None:
            comp.last_alert_pct = threshold

        label = f"{c.label or c.component_type} ({bike.brand} {bike.model})"
        _check_and_alert(
            db, activity.user_id, "component", label,
            c.accumulated_value, c.target_value, c.last_alert_pct, _mark,
        )


def get_active_gear_alerts(db: Session, user_id: str) -> list[dict]:
    """Equipo activo por encima de 80% de vida útil -- para que el Insight
    del Día (training_service.py::build_daily_insight) pueda mencionarlo.
    No incluye batería (tracking_unit=carga_pct): esa se reporta por %
    de carga, no por vida útil consumida."""
    alerts = []

    shoes = db.query(RunningShoe).filter(RunningShoe.user_id == user_id, RunningShoe.status == "active").all()
    for s in shoes:
        pct = life_pct(s.accumulated_km, s.target_km)
        if pct >= 80:
            alerts.append({
                "kind": "shoe", "label": f"{s.brand} {s.model}" + (f" ({s.nickname})" if s.nickname else ""),
                "life_pct": pct,
            })

    bikes = db.query(Bike).filter(Bike.user_id == user_id, Bike.status == "active").all()
    for b in bikes:
        components = db.query(BikeComponent).filter(
            BikeComponent.bike_id == b.id, BikeComponent.status == "active",
            BikeComponent.tracking_unit != "carga_pct",
        ).all()
        for c in components:
            pct = life_pct(c.accumulated_value, c.target_value)
            if pct >= 80:
                alerts.append({
                    "kind": "component", "label": f"{c.label or c.component_type} ({b.brand} {b.model})",
                    "life_pct": pct,
                })

    return alerts
