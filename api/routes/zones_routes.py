"""Sprint 32 — Performance Benchmark & Training Zone routes."""
from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PerformanceBenchmark, User
from ..auth import get_current_user, require_role
from ..permissions import assert_coach_owns_athlete
from ..services.zones_service import (
    compute_zones,
    get_latest_zones,
    get_all_latest_zones,
    VALID_SPORTS,
    hr_zones,
    bike_power_zones,
    run_pace_zones,
    swim_pace_zones,
)

# ── Schemas ───────────────────────────────────────────────────────────────────

class BenchmarkCreate(BaseModel):
    sport:                  str
    test_date:              str                      # YYYY-MM-DD
    ftp_watts:              Optional[int]   = None
    threshold_pace_sec_km:  Optional[int]   = None
    threshold_pace_sec_100m: Optional[int]  = None
    max_hr:                 Optional[int]   = None
    lthr:                   Optional[int]   = None
    weight_kg:              Optional[float] = None
    test_type:              Optional[str]   = None
    notes:                  Optional[str]   = None


# ── Helpers ───────────────────────────────────────────────────────────────────

_coach   = require_role("coach", "admin")
_athlete = require_role("athlete", "atleta", "coach", "admin")


def _validate_benchmark(body: BenchmarkCreate) -> None:
    if body.sport not in VALID_SPORTS:
        raise HTTPException(400, f"sport inválido. Válidos: {sorted(VALID_SPORTS)}")
    has_data = any([
        body.ftp_watts, body.threshold_pace_sec_km,
        body.threshold_pace_sec_100m, body.max_hr,
    ])
    if not has_data:
        raise HTTPException(400, "Debes proveer al menos un valor: ftp_watts, threshold_pace_sec_km, threshold_pace_sec_100m o max_hr")


def _bm_dict(bm: PerformanceBenchmark) -> dict:
    return {
        "id":                     bm.id,
        "athlete_id":             bm.athlete_id,
        "coach_id":               bm.coach_id,
        "sport":                  bm.sport,
        "ftp_watts":              bm.ftp_watts,
        "threshold_pace_sec_km":  bm.threshold_pace_sec_km,
        "threshold_pace_sec_100m": bm.threshold_pace_sec_100m,
        "max_hr":                 bm.max_hr,
        "lthr":                   bm.lthr,
        "weight_kg":              bm.weight_kg,
        "test_date":              bm.test_date,
        "test_type":              bm.test_type,
        "notes":                  bm.notes,
        "created_at":             bm.created_at.isoformat() if bm.created_at else None,
    }


# ── Coach router ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/coach", tags=["zones"])


@router.post("/athletes/{athlete_id}/benchmarks", status_code=201)
def coach_create_benchmark(
    athlete_id: str,
    body: BenchmarkCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Coach enters FTP / threshold data for an athlete."""
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    _validate_benchmark(body)

    bm = PerformanceBenchmark(
        id          = str(uuid.uuid4()),
        athlete_id  = athlete_id,
        coach_id    = coach.id,
        sport       = body.sport,
        test_date   = body.test_date,
        ftp_watts   = body.ftp_watts,
        threshold_pace_sec_km  = body.threshold_pace_sec_km,
        threshold_pace_sec_100m = body.threshold_pace_sec_100m,
        max_hr      = body.max_hr,
        lthr        = body.lthr,
        weight_kg   = body.weight_kg,
        test_type   = body.test_type,
        notes       = body.notes,
    )
    db.add(bm); db.commit(); db.refresh(bm)
    return {"benchmark": _bm_dict(bm), "zones": compute_zones(bm)}


@router.get("/athletes/{athlete_id}/benchmarks")
def coach_list_benchmarks(
    athlete_id: str,
    sport: Optional[str] = None,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """List all benchmarks for an athlete, optionally filtered by sport."""
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    q = db.query(PerformanceBenchmark).filter(
        PerformanceBenchmark.athlete_id == athlete_id
    )
    if sport:
        q = q.filter(PerformanceBenchmark.sport == sport)
    bms = q.order_by(PerformanceBenchmark.test_date.desc()).all()
    return [_bm_dict(b) for b in bms]


@router.get("/athletes/{athlete_id}/zones")
def coach_get_athlete_zones(
    athlete_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Return latest computed zones for all sports for this athlete."""
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    return get_all_latest_zones(athlete_id, db)


# ── Athlete router ────────────────────────────────────────────────────────────

athlete_router = APIRouter(prefix="/athlete", tags=["zones"])


@athlete_router.post("/benchmarks", status_code=201)
def athlete_create_benchmark(
    body: BenchmarkCreate,
    db: Session = Depends(get_db),
    me: User = Depends(_athlete),
):
    """Athlete self-reports a benchmark (FTP test, time trial, etc.)."""
    _validate_benchmark(body)
    bm = PerformanceBenchmark(
        id          = str(uuid.uuid4()),
        athlete_id  = me.id,
        coach_id    = None,
        sport       = body.sport,
        test_date   = body.test_date,
        ftp_watts   = body.ftp_watts,
        threshold_pace_sec_km  = body.threshold_pace_sec_km,
        threshold_pace_sec_100m = body.threshold_pace_sec_100m,
        max_hr      = body.max_hr,
        lthr        = body.lthr,
        weight_kg   = body.weight_kg,
        test_type   = body.test_type,
        notes       = body.notes,
    )
    db.add(bm); db.commit(); db.refresh(bm)
    return {"benchmark": _bm_dict(bm), "zones": compute_zones(bm)}


@athlete_router.get("/benchmarks")
def athlete_list_benchmarks(
    db: Session = Depends(get_db),
    me: User = Depends(_athlete),
):
    """Athlete lists own benchmarks."""
    bms = (
        db.query(PerformanceBenchmark)
        .filter(PerformanceBenchmark.athlete_id == me.id)
        .order_by(PerformanceBenchmark.test_date.desc())
        .all()
    )
    return [_bm_dict(b) for b in bms]


@athlete_router.get("/zones")
def athlete_get_zones(
    db: Session = Depends(get_db),
    me: User = Depends(_athlete),
):
    """Return latest computed zones across all 3 sports for the athlete."""
    return get_all_latest_zones(me.id, db)


@athlete_router.get("/zones/profile")
def athlete_profile_zones(
    db: Session = Depends(get_db),
    me: User = Depends(_athlete),
):
    """Compute training zones from user profile fields (ftp, fcmax, css, run_pace).
    Returns {hr_zones, power_zones, run_zones, swim_zones} ready for the frontend."""

    def _parse_pace(s: str) -> int:
        """'4:20 /km' or '1:45' → total seconds (int). Returns 0 on failure."""
        if not s:
            return 0
        part = s.strip().split()[0]   # drop ' /km' suffix
        try:
            parts = part.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, IndexError):
            pass
        return 0

    def _to_frontend(zones: list) -> list:
        """Convert internal zone dicts to the {name, range, description} format the JS expects."""
        out = []
        for z in zones:
            out.append({
                "name":        z.get("name", ""),
                "range":       z.get("label") or z.get("range", ""),
                "description": z.get("desc")  or z.get("description", ""),
            })
        return out

    result: dict = {"hr_zones": None, "power_zones": None, "run_zones": None, "swim_zones": None}

    if me.fcmax and me.fcmax > 0:
        result["hr_zones"] = _to_frontend(hr_zones(me.fcmax))

    if me.ftp and me.ftp > 0:
        result["power_zones"] = _to_frontend(bike_power_zones(me.ftp))

    if me.run_pace:
        sec = _parse_pace(me.run_pace)
        if sec > 0:
            result["run_zones"] = _to_frontend(run_pace_zones(sec))

    if me.css:
        sec = _parse_pace(me.css)
        if sec > 0:
            result["swim_zones"] = _to_frontend(swim_pace_zones(sec))

    return result
