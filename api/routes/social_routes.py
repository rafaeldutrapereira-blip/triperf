"""
Social / Comunidad — LabX
Feed, Follows, Kudos, Comments, Discover
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..auth import get_current_user
from ..models import (
    User, WorkoutLog, AssignedWorkout,
    SocialFollow, SocialKudo, SocialComment,
)
from ..schemas import CommentCreate, KudoToggleOut, SocialStatsOut

logger = logging.getLogger("labx.social")
router = APIRouter(prefix="/social", tags=["social"])

# ── Constantes de deporte ─────────────────────────────────────────────
_SPORT_LABEL = {
    "swim": "Natación", "bike": "Ciclismo",
    "run":  "Carrera",  "str":  "Fuerza", "strength": "Fuerza",
}
_SPORT_COLOR = {
    "swim": "#22D3EE", "bike": "#FF6535",
    "run":  "#10B981", "str":  "#A855F7", "strength": "#A855F7",
}


# ── Cursor helpers ────────────────────────────────────────────────────
def _parse_cursor(cursor: Optional[str]):
    if not cursor:
        return None, None
    try:
        ts_str, lid = cursor.rsplit("_", 1)
        return datetime.fromisoformat(ts_str), lid
    except Exception:
        return None, None


def _make_cursor(log: WorkoutLog) -> str:
    return f"{log.logged_at.isoformat()}_{log.id}"


# ── Serialización batch (evita N+1) ──────────────────────────────────
def _serialize_logs(logs: list, me_id: str, db: Session) -> list:
    if not logs:
        return []

    log_ids = [l.id for l in logs]

    kudos_counts = dict(
        db.query(SocialKudo.log_id, func.count(SocialKudo.id))
        .filter(SocialKudo.log_id.in_(log_ids))
        .group_by(SocialKudo.log_id)
        .all()
    )
    my_kudos = {
        row[0] for row in
        db.query(SocialKudo.log_id)
        .filter(SocialKudo.log_id.in_(log_ids), SocialKudo.user_id == me_id)
        .all()
    }
    comment_counts = dict(
        db.query(SocialComment.log_id, func.count(SocialComment.id))
        .filter(SocialComment.log_id.in_(log_ids))
        .group_by(SocialComment.log_id)
        .all()
    )

    result = []
    for log in logs:
        tmpl = (
            log.assignment.template
            if log.assignment and log.assignment.template
            else None
        )
        sport = tmpl.sport if tmpl else "run"
        result.append({
            "log_id":        log.id,
            "logged_at":     log.logged_at,
            "sport":         sport,
            "sport_label":   _SPORT_LABEL.get(sport, sport.capitalize()),
            "sport_color":   _SPORT_COLOR.get(sport, "#FF6535"),
            "activity_name": tmpl.nombre if tmpl else "Entrenamiento",
            "dist_real":     log.dist_real,
            "dur_real":      log.dur_real,
            "tss_real":      log.tss_real,
            "rpe":           log.rpe,
            "notas":         log.notas,
            "author": {
                "id":     log.user.id,
                "nombre": log.user.nombre,
            },
            "kudos_count":    kudos_counts.get(log.id, 0),
            "my_kudo":        log.id in my_kudos,
            "comments_count": comment_counts.get(log.id, 0),
        })
    return result


# ════════════════════════════════════════════════════════════════════
# FEED
# ════════════════════════════════════════════════════════════════════
@router.get("/feed")
def get_feed(
    cursor: Optional[str] = Query(None),
    limit:  int           = Query(default=15, ge=1, le=50),
    sport:  Optional[str] = Query(None, description="swim | bike | run | str"),
    db:     Session       = Depends(get_db),
    me:     User          = Depends(get_current_user),
):
    """Feed paginado por cursor con actividades de los seguidos."""
    cursor_ts, cursor_id = _parse_cursor(cursor)

    following_sq = (
        db.query(SocialFollow.following_id)
        .filter(SocialFollow.follower_id == me.id)
        .subquery()
    )

    q = (
        db.query(WorkoutLog)
        .options(
            joinedload(WorkoutLog.user),
            joinedload(WorkoutLog.assignment).joinedload(AssignedWorkout.template),
        )
        .filter(
            WorkoutLog.user_id.in_(following_sq),
            WorkoutLog.completado == True,
        )
    )

    # Filtro opcional por deporte
    if sport:
        q = (
            q.join(WorkoutLog.assignment)
             .join(AssignedWorkout.template)
             .filter(AssignedWorkout.template.has(sport=sport))
        )

    if cursor_ts and cursor_id:
        q = q.filter(
            or_(
                WorkoutLog.logged_at < cursor_ts,
                and_(
                    WorkoutLog.logged_at == cursor_ts,
                    WorkoutLog.id < cursor_id,
                ),
            )
        )

    logs = (
        q.order_by(WorkoutLog.logged_at.desc(), WorkoutLog.id.desc())
         .limit(limit + 1)
         .all()
    )

    has_more  = len(logs) > limit
    logs      = logs[:limit]
    next_cursor = _make_cursor(logs[-1]) if (has_more and logs) else None

    return {
        "data":        _serialize_logs(logs, me.id, db),
        "next_cursor": next_cursor,
        "has_more":    has_more,
    }


# ════════════════════════════════════════════════════════════════════
# STATS PROPIAS
# ════════════════════════════════════════════════════════════════════
@router.get("/stats/me", response_model=SocialStatsOut)
def my_stats(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    following = (
        db.query(func.count(SocialFollow.following_id))
        .filter(SocialFollow.follower_id == me.id)
        .scalar() or 0
    )
    followers = (
        db.query(func.count(SocialFollow.follower_id))
        .filter(SocialFollow.following_id == me.id)
        .scalar() or 0
    )
    total_logs = (
        db.query(func.count(WorkoutLog.id))
        .filter(WorkoutLog.user_id == me.id, WorkoutLog.completado == True)
        .scalar() or 0
    )
    return {"following": following, "followers": followers, "total_logs": total_logs}


# ════════════════════════════════════════════════════════════════════
# FOLLOWS
# ════════════════════════════════════════════════════════════════════
@router.post("/follows/{user_id}", status_code=201)
def follow_user(
    user_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    if user_id == me.id:
        raise HTTPException(400, "No puedes seguirte a ti mismo")

    target = db.query(User).filter(User.id == user_id, User.activo == True).first()
    if not target:
        raise HTTPException(404, "Usuario no encontrado")

    existing = db.query(SocialFollow).filter(
        SocialFollow.follower_id  == me.id,
        SocialFollow.following_id == user_id,
    ).first()
    if existing:
        return {"ok": True, "action": "already_following"}

    db.add(SocialFollow(follower_id=me.id, following_id=user_id))
    db.commit()
    return {"ok": True, "action": "followed"}


@router.delete("/follows/{user_id}")
def unfollow_user(
    user_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    follow = db.query(SocialFollow).filter(
        SocialFollow.follower_id  == me.id,
        SocialFollow.following_id == user_id,
    ).first()
    if follow:
        db.delete(follow)
        db.commit()
    return {"ok": True, "action": "unfollowed"}


@router.get("/users/{user_id}/follow-status")
def follow_status(
    user_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    is_following = db.query(SocialFollow).filter(
        SocialFollow.follower_id  == me.id,
        SocialFollow.following_id == user_id,
    ).first() is not None

    followers = (
        db.query(func.count(SocialFollow.follower_id))
        .filter(SocialFollow.following_id == user_id)
        .scalar() or 0
    )
    following = (
        db.query(func.count(SocialFollow.following_id))
        .filter(SocialFollow.follower_id == user_id)
        .scalar() or 0
    )
    return {
        "is_following":    is_following,
        "followers_count": followers,
        "following_count": following,
    }


@router.get("/users/{user_id}/followers")
def get_followers(
    user_id: str,
    limit:   int           = Query(20, ge=1, le=50),
    cursor:  Optional[str] = Query(None),
    db:      Session       = Depends(get_db),
    _:       User          = Depends(get_current_user),
):
    q = (
        db.query(SocialFollow, User)
        .join(User, User.id == SocialFollow.follower_id)
        .filter(SocialFollow.following_id == user_id)
        .order_by(SocialFollow.created_at.desc())
    )
    if cursor:
        try:
            q = q.filter(SocialFollow.created_at < datetime.fromisoformat(cursor))
        except Exception:
            pass
    rows     = q.limit(limit + 1).all()
    has_more = len(rows) > limit
    rows     = rows[:limit]
    return {
        "data":        [{"id": u.id, "nombre": u.nombre, "since": f.created_at} for f, u in rows],
        "has_more":    has_more,
        "next_cursor": rows[-1][0].created_at.isoformat() if (has_more and rows) else None,
    }


@router.get("/users/{user_id}/following")
def get_following(
    user_id: str,
    limit:   int           = Query(20, ge=1, le=50),
    cursor:  Optional[str] = Query(None),
    db:      Session       = Depends(get_db),
    _:       User          = Depends(get_current_user),
):
    q = (
        db.query(SocialFollow, User)
        .join(User, User.id == SocialFollow.following_id)
        .filter(SocialFollow.follower_id == user_id)
        .order_by(SocialFollow.created_at.desc())
    )
    if cursor:
        try:
            q = q.filter(SocialFollow.created_at < datetime.fromisoformat(cursor))
        except Exception:
            pass
    rows     = q.limit(limit + 1).all()
    has_more = len(rows) > limit
    rows     = rows[:limit]
    return {
        "data":        [{"id": u.id, "nombre": u.nombre, "since": f.created_at} for f, u in rows],
        "has_more":    has_more,
        "next_cursor": rows[-1][0].created_at.isoformat() if (has_more and rows) else None,
    }


# ════════════════════════════════════════════════════════════════════
# KUDOS (toggle)
# ════════════════════════════════════════════════════════════════════
@router.post("/logs/{log_id}/kudos", response_model=KudoToggleOut)
def toggle_kudo(
    log_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    if not db.query(WorkoutLog).filter(WorkoutLog.id == log_id).first():
        raise HTTPException(404, "Actividad no encontrada")

    existing = db.query(SocialKudo).filter(
        SocialKudo.log_id  == log_id,
        SocialKudo.user_id == me.id,
    ).first()

    if existing:
        db.delete(existing)
        action = "removed"
    else:
        db.add(SocialKudo(log_id=log_id, user_id=me.id))
        action = "added"

    db.commit()
    count = (
        db.query(func.count(SocialKudo.id))
        .filter(SocialKudo.log_id == log_id)
        .scalar() or 0
    )
    return {"action": action, "kudos_count": count}


@router.get("/logs/{log_id}/kudos")
def list_kudos(
    log_id: str,
    limit:  int     = Query(20, ge=1, le=50),
    db:     Session = Depends(get_db),
    _:      User    = Depends(get_current_user),
):
    rows = (
        db.query(SocialKudo, User)
        .join(User, User.id == SocialKudo.user_id)
        .filter(SocialKudo.log_id == log_id)
        .order_by(SocialKudo.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{"id": u.id, "nombre": u.nombre, "kudoed_at": k.created_at} for k, u in rows]


# ════════════════════════════════════════════════════════════════════
# COMMENTS
# ════════════════════════════════════════════════════════════════════
@router.get("/logs/{log_id}/comments")
def list_comments(
    log_id: str,
    limit:  int     = Query(50, ge=1, le=100),
    db:     Session = Depends(get_db),
    me:     User    = Depends(get_current_user),
):
    rows = (
        db.query(SocialComment, User)
        .join(User, User.id == SocialComment.author_id)
        .filter(SocialComment.log_id == log_id)
        .order_by(SocialComment.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":         c.id,
            "body":       c.body,
            "created_at": c.created_at,
            "author":     {"id": u.id, "nombre": u.nombre},
            "is_mine":    u.id == me.id,
        }
        for c, u in rows
    ]


@router.post("/logs/{log_id}/comments", status_code=201)
def create_comment(
    log_id: str,
    body:   CommentCreate,
    db:     Session = Depends(get_db),
    me:     User    = Depends(get_current_user),
):
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(422, "El comentario no puede estar vacío")
    if len(text) > 1000:
        raise HTTPException(422, "Máximo 1000 caracteres")

    if not db.query(WorkoutLog).filter(WorkoutLog.id == log_id).first():
        raise HTTPException(404, "Actividad no encontrada")

    comment = SocialComment(log_id=log_id, author_id=me.id, body=text)
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {
        "id":         comment.id,
        "body":       comment.body,
        "created_at": comment.created_at,
        "author":     {"id": me.id, "nombre": me.nombre},
        "is_mine":    True,
    }


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    comment = db.query(SocialComment).filter(SocialComment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comentario no encontrado")
    if comment.author_id != me.id and me.rol not in ("coach", "admin"):
        raise HTTPException(403, "Sin permiso para eliminar este comentario")
    db.delete(comment)
    db.commit()
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════
# DISCOVER (sugerencias de atletas a seguir)
# ════════════════════════════════════════════════════════════════════
@router.get("/discover")
def discover_users(
    limit: int     = Query(8, ge=1, le=20),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    """Usuarios activos no seguidos aún, ordenados por más seguidores."""
    following_sq = (
        db.query(SocialFollow.following_id)
        .filter(SocialFollow.follower_id == me.id)
        .subquery()
    )

    candidates = (
        db.query(User)
        .filter(
            User.id != me.id,
            User.activo == True,
            User.id.notin_(following_sq),
        )
        .limit(limit * 3)   # fetch extra para poder ordenar por followers
        .all()
    )

    result = []
    for u in candidates:
        fc = (
            db.query(func.count(SocialFollow.follower_id))
            .filter(SocialFollow.following_id == u.id)
            .scalar() or 0
        )
        lc = (
            db.query(func.count(WorkoutLog.id))
            .filter(WorkoutLog.user_id == u.id, WorkoutLog.completado == True)
            .scalar() or 0
        )
        result.append({
            "id":              u.id,
            "nombre":          u.nombre,
            "rol":             u.rol,
            "race_goal_name":  u.race_goal_name,
            "followers_count": fc,
            "logs_count":      lc,
        })

    result.sort(key=lambda x: x["followers_count"], reverse=True)
    return result[:limit]
