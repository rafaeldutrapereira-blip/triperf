"""
Script de inicio para Railway/producción.
Ejecuta migraciones, seed del admin, luego arranca uvicorn en $PORT.
"""
import os
import sys

# Migraciones y seed (sin arrancar uvicorn)
import start_coach_api
start_coach_api.seed_admin()

# Arrancar uvicorn en el puerto que Railway provee
port = int(os.getenv("PORT", "8000"))
import uvicorn
uvicorn.run(
    "api.coach_main:app",
    host="0.0.0.0",
    port=port,
    reload=False,
    workers=1,
)
