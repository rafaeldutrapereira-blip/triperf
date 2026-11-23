# REPORT 409 — GEMINI-MODELO

## Qué cambió
- `api/services/blood_lab_parser.py`: `GEMINI_MODEL` por defecto `gemini-3.8-flash` -> `gemini-3.5-flash`. Override por env `GEMINI_MODEL` intacto. Motivo: el 23/11 `gemini-3.8-flash` devolvía HTTP 503 «high demand» en 0,6 s; `gemini-3.5-flash` responde.
- `GEMINI_TIMEOUT` **NO se tocó** (300 s): la medición no lo justifica (ver abajo).
- `sw.js`: `BUILD_VERSION` '409' + línea de changelog. Espejos móviles regenerados (`build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`).
- Tests: `api/tests/test_gemini_409.py` (default 3.5-flash, override por env, 503 -> `ParseUnavailable` con reason `unavailable` —no existe reason propia para 503 y el alcance prohíbe tocar el parser—, timeout 300 s y su expiración). Se actualizaron `test_gemini_406.py` (esperaba 3.8-flash) y `test_asistente_claro_407.py::test_build_407` (fijaba `'408'` exacto; ahora exige >= 407).
- No se tocó: fallback Anthropic, `LAB_PARSER_PROVIDER`, endpoints, resto del parser. Sin migraciones, sin push, sin deploy.

## Tiempos medidos en el servidor (labx-server, entorno del servicio: `~/labx/.env`, clave de 53 caracteres)
Parse completo de `MODULAB_02147223.pdf` con `gemini-3.5-flash` (`parse_report`, timeout de medición 900 s):

| corrida | resultado | tiempo |
|---|---|---|
| 1 | OK, 14 marcadores, fecha 2026-05-30 | 17,7 s |
| 2 | OK, 14 marcadores, fecha 2026-05-30 | 11,0 s |

Muy por debajo de ~240 s, por lo que el timeout de 300 s se mantiene. (El diagnóstico previo de 108 s era para una respuesta mínima en un momento de saturación; la latencia de Google varía.)

## Honestidad del alcance
- La medición se hizo con el código del VM (que aún tiene 3.8-flash por defecto) forzando `GEMINI_MODEL=gemini-3.5-flash` por env: prueba el modelo, no el commit desplegado.
- Con 11–18 s el parse cabe de sobra en el navegador, pero son 2 muestras; Google puede saturarse de nuevo.
- La verificación real en vivo es subir el MODULAB tras el deploy (no es parte de esta pila).
- Medición con el PDF copiado a `/tmp` del servidor (`/tmp/MODULAB.pdf`, `/tmp/m409.py`; quedan allí).

## Suite completa
`pytest api/tests` (sin `test_zz_perf_measure`/`test_zz_repro`, archivos sin versionar ajenos a la pila): 3688 passed, 2 failed en 27 min. Los 2 fallos (`test_recuperacion_394::test_build_394_y_sello`, `test_tema_migracion_396::test_sellos_de_version`) fijaban `BUILD_VERSION == '408'` exacto; se hicieron tolerantes (>= 408) igual que `test_build_407`, y los 4 archivos afectados pasan (18 passed). No se re-corrió la suite entera tras ese ajuste.
