# LabX — Plan de Validación End-to-End (FASE 6)
**Ejecutar:** Founder (Rafael) personalmente en beta.labx.app  
**Duración estimada:** 2-3 horas  
**Prerequisito:** Deploy completo funcionando, smoke tests en verde

---

## Checklist de Validación

### 1. Infraestructura Base
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| I-01 | HTTPS forzado | Acceder a `http://beta.labx.app` | Redirect 301 → HTTPS | ☐ |
| I-02 | Certificado SSL válido | Ver candado en browser | Válido, no expirado, Let's Encrypt | ☐ |
| I-03 | Private Beta Basic Auth | Acceder a `https://beta.labx.app` sin auth | Prompt HTTP Basic Auth | ☐ |
| I-04 | Health endpoint | `curl https://beta.labx.app/health` | `{"status":"ok","db":"ok"}` | ☐ |
| I-05 | API docs ocultos | Acceder a `/docs` y `/redoc` | 404 Not Found | ☐ |
| I-06 | Archivos sensibles bloqueados | `curl https://beta.labx.app/.env` | 404 | ☐ |
| I-07 | Métricas bloqueadas externamente | `curl https://beta.labx.app/api/metrics` | 200 (API metrics JSON) | ☐ |
| I-08 | Prometheus solo loopback | Desde servidor: `curl localhost:9090` | OK; desde internet: bloqueado | ☐ |

### 2. Autenticación y Registro
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| A-01 | Registro nuevo usuario | Formulario con email, nombre, contraseña válida | Cuenta creada, email de bienvenida | ☐ |
| A-02 | Password débil rechazado | Registrar con "12345678" | Error: falta mayúscula/minúscula/número | ☐ |
| A-03 | Login exitoso | Email + password correcto | Token, redirect a dashboard | ☐ |
| A-04 | Login fallido | Password incorrecto | 401, no revela si email existe | ☐ |
| A-05 | Rate limit login | 11 intentos fallidos en 1 hora | 429 con Retry-After header | ☐ |
| A-06 | Token en cookies HttpOnly | DevTools → Application → Cookies | `lx_access_token` HttpOnly, Secure | ☐ |
| A-07 | Token NO en URL | Navegar post-login | URL no contiene `token=` | ☐ |
| A-08 | Logout revoca token | Logout, copiar token, usar en API | 401 Unauthorized | ☐ |
| A-09 | 2FA TOTP setup (si habilitado) | Setup → escanear QR → verificar código | Login requiere código TOTP | ☐ |

### 3. Dashboard Atleta
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| D-01 | Dashboard carga | `/dashboard.html` post-login | KPIs, PMC, widgets visibles | ☐ |
| D-02 | CTL/ATL/TSB visibles | Ver dashboard | Valores numéricos actuales | ☐ |
| D-03 | Gráfico PMC carga | Cambiar rango de fechas | Gráfico se actualiza | ☐ |
| D-04 | ACWR calculado | Ver ACWR widget | Valor entre 0.5 y 1.5 (rango saludable) | ☐ |
| D-05 | Daily Readiness Score | Ver DRS widget | Score 0-100 con factores | ☐ |

### 4. Sincronización Garmin
> **IMPORTANTE:** El founder ejecuta este flujo con su propia cuenta Garmin Connect.  
> Nunca solicitar credenciales a otros usuarios — ellos las ingresan ellos mismos.

| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| G-01 | Pantalla de conexión Garmin | `Settings → Garmin → Conectar` | Formulario o OAuth | ☐ |
| G-02 | Credenciales guardadas cifradas | Ingresar Garmin email/password | Sin error, token almacenado | ☐ |
| G-03 | Sync manual | Botón "Sincronizar ahora" | Actividades aparecen en dashboard | ☐ |
| G-04 | Actividades importadas | Ver lista de actividades | Al menos 1 actividad con GPS | ☐ |
| G-05 | Mapa GPS funciona | Click en actividad con GPS | Mapa Leaflet con ruta | ☐ |
| G-06 | CTL recalcula post-sync | Ver dashboard post-sync | CTL/ATL/TSB actualizados | ☐ |

### 5. Módulos LabX
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| M-01 | Blood Labs upload | Subir PDF o ingresar manualmente | Labs guardados, análisis visible | ☐ |
| M-02 | Nutrition tracking | `/nutrition.html` | Macros, hidratación, timing | ☐ |
| M-03 | Recovery page | `/recovery.html` | HRV, sleep, readiness | ☐ |
| M-04 | Mental performance | `/mental.html` | MFS score, protocolos | ☐ |
| M-05 | Analytics | `/analytics.html` | CTL projection, ACWR risk | ☐ |
| M-06 | Calendar | `/athlete-app.html#calendar` | Vista mensual, entrenamientos | ☐ |
| M-07 | Race countdown | Dashboard o `/analytics.html` | Días hasta próxima carrera | ☐ |

### 6. Coach Platform
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| C-01 | Login como coach | Usuario con rol=coach | `/coach.html` accesible | ☐ |
| C-02 | Dashboard squad | Ver lista de atletas | Cards con CTL/ATL/TSB | ☐ |
| C-03 | Perfil atleta 360° | Click en atleta | Modal con 6 módulos | ☐ |
| C-04 | Prescripción workout | Tab Prescripciones → crear | Workout aparece en atleta | ☐ |
| C-05 | Mensajes coach-atleta | Tab Mensajes → enviar | Atleta recibe notificación | ☐ |
| C-06 | Periodization Gantt | Tab Periodización | Gantt visual por fases | ☐ |

### 7. AI Coach
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| AI-01 | Pregunta básica | "¿Cómo mejoro mi FTP?" | Respuesta coherente, no vacía | ☐ |
| AI-02 | Workout generation | Pedir "generar workout zona 2 60min" | Workout estructurado | ☐ |
| AI-03 | Rate limiting IA | Plan Free → muchos requests | 403 Feature gating o 429 | ☐ |
| AI-04 | Sin ANTHROPIC_API_KEY | Si no configurado | 503 con mensaje claro | ☐ |

### 8. Stripe / Pagos
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| P-01 | Planes visibles | `/api/stripe/plans` | JSON con planes y precios | ☐ |
| P-02 | Checkout sandbox | Click en "Upgrade" | Redirect a Stripe Checkout | ☐ |
| P-03 | Pago sandbox 4242 | Tarjeta `4242 4242 4242 4242` | Pago exitoso, plan actualizado | ☐ |
| P-04 | Webhook recibido | Dashboard Stripe → Events | `checkout.session.completed` | ☐ |

### 9. Email
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| E-01 | Email de bienvenida | Registrar nuevo usuario | Email llega en < 2 min | ☐ |
| E-02 | Reset password | "Olvidé mi contraseña" | Email con link de reset | ☐ |
| E-03 | Link de reset funciona | Click en link del email | Formulario de nueva password | ☐ |

### 10. Logs y Monitoreo
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| L-01 | Logs estructurados | `docker compose logs -f api` | JSON lines con trace_id | ☐ |
| L-02 | Error en Sentry | Producir error 500 manual | Aparece en Sentry dashboard | ☐ |
| L-03 | Grafana dashboard | SSH tunnel + localhost:3000 | Métricas en tiempo real | ☐ |
| L-04 | Alerta Prometheus | Matar API 2+ min | Alert en Prometheus/Alertmanager | ☐ |

### 11. Performance
| # | Check | Procedimiento | Esperado | Estado |
|---|-------|---------------|---------|--------|
| PF-01 | Login latencia | DevTools Network tab | < 500ms | ☐ |
| PF-02 | Dashboard load | Medir Time to Interactive | < 3s en conexión 4G | ☐ |
| PF-03 | API p95 | Prometheus `histogram_quantile(0.95,...)` | < 500ms endpoints core | ☐ |

---

## Resultado Final FASE 6

**PASS mínimo para GO:** ≥ 90% de los checks en verde (no puede fallar ningún check crítico: I-01 a I-08, A-01 a A-08, G-01 a G-05, AI-01)

| Resultado | Criterio |
|-----------|----------|
| ✅ PASS | ≥ 90% checks + cero críticos fallando |
| ⚠ CONDICIONAL | 80-89% checks + críticos resueltos con workaround documentado |
| ❌ FAIL | < 80% checks o cualquier crítico sin workaround |

---

## Bugs Encontrados

| # | Fecha | Descripción | Severidad | Asignado | Estado |
|---|-------|-------------|-----------|----------|--------|
| | | | | | |

*Registrar aquí los bugs encontrados durante la validación.*
