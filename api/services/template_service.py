"""Sprint 33 — Training Plan Templates service.

Provides:
  - 3 built-in multi-week triathlon templates (Ironman 20w, 70.3 12w, Sprint 8w)
  - CRUD helpers for coach-authored templates
  - assign_template_to_athlete(): bulk-creates WorkoutPrescriptions + TrainingPhases
  - compliance_trend(): weekly adherence % for the last N weeks
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    PlanTemplate,
    PlanTemplateWeek,
    WorkoutPrescription,
    TrainingPhase,
    User,
)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_SPORTS     = {"triathlon", "run", "bike", "swim"}
VALID_DISTANCES  = {"ironman", "70.3", "sprint", "olympic", "marathon", "half-marathon", "other"}
VALID_PHASES     = {"base", "build", "peak", "taper", "transition", "recovery"}
VALID_DIFFICULTY = {"beginner", "intermediate", "advanced"}

_BUILTIN_COACH_ID = None   # NULL in DB → global / built-in


# ── Built-in template definitions ─────────────────────────────────────────────

def _tri_sessions(bike_z2_min, run_z2_min, swim_min, brick=False):
    """Standard triathlon week session stubs."""
    sessions = [
        {"sport": "swim",  "title": "Natación técnica Z2",   "duration_min": swim_min,   "tss": round(swim_min * 0.55), "zone": "Z2"},
        {"sport": "bike",  "title": "Rodaje aeróbico Z2",     "duration_min": bike_z2_min,"tss": round(bike_z2_min * 0.6), "zone": "Z2"},
        {"sport": "run",   "title": "Carrera suave Z2",       "duration_min": run_z2_min, "tss": round(run_z2_min * 0.65),"zone": "Z2"},
    ]
    if brick:
        sessions.append({"sport": "brick", "title": "Brick Bici-Carrera Z3", "duration_min": bike_z2_min + 20, "tss": round((bike_z2_min + 20) * 0.75), "zone": "Z3"})
    return sessions


BUILTIN_TEMPLATES = [
    {
        "id":            "builtin-ironman-20w",
        "coach_id":      None,
        "name":          "Ironman 20 semanas — Intermediate",
        "sport":         "triathlon",
        "distance_type": "ironman",
        "weeks":         20,
        "difficulty":    "intermediate",
        "description":   "Plan estándar 20 semanas para completar un Ironman. Base aeróbica 8 sem → Build con intervalos 8 sem → Peak 2 sem → Taper 2 sem. Carga progresiva 3:1.",
        "is_public":     True,
        "plan_weeks": [
            # Base (W1-W8) — aerobic base, low intensity
            {"week_num": 1,  "phase_type": "base",       "label": "Base 1 — Activación",     "tss_target": 280,  "hours_target": 8.0,  "sessions_json": _tri_sessions(90, 45, 35)},
            {"week_num": 2,  "phase_type": "base",       "label": "Base 2 — Volumen",         "tss_target": 320,  "hours_target": 9.0,  "sessions_json": _tri_sessions(105, 50, 40)},
            {"week_num": 3,  "phase_type": "base",       "label": "Base 3 — Carga",           "tss_target": 360,  "hours_target": 10.0, "sessions_json": _tri_sessions(120, 55, 45)},
            {"week_num": 4,  "phase_type": "recovery",   "label": "Recuperación 1",           "tss_target": 200,  "hours_target": 6.0,  "sessions_json": _tri_sessions(75, 35, 30)},
            {"week_num": 5,  "phase_type": "base",       "label": "Base 4 — Volumen",         "tss_target": 380,  "hours_target": 11.0, "sessions_json": _tri_sessions(135, 60, 45)},
            {"week_num": 6,  "phase_type": "base",       "label": "Base 5 — Carga",           "tss_target": 420,  "hours_target": 12.0, "sessions_json": _tri_sessions(150, 65, 50)},
            {"week_num": 7,  "phase_type": "base",       "label": "Base 6 — Pico base",       "tss_target": 450,  "hours_target": 13.0, "sessions_json": _tri_sessions(165, 70, 50, brick=True)},
            {"week_num": 8,  "phase_type": "recovery",   "label": "Recuperación 2",           "tss_target": 220,  "hours_target": 7.0,  "sessions_json": _tri_sessions(90, 40, 35)},
            # Build (W9-W16) — threshold intervals, long rides
            {"week_num": 9,  "phase_type": "build",      "label": "Build 1 — Introducción",   "tss_target": 460,  "hours_target": 12.5, "sessions_json": _tri_sessions(150, 65, 50)},
            {"week_num": 10, "phase_type": "build",      "label": "Build 2 — Intervalos",     "tss_target": 500,  "hours_target": 13.5, "sessions_json": _tri_sessions(165, 70, 55, brick=True)},
            {"week_num": 11, "phase_type": "build",      "label": "Build 3 — Carga alta",     "tss_target": 540,  "hours_target": 14.5, "sessions_json": _tri_sessions(180, 75, 55, brick=True)},
            {"week_num": 12, "phase_type": "recovery",   "label": "Recuperación 3",           "tss_target": 260,  "hours_target": 7.5,  "sessions_json": _tri_sessions(100, 45, 35)},
            {"week_num": 13, "phase_type": "build",      "label": "Build 4 — Simulación",     "tss_target": 560,  "hours_target": 15.0, "sessions_json": _tri_sessions(195, 80, 60, brick=True)},
            {"week_num": 14, "phase_type": "build",      "label": "Build 5 — Pico carga",     "tss_target": 580,  "hours_target": 15.5, "sessions_json": _tri_sessions(210, 85, 60, brick=True)},
            {"week_num": 15, "phase_type": "build",      "label": "Build 6 — Consolidación",  "tss_target": 520,  "hours_target": 14.0, "sessions_json": _tri_sessions(180, 75, 55)},
            {"week_num": 16, "phase_type": "recovery",   "label": "Recuperación 4",           "tss_target": 240,  "hours_target": 7.0,  "sessions_json": _tri_sessions(90, 40, 35)},
            # Peak (W17-W18) — race-specific sharpening
            {"week_num": 17, "phase_type": "peak",       "label": "Peak 1 — Calidad",         "tss_target": 420,  "hours_target": 11.0, "sessions_json": _tri_sessions(150, 60, 45, brick=True)},
            {"week_num": 18, "phase_type": "peak",       "label": "Peak 2 — Agudización",     "tss_target": 350,  "hours_target": 9.5,  "sessions_json": _tri_sessions(120, 50, 40)},
            # Taper (W19-W20) — freshen up
            {"week_num": 19, "phase_type": "taper",      "label": "Taper 1 — Reducción",      "tss_target": 220,  "hours_target": 6.5,  "sessions_json": _tri_sessions(90, 35, 30)},
            {"week_num": 20, "phase_type": "taper",      "label": "Taper 2 — Carrera week",   "tss_target": 100,  "hours_target": 3.5,  "sessions_json": _tri_sessions(40, 20, 20)},
        ],
    },
    {
        "id":            "builtin-703-12w",
        "coach_id":      None,
        "name":          "Ironman 70.3 — 12 semanas",
        "sport":         "triathlon",
        "distance_type": "70.3",
        "weeks":         12,
        "difficulty":    "intermediate",
        "description":   "Plan 12 semanas para un 70.3. Base aeróbica 4 sem → Build con intervalos 6 sem → Taper 2 sem. Ideal para atletas con base existente.",
        "is_public":     True,
        "plan_weeks": [
            {"week_num": 1,  "phase_type": "base",       "label": "Base 1",               "tss_target": 300,  "hours_target": 8.5,  "sessions_json": _tri_sessions(100, 50, 35)},
            {"week_num": 2,  "phase_type": "base",       "label": "Base 2",               "tss_target": 340,  "hours_target": 9.5,  "sessions_json": _tri_sessions(120, 55, 40)},
            {"week_num": 3,  "phase_type": "base",       "label": "Base 3",               "tss_target": 380,  "hours_target": 10.5, "sessions_json": _tri_sessions(135, 60, 45, brick=True)},
            {"week_num": 4,  "phase_type": "recovery",   "label": "Recuperación",         "tss_target": 200,  "hours_target": 6.0,  "sessions_json": _tri_sessions(75, 35, 30)},
            {"week_num": 5,  "phase_type": "build",      "label": "Build 1 — Intervalos", "tss_target": 420,  "hours_target": 11.5, "sessions_json": _tri_sessions(150, 65, 45, brick=True)},
            {"week_num": 6,  "phase_type": "build",      "label": "Build 2 — Carga",      "tss_target": 460,  "hours_target": 12.5, "sessions_json": _tri_sessions(165, 70, 50, brick=True)},
            {"week_num": 7,  "phase_type": "build",      "label": "Build 3 — Pico",       "tss_target": 490,  "hours_target": 13.0, "sessions_json": _tri_sessions(180, 75, 50, brick=True)},
            {"week_num": 8,  "phase_type": "recovery",   "label": "Recuperación",         "tss_target": 220,  "hours_target": 6.5,  "sessions_json": _tri_sessions(90, 40, 35)},
            {"week_num": 9,  "phase_type": "build",      "label": "Build 4 — Calidad",    "tss_target": 440,  "hours_target": 12.0, "sessions_json": _tri_sessions(165, 65, 50, brick=True)},
            {"week_num": 10, "phase_type": "build",      "label": "Build 5 — Simulación", "tss_target": 420,  "hours_target": 11.5, "sessions_json": _tri_sessions(150, 60, 45)},
            {"week_num": 11, "phase_type": "taper",      "label": "Taper 1",              "tss_target": 260,  "hours_target": 7.5,  "sessions_json": _tri_sessions(105, 45, 35)},
            {"week_num": 12, "phase_type": "taper",      "label": "Taper 2 — Race week",  "tss_target": 110,  "hours_target": 3.5,  "sessions_json": _tri_sessions(45, 20, 20)},
        ],
    },
    {
        "id":            "builtin-sprint-8w",
        "coach_id":      None,
        "name":          "Triatlón Sprint — 8 semanas",
        "sport":         "triathlon",
        "distance_type": "sprint",
        "weeks":         8,
        "difficulty":    "beginner",
        "description":   "Plan de entrada 8 semanas para primer triatlón sprint (750m / 20km / 5km). Énfasis en técnica y base aeróbica.",
        "is_public":     True,
        "plan_weeks": [
            {"week_num": 1,  "phase_type": "base",       "label": "Semana 1 — Inicio",    "tss_target": 180,  "hours_target": 5.5,  "sessions_json": _tri_sessions(60, 30, 25)},
            {"week_num": 2,  "phase_type": "base",       "label": "Semana 2 — Volumen",   "tss_target": 210,  "hours_target": 6.0,  "sessions_json": _tri_sessions(75, 35, 30)},
            {"week_num": 3,  "phase_type": "base",       "label": "Semana 3 — Carga",     "tss_target": 240,  "hours_target": 7.0,  "sessions_json": _tri_sessions(90, 40, 30)},
            {"week_num": 4,  "phase_type": "recovery",   "label": "Recuperación",         "tss_target": 140,  "hours_target": 4.0,  "sessions_json": _tri_sessions(50, 25, 20)},
            {"week_num": 5,  "phase_type": "build",      "label": "Semana 5 — Velocidad", "tss_target": 260,  "hours_target": 7.5,  "sessions_json": _tri_sessions(100, 45, 35)},
            {"week_num": 6,  "phase_type": "build",      "label": "Semana 6 — Brick",     "tss_target": 280,  "hours_target": 8.0,  "sessions_json": _tri_sessions(105, 45, 35, brick=True)},
            {"week_num": 7,  "phase_type": "taper",      "label": "Taper",                "tss_target": 160,  "hours_target": 5.0,  "sessions_json": _tri_sessions(70, 30, 25)},
            {"week_num": 8,  "phase_type": "taper",      "label": "Race week",            "tss_target": 80,   "hours_target": 2.5,  "sessions_json": _tri_sessions(30, 15, 15)},
        ],
    },
]


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def _week_dict(w: PlanTemplateWeek) -> dict:
    return {
        "id":           w.id,
        "week_num":     w.week_num,
        "phase_type":   w.phase_type,
        "label":        w.label,
        "tss_target":   w.tss_target,
        "hours_target": w.hours_target,
        "sessions":     json.loads(w.sessions_json) if w.sessions_json else [],
        "notes":        w.notes,
    }


def _template_dict(t: PlanTemplate, include_weeks: bool = False) -> dict:
    d = {
        "id":            t.id,
        "coach_id":      t.coach_id,
        "name":          t.name,
        "sport":         t.sport,
        "distance_type": t.distance_type,
        "weeks":         t.weeks,
        "difficulty":    t.difficulty,
        "description":   t.description,
        "is_public":     t.is_public,
        "is_builtin":    t.coach_id is None,
        "created_at":    t.created_at.isoformat() if t.created_at else None,
    }
    if include_weeks:
        d["plan_weeks"] = [_week_dict(w) for w in t.plan_weeks]
    return d


def _builtin_template_dict(bt: dict, include_weeks: bool = False) -> dict:
    d = {
        "id":            bt["id"],
        "coach_id":      None,
        "name":          bt["name"],
        "sport":         bt["sport"],
        "distance_type": bt["distance_type"],
        "weeks":         bt["weeks"],
        "difficulty":    bt["difficulty"],
        "description":   bt["description"],
        "is_public":     True,
        "is_builtin":    True,
        "created_at":    None,
    }
    if include_weeks:
        d["plan_weeks"] = [
            {
                "id":           f"{bt['id']}-w{w['week_num']}",
                "week_num":     w["week_num"],
                "phase_type":   w["phase_type"],
                "label":        w.get("label"),
                "tss_target":   w.get("tss_target"),
                "hours_target": w.get("hours_target"),
                "sessions":     w.get("sessions_json", []),
                "notes":        w.get("notes"),
            }
            for w in bt["plan_weeks"]
        ]
    return d


def list_templates(coach_id: str, db: Session) -> list[dict]:
    """Return built-in templates + coach's own templates."""
    builtins = [_builtin_template_dict(bt) for bt in BUILTIN_TEMPLATES]
    coach_own = (
        db.query(PlanTemplate)
        .filter(PlanTemplate.coach_id == coach_id)
        .order_by(PlanTemplate.created_at.desc())
        .all()
    )
    return builtins + [_template_dict(t) for t in coach_own]


def get_template(template_id: str, coach_id: str, db: Session) -> Optional[dict]:
    """Return a template with full week detail. Coaches can view built-ins + their own."""
    # Check built-ins first
    for bt in BUILTIN_TEMPLATES:
        if bt["id"] == template_id:
            return _builtin_template_dict(bt, include_weeks=True)
    # Coach's own
    t = db.query(PlanTemplate).filter(
        PlanTemplate.id == template_id,
        PlanTemplate.coach_id == coach_id,
    ).first()
    return _template_dict(t, include_weeks=True) if t else None


def create_template(coach_id: str, body: dict, db: Session) -> dict:
    """Create a new coach-authored template with its weeks."""
    tid = str(uuid.uuid4())
    t = PlanTemplate(
        id            = tid,
        coach_id      = coach_id,
        name          = body["name"],
        sport         = body.get("sport", "triathlon"),
        distance_type = body.get("distance_type"),
        weeks         = len(body.get("plan_weeks", [])) or body.get("weeks", 1),
        difficulty    = body.get("difficulty"),
        description   = body.get("description"),
        is_public     = body.get("is_public", False),
    )
    db.add(t)

    for wk in body.get("plan_weeks", []):
        db.add(PlanTemplateWeek(
            id            = str(uuid.uuid4()),
            template_id   = tid,
            week_num      = wk["week_num"],
            phase_type    = wk.get("phase_type"),
            label         = wk.get("label"),
            tss_target    = wk.get("tss_target"),
            hours_target  = wk.get("hours_target"),
            sessions_json = json.dumps(wk.get("sessions", [])),
            notes         = wk.get("notes"),
        ))

    db.commit()
    db.refresh(t)
    return _template_dict(t, include_weeks=True)


def update_template(template_id: str, coach_id: str, body: dict, db: Session) -> Optional[dict]:
    """Update metadata of a coach-authored template."""
    t = db.query(PlanTemplate).filter(
        PlanTemplate.id == template_id,
        PlanTemplate.coach_id == coach_id,
    ).first()
    if not t:
        return None
    for field in ("name", "sport", "distance_type", "difficulty", "description", "is_public"):
        if field in body:
            setattr(t, field, body[field])
    db.commit()
    db.refresh(t)
    return _template_dict(t, include_weeks=True)


def delete_template(template_id: str, coach_id: str, db: Session) -> bool:
    t = db.query(PlanTemplate).filter(
        PlanTemplate.id == template_id,
        PlanTemplate.coach_id == coach_id,
    ).first()
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


# ── Assignment engine ─────────────────────────────────────────────────────────

def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def assign_template_to_athlete(
    template_id: str,
    athlete_id: str,
    coach_id: str,
    start_date: str,      # YYYY-MM-DD — Monday of week 1
    db: Session,
) -> dict:
    """Expand a template into WorkoutPrescriptions (one per session per day) and TrainingPhases.

    Week 1 starts on start_date. Each week = 7 days.
    Sessions within a week are spread Mon/Wed/Fri/(Sat for bricks).
    Returns summary dict.
    """
    # Resolve template weeks
    tpl_weeks: list[dict] = []
    for bt in BUILTIN_TEMPLATES:
        if bt["id"] == template_id:
            for w in bt["plan_weeks"]:
                tpl_weeks.append({
                    "week_num":   w["week_num"],
                    "phase_type": w.get("phase_type"),
                    "label":      w.get("label"),
                    "tss_target": w.get("tss_target"),
                    "sessions":   w.get("sessions_json", []),
                })
            break
    else:
        t = db.query(PlanTemplate).filter(
            PlanTemplate.id == template_id,
            PlanTemplate.coach_id == coach_id,
        ).first()
        if not t:
            return {"error": "template_not_found"}
        for w in t.plan_weeks:
            tpl_weeks.append({
                "week_num":   w.week_num,
                "phase_type": w.phase_type,
                "label":      w.label,
                "tss_target": w.tss_target,
                "sessions":   json.loads(w.sessions_json) if w.sessions_json else [],
            })

    start = date.fromisoformat(start_date)
    # Session day offsets within each week (Mon=0, Wed=2, Fri=4, Sat=5)
    day_offsets = [0, 2, 4, 5]

    prescriptions_created = 0
    phases_created = 0
    phase_tracker: dict[str, dict] = {}   # phase_type → {start, end, label, tss}

    for wk in tpl_weeks:
        week_start = start + timedelta(weeks=wk["week_num"] - 1)
        sessions = wk["sessions"]

        # Create WorkoutPrescription for each session
        for i, sess in enumerate(sessions):
            day_offset = day_offsets[i % len(day_offsets)]
            session_date = week_start + timedelta(days=day_offset)
            rx = WorkoutPrescription(
                id          = str(uuid.uuid4()),
                coach_id    = coach_id,
                athlete_id  = athlete_id,
                title       = sess.get("title", f"Semana {wk['week_num']} · {sess.get('sport','')}"),
                description = f"[Plantilla] {wk.get('label', '')} — {sess.get('zone', '')}",
                sport       = sess.get("sport", "run"),
                date_iso    = _iso(session_date),
                duration_min = sess.get("duration_min"),
                tss_target   = sess.get("tss"),
                structure_json = json.dumps({"zone": sess.get("zone"), "template_id": template_id}),
                status      = "pending",
            )
            db.add(rx)
            prescriptions_created += 1

        # Accumulate phase boundaries
        pt = wk.get("phase_type") or "base"
        week_end = week_start + timedelta(days=6)
        if pt not in phase_tracker:
            phase_tracker[pt] = {
                "start": week_start,
                "end":   week_end,
                "label": wk.get("label", pt.capitalize()),
                "tss":   wk.get("tss_target") or 0,
            }
        else:
            phase_tracker[pt]["end"] = week_end
            if wk.get("tss_target"):
                phase_tracker[pt]["tss"] = max(phase_tracker[pt]["tss"], wk["tss_target"])

    # Create one TrainingPhase per phase block
    for pt, info in phase_tracker.items():
        db.add(TrainingPhase(
            id               = str(uuid.uuid4()),
            coach_id         = coach_id,
            athlete_id       = athlete_id,
            phase_type       = pt,
            label            = info["label"],
            start_date       = _iso(info["start"]),
            end_date         = _iso(info["end"]),
            tss_weekly_target = info["tss"],
        ))
        phases_created += 1

    db.commit()

    end_date = start + timedelta(weeks=len(tpl_weeks)) - timedelta(days=1)
    return {
        "template_id":            template_id,
        "athlete_id":             athlete_id,
        "start_date":             start_date,
        "end_date":               _iso(end_date),
        "weeks":                  len(tpl_weeks),
        "prescriptions_created":  prescriptions_created,
        "phases_created":         phases_created,
    }


# ── Compliance trend ──────────────────────────────────────────────────────────

def compliance_trend(athlete_id: str, weeks: int, db: Session) -> list[dict]:
    """Return weekly compliance (% of prescriptions completed) for last N weeks.

    A prescription is 'completed' when status == 'completed'.
    """
    from sqlalchemy import func
    from ..models import WorkoutPrescription

    today = date.today()
    result = []

    for i in range(weeks - 1, -1, -1):
        week_end   = today - timedelta(weeks=i)
        week_start = week_end - timedelta(days=6)
        iso_start  = _iso(week_start)
        iso_end    = _iso(week_end)

        total = (
            db.query(func.count(WorkoutPrescription.id))
            .filter(
                WorkoutPrescription.athlete_id == athlete_id,
                WorkoutPrescription.date_iso >= iso_start,
                WorkoutPrescription.date_iso <= iso_end,
            )
            .scalar() or 0
        )
        done = (
            db.query(func.count(WorkoutPrescription.id))
            .filter(
                WorkoutPrescription.athlete_id == athlete_id,
                WorkoutPrescription.date_iso >= iso_start,
                WorkoutPrescription.date_iso <= iso_end,
                WorkoutPrescription.status == "completed",
            )
            .scalar() or 0
        )

        pct = round(done / total * 100) if total > 0 else None
        result.append({
            "week_start":  iso_start,
            "week_end":    iso_end,
            "total_rx":    total,
            "completed_rx": done,
            "compliance_pct": pct,
        })

    return result
