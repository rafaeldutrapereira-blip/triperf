"""
LabX Coach Platform — FastAPI entry point
=========================================
Arrancar:
    python start_coach_api.py
  o directamente:
    uvicorn api.coach_main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import logging
from pathlib import Path

# Cargar .env antes de que otros módulos lean variables de entorno
try:
    from dotenv import load_dotenv as _ld
    _ld(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from .database import engine, Base
from .routes.public_routes           import router as public_router
from .routes.auth_routes            import router as auth_router
from .routes.admin_routes           import router as admin_router
from .routes.coach_routes           import router as coach_router
from .routes.athlete_routes         import router as athlete_router
from .routes.week_template_routes   import router as week_template_router
from .routes.personal_routes        import router as personal_router
from .routes.stripe_routes          import router as stripe_router
from .routes.ai_routes              import router as ai_router
from .routes.report_routes          import router as report_router
from .routes.import_routes          import router as import_router
from .routes.message_routes         import router as message_router
from .routes.notification_routes    import router as notification_router
from .routes.strava_routes          import router as strava_router
from .routes.events_routes          import router as events_router
from .routes.blood_lab_routes       import router as blood_lab_router
from .routes.readiness_routes       import router as readiness_router
from .routes.race_routes            import router as race_router
from .routes.food_diary_routes      import router as food_diary_router
from .routes.injury_risk_routes     import router as injury_risk_router
from .routes.plan_builder_routes    import router as plan_builder_router
from .routes.performance_analytics_routes import router as perf_analytics_router
from .routes.community_routes            import router as community_router
from .routes.nutrition_routes            import router as nutrition_router
from .routes.recovery_routes            import router as recovery_router
from .routes.adaptive_routes            import router as adaptive_router
from .routes.mental_routes              import router as mental_router
from .routes.workout_prescription_routes import router as prescription_router
from .routes.periodization_routes       import router as periodization_router
from .routes.periodization_routes       import athlete_router as periodization_athlete_router
from .routes.zones_routes               import router as zones_router
from .routes.zones_routes               import athlete_router as zones_athlete_router
from .routes.template_routes            import router as template_router
from .routes.template_routes            import athlete_router as template_athlete_router
from .routes.calendar_routes            import router as calendar_router

_ROOT_DIR = Path(__file__).resolve().parent.parent
_IS_PROD  = os.getenv("APP_ENV", "development") == "production"

# ── Observability: trace_id + metrics ─────────────────────────────────────────
import time as _time
from .metrics import (
    trace_id_ctx, new_trace_id, current_trace_id,
    http_requests_total, http_request_duration_seconds, active_requests_gauge,
    get_metrics_output,
)

# ── S17: Logging estructurado JSON (producción) vs texto (desarrollo) ──
class _JsonFormatter(logging.Formatter):
    """S17: Emite cada log como una línea JSON — compatible con Datadog/CloudWatch."""
    import json as _json

    def format(self, record: logging.LogRecord) -> str:
        import json
        payload = {
            "ts":       self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":    record.levelname,
            "logger":   record.name,
            "msg":      record.getMessage(),
            "trace_id": current_trace_id() or getattr(record, "trace_id", ""),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key in ("user_id", "request_id", "ip", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if _IS_PROD:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(handler)


_configure_logging()
logger = logging.getLogger("labx")

# ── C-17: Startup validation — falla hard en producción si hay defaults inseguros ──
_INSECURE_DEFAULTS = {
    "JWT_SECRET":  ["CAMBIAR-EN-PRODUCCION", "labx-local-dev-secret", "secret", "changeme"],
    "FERNET_KEY":  ["CAMBIAR-EN-PRODUCCION"],
    "ADMIN_PASS":  ["CAMBIAR-EN-PRODUCCION"],
}
if _IS_PROD:
    _startup_errors = []
    for _var, _bad_prefixes in _INSECURE_DEFAULTS.items():
        _val = os.getenv(_var, "")
        if not _val:
            _startup_errors.append(f"  · {_var} no está configurada")
        elif any(_val.startswith(p) for p in _bad_prefixes):
            _startup_errors.append(f"  · {_var} tiene valor por defecto inseguro")
        elif _var == "JWT_SECRET" and len(_val) < 32:
            _startup_errors.append(f"  · JWT_SECRET debe tener al menos 32 caracteres (tiene {len(_val)})")
    # CORS_ORIGINS vacío en producción implica wildcard — inaceptable
    if not os.getenv("CORS_ORIGINS", "").strip():
        _startup_errors.append("  · CORS_ORIGINS no configurada — CORS wildcard (*) en producción es inseguro")
    # SENTRY_DSN ausente en producción significa errores invisibles
    if not os.getenv("SENTRY_DSN", "").strip():
        _startup_errors.append("  · SENTRY_DSN no configurada — los errores de producción no se reportarán")
    if _startup_errors:
        import sys
        logger.critical("STARTUP ABORTADO — Variables inseguras en producción:\n%s", "\n".join(_startup_errors))
        sys.exit(1)

    # Verificar que SQLite no se use en producción
    _db_url = os.getenv("DATABASE_URL", "")
    if not _db_url or "sqlite" in _db_url:
        logger.critical("STARTUP ABORTADO — DATABASE_URL debe ser PostgreSQL en producción (no SQLite)")
        import sys; sys.exit(1)

    logger.info("Startup validation: todas las variables críticas configuradas correctamente")

# ── Sentry (si SENTRY_DSN configurado) ────────────────────────
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.05,
            environment=os.getenv("APP_ENV", "development"),
        )
        logger.info("Sentry inicializado (env=%s)", os.getenv("APP_ENV"))
    except ImportError:
        logger.warning("sentry-sdk no instalado — pip install sentry-sdk[fastapi]")
elif _IS_PROD:
    logger.warning(
        "SENTRY_DSN no configurada en producción — errores no se reportan a Sentry. "
        "Configurar SENTRY_DSN para habilitar error tracking."
    )

# ── CORS origins desde env ─────────────────────────────────────
_raw_origins = os.getenv("CORS_ORIGINS", "")
if _raw_origins:
    CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    _CORS_CREDS = True
else:
    # Desarrollo local: wildcard sin credentials (compatible con file:// → Origin:null)
    CORS_ORIGINS = ["*"]
    _CORS_CREDS = False  # "*" + credentials=True es inválido en browsers

# Crear tablas si no existen (SQLite auto-bootstrap)
Base.metadata.create_all(bind=engine)

class TraceIdMiddleware(BaseHTTPMiddleware):
    """Injects a unique trace_id per request via contextvars and X-Trace-Id response header."""

    async def dispatch(self, request: Request, call_next):
        tid = request.headers.get("X-Trace-Id") or new_trace_id()
        token = trace_id_ctx.set(tid)
        try:
            response = await call_next(request)
        finally:
            trace_id_ctx.reset(token)
        response.headers["X-Trace-Id"] = tid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status and duration for every request."""

    _SKIP_PATHS = {"/health", "/metrics"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)
        t0 = _time.monotonic()
        active_requests_gauge.inc()
        try:
            response = await call_next(request)
        finally:
            active_requests_gauge.dec()
        duration = _time.monotonic() - t0
        path = request.url.path
        method = request.method
        status = response.status_code
        http_requests_total.labels(method=method, path=path, status=status).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)
        logger.info(
            "%s %s %s %.0fms",
            method, path, status, duration * 1000,
            extra={"duration_ms": round(duration * 1000), "trace_id": current_trace_id()},
        )
        return response


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rechaza requests con body > 1 MB para prevenir abusos — salvo en los
    endpoints de subida de archivos (fotos, GPX, .fit/.tcx), que ya validan
    su propio límite más generoso en el handler (8MB fotos, 15MB GPX, etc.)
    y con un teléfono real esto se pasaba de 1MB casi siempre, tirando 413
    antes de que el request llegara al endpoint (bug real: fotos de cámara
    nunca lograban subirse, ni en avatar ni en galería de actividad).
    """
    _MAX_BYTES = 1 * 1024 * 1024
    _EXEMPT_PREFIXES = (
        "/api/athlete/profile/avatar",
        "/api/athlete/activities/",   # /{id}/photo y /{id}/photos/*
        "/api/import/import-activity",
        "/api/races/parse-gpx",
    )

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(self._EXEMPT_PREFIXES):
            return await call_next(request)
        cl = request.headers.get("content-length")
        if cl and int(cl) > self._MAX_BYTES:
            return JSONResponse(
                {"detail": "Payload demasiado grande (máximo 1 MB)"},
                status_code=413,
            )
        return await call_next(request)


class ContentTypeMiddleware(BaseHTTPMiddleware):
    """
    S2/I-12: Valida Content-Type en POST/PUT/PATCH con body.
    Previene ataques de content-type confusion.
    """
    _MUTATION_METHODS = {"POST", "PUT", "PATCH"}
    _EXEMPT_PATHS = {
        "/api/stripe/webhook",    # Stripe envía text/plain con firma
        "/api/v1/stripe/webhook",
    }

    async def dispatch(self, request: Request, call_next):
        if (request.method in self._MUTATION_METHODS
                and request.url.path not in self._EXEMPT_PATHS):
            ct = request.headers.get("content-type", "")
            cl = request.headers.get("content-length", "0")
            # Solo validar si hay body real
            if int(cl or 0) > 0 and "application/json" not in ct and "multipart/form-data" not in ct:
                return JSONResponse(
                    {"detail": "Content-Type debe ser application/json"},
                    status_code=415,
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Agrega headers de seguridad HTTP a todas las respuestas."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]    = "nosniff"
        response.headers["X-Frame-Options"]           = "DENY"
        response.headers["X-XSS-Protection"]          = "1; mode=block"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
        # No-cache para HTML: fuerza al browser a revalidar en cada visita
        ct = response.headers.get("content-type", "")
        if "text/html" in ct:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"]        = "no-cache"
        # No-cache para /api/*: sin esto el browser puede reusar una respuesta
        # JSON vieja (ej. datos Garmin desactualizados) aunque el usuario haga
        # hard-refresh de la página, porque fetch() posteriores al load no
        # siempre respetan el bypass de caché del hard-refresh.
        elif request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"
            response.headers["Pragma"]        = "no-cache"
        # No-cache para sw.js: es el ÚNICO archivo sin el que las
        # actualizaciones de la PWA no llegan NUNCA, sin importar qué tan
        # agresivo sea el código de auto-reload en athlete-app.html. Sin este
        # header, sw.js cae en el caching heurístico por defecto del browser
        # (basado en Last-Modified) — el propio algoritmo de actualización
        # de Service Worker respeta la caché HTTP normal del script principal
        # salvo que el servidor diga explícitamente que no debe cachearse.
        # Bug real: reg.update() se estaba llamando correctamente pero
        # comparaba contra una copia de sw.js servida desde caché del
        # navegador, nunca contra la versión nueva real — ninguna
        # actualización llegaba a un teléfono ya instalado, sin importar
        # cuántas veces se llamara a reg.update() ni qué tan bueno fuera el
        # listener de controllerchange, porque el navegador nunca detectaba
        # que había un sw.js distinto para empezar.
        elif request.url.path == "/sw.js":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"]        = "no-cache"
        # No-cache para el resto de JS/CSS propios (lx-info.js, dash-header.js,
        # auth.js, nav.js, etc.): mismo bug de fondo que sw.js (Cache-Control
        # ausente = heurística por defecto del browser/CDN), encontrado en
        # vivo el 2026-08-13 — Cloudflare cacheó lx-info.js por 4h (su
        # default para .js) y siguió sirviendo una versión vieja después de
        # un fix real ya deployado. "no-cache" (no "no-store") a propósito:
        # permite cachear pero exige revalidar contra el origen en cada
        # request (usa el ETag/Last-Modified que StaticFiles ya manda),
        # así no se pierde el beneficio de caché para el caso común sin
        # arriesgar servir código viejo cuando sí cambia.
        elif request.url.path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        if os.getenv("APP_ENV", "development") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        return response


@asynccontextmanager
async def lifespan(app):
    # Cargar tokens revocados desde DB al cache en memoria
    from .auth import load_revoked_tokens_from_db
    load_revoked_tokens_from_db()
    logger.info("Cache de tokens revocados cargado desde DB")

    if os.getenv("APP_ENV") != "test":
        from .scheduler import start_scheduler, stop_scheduler
        start_scheduler(os.getenv("DATABASE_URL"))
        yield
        stop_scheduler()
    else:
        yield


import uuid as _uuid_mod
from fastapi import HTTPException as _HTTPExc
from fastapi.exceptions import RequestValidationError as _RVError

_OPENAPI_TAGS = [
    {"name": "auth",     "description": "Autenticación, JWT, 2FA TOTP, reset de contraseña"},
    {"name": "athlete",  "description": "Dashboard, plan de entrenamiento, actividades, GDPR"},
    {"name": "coach",    "description": "Gestión de atletas, grupos, templates, asignaciones"},
    {"name": "garmin",   "description": "Sincronización Garmin Connect — actividades e historial"},
    {"name": "strava",   "description": "OAuth Strava — conectar, sincronizar, desconectar"},
    {"name": "stripe",   "description": "Suscripciones y planes de pago"},
    {"name": "social",   "description": "Follows, kudos y comentarios entre atletas"},
    {"name": "notifications", "description": "Web Push VAPID — suscripción y envío"},
    {"name": "ai",       "description": "Coach IA — preguntas sobre entrenamiento"},
    {"name": "admin",    "description": "Administración del sistema (solo admin)"},
    {"name": "infra",    "description": "Health checks y métricas de infraestructura"},
]

_METRICS_ALLOWED_IPS = {"127.0.0.1", "::1", "0.0.0.0"}
_metrics_start = __import__("time").time()


def create_app() -> FastAPI:
    """
    R-12: App factory — creates and returns a configured FastAPI instance.

    All configuration is read from environment variables (set before calling).
    Calling create_app() multiple times produces independent app instances,
    enabling isolated integration tests without global state.
    """
    _app = FastAPI(
        title       = "LabX Coach API",
        description = (
            "## Plataforma de coaching para triatletas\n\n"
            "API REST para la plataforma **LabX** — gestión de atletas, sincronización Garmin/Strava, "
            "carga de entrenamiento (CTL/ATL/TSB), planes de nutrición y coaching IA.\n\n"
            "### Autenticación\n"
            "Usar `POST /api/auth/login` para obtener un token JWT. "
            "Enviar en header `Authorization: Bearer <token>` o via HttpOnly cookie `lx_access_token`.\n\n"
            "### Base URL\n"
            "Todos los endpoints están disponibles bajo `/api/`."
        ),
        version     = "1.3.0",
        docs_url    = "/docs"  if (not _IS_PROD or os.getenv("ENABLE_DOCS") == "1") else None,
        redoc_url   = "/redoc" if (not _IS_PROD or os.getenv("ENABLE_DOCS") == "1") else None,
        openapi_tags= _OPENAPI_TAGS,
        lifespan    = lifespan,
        contact     = {"name": "LabX Team", "email": "soporte@labx.app"},
        license_info= {"name": "Propietario — uso interno"},
    )

    # ── Middleware stack (LIFO — last added = outermost) ──────────
    _app.add_middleware(GZipMiddleware, minimum_size=1000)
    _app.add_middleware(RequestLoggingMiddleware)
    _app.add_middleware(TraceIdMiddleware)
    _app.add_middleware(ContentTypeMiddleware)
    _app.add_middleware(ContentSizeLimitMiddleware)
    _app.add_middleware(SecurityHeadersMiddleware)
    _app.add_middleware(
        CORSMiddleware,
        allow_origins     = CORS_ORIGINS,
        allow_credentials = _CORS_CREDS,
        allow_methods     = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers     = ["Authorization", "Content-Type", "Accept"],
    )

    # ── Exception handlers ────────────────────────────────────────

    @_app.exception_handler(_HTTPExc)
    async def http_exception_handler(request: Request, exc: _HTTPExc):
        req_id = str(_uuid_mod.uuid4())[:8]
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "errors": [{"code": str(exc.status_code), "message": exc.detail}],
                "request_id": req_id,
            },
            headers=getattr(exc, "headers", None) or {},
        )

    @_app.exception_handler(_RVError)
    async def validation_exception_handler(request: Request, exc: _RVError):
        req_id = str(_uuid_mod.uuid4())[:8]
        errors = []
        for e in exc.errors():
            loc = ".".join(str(l) for l in e.get("loc", []) if l != "body")
            errors.append({"code": "validation_error", "message": e["msg"], "field": loc or None})
        return JSONResponse(
            status_code=422,
            content={"ok": False, "errors": errors, "request_id": req_id},
        )

    @_app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        req_id = str(_uuid_mod.uuid4())[:8]
        logger.error("[%s] Unhandled error on %s %s: %s",
                     req_id, request.method, request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "errors": [{"code": "internal_error", "message": "Error interno del servidor"}],
                "request_id": req_id,
            },
        )

    # ── Routers ───────────────────────────────────────────────────
    _app.include_router(public_router,        prefix="/api")
    _app.include_router(auth_router,          prefix="/api")
    _app.include_router(admin_router,         prefix="/api")
    _app.include_router(coach_router,         prefix="/api")
    _app.include_router(athlete_router,       prefix="/api")
    _app.include_router(week_template_router, prefix="/api")
    _app.include_router(personal_router,      prefix="/api")
    _app.include_router(stripe_router,        prefix="/api")
    _app.include_router(ai_router,            prefix="/api")
    _app.include_router(report_router,        prefix="/api")
    _app.include_router(import_router,        prefix="/api")
    _app.include_router(message_router,       prefix="/api")
    _app.include_router(notification_router,  prefix="/api")
    _app.include_router(strava_router,        prefix="/api")
    _app.include_router(events_router,        prefix="/api")
    _app.include_router(blood_lab_router,     prefix="/api")
    _app.include_router(readiness_router,     prefix="/api")
    _app.include_router(race_router,          prefix="/api")
    _app.include_router(food_diary_router,    prefix="/api")
    _app.include_router(injury_risk_router,   prefix="/api")
    _app.include_router(plan_builder_router,  prefix="/api")
    _app.include_router(perf_analytics_router, prefix="/api")
    _app.include_router(community_router,      prefix="/api")
    _app.include_router(nutrition_router,      prefix="/api")
    _app.include_router(recovery_router,       prefix="/api")
    _app.include_router(adaptive_router,       prefix="/api")
    _app.include_router(mental_router,         prefix="/api")
    _app.include_router(prescription_router,           prefix="/api")
    _app.include_router(periodization_router,          prefix="/api")
    _app.include_router(periodization_athlete_router,  prefix="/api")
    _app.include_router(zones_router,                  prefix="/api")
    _app.include_router(zones_athlete_router,          prefix="/api")
    _app.include_router(template_router,               prefix="/api")
    _app.include_router(template_athlete_router,       prefix="/api")
    _app.include_router(calendar_router,               prefix="/api")

    # ── Infra endpoints ───────────────────────────────────────────

    @_app.get("/health", tags=["infra"])
    def health():
        from .database import engine
        try:
            with engine.connect() as c:
                c.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "service": "labx-coach-api",
            "version": _app.version,
            "db": "ok" if db_ok else "error",
            "env": os.getenv("APP_ENV", "development"),
        }

    @_app.get("/metrics", tags=["infra"], include_in_schema=False)
    def metrics_endpoint(request: Request):
        """Prometheus metrics — restricted to loopback or METRICS_SECRET bearer token."""
        client_ip    = request.client.host if request.client else ""
        auth_header  = request.headers.get("Authorization", "")
        metrics_secret = os.getenv("METRICS_SECRET", "")
        if client_ip not in _METRICS_ALLOWED_IPS:
            if not metrics_secret:
                return JSONResponse({"detail": "metrics not available"}, status_code=404)
            if auth_header != f"Bearer {metrics_secret}":
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        from .metrics import is_available
        if not is_available():
            return JSONResponse({"detail": "prometheus-client not installed"}, status_code=503)
        body, content_type = get_metrics_output()
        from fastapi.responses import Response as _Resp
        return _Resp(content=body, media_type=content_type)

    @_app.get("/api/metrics", tags=["infra"])
    def metrics():
        import time
        from .database import engine
        from sqlalchemy import text as _text
        uptime = time.time() - _metrics_start
        try:
            with engine.connect() as c:
                users      = c.execute(_text("SELECT COUNT(*) FROM users")).scalar()
                activities = c.execute(_text("SELECT COUNT(*) FROM garmin_activities")).scalar()
                db_ok      = 1
        except Exception:
            users = activities = 0
            db_ok = 0
        try:
            from .redis_client import is_available as _redis_ok
            redis_up = 1 if _redis_ok() else 0
        except Exception:
            redis_up = 0
        try:
            from .routes.events_routes import _subscribers
            sse_conns = sum(len(v) for v in _subscribers.values())
        except Exception:
            sse_conns = 0
        lines = [
            "# HELP labx_up API is running", "# TYPE labx_up gauge", "labx_up 1",
            "# HELP labx_uptime_seconds Seconds since start", "# TYPE labx_uptime_seconds counter",
            f"labx_uptime_seconds {uptime:.2f}",
            "# HELP labx_db_up Database connectivity", "# TYPE labx_db_up gauge", f"labx_db_up {db_ok}",
            "# HELP labx_redis_up Redis connectivity", "# TYPE labx_redis_up gauge", f"labx_redis_up {redis_up}",
            "# HELP labx_users_total Total registered users", "# TYPE labx_users_total gauge",
            f"labx_users_total {users}",
            "# HELP labx_activities_total Total synced activities", "# TYPE labx_activities_total gauge",
            f"labx_activities_total {activities}",
            "# HELP labx_sse_connections Active SSE connections", "# TYPE labx_sse_connections gauge",
            f"labx_sse_connections {sse_conns}",
        ]
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    # ── Static frontend ───────────────────────────────────────────
    if _ROOT_DIR.exists():
        from fastapi.responses import FileResponse

        @_app.get("/", include_in_schema=False)
        async def root():
            return FileResponse(str(_ROOT_DIR / "landing.html"))

        _app.mount("/", StaticFiles(directory=str(_ROOT_DIR), html=True), name="frontend")

    return _app


# Module-level app instance — used by uvicorn and test fixtures
app = create_app()
