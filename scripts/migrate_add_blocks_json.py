"""
Migración: agrega columna blocks_json a workout_templates (si no existe).
Ejecutar UNA VEZ: python scripts/migrate_add_blocks_json.py
"""
import sqlite3, os, sys

DB_PATHS = [
    "labx.db",
    "api/labx.db",
    "coach.db",
    "api/coach.db",
]

def find_db():
    for p in DB_PATHS:
        if os.path.exists(p):
            return p
    return None

def migrate(db_path: str):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("PRAGMA table_info(workout_templates)")
    cols = [row[1] for row in cur.fetchall()]
    if "blocks_json" in cols:
        print(f"[{db_path}] blocks_json ya existe — nada que hacer.")
    else:
        cur.execute("ALTER TABLE workout_templates ADD COLUMN blocks_json TEXT")
        con.commit()
        print(f"[{db_path}] ✓ Columna blocks_json añadida.")
    con.close()

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else find_db()
    if not db:
        print("No se encontró ninguna base de datos. Pasa la ruta como argumento.")
        sys.exit(1)
    migrate(db)
