"""
Migración de seguridad: cifra todas las contraseñas Garmin que están en texto plano.
Usa SQL directo (no ORM) para evitar dependencias de columnas no existentes en la DB.

Uso:
    cd C:\\Users\\rafae\\projects\\LabX
    python -m scripts.migrate_encrypt_garmin_passwords [--dry-run]
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

_fernet_key = os.getenv("FERNET_KEY", "")
if not _fernet_key:
    print("ERROR: FERNET_KEY no configurada. Configura la variable y vuelve a ejecutar.")
    sys.exit(1)

from api.crypto import encrypt_if_plain, is_encrypted

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/labx_coach.db")
if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if not Path(db_path).is_absolute():
        db_path = str(Path(__file__).resolve().parent.parent / db_path)
else:
    print(f"ERROR: Este script solo soporta SQLite. DATABASE_URL={DATABASE_URL}")
    sys.exit(1)


def run_migration(dry_run: bool = False) -> None:
    if not Path(db_path).exists():
        print(f"ERROR: No se encontró la base de datos en {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        "SELECT id, email, garmin_password FROM users "
        "WHERE garmin_password IS NOT NULL AND garmin_email IS NOT NULL"
    ).fetchall()

    total = len(rows)
    already_encrypted = 0
    migrated = 0
    failed = 0

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Analizando {total} usuario(s) con credenciales Garmin...\n")

    for row in rows:
        uid   = row["id"]
        email = (row["email"] or uid)[:35]
        pwd   = row["garmin_password"]

        if is_encrypted(pwd):
            already_encrypted += 1
            print(f"  ✓  {email:<35}  ya cifrada   (len={len(pwd)})")
            continue

        new_pwd = encrypt_if_plain(pwd)
        if not new_pwd or not is_encrypted(new_pwd):
            failed += 1
            print(f"  ✗  {email:<35}  FALLO al cifrar")
            continue

        if not dry_run:
            cur.execute(
                "UPDATE users SET garmin_password = ? WHERE id = ?",
                (new_pwd, uid)
            )
            conn.commit()

        migrated += 1
        action = "se cifraría" if dry_run else "cifrada ✅"
        print(f"  🔒 {email:<35}  {action}  (plaintext len={len(pwd)})")

    conn.close()

    print(f"""
{'─'*65}
RESUMEN {'(DRY RUN — ningún cambio aplicado)' if dry_run else ''}
  Total usuarios con Garmin : {total}
  Ya cifradas               : {already_encrypted}
  Migradas                  : {migrated}
  Fallidas                  : {failed}
{'─'*65}
""")

    if failed > 0:
        print("ADVERTENCIA: Contraseñas que no se pudieron cifrar. Verificar FERNET_KEY.")
        sys.exit(2)
    elif migrated == 0:
        print("OK: Todas las contraseñas ya estaban cifradas. Nada que hacer.")
    elif not dry_run:
        print("OK: Migración completada. Verificar con --dry-run que todo quedó en estado cifrado.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run_migration(dry_run=dry)
