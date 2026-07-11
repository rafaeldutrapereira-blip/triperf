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

# Cargar .env ANTES de importar módulos de la API (leen vars de entorno al importar)
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

data_dir = Path(__file__).parent / "data"
data_dir.mkdir(exist_ok=True)

from api.database import engine, SessionLocal, Base
from api.models import User
from api.auth import hash_password

Base.metadata.create_all(bind=engine)


def run_alembic_upgrade():
    """Run alembic upgrade head to apply all pending migrations."""
    from pathlib import Path as _Path
    from api.database import DATABASE_URL
    try:
        from alembic.config import Config as _AlembicConfig
        from alembic import command as _alembic_command
        cfg = _AlembicConfig(str(_Path(__file__).parent / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
        _alembic_command.upgrade(cfg, "head")
        print("[OK] Alembic upgrade head completado")
    except Exception as e:
        print(f"[WARN] Alembic upgrade falló: {e} — continuando (create_all ya aplicó el schema)")


run_alembic_upgrade()


def seed_admin():
    _is_prod = os.getenv("APP_ENV", "development") == "production"

    admin_email  = os.getenv("ADMIN_EMAIL",  "admin@labx.com")
    admin_pass   = os.getenv("ADMIN_PASS",   "")
    admin_nombre = os.getenv("ADMIN_NOMBRE", "Admin")
    demo_email   = os.getenv("DEMO_EMAIL",   "demo@labx.com")
    demo_pass    = os.getenv("DEMO_PASS",    "")

    if _is_prod and not admin_pass:
        import sys
        print("[FATAL] ADMIN_PASS no configurada. No se puede seed en producción sin contraseña.")
        sys.exit(1)

    # En desarrollo, usar contraseña temporal si no está configurada
    if not admin_pass:
        admin_pass = "labx-dev-change-me"
        print("[WARN] ADMIN_PASS no configurada — usando contraseña temporal (solo dev)")
    if not demo_pass:
        demo_pass = "labx-dev-change-me"

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == admin_email).first()
        if not existing:
            admin = User(
                email         = admin_email,
                nombre        = admin_nombre,
                password_hash = hash_password(admin_pass),
                rol           = "admin",
                plan_nivel    = "elite",
                activo        = True,
            )
            db.add(admin)

            demo_coach = User(
                email         = demo_email,
                nombre        = "Coach Demo",
                password_hash = hash_password(demo_pass),
                rol           = "coach",
                plan_nivel    = "basico",
                activo        = True,
            )
            db.add(demo_coach)

            db.commit()
            # No imprimir contraseñas en producción
            print(f"[OK] Usuarios iniciales creados: {admin_email} (admin), {demo_email} (coach)")
        else:
            print("[OK] DB lista (usuarios ya existen)")
    finally:
        db.close()


if __name__ == "__main__":
    _is_prod = os.getenv("APP_ENV", "development") == "production"
    _port    = int(os.getenv("PORT", "8000"))

    print("=" * 50)
    print("  LabX Coach API")
    print(f"  Env: {os.getenv('APP_ENV', 'development')}")
    print("=" * 50)
    seed_admin()
    print(f"\n  Servidor en:  http://localhost:{_port}")
    if not _is_prod:
        print(f"  Docs:         http://localhost:{_port}/docs")
    print()

    import uvicorn
    uvicorn.run(
        "api.coach_main:app",
        host        = "0.0.0.0",
        port        = _port,
        reload      = not _is_prod,
        reload_dirs = ["api"] if not _is_prod else None,
    )
