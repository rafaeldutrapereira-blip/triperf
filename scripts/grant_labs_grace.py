"""
B12 — Gracia de 90 días de Labs para los Elite actuales. Ejecutar UNA vez, al
desplegar B12, después de configurar LABX_ADDONS=1.

Uso (en el VM, con el venv del backend):
    python scripts/grant_labs_grace.py          # dry-run: cuenta y lista
    python scripts/grant_labs_grace.py --apply  # crea los entitlements

Hacer respaldo de la BD antes de --apply.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.database import SessionLocal  # noqa: E402
from api.services.labs_grace import apply_grace, plan_grace  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        if apply:
            n = apply_grace(db)
            print(f"[APLICADO] entitlements de gracia creados: {n}")
        else:
            ids = plan_grace(db)
            print(f"[DRY-RUN] Elite sin Labs entitlement: {len(ids)}")
            for uid in ids:
                print(f"  user={uid}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
