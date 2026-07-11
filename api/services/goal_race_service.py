"""
Goal Race Intelligence Service — Sprint 29.

Given an athlete's goal race and current CTL, computes the strategic
training directive: required weekly TSS, CTL progression, peak form window.
"""
from __future__ import annotations
import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import RaceEvent, GarminTrainingLoad

_CTL_TAU   = 42
_ATL_TAU   = 7
_CTL_DECAY = 1 - math.exp(-1 / _CTL_TAU)   # ≈ 0.02326
_ATL_DECAY = 1 - math.exp(-1 / _ATL_TAU)   # ≈ 0.13534

# Target CTL by race distance (conservative but competitive targets)
_CTL_TARGETS: dict[str, int] = {
    "sprint":  45,
    "olympic": 60,
    "703":     75,
    "70.3":    75,
    "half":    75,
    "full":    90,
    "ironman": 90,
    "21k":     55,
    "42k":     65,
    "marathon": 65,
    "custom":  65,
}

# Taper duration in days by distance
_TAPER_DAYS: dict[str, int] = {
    "sprint":   7,
    "olympic":  10,
    "703":      14,
    "70.3":     14,
    "half":     14,
    "full":     21,
    "ironman":  21,
    "21k":      10,
    "42k":      14,
    "marathon": 14,
    "custom":   10,
}

# Distance labels
_DIST_LABEL: dict[str, str] = {
    "sprint":   "Sprint",
    "olympic":  "Olímpico",
    "703":      "70.3 (media)",
    "70.3":     "70.3 (media)",
    "half":     "70.3 (media)",
    "full":     "Ironman",
    "ironman":  "Ironman",
    "21k":      "Media Maratón",
    "42k":      "Maratón",
    "marathon": "Maratón",
    "custom":   "Custom",
}


def _ctl_target_for_distance(distance: Optional[str]) -> int:
    key = (distance or "custom").lower().replace(" ", "")
    return _CTL_TARGETS.get(key, 65)


def _taper_days_for_distance(distance: Optional[str]) -> int:
    key = (distance or "custom").lower().replace(" ", "")
    return _TAPER_DAYS.get(key, 10)


def _dist_label(distance: Optional[str]) -> str:
    key = (distance or "custom").lower().replace(" ", "")
    return _DIST_LABEL.get(key, "Custom")


def _ctl_after_n_days(ctl_init: float, tss_daily: float, n_days: int) -> float:
    """Banister CTL projection with constant daily TSS."""
    ctl = ctl_init
    for _ in range(n_days):
        ctl = ctl * (1 - _CTL_DECAY) + tss_daily * _CTL_DECAY
    return ctl


def _required_daily_tss(ctl_start: float, ctl_target: float, build_days: int) -> float:
    """Daily TSS needed to reach ctl_target from ctl_start in build_days (Banister)."""
    if build_days <= 0:
        return 0.0
    decay_n = (1 - _CTL_DECAY) ** build_days
    denominator = 1 - decay_n
    if denominator < 1e-9:
        return ctl_target
    tss_daily = (ctl_target - ctl_start * decay_n) / denominator
    return max(0.0, tss_daily)


def _week_by_week_projection(
    ctl_init: float,
    atl_init: float,
    tss_daily_build: float,
    tss_daily_taper: float,
    build_days: int,
    taper_days: int,
) -> list[dict]:
    """Day-by-day CTL/ATL/TSB projection for chart rendering."""
    rows = []
    ctl = ctl_init
    atl = atl_init
    total_days = build_days + taper_days
    today = date.today()

    for i in range(total_days + 1):
        d = today + timedelta(days=i)
        tss = tss_daily_taper if i >= build_days else tss_daily_build
        if i > 0:
            ctl = ctl * (1 - _CTL_DECAY) + tss * _CTL_DECAY
            atl = atl * (1 - _ATL_DECAY) + tss * _ATL_DECAY
        tsb = ctl - atl
        rows.append({
            "date_iso":  d.isoformat(),
            "day_offset": i,
            "ctl":  round(ctl, 1),
            "atl":  round(atl, 1),
            "tsb":  round(tsb, 1),
            "is_taper": i >= build_days,
        })

    return rows


def _acwr_for_tss_daily(tss_daily: float, current_tss_28d_avg: float) -> float:
    acute = tss_daily
    chronic = current_tss_28d_avg if current_tss_28d_avg > 0 else tss_daily
    return round(acute / chronic, 2) if chronic > 0 else 1.0


def _tsb_form_label(tsb: float) -> str:
    if tsb >= 15:  return "Forma Pico"
    if tsb >= 5:   return "Buena Forma"
    if tsb > -5:   return "Neutro"
    if tsb > -15:  return "Fatiga Moderada"
    if tsb > -25:  return "Fatiga Alta"
    return "Sobrecarga"


# ── Public API ────────────────────────────────────────────────────────────────

def compute_race_countdown(user_id: str, db: Session) -> dict:
    """
    Full strategic race intelligence:
    - Find next goal race (is_goal_race=True, else next upcoming)
    - Get current CTL/ATL from latest GarminTrainingLoad
    - Compute CTL gap, required weekly TSS, week-by-week projection
    - Return conservative + aggressive scenarios
    """
    today = date.today()

    # 1. Find goal race
    race = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == user_id,
            RaceEvent.date_iso >= today.isoformat(),
            RaceEvent.is_goal_race == True,
        )
        .order_by(RaceEvent.date_iso)
        .first()
    )
    if not race:
        # Fallback: next upcoming race
        race = (
            db.query(RaceEvent)
            .filter(
                RaceEvent.user_id == user_id,
                RaceEvent.date_iso >= today.isoformat(),
            )
            .order_by(RaceEvent.date_iso)
            .first()
        )

    if not race:
        return {"has_race": False}

    race_date    = date.fromisoformat(race.date_iso)
    days_to_race = (race_date - today).days

    if days_to_race < 0:
        return {"has_race": False}

    # 2. Current CTL/ATL
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    ctl_current = round(load.ctl, 1) if load and load.ctl else 40.0
    atl_current = round(load.atl, 1) if load and load.atl else 45.0
    tsb_current = round(ctl_current - atl_current, 1)

    # 3. Compute TSS 28d average (for ACWR check)
    cutoff_28d = (today - timedelta(days=28)).isoformat()
    loads_28d = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id == user_id,
            GarminTrainingLoad.date_iso >= cutoff_28d,
        )
        .all()
    )
    tss_28d_avg = sum(l.tss for l in loads_28d) / 28.0 if loads_28d else max(1.0, ctl_current * 0.9)

    # 4. Race targets
    distance     = race.distance or "custom"
    ctl_target   = _ctl_target_for_distance(distance)
    taper_days   = _taper_days_for_distance(distance)
    build_days   = max(0, days_to_race - taper_days)
    ctl_gap      = max(0, ctl_target - ctl_current)
    already_fit  = ctl_current >= ctl_target

    weeks_to_build = round(build_days / 7.0, 1)
    weeks_total    = round(days_to_race / 7.0, 1)

    # 5. Required daily TSS during build phase
    tss_daily_build = _required_daily_tss(ctl_current, ctl_target, build_days) if build_days > 0 else ctl_current
    tss_weekly_build = round(tss_daily_build * 7, 0)

    # Taper phase: reduce to ~50% of build TSS
    tss_daily_taper = round(tss_daily_build * 0.5, 1) if not already_fit else round(ctl_current * 0.5, 1)

    # 6. ACWR check on the required TSS
    acwr_required = _acwr_for_tss_daily(tss_daily_build, tss_28d_avg)
    is_safe_ramp  = acwr_required <= 1.3

    # 7. Conservative scenario: ACWR capped at 1.2
    max_daily_tss_safe = tss_28d_avg * 1.2
    tss_daily_conservative = min(tss_daily_build, max_daily_tss_safe)
    ctl_conservative_on_race = _ctl_after_n_days(ctl_current, tss_daily_conservative, build_days)
    if taper_days > 0:
        ctl_conservative_on_race = _ctl_after_n_days(ctl_conservative_on_race, tss_daily_taper, taper_days)

    # 8. Week-by-week projection (for chart)
    projection = _week_by_week_projection(
        ctl_current, atl_current,
        tss_daily_build, tss_daily_taper,
        build_days, taper_days,
    )

    # 9. CTL on race day (from projection)
    ctl_on_race_day = projection[-1]["ctl"] if projection else ctl_current
    tsb_on_race_day = projection[-1]["tsb"] if projection else 0.0
    form_on_race    = _tsb_form_label(tsb_on_race_day)

    # 10. Taper start date
    taper_start_date = (race_date - timedelta(days=taper_days)).isoformat()

    # 11. Peak form window: TSB highest in last 14 days before race
    race_window = [r for r in projection if r["is_taper"]]
    peak_entry  = max(race_window, key=lambda r: r["tsb"]) if race_window else None

    # 12. Directive message
    if already_fit:
        directive = f"CTL {ctl_current} ≥ objetivo {ctl_target}. Mantén {round(tss_28d_avg * 7, 0):.0f} TSS/sem y ejecuta el taper desde {taper_start_date}."
    elif not is_safe_ramp:
        directive = (
            f"Necesitas +{ctl_gap} CTL en {weeks_to_build:.0f} semanas. "
            f"Ramp seguro máx: {round(tss_daily_conservative * 7, 0):.0f} TSS/sem → CTL proyectado {round(ctl_conservative_on_race, 1)} (bajo objetivo). "
            f"Considera revisar el objetivo o ampliar el período de preparación."
        )
    else:
        directive = (
            f"Necesitas {tss_weekly_build:.0f} TSS/semana durante {weeks_to_build:.0f} semanas para llegar a CTL {ctl_target}. "
            f"Taper desde {taper_start_date} ({taper_days}d). ACWR proyectado: {acwr_required} ✓"
        )

    return {
        "has_race": True,
        "race": {
            "id":       race.id,
            "name":     race.name,
            "date_iso": race.date_iso,
            "distance": distance,
            "distance_label": _dist_label(distance),
            "is_goal_race": race.is_goal_race,
        },
        "countdown": {
            "days_to_race":   days_to_race,
            "weeks_total":    weeks_total,
            "build_days":     build_days,
            "taper_days":     taper_days,
            "taper_start_date": taper_start_date,
        },
        "fitness": {
            "ctl_current":  ctl_current,
            "atl_current":  atl_current,
            "tsb_current":  tsb_current,
            "tss_28d_avg":  round(tss_28d_avg, 1),
        },
        "targets": {
            "ctl_target":     ctl_target,
            "ctl_gap":        ctl_gap,
            "already_fit":    already_fit,
            "ctl_on_race_day": round(ctl_on_race_day, 1),
            "tsb_on_race_day": round(tsb_on_race_day, 1),
            "form_on_race":   form_on_race,
        },
        "directive": {
            "tss_weekly":     tss_weekly_build,
            "tss_daily":      round(tss_daily_build, 1),
            "acwr_projected": acwr_required,
            "is_safe_ramp":   is_safe_ramp,
            "message":        directive,
            "tss_conservative_weekly": round(tss_daily_conservative * 7, 0),
            "ctl_conservative":        round(ctl_conservative_on_race, 1),
        },
        "peak_form": {
            "date_iso":  peak_entry["date_iso"] if peak_entry else taper_start_date,
            "day_offset": peak_entry["day_offset"] if peak_entry else build_days,
            "tsb":       peak_entry["tsb"] if peak_entry else 0.0,
        },
        "projection": projection[::3] if len(projection) > 30 else projection,
    }
