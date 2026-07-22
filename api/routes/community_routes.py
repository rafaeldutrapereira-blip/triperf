"""
LabX Comunidad Triatlón LATAM — Routes completas (Sprint 13 / Módulo §10-11)

Endpoints:
  POST   /community/follow/{user_id}             — Seguir usuario
  DELETE /community/follow/{user_id}             — Unfollow
  GET    /community/followers                    — Mis seguidores
  GET    /community/following                    — Usuarios que sigo
  GET    /community/suggestions                  — Sugerencias de seguir

  POST   /community/posts                        — Publicar actividad / nota
  GET    /community/feed                         — Feed paginado
  GET    /community/feed/CommunityGroup/{group_id}        — Feed de grupo
  GET    /community/posts/{post_id}              — Detalle de post
  DELETE /community/posts/{post_id}              — Borrar post

  POST   /community/posts/{post_id}/kudo         — Dar kudo
  DELETE /community/posts/{post_id}/kudo         — Retirar kudo
  POST   /community/posts/{post_id}/comments     — Comentar
  GET    /community/posts/{post_id}/comments     — Listar comentarios
  DELETE /community/comments/{comment_id}        — Borrar comentario

  POST   /community/groups                       — Crear grupo
  GET    /community/groups                       — Listar grupos (search)
  GET    /community/groups/{group_id}            — Detalle grupo
  POST   /community/groups/{group_id}/join       — Unirse
  DELETE /community/groups/{group_id}/leave      — Salir
  GET    /community/groups/{group_id}/members    — Lista miembros
  GET    /community/groups/{group_id}/leaderboard — Leaderboard semanal

  POST   /community/groups/{group_id}/challenges — Crear reto
  GET    /community/groups/{group_id}/challenges — Listar retos
  GET    /community/challenges/{challenge_id}/leaderboard — Ranking reto

  GET    /community/notifications                — Mis notificaciones
  POST   /community/notifications/mark-read      — Marcar leídas
  GET    /community/notifications/count          — Contador no leídas

  GET    /community/profile/{user_id}            — Perfil público
  PATCH  /community/settings                     — Visibilidad default
  POST   /community/posts/{post_id}/share-card   — Generar imagen para compartir
"""
from __future__ import annotations

import logging
import secrets
import uuid as _uuid_mod
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, desc, and_
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import (
    User,
    Follow,
    CommunityPost,
    Kudo,
    Comment,
    CommunityGroup,
    CommunityGroupMember,
    Challenge,
    ChallengeEntry,
    CommunityNotification,
    GarminActivity,
    GarminTrainingLoad,
    RecoveryScore,
)

logger = logging.getLogger("labx.community")

router = APIRouter(prefix="/community", tags=["community"])

KUDO_TYPES = {"power", "fire", "trophy", "epic", "love"}
VISIBILITY  = {"public", "followers", "coach_only", "private"}
VISIBILITY_DEFAULT = "followers"

SPORT_ICON = {
    "swim": "🏊", "bike": "🚴", "run": "🏃",
    "strength": "💪", "brick": "⚡", "other": "🏅",
}
KUDO_EMOJI = {
    "power": "💪", "fire": "🔥", "trophy": "🏆", "epic": "😎", "love": "❤️",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(_uuid_mod.uuid4())


def _avatar_initials(name: str) -> str:
    """Iniciales de nombre + apellido para el avatar (ej. 'Rafael Dutra
    Pereira' -> 'RP'). Con un solo nombre, o vacío, cae a una sola letra."""
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _avatar_url(user) -> str | None:
    """URL de la foto de perfil real si el usuario tiene una — el frontend
    cae a la pelota con iniciales (_avatar_initials) cuando esto da None."""
    if user is not None and getattr(user, "avatar_photo_path", None):
        return f"/api/athlete/profile/avatar/{user.id}"
    return None


def _notif(
    db:        Session,
    user_id:   str,
    actor_id:  str,
    notif_type:str,
    body:      str,
    post_id:   str | None = None,
    group_id:  str | None = None,
) -> None:
    """Crea una notificación in-app y la emite por SSE si hay broker disponible."""
    if user_id == actor_id:
        return
    n = CommunityNotification(
        id         = _new_id(),
        user_id    = user_id,
        actor_id   = actor_id,
        notif_type = notif_type,
        post_id    = post_id,
        group_id   = group_id,
        body       = body[:200],
    )
    db.add(n)

    # Emitir SSE si el broker está disponible
    try:
        from ..sse_broker import broker
        if broker:
            import asyncio, json
            payload = json.dumps({"type": "community", "subtype": notif_type, "body": body})
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.ensure_future(broker.publish(user_id, payload))
            )
    except Exception:
        pass


def _serialize_post(p: CommunityPost, viewer_id: str) -> dict:
    kudos_grouped = {}
    for k in p.kudos:
        kudos_grouped.setdefault(k.kudo_type, []).append(k.user_id)

    my_kudos = [k.kudo_type for k in p.kudos if k.user_id == viewer_id]

    return {
        "id":          p.id,
        "user_id":     p.user_id,
        "author":      p.user.nombre if p.user else "—",
        "post_type":   p.post_type,
        "title":       p.title,
        "body":        p.body,
        "visibility":  p.visibility,
        "sport":       p.sport,
        "icon":        SPORT_ICON.get(p.sport or "other", "ðŸ…"),
        "dist_km":     p.dist_km,
        "dur_min":     p.dur_min,
        "tss":         p.tss,
        "ctl_day":     p.ctl_day,
        "tsb_day":     p.tsb_day,
        "rpe":         p.rpe,
        "card_image":  f"/api/community/posts/{p.id}/share-card" if p.card_image else None,
        "kudos":       {kt: len(uids) for kt, uids in kudos_grouped.items()},
        "kudos_total": sum(len(uids) for uids in kudos_grouped.values()),
        "my_kudos":    my_kudos,
        "n_comments":  len([c for c in p.comments if not c.deleted_at]),
        "created_at":  p.created_at.isoformat(),
    }


def _serialize_comment(c: Comment) -> dict:
    return {
        "id":        c.id,
        "post_id":   c.post_id,
        "user_id":   c.user_id,
        "author":    c.author.nombre if c.author else "—",
        "parent_id": c.parent_id,
        "body":      c.body if not c.deleted_at else "[eliminado]",
        "deleted":   bool(c.deleted_at),
        "created_at":c.created_at.isoformat(),
    }


def _serialize_group(g: CommunityGroup, viewer_id: str, db: Session) -> dict:
    n_members = db.query(func.count(CommunityGroupMember.id)).filter(CommunityGroupMember.group_id == g.id).scalar()
    is_member = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.group_id == g.id,
        CommunityGroupMember.user_id  == viewer_id,
    ).first() is not None
    return {
        "id":          g.id,
        "name":        g.name,
        "description": g.description,
        "sport":       g.sport,
        "level":       g.level,
        "is_private":  g.is_private,
        "city":        g.city,
        "country":     g.country,
        "n_members":   n_members,
        "is_member":   is_member,
        "owner_id":    g.owner_id,
        "invite_code": g.invite_code if is_member else None,
        "created_at":  g.created_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# § FOLLOW SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/follow/{target_user_id}", status_code=201)
def follow_user(
    target_user_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Seguir a un usuario."""
    if target_user_id == me.id:
        raise HTTPException(400, "No puedes seguirte a ti mismo")
    target = db.query(User).filter(User.id == target_user_id, User.activo == True).first()
    if not target:
        raise HTTPException(404, "Usuario no encontrado")

    existing = db.query(Follow).filter(
        Follow.follower_id == me.id,
        Follow.followed_id == target_user_id,
    ).first()
    if existing:
        return {"ok": True, "already_following": True}

    follow = Follow(id=_new_id(), follower_id=me.id, followed_id=target_user_id)
    db.add(follow)
    _notif(db, target_user_id, me.id, "follow",
           f"{me.nombre or me.email} comenzó a seguirte")
    db.commit()
    return {"ok": True, "following": target_user_id}


@router.delete("/follow/{target_user_id}")
def unfollow_user(
    target_user_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    follow = db.query(Follow).filter(
        Follow.follower_id == me.id,
        Follow.followed_id == target_user_id,
    ).first()
    if follow:
        db.delete(follow)
        db.commit()
    return {"ok": True}


@router.get("/followers")
def my_followers(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    rows = db.query(Follow).filter(Follow.followed_id == me.id).all()
    return [{"user_id": r.follower_id, "nombre": r.follower.nombre if r.follower else "—"} for r in rows]


@router.get("/following")
def my_following(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    rows = db.query(Follow).filter(Follow.follower_id == me.id).all()
    return [{"user_id": r.followed_id, "nombre": r.followed.nombre if r.followed else "—"} for r in rows]


@router.get("/suggestions")
def follow_suggestions(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Sugiere atletas: mismos grupos + atletas del mismo coach."""
    already_following = {
        r.followed_id
        for r in db.query(Follow).filter(Follow.follower_id == me.id).all()
    }
    already_following.add(me.id)

    # Compañeros de grupo
    my_group_ids = [gm.group_id for gm in db.query(CommunityGroupMember).filter(CommunityGroupMember.user_id == me.id).all()]
    candidates = []
    if my_group_ids:
        group_peers = db.query(CommunityGroupMember.user_id).filter(
            CommunityGroupMember.group_id.in_(my_group_ids),
            CommunityGroupMember.user_id.notin_(already_following),
        ).limit(10).all()
        candidates = [db.query(User).filter(User.id == r[0]).first() for r in group_peers]

    # Atletas del mismo coach
    if hasattr(me, "coach_id") and me.coach_id:
        peer_plans = []  # omitido por simplicidad; se extiende en v1.1

    result = []
    seen: set[str] = set()
    for u in candidates:
        if u and u.id not in seen:
            seen.add(u.id)
            country = getattr(u, "country_code", None)
            result.append({
                "user_id":        u.id,
                "nombre":         u.nombre or u.email,
                "avatar_initial": _avatar_initials(u.nombre or u.email),
                "avatar_url":     _avatar_url(u),
                "country_flag":   COUNTRY_FLAG.get(country or "", ""),
                "reason":         "Comparte un grupo contigo",
            })

    return result[:8]


# ─────────────────────────────────────────────────────────────────────────────
# § POSTS — FEED
# ─────────────────────────────────────────────────────────────────────────────

class _PostIn(BaseModel):
    body:       Optional[str]  = None
    visibility: str            = VISIBILITY_DEFAULT
    activity_id: Optional[str] = None   # GarminActivity.id
    post_type:  str            = "activity"   # activity | note

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v):
        if v not in VISIBILITY:
            raise ValueError(f"visibility debe ser uno de {VISIBILITY}")
        return v

    @field_validator("body")
    @classmethod
    def trim_body(cls, v):
        if v:
            v = v.strip()
            if len(v) > 1000:
                raise ValueError("body máximo 1000 caracteres")
        return v


@router.post("/posts", status_code=201)
def create_post(
    body: _PostIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Publicar actividad o nota en el feed."""
    act = None
    if body.activity_id:
        act = db.query(GarminActivity).filter(
            GarminActivity.id      == body.activity_id,
            GarminActivity.user_id == me.id,
        ).first()
        if not act:
            raise HTTPException(404, "Actividad no encontrada")

        # Traer CTL/TSB del día de la actividad
        tl = db.query(GarminTrainingLoad).filter(
            GarminTrainingLoad.user_id  == me.id,
            GarminTrainingLoad.date_iso == act.date_iso,
        ).first()

    # El feed puede haber creado ya un CommunityPost para esta actividad
    # (auto-post del sync, o _get_or_create_post_for_activity al construir
    # el feed) — reutilizarlo en vez de duplicar, si no el caption del
    # usuario queda en un post huérfano que el feed nunca vuelve a mostrar.
    post = (
        db.query(CommunityPost).filter(CommunityPost.activity_id == act.id).first()
        if act else None
    )
    if post:
        post.body       = body.body
        post.visibility = body.visibility
    else:
        post = CommunityPost(
            id         = _new_id(),
            user_id    = me.id,
            activity_id= act.id if act else None,
            post_type  = body.post_type,
            body       = body.body,
            visibility = body.visibility,
            sport      = act.sport if act else None,
            dist_km    = act.dist_km if act else None,
            dur_min    = act.dur_min if act else None,
            tss        = act.tss    if act else None,
            ctl_day    = tl.ctl     if act and tl else None,
            tsb_day    = tl.tsb     if act and tl else None,
        )
        db.add(post)
    db.commit()
    db.refresh(post)
    return _serialize_post(post, me.id)


@router.get("/feed")
def get_feed(
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=50),
    sport:    Optional[str] = Query(None),
    db:       Session       = Depends(get_db),
    me:       User          = Depends(get_current_user),
):
    """Feed paginado: posts propios + de usuarios que sigo."""
    following_ids = {
        r.followed_id
        for r in db.query(Follow).filter(Follow.follower_id == me.id).all()
    }
    following_ids.add(me.id)

    q = db.query(CommunityPost).filter(
        CommunityPost.user_id.in_(following_ids),
        or_(
            CommunityPost.visibility.in_(["public", "followers"]),
            CommunityPost.user_id == me.id,
        ),
    )
    if sport:
        q = q.filter(CommunityPost.sport == sport)

    total = q.count()
    posts = (
        q.order_by(desc(CommunityPost.created_at))
         .offset((page - 1) * per_page)
         .limit(per_page)
         .all()
    )
    return {
        "items":    [_serialize_post(p, me.id) for p in posts],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, (total + per_page - 1) // per_page),
        "has_next": page * per_page < total,
    }


@router.get("/feed/public")
def get_public_feed(
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=50),
    sport:    Optional[str] = Query(None),
    db:       Session       = Depends(get_db),
    me:       User          = Depends(get_current_user),
):
    """Feed público — para la landing y para nuevos usuarios."""
    q = db.query(CommunityPost).filter(CommunityPost.visibility == "public")
    if sport:
        q = q.filter(CommunityPost.sport == sport)
    total = q.count()
    posts = q.order_by(desc(CommunityPost.created_at)).offset((page-1)*per_page).limit(per_page).all()
    return {
        "items":    [_serialize_post(p, me.id) for p in posts],
        "total":    total,
        "page":     page,
        "has_next": page * per_page < total,
    }


@router.get("/posts/{post_id}")
def get_post(
    post_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post no encontrado")

    # Verificar visibilidad
    if post.visibility == "private" and post.user_id != me.id:
        raise HTTPException(403, "Post privado")
    if post.visibility == "coach_only" and post.user_id != me.id:
        # Verificar si soy el coach del atleta
        from ..models import TrainingPlan
        is_coach = db.query(TrainingPlan).filter(
            TrainingPlan.athlete_id == post.user_id,
            TrainingPlan.coach_id   == me.id,
        ).first() is not None
        if not is_coach:
            raise HTTPException(403, "Solo visible al coach")

    return _serialize_post(post, me.id)


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    post = db.query(CommunityPost).filter(
        CommunityPost.id      == post_id,
        CommunityPost.user_id == me.id,
    ).first()
    if not post:
        raise HTTPException(404, "Post no encontrado o no autorizado")
    db.delete(post)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § KUDOS
# ─────────────────────────────────────────────────────────────────────────────

class _KudoIn(BaseModel):
    kudo_type: str

    @field_validator("kudo_type")
    @classmethod
    def validate_type(cls, v):
        if v not in KUDO_TYPES:
            raise ValueError(f"kudo_type debe ser uno de {KUDO_TYPES}")
        return v


@router.post("/posts/{post_id}/kudo", status_code=201)
def give_kudo(
    post_id: str,
    body:    _KudoIn,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post no encontrado")

    existing = db.query(Kudo).filter(
        Kudo.post_id   == post_id,
        Kudo.user_id   == me.id,
        Kudo.kudo_type == body.kudo_type,
    ).first()
    if existing:
        raise HTTPException(409, "Ya diste este kudo")

    kudo = Kudo(id=_new_id(), post_id=post_id, user_id=me.id, kudo_type=body.kudo_type)
    db.add(kudo)

    emoji = KUDO_EMOJI.get(body.kudo_type, "👍")
    _notif(db, post.user_id, me.id, "kudo",
           f"{me.nombre or me.email} reaccionó {emoji} a tu actividad",
           post_id=post_id)
    db.commit()
    kudo_count = db.query(Kudo).filter(Kudo.post_id == post_id).count()
    return {"ok": True, "kudo_type": body.kudo_type, "kudo_count": kudo_count}


@router.delete("/posts/{post_id}/kudo")
def remove_kudo(
    post_id:   str,
    kudo_type: str = Query(...),
    db:        Session = Depends(get_db),
    me:        User    = Depends(get_current_user),
):
    kudo = db.query(Kudo).filter(
        Kudo.post_id   == post_id,
        Kudo.user_id   == me.id,
        Kudo.kudo_type == kudo_type,
    ).first()
    if kudo:
        db.delete(kudo)
        db.commit()
    kudo_count = db.query(Kudo).filter(Kudo.post_id == post_id).count()
    return {"ok": True, "kudo_count": kudo_count}


# ─────────────────────────────────────────────────────────────────────────────
# § COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

class _CommentIn(BaseModel):
    body:      str
    parent_id: Optional[str] = None

    @field_validator("body")
    @classmethod
    def validate_body(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("El comentario no puede estar vacío")
        if len(v) > 500:
            raise ValueError("Máximo 500 caracteres")
        return v


@router.post("/posts/{post_id}/comments", status_code=201)
def add_comment(
    post_id: str,
    body:    _CommentIn,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post no encontrado")

    comment = Comment(
        id        = _new_id(),
        post_id   = post_id,
        user_id   = me.id,
        parent_id = body.parent_id,
        body      = body.body,
    )
    db.add(comment)

    _notif(db, post.user_id, me.id, "comment",
           f"{me.nombre or me.email} comentó en tu actividad: \"{body.body[:60]}\"",
           post_id=post_id)
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment)


@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    comments = (
        db.query(Comment)
        .filter(Comment.post_id == post_id)
        .order_by(Comment.created_at)
        .all()
    )
    return [_serialize_comment(c) for c in comments]


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db:         Session = Depends(get_db),
    me:         User    = Depends(get_current_user),
):
    c = db.query(Comment).filter(
        Comment.id      == comment_id,
        Comment.user_id == me.id,
    ).first()
    if not c:
        raise HTTPException(404, "Comentario no encontrado o no autorizado")
    c.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § GROUPS / CLUBS
# ─────────────────────────────────────────────────────────────────────────────

class _GroupIn(BaseModel):
    name:        str
    description: Optional[str] = None
    sport:       str           = "triathlon"
    level:       str           = "open"
    is_private:  bool          = False
    city:        Optional[str] = None
    country:     Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if len(v) < 3:   raise ValueError("Nombre mínimo 3 caracteres")
        if len(v) > 60:  raise ValueError("Nombre máximo 60 caracteres")
        return v


@router.post("/groups", status_code=201)
def create_group(
    body: _GroupIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    existing = db.query(CommunityGroup).filter(CommunityGroup.name == body.name).first()
    if existing:
        raise HTTPException(409, "Ya existe un grupo con ese nombre")

    g = CommunityGroup(
        id          = _new_id(),
        owner_id    = me.id,
        name        = body.name,
        description = body.description,
        sport       = body.sport,
        level       = body.level,
        is_private  = body.is_private,
        city        = body.city,
        country     = body.country,
        invite_code = secrets.token_urlsafe(8) if body.is_private else None,
    )
    db.add(g)
    db.flush()

    member = CommunityGroupMember(id=_new_id(), group_id=g.id, user_id=me.id, role="admin")
    db.add(member)
    db.commit()
    return _serialize_group(g, me.id, db)


@router.get("/groups")
def list_groups(
    search:   Optional[str] = Query(None),
    sport:    Optional[str] = Query(None),
    mine:     bool          = Query(False),
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(20, ge=1, le=50),
    db:       Session       = Depends(get_db),
    me:       User          = Depends(get_current_user),
):
    q = db.query(CommunityGroup).filter(CommunityGroup.is_private == False)
    if mine:
        my_ids = [gm.group_id for gm in db.query(CommunityGroupMember).filter(CommunityGroupMember.user_id == me.id).all()]
        q = db.query(CommunityGroup).filter(CommunityGroup.id.in_(my_ids))
    if search:
        q = q.filter(CommunityGroup.name.ilike(f"%{search}%"))
    if sport:
        q = q.filter(CommunityGroup.sport == sport)

    total  = q.count()
    groups = q.order_by(CommunityGroup.name).offset((page-1)*per_page).limit(per_page).all()
    return {
        "items":    [_serialize_group(g, me.id, db) for g in groups],
        "total":    total,
        "page":     page,
        "has_next": page * per_page < total,
    }


@router.get("/groups/{group_id}")
def get_group(
    group_id: str,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    g = db.query(CommunityGroup).filter(CommunityGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    return _serialize_group(g, me.id, db)


@router.post("/groups/{group_id}/join")
def join_group(
    group_id:    str,
    invite_code: Optional[str] = Query(None),
    db:          Session = Depends(get_db),
    me:          User    = Depends(get_current_user),
):
    g = db.query(CommunityGroup).filter(CommunityGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    if g.is_private and g.invite_code != invite_code:
        raise HTTPException(403, "Código de invitación incorrecto")

    existing = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.group_id == group_id,
        CommunityGroupMember.user_id  == me.id,
    ).first()
    if existing:
        return {"ok": True, "already_member": True}

    member = CommunityGroupMember(id=_new_id(), group_id=group_id, user_id=me.id, role="member")
    db.add(member)
    db.commit()
    return {"ok": True, "group_id": group_id}


@router.delete("/groups/{group_id}/leave")
def leave_group(
    group_id: str,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    m = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.group_id == group_id,
        CommunityGroupMember.user_id  == me.id,
    ).first()
    if m:
        if m.role == "admin":
            raise HTTPException(400, "El admin debe transferir ownership antes de salir")
        db.delete(m)
        db.commit()
    return {"ok": True}


@router.get("/groups/{group_id}/members")
def list_members(
    group_id: str,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    g = db.query(CommunityGroup).filter(CommunityGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")

    members = db.query(CommunityGroupMember).filter(CommunityGroupMember.group_id == group_id).all()
    return [
        {
            "user_id":   m.user_id,
            "nombre":    m.user.nombre if m.user else "—",
            "rol_app":   m.user.rol if m.user else None,
            "role":      m.role,
            "joined_at": m.joined_at.isoformat(),
        }
        for m in members
    ]


@router.get("/groups/{group_id}/feed")
def group_feed(
    group_id: str,
    page:     int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    """Feed de actividades de miembros del grupo."""
    is_member = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.group_id == group_id,
        CommunityGroupMember.user_id  == me.id,
    ).first()
    g = db.query(CommunityGroup).filter(CommunityGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    if g.is_private and not is_member:
        raise HTTPException(403, "Grupo privado")

    member_ids = [gm.user_id for gm in db.query(CommunityGroupMember).filter(CommunityGroupMember.group_id == group_id).all()]
    q = db.query(CommunityPost).filter(
        CommunityPost.user_id.in_(member_ids),
        CommunityPost.visibility.in_(["public", "followers"]),
    )
    total = q.count()
    posts = q.order_by(desc(CommunityPost.created_at)).offset((page-1)*per_page).limit(per_page).all()
    return {
        "items":    [_serialize_post(p, me.id) for p in posts],
        "total":    total,
        "page":     page,
        "has_next": page * per_page < total,
    }


@router.get("/groups/{group_id}/leaderboard")
def group_leaderboard(
    group_id: str,
    metric:   str = Query("tss", pattern="^(tss|km|activities|hours)$"),
    period:   str = Query("week", pattern="^(week|month|year)$"),
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    """Leaderboard de miembros del grupo."""
    g = db.query(CommunityGroup).filter(CommunityGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")

    today = date.today()
    if period == "week":
        dow   = today.weekday()
        start = (today - timedelta(days=dow)).isoformat()
        end   = today.isoformat()
    elif period == "month":
        start = today.replace(day=1).isoformat()
        end   = today.isoformat()
    else:
        start = today.replace(month=1, day=1).isoformat()
        end   = today.isoformat()

    member_ids = [gm.user_id for gm in db.query(CommunityGroupMember).filter(CommunityGroupMember.group_id == group_id).all()]

    from ..models import GarminActivity
    board = []
    for uid in member_ids:
        acts = db.query(GarminActivity).filter(
            GarminActivity.user_id  == uid,
            GarminActivity.date_iso >= start,
            GarminActivity.date_iso <= end,
        ).all()

        if metric == "tss":
            value = round(sum(a.tss or 0 for a in acts), 1)
        elif metric == "km":
            value = round(sum(a.dist_km or 0 for a in acts), 1)
        elif metric == "activities":
            value = len(acts)
        else:  # hours
            value = round(sum(a.dur_min or 0 for a in acts) / 60, 1)

        user = db.query(User).filter(User.id == uid).first()
        if user:
            board.append({
                "user_id": uid,
                "nombre":  user.nombre or user.email,
                "value":   value,
                "is_me":   uid == me.id,
            })

    board.sort(key=lambda x: x["value"], reverse=True)
    for i, b in enumerate(board):
        b["rank"] = i + 1

    return {
        "group_id": group_id,
        "metric":   metric,
        "period":   period,
        "start":    start,
        "end":      end,
        "board":    board,
    }


# ─────────────────────────────────────────────────────────────────────────────
# § CHALLENGES — RETOS DE GRUPO
# ─────────────────────────────────────────────────────────────────────────────

class _ChallengeIn(BaseModel):
    name:        str
    description: Optional[str] = None
    metric:      str   # km | tss | activities | hours
    sport:       str   = "all"
    target:      float
    start_date:  str
    end_date:    str

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v):
        if v not in {"km", "tss", "activities", "hours"}:
            raise ValueError("metric debe ser km|tss|activities|hours")
        return v

    @field_validator("target")
    @classmethod
    def validate_target(cls, v):
        if v <= 0:
            raise ValueError("target debe ser positivo")
        return v


@router.post("/groups/{group_id}/challenges", status_code=201)
def create_challenge(
    group_id: str,
    body:     _ChallengeIn,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    is_member = db.query(CommunityGroupMember).filter(
        CommunityGroupMember.group_id == group_id,
        CommunityGroupMember.user_id  == me.id,
        CommunityGroupMember.role.in_(["admin", "coach"]),
    ).first()
    if not is_member:
        raise HTTPException(403, "Solo admin o coach pueden crear retos")

    ch = Challenge(
        id          = _new_id(),
        group_id    = group_id,
        creator_id  = me.id,
        name        = body.name,
        description = body.description,
        metric      = body.metric,
        sport       = body.sport,
        target      = body.target,
        start_date  = body.start_date,
        end_date    = body.end_date,
    )
    db.add(ch)

    # Crear entries para todos los miembros del grupo
    member_ids = [gm.user_id for gm in db.query(CommunityGroupMember).filter(CommunityGroupMember.group_id == group_id).all()]
    for uid in member_ids:
        db.add(ChallengeEntry(id=_new_id(), challenge_id=ch.id, user_id=uid))

    db.commit()
    return {"ok": True, "challenge_id": ch.id}


@router.get("/groups/{group_id}/challenges")
def list_challenges(
    group_id: str,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    chs = db.query(Challenge).filter(Challenge.group_id == group_id).order_by(desc(Challenge.created_at)).all()
    result = []
    for ch in chs:
        my_entry = db.query(ChallengeEntry).filter(
            ChallengeEntry.challenge_id == ch.id,
            ChallengeEntry.user_id      == me.id,
        ).first()
        result.append({
            "id":          ch.id,
            "name":        ch.name,
            "description": ch.description,
            "metric":      ch.metric,
            "sport":       ch.sport,
            "target":      ch.target,
            "start_date":  ch.start_date,
            "end_date":    ch.end_date,
            "is_active":   ch.is_active,
            "my_progress": my_entry.progress if my_entry else 0,
            "my_pct":      round(my_entry.progress / ch.target * 100, 1) if my_entry and ch.target else 0,
        })
    return result


@router.get("/challenges/{challenge_id}/leaderboard")
def challenge_leaderboard(
    challenge_id: str,
    db:           Session = Depends(get_db),
    me:           User    = Depends(get_current_user),
):
    """Recalcula el leaderboard del reto desde las actividades Garmin."""
    ch = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not ch:
        raise HTTPException(404, "Reto no encontrado")

    from ..models import GarminActivity

    board = []
    for entry in ch.entries:
        acts = db.query(GarminActivity).filter(
            GarminActivity.user_id  == entry.user_id,
            GarminActivity.date_iso >= ch.start_date,
            GarminActivity.date_iso <= ch.end_date,
        )
        if ch.sport != "all":
            acts = acts.filter(GarminActivity.sport == ch.sport)
        acts = acts.all()

        if ch.metric == "km":
            value = round(sum(a.dist_km or 0 for a in acts), 1)
        elif ch.metric == "tss":
            value = round(sum(a.tss or 0 for a in acts), 1)
        elif ch.metric == "activities":
            value = len(acts)
        else:  # hours
            value = round(sum(a.dur_min or 0 for a in acts) / 60, 1)

        entry.progress     = value
        entry.last_updated = datetime.now(timezone.utc).replace(tzinfo=None)

        user = db.query(User).filter(User.id == entry.user_id).first()
        board.append({
            "user_id":  entry.user_id,
            "nombre":   user.nombre if user else "—",
            "progress": value,
            "pct":      round(value / ch.target * 100, 1) if ch.target else 0,
            "is_me":    entry.user_id == me.id,
        })

    db.commit()
    board.sort(key=lambda x: x["progress"], reverse=True)
    for i, b in enumerate(board):
        b["rank"] = i + 1

    return {
        "challenge": {
            "id":      ch.id,
            "name":    ch.name,
            "metric":  ch.metric,
            "target":  ch.target,
            "end_date":ch.end_date,
        },
        "board": board,
    }


# ─────────────────────────────────────────────────────────────────────────────
# § NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/notifications")
def my_notifications(
    page:     int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    q = db.query(CommunityNotification).filter(
        CommunityNotification.user_id == me.id
    ).order_by(desc(CommunityNotification.created_at))
    total = q.count()
    notifs = q.offset((page-1)*per_page).limit(per_page).all()
    return {
        "items": [
            {
                "id":         n.id,
                "type":       n.notif_type,
                "actor":      n.actor.nombre if n.actor else "—",
                "body":       n.body,
                "post_id":    n.post_id,
                "group_id":   n.group_id,
                "read":       bool(n.read_at),
                "created_at": n.created_at.isoformat(),
            }
            for n in notifs
        ],
        "total":    total,
        "has_next": page * per_page < total,
    }


@router.get("/notifications/count")
def unread_notif_count(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    n = db.query(func.count(CommunityNotification.id)).filter(
        CommunityNotification.user_id == me.id,
        CommunityNotification.read_at.is_(None),
    ).scalar()
    return {"unread": n}


@router.post("/notifications/mark-read")
def mark_notifs_read(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.query(CommunityNotification).filter(
        CommunityNotification.user_id == me.id,
        CommunityNotification.read_at.is_(None),
    ).update({"read_at": now})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § PROFILE PÚBLICO
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profile/{user_id}")
def public_profile(
    user_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    """Perfil público de un usuario. user_id='me' → el propio usuario logueado."""
    target_id = me.id if user_id == "me" else user_id
    user = db.query(User).filter(User.id == target_id, User.activo == True).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    n_followers = db.query(func.count(Follow.id)).filter(Follow.followed_id == target_id).scalar()
    n_following = db.query(func.count(Follow.id)).filter(Follow.follower_id == target_id).scalar()
    is_following = db.query(Follow).filter(
        Follow.follower_id == me.id, Follow.followed_id == target_id
    ).first() is not None

    # Stats del año actual
    yr = date.today().year
    from ..models import GarminActivity as GA
    year_acts = db.query(GA).filter(
        GA.user_id  == target_id,
        GA.date_iso >= f"{yr}-01-01",
        GA.date_iso <= f"{yr}-12-31",
    ).all()

    # Posts públicos
    posts = (
        db.query(CommunityPost)
        .filter(
            CommunityPost.user_id    == target_id,
            CommunityPost.visibility == "public",
        )
        .order_by(desc(CommunityPost.created_at))
        .limit(10)
        .all()
    )

    country = getattr(user, "country_code", None)
    return {
        "user": {
            "id":             user.id,
            "name":           user.nombre or user.email.split("@")[0],
            "avatar_initial": _avatar_initials(user.nombre or user.email),
            "avatar_url":     _avatar_url(user),
            "country_code":   country,
            "country_flag":   COUNTRY_FLAG.get(country or "", ""),
        },
        "rol":              user.rol,
        "follower_count":   n_followers,
        "following_count":  n_following,
        "is_following":      is_following,
        "season_stats": {
            "activities": len(year_acts),
            "km":         round(sum(a.dist_km or 0 for a in year_acts), 1),
            "hours":      round(sum(a.dur_min or 0 for a in year_acts) / 60, 1),
            "tss":        round(sum(a.tss or 0 for a in year_acts), 1),
        },
        "recent_posts": [_serialize_post(p, me.id) for p in posts],
    }


# ─────────────────────────────────────────────────────────────────────────────
# § SHARE CARD — Imagen PNG para Instagram/WhatsApp
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/share-card")
def generate_share_card(
    post_id: str,
    db:      Session  = Depends(get_db),
    me:      User     = Depends(get_current_user),
):
    """
    B-23 ext: Genera imagen 1080x1080 PNG para compartir en redes sociales.
    Requiere Pillow. Si no está instalado, devuelve URL placeholder.
    """
    import os

    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post no encontrado")
    if post.user_id != me.id:
        raise HTTPException(403, "Solo el autor puede generar la tarjeta")

    card_dir = "data/activity_cards"
    os.makedirs(card_dir, exist_ok=True)
    out_path = os.path.join(card_dir, f"{post_id}.png")

    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 1080, 1080
        img  = Image.new("RGB", (W, H), color=(11, 15, 26))   # --bg
        draw = ImageDraw.Draw(img)

        # Fondo gradiente simulado (rectángulos)
        for i in range(H):
            ratio = i / H
            r = int(11  + (26  - 11)  * ratio)
            g = int(15  + (16  - 15)  * ratio)
            b = int(26  + (35  - 26)  * ratio)
            draw.rectangle([(0, i), (W, i+1)], fill=(r, g, b))

        # Franja naranja superior
        draw.rectangle([(0, 0), (W, 8)], fill=(255, 101, 53))

        # Logo
        try:
            font_big   = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 64)
            font_mid   = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 48)
            font_small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf",   32)
            font_logo  = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 40)
        except Exception:
            font_big   = ImageFont.load_default()
            font_mid   = font_big
            font_small = font_big
            font_logo  = font_big

        # Logo LabX
        draw.text((60, 40), "LabX", fill=(255, 101, 53), font=font_logo)

        # Nombre atleta
        draw.text((60, 120), me.nombre or me.email, fill=(232, 236, 244), font=font_mid)

        # Icono y deporte
        sport_line = f"{SPORT_ICON.get(post.sport or 'other', 'ðŸ…')}  {(post.sport or 'Entrenamiento').upper()}"
        draw.text((60, 200), sport_line, fill=(148, 163, 184), font=font_small)

        # Stats principales
        stats = []
        if post.dist_km:  stats.append(f"{post.dist_km} km")
        if post.dur_min:
            h = post.dur_min // 60; m = post.dur_min % 60
            stats.append(f"{h}:{m:02d}h")
        if post.tss:      stats.append(f"TSS {int(post.tss)}")
        if post.ctl_day:  stats.append(f"CTL {int(post.ctl_day)}")

        draw.text((60, 420), " · ".join(stats), fill=(232, 236, 244), font=font_big)

        # Body / caption
        if post.body:
            draw.text((60, 560), f'"{post.body[:80]}"', fill=(148, 163, 184), font=font_small)

        # Footer
        draw.text((60, H - 80), "labx.app", fill=(90, 106, 132), font=font_small)

        img.save(out_path, "PNG", optimize=True)
        post.card_image = f"{post_id}.png"
        db.commit()

    except ImportError:
        pass   # Pillow no instalado; se sigue sin imagen

    if os.path.isfile(out_path):
        with open(out_path, "rb") as f:
            data = f.read()
        return Response(content=data, media_type="image/png",
                        headers={"Cache-Control": "max-age=3600"})

    return {"card_url": f"/api/community/posts/{post_id}/share-card", "ready": False}


# ─────────────────────────────────────────────────────────────────────────────
# § SETTINGS — Visibilidad default
# ─────────────────────────────────────────────────────────────────────────────

class _SettingsIn(BaseModel):
    default_visibility: str

    @field_validator("default_visibility")
    @classmethod
    def validate_vis(cls, v):
        if v not in VISIBILITY:
            raise ValueError(f"Debe ser uno de {VISIBILITY}")
        return v


@router.patch("/settings")
def update_community_settings(
    body: _SettingsIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Actualiza configuración de privacidad por defecto del atleta."""
    if not hasattr(me, "community_visibility"):
        pass  # campo no en modelo básico — se gestiona via JSON extra si hay columna
    return {"ok": True, "default_visibility": body.default_visibility}


# ─────────────────────────────────────────────────────────────────────────────
# § 16 — IA: Smart Kudos Context + Feed Ranking
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}/ai-context")
def ai_kudo_context(
    post_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    """
    Genera contexto inteligente para el kudo:
    — detecta si fue una sesión excepcional (TSS > CTL, TSB negativo, PB implícito)
    — devuelve mensaje sugerido para comentar
    """
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post no encontrado")

    insights: list[str] = []
    kudo_suggestion = "power"

    if post.tss and post.ctl_day:
        ratio = post.tss / post.ctl_day if post.ctl_day else 0
        if ratio >= 1.5:
            insights.append(f"TSS {int(post.tss)} — {ratio:.1f}× su CTL habitual. Sesión excepcional.")
            kudo_suggestion = "epic"
        elif ratio >= 1.0:
            insights.append(f"TSS {int(post.tss)} — por encima de su CTL ({int(post.ctl_day)}). Buen esfuerzo.")
            kudo_suggestion = "fire"

    if post.tsb_day is not None and post.tsb_day < -20:
        insights.append(f"TSB en {int(post.tsb_day)}: entrenó bajo fatiga acumulada. Pura garra.")
        kudo_suggestion = "trophy"

    if post.dist_km and post.sport in ("run", "bike"):
        ref = {"run": 42.2, "bike": 180.0}
        if post.dist_km >= ref.get(post.sport, 999):
            insights.append(f"{post.dist_km} km en {post.sport} — distancia de competencia.")
            kudo_suggestion = "trophy"

    if not insights:
        insights.append("Consistencia es la clave del rendimiento.")

    author = post.user.nombre if post.user else "El atleta"
    comment = f"{author} — {insights[0]}"

    return {
        "post_id":          post_id,
        "suggested_kudo":   kudo_suggestion,
        "ai_comment":       comment,
        "insights":         insights,
    }


@router.get("/feed/ranked")
def ranked_feed(
    page:     int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    """
    Feed con ranking IA — posts ordenados por relevancia:
    score = kudos_total * 3 + n_comments * 2 + tss_normalized + recency_decay
    Favorece contenido de calidad sobre cronología pura.
    """
    following_ids = {
        r.followed_id
        for r in db.query(Follow).filter(Follow.follower_id == me.id).all()
    }
    following_ids.add(me.id)

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    posts = db.query(CommunityPost).filter(
        CommunityPost.user_id.in_(following_ids),
        CommunityPost.visibility.in_(["public", "followers"]),
        CommunityPost.created_at >= cutoff,
    ).all()

    def _score(p: CommunityPost) -> float:
        kudos = sum(len([k for k in p.kudos if k.kudo_type == kt]) for kt in KUDO_TYPES)
        comments = len([c for c in p.comments if not c.deleted_at])
        tss_norm = min((p.tss or 0) / 150.0, 2.0)
        age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - p.created_at).total_seconds() / 3600
        recency = 1.0 / (1.0 + age_h / 24.0)
        return kudos * 3 + comments * 2 + tss_norm + recency * 5

    ranked = sorted(posts, key=_score, reverse=True)
    page_posts = ranked[(page-1)*per_page: page*per_page]

    return {
        "items":    [_serialize_post(p, me.id) for p in page_posts],
        "total":    len(ranked),
        "page":     page,
        "has_next": page * per_page < len(ranked),
        "algorithm": "engagement_tss_recency_v1",
    }


@router.post("/posts/{post_id}/flag")
def flag_post(
    post_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(get_current_user),
):
    """§ 17 Security — Reportar post inapropiado."""
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post no encontrado")
    post.is_flagged = True
    post.flagged_by = me.id
    db.commit()
    logger.warning("Post flagged: post_id=%s by user=%s", post_id, me.id)
    return {"ok": True, "message": "Reporte enviado. El equipo revisará el contenido."}


# =============================================================================
# SPRINT 17 — ENRICHED ACTIVITY FEED + LATAM LEADERBOARD + SEARCH + STATS
# =============================================================================

SPORT_EMOJI_S17 = {
    "running": "🏃", "run": "🏃",
    "cycling": "🚴", "bike": "🚴", "riding": "🚴",
    "swimming": "🏊", "swim": "🏊",
    "triathlon": "🏁",
    "trail_running": "🏔️", "trail": "🏔️",
    "strength": "💪", "workout": "💪",
    "other": "⚡",
}

COUNTRY_FLAG = {
    "CL": "🇨🇱", "BR": "🇧🇷", "AR": "🇦🇷", "MX": "🇲🇽",
    "CO": "🇨🇴", "PE": "🇵🇪", "EC": "🇪🇨", "UY": "🇺🇾",
    "PY": "🇵🇾", "BO": "🇧🇴", "VE": "🇻🇪",
    "US": "🇺🇸", "ES": "🇪🇸", "PT": "🇵🇹",
}

RECOVERY_LEVEL_LABEL = {
    "optimal":  "Forma óptima",
    "good":     "Bien recuperado",
    "moderate": "Recuperación moderada",
    "low":      "Fatiga acumulada",
    "critical": "Descanso urgente",
}


def _get_or_create_post_for_activity(act, db):
    """
    El feed muestra GarminActivity, pero kudos/comentarios se guardan contra
    CommunityPost (Kudo.post_id -> community_posts.id). Sin este puente, el
    frontend mandaba el id de la actividad como si fuera un post_id y
    give_kudo() nunca encontraba el post (404 silencioso, "no guarda kudos").
    La mayoría de actividades ya tienen su post auto-creado en el sync
    (garmin_pull_service.py, actividades >=10min) — para las que no, se crea
    aquí mismo bajo demanda.
    """
    post = db.query(CommunityPost).filter(CommunityPost.activity_id == act.id).first()
    if post:
        return post
    post = CommunityPost(
        id          = _new_id(),
        user_id     = act.user_id,
        activity_id = act.id,
        post_type   = "activity",
        visibility  = "followers",
        sport       = act.sport,
        dist_km     = act.dist_km,
        dur_min     = act.dur_min,
        tss         = act.tss,
    )
    db.add(post)
    db.flush()
    return post


def _route_preview_for_activity(activity_id, max_points=40):
    """Polyline simplificada [[lat,lon],...] para mini-mapa del feed, o None si no hay track GPS."""
    from pathlib import Path
    import json as _json

    track_path = Path("data/tracks") / f"{activity_id}.json"
    if not track_path.exists():
        return None
    try:
        points = _json.loads(track_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not points or len(points) < 2:
        return None

    stride = max(1, len(points) // max_points)
    sampled = points[::stride]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return [[round(p["lat"], 5), round(p["lon"], 5)] for p in sampled if "lat" in p and "lon" in p]


def _owner_shares_route(owner) -> bool:
    """Respeta la preferencia de privacidad share_route del dueño de la
    actividad para el mini-mapa del feed (ver /athlete/community-privacy)."""
    if not owner:
        return False
    from .athlete_routes import _get_share_prefs
    return _get_share_prefs(owner)["share_route"]


def _build_activity_card_s17(act, viewer_id, db):
    owner    = db.query(User).filter_by(id=act.user_id).first()
    act_date = act.date_iso
    post     = _get_or_create_post_for_activity(act, db)
    kudo_count = db.query(Kudo).filter(Kudo.post_id == post.id).count()
    my_kudo    = db.query(Kudo).filter(Kudo.post_id == post.id, Kudo.user_id == viewer_id).first()

    rec = None
    if act_date:
        rec = db.query(RecoveryScore).filter_by(
            user_id=act.user_id, date_iso=act_date
        ).first()

    tl = None
    if act_date:
        tl = (
            db.query(GarminTrainingLoad)
            .filter_by(user_id=act.user_id, date_iso=act_date)
            .first()
        )

    sport_raw = (act.sport or "other").lower()
    sport_key = next((k for k in SPORT_EMOJI_S17 if k in sport_raw), "other")
    country   = getattr(owner, "country_code", None) if owner else None

    return {
        "id":          post.id,
        "activity_id": act.activity_id,
        "type":        "garmin_activity",
        "kudo_count":  kudo_count,
        "my_kudo":     my_kudo.kudo_type if my_kudo else None,
        "caption":     post.body,
        "user": {
            "id":             owner.id if owner else None,
            "name":           (owner.nombre or owner.email.split("@")[0]) if owner else "—",
            "avatar_initial": _avatar_initials(owner.nombre or owner.email) if owner else "?",
            "avatar_url":     _avatar_url(owner),
            "country_code":   country,
            "country_flag":   COUNTRY_FLAG.get(country or "", ""),
        },
        "sport":        sport_raw,
        "sport_emoji":  SPORT_EMOJI_S17.get(sport_key, "⚡"),
        "name":         act.name or sport_raw.capitalize(),
        "date_iso":     act_date,
        "distance_km":  round(act.dist_km or 0, 2),
        "duration_min": round(act.dur_min or 0, 1),
        "elevation_m":  act.elev_m,
        "tss":          round(act.tss, 1) if act.tss else None,
        "avg_hr":       act.avg_hr,
        "avg_pace_min_km": act.pace_str,
        "avg_power_w":  act.avg_power,
        "route_preview": (
            _route_preview_for_activity(act.activity_id)
            if act.user_id == viewer_id or _owner_shares_route(owner)
            else None
        ),
        "recovery": {
            "score":      rec.score if rec else None,
            "level":      rec.level if rec else None,
            "color":      rec.color if rec else None,
            "label":      RECOVERY_LEVEL_LABEL.get(rec.level, "") if rec else None,
            "suggestion": rec.training_suggestion if rec else None,
        },
        "training_load": {
            "ctl": round(tl.ctl, 1) if tl and tl.ctl else None,
            "tsb": round(tl.tsb, 1) if tl and tl.tsb else None,
            "atl": round(tl.atl, 1) if tl and tl.atl else None,
        },
        "is_viewer_activity": act.user_id == viewer_id,
    }


@router.get("/activity-feed")
def garmin_activity_feed(
    limit: int = Query(20, le=50),
    offset: int = Query(0, ge=0),
    sport: Optional[str] = None,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    followed_ids = [
        f.followed_id for f in
        db.query(Follow).filter_by(follower_id=me.id).all()
    ]
    feed_ids = [me.id] + followed_ids

    q = db.query(GarminActivity).filter(
        GarminActivity.user_id.in_(feed_ids),
        GarminActivity.date_iso.isnot(None),
    )
    if sport:
        q = q.filter(GarminActivity.sport.ilike(f"%{sport}%"))

    acts = (
        q.order_by(GarminActivity.date_iso.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    cards = [_build_activity_card_s17(a, me.id, db) for a in acts]
    db.commit()  # persiste cualquier CommunityPost creado on-the-fly en _get_or_create_post_for_activity
    return {
        "feed":            cards,
        "count":           len(cards),
        "following_count": len(followed_ids),
        "has_more":        len(acts) == limit,
    }


@router.get("/leaderboard")
def latam_leaderboard(
    metric:       str           = Query("tss"),
    sport:        str           = Query("all"),
    period:       str           = Query("week"),
    country_code: Optional[str] = None,
    scope:        str           = Query("social"),
    limit:        int           = Query(25, le=50),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    from datetime import date as _date
    today = _date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
    elif period == "month":
        start = today.replace(day=1)
    elif period == "year":
        start = today.replace(month=1, day=1)
    else:
        start = None
    start_iso = start.isoformat() if start else "2000-01-01"

    if scope == "social":
        followed_ids = [
            f.followed_id for f in
            db.query(Follow).filter_by(follower_id=me.id).all()
        ]
        user_ids = [me.id] + followed_ids
        users = db.query(User).filter(User.id.in_(user_ids)).all()
    elif scope == "country":
        cc = (country_code or getattr(me, "country_code", None) or "").upper()
        if not cc:
            raise HTTPException(400, "country_code required for country scope")
        users = db.query(User).filter(User.country_code == cc).all()
    else:
        users = db.query(User).limit(500).all()

    rows = []
    for u in users:
        acts_q = db.query(GarminActivity).filter(
            GarminActivity.user_id == u.id,
            GarminActivity.date_iso >= start_iso,
        )
        if sport != "all":
            acts_q = acts_q.filter(
                GarminActivity.sport.ilike(f"%{sport}%")
            )
        acts = acts_q.all()
        total = 0.0
        for a in acts:
            if metric == "tss":
                total += a.tss or 0.0
            elif metric == "distance_km":
                total += a.dist_km or 0.0
            elif metric == "elevation_m":
                total += a.elev_m or 0.0
            elif metric == "duration_h":
                total += (a.dur_min or 0) / 60
        country = getattr(u, "country_code", None)
        rows.append({
            "user": {
                "id":             u.id,
                "name":           (u.nombre or u.email.split("@")[0]),
                "avatar_initial": _avatar_initials(u.nombre or u.email),
                "avatar_url":     _avatar_url(u),
                "country_code":   country,
                "country_flag":   COUNTRY_FLAG.get(country or "", ""),
            },
            "value":          round(total, 2),
            "is_me":          u.id == me.id,
            "activity_count": len(acts),
        })

    rows.sort(key=lambda x: x["value"], reverse=True)
    rows = rows[:limit]
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    metric_labels = {
        "tss":         "TSS Total",
        "distance_km": "Km Totales",
        "elevation_m": "Elevación (m)",
        "duration_h":  "Horas de entrenamiento",
    }
    return {
        "leaderboard":    rows,
        "scope":          scope,
        "sport":          sport,
        "metric":         metric,
        "metric_label":   metric_labels.get(metric, metric),
        "period":         period,
        "period_start":   start_iso,
        "my_rank":        next((r["rank"] for r in rows if r["is_me"]), None),
        "total_athletes": len(rows),
    }


@router.get("/search")
def search_athletes_s17(
    q:     str = Query(..., min_length=2, max_length=80),
    limit: int = Query(10, le=25),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    term = f"%{q.strip()}%"
    candidates = db.query(User).filter(
        (User.nombre.ilike(term)) | (User.email.ilike(term))
    ).limit(limit + 1).all()

    following_ids = {
        f.followed_id for f in
        db.query(Follow).filter_by(follower_id=me.id).all()
    }
    results = []
    for u in candidates:
        if u.id == me.id:
            continue
        country = getattr(u, "country_code", None)
        tl = (
            db.query(GarminTrainingLoad)
            .filter_by(user_id=u.id)
            .order_by(GarminTrainingLoad.date_iso.desc())
            .first()
        )
        results.append({
            "id":             u.id,
            "name":           u.nombre or u.email.split("@")[0],
            "avatar_initial": _avatar_initials(u.nombre or u.email),
            "avatar_url":     _avatar_url(u),
            "country_code":   country,
            "country_flag":   COUNTRY_FLAG.get(country or "", ""),
            "is_following":   u.id in following_ids,
            "ctl":            round(tl.ctl, 1) if tl and tl.ctl else None,
        })
        if len(results) >= limit:
            break
    return {"results": results, "count": len(results), "query": q}


@router.get("/stats")
def my_community_stats(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    follower_count  = db.query(Follow).filter_by(followed_id=me.id).count()
    following_count = db.query(Follow).filter_by(follower_id=me.id).count()
    my_posts        = db.query(CommunityPost).filter_by(user_id=me.id).all()
    post_ids        = [p.id for p in my_posts]
    kudos_received  = (
        db.query(Kudo).filter(Kudo.post_id.in_(post_ids)).count()
        if post_ids else 0
    )
    clubs_count = db.query(CommunityGroupMember).filter_by(user_id=me.id).count()
    return {
        "follower_count":  follower_count,
        "following_count": following_count,
        "kudos_received":  kudos_received,
        "clubs_count":     clubs_count,
        "posts_count":     len(my_posts),
    }

