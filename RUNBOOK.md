# LabX — Runbook de Operaciones

**Versión:** BUILD 28 / Sprint 46  
**Última actualización:** 2026-07-04  
**SLA respuesta a incidente crítico:** < 1 hora  
**SLA respuesta a incidente alto:** < 4 horas

---

## 1. Arranque del sistema

### Desarrollo local
```bash
cd C:\Users\rafae\projects\LabX
uvicorn api.coach_main:app --reload --host 0.0.0.0 --port 8000
```

### Producción (Docker)
```bash
docker compose -f docker-compose.prod.yml up -d
# Deploy completo (recomendado):
bash deploy/deploy.sh
# Verificar salud:
curl https://beta.labx.app/health
```

### Verificación de arranque exitoso
```
GET /health → {"status": "ok", "db": "ok", "redis": "ok"}
GET /metrics → líneas con labx_http_requests_total > 0
```

---

## 2. Diagnóstico rápido (< 5 minutos)

### El servidor no responde
```bash
# 1. ¿Está corriendo?
docker compose -f docker-compose.prod.yml ps
# Si está caído:
docker compose -f docker-compose.prod.yml up -d api
# 2. Ver logs del último arranque:
docker compose -f docker-compose.prod.yml logs api --tail 100
# 3. Smoke test rápido:
bash deploy/smoke_test.sh
```

### Base de datos no accesible
```bash
# PostgreSQL producción:
docker compose -f docker-compose.prod.yml exec db psql -U labx -d labx_prod -c "SELECT 1;"
# Via PGBouncer:
docker compose -f docker-compose.prod.yml exec pgbouncer psql -h 127.0.0.1 -p 6432 -U labx -d labx_prod -c "SELECT 1;"
```

### Redis no accesible
```bash
docker compose -f docker-compose.prod.yml exec redis redis-cli ping  # debe responder PONG
```

### Errores en Sentry
1. Ir a https://sentry.io/ → proyecto LabX
2. Filtrar por `level:error` en las últimas 24h
3. Los errores más frecuentes primero son los más prioritarios

---

## 3. Incidentes críticos (P0)

### INCIDENTE: Credencial comprometida / token JWT robado

**Síntoma:** Acceso no autorizado a datos de atleta detectado.  
**Acciones (en orden):**
1. Revocar token inmediatamente:
   ```bash
   python -c "
   from api.database import SessionLocal
   from api.models import RevokedToken
   from datetime import datetime, timedelta, timezone
   db = SessionLocal()
   db.add(RevokedToken(token_hash='<SHA256_DEL_TOKEN>', expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
   db.commit()
   db.close()
   "
   ```
2. Incrementar `token_gen` del usuario afectado (invalida todas sus sesiones):
   ```sql
   UPDATE users SET token_gen = token_gen + 1 WHERE email = '<email>';
   ```
3. Cambiar `JWT_SECRET` en producción → reiniciar servidor → todos los tokens son inválidos.
4. Notificar al usuario afectado por email.
5. Documentar el incidente con timestamp y acciones tomadas.

---

### INCIDENTE: Base de datos corrompida / accidente de datos

**Síntoma:** Errores SQL masivos, datos inconsistentes, DROP accidental.  
**Acciones:**
1. Parar el servidor inmediatamente:
   ```bash
   docker compose -f docker-compose.prod.yml stop api worker
   ```
2. Verificar el backup más reciente:
   ```bash
   docker compose -f docker-compose.prod.yml exec backup python backup.py --list
   ```
3. Restaurar desde backup PostgreSQL:
   ```bash
   # Restaurar dump SQL:
   docker compose -f docker-compose.prod.yml exec db psql -U labx -d labx_prod < backups/labx_<TIMESTAMP>.sql
   # (o .sql.gz descomprimido primero: gunzip labx_<TIMESTAMP>.sql.gz)
   ```
4. Reiniciar el servidor:
   ```bash
   docker compose -f docker-compose.prod.yml up -d api worker
   ```
5. Verificar integridad:
   ```bash
   curl http://localhost:8000/health
   ```
6. **RTO objetivo:** < 4 horas. **RPO objetivo:** < 24 horas (último backup nocturno).

---

### INCIDENTE: Garmin API down / sync masivo fallando

**Síntoma:** `garmin_sync_status.status = 'error'` para múltiples usuarios.  
**Acciones:**
1. Verificar estado de la API de Garmin (downtime externo):
   - https://status.garmin.com
2. Si es downtime de Garmin → esperar, no hay acción de nuestra parte.
3. Si es error nuestro → revisar logs de Celery:
   ```bash
   docker compose -f docker-compose.prod.yml logs worker --tail 100 | grep ERROR
   ```
4. Si el token expiró (`needs_reauth`):
   - El usuario debe reconectar desde Mi Perfil → Garmin.
   - No hay acción del servidor.

---

### INCIDENTE: Stripe webhook fallando (pagos no procesados)

**Síntoma:** Pagos completados en Stripe Dashboard pero `plan_nivel` no actualizado en DB.  
**Acciones:**
1. Verificar el endpoint del webhook:
   ```bash
   curl -X POST http://localhost:8000/api/stripe/webhook -H "Content-Type: application/json" -d '{}'
   # Esperar 400 (firma inválida) — si es 404, el endpoint está caído
   ```
2. Revisar logs de Stripe Dashboard → Webhooks → intentos fallidos.
3. Si el webhook falló, re-enviarlo desde Stripe Dashboard.
4. Actualización manual de emergencia (último recurso):
   ```sql
   UPDATE users SET plan_nivel = 'pro' WHERE stripe_customer_id = 'cus_<ID>';
   ```

---

### INCIDENTE: API con latencia > 2s / sistema lento

**Síntoma:** Usuarios reportan lentitud. `/metrics` muestra P95 > 2s.  
**Diagnóstico:**
```bash
# Ver métricas de latencia:
curl http://localhost:8000/metrics | grep labx_http_request_duration

# Ver queries lentas en SQLite (si es en dev):
python -c "
import sqlite3
conn = sqlite3.connect('data/labx_coach.db')
conn.set_trace_callback(print)
conn.execute('SELECT COUNT(*) FROM garmin_activities')
"
```
**Causas comunes:**
- Query N+1 en un endpoint de lista → agregar `.joinedload()`
- DB bloqueada por escritura larga → revisar locks
- Redis saturado → `docker exec labx-redis redis-cli info memory`

---

## 4. Mantenimiento preventivo

### Diario (automático)
- Backup: `python backup.py` (cron 02:00 via Task Scheduler)
- Limpieza de tokens revocados expirados (automática en cada login)

### Semanal (manual — lunes)
```bash
# 1. Verificar que el último backup existe y tiene tamaño > 0:
docker compose -f docker-compose.prod.yml exec backup python backup.py --list

# 2. Verificar alembic current:
docker compose -f docker-compose.prod.yml run --rm api alembic current
# debe mostrar d1e2f3a4b5c6 (head)

# 3. Smoke tests:
bash deploy/smoke_test.sh

# 4. Ver errores en Sentry de los últimos 7 días

# 5. Revisar pip-audit en CI — ver GitHub Actions → security-check
```

### Mensual
- Rotar `JWT_SECRET` (requiere que todos los usuarios vuelvan a loguearse)
- Revisar que los backups en S3/almacenamiento externo existen
- Actualizar dependencias:
  ```bash
  pip list --outdated
  pip install --upgrade <paquetes-críticos>
  ```

---

## 5. Deploy de nueva versión

```bash
# Deploy completo automatizado (recomendado):
bash deploy/deploy.sh

# Update incremental (sin rebuild completo):
bash deploy/update.sh

# Solo static files (0 downtime):
bash deploy/update.sh --static-only
```

**Rollback de emergencia:**
```bash
bash deploy/rollback.sh                 # Rollback al tag anterior automáticamente
bash deploy/rollback.sh v1.2.3          # Rollback a tag específico
```

---

## 6. Escalamiento de incidentes

| Severidad | Tiempo máx. respuesta | Acción |
|-----------|----------------------|--------|
| P0 — Sistema caído / brecha de seguridad | 30 minutos | Notificar a todos los usuarios afectados. Parar el servidor si hay riesgo de datos. |
| P1 — Funcionalidad crítica degradada | 2 horas | Investigar causa raíz. Comunicar ETA a usuarios. |
| P2 — Bug funcional no crítico | 24 horas | Crear issue en el backlog. Fix en próximo sprint. |
| P3 — Mejora o problema cosmético | 72 horas | Backlog. Sin comunicación proactiva. |

---

## 7. Contactos de emergencia

| Proveedor | Soporte | Panel |
|-----------|---------|-------|
| Anthropic (IA) | console.anthropic.com | Status: status.anthropic.com |
| Stripe | dashboard.stripe.com/support | Status: status.stripe.com |
| Garmin Connect | developer.garmin.com/support | Status: status.garmin.com |
| Sentry | sentry.io/support | sentry.io |

---

## 8. Comandos de utilidad frecuente

```bash
# Estado de todos los servicios
docker compose -f docker-compose.prod.yml ps

# Ver logs en tiempo real
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f worker

# Test de salud del servidor
curl https://beta.labx.app/health

# Smoke tests
bash deploy/smoke_test.sh

# Métricas Prometheus (desde el servidor)
curl http://127.0.0.1:8000/metrics | grep labx_

# Último backup
docker compose -f docker-compose.prod.yml exec backup python backup.py --list

# Estado de Alembic
docker compose -f docker-compose.prod.yml run --rm api alembic current

# Conectar a PostgreSQL directo
docker compose -f docker-compose.prod.yml exec db psql -U labx -d labx_prod

# Verificar roles en DB
docker compose -f docker-compose.prod.yml exec db \
    psql -U labx -d labx_prod -c "SELECT DISTINCT rol FROM users;"

# Redis stats
docker compose -f docker-compose.prod.yml exec redis redis-cli info stats

# Celery workers activos
docker compose -f docker-compose.prod.yml exec worker \
    celery -A api.worker.celery_app inspect active
```
