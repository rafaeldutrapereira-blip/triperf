# REPORT-412 — H1-XSS (BUILD 412)

## Qué cambió
- `public_activity.html`: se agregó `esc()` (copia de `shared_plan.html`) y se aplica a `d.owner.name`, `d.name`, la inicial del avatar, `d.date_iso`, `s.v`/`s.l` de los stats y el `msg` de `empty()`. Revisado el archivo completo: ya no queda interpolación cruda de datos de usuario. Los textos de `_t()` (i18n propios) no se escapan. `avatar_url` NO se tocó (el servidor lo construye como `/api/athlete/profile/avatar/<id>`), `d.route_preview` solo se usa como datos numéricos en Leaflet.
- `api/auth.py`: nuevo `clean_display_name()`, único punto de validación (reutilizable por ENDURECIMIENTO/mailer).
- `api/routes/athlete_routes.py` (`PATCH /athlete/profile`) y `api/routes/auth_routes.py` (`/auth/register`, cuenta nueva y reclamo de invitación) lo usan.
- `sw.js`: BUILD_VERSION 412 + línea de changelog. Espejos móviles regenerados (`build_www.py` + `node .../capacitor sync`).
- Tests: `api/tests/test_h1_xss_nombres.py` (24).

## Criterio exacto de validación
Tras `strip()`, se rechaza con HTTP 422 (`detail.code = invalid_name`) todo nombre que contenga `<`, `>` o caracteres de control (ord < 32 o 127). Se permiten acentos, espacios, apóstrofes (`'` y `’`), guiones, `&`, puntos. Se eligió rechazar y no neutralizar, para que el atleta vea el error y no se guarde un nombre alterado en silencio; `<`/`>` son lo mínimo necesario para abrir una etiqueta y no aparecen en nombres reales. Un nombre vacío mantiene el comportamiento previo (se ignora en el perfil; en el reclamo conserva el existente).

## Evidencia
- `test_h1_xss_nombres.py`: 24 passed.
- Suite completa `pytest api`: **3746 passed, 1 skipped, 0 failed** (log: `labx-overnight/h1-xss-full.log`). Una corrida previa con `-x` falló `test_mobile_mirrors_match_root_sw` por espejos desactualizados; resuelto regenerándolos.
- `npm run test:js`: 313 pass, **9 fail — preexistentes**: idénticos con y sin mis cambios (verificado con `git stash`); son tests que fijan `BUILD_VERSION = '404'` en sw.js (HEAD ya estaba en 411). No se tocaron.

## Honestidad del alcance
- Los nombres YA guardados en la BD con `<`/`>` no se migran (sin migraciones); quedan neutralizados solo por el escape de la página. Otros lugares que muestren `nombre` con `innerHTML` o plantillas de correo NO se revisaron aquí (el correo lo cubre ENDURECIMIENTO).
- El nombre de actividad (`d.name`, viene de Garmin) no se valida en servidor; el endpoint público lo devuelve crudo y la defensa es el escape en la página.
- Otros caminos que fijan `User.nombre` (p. ej. coach que invita atletas, intervals/OAuth) no se cambiaron.
- No se tocó la CSP (`unsafe-inline` sigue). Sin push ni deploy.
- Nota de numeración: commits recientes mencionan BUILD 414/415 en sus mensajes, pero `sw.js` estaba en 411; se usó 412 según `build-h1-xss.txt`.
