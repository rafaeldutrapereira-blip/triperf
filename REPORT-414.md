# REPORT-414 — A3-LABS-TEAM (BUILD 414)

## Qué cambió
Un coach con invitación solo **pendiente** (`CoachAthlete.status='pending'`, `activo=True` por defecto) ya no accede a datos del atleta:

| Ruta | Antes | Ahora |
|---|---|---|
| `GET /labs/team` (`blood_lab_routes.py`) | filtraba solo `activo==True` | además `status=='active'` |
| `GET /coach/athletes/{id}/gear` (`gear_routes.py`) | idem | idem; 403 si no hay relación activa (contrato sin cambio) |
| `GET /ai/coach-copilot` (`ai_routes.py`) | `active` (= `activo`) | `activo` y `status=='active'` |

Se conserva `activo==True` además de `status` (más estricto: una relación desactivada sigue sin dar acceso). Criterio equivalente al de `permissions.py` y `adaptive_routes.py` (`status=='active'`); no hay helper compartido que reutilizar para estas consultas directas.

**Códigos de estado (sin cambio de contrato):** `/labs/team` y `/ai/coach-copilot` devuelven 200 con lista vacía/0 atletas; gear devuelve 403.

## Arreglo adicional necesario (bug previo)
`/ai/coach-copilot` usaba `u.name` (el modelo `User` tiene `nombre`): con **cualquier** relación válida la ruta fallaba con 500 (`AttributeError`). Se cambió a `u.nombre`; sin esto no se puede demostrar que la relación activa ve datos.

## Otros filtros `activo==True`
En las tres rutas no quedaban otros puntos de control de acceso con el mismo patrón.

## coach_athlete_ids (`permissions.py`) — PENDIENTE, no cambiado
La parte de relación ya usa `status=='active'` (A1), pero la función sigue **uniendo miembros de grupo** (`GroupMember`) sin exigir relación activa. No afecta a estas tres rutas (consultan `CoachAthlete` directamente), por eso no se tocó (fuera de alcance). Pendiente explícito: alinear la rama de grupos. Igual ocurre en `get_athletes_for_coach`.

## Tests
- Nuevo `api/tests/test_a3_labs_team.py`: 6 tests, 6 passed (pendiente → vacío/403/0; activa → ve datos; sin relación → vacío; gear propio del atleta intacto).
- Suite completa (`api/tests`, excluyendo los dos archivos sin seguimiento `test_zz_perf_measure.py` y `test_zz_repro.py`, que no son del repo): **3760 passed, 0 failed, 0 errors** en 28m39s. Salida en `labx-overnight/a3-pytest-full.txt`. Sin fallos preexistentes.

## Otros
- `sw.js` BUILD_VERSION 414; espejos móviles regenerados (`build_www.py` + `capacitor sync` vía node).
- Sin push, sin deploy, sin migraciones. No se tocó `/labs/parse`, rutas de examen, `permissions.py`, `athlete_routes.py` ni invitaciones.
- Alcance honesto: no se verificó en dispositivo ni contra producción; solo tests locales.
