# REPORT-398 — PERFIL (BUILD 398)

## Dónde vive Perfil
- Página: `athlete_profile.html` (ruta `athlete_profile`). Carga datos con `GET /athlete/profile` (`loadProfile`), carreras (`loadRaces`), estado de Garmin/wearables/intervals.icu (`_gModel`, `_wearState`), invitaciones de coach (`_pendingInvites`), sesiones, privacidad, add-ons.
- Contenido real: cabecera «Tu cuenta en una mirada» (PERFIL-ORDEN 351, datos clave + conexiones), medidor «Perfil completo: N de M», pestañas Mis datos (datos personales, Mis carreras, pliegue «Mis marcas y zonas»), Conexiones, y Cuenta (add-ons, privacidad, contraseña, 2FA, notificaciones, sesiones, zona de peligro).

## Estado encontrado
Ya tenía una cabecera «en una mirada» y un pliegue de marcas/zonas (351), pero ninguna frase de respuesta en palabras, y contraseña/2FA/notificaciones/sesiones estaban siempre abiertas.

## Cambios
- **Capa 1:** `#prof-answer` arriba, con una frase armada por `renderProfileAnswer()` (llamada desde `renderAccountGlance`, que ya se repinta con cada fuente) con datos reales: cuántos datos le faltan al perfil y cuáles (`profileCompleteness`, el mismo cálculo del medidor), conexiones activas (`accountGlanceConns`; la frase de conexiones se omite mientras alguna está «consultando»), invitaciones de coach pendientes. Sin cifras nuevas.
- **Capa 2:** la cabecera existente (datos + conexiones) con una línea de porqué (`#prof-why`: LabX usa estos datos para zonas y rangos de exámenes, coherente con `PROFILE_FIELDS`). Medidor, índice y pestañas sin cambios.
- **Capa 3:** `<details id="prof-l3-account">` plegado con contraseña, verificación en dos pasos (2FA), notificaciones y sesiones. Zona de peligro, add-ons, privacidad e invitaciones quedan visibles. Todos los ids y handlers se conservan (test 351 intacto).
- Solo variables de tema. i18n: 7 claves nuevas ES/PT/EN (`prof_why`, `prof_ans_*`, `prof_l3_account`). Sin backend, sin migraciones.
- Sellos: `BUILD_VERSION='398'` con changelog; `i18n.js?v=398` en páginas, `sw.js` y asserts de tests previos.
- Corrección menor: la línea de changelog de la 397 en `sw.js` decía «12 claves»; conté 13 claves `rd_*` en el diff de la 397 (rd_ans_ x6, rd_hist_ x6, rd_l3_record). La convención reemplaza la línea de cada build, así que esa línea ya no existe; `REPORT-397.md` ya decía 13 y no se tocó.

## Se mantuvo
Todo el contenido existente de Perfil, solo cambió la presentación.

## Tests
- Nuevo `tests/js/perfil_398.test.js` (5 tests), agregado a `test:js`. En la base (sin `athlete_profile.html`/`i18n.js` nuevos) fallan 5 de 5; con el cambio pasan.
- `npm run test:js`: **309 tests, 309 pass, 0 fail** (304 + 5).
- Espejos móviles regenerados con `build_www.py` + `cap sync`; árbol rastreado sin cambios inesperados.
- pytest: ver abajo.

## pytest (api/tests)
**3659 passed, 0 failed, 1 skipped** (28 min). Los 2 tests de espejos móviles pasan (copias regeneradas); `test_calendario_vivo_375` no falló esta vez. Log: `C:\Users\rafae\labx-overnight\perfil398.log` (copia de `perfil398_run.log`; el log original estaba bloqueado por un proceso previo).

## Commit
Solo local en main: `feat(perfil): capa ejecutiva en Perfil (PERFIL, BUILD 398)`. Sin push, sin deploy, sin migraciones. Los archivos sin seguimiento previos (`_*.py`, `data/`, etc.) no se incluyen.
