# REPORT-406 — GEMINI (BUILD 406)

## Cambio
- `api/services/blood_lab_parser.py`: `GEMINI_TIMEOUT` 90 -> 300 s (la lectura real tardó ~270 s en el smoke test del 15/11), sobreescribible por env `GEMINI_TIMEOUT` (valor inválido o <=0 cae a 300). `GEMINI_MODEL` default `gemini-3.5-flash` -> `gemini-3.8-flash` (override por env `GEMINI_MODEL` intacto).
- `sw.js`: `BUILD_VERSION` '406' + línea de changelog. Dos tests que fijaban '405' (`test_recuperacion_394`, `test_tema_migracion_396`) se actualizaron a '406'.
- Espejos móviles regenerados con `build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`.
- No tocado: `GEMINI_API_KEY` y su carga, `LAB_PARSER_PROVIDER`, fallback Anthropic, mensaje del frontend, Garmin/intervals. Sin migraciones, sin push, sin deploy.

## Evidencia de tests
- Nuevos: `api/tests/test_gemini_406.py` (5 tests): defaults, timeout aplicado 300 y override por env, URL con el modelo (y override), respuesta simulada de 270 s que ahora se parsea (14 marcadores; con timeout 90 sigue rindiéndose), mapeo de errores (429 -> quota, 500 -> unavailable, billing Anthropic -> billing).
- Suite completa `pytest api/tests`: **3676 passed, 1 skipped, 0 failed** (26:56). Sin fallos preexistentes. Salida en `labx-overnight/gemini406-pytest.log`.

## Honestidad del alcance
- **La lectura real con Gemini NO se verificó aquí**: el constructor no tiene la clave. Los tests usan dobles de red. La verificación real (subir `MODULAB_02147223.pdf` en producción tras el deploy) es paso de Pocoyo.
- Si falla tras el deploy con el modelo/timeout nuevos, el diagnóstico (a)-(d) del SPEC queda abierto (p. ej. otro cuello de botella en la capa de proxy/Cloudflare, que corta ~100 s en conexiones sin respuesta; no verificable localmente).
- `labx-overnight/gemini406.log` estaba bloqueado por otro proceso (lo escribe el lanzador); el log de pytest quedó en `gemini406-pytest.log`.
