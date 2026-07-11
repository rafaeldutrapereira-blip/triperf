# LabX — Security Audit Report (FASE 4)
**Fecha:** 2026-07-04  
**Scope:** OWASP Top 10 2021 + superficies específicas LabX  
**Revisor:** Board (CTO/CEO/Dev)

---

## OWASP Top 10 — Estado por categoría

| # | Categoría | Estado | Evidencia |
|---|-----------|--------|-----------|
| A01 | Broken Access Control | **PASS** | JWT + roles (atleta/coach/admin), `get_current_user` en cada endpoint protegido, token revocation en DB |
| A02 | Cryptographic Failures | **PASS** | bcrypt para passwords, Fernet AES-128 para credenciales Garmin, JWT HS256 con secret ≥64 chars, cookies HttpOnly+Secure+SameSite=Lax |
| A03 | Injection | **PASS** | SQLAlchemy ORM — sin SQL raw de inputs de usuario; `subprocess.run(list)` en backup.py (corregido) |
| A04 | Insecure Design | **PASS** | Rate limiting 2-capa (Redis + DB), password policy (8 chars, upper/lower/digit), 2FA TOTP, audit trail completo |
| A05 | Security Misconfiguration | **PASS** | Startup abortado si JWT_SECRET/FERNET_KEY/ADMIN_PASS son defaults; SQLite bloqueado en prod; ENABLE_DOCS=0 en prod |
| A06 | Vulnerable Components | **PARTIAL** | Sin auditoría automática de dependencias (pip-audit no configurado en CI) — ver acción pendiente |
| A07 | Auth Failures | **PASS** | 2FA TOTP + backup codes de un solo uso, device fingerprinting, alerta por email en dispositivo nuevo, token revocation inmediata en logout |
| A08 | Software/Data Integrity | **PASS** | Stripe webhook verifica firma HMAC, Alembic migrations versionadas, Docker build reproducible |
| A09 | Logging Failures | **PASS** | JSON structured logs en producción, audit trail (tabla audit_logs), Sentry DSN, trace_id por request, Prometheus métricas |
| A10 | SSRF | **PASS** | No hay fetching de URLs arbitrarias de usuario; Garmin sync usa biblioteca oficial; imports externos fijos |

---

## Superficies específicas LabX

### JWT
- **Algoritmo:** HS256 con secret ≥64 chars (validado en startup)
- **Expiración:** 8h por defecto, 30d con remember_me
- **Revocación:** tabla `revoked_tokens` en DB + cache en memoria al startup
- **Entrega:** HttpOnly cookie (primaria) + Authorization header (backward compat)
- **Audience:** claim `aud=labx-app` validado en decode
- **Estado:** ✅ PASS

### CORS
- **Producción:** lista blanca explícita via `CORS_ORIGINS` env var — wildcard bloqueado
- **Credentials:** `allow_credentials=True` solo cuando CORS_ORIGINS no es `*`
- **Headers permitidos:** `["Authorization", "Content-Type", "Accept"]` — no wildcardead
- **Estado:** ✅ PASS

### Rate Limiting
- **Login:** 10 intentos/hora por IP (Redis + DB fallback)
- **Registro:** 5 intentos/hora por IP
- **Reset password:** 3 intentos/hora por IP
- **nginx:** `limit_req_zone` adicional (10r/m auth, 60r/m API general)
- **Headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
- **Estado:** ✅ PASS

### Secrets Management
- **Rotación Fernet:** `FERNET_KEY_OLD` para compatibilidad durante rotación
- **Validación startup:** Falla hard si cualquier secret usa default inseguro
- **Backup.py:** Ahora usa `subprocess.Popen(list)` — sin shell injection posible
- **Estado:** ✅ PASS

### CSP (Content Security Policy)
- **nginx:** CSP completo con allowlist de `js.stripe.com`, `cdn.jsdelivr.net`, `fonts.googleapis.com`
- **API middleware:** `SecurityHeadersMiddleware` añade CSP en respuestas API (producción)
- **Inconsistencia detectada:** CSP del middleware API incluye `'unsafe-inline'` — aceptable para fase beta (el frontend usa inline scripts para i18n/charts)
- **Estado:** ✅ PASS (con nota)

### SQL Injection
- **ORM:** SQLAlchemy con parámetros — sin concatenación de strings de usuario
- **Búsquedas:** `ilike` con `%...%` — sin interpolación directa
- **Raw SQL:** ningún uso en rutas públicas; solo `SELECT 1` y `COUNT(*)` en health/metrics
- **Estado:** ✅ PASS

### Garmin Credentials
- **Almacenamiento:** cifrado Fernet (AES-128-CBC + HMAC-SHA256)
- **Transmisión:** solo via HTTPS (cookie HttpOnly)
- **Acceso:** solo el propio usuario puede actualizar sus credenciales
- **Estado:** ✅ PASS

---

## Acciones Pendientes (no bloqueantes para beta privada)

| Prioridad | Acción | Impacto |
|-----------|--------|---------|
| P1 | Agregar `pip-audit` a GitHub Actions CI (A06) | Detecta CVEs en dependencias automáticamente |
| P1 | Agregar `dependabot.yml` para actualizaciones automáticas | Reduce ventana de exposición a CVEs |
| P2 | Rotar a JWT RS256 (asimétrico) antes de go-live público | Permite verificación sin compartir secret |
| P2 | Implementar `helmet`-equivalent para HTML pages (meta CSP tags) | Refuerza CSP sin depender de nginx |
| P3 | Agregar `X-Request-ID` a todas las responses de error (ya tiene `request_id` en body) | Correlación logs más fácil |
| P3 | Implementar TOTP setup obligatorio para cuentas coach/admin | Fortalece postura ante compromisos de password |

---

## Hallazgos corregidos en esta sesión

1. **backup.py: `os.system(f"pg_dump {DB_URL}")`** → `subprocess.Popen(list)` — eliminada superficie de shell injection si DATABASE_URL contiene caracteres especiales
2. **`.env.production.example`** → añadidas 15 variables faltantes (POSTGRES_*, VAPID_*, STRAVA_*, GARMIN_*, STRIPE_PRICE_*, METRICS_SECRET, APP_URL, DEPLOY_TAG)

---

## Veredicto FASE 4

**RESULTADO: PASS con 2 items P1 pendientes (no bloqueantes para beta privada)**

El sistema es seguro para un programa de beta privada con 3-5 usuarios seleccionados. Los items P1 deben completarse antes del go-live público.
