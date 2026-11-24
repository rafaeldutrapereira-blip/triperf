# REPORT — fix exposición de la raíz estática (LabX)

Fecha: 2026-11-24 · Base: BUILD 411 (3579cd9) · Commit SOLO LOCAL (sin push ni deploy).

## Verificación previa
`git diff --quiet` y `git diff --cached --quiet`: ambos limpios (solo había archivos sin rastrear ajenos al fix; no se tocaron).

## Cambio
`api/coach_main.py`: el mount `StaticFiles(directory=_ROOT_DIR, html=True)` pasa a `_PublicStaticFiles`, una subclase que devuelve 404 antes de tocar disco cuando la ruta no es frontend público:

- cualquier segmento que empiece por `.` (`.env`, `.git/...`, `.github`) o `..`;
- primer directorio en una lista de bloqueo (`data`, `backups`, `logs`, `api`, `alembic`, `deploy`, `scripts`, `tests`, `utils`, `models`, `node_modules`, `audits`, `nginx`, `docs`, `e2e`, `android`, `ios`, `www`, `store-assets`, `assets_onepager`, `__pycache__`);
- extensión fuera de una lista permitida (html/htm/js/mjs/css/json/webmanifest/xml/svg/png/jpg/jpeg/gif/webp/ico/avif/fuentes/map/mp3/mp4/pdf). Con esto `.db`, `.sqlite*`, `.py`, `.md`, `.log`, `.txt`, `.ps1`, `.cmd`, `.example`, etc. dan 404. Única excepción `.txt`: `robots.txt` y `security.txt`.

Se decodifica el path (`%2e`) antes de evaluar. Se eligió guard (no directorio público dedicado) para no reestructurar la app.

`api/tests/test_static_root_guard.py`: nuevo, 11 rutas bloqueadas + 4 públicas.

## Pruebas locales (uvicorn real en :8765, curl `--path-as-is`)
| Ruta | Resultado |
|---|---|
| /.env | 404 |
| /%2e%65nv (codificado) | 404 |
| /vendor/../.env | 404 |
| /.git/config | 404 |
| /data/ , /data/x.db | 404 |
| /x.db, /x.sqlite3 | 404 |
| /requirements-api.txt | 404 |
| /api/coach_main.py | 404 |
| / | 200 |
| /sw.js | 200 |
| /public_activity.html | 200 |
| /dashboard.html | 200 |
| /vendor/chart.umd.min.js | 200 |
| /health | 200 |

Tests: `test_static_root_guard.py` + `test_plan_gating_b1.py` → 53 passed. Suite completa: ver nota abajo.

## Riesgos / notas
- Antes de este fix `/requirements-api.txt`, `/CLAUDE.md` y otros .md/.py de la raíz también eran públicos; ahora son 404. Si alguna pantalla dependía de un `.md`/`.txt` de la raíz, dará 404 (revisé referencias en *.html/*.js a directorios bloqueados: ninguna).
- Si se agrega un tipo de asset nuevo (p. ej. `.wasm`, `.csv`), hay que sumarlo a `_STATIC_ALLOWED_EXT`.
- `.well-known/` (dotfile) queda bloqueado; hoy no existe en la raíz. Si se necesita (assetlinks/apple-app-site-association), añadir excepción.
- Esto NO rota secretos: el `.env` estuvo expuesto en producción, la rotación (RESEND_API_KEY, JWT_SECRET, DATABASE_URL, etc.) debe hacerse tras el deploy, por separado.
- Tras el deploy, verificar en vivo `https://labxperformanceapp.com/.env` → 404. Este cambio no toca `sw.js`, por lo que no requiere bump de BUILD_VERSION.
