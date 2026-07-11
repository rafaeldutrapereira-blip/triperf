# LabX — Auditoría de Arquitectura · Fase 3
**Fecha:** 2026-07-03  
**Auditor:** CTO / Claude Sonnet 4.6  
**Versión código:** 1676 tests passing, BUILD_VERSION 27

---

## Índice

1. [Arquitectura actual (estado real)](#1-arquitectura-actual)
2. [Arquitectura objetivo (target)](#2-arquitectura-objetivo)
3. [Riesgos de escalabilidad](#3-riesgos-de-escalabilidad)
4. [Seguridad](#4-seguridad)
5. [Costos cloud](#5-costos-cloud)
6. [Observabilidad](#6-observabilidad)
7. [Plan de refactorización](#7-plan-de-refactorizacion)

---

## 1. Arquitectura actual

### Stack verificado

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Framework API | FastAPI | ≥0.115.0 |
| ORM | SQLAlchemy | ≥2.0.0 |
| Validación | Pydantic | ≥2.9.0 |
| Servidor ASGI | Uvicorn + Gunicorn | ≥0.34.0 |
| Auth | python-jose (JWT) + passlib (bcrypt) | 3.3.0 / 1.7.4 |
| Encriptación | cryptography (Fernet) | ≥42.0.0 |
| DB desarrollo | SQLite + WAL mode | bundled |
| DB producción | PostgreSQL 16 | Alpine |
| Cache / Rate limit | Redis 7 (opcional) | Alpine |
| Pagos | Stripe SDK | ≥8.0.0 |
| Email | Resend | ≥2.0.0 |
| AI | Anthropic API (sync HTTP) | vía httpx |
| Monitoring | Sentry (opcional) | FastAPI + SQLAlchemy integration |
| Runtime Docker | Python 3.11-slim | prod |
| Runtime dev | Python 3.12 ARM | Windows |

### Diagrama de la arquitectura actual

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  nginx (reverse proxy)                              │
│  - Rate limit: auth 5/min, AI 10/min, API 60/min   │
│  - TLS 1.2/1.3 · HSTS · CSP headers               │
│  - Sirve static HTML/JS/CSS (PWA)                  │
└──────────────────────┬──────────────────────────────┘
                       │ keepalive 32
                       ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI (Uvicorn, 1 proceso, 1 worker por defecto) │
│                                                     │
│  coach_main.py (~960 líneas)                       │
│  34 routers × 2 prefijos (/api + /api/v1)          │
│  22 service files                                   │
│  BackgroundTasks (sin queue real)                  │
│                                                     │
│  Middleware: CORS · GZip · RequestID · Sentry      │
└────────────┬────────────────────┬───────────────────┘
             │                    │
             ▼                    ▼
┌────────────────────┐  ┌─────────────────────────┐
│  SQLite (dev)      │  │  Redis (opcional)        │
│  PostgreSQL (prod) │  │  - Rate limiting         │
│                    │  │  - Dashboard cache       │
│  Alembic +         │  │  - Token blacklist       │
│  hot migrations    │  │  256 MB LRU              │
│  en startup        │  └─────────────────────────┘
└────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  Servicios externos                                 │
│  - Garmin Connect (sync actividades)               │
│  - Strava OAuth                                    │
│  - Anthropic API (AI análisis)                     │
│  - Stripe (pagos)                                  │
│  - Resend (email transaccional)                    │
│  - Web Push VAPID                                  │
└─────────────────────────────────────────────────────┘
```

### Inventario de módulos

**34 route modules** (todos bajo `/api` Y `/api/v1` — doble registro):

| Módulo | Dominio |
|--------|---------|
| auth_routes | Login, registro, 2FA, token refresh |
| admin_routes | Gestión usuarios, credenciales Garmin |
| athlete_routes | Perfil, actividades, wellness, GDPR |
| coach_routes | Atletas del coach, workouts, grupos |
| blood_lab_routes | Exámenes de sangre + análisis IA |
| recovery_routes | HRV, recovery score, protoclos |
| adaptive_routes | Plan adaptativo por TSB/compliance |
| mental_routes | MFS 4 factores, protocolos mentales |
| race_routes | Race Day Intelligence, CTL pacing |
| ai_routes | AI Engine v2, workout gen, copilot |
| nutrition_routes | Nutrición de carrera, carbloading |
| food_diary_routes | Diario alimentario, macros |
| performance_analytics_routes | CTL/ATL/TSB, year in review |
| periodization_routes | Gantt temporada, fases |
| zones_routes | Coggan 5-zone, pace zones |
| plan_builder_routes | Planes de entrenamiento |
| workout_prescription_routes | Prescripciones coach→atleta |
| template_routes | Plantillas de plan (Ironman/70.3/Sprint) |
| calendar_routes | Calendario mensual + semanal |
| community_routes | Feed, leaderboard, grupos |
| readiness_routes | Daily Readiness Score |
| injury_risk_routes | Injury risk prediction |
| report_routes | PDF semanal coach/atleta |
| message_routes | Mensajería interna |
| notification_routes | Bell, notificaciones, Web Push |
| strava_routes | OAuth Strava, sync |
| events_routes | Eventos de carrera |
| import_routes | Import .fit/.tcx/.gpx |
| personal_routes | PRs, estadísticas personales |
| week_template_routes | Templates semana |
| notes_macro_routes | Notas coach sobre atleta |
| stripe_routes | Pagos, planes, webhooks |
| admin_routes | Admin panel |
| social_routes | (archivo presente, no registrado) |

**22 service files** con lógica de negocio separada correctamente.

### Esquema de base de datos

**~52 tablas** identificadas (ORM + hot migrations combinados):

| Grupo | Tablas |
|-------|--------|
| Core | users, groups, group_members |
| Actividades | garmin_activities, garmin_training_load, garmin_sync_status |
| Entrenamiento | workout_templates, assigned_workouts, workout_logs |
| Planes | training_plans, plan_sessions, plan_adaptations |
| Wellness | wellness_logs, recovery_scores |
| Analíticas | blood_lab_exams, injury_risk_snapshots |
| Nutrición | food_diary_entries, hydration_logs, weight_logs, supplement_logs, custom_foods, favorite_foods, nutrition_plans, nutrition_insights |
| Comunidad | community_posts, follows, kudos, comments, community_groups, community_group_members, challenges, challenge_entries, community_notifications |
| Racing | race_events |
| Mental | mental_sessions, mental_protocols |
| Periódización | training_phases, macrocycles, macrocycle_weeks |
| Zonas | benchmark_tests |
| Mensajería | messages |
| Notificaciones | notifications, push_subscriptions |
| Seguridad | revoked_tokens, login_attempts, audit_logs, password_reset_tokens, drip_logs |
| Prescripciones | workout_prescriptions |
| Calendario | athlete_calendar_events |

### CI/CD pipeline actual

6 jobs en paralelo:
1. **test** — pytest + coverage (threshold 40%)
2. **lint** — flake8 (max-line 120, ignora E501/W503)
3. **js-check** — node --check nav.js sw.js
4. **docker-build** — docker build (sin push)
5. **security-check** — bandit (HIGH/CRITICAL) + pip-audit
6. **smoke-test** — solo en `main`, levanta uvicorn y chequea 4 endpoints

---

## 2. Arquitectura objetivo

### Principios de diseño

1. **Modular, no microservicios** — el monolito se mantiene, pero se estructura en dominios claros con boundaries explícitos. Los microservicios son prematuros para el volumen actual; añaden latencia de red y complejidad operacional sin beneficio real bajo 10k usuarios.

2. **Stateless app** — toda la sesión en JWT, toda la cache en Redis. La app no guarda estado local. Esto es el prerrequisito para escalar horizontalmente.

3. **Queue para trabajo async** — reemplazar BackgroundTasks con una cola persistente (Celery + Redis o ARQ) para Garmin sync, AI analysis, email, PDF generation.

4. **Single migration system** — Alembic exclusivamente. Eliminar hot migrations en startup.

5. **Observabilidad de primera clase** — métricas, trazas y logs estructurados desde el día uno en prod.

### Diagrama objetivo (12 meses)

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Cloudflare CDN / WAF                                       │
│  - DDoS protection · Bot mitigation · Cache static assets  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  nginx (o Caddy) — Load Balancer                           │
│  - Rate limit por zona (auth/AI/API)                       │
│  - SSL termination                                         │
└──────┬─────────────────────────────────────────────────────┘
       │ round-robin
       ├──────────────┬──────────────┐
       ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ API pod  │  │ API pod  │  │ API pod  │   ← Horizontal scaling
│ uvicorn  │  │ uvicorn  │  │ uvicorn  │     (stateless, 3 instancias)
│ 4 workers│  │ 4 workers│  │ 4 workers│
└────┬─────┘  └────┬─────┘  └────┬─────┘
     └──────────────┴──────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
┌──────────────┐    ┌──────────────────┐
│ PostgreSQL   │    │  Redis Cluster   │
│ (managed)    │    │  - Session cache │
│ - Primary    │    │  - Rate limits   │
│ - 1 replica  │    │  - Job queue     │
│ - PGBouncer  │    │  - Token BL      │
└──────────────┘    └──────────────────┘
                           │
                           ▼
               ┌─────────────────────────┐
               │  Worker pods (Celery)   │
               │  - garmin_sync          │
               │  - ai_analysis          │
               │  - pdf_generation       │
               │  - email_dispatch       │
               └─────────────────────────┘

Observabilidad:
  ┌──────────────────────────────────────────────┐
  │  Prometheus + Grafana (métricas)             │
  │  Sentry (errores + trazas)                   │
  │  Loki + Grafana (logs JSON)                  │
  │  Uptime Robot / BetterStack (alertas)        │
  └──────────────────────────────────────────────┘
```

### Evolución por fases

**Fase A — MVP productivo (ahora → 3 meses)**
- Mantener monolito, 1 instancia
- PostgreSQL managed (Railway/Render)
- Redis managed
- Alembic migrations only (eliminar hot migrations)
- Sentry + estructured logging activos
- Coverage ≥ 70%

**Fase B — Preparar escala (3 → 6 meses)**
- Celery + Redis para Garmin sync y AI calls
- PGBouncer connection pooling
- Prometheus + Grafana básico
- 2 instancias app (blue/green deploy)

**Fase C — Escala real (6 → 12 meses)**
- Cloudflare CDN
- 3+ instancias con auto-scaling
- PostgreSQL replica de lectura
- S3/R2 para archivos (fotos, .fit/.tcx, PDFs)
- Separar dominio AI como servicio independiente si el costo lo justifica

---

## 3. Riesgos de escalabilidad

### CRÍTICO — Resuelto antes del go-live

#### SC-01: Doble registro de rutas
**Impacto:** Todos los routers registrados dos veces (`/api` y `/api/v1`). FastAPI crea ~680 rutas en lugar de ~340. Aumenta tiempo de arranque, memoria, y confunde el router interno.

**Evidencia:**
```python
# coach_main.py líneas 889-958
app.include_router(auth_router, prefix="/api")
# ...34 routers × 2 prefijos
app.include_router(auth_router, prefix="/api/v1")
```

**Fix:** Mantener solo `/api`. Si se necesita versioning futuro, usar un header `API-Version` o un middleware de routing. Riesgo de romper clientes existentes si ya usan `/api/v1` en producción — auditar primero.

#### SC-02: Tres sistemas de migración concurrentes
**Impacto:** `start_coach_api.py::migrate_db()` + inline ALTER TABLEs en `coach_main.py` + Alembic (sin archivos de versión). En deploy multi-instancia, dos pods ejecutarían `migrate_db()` en paralelo → race condition en ALTER TABLE → startup crash.

**Evidencia:**
- `start_coach_api.py` líneas 32-269: 30+ ALTER TABLE y CREATE TABLE
- `coach_main.py` líneas 171-700+: otro bloque de CREATE TABLE inline
- `api/migrations/versions/` — vacío (Alembic sin versiones aplicadas)

**Fix:** Consolidar en Alembic. Ejecutar migraciones como paso dedicado en CI/CD antes del deploy, no en startup de la app.

#### SC-03: AI calls bloqueando workers uvicorn
**Impacto:** Llamadas a Anthropic API en handlers síncronos. Una llamada de 20-30s bloquea un worker thread de uvicorn. Con configuración default (1 worker), toda la API queda bloqueada durante análisis IA. Con 4 workers, un spike de 4 requests simultáneos de AI = app completamente bloqueada.

**Fix a corto plazo:** Mover AI calls a Celery worker. El endpoint devuelve 202 Accepted con job_id; el cliente hace polling o recibe webhook.

**Fix a largo plazo:** Usar `asyncio` + `httpx.AsyncClient` para calls no bloqueantes dentro del event loop.

#### SC-04: BackgroundTasks ≠ queue persistente
**Impacto:** `background_sync_user` usa `SessionLocal()` de producción (no el override de tests). Si la tarea falla, el error se pierde silenciosamente. No hay retry, no hay dead letter queue. Un reinicio del servidor cancela todas las tareas en vuelo.

**Evidencia:** `garmin_pull_service.py:1067` — `db = SessionLocal()` (hardcoded, no injectable).

**Fix:** ARQ o Celery con Redis broker. Tareas persistentes, retry configurable, monitoring en Flower.

### ALTO — Resolver en 90 días

#### SC-05: Sin connection pooling para PostgreSQL
**Impacto:** SQLAlchemy default usa pool de 5 conexiones + 10 overflow. Para 3 pods × 4 workers = potencialmente 60 conexiones en pico. PostgreSQL default permite 100. Sin PGBouncer, un spike de tráfico agota el pool.

**Fix:** Configurar `pool_size`, `max_overflow`, `pool_timeout` en `database.py`. Agregar PGBouncer en modo transaction pooling delante de PostgreSQL.

#### SC-06: Archivos locales en contenedor
**Impacto:** Fotos de actividades (`data/photos/`), PDFs generados, backups — todo en el volumen local del contenedor. Con 2+ instancias, una foto subida al pod A no es visible en el pod B. 

**Fix:** Migrar a S3 / Cloudflare R2 para archivos binarios. Costo ~$0.02/GB/mes.

#### SC-07: Garmin sync síncrono en login
**Impacto:** El login encola Garmin sync si `user.garmin_email` está set. Si Garmin Connect está lento, el sync retarda el background task (no el login en sí). Pero si el task falla, el error se logea como 500 en el request de login.

**Fix:** Evaluar si el sync en login agrega valor real vs. cron cada 6h. Desacoplar completamente.

#### SC-08: SQLite en dev vs PostgreSQL en prod
**Impacto:** Comportamientos divergentes: SQLite tiene locking diferente, tipos de columna más permisivos, sin soporte real para `RETURNING`, sin `pg_trgm` para búsqueda de texto, sin JSON nativo, sin `JSONB` indexable. Un bug que solo aparece en PostgreSQL no se detecta en dev hasta staging/prod.

**Fix:** Proveer un `docker-compose.override.yml` que levante PostgreSQL localmente. El dev local debería poder correr con PostgreSQL con un solo comando.

### MEDIO — Roadmap 6 meses

#### SC-09: Coach_main.py de 960+ líneas
Single entry point que importa 34 módulos, define 3 clases de middleware, configura logging, valida env vars, ejecuta migraciones, registra rutas y monta estáticos. Difícil de mantener y testear de forma aislada.

**Fix:** Extraer en: `create_app()` factory, `configure_logging()`, `run_migrations()`, `register_routers()`.

#### SC-10: Umbral de cobertura al 40%
**Impacto:** 60% del código sin tests. Los tests que sí existen ignoran módulos clave (`test_strava.py`, `test_stripe.py`, `test_year_in_review.py` excluidos del CI).

**Fix:** Subir a 70% en 60 días, 80% en 6 meses. Reforzar Stripe (dinero), Strava OAuth (integración), y rutas de AI.

---

## 4. Seguridad

### Fortalezas actuales

| Control | Estado |
|---------|--------|
| JWT + refresh tokens | ✅ |
| Fernet encryption para credentials Garmin/Strava | ✅ |
| bcrypt password hashing | ✅ |
| 2FA TOTP opcional + backup codes | ✅ |
| Token blacklist (revoked_tokens) | ✅ |
| Token generation counter (invalida todas las sesiones) | ✅ |
| IDOR checks via `assert_coach_owns_athlete` | ✅ (Sprint 36) |
| Role-based access (admin/coach/athlete) | ✅ |
| nginx rate limiting por zona | ✅ |
| Redis rate limiting en API | ✅ |
| GDPR Art. 17/20 (delete + export) | ✅ (Sprint 37) |
| Audit logs | ✅ |
| Sentry error tracking | ✅ (opcional) |
| Startup validation en producción | ✅ |
| Bandit + pip-audit en CI | ✅ |
| TLS 1.2/1.3 + HSTS + CSP headers | ✅ |

### Vulnerabilidades pendientes

#### S-01: Credenciales por defecto en código (CRÍTICO)
**Evidencia:** `start_coach_api.py` líneas 277-281:
```python
admin_pass   = os.getenv("ADMIN_PASS",   "kona2026")   # default inseguro
demo_pass    = os.getenv("DEMO_PASS",    "demo123")    # default inseguro
```
Un deploy sin `.env` → admin con contraseña conocida públicamente.

**Fix:** Eliminar defaults. Si `ADMIN_PASS` no está seteada en producción, `seed_admin()` debe fallar con exit(1). La startup validation ya existe para JWT_SECRET — extenderla.

#### S-02: Redis rate limiting con fallback silencioso
**Evidencia:** `redis_client.py` línea 153:
```python
if count == -1:
    return True, 0   # Redis no disponible — dejar pasar
```
Si Redis cae, toda protección de rate limit desaparece. Un atacante puede causar DoS a Anthropic API o fuerza bruta a login sin freno.

**Fix:** Fallback a DB-based rate limiting vía `login_attempts` table (ya existe). Para endpoints críticos (login, register, AI), el fallback debe ser restrictivo, no permisivo.

#### S-03: CSP con 'unsafe-inline' en scripts
**Evidencia:** `nginx/labx.conf` línea 67:
```
script-src 'self' 'unsafe-inline'
```
Permite XSS via inline scripts. Debería usar nonces o hashes.

**Fix:** Migrar a CSP con nonces generados por el servidor. Requiere cambios en templates HTML para incluir el nonce en cada `<script>`.

#### S-04: OpenAPI docs sin protección en producción
**Evidencia:** `nginx/labx.conf` línea 178-184:
```nginx
location ~ ^/(docs|redoc|openapi.json) {
    proxy_pass http://labx_api;
    # Descomentar para bloquear en producción:
    # return 403;
}
```
El comentario existe pero la instrucción está desactivada. FastAPI expone `/docs` y `redoc` en producción si `ENABLE_DOCS=1` (default en docker-compose).

**Fix:** Proteger con `allow_origins` + `return 403` cuando `APP_ENV=production`, o al menos con HTTP Basic Auth.

#### S-05: Garmin password sin rotación de clave Fernet
**Evidencia:** `docker-compose.yml` línea 15: `FERNET_KEY_OLD` existe (soporte para rotación), pero no hay lógica de re-encriptado automático al rotar la clave.

**Fix:** Implementar un comando de mantenimiento `python manage.py rotate-encryption` que re-encripte todos los `garmin_password` al cambiar `FERNET_KEY`.

#### S-06: CORS en desarrollo es wildcard sin validación
**Evidencia:** `coach_main.py` líneas 162-163:
```python
CORS_ORIGINS = ["*"]
_CORS_CREDS = False  # "*" + credentials=True es inválido
```
En dev local con `CORS_ORIGINS` vacío, CORS es `allow_origins=["*"]`. Si un desarrollador conecta la DB a datos reales en dev, cualquier sitio puede hacer requests cross-origin.

**Fix:** Agregar `CORS_ORIGINS` al `.env.example` con un valor de dev explícito (localhost:3000, etc.).

#### S-07: SQL injection via hot migrations
Las hot migrations en `coach_main.py` y `start_coach_api.py` usan f-strings o concatenación para construir SQL en algunos casos. Aunque son ejecutadas solo al startup (no con input de usuario), es un patrón peligroso que debe eliminarse al migrar a Alembic.

### Checklist de seguridad para go-live

```
[ ] S-01: Eliminar defaults "kona2026" y "demo123" del código
[ ] S-02: Rate limit fallback restrictivo cuando Redis no disponible  
[ ] S-03: CSP sin 'unsafe-inline' (nonces o hashes)
[ ] S-04: Bloquear /docs /redoc en APP_ENV=production
[ ] S-05: Script rotate-encryption implementado
[ ] S-06: .env.example con CORS_ORIGINS explícito
[ ] Confirmar que FERNET_KEY y JWT_SECRET son diferentes
[ ] Pen test de los 10 endpoints más críticos (login, payment, GDPR delete)
[ ] Revisar todos los endpoints con datos financieros (Stripe webhooks)
```

---

## 5. Costos cloud

### Escenario A — Launch (0-200 usuarios activos)

**Plataforma recomendada: Railway (simplicidad) o Render**

| Servicio | Especificación | Costo/mes |
|---------|---------------|-----------|
| App (1 instancia) | 512MB RAM, 0.5 CPU | $10-20 |
| PostgreSQL managed | 1 GB storage, backups | $10-20 |
| Redis managed | 25 MB (rate limit + cache) | $5-10 |
| Dominio + SSL | Let's Encrypt (gratis) | $1-2 |
| **Total** | | **~$26-52/mes** |

**AI costs (Anthropic):**
- 50 análisis/día × 2000 tokens promedio = 100k tokens/día
- Claude Haiku ($0.80/1M input tokens): ~$2.40/mes
- Claude Sonnet ($3.00/1M input tokens): ~$9/mes
- Recomendación: Haiku para análisis de labs, Sonnet para coach copilot

**Total estimado Escenario A: $30-65/mes**

### Escenario B — Crecimiento (200-2000 usuarios activos)

| Servicio | Especificación | Costo/mes |
|---------|---------------|-----------|
| App (2-3 instancias) | 1GB RAM, 1 CPU c/u | $40-80 |
| PostgreSQL managed | 10 GB storage, 2 vCPU, read replica | $40-80 |
| Redis managed | 100 MB | $15-25 |
| Workers Celery (2) | 512MB RAM c/u | $20-40 |
| S3/R2 storage (fotos, PDFs) | 10 GB | $2-5 |
| CDN (Cloudflare) | Free tier | $0-20 |
| Monitoring (Grafana Cloud) | Free tier hasta 10k series | $0-50 |
| **Total** | | **~$117-300/mes** |

**AI costs a este escenario:**
- 500 análisis/día × 2000 tokens = 1M tokens/día
- Claude Haiku: ~$24/mes
- Claude Sonnet (solo premium): ~$15-30/mes adicional

**Total estimado Escenario B: $156-360/mes**

### Escenario C — Escala LATAM (2000-10000 usuarios activos)

| Servicio | Especificación | Costo/mes |
|---------|---------------|-----------|
| App (5+ instancias, auto-scale) | ECS Fargate o Fly.io | $200-400 |
| PostgreSQL (RDS o Cloud SQL) | db.t3.medium + read replica | $150-250 |
| Redis (ElastiCache) | cache.t3.small cluster | $50-100 |
| Workers (5+ Celery) | | $100-200 |
| S3/R2 (100 GB) | | $10-20 |
| CDN + WAF (Cloudflare Pro) | | $20-200 |
| Monitoring full stack | | $50-150 |
| **Total** | | **~$580-1320/mes** |

### Comparativa de plataformas

| Plataforma | Pro | Contra | Ideal para |
|-----------|-----|--------|-----------|
| **Railway** | Deploy simple, PostgreSQL nativo, scaling fácil | Precio escala rápido | Escenario A/B |
| **Render** | Free tier, auto-deploy desde Git | Cold starts en free | Escenario A |
| **Fly.io** | Multi-región, edge deployment, Docker nativo | Curva de aprendizaje | Escenario B/C |
| **AWS ECS** | Total control, ecosistema completo | Complejidad operacional alta | Escenario C |
| **GCP Cloud Run** | Serverless, scale to zero | Cold starts, pricing impredecible | Escenario A/B |

**Recomendación para LabX:** Railway para el go-live (semanas, no meses para configurar). Migrar a Fly.io o AWS cuando se superen 500 usuarios concurrentes o $200/mes de infra.

### Optimizaciones de costo

1. **Cachear respuestas de dashboard** (ya implementado parcialmente vía Redis): 5-min TTL reduce DB queries ~60% para los endpoints más pesados.
2. **Rate limit AI agresivo** (ya implementado): 10 análisis/hora/usuario. A $0.003/análisis con Haiku, 10 usuarios VIP haciendo 10 análisis/hora = $0.30/hora máximo.
3. **Compresión nginx activada** (ya en config): reduce 60-70% bandwidth en responses JSON grandes.
4. **Backups incrementales** vs. full dump diario: PostgreSQL continuous archiving a S3 es más barato que un dump completo.
5. **Índices correctos**: Los queries N+1 en las rutas de analytics (coach.squad_overview) pueden multiplicar por 10 el costo de DB en pico. PGAnalyze o pg_stat_statements para identificar los peores offenders.

---

## 6. Observabilidad

### Estado actual

| Capa | Estado | Gaps |
|------|--------|------|
| Logging | ✅ JSON estructurado en prod | Sin correlación trace_id entre requests |
| Error tracking | ✅ Sentry (opcional, no obligatorio) | No activado por defecto |
| Métricas | ❌ No existe | Sin Prometheus, sin latencia por endpoint |
| Distributed tracing | ❌ No existe | No hay spans, no hay dependency graph |
| Alertas | ❌ No configuradas | Sin PagerDuty/OpsGenie/BetterStack |
| Uptime monitoring | ❌ No configurado | Sin check externo al /health |
| APM | ❌ No existe | No se puede ver tiempo en DB vs. lógica |
| Dashboard ops | ❌ No existe | No hay Grafana/Datadog board |

### Logging actual — análisis

**Fortalezas:**
- `_JsonFormatter` en producción produce líneas JSON parseable por Datadog/CloudWatch/Loki
- Request ID generado en middleware (visible en logs)
- Logs de seguridad: login exitoso/fallido, cambios de contraseña, garmin sync
- Sentry integración disponible vía `SENTRY_DSN`

**Gaps:**
```python
# Actual — sin trace_id cross-request
{"ts": "2026-07-03T...", "level": "INFO", "logger": "labx.auth", "msg": "Login exitoso user_id=xxx"}

# Objetivo — con trace_id y campos estructurados
{"ts": "...", "level": "INFO", "logger": "labx.auth", "msg": "login_success",
 "trace_id": "abc123", "user_id": "xxx", "rol": "athlete", "duration_ms": 12,
 "ip": "1.2.3.4", "region": "SAO"}
```

### Stack de observabilidad objetivo

**Opción A — OSS self-hosted (bajo costo)**
```
Logs:    Promtail → Loki → Grafana
Métricas: Prometheus ← FastAPI /metrics → Grafana  
Errores:  Sentry (cloud, free tier hasta 5k eventos/mes)
Alertas:  Grafana Alerting → Slack/PagerDuty
Uptime:   UptimeRobot (free, 5 monitores)
```
Costo: ~$20/mes por el Grafana Cloud free tier + servidor para Loki

**Opción B — SaaS todo-en-uno (recomendada para go-live)**
```
Logs + Métricas + APM: Datadog (desde $15/host/mes)
  o BetterStack (desde $0, muy buena DX para startups)
  o New Relic Free (100 GB/mes gratis)
Errores: Sentry ($26/mes Business)
Uptime:  BetterStack (gratis hasta 10 monitores)
```

### Implementación mínima viable de observabilidad

Estos cambios tienen máximo impacto, mínimo esfuerzo:

**1. Métricas básicas (2 horas de trabajo)**
```python
# api/metrics.py
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT    = Counter("labx_requests_total", "Total requests", ["method","endpoint","status"])
REQUEST_DURATION = Histogram("labx_request_duration_seconds", "Request duration", ["endpoint"])
DB_QUERY_DURATION = Histogram("labx_db_query_seconds", "DB query duration", ["operation"])

# En coach_main.py — middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_DURATION.labels(request.url.path).observe(time.time() - start)
    return response

@app.get("/metrics")
def get_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

**2. Trace ID en todos los logs (1 hora)**
```python
# Middleware que inyecta trace_id en el contexto del request
import contextvars
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

class _JsonFormatterWithTrace(logging.Formatter):
    def format(self, record):
        payload = {..., "trace_id": _trace_id.get()}
        return json.dumps(payload)
```

**3. Health check enriquecido (30 minutos)**
```python
# Actual: solo 200 OK
# Objetivo: estado de componentes
@app.get("/health")
def health():
    db_ok = check_db()
    redis_ok = redis_client.is_available()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "unavailable",
        "version": BUILD_VERSION,
        "uptime_s": int(time.time() - START_TIME),
    }
```

**4. Sentry obligatorio en producción (15 minutos)**
```python
# Cambiar de opcional a requerido en prod
if _IS_PROD and not _sentry_dsn:
    logger.critical("SENTRY_DSN no configurado en producción — observabilidad comprometida")
    # No bloquear el arranque, pero alertar prominentemente
```

### KPIs de observabilidad a monitorear

| Métrica | Alerta | Acción |
|---------|--------|--------|
| p99 latencia `/api/athlete/dashboard` | > 2s | Revisar queries N+1 |
| Error rate | > 1% | PagerDuty página on-call |
| DB connections activas | > 80% del pool | Escalar o añadir PGBouncer |
| Redis hit rate | < 60% | Revisar TTLs o keys |
| Garmin sync failures/hora | > 10 | Rate limit de Garmin / credenciales |
| AI calls/hora | > 500 | Activar circuit breaker |
| Espacio en disco | > 80% | Escalar volumen |
| Uptime | < 99.5% / 30d | SLA breach, revisión de infra |

---

## 7. Plan de refactorización

### Priorización (impacto × urgencia)

| ID | Trabajo | Impacto | Urgencia | Esfuerzo | Sprint |
|----|---------|---------|----------|---------|--------|
| R-01 | Eliminar credenciales por defecto | Seguridad crítica | 🔴 Hoy | 30 min | S38 |
| R-02 | Bloquear /docs en producción | Seguridad alta | 🔴 Hoy | 15 min | S38 |
| R-03 | Consolidar migrations en Alembic | Arquitectura crítica | 🟠 2 semanas | 3 días | S39 |
| R-04 | Eliminar doble registro de rutas | Rendimiento/claridad | 🟠 2 semanas | 2h | S38 |
| R-05 | Rate limit fallback restrictivo | Seguridad alta | 🟠 2 semanas | 2h | S38 |
| R-06 | Métricas Prometheus + trace_id | Observabilidad | 🟡 1 mes | 1 día | S39 |
| R-07 | Celery worker para Garmin sync | Confiabilidad alta | 🟡 1 mes | 3 días | S40 |
| R-08 | Celery worker para AI calls | Rendimiento alto | 🟡 1 mes | 2 días | S40 |
| R-09 | PostgreSQL en dev local | DX + confiabilidad | 🟡 1 mes | 4h | S39 |
| R-10 | PGBouncer connection pooling | Escalabilidad | 🟡 2 meses | 4h | S41 |
| R-11 | S3/R2 para archivos binarios | Escalabilidad media | 🟢 3 meses | 2 días | S42 |
| R-12 | App factory pattern | Mantenibilidad | 🟢 3 meses | 1 día | S42 |
| R-13 | CSP sin unsafe-inline | Seguridad media | 🟢 3 meses | 3 días | S42 |
| R-14 | Coverage ≥ 70% | Calidad | 🟢 3 meses | 5 días | S43 |

### Sprint 38 — Hardening urgente (1-2 días)

```
R-01: start_coach_api.py — eliminar defaults inseguros
      - admin_pass: fallar hard si ADMIN_PASS no está en env en producción
      - demo_pass: idem o eliminar usuario demo de seed en producción

R-02: nginx/labx.conf — descomentar return 403 para /docs en producción
      + Agregar condicional en coach_main.py: disable Swagger si ENABLE_DOCS != "1"

R-04: coach_main.py — eliminar bloque de rutas /api/v1 (líneas 925-958)
      Auditar si hay clientes que consuman /api/v1 antes de eliminar

R-05: redis_client.py check_rate_limit_redis()
      Si Redis no disponible Y el endpoint es crítico (login, register, AI),
      consultar login_attempts table como fallback restrictivo
```

### Sprint 39 — Migraciones + observabilidad (1 semana)

```
R-03: Consolidar migrations
  1. Exportar schema actual de PostgreSQL prod a Alembic base revision
  2. Eliminar migrate_db() de start_coach_api.py
  3. Eliminar bloque hot-migrations de coach_main.py (líneas 168-700+)
  4. Configurar alembic.ini para leer DATABASE_URL del env
  5. Agregar step "alembic upgrade head" al CI pipeline antes del deploy

R-06: Observabilidad básica
  1. api/metrics.py — Prometheus counters + histograms
  2. GET /metrics endpoint (protegido por IP o token)
  3. Middleware trace_id injection
  4. _JsonFormatter actualizado para incluir trace_id y duration_ms
  5. Sentry obligatorio en producción (warning prominente si no configurado)

R-09: docker-compose.override.yml para PostgreSQL local
  - Levanta postgres:16 en local
  - Permite hacer "docker compose up" con PG real en dev
```

### Sprint 40 — Workers async (1 semana)

```
R-07: Celery para Garmin sync
  1. Instalar celery[redis], flower
  2. api/tasks/garmin_tasks.py — envolver background_sync_user como @app.task
  3. auth_routes.py — reemplazar background_tasks.add_task() con .delay()
  4. docker-compose.yml — agregar servicio celery-worker
  5. Flower dashboard en /flower (protegido)

R-08: Celery para AI calls
  1. api/tasks/ai_tasks.py — analyze_blood_labs, generate_workout, coach_copilot
  2. Endpoints AI devuelven 202 Accepted + job_id
  3. GET /api/ai/jobs/{job_id} para polling
  4. (Opcional) WebSocket o SSE para resultado en tiempo real
```

### Sprint 41 — Infraestructura escala (1 semana)

```
R-10: PGBouncer
  - docker-compose.yml — agregar pgbouncer en modo transaction pooling
  - database.py — pool_size=5, max_overflow=10, pool_timeout=30
  - Pre-flight check: pgbouncer puede servir 100+ conexiones app con 20 conexiones PG

Grafana + Prometheus (self-hosted o Cloud free tier)
  - Dashboard: latency p50/p95/p99, error rate, DB connections, Redis hit rate
  - Alert rule: error rate > 1% → Slack notification

Deploy automático en merge a main
  - .github/workflows/deploy.yml
  - SSH + docker compose pull + docker compose up -d (zero-downtime vía healthcheck)
```

### Sprint 42-43 — Madurez (2-3 semanas)

```
R-11: Archivos a S3/R2
  - api/storage.py — wrapper abstracto (local en dev, S3 en prod)
  - Migrar foto_path en garmin_activities a URL de S3
  - Migrar PDF generation a generar en memoria y subir a S3
  - Signed URLs con 1h de expiración para descargas

R-12: App factory
  - coach_main.py → api/app.py + api/create_app()
  - Permite testear la app con diferentes configs sin efectos globales

R-14: Coverage ≥ 70%
  - Prioridad: Stripe (flujo de pago), Strava OAuth, AI engine
  - Eliminar --ignore de test_stripe.py y test_strava.py en CI
  - Mutation testing (mutmut) en módulos críticos
```

### Métricas de éxito del plan de refactorización

| Métrica | Hoy | Sprint 38 | Sprint 40 | Sprint 43 |
|---------|-----|-----------|-----------|-----------|
| Tests passing | 1676 | 1700+ | 1800+ | 2000+ |
| Coverage | ~40% | 40% | 50% | 70% |
| Hot migrations | 3 sistemas | 2 sistemas | 1 sistema | Alembic only |
| Rutas duplicadas | 2× | 1× | 1× | 1× |
| AI call blocking | Sí | Sí | No (async) | No |
| Observabilidad | Logs + Sentry opt | Logs+Sentry+traces | +Prometheus | +Grafana+alerts |
| Tiempo arranque app | ~3s | ~2s | ~2s | ~1.5s |
| Credenciales por defecto | ⚠️ | ✅ | ✅ | ✅ |

---

## Resumen ejecutivo

**LabX tiene una arquitectura sólida para un MVP pero con 5 deudas técnicas críticas** que deben resolverse antes de escalar:

1. **Credenciales por defecto** en código fuente — riesgo de acceso no autorizado en producción
2. **Tres sistemas de migración** — race condition garantizada en deploy multi-instancia
3. **AI calls bloqueantes** — una ráfaga de 4 requests paralelos de AI bloquea toda la API
4. **Rate limit silencioso** cuando Redis no está disponible — protección fantasma
5. **Doble registro de rutas** — complejidad interna sin beneficio real

Con los Sprints 38-40 (≈10 días de trabajo), LabX pasa de "frágil pero funcional" a "production-ready para 500 usuarios". Los Sprints 41-43 lo llevan a escala de 5000+ usuarios con observabilidad completa.

El costo operacional es manejable: **$30-65/mes para el launch**, escalando linealmente hasta ~$300/mes en 2000 usuarios activos. El mayor riesgo de costo es Anthropic API si se activan las features de AI de forma amplia — implementar el circuit breaker de AI en Sprint 40 es la protección más importante para el P&L.
