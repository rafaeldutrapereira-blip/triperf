# REPORT 411 — SYNC-ERROR-REAL

Solo LOCAL: commit en main, sin push, sin deploy, sin migraciones. Base: HEAD BUILD 409.

## Qué cambió

1. **Rastro del sync manual** (`api/routes/garmin_official_routes.py`): cada `POST /integrations/garmin/sync` escribe `[GARMIN-SYNC] inicio user=<id>` y `[GARMIN-SYNC] fin user=<id> result=<causa> dur_s=<s> detail=<error exacto>`. Solo log (logger `labx.garmin_official`); sin tablas.
2. **Error honesto por causa**: el endpoint clasifica el fallo del pull leyendo el mensaje de `GarminOfficialError` (el pull no se tocó):
   - `pull_timeout` — «Garmin tardó demasiado en responder» (mensaje con `Timeout`)
   - `garmin_error` — «Garmin devolvió un error» (5xx o sin respuesta)
   - `pull_failed` — rechazo 401/403 u otra respuesta (mensaje anterior, sin cambios)
   - `needs_reconnect` / `not_connected` / `unavailable` — igual que antes
   El frontend (`athlete-app.html`, `athlete_profile.html`) mapea las dos causas nuevas y, cuando la petición se corta (`.catch`), muestra «Se cortó la conexión con LabX antes de terminar» en vez del `gsync_err` genérico. i18n ES/PT/EN: `gsync_timeout`, `gsync_garmin_error`, `gsync_network`.
3. **Ingest idempotente** (`api/garmin_ingest.py`): las inserciones de actividad, sueño y diario van en un SAVEPOINT (`_insert_ignoring_duplicate`). Si otra vía ya insertó la misma clave única, se ignora en silencio (sin `IntegrityError` ni log) y el resto de la transacción queda intacto.
4. `sw.js` BUILD_VERSION `'411'` + changelog. Espejos móviles regenerados con `build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`.

## Tests

- Nuevos: `api/tests/test_sync_error_real_411.py` (log del intento, error por causa, mapeo front/i18n, duplicados de actividad y sueño, duplicado sin romper el lote): 55 passed junto con `test_sync_conexiones_379.py`.
- Existente de la zona: `test_sync_conexiones_379.py` en verde (55 passed entre ambos archivos).
- **Suite completa** (`pytest api -x`, log en `labx-overnight/sync411-pytest.txt`): 0 F / 0 E; 3705 puntos de progreso en verde y 1 skip/xfail. Sin fallos preexistentes. Nota: por el doble `-q` pytest no imprimió la línea resumen final, el conteo sale de los marcadores de progreso (no de un total reportado por pytest).

## Alcance y honestidad

- No se tocó OAuth, tokens, refresh, el pull (siguen las 7 ventanas de 24 h, 20 s c/u) ni Polar/Wahoo.
- **El timeout de Cloudflare (~100 s) NO está resuelto**: el pull sigue pudiendo tardar hasta ~140 s. Si Cloudflare corta antes, el navegador ve un corte de red y verá «Se cortó la conexión…»; el rastro `[GARMIN-SYNC]` del servidor dirá si el pull terminó o falló. Acortar/paralelizar el pull queda fuera de esta pila.
- La clasificación se basa en el texto de `GarminOfficialError`; si ese texto cambia, cae a `pull_failed` (mensaje genérico previo).
- El token OAuth del coach venció el 22/11 21:09: **el refresh del token vencido se ejercerá por primera vez en el próximo sync manual real**. No se probó contra Garmin real y no es parte de esta pila.
- Los duplicados del push se verificaron simulando la carrera con mocks (consulta previa que no ve la fila); no se reprodujo contra la BD de producción.
