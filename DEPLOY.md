# LabX — Guía de Deploy en Producción
**Stack:** FastAPI + PostgreSQL 16 + Redis 7 + Celery + Nginx + Docker Compose  
**Target:** Ubuntu 22.04 LTS — VPS mínimo 2 vCPU / 4 GB RAM / 40 GB SSD

---

## Checklist rápido (primera vez)

```
[ ] 1. Provisionar VPS (DigitalOcean / Hetzner)
[ ] 2. Apuntar DNS: beta.labx.app → IP del VPS
[ ] 3. Ejecutar: bash deploy/setup_server.sh  (como root)
[ ] 4. Clonar repo como usuario labx
[ ] 5. Generar secrets: bash deploy/generate_secrets.sh --write
[ ] 6. Completar campos <COMPLETAR> en .env
[ ] 7. Instalar nginx config: cp deploy/nginx-beta.conf /etc/nginx/sites-available/beta.labx.app
[ ] 8. Crear htpasswd: echo "fundador:$(openssl passwd -apr1 'password')" > /etc/nginx/.htpasswd-beta
[ ] 9. SSL: certbot --nginx -d beta.labx.app
[ ] 10. Deploy: bash deploy/deploy.sh
[ ] 11. Observabilidad: bash deploy/setup_observability.sh
[ ] 12. Smoke: bash deploy/smoke_test.sh
```

---

## Paso 1 — Provisionar VPS

**DigitalOcean Droplet recomendado para beta:**
- Plan: Basic $24/mes (2 vCPU, 4GB RAM, 80GB SSD)
- SO: Ubuntu 22.04 LTS x64
- Región: NYC o Frankfurt (latencia LATAM)
- Agregar SSH key antes de crear

**Hetzner (más económico):**
- CPX21: 3 vCPU, 4GB RAM, 80GB SSD — €7.49/mes
- SO: Ubuntu 22.04

Anota la IP pública: `__________________`

---

## Paso 2 — DNS

En Cloudflare (recomendado) o tu DNS provider:

```
Tipo: A
Nombre: beta
Valor: <IP del VPS>
TTL: 300
Proxy: Desactivado (nube naranja → nube gris) para Let's Encrypt
```

Verificar propagación: `dig beta.labx.app +short`

---

## Paso 3 — Setup del servidor

```bash
# Conectar al VPS como root
ssh root@<IP>

# Descargar y ejecutar setup
curl -fsSL https://raw.githubusercontent.com/TU_ORG/labx/main/deploy/setup_server.sh | bash
# O si ya clonaste:
bash deploy/setup_server.sh
```

Esto instala: Docker, Nginx, Certbot, UFW, Fail2ban, Logrotate.

---

## Paso 4 — Clonar repositorio

```bash
# Cambiar al usuario labx
su - labx

# Clonar
git clone https://github.com/TU_ORG/labx.git /opt/labx/app
cd /opt/labx/app
```

---

## Paso 5 — Generar Secrets

```bash
cd /opt/labx/app

# Genera JWT_SECRET, FERNET_KEY, POSTGRES_PASSWORD, METRICS_SECRET, etc.
bash deploy/generate_secrets.sh --write

# Completar los campos marcados como <COMPLETAR>
nano .env
```

**Campos obligatorios a completar manualmente:**
```
ADMIN_PASS=<contraseña segura del admin>
SENTRY_DSN=<obtener en sentry.io>
ANTHROPIC_API_KEY=<sk-ant-xxxx de console.anthropic.com>
RESEND_API_KEY=<re_xxxx de resend.com>
STRIPE_SECRET_KEY=<sk_live_xxxx o sk_test_xxxx>
STRIPE_WEBHOOK_SECRET=<whsec_xxxx>
```

Proteger el archivo:
```bash
chmod 600 .env
```

---

## Paso 6 — Nginx + SSL

```bash
# Como root:
# 1. Copiar config de nginx
cp /opt/labx/app/deploy/nginx-beta.conf /etc/nginx/sites-available/beta.labx.app
ln -sf /etc/nginx/sites-available/beta.labx.app /etc/nginx/sites-enabled/

# 2. Crear htpasswd para Private Beta
echo "fundador:$(openssl passwd -apr1 'TU_PASSWORD_BETA')" > /etc/nginx/.htpasswd-beta
# Agregar más usuarios si necesitas:
# echo "user2:$(openssl passwd -apr1 'password2')" >> /etc/nginx/.htpasswd-beta

# 3. Verificar nginx config
nginx -t

# 4. Obtener SSL (asegúrate que DNS ya propagó)
certbot --nginx -d beta.labx.app --non-interactive --agree-tos -m admin@labx.app

# 5. Reload nginx
systemctl reload nginx
```

---

## Paso 7 — Primer Deploy

```bash
# Como usuario labx:
cd /opt/labx/app

# Deploy completo: build, migrate, start, health check, smoke tests
bash deploy/deploy.sh
```

El script tarda ~5-10 minutos en el primer build. Los siguientes son más rápidos (cache Docker).

---

## Paso 8 — Observabilidad

```bash
# Levantar Prometheus + Grafana + exporters
bash deploy/setup_observability.sh

# Acceder a Grafana via SSH tunnel (desde tu máquina local):
ssh -L 3000:localhost:3000 labx@beta.labx.app
# Abrir: http://localhost:3000 (admin / ver GRAFANA_PASSWORD en .env)
```

---

## Paso 9 — Verificación

```bash
# Smoke tests
bash deploy/smoke_test.sh

# Health check
curl https://beta.labx.app/health

# Ver logs
docker compose -f docker-compose.prod.yml logs -f api

# Estado de servicios
docker compose -f docker-compose.prod.yml ps
```

---

## Operaciones del día a día

```bash
# Deploy de nueva versión
bash deploy/deploy.sh

# Update incremental (sin full rebuild)
bash deploy/update.sh

# Solo actualizar static files (0 downtime)
bash deploy/update.sh --static-only

# Rollback al tag anterior
bash deploy/rollback.sh

# Smoke tests
bash deploy/smoke_test.sh

# Ver logs en tiempo real
docker compose -f docker-compose.prod.yml logs -f api

# Backup manual
docker compose -f docker-compose.prod.yml exec backup python backup.py

# Conectar a DB
docker compose -f docker-compose.prod.yml exec db psql -U labx -d labx_prod

# Restart rápido API
docker compose -f docker-compose.prod.yml restart api
```

---

## Variables de entorno — Referencia

Ver [.env.production.example](.env.production.example) para la lista completa con documentación.

Las variables marcadas con `?` en docker-compose.prod.yml son **obligatorias** (la app falla en startup si están vacías).

---

## Costos estimados (beta privada)

| Servicio | Costo/mes |
|----------|-----------|
| VPS (Hetzner CPX21) | €7.49 |
| Dominio .app/año | ~$14 → ~$1.17/mes |
| Cloudflare | Gratis (Free plan) |
| Sentry | Gratis (5K events/mes) |
| Resend | Gratis (3K emails/mes) |
| Anthropic API | ~$5-20 (uso real) |
| Stripe | 0% (solo en transacciones) |
| **Total fijo/mes** | **~€10** |

---

## Troubleshooting

### API no arranca
```bash
docker compose -f docker-compose.prod.yml logs api
# Verificar variables: grep -E "JWT_SECRET|DATABASE_URL" .env
```

### Migraciones fallan
```bash
docker compose -f docker-compose.prod.yml run --rm api alembic current
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

### Nginx 502 Bad Gateway
```bash
curl http://127.0.0.1:8000/health  # Verificar API local
docker compose -f docker-compose.prod.yml ps  # Verificar contenedores
```

### Backup falla
```bash
docker compose -f docker-compose.prod.yml logs backup
# pg_dump debe estar instalado (ya incluido en Dockerfile)
```

### SSL expirado
```bash
certbot renew --dry-run  # Test
certbot renew            # Renovar
```
