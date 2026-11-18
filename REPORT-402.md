# REPORT-402 — TSS-LATENTE (BUILD 402)

## Causa raiz
`GarminActivity` no tiene `training_stress_score`; la columna real es `tss` (api/models.py). Cuatro lecturas vivas lanzaban AttributeError (misma clase que la pila 393).

## Cambios
- `api/routes/plan_builder_routes.py`: plan-vs-actual (`tss_actual`) y panel de cumplimiento del coach (`tss_a`) -> `a.tss`.
- `api/services/plan_matching_service.py`: seleccion por TSS mas cercano y `tss_actual` -> `tss`.
- Busqueda en el repo (py/js/html, sin www/android/ios): no quedan otras lecturas vivas; solo el comentario de la 393 y una cita en un test.
- `sw.js` BUILD_VERSION '402' + changelog; `i18n.js?v=400` -> `?v=402` en paginas, sw.js y tests que lo fijan (py y js). Sin textos de UI ni i18n nuevos.
- Tests nuevos: `api/tests/test_tss_latente_402.py` (3 tests; fallan en la base, pasan con el arreglo).

## HALLAZGO FUERA DE ALCANCE (no corregido)
`plan_matching_service.match_sessions_for_user` tambien lee `best.moving_time_seconds`, `best.distance_meters` y `best.started_at`, que NO existen en `GarminActivity` (0 apariciones en models.py; el modelo tiene `dur_min`, `dist_km`). Tras este arreglo, el emparejamiento sigue lanzando AttributeError en esas lineas cuando hay una actividad compatible. El test de matching define esos atributos como None via monkeypatch solo para aislar la seleccion por TSS. Requiere una pila propia.

## Verificacion
- `npm run test:js`: 314/314.
- pytest api/tests (tras `build_www.py` + `npx cap sync`): 3660 passed, 1 skipped, 2 failed. Los 2 fallos son los conocidos `test_calendario_vivo_375` (test_c_evento_borrado_en_origen_desaparece, test_c2_pasado_se_conserva_y_fallo_no_borra). Los 2 de espejos moviles no reaparecieron. Sin regresiones nuevas.
- Log: el archivo C:\Users\rafae\labx-overnight\tss402.log estaba bloqueado ("Device or resource busy") y no pude escribirlo; los resultados estan aqui.

## Commit
Local en main, sin push ni deploy ni migraciones.
