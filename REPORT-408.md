# REPORT-408 — GARMIN-RETORNO-WEB

## Qué cambió
- `api/routes/garmin_official_routes.py`: el callback ya conoce al usuario (el `state` consumido devuelve `user_id`), así que consulta `users.rol`. `coach`/`admin` → `/dashboard.html?garmin=<resultado>`; atleta (y cualquier caso sin state válido) → `/athlete-app.html?garmin=...` como antes. Solo cambia el destino del redirect; OAuth, tokens y sync intactos.
- `dashboard.html`: `garminReturnConsume()` lee `?garmin=connected|denied|error|error_state`, muestra el aviso (claves i18n existentes `garmin_ret_ok/denied/err`) y limpia el parámetro de la URL.
- `sw.js`: BUILD_VERSION `'408'` + changelog. Espejos móviles regenerados (`build_www.py` + `node .../capacitor sync`).
- Tests: 6 nuevos en `api/tests/test_garmin_official.py` (coach→dashboard, atleta→app, denied/error por rol, sin state→app, sin tarjeta duplicada al reconectar, dashboard consume el parámetro). Se actualizó el pin `BUILD_VERSION` 407→408 en 3 tests Python existentes.

## Decisión de destino
Se redirige a `/dashboard.html` directo (no `shell.html?p=dashboard.html`): la shell carga el iframe sin reenviar query params, así el aviso se perdería. Stripe ya usa `/dashboard.html?...` igual.

## Evidencia
- `pytest api`: **3686 passed, 1 skipped, 0 failed** (log: `labx-overnight/pytest408.txt`).
- `npm run test:js`: 313 pass, **9 fail — preexistentes**: tests JS que fijan `BUILD_VERSION = '404'` (ya rotos desde 405–407). No se tocaron.
- Verificación en navegador real del aviso: no hecha (solo tests estáticos del HTML).

## Alcance honesto
- El sync posterior a la reconexión **sigue sin correr**; no es parte de esta pila.
- Polar/Wahoo no se tocaron. Sin migraciones, sin push, sin deploy.
