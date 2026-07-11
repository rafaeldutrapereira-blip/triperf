"""
Helpers de autorización — verificaciones de ownership coach/atleta.
Todas las funciones lanzan HTTPException 403/404 si la verificación falla.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Group, GroupMember, User


def assert_coach_owns_athlete(coach_id: str, athlete_id: str, db: Session) -> User:
    """
    Verifica que el atleta pertenece a algún grupo del coach.
    Lanza 404 si el atleta no existe, 403 si no pertenece al coach.
    Retorna el objeto User del atleta.
    """
    athlete = db.query(User).filter(User.id == athlete_id, User.activo == True).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Atleta no encontrado")

    # Admin puede ver cualquier atleta
    coach = db.query(User).filter(User.id == coach_id).first()
    if coach and coach.rol == "admin":
        return athlete

    # Verificar que el atleta pertenece a un grupo del coach
    membership = (
        db.query(GroupMember)
        .join(Group, Group.id == GroupMember.group_id)
        .filter(
            Group.coach_id == coach_id,
            GroupMember.athlete_id == athlete_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado: este atleta no pertenece a tus grupos",
        )
    return athlete


def assert_coach_owns_group(coach_id: str, group_id: str, db: Session) -> Group:
    """
    Verifica que el grupo pertenece al coach.
    Lanza 404 si el grupo no existe, 403 si no es del coach.
    """
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    coach = db.query(User).filter(User.id == coach_id).first()
    if coach and coach.rol == "admin":
        return group

    if group.coach_id != coach_id:
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado: este grupo no te pertenece",
        )
    return group


def get_athletes_for_coach(coach_id: str, db: Session) -> list[str]:
    """Retorna lista de athlete_ids que pertenecen a grupos del coach."""
    coach = db.query(User).filter(User.id == coach_id).first()
    if coach and coach.rol == "admin":
        return [u.id for u in db.query(User.id).filter(User.rol == "atleta", User.activo == True).all()]

    rows = (
        db.query(GroupMember.athlete_id)
        .join(Group, Group.id == GroupMember.group_id)
        .filter(Group.coach_id == coach_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]
