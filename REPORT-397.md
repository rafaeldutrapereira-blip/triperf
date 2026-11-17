# REPORT-397 — RACE-DAY (BUILD 397)

## Dónde vive Race Day
- Página: `race_day.html` (ruta `race_day`, gating con `KL.guard('race_day')`; backend en `api/routes/race_routes.py`).
- Datos: `GET /api/races/dashboard-s19` (carrera objetivo + plan guardado), `POST /api/races/auto-plan` (generador), `GET /api/races?limit=20` (historial), `POST /api/races/record-result` (resultado).
- Contenido real: pestaña **Mi carrera** (cuenta regresiva, plan con tiempo/vatios/ritmo, combustible por hora, plan en palabras, detalle plegado, ajustes avanzados plegados) y pestaña **Mis carreras** (historial con puntaje de ejecución + formulario de resultado + análisis).

## Estado encontrado
La pestaña Mi carrera YA tenía capas desde BUILD 350 (RACEDAY-CAPAS: `rd-l1` / `rd-l2` / `rd-advanced`, test `test_raceday_capas_350.py`). Faltaban: (a) una respuesta en palabras al inicio y (b) la pestaña Mis carreras, que era plana (historial y formulario largo siempre abierto). Solo se completó eso; lo ya hecho en 350 no se tocó.

## Cambios
- **Capa 1, Mi carrera:** tarjeta `#rd-answer` arriba: «Faltan N días para <carrera>. Con tu plan, tu tiempo estimado es T. En bici, apunta a W W. Al correr, sal a P por kilómetro.» (o aviso de que aún no hay plan). Se arma en `renderAnswer`, llamado desde `renderPlanSummary`, con los mismos datos que ya se mostraban (se actualiza también al generar el plan).
- **Capa 1, Mis carreras:** `#rd-hist-answer`: última carrera con puntaje real (la de fecha más reciente con `pacing_score`), con veredicto en palabras (≥80 / ≥60 / menos) y «Puntaje de ejecución (Pacing Score)»; si no hay, lo dice. No se calcula ningún agregado.
- **Capa 2:** frase del porqué + historial (`#history-list`) sin cambios de datos.
- **Capa 3:** el formulario «Registrar resultado» queda en `<details id="rd-result-detail">` plegado; se abre solo al guardar un resultado para mostrar el análisis. Todos los ids se conservan.
- Solo variables de tema (`--text`, `--sub`); sin colores fijos nuevos. i18n: 13 claves nuevas ES/PT/EN (`rd_ans_*`, `rd_hist_*`, `rd_l3_record`). Sello `i18n.js?v=397` en páginas, `sw.js` y asserts de tests previos; `BUILD_VERSION='397'` con changelog.
- Sin backend, sin migraciones, sin tocar `www/`, `android/`, `ios/`.

## Se mantuvo
Todo el contenido existente (ids de 350 intactos, generador, ajustes avanzados, combustible, mensaje de guardado, análisis).

## Tests
- Nuevo `tests/js/raceday_397.test.js` (5 tests), agregado a `test:js`. Sobre la base (race_day.html sin el cambio) falla 4 de 5; con el cambio pasan.
- `npm run test:js`: **304 tests, 304 pass, 0 fail** (299 reales en la base + 5 nuevos).
- pytest: ver sección final.

## pytest (api/tests)
**3657 passed, 2 failed, 1 skipped** (28 min).
Fallos: `test_i18n.py::test_mobile_mirrors_match_root_i18n` y `::test_mobile_mirrors_match_root_sw`. Causa: son consecuencia directa de esta pila (cambian `i18n.js` y `sw.js`) y las copias `www/`, `android/`, `ios/` no se tocan por instrucción; se resuelven al regenerarlas con `scripts/build_www.py` + `npx cap sync` en el build. No son un bug de lógica. `test_calendario_vivo_375` no falló esta vez.

## Commit
Solo local en main: `feat(race-day): capa ejecutiva en Race Day (RACE-DAY, BUILD 397)`. Sin push, sin deploy, sin migraciones.
