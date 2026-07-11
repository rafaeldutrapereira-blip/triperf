"""
Endpoints: Datos personales de Rafael desde los CSVs (activities, training_load, rhr).
Sirve el equivalente de window.KL_DATA directamente desde la API.
Solo accesible para admin (y opcionalmente coach).
"""
from __future__ import annotations

import csv
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/personal", tags=["personal"])
_admin = require_role("admin")
_coach_or_admin = require_role("coach", "admin")

DATA_DIR = Path(__file__).parent.parent.parent / "data"


# ─────────────────────────────────────────────
# Helpers CSV
# ─────────────────────────────────────────────
def _read_csv(name: str) -> list[dict]:
    p = DATA_DIR / name
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(v, default=0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except Exception:
        return default


def _i(v, default=0) -> int:
    try:
        return int(float(v)) if v not in (None, "") else default
    except Exception:
        return default


# ─────────────────────────────────────────────
# GET /api/personal/data
# Devuelve el equivalente de window.KL_DATA
# ─────────────────────────────────────────────
@router.get("/data")
def get_personal_data(coach: User = Depends(_coach_or_admin)):
    training = _read_csv("training_load.csv")
    activities = _read_csv("activities.csv")
    rhr_rows = _read_csv("rhr.csv")

    # ── Valores actuales CTL/ATL/TSB/ACWR
    latest = training[-1] if training else {}
    ctl = _f(latest.get("ctl"))
    atl = _f(latest.get("atl"))
    tsb = _f(latest.get("tsb"))
    acwr = round(_f(latest.get("acwr")), 2)

    # ACWR zone: 0.8-1.3 óptimo, <0.8 sub-entrenamiento, >1.3 riesgo, >1.5 alto riesgo
    if acwr >= 1.5:
        acwr_zone = "danger"
    elif acwr >= 1.3:
        acwr_zone = "warning"
    elif acwr >= 0.8:
        acwr_zone = "optimal"
    else:
        acwr_zone = "low"

    # ACWR history (últimos 60 días)
    acwr_history: list[dict] = []
    cutoff_acwr = (date.today() - timedelta(days=60)).isoformat()
    for row in training:
        if row.get("date", "") >= cutoff_acwr:
            v = _f(row.get("acwr"))
            if v:
                acwr_history.append({"dt": row["date"], "acwr": round(v, 2)})

    # CTL change (vs 7 días atrás)
    ctl_7d = _f(training[-8]["ctl"]) if len(training) >= 8 else ctl
    ctl_change = round(ctl - ctl_7d, 1)

    # Readiness simple: TSB normalizado 0-100
    readiness = max(0, min(100, int(50 + tsb * 1.5)))

    # ── TSS de la semana actual
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    tss_week = 0.0
    for row in training:
        try:
            d = date.fromisoformat(row["date"])
        except Exception:
            continue
        if mon <= d <= today:
            tss_week += _f(row.get("tss"))

    # ── PMC semanal (últimas 104 semanas)
    pmc: list[dict] = []
    if training:
        first_date = date.fromisoformat(training[0]["date"])
        # Agrupar por semana (lunes)
        by_week: dict[str, dict] = {}
        for row in training:
            try:
                d = date.fromisoformat(row["date"])
            except Exception:
                continue
            dow = d.weekday()
            wmon = (d - timedelta(days=dow)).isoformat()
            if wmon not in by_week:
                by_week[wmon] = {"tss": 0.0, "ctl": 0.0, "atl": 0.0, "tsb": 0.0, "days": 0}
            by_week[wmon]["tss"]  += _f(row.get("tss"))
            by_week[wmon]["ctl"]   = _f(row.get("ctl"))
            by_week[wmon]["atl"]   = _f(row.get("atl"))
            by_week[wmon]["tsb"]   = _f(row.get("tsb"))
            by_week[wmon]["days"] += 1

        cutoff = (today - timedelta(weeks=104)).isoformat()
        for wmon in sorted(by_week.keys()):
            if wmon < cutoff:
                continue
            w = by_week[wmon]
            pmc.append({
                "dt":  wmon,
                "l":   round(w["tss"], 1),
                "ctl": round(w["ctl"], 1),
                "atl": round(w["atl"], 1),
                "tsb": round(w["tsb"], 1),
            })

    # ── TSB diario (últimos 731 días)
    tsb_history: list[dict] = []
    cutoff_tsb = (today - timedelta(days=731)).isoformat()
    for row in training:
        if row.get("date", "") >= cutoff_tsb:
            tsb_history.append({"dt": row["date"], "tsb": round(_f(row.get("tsb")), 1)})

    # ── Wellness: RHR + Body Battery (últimos 180 días)
    rhr_history: list[dict] = []
    bb_history:  list[dict] = []
    cutoff_rhr = (today - timedelta(days=180)).isoformat()
    for row in rhr_rows:
        if row.get("date", "") < cutoff_rhr:
            continue
        rhr = _f(row.get("rhr"))
        bb  = _f(row.get("body_battery"))
        bhi = _f(row.get("bb_high"))
        if rhr:
            rhr_history.append({"dt": row["date"], "rhr": round(rhr)})
        if bb:
            bb_history.append({"dt": row["date"], "bb": round(bb), "bhi": round(bhi)})

    # ── Sueño (últimos 180 días desde sleep.csv)
    sleep_rows = _read_csv("sleep.csv")
    sleep_history: list[dict] = []
    sleep_7d: list[float] = []
    sleep_score_last = 0
    cutoff_sleep = (today - timedelta(days=180)).isoformat()
    for row in sleep_rows:
        dt = row.get("date", "")
        if dt < cutoff_sleep:
            continue
        h = _f(row.get("sleep_duration_h"))
        sc = _f(row.get("sleep_score"))
        if h > 0:
            sleep_history.append({
                "dt": dt, "h": round(h, 2),
                "score": round(sc) if sc else 0,
                "deep": round(_f(row.get("deep_sleep_h")), 2),
                "rem":  round(_f(row.get("rem_sleep_h")), 2),
            })
            if dt >= (today - timedelta(days=7)).isoformat():
                sleep_7d.append(h)
            if sc:
                sleep_score_last = round(sc)
    sleep_h_avg = round(sum(sleep_7d) / len(sleep_7d), 1) if sleep_7d else 0

    # ── HRV (desde hrv.csv — puede estar vacío si Garmin no lo provee)
    hrv_rows_csv = _read_csv("hrv.csv")
    hrv_history: list[dict] = []
    hrv_last = 0
    cutoff_hrv = (today - timedelta(days=90)).isoformat()
    for row in hrv_rows_csv:
        dt = row.get("date", "")
        if dt < cutoff_hrv:
            continue
        v = _f(row.get("hrv_last_night") or row.get("hrv_weekly_avg") or row.get("hrv"))
        if v > 0:
            hrv_history.append({"dt": dt, "hrv": round(v)})
            hrv_last = round(v)

    # ── Actividades recientes (últimas 90)
    sport_map = {"running": "run", "cycling": "bike", "swimming": "swim",
                 "strength_training": "str", "multisport": "tri"}
    recent_acts: list[dict] = []
    for row in activities[:90]:  # CSV is newest-first; first 90 = most recent
        sport_raw = (row.get("sport") or "").lower()
        sport = sport_map.get(sport_raw, sport_raw)
        recent_acts.append({
            "activity_id":   _i(row.get("activity_id")),
            "name":          row.get("name", ""),
            "sport":         sport,
            "date":          (row.get("date") or "")[:10],
            "duration_sec":  _f(row.get("duration_sec")),
            "distance_m":    _f(row.get("distance_m")),
            "avg_hr":        _f(row.get("avg_hr")),
            "max_hr":        _f(row.get("max_hr")),
            "calories":      _i(row.get("calories")),
            "avg_power":     _f(row.get("avg_power")),
            "tss":           _f(row.get("tss")),
        })

    # ── Disciplinas semana actual (swim_km, bike_km, run_km, strength_n)
    weekly_disc = {"swim_km": 0.0, "bike_km": 0.0, "run_km": 0.0, "strength_n": 0}
    for row in activities:
        try:
            d = date.fromisoformat((row.get("date") or "")[:10])
        except Exception:
            continue
        if not (mon <= d <= today):
            continue
        sp = (row.get("sport") or "").lower()
        dist_km = _f(row.get("distance_m")) / 1000
        if "swim" in sp:
            weekly_disc["swim_km"] += dist_km
        elif "bike" in sp or "cycl" in sp or "ride" in sp:
            weekly_disc["bike_km"] += dist_km
        elif "run" in sp:
            weekly_disc["run_km"] += dist_km
        elif "str" in sp or "strength" in sp:
            weekly_disc["strength_n"] += 1

    return {
        "generated":    today.isoformat(),
        "source":       "api_csv",
        "ctl":          round(ctl, 1),
        "atl":          round(atl, 1),
        "tsb":          round(tsb, 1),
        "ctl_change":   ctl_change,
        "atl_delta":    round(atl - _f(training[-8]["atl"]) if len(training) >= 8 else 0, 1),
        "readiness":    readiness,
        "tss_week":     round(tss_week),
        "tss_week_target": 520,
        "pmc":          pmc,
        "tsb_history":  tsb_history,
        "rhr_history":  rhr_history,
        "bb_history":   bb_history,
        "activities":   recent_acts,  # already newest-first from CSV[:90]
        "weekly_disc":  {k: round(v, 1) if isinstance(v, float) else v
                         for k, v in weekly_disc.items()},
        "acwr":         acwr,
        "acwr_zone":    acwr_zone,
        "acwr_history": acwr_history,
        "hrv":          hrv_last,
        "sleep_score":  sleep_score_last,
        "sleep_h":      sleep_h_avg,
        "sleep_history": sleep_history,
        "hrv_history":   hrv_history,
    }


# ─────────────────────────────────────────────
# GET /api/personal/rpe-history
# ─────────────────────────────────────────────
@router.get("/rpe-history")
def get_rpe_history(days: int = 365, db: Session = Depends(get_db),
                    coach: User = Depends(_coach_or_admin)):
    """Historial RPE de todos los workout_logs que tienen rpe != NULL."""
    from ..models import WorkoutLog, AssignedWorkout
    from sqlalchemy import and_
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = (
        db.query(WorkoutLog, AssignedWorkout)
        .join(AssignedWorkout, WorkoutLog.assignment_id == AssignedWorkout.id)
        .filter(WorkoutLog.rpe != None)
        .filter(AssignedWorkout.date_iso >= cutoff)
        .order_by(AssignedWorkout.date_iso)
        .all()
    )
    result = []
    for log, aw in rows:
        result.append({
            "date":  aw.date_iso,
            "value": log.rpe,
            "sport": aw.template.sport if aw.template else None,
        })
    return result


# ─────────────────────────────────────────────
# GET /api/personal/sync/status
# ─────────────────────────────────────────────
@router.get("/sync/status")
def sync_status(coach: User = Depends(_coach_or_admin)):
    log_path = DATA_DIR / "sync.log"
    last_sync = None
    activities_count = 0

    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        last_sync = lines[-1] if lines else None

    acts_path = DATA_DIR / "activities.csv"
    if acts_path.exists():
        with open(acts_path, encoding="utf-8") as f:
            activities_count = max(0, sum(1 for _ in f) - 1)

    training = _read_csv("training_load.csv")
    latest = training[-1] if training else {}

    return {
        "last_sync":       last_sync,
        "activities_count": activities_count,
        "training_days":   len(training),
        "latest_date":     latest.get("date"),
        "ctl":             round(_f(latest.get("ctl")), 1),
        "atl":             round(_f(latest.get("atl")), 1),
        "tsb":             round(_f(latest.get("tsb")), 1),
    }


# ─────────────────────────────────────────────
# POST /api/personal/sync
# Dispara sync_garmin.py + export_data.py (solo admin)
# ─────────────────────────────────────────────
_sync_running = False

@router.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks, admin: User = Depends(_admin)):
    global _sync_running
    if _sync_running:
        raise HTTPException(409, "Sync ya en progreso")

    def _run_sync():
        global _sync_running
        _sync_running = True
        try:
            project_root = Path(__file__).parent.parent.parent
            import sys
            python = sys.executable
            subprocess.run([python, str(project_root / "sync_garmin.py")],
                           cwd=str(project_root), timeout=600)
            subprocess.run([python, str(project_root / "export_data.py")],
                           cwd=str(project_root), timeout=120)
            log_path = project_root / "data" / "sync.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M UTC") + " — sync OK\n")
        except Exception as ex:
            pass
        finally:
            _sync_running = False

    background_tasks.add_task(_run_sync)
    return {"status": "started", "message": "Sync Garmin iniciado en background"}
