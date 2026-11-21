# REPORT-405 — SIMULACION-MARCAS (BUILD 405)

Validacion virtual de Wahoo y Polar con un servidor mock local y un corredor automatico. Solo local: sin push, sin deploy, sin migraciones.

## Que se construyo

| Archivo | Cambio |
|---|---|
| `api/tests/mock_vendors.py` | Servidor HTTP stdlib (`ThreadingHTTPServer`, puerto libre en 127.0.0.1). Wahoo: `GET /oauth/authorize`, `POST /oauth/token`, `GET /v1/workouts` (+ `/{id}`). Polar: `GET /oauth2/authorization` (302 con code falso), `POST /v2/oauth2/token`, `POST /v3/users`, `GET /v3/exercises` (+ `/{id}`, `/{id}/gpx`). |
| `api/tests/mock_vendors_runner.py` | Corredor de punta a punta. Un comando: `python -m api.tests.mock_vendors_runner` (desde la raiz). Escribe `corrida-mock-405.{md,json}` en `labx-overnight/sprint-simulacion-marcas/`. Exit 0 si todo cuadra. |
| `api/tests/test_mock_vendors_405.py` | 6 tests nuevos (corredor con y sin GPX, fixtures verbatim, URLs por defecto sin cambios, overrides por env, `NotImplementedError` de Polar intacto). |
| `api/providers/wahoo.py`, `polar.py` | URLs base por env (`WAHOO_API_BASE_URL`, `WAHOO_TOKEN_URL`, `POLAR_API_BASE_URL`, `POLAR_TOKEN_URL`, `POLAR_AUTH_URL`), leidas en cada llamada; default = URL real. Sin esas variables el comportamiento es identico. |
| `sw.js` | `BUILD_VERSION` 404 -> 405 + linea de changelog. |

## Que se mockeo (y que no)

- **Datos de actividad: verbatim.** El mock solo sirve `api/tests/fixtures/wahoo/doc_sample_get_workout.json` y `.../polar/doc_sample_exercise.json`, sin tocar campos. Un test compara la respuesta del mock con el fixture (igualdad exacta).
- **Errores honestos:** 401 con token malo/ausente, 404 con id inexistente o ruta desconocida, 401 con `code` invalido.
- **Lo unico fabricado** es el sobre de OAuth (tokens `mock-*`, `expires_in`), que no es dato del vendor: sin el no se puede ejercitar el intercambio de code.
- **GPX de Polar:** no hay fixture oficial, asi que por defecto el mock responde 404 (caso cubierto por un test). En la corrida "con GPX" se sirve un GPX **sintetico de 2 puntos**, declarado como tal en el codigo, que solo comprueba el cableado `download_gps` -> `_parse_gpx` -> archivo. No es dato de Polar.
- El mock no implementa la transaccion de ejercicios de AccessLink (`POST /users/{id}/exercise-transactions`) porque `PolarProvider.list_activities` no la usa: lee `GET /v3/exercises`. Eso es una decision previa del provider, no del mock.

## Flujo probado (punto de entrada real verificado en codigo)

1. Pantalla de autorizacion del mock -> code.
2. `wearable_oauth_routes._exchange` (instancia `WahooProvider`/`PolarProvider` y llama `authenticate`; Polar ademas registra el usuario con `POST /v3/users`) + `provider_oauth.save_connection` (token cifrado con Fernet) — el mismo codigo del callback OAuth.
3. `provider_sync_service.sync_provider_user` — el mismo punto que usa `POST /integrations/<marca>/sync`: `provider_oauth.get_valid_access_token` + `registry.get_provider` + `list_activities` + `get_activity_detail` + `_upsert` en `garmin_activities` (+ `download_gps` en Polar).
4. Segundo sync: idempotente (0 guardadas, 1 fila).
5. BD: SQLite temporal creada por el propio corredor (`create_all`), borrada al terminar; el CLI ademas fija `DATABASE_URL` a un archivo temporal antes de importar `api.*`. Nunca toca la BD del repo ni la de produccion. El mock se apaga al final.

Los fixtures oficiales son de 2008/2015, por eso el corredor usa `days=40000` (la ventana por defecto de 30 dias los descartaria).

## Evidencia (corrida `python -m api.tests.mock_vendors_runner`: 29/29 chequeos OK)

| Campo | Wahoo `wahoo_56519` | Polar `polar_2AC312F` |
|---|---|---|
| fecha | 2015-08-12 | 2008-10-13 |
| deporte | other (`workout_type_id=40`, ver nota) | other (`OTHER`) |
| duracion | 12 min | 164 min (`PT2H44M`) |
| distancia | 24.91 km | 1.6 km |
| FC media | 100 | 129 |
| potencia media | 95 | — (Polar no la trae) |
| calorias | 1500 | 530 |
| desnivel | 450 m | — |
| TSS | 304.9 (nativo `power_bike_tss_last`) | 137.3 (%FCmax, fcmax=182) |
| GPX | n/a (solo .FIT) | 2 puntos (GPX sintetico) |

Nota Wahoo: el fixture oficial trae `workout_type_id=40` (KITEBOARDING en la tabla de Wahoo) con metricas de bici; es una inconsistencia de la documentacion y se deja tal cual, por lo que el deporte queda `other`. El corredor lo afirma explicitamente.

Reporte completo: `labx-overnight/sprint-simulacion-marcas/corrida-mock-405.md` / `.json`.

## Tests

- Nuevos + sync + contrato de providers: 33 passed (`test_mock_vendors_405.py`, `test_provider_sync_service.py`, `test_provider_contract.py`).
- Suite completa (`pytest api/tests`, excluyendo `test_zz_perf_measure.py` y `test_zz_repro.py`, archivos sin seguimiento ajenos a esta pila): **3671 passed, 0 failed, 27m53s**.
- Una primera pasada con `-x` se detuvo en `test_recuperacion_394.py::test_build_394_y_sello`: fijaba `BUILD_VERSION = '404'` y falla por diseno al subir el sello. Se actualizo ese valor a 405 en ese test y en `test_tema_migracion_396.py` (mismo patron) y se repitio la suite completa sin `-x`. No hay fallos preexistentes.

## Honestidad del alcance

- El mock valida **el lado de LabX**: OAuth (intercambio de code, registro Polar), sync, normalizacion, guardado, dedupe e idempotencia.
- **No** valida el handshake con el vendor real: que Wahoo/Polar acepten nuestro `client_id`/redirect, los formatos reales de respuesta mas alla del ejemplo de la doc, paginacion real, expiracion/refresh real, ni limites de la API. Eso sigue pendiente de **1 cuenta real** (app del telefono o beta) antes de prender `WAHOO_ENABLED` / `POLAR_ENABLED`.
- Un fixture = una actividad por marca: no cubre mezclas de deportes, actividades sin FC/potencia ni lotes grandes.
- No se tocaron: `.env` de produccion, flags en produccion, `download_splits`/`get_health_daily`/`get_sleep` de Polar (siguen `NotImplementedError`), Garmin/intervals. Sin migraciones.
