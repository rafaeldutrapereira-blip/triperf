"""
URL pública de la app, usada para enlaces en correos, redirecciones de pago y
URLs de archivos locales.

Producción carga .env, que no define APP_URL: sin esta función, cada módulo caía
en su propio valor por defecto (localhost) y los enlaces llegaban rotos.
Si APP_URL está definida (y no vacía), se respeta.
"""
import os

PUBLIC_APP_URL = "https://labxperformanceapp.com"


def get_app_url() -> str:
    raw = (os.getenv("APP_URL") or "").strip()
    return (raw or PUBLIC_APP_URL).rstrip("/")
