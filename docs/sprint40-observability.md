# Sprint 40 — Observabilidad (completado 2026-07-03)

## R-06: Observability basics

### Archivos creados/modificados
- `api/metrics.py` — módulo nuevo
- `api/coach_main.py` — 4 cambios
- `api/tests/test_observability.py` — 17 tests nuevos
- `requirements-api.txt` — creado (faltaba)
- `requirements_coach.txt` — añadido prometheus-client

---

### `api/metrics.py`
- `ContextVar[str] trace_id_ctx` — propagado en cada request
- `new_trace_id()` / `current_trace_id()` — helpers
- Prometheus metrics (no-op si prometheus-client no instalado):
  - `labx_http_requests_total` (counter, labels: method, path, status)
  - `labx_http_request_duration_seconds` (histogram, labels: method, path)
  - `labx_active_requests` (gauge)
  - `labx_auth_failures_total` (counter, labels: reason)
- `is_available()` / `get_metrics_output()` — helpers para el endpoint

---

### `api/coach_main.py` — cambios

**`_JsonFormatter` actualizado:**
- Incluye `trace_id` de contextvars en cada log JSON
- Incluye `duration_ms` si presente en el record

**Sentry warning en producción:**
- Si `SENTRY_DSN` no está configurada en `APP_ENV=production`, loguea WARNING

**`TraceIdMiddleware`:**
- Genera `trace_id` (UUID hex 16 chars) por request
- Propaga en contextvars (disponible en todos los logs del request)
- Inyecta `X-Trace-Id` en la respuesta
- Acepta `X-Trace-Id` del cliente (para trazabilidad end-to-end)

**`RequestLoggingMiddleware`:**
- Loguea `METHOD PATH STATUS Xms` para cada request
- Actualiza Prometheus counters + histogram
- Incrementa/decrementa `active_requests_gauge`
- Omite `/health` y `/metrics` para no llenar logs con health checks

**`GET /metrics` endpoint:**
- `include_in_schema=False` — no aparece en OpenAPI docs
- Seguridad: permite si IP es loopback (127.0.0.1, ::1, 0.0.0.0)
- De IPs externas: requiere `Authorization: Bearer $METRICS_SECRET`
- Sin `METRICS_SECRET` configurado: retorna 404 desde IPs externas
- Retorna 503 si prometheus-client no instalado

**`requirements-api.txt` creado:**
- Unifica dependencias API en un archivo que el CI ya referenciaba
- Incluye `prometheus-client>=0.20.0` como opcional

---

### Tests (17 nuevos)
- `TestTraceId` (7): header presente, hex 16 chars, unique por request, echo de cliente, 404, errors
- `TestMetricsEndpoint` (5): endpoint existe, no en schema, blocked sin secret, accesible con secret, bloqueado con wrong secret
- `TestMetricsModule` (5): imports, new_trace_id format, ctx default, output types, noop methods

---

### Variables de entorno nuevas
| Variable | Default | Descripción |
|---|---|---|
| `METRICS_SECRET` | `""` | Bearer token para acceder a `/metrics` desde IPs externas |
| `SENTRY_DSN` | `""` | Ya existía — ahora loguea WARNING en prod si no configurada |

---

### Tests
1658 passed, 0 failures (+17 vs Sprint 39)
