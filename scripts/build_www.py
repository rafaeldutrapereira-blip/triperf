"""
Sprint 55 (multi-marca / app nativa) — genera www/ para Capacitor.

Capacitor empaqueta TODO lo que haya en `webDir` dentro del APK/IPA final
(queda legible para cualquiera que decompile la app). Por eso esto usa
una whitelist estricta de extensiones de frontend en vez de copiar la
raiz del repo entera -- ahi tambien viven .env/.env.production con
secretos reales, que jamas deben terminar dentro de un app bundle.

Uso: python scripts/build_www.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WWW = ROOT / "www"

_ALLOWED_EXT = {".html", ".js", ".css", ".svg", ".png", ".ico", ".json"}
_EXCLUDE_NAMES = {"package.json", "package-lock.json", "capacitor.config.json"}


def build():
    if WWW.exists():
        shutil.rmtree(WWW)
    WWW.mkdir(parents=True)

    copied = 0
    for f in ROOT.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in _ALLOWED_EXT:
            continue
        if f.name in _EXCLUDE_NAMES:
            continue
        shutil.copy2(f, WWW / f.name)
        copied += 1

    # Capacitor exige un index.html como entry point del webDir. El punto
    # de entrada real de la app es athlete-app.html (ver manifest.json:
    # start_url) -- se copia tal cual como index.html, sin duplicar
    # mantenimiento del contenido.
    entry = ROOT / "athlete-app.html"
    if entry.exists():
        shutil.copy2(entry, WWW / "index.html")
        copied += 1

    print(f"www/ generado con {copied} archivos (whitelist: {sorted(_ALLOWED_EXT)})")


if __name__ == "__main__":
    build()
