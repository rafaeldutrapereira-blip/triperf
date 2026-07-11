# Sprint 38 — Security Hardening (completado 2026-07-03)

## Cambios implementados

### R-01: Credenciales por defecto eliminadas
**Archivo:** `start_coach_api.py`
- Eliminados defaults inseguros `admin_pass="kona2026"` y `demo_pass="demo123"`
- En producción (`APP_ENV=production`): falla con sys.exit(1) si `ADMIN_PASS` no está configurada
- En desarrollo: usa contraseña temporal `"labx-dev-change-me"` con WARN en consola

### R-02: OpenAPI docs bloqueados en producción
**Archivo:** `api/coach_main.py`
- En `APP_ENV=production`, `/docs` y `/redoc` retornan 404 a menos que `ENABLE_DOCS=1` sea explícito
- Antes: `ENABLE_DOCS` defaulteaba a "1", exponiendo el schema completo en producción

### R-04: Doble registro de rutas eliminado
**Archivo:** `api/coach_main.py`
- Eliminado bloque `/api/v1` (líneas 924-958, 35 routers × 2 = 70 registraciones → 35)
- Verificado: ningún archivo JS/HTML usa `/api/v1`
- Reducción de rutas: ~680 → ~340

### R-05: Rate limit strict para endpoints AI
**Archivos:** `api/redis_client.py`, `api/routes/blood_lab_routes.py`
- `check_rate_limit_redis()` tiene nuevo parámetro `strict=False`
- `strict=True` bloquea cuando Redis no está disponible (en lugar de permitir)
- Aplicado en: AI blood lab analysis (10/hora/usuario)
- Protege contra: spike de costos Anthropic cuando Redis cae

## Tests
1676 passed, 0 failures (sin regresiones)
