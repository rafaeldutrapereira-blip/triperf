# LabX — Certificación GO / NO GO (FASE 9)
**Board:** CTO + CEO + Dev  
**Fecha de revisión:** [completar]  
**Versión evaluada:** [completar — git SHA]

---

## Scorecard de Certificación

### Dominio 1: Infraestructura y Despliegue

| Criterio | Estado | Evidencia | Puntos |
|----------|--------|-----------|--------|
| HTTPS enforced (HTTP → 301 HTTPS) | ☐ PASS / ☐ FAIL | | 5 |
| SSL válido, TLSv1.2+ solamente | ☐ PASS / ☐ FAIL | | 5 |
| Private Beta Basic Auth activo | ☐ PASS / ☐ FAIL | | 5 |
| Docker Compose prod running estable | ☐ PASS / ☐ FAIL | | 5 |
| Alembic `upgrade head` sin errores | ☐ PASS / ☐ FAIL | | 5 |
| Backup diario automático funcional | ☐ PASS / ☐ FAIL | | 5 |
| Restore manual exitoso (test real) | ☐ PASS / ☐ FAIL | | 5 |
| **Subtotal** | | | **/35** |

### Dominio 2: Seguridad

| Criterio | Estado | Evidencia | Puntos |
|----------|--------|-----------|--------|
| OWASP A01-A10 auditado (FASE 4) | ☐ PASS / ☐ FAIL | security_audit.md | 5 |
| Secrets no hardcoded en repo | ☐ PASS / ☐ FAIL | `git grep JWT_SECRET` → vacío | 10 |
| Rate limiting login funcional | ☐ PASS / ☐ FAIL | test_429 E2E | 5 |
| Token HttpOnly cookie verificado | ☐ PASS / ☐ FAIL | DevTools | 5 |
| Archivos .env/.py bloqueados | ☐ PASS / ☐ FAIL | curl 404 | 5 |
| API docs deshabilitados en prod | ☐ PASS / ☐ FAIL | curl 404 /docs | 5 |
| **Subtotal** | | | **/35** |

### Dominio 3: Disponibilidad y Performance

| Criterio | Estado | Evidencia | Puntos |
|----------|--------|-----------|--------|
| Uptime ≥ 99.5% últimos 7 días | ☐ PASS / ☐ FAIL | Grafana uptime panel | 10 |
| 5xx rate < 0.1% últimas 48h | ☐ PASS / ☐ FAIL | Prometheus `rate(http_requests[1h])` | 10 |
| P95 latency core endpoints < 500ms | ☐ PASS / ☐ FAIL | Grafana latency panel | 5 |
| Health endpoint responde < 200ms | ☐ PASS / ☐ FAIL | `curl -w "%{time_total}"` | 5 |
| Garmin sync success rate ≥ 95% | ☐ PASS / ☐ FAIL | Celery logs | 5 |
| **Subtotal** | | | **/35** |

### Dominio 4: Observabilidad

| Criterio | Estado | Evidencia | Puntos |
|----------|--------|-----------|--------|
| Logs JSON estructurados en prod | ☐ PASS / ☐ FAIL | `docker logs api` | 5 |
| Sentry recibe errores reales | ☐ PASS / ☐ FAIL | Sentry dashboard | 5 |
| Grafana dashboards activos | ☐ PASS / ☐ FAIL | SSH tunnel + screenshot | 5 |
| Alertas Prometheus configuradas | ☐ PASS / ☐ FAIL | alerting_rules.yml | 5 |
| **Subtotal** | | | **/20** |

### Dominio 5: Validación Funcional

| Criterio | Estado | Evidencia | Puntos |
|----------|--------|-----------|--------|
| E2E suite: 130 PASS, 0 FAIL | ☐ PASS / ☐ FAIL | `pytest e2e/ -q` output | 10 |
| Unit tests: ≥ 1900 PASS, 0 FAIL | ☐ PASS / ☐ FAIL | `pytest api/tests/ -q` output | 10 |
| Smoke tests post-deploy: 0 FAIL | ☐ PASS / ☐ FAIL | `bash deploy/smoke_test.sh` | 5 |
| E2E Validation FASE 6 ≥ 90% | ☐ PASS / ☐ FAIL | e2e_validation_plan.md | 10 |
| Garmin sync end-to-end founder | ☐ PASS / ☐ FAIL | Manual test personal | 10 |
| **Subtotal** | | | **/45** |

### Dominio 6: Dogfood Program

| Criterio | Estado | Evidencia | Puntos |
|----------|--------|-----------|--------|
| ≥ 3 usuarios completaron onboarding | ☐ PASS / ☐ FAIL | Auth logs | 5 |
| DAU/MAU ≥ 60% durante 14 días | ☐ PASS / ☐ FAIL | Login logs | 5 |
| NPS mediana ≥ 7 | ☐ PASS / ☐ FAIL | Survey results | 10 |
| P0 bugs: 0 abiertos | ☐ PASS / ☐ FAIL | Bug tracker | 10 |
| P1 bugs: ≤ 1 abierto con workaround | ☐ PASS / ☐ FAIL | Bug tracker | 5 |
| **Subtotal** | | | **/35** |

---

## Scoring

| Dominio | Máximo | Obtenido |
|---------|--------|----------|
| 1. Infraestructura | 35 | |
| 2. Seguridad | 35 | |
| 3. Disponibilidad | 35 | |
| 4. Observabilidad | 20 | |
| 5. Validación funcional | 45 | |
| 6. Dogfood | 35 | |
| **TOTAL** | **205** | |

### Umbrales de Decisión

| Score | Decisión | Acción |
|-------|----------|--------|
| ≥ 185 (90%) | **GO** ✅ | Proceder con invitaciones beta privada |
| 165-184 (80-89%) | **GO CONDICIONAL** ⚠ | Go con plan de fix en 72h para gaps |
| 145-164 (70-79%) | **NO GO — REMEDIAR** 🔶 | War Room extendido, re-certificar |
| < 145 (< 70%) | **NO GO** ❌ | Parar, redefinir prioridades |

---

## Items Bloqueantes (veto automático)

Independientemente del score, si cualquiera de estos falla → **NO GO**:

- [ ] Secrets (JWT_SECRET, FERNET_KEY) en texto plano en repo o logs
- [ ] Cualquier P0 bug abierto sin workaround
- [ ] API docs (`/docs`) accesible en producción
- [ ] Backup nunca se ejecutó exitosamente
- [ ] SSL expirado o self-signed
- [ ] Garmin sync completamente roto (0% success rate)

---

## Decisión Final

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  LABX BETA — DECISIÓN GO / NO GO
  Fecha: [completar]
  Score: [X] / 205 ([Y]%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  DECISIÓN: [ ] GO  [ ] GO CONDICIONAL  [ ] NO GO

  Rationale:
  ___________________________________________
  ___________________________________________
  ___________________________________________

  Items pendientes para próximo milestone:
  1. ___________________________________________
  2. ___________________________________________
  3. ___________________________________________

  Firmado: Rafael Dutra (Founder/CEO/CTO)
  Fecha:   [completar]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Post-GO: Siguiente Milestone

Si la decisión es GO, las prioridades inmediatas son:

1. **Expansión beta:** Invitar 10-20 triatletas seleccionados (boca a boca)
2. **Dominio production:** `app.labx.app` con Cloudflare + DNS final
3. **React Native MVP:** Auth + Dashboard + Notificaciones push
4. **Stripe producción real:** Activar con primeros pagos reales
5. **Coach beta partnerships:** 2-3 coaches reales con atletas reales
6. **PostgreSQL backup a S3:** Reemplazar backup local por backup remoto
7. **Dependabot alerts:** Monitorear CVEs semanalmente
