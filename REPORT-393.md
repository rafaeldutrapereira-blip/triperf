# REPORT-393 — TENDENCIAS-BLOODLABS (BUILD 393)

Base: origin/main 36288bc (BUILD 392). Árbol rastreado limpio al empezar (`git diff --quiet` y `--cached` OK).

## Causa raíz

La pestana Tendencias (`renderTrendsTab()` en `blood_labs.html`) lee `GET /labs/timeline?all=1`
(`loadTimeline()`); la tabla de comparación de la 392 lee `/labs/exams` + detalle de cada examen. Son rutas distintas.

`/labs/timeline` llama a `compute_correlations` → `_get_perf_window` (`api/services/blood_labs_correlation_service.py`),
que para cada examen consulta las actividades Garmin de ±30 días y hacía
`a.training_stress_score for a in acts`. **`GarminActivity` no tiene esa columna; la real es `tss`**
(`api/models.py`, clase `GarminActivity`). En cuanto hay al menos una actividad en la ventana de un examen,
el endpoint lanza `AttributeError` → HTTP 500. En el front `apiGet` rechaza, `loadTimeline` hace `catch` y deja
`TIMELINE = null`, y `renderTrendsTab` interpreta `null` igual que "sin exámenes" y pinta `bl_tr_none`
("Aún no hay exámenes…"). Es el patrón recurrente "campos de modelo inexistentes" de CLAUDE.md.

Por qué no lo detectaron los tests de la 389: su fixture `coach5` crea cargas (`GarminTrainingLoad`) pero ninguna
`GarminActivity`, así que la lista `acts` quedaba vacía y la línea con el campo inexistente nunca se evaluaba.
(Verificado: sin el arreglo, el test nuevo falla con `AttributeError: 'GarminActivity' object has no attribute 'training_stress_score'`.)

Nota de honestidad: no pude consultar la cuenta real en producción desde aquí; la causa se establece por código y se
reproduce en test, y es consistente con el síntoma (vacío pese a 5 exámenes, tabla de comparación sí funciona).

## Arreglo

- `api/services/blood_labs_correlation_service.py`: `a.training_stress_score` → `a.tss` (2 líneas). Sin migración.
- Sin cambios de UI ni claves i18n nuevas (la pestana ya dibujaba las tendencias cuando recibe datos; textos existentes).
- Bump BUILD 393: `sw.js` (BUILD_VERSION + línea de changelog + precache `/i18n.js?v=393`) y sello `?v=392`→`?v=393`
  en todas las páginas HTML raíz que lo llevaban; asserts de sello actualizados en los tests que lo fijan.

## Archivos cambiados

- `api/services/blood_labs_correlation_service.py` (arreglo)
- `sw.js`, y sello `?v=393` en 404, adaptive, ai_coach, analytics, app_invitacion, athlete-app, athlete_profile, blood_labs,
  coach, community, dashboard, detalle, estado, gear, huella, indoor_workout, invitacion, landing, login, nutrition,
  onboarding, public_activity, race_day, recovery, registro, reset-password, shared_plan, shared_report, shell,
  training_detail, training_plan (`.html`)
- Tests: `api/tests/test_bloodlabs_ejecutiva.py` (sello 393 + test nuevo con actividades en la ventana),
  `tests/js/bloodlabs_tendencias_393.test.js` (nuevo), `tests/js/bloodlabs_simple_391.test.js` y
  `tests/js/bloodlabs_tabla_392.test.js` (sello/BUILD a 393).
- No se tocaron `www/`, `android/`, `ios/`, ni el flujo de carga/lectura, ni la tabla de comparación.

## Pendientes fuera de alcance (no tocados)

- El mismo campo inexistente `training_stress_score` aparece en `api/routes/plan_builder_routes.py` (líneas ~494 y ~841)
  y `api/services/plan_matching_service.py` (~157, ~160): mismo bug latente. Conviene una pila aparte.
- Un fallo de carga del timeline se muestra como "sin exámenes" (indistinguible del vacío real). Mejora de UX posible.
- Los gráficos de tendencias usan colores fijos de Chart.js (`#0EA5E9`, `#3D6880`) ya existentes; no se tocaron.

## Verificación

- `npm run test:js`: 282 tests, 282 pass, 0 fail (incluye `bloodlabs_tendencias_393.test.js`: con 5 exámenes dibuja
  hemoglobina/ferritina/vitamina D sin mensaje de vacío, `null` → vacío, tabla de comparación `#bl-cmp-table` presente, sello 393).
- `pytest api/tests/test_bloodlabs_ejecutiva.py`: 25 passed.
- Suite completa `pytest api/tests` (excluyendo los 2 archivos untracked `test_zz_*`, ajenos a la pila): **3647 passed, 2 failed** (26 min).
  - FAILED `test_i18n.py::test_mobile_mirrors_match_root_i18n` y `::test_mobile_mirrors_match_root_sw`: los conocidos de espejos móviles
    (copias gitignoradas www/android/ios con i18n.js/sw.js de la 391; se regeneran en el build; en CI se saltan). No son regresión.
  - Los 2 de `test_calendario_vivo_375` NO fallaron en esta corrida (no reaparecieron).
  - Cero fallos por regresión de esta pila.
- Log completo de pytest: `C:\Users\rafae\labx-overnight\blood393-pytest-full.txt`.

## Commit

Local en main, sin push ni deploy: `feat(blood-labs): tendencias ven los examenes cargados (TENDENCIAS-BLOODLABS, BUILD 393)`.
