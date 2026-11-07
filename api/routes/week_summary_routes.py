"""
Sprint 3 -- franja semanal de Mi Plan (solo lectura).

GET /api/training-plan/week-summary?monday=YYYY-MM-DD junta, para los 7 dias de
una semana: wellness (sueno, HRV, FC reposo), actividades hechas con su TSS,
sesiones del plan propio, y los totales de la semana con CTL/ATL/TSB/ramp del
PMC existente (garmin_training_load). NO recalcula carga: lee las columnas que
ya escribe el sync. Lo que no existe para esa semana se omite (None / ausente),
nunca se rellena con un placeholder.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    GarminActivity, GarminHealthDaily, GarminSleepSession, GarminTrainingLoad,
    OwnPlanSession, User,
)
from ..plan_features import require_feature

router = APIRouter(
    prefix="/training-plan",
    tags=["training-plan"],
    dependencies=[Depends(require_feature("training_plan"))],
)


def _r(v, nd=1):
    return None if v is None else round(float(v), nd)


@router.get("/week-summary")
def week_summary(
    monday: str = Query(..., description="YYYY-MM-DD; se normaliza al lunes de esa semana"),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    try:
        ref = datetime.strptime(monday, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "monday debe ser YYYY-MM-DD")
    mon = ref - timedelta(days=ref.weekday())
    days_iso = [(mon + timedelta(days=i)).isoformat() for i in range(7)]
    first, last = days_iso[0], days_iso[-1]

    acts = (db.query(GarminActivity)
              .filter(GarminActivity.user_id == me.id,
                      GarminActivity.date_iso >= first, GarminActivity.date_iso <= last)
              .order_by(GarminActivity.date_iso, GarminActivity.activity_id).all())
    plans = (db.query(OwnPlanSession)
               .filter(OwnPlanSession.user_id == me.id,
                       OwnPlanSession.date_iso >= first, OwnPlanSession.date_iso <= last)
               .order_by(OwnPlanSession.date_iso, OwnPlanSession.created_at).all())
    health = {h.date_iso: h for h in db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id == me.id,
        GarminHealthDaily.date_iso >= first, GarminHealthDaily.date_iso <= last).all()}
    sleep = {s.date_iso: s for s in db.query(GarminSleepSession).filter(
        GarminSleepSession.user_id == me.id,
        GarminSleepSession.date_iso >= first, GarminSleepSession.date_iso <= last).all()}

    # PMC: ventana [lunes-8d, domingo] para tener la fila de hace 7 dias del ramp.
    load_from = (mon - timedelta(days=8)).isoformat()
    loads = {l.date_iso: l for l in db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id == me.id,
        GarminTrainingLoad.date_iso >= load_from, GarminTrainingLoad.date_iso <= last).all()}

    days = []
    tot_min = 0
    for d in days_iso:
        w = {}
        h, s = health.get(d), sleep.get(d)
        if s is not None and s.total_min:
            w["sleep_h"] = round(s.total_min / 60, 1)
        if h is not None:
            if h.hrv_last_night is not None:
                w["hrv"] = round(h.hrv_last_night)
            if h.resting_hr is not None:
                w["rhr"] = h.resting_hr
        done = []
        for a in acts:
            if a.date_iso != d:
                continue
            tot_min += a.dur_min or 0
            done.append({"activity_id": a.activity_id, "name": a.name, "sport": a.sport,
                         "dur_min": a.dur_min, "dist_km": a.dist_km,
                         "tss": _r(a.tss) if a.tss else None})
        planned = []
        for p in plans:
            if p.date_iso != d:
                continue
            try:
                extra = json.loads(p.data_json or "{}")
            except ValueError:
                extra = {}
            planned.append({"id": p.id, "name": p.name, "sport": p.sport,
                            "dur_min": p.dur_min, "dist_km": p.dist_km, "tss": p.tss,
                            "status": extra.get("status") if isinstance(extra, dict) else None})
        ld = loads.get(d)
        days.append({"date_iso": d, "wellness": w, "done": done, "planned": planned,
                     "tss_day": _r(ld.tss) if ld is not None else None})

    week_loads = [loads[d] for d in days_iso if d in loads]
    summary = {
        "dur_min": tot_min if any(x["done"] for x in days) else None,
        "tss": _r(sum(l.tss or 0 for l in week_loads)) if week_loads else None,
        "ctl": None, "atl": None, "tsb": None, "ramp": None, "pmc_date": None,
    }
    # PMC "al domingo": si la semana no termino, ultimo dia con fila <= domingo
    # (nunca se proyecta ni se inventa). Ramp = CTL(fecha) - CTL(fecha-7d).
    pmc_row = None
    for d in reversed(days_iso):
        if d in loads:
            pmc_row = loads[d]
            break
    if pmc_row is not None:
        summary.update(ctl=_r(pmc_row.ctl), atl=_r(pmc_row.atl), tsb=_r(pmc_row.tsb),
                       pmc_date=pmc_row.date_iso)
        prev = loads.get((date.fromisoformat(pmc_row.date_iso) - timedelta(days=7)).isoformat())
        if prev is not None:
            summary["ramp"] = _r(pmc_row.ctl - prev.ctl)
    return {"monday": first, "sunday": last, "days": days, "summary": summary}
