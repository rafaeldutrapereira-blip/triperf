from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate, GarminCredentials
from ..auth import hash_password, require_role
from ..crypto import encrypt as _enc
from ..permissions import assert_coach_owns_athlete

router = APIRouter(prefix="/admin", tags=["admin"])
_admin = require_role("admin")


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(_admin)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _=Depends(_admin)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email ya registrado")
    user = User(
        email         = body.email.lower(),
        nombre        = body.nombre,
        password_hash = hash_password(body.password),
        rol           = body.rol,
        plan_nivel    = body.plan_nivel,
    )
    db.add(user); db.commit(); db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db), _=Depends(_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate,
                db: Session = Depends(get_db), _=Depends(_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    if body.nombre     is not None: u.nombre     = body.nombre
    if body.email      is not None: u.email      = body.email.lower()
    if body.rol        is not None: u.rol        = body.rol
    if body.plan_nivel is not None: u.plan_nivel = body.plan_nivel
    if body.activo     is not None: u.activo     = body.activo
    if body.password   is not None: u.password_hash = hash_password(body.password)
    db.commit(); db.refresh(u)
    return u


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, db: Session = Depends(get_db), _=Depends(_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    u.activo = False   # soft delete
    db.commit()


@router.post("/users/{user_id}/garmin", response_model=dict)
def set_athlete_garmin(
    user_id: str,
    body: GarminCredentials,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("admin", "coach"))
):
    """Admin/coach guarda las credenciales Garmin de un atleta."""
    if me.rol == "admin":
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(404, "Usuario no encontrado")
    else:
        u = assert_coach_owns_athlete(me.id, user_id, db)
    u.garmin_email    = body.garmin_email
    u.garmin_password = _enc(body.garmin_password)
    db.commit()
    return {"ok": True, "garmin_email": body.garmin_email}
