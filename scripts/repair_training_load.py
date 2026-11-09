"""CARGA-AL-DIA: repara garmin_training_load de usuarios atrasados.

Recalcula (con recalculate_training_load, sin tocar formulas) SOLO a los usuarios cuya
ultima actividad es posterior a su ultima fila de carga, o que tienen actividades y
ninguna fila. Idempotente: una segunda corrida no encuentra usuarios atrasados.

Uso (desde la raiz del repo, con DATABASE_URL apuntando a la BD deseada):
    python scripts/repair_training_load.py --dry-run   # solo lista
    python scripts/repair_training_load.py             # repara
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def find_stale_users(db) -> list[tuple[str, str, str | None]]:
    """-> [(user_id, ultima_actividad_iso, ultima_carga_iso|None)] de los atrasados."""
    from sqlalchemy import func
    from api.models import GarminActivity, GarminTrainingLoad

    acts = dict(
        db.query(GarminActivity.user_id, func.max(GarminActivity.date_iso))
        .filter(GarminActivity.date_iso.isnot(None))
        .group_by(GarminActivity.user_id)
        .all()
    )
    loads = dict(
        db.query(GarminTrainingLoad.user_id, func.max(GarminTrainingLoad.date_iso))
        .group_by(GarminTrainingLoad.user_id)
        .all()
    )
    out = []
    for uid, last_act in acts.items():
        last_load = loads.get(uid)
        if last_load is None or last_act > last_load:
            out.append((uid, last_act, last_load))
    return sorted(out)


def repair(db, dry_run: bool = False) -> dict:
    from api.services.training_service import recalculate_training_load

    stale = find_stale_users(db)
    fixed, failed = 0, 0
    if not dry_run:
        for uid, _act, _load in stale:
            try:
                recalculate_training_load(db, uid)
                fixed += 1
            except Exception as exc:  # un usuario roto no frena al resto
                db.rollback()
                failed += 1
                print("  ERROR user=%s: %s" % (uid, type(exc).__name__), file=sys.stderr)
    return {
        "stale": len(stale),
        "repaired": fixed,
        "failed": failed,
        "until": date.today().isoformat() if fixed else None,
    }


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    from api.database import SessionLocal

    db = SessionLocal()
    try:
        res = repair(db, dry_run=dry)
    finally:
        db.close()
    if dry:
        print("[dry-run] usuarios atrasados: %d (no se modifico nada)" % res["stale"])
    else:
        print(
            "usuarios atrasados: %d | reparados: %d | fallidos: %d | carga reconstruida hasta: %s"
            % (res["stale"], res["repaired"], res["failed"], res["until"] or "-")
        )
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
