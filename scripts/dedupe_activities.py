"""PILA 374 DEDUPE: detecta y marca actividades duplicadas (la misma sesion por varias vias).

Nunca borra filas: --apply escribe duplicate_of_id / duplicate_reason (reversible poniendolos
en NULL). Conserva como canonica la fila mas completa (mas campos con dato; empate: mayor
duracion registrada). Idempotente. Tras --apply recalcula la carga de entrenamiento de los
usuarios afectados (sin los duplicados).

Uso (desde la raiz del repo, con DATABASE_URL apuntando a la BD deseada):
    python scripts/dedupe_activities.py --dry-run [--user-id ID]   # solo reporta
    python scripts/dedupe_activities.py --apply   [--user-id ID]   # marca
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fmt(r) -> str:
    return (f"{r.activity_id} '{r.name or ''}' {r.sport} {r.dur_min}min "
            f"{r.dist_km or 0}km tss={r.tss or 0}")


def run(db, apply: bool = False, user_id: str | None = None, out=print) -> dict:
    from api.activity_dedupe import apply_groups, find_duplicate_groups

    groups = find_duplicate_groups(db, user_id)
    pending = [g for g in groups
               if any(d.duplicate_of_id != g["canonical"].id for d in g["duplicates"])
               or g["canonical"].duplicate_of_id is not None]
    for g in groups:
        state = "ya marcado" if g not in pending else ("A MARCAR" if apply else "detectado")
        out(f"[{state}] user={g['user_id']} fecha={g['date_iso']}")
        out(f"    canonica : {_fmt(g['canonical'])}")
        for d in g["duplicates"]:
            out(f"    duplicada: {_fmt(d)}")
    changed = 0
    users: set[str] = set()
    if apply and pending:
        changed = apply_groups(pending)
        users = {g["user_id"] for g in pending}
        db.commit()
        from api.services.training_service import recalculate_training_load
        for uid in sorted(users):
            try:
                recalculate_training_load(db, uid)
                db.commit()
            except Exception as exc:  # no bloquea el marcado
                db.rollback()
                out(f"  aviso: no se pudo recalcular la carga de {uid}: {type(exc).__name__}")
    out(f"grupos={len(groups)} pendientes={len(pending)} filas_marcadas={changed}"
        f"{' (dry-run: no se escribio nada)' if not apply else ''}")
    return {"groups": len(groups), "pending": len(pending), "marked": changed}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--user-id")
    a = ap.parse_args(argv)
    from api.database import SessionLocal
    db = SessionLocal()
    try:
        run(db, apply=a.apply, user_id=a.user_id)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
