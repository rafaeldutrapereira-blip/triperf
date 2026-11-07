"""W17 - Plan del dia: suma las sesiones vengan de donde vengan.

Fuentes hoy: asignaciones LabX (assigned_workouts, source 'labx') y plan
descargado de Garmin (garmin_planned_workouts, source 'garmin'). Futuro:
intervals.icu cuando el atleta lo conecte (misma normalizacion).
Solo lectura; no toca la sincronizacion Garmin.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import AssignedWorkout, GarminActivity, GarminPlannedWorkout

_SPORT_ALIAS = {"gym": "strength"}


def _sport(s: Optional[str]) -> str:
    s = (s or "other").lower().strip()
    return _SPORT_ALIAS.get(s, s)


def _norm_title(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _similar(a: str, b: str) -> bool:
    """Titulo igual o muy parecido (uno contiene al otro, o mismas palabras)."""
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / len(wa | wb) >= 0.7


def garmin_planned_items(db: Session, user_id: str, start: Optional[str], end: Optional[str]) -> list:
    """Filas de garmin_planned_workouts del usuario, normalizadas al contrato de /athlete/plan."""
    q = db.query(GarminPlannedWorkout).filter(GarminPlannedWorkout.user_id == user_id)
    if start:
        q = q.filter(GarminPlannedWorkout.date_iso >= start)
    if end:
        q = q.filter(GarminPlannedWorkout.date_iso <= end)
    items = []
    for g in q.order_by(GarminPlannedWorkout.date_iso).all():
        try:
            created = datetime.fromisoformat(g.date_iso)
        except (TypeError, ValueError):
            created = datetime(1970, 1, 1)
        items.append({
            "id": "garmin:" + str(g.id),
            "date_iso": g.date_iso,
            "notas": g.description,
            "coach_comment": None,
            "athlete_id": user_id,
            "group_id": None,
            "template": {
                "id": "garmin:" + str(g.id),
                "coach_id": "",
                "sport": _sport(g.sport),
                "tipo": None,
                "nombre": g.title or "",
                "dur_min": int(round(g.dur_min)) if g.dur_min is not None else None,
                "dist_km": g.dist_km,
                "tss": int(round(g.tss_planned)) if g.tss_planned is not None else None,
                "notas": g.description,
                "blocks_json": None,
                "created_at": created,
            },
            "logs": [],
            "created_at": created,
            "source": "garmin",
            "done": False,
        })
    return items


def _dedupe(labx: list, garmin: list) -> list:
    """Descarta filas Garmin ya cubiertas por una asignacion LabX (gana LabX)."""
    by_day: dict = {}
    for a in labx:
        by_day.setdefault(a.date_iso, []).append(a)
    out = []
    for g in garmin:
        gt = g["template"]
        dup = False
        for a in by_day.get(g["date_iso"], []):
            t = a.template
            if t is None or _sport(t.sport) != gt["sport"]:
                continue
            if _similar(_norm_title(t.nombre), _norm_title(gt["nombre"])):
                dup = True
                break
        if not dup:
            out.append(g)
    return out


def drop_own_plan_twins(db: Session, user_id: str, rows: list) -> list:
    """Quita de `rows` (dicts con date_iso/sport/title, de garmin_planned_workouts) las
    copias devueltas de una sesion del plan propio (own_plan_sessions): viaje LabX ->
    intervals -> Garmin -> sync legacy. Mismo dia + mismo deporte + titulo igual/parecido
    (criterio W17); gana la sesion LabX. Solo vista: no modifica ninguna fila."""
    if not rows:
        return rows
    from ..models import OwnPlanSession
    dates = {r["date_iso"] for r in rows}
    own: dict = {}
    for s in db.query(OwnPlanSession).filter(
            OwnPlanSession.user_id == user_id, OwnPlanSession.date_iso.in_(dates)).all():
        own.setdefault(s.date_iso, []).append((_sport(s.sport), _norm_title(s.name)))
    if not own:
        return rows
    out = []
    for r in rows:
        sp, tt = _sport(r.get("sport")), _norm_title(r.get("title"))
        if any(osp == sp and _similar(ot, tt) for osp, ot in own.get(r["date_iso"], [])):
            continue
        out.append(r)
    return out


def _mark_done(db: Session, user_id: str, garmin: list) -> None:
    """done=True solo con actividad sincronizada del mismo dia y deporte."""
    if not garmin:
        return
    dates = {g["date_iso"] for g in garmin}
    acts = db.query(GarminActivity.date_iso, GarminActivity.sport).filter(
        GarminActivity.user_id == user_id, GarminActivity.date_iso.in_(dates)).all()
    seen = {(d, _sport(s)) for d, s in acts}
    for g in garmin:
        g["done"] = (g["date_iso"], g["template"]["sport"]) in seen


def build_plan(db: Session, user_id: str, start: Optional[str], end: Optional[str],
               include_garmin: bool = False) -> list:
    """Asignaciones LabX (+ plan Garmin normalizado si include_garmin), por fecha."""
    q = db.query(AssignedWorkout).filter(
        AssignedWorkout.athlete_id == user_id, AssignedWorkout.deleted_at.is_(None))
    if start:
        q = q.filter(AssignedWorkout.date_iso >= start)
    if end:
        q = q.filter(AssignedWorkout.date_iso <= end)
    labx = q.order_by(AssignedWorkout.date_iso).all()
    if not include_garmin:
        return labx
    garmin = _dedupe(labx, garmin_planned_items(db, user_id, start, end))
    _mark_done(db, user_id, garmin)
    rows = list(labx) + garmin
    rows.sort(key=lambda x: x["date_iso"] if isinstance(x, dict) else x.date_iso)
    return rows


# -- W21: actividades adicionales (realizado completo) ----------------------
def _match_day(planned: list, reals: list) -> set:
    """Regla de calce existente (training_plan.html pairPlanAndReal): mismo deporte,
    1 a 1, por duracion mas cercana (greedy). Devuelve los indices de `reals` calzados."""
    pairs = []
    for gi, g in enumerate(reals):
        for pi, p in enumerate(planned):
            if p["sport"] == g["sport"]:
                pairs.append((abs((g["dur_min"] or 0) - (p["dur_min"] or 0)), gi, pi))
    pairs.sort(key=lambda x: x[0])
    ug, up, matched = set(), set(), set()
    for _, gi, pi in pairs:
        if gi in ug or pi in up:
            continue
        ug.add(gi)
        up.add(pi)
        matched.add(gi)
    return matched


def build_realizado(db: Session, user_id: str, start: Optional[str], end: Optional[str]) -> dict:
    """Actividades reales del rango (sin el tope de 100 dias del dashboard); marca
    `adicional` las que no calzan con ninguna sesion planificada del dia. Los totales
    suman todas (calzadas + adicionales)."""
    q = db.query(GarminActivity).filter(GarminActivity.user_id == user_id)
    if start:
        q = q.filter(GarminActivity.date_iso >= start)
    if end:
        q = q.filter(GarminActivity.date_iso <= end)
    acts = q.order_by(GarminActivity.date_iso, GarminActivity.id).all()

    planned_by_day: dict = {}
    for row in build_plan(db, user_id, start, end, include_garmin=True):
        if isinstance(row, dict):
            d, t = row["date_iso"], row["template"]
            sp, dur = t["sport"], t["dur_min"]
        else:
            d = row.date_iso
            sp = _sport(row.template.sport if row.template else None)
            dur = row.template.dur_min if row.template else None
        planned_by_day.setdefault(d, []).append({"sport": sp, "dur_min": dur})

    by_day: dict = {}
    for a in acts:
        by_day.setdefault(a.date_iso, []).append({
            "activity_id": a.activity_id, "name": a.name, "sport": _sport(a.sport),
            "date_iso": a.date_iso, "dur_min": a.dur_min or 0, "dist_km": a.dist_km or 0.0,
            "tss": a.tss or 0.0, "avg_hr": a.avg_hr, "avg_power": a.avg_power,
            "pace_str": a.pace_str, "swim_pace": a.swim_pace,
        })
    items = []
    totals = {"tss": 0.0, "dur_min": 0, "adicional_tss": 0.0, "adicional_dur_min": 0}
    by_date: dict = {}
    for d, reals in by_day.items():
        matched = _match_day(planned_by_day.get(d, []), reals)
        for i, r in enumerate(reals):
            r["adicional"] = i not in matched
            items.append(r)
            t = by_date.setdefault(d, {"tss": 0.0, "dur_min": 0})
            t["tss"] += r["tss"]
            t["dur_min"] += r["dur_min"]
            totals["tss"] += r["tss"]
            totals["dur_min"] += r["dur_min"]
            if r["adicional"]:
                totals["adicional_tss"] += r["tss"]
                totals["adicional_dur_min"] += r["dur_min"]
    items.sort(key=lambda x: (x["date_iso"], str(x["activity_id"])))
    return {"activities": items, "by_date": by_date, "totals": totals}
