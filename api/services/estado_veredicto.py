"""Veredicto unico de "como estoy hoy" (A1).

Fuente unica de la regla que antes vivia duplicada en estado.html, dashboard.html
y el semaforo de la app. No recalcula Recovery ni Mental: reutiliza
``_get_or_compute_score`` (recovery_routes) y ``_get_or_compute_mfs``
(mental_routes), las mismas funciones que alimentan ``/recovery/dashboard`` y
``/mental/dashboard``.

Regla (identica a estado.html): gana la PEOR severidad entre Recovery y Mental;
con severidad igual gana el MENOR score; con empate total gobierna Recovery.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Optional

from sqlalchemy.orm import Session

from ..models import User
from ..plan_features import has_feature

REC_TEXT_MAX = 200  # misma truncacion que muestra la web

_MEN_LEVEL_LABEL = {
    "peak": "Forma Mental Pico",
    "good": "Bueno",
    "moderate": "Moderado",
    "low": "Bajo",
    "critical": "Crítico",
}


def recovery_sev(score: float) -> int:
    return 0 if score >= 70 else 1 if score >= 40 else 2


def mental_sev(level: Optional[str], score: float) -> int:
    if level in ("peak", "good"):
        return 0
    if level == "moderate":
        return 1
    if level in ("low", "critical"):
        return 2
    return 0 if score >= 70 else 1 if score >= 55 else 2


def pick_governing(rec: Optional[dict], men: Optional[dict]) -> Optional[dict]:
    """Aplica la regla de fusion sobre dos partes (cada una con sev y score)."""
    if rec and men:
        if rec["sev"] != men["sev"]:
            return rec if rec["sev"] > men["sev"] else men
        return men if men["score"] < rec["score"] else rec
    return rec or men


def _recovery_part(user: User, date_iso: str, db: Session) -> Optional[dict]:
    from ..routes.recovery_routes import _get_or_compute_score

    data = _get_or_compute_score(user.id, date_iso, db)
    # Sin ningun factor el calculo devuelve un 50 "neutral" de relleno
    # (data_completeness == 0): no es una medicion, no se usa como veredicto.
    if not data or data.get("score") is None or not data.get("data_completeness"):
        return None
    score = round(data["score"])
    return {
        "src": "rec",
        "score": score,
        "sev": recovery_sev(score),
        "level": data.get("level"),
        "label": data.get("label") or "",
        "text": (data.get("recommendation") or "")[:REC_TEXT_MAX],
        "data_completeness": data.get("data_completeness"),
    }


def _mental_part(user: User, date_iso: str, db: Session, has_real_recovery: bool) -> Optional[dict]:
    from ..models import MentalCheckin
    from ..routes.mental_routes import _get_or_compute_mfs

    # El MFS se alimenta tambien del RecoveryScore persistido, y ese cache guarda
    # el 50 de relleno cuando no hay datos. Sin check-in mental y sin Recovery
    # real, cualquier MFS seria derivado de ese relleno: no es un dato.
    if not has_real_recovery and not db.query(MentalCheckin).filter_by(
            user_id=user.id, date_iso=date_iso).first():
        return None

    mfs = _get_or_compute_mfs(user.id, date_iso, db)
    if not mfs or mfs.score is None:
        return None
    score = round(mfs.score)
    return {
        "src": "men",
        "score": score,
        "sev": mental_sev(mfs.level, score),
        "level": mfs.level,
        "label": _MEN_LEVEL_LABEL.get(mfs.level or "", mfs.level or ""),
        "text": mfs.recommendation or "",
        "data_completeness": mfs.data_completeness,
    }


def _public(part: Optional[dict]) -> Optional[dict]:
    if part is None:
        return None
    return {k: part[k] for k in ("score", "sev", "level", "label", "text", "data_completeness")}


def build_estado_hoy(user: User, db: Session, date_iso: Optional[str] = None) -> dict:
    d_iso = date_iso or _date.today().isoformat()
    can_rec = has_feature(user, "recovery")
    can_men = has_feature(user, "mental")

    # Recovery primero: el MFS lee el RecoveryScore ya persistido del dia.
    rec = _recovery_part(user, d_iso, db) if can_rec else None
    men = _mental_part(user, d_iso, db, rec is not None) if can_men else None
    gov = pick_governing(rec, men)

    base = {
        "date_iso": d_iso,
        "available": {"recovery": can_rec, "mental": can_men},
        "recovery": _public(rec),
        "mental": _public(men),
    }
    if gov is None:
        if not can_rec and not can_men:
            status, label, text = (
                "plan_locked",
                "Estado no disponible en tu plan",
                "Recuperación y Mental se incluyen desde el plan Age Group.",
            )
        else:
            status, label, text = (
                "no_data",
                "Sin datos de hoy",
                "Todavía no hay datos de hoy. Registra tu día (bienestar y estado mental) para ver tu estado.",
            )
        return {**base, "status": status, "sev": None, "label": label, "text": text,
                "governs": None, "score": None}
    return {**base, "status": "ok", "sev": gov["sev"], "label": gov["label"], "text": gov["text"],
            "governs": gov["src"], "score": gov["score"]}
