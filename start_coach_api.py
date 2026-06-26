# -*- coding: utf-8 -*-
"""
Arranca el servidor de la Coach API y crea el usuario admin si no existe.
Ejecutar desde la raiz del proyecto:
    python start_coach_api.py
"""
import sys
import os

# Forzar UTF-8 en stdout para Windows cmd/powershell
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path

data_dir = Path(__file__).parent / "data"
data_dir.mkdir(exist_ok=True)

from api.database import engine, SessionLocal, Base
from api.models import User
from api.auth import hash_password

Base.metadata.create_all(bind=engine)


def migrate_db():
    """Aplica columnas nuevas a tablas existentes (solo SQLite — PostgreSQL usa create_all)."""
    from api.database import DATABASE_URL
    if not DATABASE_URL.startswith("sqlite"):
        print("[OK] PostgreSQL detectado — create_all() maneja el schema, migrate_db() omitida.")
        return
    with engine.connect() as conn:
        # Obtener columnas actuales de la tabla users
        cols = {row[1] for row in conn.execute(
            __import__('sqlalchemy').text("PRAGMA table_info(users)")
        )}
        additions = []
        if "garmin_email"      not in cols: additions.append("ALTER TABLE users ADD COLUMN garmin_email TEXT")
        if "garmin_password"   not in cols: additions.append("ALTER TABLE users ADD COLUMN garmin_password TEXT")
        if "race_goal_name"    not in cols: additions.append("ALTER TABLE users ADD COLUMN race_goal_name TEXT")
        if "race_goal_date"    not in cols: additions.append("ALTER TABLE users ADD COLUMN race_goal_date TEXT")
        if "ftp"               not in cols: additions.append("ALTER TABLE users ADD COLUMN ftp INTEGER")
        if "weight_kg"         not in cols: additions.append("ALTER TABLE users ADD COLUMN weight_kg REAL")
        if "height_cm"         not in cols: additions.append("ALTER TABLE users ADD COLUMN height_cm INTEGER")
        if "vo2max"            not in cols: additions.append("ALTER TABLE users ADD COLUMN vo2max REAL")
        if "fcmax"             not in cols: additions.append("ALTER TABLE users ADD COLUMN fcmax INTEGER")
        if "css"               not in cols: additions.append("ALTER TABLE users ADD COLUMN css TEXT")
        if "run_pace"          not in cols: additions.append("ALTER TABLE users ADD COLUMN run_pace TEXT")

        # workout_logs
        log_cols = {row[1] for row in conn.execute(
            __import__('sqlalchemy').text("PRAGMA table_info(workout_logs)")
        )}
        if "rpe" not in log_cols:
            additions.append("ALTER TABLE workout_logs ADD COLUMN rpe INTEGER")

        # assigned_workouts — coach_comment para Etapa Media
        aw_cols = {row[1] for row in conn.execute(
            __import__('sqlalchemy').text("PRAGMA table_info(assigned_workouts)")
        )}
        if "coach_comment" not in aw_cols:
            additions.append("ALTER TABLE assigned_workouts ADD COLUMN coach_comment TEXT")

        # blood_lab_exams — nueva tabla P1
        try:
            conn.execute(__import__('sqlalchemy').text("SELECT 1 FROM blood_lab_exams LIMIT 1"))
        except Exception:
            conn.execute(__import__('sqlalchemy').text(
                "CREATE TABLE IF NOT EXISTS blood_lab_exams ("
                "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, date_iso TEXT NOT NULL, "
                "lab_name TEXT, context TEXT, values_json TEXT NOT NULL, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            additions.append("CREATE TABLE blood_lab_exams")

        # nutrition_plans — nueva tabla P2
        try:
            conn.execute(__import__('sqlalchemy').text("SELECT 1 FROM nutrition_plans LIMIT 1"))
        except Exception:
            conn.execute(__import__('sqlalchemy').text(
                "CREATE TABLE IF NOT EXISTS nutrition_plans ("
                "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, race_name TEXT, "
                "race_date TEXT, race_dist TEXT, total_kcal INTEGER, "
                "cho_g REAL, fluid_ml INTEGER, sodium_mg INTEGER, "
                "params_json TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            additions.append("CREATE TABLE nutrition_plans")

        # login_attempts — rate limiting persistente
        try:
            conn.execute(__import__('sqlalchemy').text("SELECT 1 FROM login_attempts LIMIT 1"))
        except Exception:
            conn.execute(__import__('sqlalchemy').text(
                "CREATE TABLE IF NOT EXISTS login_attempts ("
                "id TEXT PRIMARY KEY, ip TEXT NOT NULL, "
                "attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
            conn.execute(__import__('sqlalchemy').text(
                "CREATE INDEX IF NOT EXISTS ix_login_attempts_ip ON login_attempts(ip)"
            ))
            conn.execute(__import__('sqlalchemy').text(
                "CREATE INDEX IF NOT EXISTS ix_login_attempts_at ON login_attempts(attempted_at)"
            ))
            additions.append("CREATE TABLE login_attempts")

        # drip_logs — control de emails de onboarding enviados
        try:
            conn.execute(__import__('sqlalchemy').text("SELECT 1 FROM drip_logs LIMIT 1"))
        except Exception:
            conn.execute(__import__('sqlalchemy').text(
                "CREATE TABLE IF NOT EXISTS drip_logs ("
                "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
                "tag TEXT NOT NULL, sent_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.execute(__import__('sqlalchemy').text(
                "CREATE INDEX IF NOT EXISTS ix_drip_logs_user ON drip_logs(user_id)"
            ))
            additions.append("CREATE TABLE drip_logs")

        for sql in additions:
            if not sql.startswith("CREATE TABLE"):
                conn.execute(__import__('sqlalchemy').text(sql))
            print("[OK] Migración: " + sql)
        if additions:
            conn.commit()


migrate_db()


def seed_admin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == "rafael@labx.com").first()
        if not existing:
            admin = User(
                email         = "rafael@labx.com",
                nombre        = "Rafael",
                password_hash = hash_password("kona2026"),
                rol           = "admin",
                plan_nivel    = "elite",
                activo        = True,
            )
            db.add(admin)

            demo_coach = User(
                email         = "demo@labx.com",
                nombre        = "Coach Demo",
                password_hash = hash_password("demo123"),
                rol           = "coach",
                plan_nivel    = "basico",
                activo        = True,
            )
            db.add(demo_coach)

            db.commit()
            print("[OK] Usuarios iniciales creados:")
            print("  admin  -> rafael@labx.com / kona2026")
            print("  coach  -> demo@labx.com   / demo123")
        else:
            print("[OK] DB lista (usuarios ya existen)")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("  LabX Coach API")
    print("=" * 50)
    seed_admin()
    print("\n  Servidor en:  http://localhost:8000")
    print("  Docs:         http://localhost:8000/docs\n")

    import uvicorn
    uvicorn.run(
        "api.coach_main:app",
        host        = "0.0.0.0",
        port        = 8000,
        reload      = True,
        reload_dirs = ["api"],
    )
