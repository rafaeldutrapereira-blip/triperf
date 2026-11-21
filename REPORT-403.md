# REPORT-403 — MATCHING (BUILD 403)

## Causa
`match_sessions_for_user` (`api/services/plan_matching_service.py`) leía de `GarminActivity` tres atributos que no existen en el modelo: `moving_time_seconds`, `distance_meters` y `started_at`. Al emparejar una actividad compatible levantaba `AttributeError`; `match_sessions_all_users` lo captura por usuario y lo registra, así que el matching fallaba en silencio (cero sesiones emparejadas, sin adherencia plan-vs-real). La 402 ya había corregido solo la lectura de TSS.

## Cambio
- `duration_actual_min` ← `dur_min`; `distance_actual_km` ← `dist_km` (redondeado a 2 decimales); ambos `None` si la columna viene vacía.
- `completed_at` ← `date_iso` a medianoche (`PlanSession.completed_at` es `DateTime` nullable; `GarminActivity` no guarda hora de inicio, no se inventó ninguna). Si `date_iso` no es parseable queda `None`.
- Sin cambios en selección por TSS, compatibilidad de deporte, ventana de fechas, `used_activity_ids` ni auto-skip.
- Búsqueda en el repo (`*.py`): no hay otros usos sobre `GarminActivity`. Las únicas otras apariciones son el parámetro `distance_meters` de `garmin_connector.py` (función propia, no el modelo) — sin tocar.
- Nota: medianoche es solo fecha; otras pantallas usan `completed_at` no nulo como "sesión completada", por eso se selló con la fecha en vez de dejar `None`.

## Archivos
- `api/services/plan_matching_service.py` (fix)
- `api/tests/test_plan_matching_403.py` (nuevo, 3 tests: campos reales, vacíos → None, regresión del AttributeError vía `match_sessions_all_users`)
- `api/tests/test_tss_latente_402.py`: se quitó el monkeypatch que definía los 3 atributos inexistentes en None (ya no hace falta).
- `api/tests/test_recuperacion_394.py` y `api/tests/test_tema_migracion_396.py`: sus asserts fijaban `BUILD_VERSION = '402'`; actualizados a `'403'` (la suite falló en esos 2 por el bump, no por el matching).
- `sw.js`: `BUILD_VERSION = '403'` + línea de changelog. Sin cambios de UI ni i18n (`i18n.js?v=402` se conserva).
- Espejos móviles: regenerados con `scripts/build_www.py` + `npx cap sync` (gitignorados, no entran al commit).

## Verificación
- Los 3 tests nuevos fallan sin el fix (log: `'GarminActivity' object has no attribute 'moving_time_seconds'`) y pasan con él.
- Suite completa `api/tests`: 3663 passed, 1 skipped, **2 failed** (22 min). Los 2 fallos eran los asserts de `'402'` mencionados arriba, causados por mi bump; corregidos y re-corridos junto con los tests 402/403: 16 passed. No se repitió la suite completa tras ese ajuste de 2 líneas.
- Alcance: el árbol contiene además archivos sin seguimiento ajenos a la 403 (REPORT-399/401, `_*.py`, `data/`, etc.); no se incluyeron en el commit.
- Corrección menor: un typo `d =date` que quedó en el test 402 se arregló.

## Commit
Local en main, sin push, sin deploy, sin migraciones.
