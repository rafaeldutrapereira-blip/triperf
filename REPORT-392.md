# REPORT-392 — BLOODLABS-TABLA (BUILD 392)

## Causa
La comparacion de Blood Labs era un par de selectores (examen / «vs») mas una lista de 5 variaciones entre solo dos examenes; no habia una vista con todos los examenes a la vez.

## Cambio
- `blood_labs.html`: nueva seccion «Comparacion de examenes» (`#bl-cmp-table`, `renderCompareTable()`) en el Resumen, en el lugar de la comparacion, bajo la respuesta/alertas/TRS y antes de «Ver detalle». Filas = marcadores (agrupados por categoria, sin plegar), columnas = TODOS los examenes (mas antiguo -> mas reciente, con laboratorio), una sola tabla sin paginar, con scroll horizontal y primera columna fija. Cada valor va coloreado segun el veredicto del servidor y lleva debajo su linea de referencia («Dentro de su rango», «Por debajo de su rango», ...). Se redibuja al cambiar de examen y tras guardar/eliminar.
- Estilo solo con `var(--...)`; textos por i18n `bl_tbl_*` (7 claves, ES/PT/EN) en `i18n.js`.
- `sw.js`: BUILD_VERSION '392' + changelog; sello `i18n.js?v=391` -> `392` en 34 archivos (paginas, sw.js, tests que lo fijan).
- Tests: nuevo `tests/js/bloodlabs_tabla_392.test.js` (ejecuta `renderCompareTable` con datos simulados), agregado a `npm run test:js`; `bloodlabs_simple_391.test.js` y `api/tests/test_bloodlabs_ejecutiva.py` actualizados al sello 392.

## Lo que NO cuadra con el codigo (decision a tomar)
1. **Rangos de referencia numericos: no estan disponibles en el cliente.** `GET /labs/exams/{id}` y `/labs/markers` no devuelven `low/opt_low/opt_high/high`; esos rangos solo existen en `MARKERS` de `api/routes/blood_lab_routes.py`. Como el alcance prohibe tocar el backend y no se deben inventar ni copiar cifras (dependen ademas del sexo), la «linea base» de la tabla es el veredicto del servidor contra su estandar (`zone`/`status`), no los numeros. Para mostrar «min–max» junto a cada valor hace falta exponer los rangos en el backend (p. ej. `ref_low/ref_high/opt_low/opt_high` por marcador en el detalle del examen): trabajo aparte.
2. **Selectores y variaciones se conservaron.** `sel-exam` sigue siendo necesario (alimenta «Ver detalle»); `sel-comp`/«vs» y el bloque de variaciones siguen existiendo (debajo de la tabla, como resumen del par elegido) porque otros tests (`test_bloodlabs_ejecutiva`, `test_labs_capas_352`, `bloodlabs_simple_391`) fijan esos ids. La tabla es la vista principal; retirar el «vs» es una limpieza posterior.
3. La tabla pide el detalle de cada examen (`GET /labs/exams/{id}`, una peticion por examen, en paralelo, con cache); cada lectura queda en el registro de auditoria del backend.
4. Sin sexo declarado el servidor no evalua: las celdas muestran el valor sin color y «Sin evaluar».

## Verificacion
- `npm run test:js`: 282 pass, 0 fail (incluye bloodlabs_tabla_392 y bloodlabs_simple_391).
- pytest `api/tests` (sin los 2 archivos sin rastrear `test_zz_*`): **3644 passed, 4 failed** (28 min). Salida en `C:\Users\rafae\labx-overnight\pytest392.out` (`blood392.log` lo ocupa otro proceso de la sesion).
  - 2 previos y ajenos (fallan igual en la base limpia): `test_calendario_vivo_375.py::test_c_evento_borrado_en_origen_desaparece`, `::test_c2_pasado_se_conserva_y_fallo_no_borra`.
  - 2 causados por este cambio, esperados: `test_i18n.py::test_mobile_mirrors_match_root_i18n` y `::test_mobile_mirrors_match_root_sw`. Las copias gitignoradas `www/`, `android/`, `ios/` de esta PC siguen con i18n.js/sw.js de la 391 (el alcance prohibe tocarlas). Se resuelven con `python scripts/build_www.py` + `npx cap sync`; en CI las copias no existen y el test se salta. **Por estos fallos, el trabajo no esta cerrado hasta regenerar las copias.**
- Fallos previos, ajenos al cambio (tambien fallan en la base limpia 4af9355): `test_calendario_vivo_375.py::test_c_evento_borrado_en_origen_desaparece` y `::test_c2_pasado_se_conserva_y_fallo_no_borra` (`planned_removed == 0`).
- No verificado en navegador (no se levanto la app); solo tests y render con DOM simulado.

## Commit
Local en main, sin push/deploy/migraciones: «feat(blood-labs): tabla clinica de comparacion (BLOODLABS-TABLA, BUILD 392)».
