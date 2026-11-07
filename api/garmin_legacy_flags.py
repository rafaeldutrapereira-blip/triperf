"""RETIRO-1: interruptores del conector Garmin legacy (email + contrasena).

Se leen del entorno en cada llamada (sin cache) para poder cambiarlos sin
reiniciar tests ni depender del orden de import.

- GARMIN_LEGACY_CONNECT_ENABLED: default CERRADO. Solo "1" permite conexiones
  NUEVAS por credenciales (valvula de escape para testes/emergencias).
- GARMIN_LEGACY_SYNC_ENABLED: default ENCENDIDO. "0" apaga TODA entrada al
  sync legacy (manual, dispatch/notify, login, scheduler, Celery, provider).
"""
import os

CONNECT_CLOSED_MESSAGE = (
    "La conexión Garmin por contraseña está cerrada; "
    "conecta tu Garmin con el botón principal."
)


def legacy_connect_enabled() -> bool:
    return os.getenv("GARMIN_LEGACY_CONNECT_ENABLED", "").strip() == "1"


def legacy_sync_enabled() -> bool:
    return os.getenv("GARMIN_LEGACY_SYNC_ENABLED", "").strip() != "0"
