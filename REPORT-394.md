# REPORT-394 — RECUPERACION-ATLETAS (BUILD 394)

## Causa raiz
- Frontend: `recovery.html` (`loadCoachView`, embebido desde `coach.html` con `?view=coach`) pide `GET /api/recovery/coach-view`.
- Backend: `api/routes/recovery_routes.py::coach_recovery_view` validaba el rol con `getattr(me, "role", None)`. El modelo `User` no tiene `role`; el campo es `rol`. El `getattr` devolvia siempre `None`, asi que TODO coach/admin recibia 403 ("Solo coaches pueden acceder a esta vista.").
- El JS hacia `if (r.status === 403) return null;` y luego `if (!d) return;`, y el `.catch(function(){})` era vacio: ningun camino reemplazaba el "Cargando vista de atletas…" inicial. La vista quedaba colgada para siempre.
- Reproducido con pytest (coach + atleta en un grupo): 403 en la base.

## Arreglo (minimo)
- Backend: `me.rol` en lugar de `me.role` (una linea).
- Frontend: un error HTTP (`!r.ok`) o de red ahora muestra un aviso (`rcw_load_error`, ES/PT/EN) en vez de dejar "Cargando"; el 403 ya no se traga en silencio.
- Sin migraciones. No se tocaron tablero 382, boton alertas 390, Blood Labs ni www/android/ios.

## Archivos
api/routes/recovery_routes.py, recovery.html, i18n.js (rcw_load_error x3), sw.js (BUILD 394 + changelog), sello `i18n.js?v=394` en las paginas, tests: api/tests/test_recuperacion_394.py (nuevo), tests/js/recuperacion_394.test.js (nuevo), asserts de sello actualizados en tests/js/bloodlabs_*.test.js y api/tests/test_bloodlabs_ejecutiva.py.

## Verificacion
- Test pytest nuevo: falla en la base (403), pasa con el arreglo (3 passed).
- `npm run test:js`: 282 pass, 0 fail.
- pytest api/tests completo: 3650 passed, 1 skipped, 2 failed. Los 2 fallos son los conocidos de espejos moviles (`test_mobile_mirrors_match_root_i18n` y `_root_sw`; copias gitignoradas sin regenerar). Sin regresiones nuevas.
- No se verifico en vivo con la cuenta coach (sin push/deploy).
- Log: C:\Users\rafae\labx-overnight\recup394_run.log (recup394.log quedo bloqueado por un proceso previo; se copio si fue posible).
