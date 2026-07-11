"""
Normalización de roles: unifica 'athlete' → 'atleta' en la tabla users.

Uso:
    cd C:\\Users\\rafae\\projects\\LabX
    python -m scripts.migrate_normalize_roles [--dry-run]
"""
import sys
import os
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/labx_coach.db")
if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if not Path(db_path).is_absolute():
        db_path = str(Path(__file__).resolve().parent.parent / db_path)
else:
    print(f"ERROR: Solo soporta SQLite. DATABASE_URL={DATABASE_URL}")
    sys.exit(1)


def run_migration(dry_run: bool = False) -> None:
    if not Path(db_path).exists():
        print(f"ERROR: No se encontró la DB en {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    distinct_roles = [r[0] for r in cur.execute("SELECT DISTINCT rol FROM users").fetchall()]
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Roles actuales en DB: {distinct_roles}\n")

    rows = cur.execute("SELECT id, email, rol FROM users WHERE rol = 'athlete'").fetchall()
    print(f"Usuarios con rol='athlete' (legacy): {len(rows)}")

    for row in rows:
        uid   = row["id"]
        email = (row["email"] or uid)[:40]
        action = "se cambiaría" if dry_run else "cambiado ✅"
        print(f"  👤 {email:<40}  athlete → atleta  ({action})")
        if not dry_run:
            cur.execute("UPDATE users SET rol='atleta' WHERE id=?", (uid,))

    if not dry_run and rows:
        conn.commit()

    conn.close()

    print(f"""
{'─'*60}
RESUMEN {'(DRY RUN)' if dry_run else ''}
  Usuarios migrados: {len(rows)}
{'─'*60}
""")

    if not rows:
        print("OK: No hay roles 'athlete' en la DB. Nada que hacer.")
    elif not dry_run:
        print("OK: Roles normalizados. Solo 'atleta' existe ahora.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run_migration(dry_run=dry)
