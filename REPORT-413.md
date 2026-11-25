# REPORT-413 — H7-SESIONES (BUILD 413)

Las sesiones sobreviven al cambio de contrasena (R3 §2, H7). Solo local: commit en main, sin push, sin deploy, sin migraciones.

## Cambios
- `api/routes/auth_routes.py`
  - `change_password`: sube `token_gen` (mismo mecanismo que `/auth/revoke-all`: `me.token_gen = (me.token_gen or 1) + 1`). Reemite cookie `lx_access_token` y devuelve `access_token` nuevo para quien hizo el cambio (si no, su propia sesion quedaba expulsada).
  - `reset_password`: sube `token_gen` del usuario. No reemite nada (no hay sesion autenticada).
- `api/routes/athlete_routes.py` `PATCH /athlete/profile`: si viene `password`, se exige `old_password` correcta (400 si falta o no coincide) y se aplica `_validate_password_strength` (la politica existente de `change_password`, 422). Validacion ANTES de mutar nada. Al cambiar sube `token_gen`, reemite cookie y devuelve `access_token`.
- `api/schemas.py`: `AthleteProfileUpdate.old_password` (opcional).
- `athlete_profile.html`: tras `change-password` guarda el `access_token` devuelto en `lx_co_token` (el bearer anterior ya estaria revocado).
- `sw.js`: BUILD_VERSION 413 + linea de changelog. Espejos moviles regenerados (`build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`).

## Opcion elegida en PATCH /athlete/profile
**Exigir la contrasena actual** (no quitar el campo). Por que: el flujo permite verificarla limpiamente con `verify_password` y no rompe contratos existentes. Ningun frontend del repo manda `password` a este endpoint (el UI usa `/auth/change-password`), asi que el impacto en clientes es nulo.

## Tests
- Nuevo `api/tests/test_h7_sesiones.py`: 8 tests en verde (change_password y reset_password revocan tokens previos con 401; profile sin/incorrecta clave actual no cambia la clave; politica de fortaleza; con la actual cambia y revoca; PATCH sin password no toca sesiones; `/auth/revoke-all` intacto).
- Nota de test: el TestClient conserva la cookie reemitida y esta tiene prioridad sobre el header, por eso el helper la limpia para probar solo el bearer.
- Suite completa (`python -m pytest api/tests`, 28 min): **3754 passed, 0 failed, 0 errors**. Se excluyeron `test_zz_perf_measure.py` y `test_zz_repro.py` (archivos sin rastrear, ajenos a esta pila). Salida: `labx-overnight/h7-pytest-full.txt`. Sin fallos preexistentes.

## Alcance / honestidad
- NO tocado: `PATCH /admin/users` (sigue sin subir `token_gen`), login/2FA, expiracion de tokens.
- `reset_password` conserva su validacion previa (solo largo >= 8), no la politica completa de `change_password`; fuera del alcance del SPEC.
- Tokens revocados siguen vivos hasta que se valida `gen` en cada request (mecanismo existente); no se cambio.
- La cookie/bearer de otros dispositivos del mismo usuario queda invalida: deberan volver a iniciar sesion (intencional).
