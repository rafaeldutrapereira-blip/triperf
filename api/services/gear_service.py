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
    Bike, BikeComponent, BikeActivityLink,
)

logger = logging.getLogger(__name__)


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
        # tracking_unit == "meses": se mide por tiempo calendario desde
        # installed_date/last_service_date, no por acumulado de actividad.
