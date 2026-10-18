"""
B6 — Migración de planes de nutrición a Race Day (fuente única).

Cada fila de nutrition_plans (un plan por atleta) se regenera con el generador
de Race Day (_gen_nutrition) para la carrera más próxima del atleta, y se guarda
en race_plans.nutrition_plan_json. Los valores pueden cambiar: es el costo de
tener una sola fuente de verdad (decisión de Rafael).

- plan_migration(): dry-run, no escribe.
- apply_migration(): escribe. Es idempotente (regenera lo mismo con los mismos datos).
- Las filas de nutrition_plans NO se borran: quedan como respaldo.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import NutritionPlan, RacePlan, User
from ..routes.race_routes import _gen_nutrition, nearest_race_for

DEFAULT_TOTAL_S = 7200


def _sweat_from(params_json: str | None) -> float:
    try:
        v = float((json.loads(params_json or "{}")).get("sweat") or 0.8)
    except (ValueError, TypeError, AttributeError):
        v = 0.8
    return min(max(v, 0.3), 2.5)


def plan_migration(db: Session, today_iso: str | None = None) -> list[dict]:
    today = today_iso or date.today().isoformat()
    report: list[dict] = []
    for plan in db.query(NutritionPlan).order_by(NutritionPlan.user_id).all():
        user = db.get(User, plan.user_id)
        race = nearest_race_for(db, plan.user_id, today)
        if race is None:
            report.append({"user_id": plan.user_id, "status": "sin_carrera"})
            continue
        rp = (db.query(RacePlan)
              .filter_by(user_id=plan.user_id, race_event_id=race.id).first())
        total_s = (rp.total_pred_s if rp and rp.total_pred_s else None) \
            or race.pred_total_sec or DEFAULT_TOTAL_S
        weight = (user.weight_kg if user and user.weight_kg else 70.0)
        nutrition = _gen_nutrition(total_s, race.distance or "olympic", weight, _sweat_from(plan.params_json))
        report.append({
            "user_id": plan.user_id,
            "status": "migrado",
            "race_id": race.id,
            "race_date": race.date_iso,
            "nutrition": nutrition,
        })
    return report


def apply_migration(db: Session, today_iso: str | None = None) -> list[dict]:
    report = plan_migration(db, today_iso)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for item in report:
        if item["status"] != "migrado":
            continue
        rp = (db.query(RacePlan)
              .filter_by(user_id=item["user_id"], race_event_id=item["race_id"]).first())
        if rp is None:
            rp = RacePlan(user_id=item["user_id"], race_event_id=item["race_id"], race_date=item["race_date"])
            db.add(rp)
        rp.nutrition_plan_json = json.dumps(item["nutrition"])
        rp.generated_at = now
    db.commit()
    return report
