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

from sqlalchemy.orm import Session

from ..models import (
    GarminActivity, RunningShoe, ShoeActivityLink,
    Bike, BikeComponent, BikeActivityLink, User,
)

logger = logging.getLogger(__name__)


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


def _assign_shoe(db: Session, activity: GarminActivity) -> None:
    already = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == activity.id).first()
    if already:
        return

    dist_km = activity.dist_km or 0.0
    if dist_km <= 0:
        return

    # La sincronización real no distingue rodaje/series/competencia -- se
    # asigna a la zapatilla marcada como default para "rodaje", que es el
    # bucket general de running. Series/competición se asignan a mano
    # desde la UI cuando el atleta quiere trackear una zapatilla distinta
    # para esos casos.
    shoes = db.query(RunningShoe).filter(
        RunningShoe.user_id == activity.user_id,
        RunningShoe.status == "active",
    ).all()
    default_shoe = None
    for s in shoes:
        types = json.loads(s.default_for_json) if s.default_for_json else []
        if "rodaje" in types:
            default_shoe = s
            break
    if not default_shoe:
        return

    db.add(ShoeActivityLink(shoe_id=default_shoe.id, activity_id=activity.id, distance_km=dist_km))
    default_shoe.accumulated_km = (default_shoe.accumulated_km or 0.0) + dist_km

    def _mark(threshold: int) -> None:
        default_shoe.last_alert_pct = threshold

    label = f"{default_shoe.brand} {default_shoe.model}" + (f" ({default_shoe.nickname})" if default_shoe.nickname else "")
    _check_and_alert(
        db, activity.user_id, "shoe", label,
        default_shoe.accumulated_km, default_shoe.target_km, default_shoe.last_alert_pct, _mark,
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
