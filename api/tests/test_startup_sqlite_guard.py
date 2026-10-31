"""
P12 — Guard de SQLite en producción (ALLOW_SQLITE_IN_PROD).

La validación de arranque vive dentro de `if _IS_PROD:` en api/coach_main.py y
corre al IMPORTAR el módulo. Por eso se prueba en un subproceso: importarlo en
el proceso de pytest abortaría la suite entera con sys.exit(1).

Contrato:
  - DATABASE_URL vacía                      → aborta (con o sin flag).
  - DATABASE_URL SQLite, sin flag           → aborta.
  - DATABASE_URL SQLite, ALLOW_SQLITE_IN_PROD=1 → arranca + warning.
  - ALLOW_SQLITE_IN_PROD con otro valor     → aborta (solo "1" exacto).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Entorno que satisface el RESTO de la validación de producción, para que los
# tests aislen únicamente el guard de SQLite.
BASE_ENV = {
    "APP_ENV": "production",
    "JWT_SECRET": "j" * 48,                     # >=32 chars, no es default
    # Clave Fernet válida SOLO para tests (la misma que usa el CI). No es secreta.
    "FERNET_KEY": "a8LviK0SEYpIO2ZlfS9b165x2DVbJuDswUVqZ66FlqY=",
    "ADMIN_PASS": "admin-pass-de-prueba-no-default",
    "CORS_ORIGINS": "https://labxperformanceapp.com",
    "SENTRY_DSN": "",
    "ENABLE_DOCS": "0",
}


def _startup(tmp_path, *, database_url, flag=None):
    """Importa api.coach_main en un subproceso con el entorno indicado."""
    env = os.environ.copy()
    env.pop("ALLOW_SQLITE_IN_PROD", None)
    env.pop("DATABASE_URL", None)
    env.update(BASE_ENV)
    db_path = (tmp_path / "startup.db").as_posix()
    env["DATABASE_URL"] = database_url.format(db=db_path) if database_url else ""
    if flag is not None:
        env["ALLOW_SQLITE_IN_PROD"] = flag

    proc = subprocess.run(
        [sys.executable, "-c", "import api.coach_main"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return proc, (proc.stdout or "") + (proc.stderr or "")


def test_prod_sqlite_sin_flag_aborta(tmp_path):
    proc, out = _startup(tmp_path, database_url="sqlite:///{db}")
    assert proc.returncode != 0, out[-2000:]
    assert "STARTUP ABORTADO" in out
    assert "SQLite" in out


def test_prod_sqlite_con_flag_arranca_y_avisa(tmp_path):
    proc, out = _startup(tmp_path, database_url="sqlite:///{db}", flag="1")
    assert proc.returncode == 0, out[-2000:]
    assert "SQLite en producción permitido explícitamente por ALLOW_SQLITE_IN_PROD=1" in out
    assert "pendiente migración a PostgreSQL" in out


def test_flag_con_otro_valor_no_habilita(tmp_path):
    proc, out = _startup(tmp_path, database_url="sqlite:///{db}", flag="true")
    assert proc.returncode != 0, out[-2000:]
    assert "STARTUP ABORTADO" in out


def test_database_url_vacia_no_arranca_incluso_con_flag(tmp_path):
    """Vacía nunca arranca.

    Ojo: con DATABASE_URL="" el proceso muere ANTES del guard, en
    api/database.py (create_engine no puede parsear ""), así que el mensaje es
    de SQLAlchemy y no "STARTUP ABORTADO". Lo que importa —y se verifica— es
    que el flag no lo haga arrancar igual.
    """
    proc, out = _startup(tmp_path, database_url="", flag="1")
    assert proc.returncode != 0, out[-2000:]
    assert "permitido explícitamente" not in out
