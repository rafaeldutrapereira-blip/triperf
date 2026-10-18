"""
B6 — Migra los planes de nutrición de /athlete/nutrition-plan a la carrera más
próxima de cada atleta, con el generador de Race Day.

Uso (en el VM, con el venv del backend):
    python scripts/migrate_nutrition_plans.py          # dry-run: muestra el reporte
    python scripts/migrate_nutrition_plans.py --apply  # escribe en race_plans

No borra nada de nutrition_plans. Hacer respaldo de la BD antes de --apply.
"""
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.database import SessionLocal  # noqa: E402
from api.services.nutrition_migration import apply_migration, plan_migration  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        report = apply_migration(db) if apply else plan_migration(db)
    finally:
        db.close()
    counts = collections.Counter(item["status"] for item in report)
    mode = "APLICADO" if apply else "DRY-RUN (sin escritura)"
    print(f"[{mode}] planes revisados: {len(report)}")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")
    for item in report:
        if item["status"] == "migrado":
            print(f"  user={item['user_id']} carrera={item['race_id']} fecha={item['race_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
