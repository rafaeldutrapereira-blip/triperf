# LabX — War Room (FASE 8) — 7 días de estabilización
**Activar:** Inmediatamente después del Dogfood Program  
**Duración:** 7 días  
**Regla principal:** CERO features nuevas. Solo fixes, performance, UX.

---

## Objetivos de la War Room

1. Resolver todos los P0 y P1 del dogfood
2. Optimizar las 3 métricas más débiles (según Grafana)
3. Preparar `CHANGELOG.md` para el go-live
4. Verificar que backups funcionan (restaurar uno manualmente)
5. Escribir runbook de incidentes

---

## Estructura de Día Tipo

| Hora | Actividad |
|------|-----------|
| 08:00 | Review Sentry errors del día anterior |
| 08:30 | Review Prometheus alerts |
| 09:00 | Fix P0/P1 identificados |
| 12:00 | Deploy incremental (si hay fixes) |
| 17:00 | Review Grafana métricas del día |
| 17:30 | Actualizar bug tracker |
| 18:00 | Comunicar a beta testers (si hay fixes) |

---

## Criterios de Salida (para ir a FASE 9)

| Criterio | Target | Cómo medir |
|----------|--------|------------|
| P0 abiertos | 0 | Bug tracker |
| P1 abiertos | ≤ 1 con workaround | Bug tracker |
| 5xx rate | < 0.1% en 48h | Prometheus |
| P95 latency core endpoints | < 500ms | Grafana |
| Backup restore exitoso | 1 restore manual OK | Manual check |
| Uptime 7 días | > 99.5% | Grafana uptime |
| Garmin sync success rate | > 95% | Celery logs |

---

## Runbook de Incidentes

### Incident Severity Levels
- **SEV1:** API completamente caída (usuarios no pueden login)
- **SEV2:** Feature principal rota (ej: Garmin sync, dashboard no carga)
- **SEV3:** Feature secundaria degradada (ej: AI lento, un módulo falla)
- **SEV4:** UI/UX issue, sin impacto funcional

### SEV1 Response Protocol
1. **T+0:** Detectar (Prometheus alert o reporte usuario)
2. **T+5min:** Verificar con `bash deploy/smoke_test.sh`
3. **T+10min:** Si smoke fails → `bash deploy/rollback.sh`
4. **T+15min:** Comunicar a beta testers: "Detectamos un problema, trabajando en ello"
5. **T+60min:** Root cause analysis
6. **T+2h:** Fix + nuevo deploy o confirm rollback es solución
7. **T+4h:** Post-mortem escrito (qué pasó, por qué, cómo prevenir)

### Comandos de Emergencia
```bash
# Ver logs en tiempo real
docker compose -f docker-compose.prod.yml logs -f api

# Restart rápido sin rebuild
bash deploy/update.sh --env-reload

# Rollback al tag anterior
bash deploy/rollback.sh

# Ver estado de todos los servicios
docker compose -f docker-compose.prod.yml ps

# Verificar Celery workers
docker compose -f docker-compose.prod.yml exec worker \
    celery -A api.worker.celery_app inspect active

# Conectar a DB directo
docker compose -f docker-compose.prod.yml exec db \
    psql -U labx -d labx_prod

# Forzar backup manual
docker compose -f docker-compose.prod.yml exec backup python backup.py

# Ver métricas de Redis
docker compose -f docker-compose.prod.yml exec redis redis-cli info stats
```

---

## Daily Incident Report Template

```
LABX DAILY REPORT — [FECHA]
============================

UPTIME: XX.X%
ERRORES 5xx: X (Y% de requests)
P95 LATENCIA: Xms

INCIDENTES DEL DÍA:
  - Ninguno / [descripción]

FIXES DEPLOYADOS:
  - [ID] [descripción del fix]

MÉTRICAS CLAVE:
  - Usuarios activos: X
  - Syncs Garmin exitosos: X/Y (Z%)
  - AI requests: X

MAÑANA:
  - [prioridades]
```

---

## Post-War Room Checklist

Antes de entrar a FASE 9 (Certificación), verificar:

- [ ] Todos los criterios de salida cumplidos
- [ ] CHANGELOG.md escrito con todos los fixes
- [ ] Runbook de incidentes probado al menos una vez
- [ ] Backup restaurado manualmente y verificado
- [ ] `.env.production.example` actualizado con cualquier variable nueva
- [ ] SSL certbot renewal testado: `certbot renew --dry-run`
- [ ] E2E suite pasa en 100%: `pytest e2e/ -q`
- [ ] Unit tests pasan: `pytest api/tests/ --noconftest -q`
