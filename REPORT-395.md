# REPORT-395 — GARMIN-OAUTH-RETURN (BUILD 395)

## Causa raíz (verificada en código)
El enunciado decía que `WEARABLE_OAUTH` no incluía garmin y por eso no había aviso, sync ni vuelta. En `main` (dd82859) eso ya estaba **parcialmente resuelto por la 379**, y la lista `WEARABLE_OAUTH = ['polar','wahoo']` se dejó así a propósito (una tarjeta por marca; la de Garmin ya existe en `_garminRow`; un test de la 379 lo fija).

Flujo real:
1. `api/routes/garmin_official_routes.py` `/integrations/garmin/callback` redirige a `/athlete-app.html?garmin=connected|denied|error|error_state` (`_redirect`).
2. `athlete-app.html` `initApp()` llama `garminReturnRead()` (lee `q.get('garmin')`, limpia el parámetro con `history.replaceState`) y `garminReturnConsume()`.
3. `garminReturnConsume()` mostraba el toast (`garmin_ret_ok`) y navegaba a Hoy (o a `dashboard.html` dentro del marco de la shell), pero **nunca llamaba a `POST /integrations/garmin/sync`**. El callback tampoco dispara sync del lado servidor. Ese es el defecto que queda: tras conectar no se traía ninguna actividad hasta que el atleta pulsaba el botón manual de Perfil.

Aviso y vuelta al dashboard: ya funcionaban (379). Lo que faltaba: el sync.

## Arreglo (mínimo, solo frontend)
`athlete-app.html`:
- `garminOfficialSync()` ahora devuelve la promesa (y `Promise.resolve()` si ya hay uno en curso).
- `garminReturnConsume()`: con `connected`, tras 1,5 s (para que se lea el aviso) dispara `garminOfficialSync()` (mismo endpoint y mensajes honestos `gsync_*` del botón manual). Dentro de la shell la navegación a `dashboard.html` espera a que el sync termine (tope 10 s) + 1,2 s; navegar antes habría abortado la petición en vuelo. Fuera de la shell va a Hoy y el sync corre de fondo. `denied`/`error` no sincronizan.
- Sin claves i18n nuevas: se reutilizan `garmin_ret_*` y `gsync_*` (ya existen ES/PT/EN). Sin colores ni texto fijo nuevos.
- Polar/Wahoo intactos (`WEARABLE_OAUTH`, `wearableReadReturn`, `_wearConsumeReturn` no se tocaron; test lo afirma).

BUILD 395: `sw.js` (`BUILD_VERSION`, línea de changelog reemplazada según convención de la 394, `/i18n.js?v=395`), sello `i18n.js?v=395` en todas las páginas y en los asserts de 391/392/393/394 que lo fijaban.

## Archivos
`athlete-app.html`, `sw.js`, 35 páginas `.html` (solo sello `i18n.js?v=`), `tests/js/garmin_return_395.test.js` (nuevo), `tests/js/bloodlabs_{simple_391,tabla_392,tendencias_393}.test.js`, `api/tests/test_bloodlabs_ejecutiva.py`, `api/tests/test_recuperacion_394.py` (solo 394→395). Sin migraciones, sin backend. No se tocó www/android/ios.

## Verificación
- Test nuevo `tests/js/garmin_return_395.test.js`: contra athlete-app.html de la base, 3 de 6 fallan (retorno connected sin sync, promesa); con el arreglo 6/6.
- `npm run test:js`: 282 pass, 0 fail.
- pytest (`api/tests`): **3650 passed, 2 failed, 1 skipped**. Los 2 fallos son los conocidos y no son regresión: `test_i18n.py::test_mobile_mirrors_match_root_i18n` y `::test_mobile_mirrors_match_root_sw` (copias gitignoradas www/android/ios sin regenerar; en CI se saltan). `test_calendario_vivo_375` pasó.
- Commit: local en main, sin push ni deploy (mensaje: feat(wearables): retorno OAuth de Garmin completo (GARMIN-OAUTH-RETURN, BUILD 395)).

## Pendiente / observaciones
- No probado en dispositivo real ni con Garmin real (el OAuth no es ejecutable aquí).
- Si el sync oficial falla (`needs_reconnect`, etc.), el atleta ve el mensaje de error de `garminSyncMessage` y luego el dashboard.
