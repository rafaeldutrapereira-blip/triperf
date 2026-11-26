# REPORT-419 — CLOUDFLARE-SYNC

## Medición (antes de cambiar)
- **Código original:** 7 ventanas de 24 h en serie, `timeout=20` s cada una → peor caso 7×20 = **140 s** (> corte ~100 s de Cloudflare); además la primera ventana fallida abortaba el pull y descartaba las demás.
- **Datos reales NO disponibles:** el log `[GARMIN-SYNC]` de producción no está en este equipo y el token OAuth del coach solo existe en la VM (BD local sin filas en `garmin_oauth_tokens`); un probe contra la API real habría exigido tocar producción, vetado por el SPEC. **No hay latencia real por ventana medida.** Lo que sí hay: el cálculo por cotas (timeout) y una simulación con latencia (escala 1:10):
  - normal (0,2 s/ventana): secuencial 1,40 s → paralelo(4) 0,41 s
  - peor (2,0 s/ventana, = 20 s reales): secuencial 14,0 s → paralelo(4) 4,0 s (≙ 40 s reales)
- Se añadió al log `[GARMIN-SYNC] ventanas user=… dur_s=[…] fallidas=N` para obtener la medición real por ventana en el próximo sync en producción.

## Arreglo elegido: (a) paralelizar con pool acotado
`fetch_recent_activities_detailed` (api/garmin_official.py) usa `ThreadPoolExecutor(max_workers=PULL_WORKERS=4)`; mismas 7 ventanas, mismo `_get_activities_window` y timeout de 20 s, orden de resultados preservado (más reciente primero). Peor caso: 2 rondas × 20 s = **40 s**, caso normal por debajo de 10 s. `fetch_recent_activities` conserva su contrato (lanza el error de la primera ventana fallida).
El endpoint ahora guarda las actividades de las ventanas que respondieron aunque otra falle, y sigue reportando la causa clasificada de la 411 (`pull_timeout`/`garmin_error`/`pull_failed`), con el conteo parcial en el detalle del log.

**Por qué no las otras:** (b) acortar días/ventanas: la API de Garmin limita a 24 h por consulta y recortar días pierde actividades. (c) asíncrono 202 + encuesta: exige estado en servidor, endpoint nuevo y cambios de frontend/i18n; excesivo cuando (a) ya deja el peor caso en 40 s.

## Sin tocar
OAuth, tokens, refresh, clasificación de errores 411, mensajes `gsync_*`, Polar/Wahoo, ingest, migraciones. Frontend sin cambios (el contrato de respuesta es el mismo).

## Tests
- Nuevos `api/tests/test_cloudflare_sync_419.py` (7, verdes): mismas actividades y orden, pool acotado y paralelo real, timeout 20 s por ventana, ventana fallida no pierde las demás ni la causa, endpoint guarda parciales y reporta causa, respuesta con mocks de latencia bastante por debajo del tiempo secuencial, peor caso teórico ≤ 90 s.
- Tests 379/411 de sync: verdes (59 junto a los nuevos).
- Suite completa (api/, sin los 2 archivos zz_ sin rastrear): **3814 passed, 2 failed** (30 min; salida en labx-overnight/pytest-419.txt). Los 2 fallos son preexistentes (verificado también sin mis cambios): `test_calendario_vivo_375.py::test_c_evento_borrado_en_origen_desaparece` y `::test_c2_pasado_se_conserva_y_fallo_no_borra`; dependen de fechas/estado de intervals, ajenos a esta pila.

## Honestidad del alcance
- La mejora se demuestra por simulación y por cota, no con latencia real de Garmin. Si Garmin limita por tasa en paralelo (429), una ventana fallaría con `pull_failed` y se guardarían las demás; ver el log `ventanas` en producción y bajar `PULL_WORKERS` si ocurre.
- Si Garmin está lento en TODAS las ventanas a 20 s, el peor caso (~40 s) cabe, pero el refresh de token previo (no acotado aquí) no se contó.
- `sw.js` BUILD 419; espejos móviles regenerados con `build_www.py` + capacitor sync por node.
