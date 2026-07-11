# LabX — Programa Dogfood Interno (FASE 7)
**Duración:** 14 días  
**Participantes:** Founder (Rafael) + 2-3 usuarios seleccionados  
**Objetivo:** Detectar bugs reales, validar UX, medir retención de uso diario

---

## Participantes Beta

| Rol | Perfil ideal | Acceso |
|-----|-------------|--------|
| Founder | Triatleta activo, conoce el sistema | admin + atleta |
| Beta 1 | Triatleta Ironman, poco técnico | atleta |
| Beta 2 | Coach/entrenador, experiencia digital media | coach + atleta |
| Beta 3 | Triatleta sprint/olímpico, nativo digital | atleta |

**Onboarding:** Cada participante recibe un link de invitación por email con:
- URL: `https://beta.labx.app`
- Usuario/contraseña Basic Auth (mismos para todos)
- Guía de 5 pasos para conectar Garmin
- Canal de comunicación (WhatsApp group o Slack)

---

## Plan de Uso Diario

### Semana 1 — Core Features

| Día | Tarea | Feature | Métrica |
|-----|-------|---------|---------|
| D1 | Crear cuenta + conectar Garmin | Auth + Garmin sync | Tiempo setup < 5 min |
| D1 | Ver dashboard por primera vez | Dashboard | Primera impresión |
| D2 | Revisar entrenamiento de ayer | Dashboard + Activities | Datos correctos vs Garmin |
| D3 | Cargar análisis de sangre | Blood Labs | Lab parsing correcto |
| D4 | Explorar recomendaciones nutrición | Nutrition | Recomendaciones relevantes |
| D5 | Check Daily Readiness Score | Readiness | HRV correlacionado con sensación |
| D6 | Ver Recovery page post carrera dura | Recovery | Recovery score vs percepción |
| D7 | Retrospectiva semana 1 | — | Feedback general |

### Semana 2 — Advanced Features

| Día | Tarea | Feature | Métrica |
|-----|-------|---------|---------|
| D8 | Explorar Analytics CTL projection | Analytics | Proyección razonable |
| D9 | Crear goal race + countdown | Race countdown | Cuenta correcta |
| D10 | AI Coach: preguntas sobre entrenamiento | AI Coach | Respuestas útiles/relevantes |
| D11 | Ver Mental Performance metrics | Mental | Correlación con estado real |
| D12 | Explorar Calendar y próximas sesiones | Calendar | Sesiones importadas |
| D13 | Simular flujo coach (Beta 2) | Coach platform | Prescripción llega al atleta |
| D14 | Retrospectiva + NPS survey | — | NPS ≥ 7 |

---

## Métricas de Éxito

### Engagement
| Métrica | Objetivo | Medición |
|---------|----------|----------|
| DAU/MAU | ≥ 70% (de 3-4 usuarios) | Logins únicos/día |
| Sessions/user/day | ≥ 1 | Logs de auth |
| Avg session length | ≥ 5 min | Logs de actividad |
| Garmin sync exits | 0 | Celery error logs |

### Calidad
| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Crash rate | < 1% de sesiones | Sentry |
| 5xx rate | < 0.1% | Prometheus |
| P95 API latency | < 500ms | Grafana |
| Backup exitoso diario | 100% | Cron logs |

### NPS Survey (Día 14)
Preguntas clave:
1. ¿Del 0 al 10, qué tan probable es que recomiendes LabX a otro triatleta?
2. ¿Qué feature usaste más? ¿Por qué?
3. ¿Qué feature encontraste confuso o roto?
4. ¿Qué te faltó que esperabas encontrar?
5. ¿Pagarías por LabX? ¿Cuánto/mes?

---

## Bug Tracker

| ID | Fecha | Reporter | Feature | Descripción | Severidad | Estado | Fix |
|----|-------|----------|---------|-------------|-----------|--------|-----|
| | | | | | | | |

**Severidades:**
- P0: Crash / pérdida de datos / auth roto
- P1: Feature principal no funciona
- P2: Feature secundario degradado
- P3: UI/UX mejorable, no roto

**SLA de respuesta:**
- P0: Fix en < 4 horas (War Room activado)
- P1: Fix en < 24 horas
- P2: Fix en 3-5 días
- P3: Backlog priorizado post-go-live

---

## Comunicación con Beta Testers

### Reglas de oro
1. **Nunca** pedir credenciales de Garmin/Strava por chat — ellos las ingresan en la app
2. Responder todos los bugs en < 2 horas (aunque el fix tome más)
3. Comunicar proactivamente downtime o mantenimiento
4. Agradecer feedback — cada bug es un regalo

### Canal WhatsApp/Slack
- Formato de reporte: `[BUG][Feature] Descripción + screenshot`
- Actualizaciones de deploy: "Deploy v1.2 ✅ — fixes: X, Y, Z"
- Encuesta NPS: Google Forms, día 14

---

## Go/No-Go desde Dogfood

**GO si:**
- NPS ≥ 7 (mediana)
- 0 P0 bugs abiertos
- ≤ 2 P1 bugs abiertos con workaround documentado
- DAU/MAU ≥ 60%
- Al menos 2 usuarios dicen que "lo usarían diariamente"

**NO GO si:**
- NPS < 5
- Garmin sync falla consistentemente
- Cualquier P0 sin fix en la semana 2
- Ningún usuario lo usó después del día 3
