"""
P13 — /openapi.json debe seguir la misma condición que /docs y /redoc.

En producción la documentación se deshabilita salvo ENABLE_DOCS=1. Hasta este
cambio `openapi_url` no se pasaba a FastAPI, así que /openapi.json quedaba
público aunque /docs y /redoc devolvieran 404.

Igual que en test_startup_sqlite_guard.py, la app decide el modo al IMPORTAR
el módulo (la `_IS_PROD` y el constructor de FastAPI corren ahí), así que cada
caso se prueba en un subproceso con su propio entorno y se consulta con
TestClient.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Entorno que satisface la validación de arranque de producción, para aislar
# únicamente el efecto de ENABLE_DOCS sobre las rutas de documentación.
BASE_ENV = {
    "APP_ENV": "production",
    "JWT_SECRET": "j" * 48,
    # Clave Fernet válida SOLO para tests (la misma que usa el CI). No es secreta.
    "FERNET_KEY": "a8LviK0SEYpIO2ZlfS9b165x2DVbJuDswUVqZ66FlqY=",
    "ADMIN_PASS": "admin-pass-de-prueba-no-default",
    "CORS_ORIGINS": "https://labxperformanceapp.com",
    "SENTRY_DSN": "",
    "ALLOW_SQLITE_IN_PROD": "1",
}

_PROBE = """
import json
from fastapi.testclient import TestClient
from api.coach_main import app

client = TestClient(app)
codes = {p: client.get(p).status_code for p in ("/openapi.json", "/docs", "/redoc", "/health")}
print("RESULT:" + json.dumps(codes))
"""


def _codes(tmp_path, **overrides):
    """Importa la app en un subproceso y devuelve los status code de las rutas."""
    env = os.environ.copy()
    for key in ("ENABLE_DOCS", "ALLOW_SQLITE_IN_PROD"):
        env.pop(key, None)
    env.update(BASE_ENV)
    env["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'openapi.db').as_posix()}"
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    line = next(
        (ln for ln in (proc.stdout or "").splitlines() if ln.startswith("RESULT:")),
        None,
    )
    assert line, (
        f"el subproceso no devolvió resultado (exit {proc.returncode})\n"
        f"--- stdout ---\n{(proc.stdout or '')[-1500:]}\n"
        f"--- stderr ---\n{(proc.stderr or '')[-1500:]}"
    )
    return json.loads(line[len("RESULT:"):])


def test_production_sin_enable_docs_cierra_todo(tmp_path):
    codes = _codes(tmp_path, ENABLE_DOCS="0")
    assert codes["/openapi.json"] == 404
    assert codes["/docs"] == 404
    assert codes["/redoc"] == 404
    assert codes["/health"] == 200  # la app sigue viva


def test_production_con_enable_docs_1_los_expone(tmp_path):
    codes = _codes(tmp_path, ENABLE_DOCS="1")
    assert codes["/openapi.json"] == 200
    assert codes["/docs"] == 200


def test_development_sigue_abierto(tmp_path):
    """En desarrollo no cambia nada: sin ENABLE_DOCS igual responde 200."""
    codes = _codes(tmp_path, APP_ENV="development", ENABLE_DOCS=None)
    assert codes["/openapi.json"] == 200
    assert codes["/docs"] == 200
