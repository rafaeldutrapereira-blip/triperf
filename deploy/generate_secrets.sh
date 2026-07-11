#!/usr/bin/env bash
# =============================================================================
# LabX — Generate Production Secrets
# Genera todos los secretos criptográficos necesarios para .env de producción.
# Ejecutar UNA SOLA VEZ en el servidor de producción.
#
# Uso:
#   bash deploy/generate_secrets.sh                   → imprime a stdout
#   bash deploy/generate_secrets.sh --write           → escribe directamente en .env
#   bash deploy/generate_secrets.sh --write --force   → sobreescribe .env existente
# =============================================================================
set -euo pipefail

WRITE_ENV=false
FORCE=false
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"

for arg in "$@"; do
    case $arg in
        --write) WRITE_ENV=true ;;
        --force) FORCE=true ;;
    esac
done

# ── Verificar Python 3 disponible ────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 requerido para generar secretos" >&2
    exit 1
fi

# ── Generar secretos ─────────────────────────────────────────────────────────
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || \
             python3 -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
METRICS_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
GRAFANA_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
FLOWER_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

# Intentar generar VAPID keys si web-push está disponible
VAPID_PUBLIC=""
VAPID_PRIVATE=""
if command -v npx &>/dev/null; then
    VAPID_OUTPUT=$(npx --yes web-push generate-vapid-keys 2>/dev/null || echo "")
    if [[ -n "$VAPID_OUTPUT" ]]; then
        VAPID_PUBLIC=$(echo "$VAPID_OUTPUT" | grep "Public Key:" | awk '{print $3}')
        VAPID_PRIVATE=$(echo "$VAPID_OUTPUT" | grep "Private Key:" | awk '{print $3}')
    fi
fi

if [[ -z "$VAPID_PUBLIC" ]]; then
    VAPID_PUBLIC="<GENERAR: npx web-push generate-vapid-keys>"
    VAPID_PRIVATE="<GENERAR: npx web-push generate-vapid-keys>"
fi

# ── Output ───────────────────────────────────────────────────────────────────
SECRETS_BLOCK="
# ══════════════════════════════════════════════════════
# LABX PRODUCTION SECRETS — generados $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# NUNCA compartir estos valores. NUNCA commitear este archivo.
# ══════════════════════════════════════════════════════

# ── Seguridad JWT ─────────────────────────────────────
JWT_SECRET=${JWT_SECRET}
JWT_AUDIENCE=labx-app
TOKEN_HOURS=8

# ── Cifrado Fernet (credenciales Garmin) ──────────────
FERNET_KEY=${FERNET_KEY}
# FERNET_KEY_OLD=   # ← completar si estás rotando la clave

# ── PostgreSQL ────────────────────────────────────────
POSTGRES_USER=labx
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=labx_prod
DATABASE_URL=postgresql://labx:${POSTGRES_PASSWORD}@pgbouncer:6432/labx_prod

# ── App ───────────────────────────────────────────────
APP_ENV=production
APP_URL=https://beta.labx.app
CORS_ORIGINS=https://beta.labx.app
ENABLE_DOCS=0

# ── Observabilidad ─────────────────────────────────────
METRICS_SECRET=${METRICS_SECRET}
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
FLOWER_USER=admin
FLOWER_PASSWORD=${FLOWER_PASSWORD}
SENTRY_DSN=<COMPLETAR: https://<id>@o<org>.ingest.sentry.io/<project>>

# ── Admin seed ────────────────────────────────────────
ADMIN_EMAIL=admin@labx.app
ADMIN_PASS=<COMPLETAR: contraseña segura para el admin>
ADMIN_NOMBRE=Admin

# ── Push Notifications (VAPID) ────────────────────────
VAPID_PUBLIC_KEY=${VAPID_PUBLIC}
VAPID_PRIVATE_KEY=${VAPID_PRIVATE}
VAPID_SUBJECT=mailto:admin@labx.app

# ── Redis ─────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# ── Storage ───────────────────────────────────────────
STORAGE_BACKEND=local
# STORAGE_BACKEND=s3
# AWS_ACCESS_KEY_ID=<COMPLETAR>
# AWS_SECRET_ACCESS_KEY=<COMPLETAR>
# AWS_S3_BUCKET=labx-prod-storage
# AWS_REGION=us-east-1

# ── Backups ───────────────────────────────────────────
BACKUP_KEEP_DAYS=30

# ── Email (Resend) ────────────────────────────────────
RESEND_API_KEY=<COMPLETAR: re_xxxx — obtener en resend.com>
EMAIL_FROM=noreply@labx.app

# ── Stripe ────────────────────────────────────────────
STRIPE_SECRET_KEY=<COMPLETAR: sk_live_xxxx o sk_test_xxxx>
STRIPE_WEBHOOK_SECRET=<COMPLETAR: whsec_xxxx>
STRIPE_PRICE_PRO=<COMPLETAR: price_xxxx>
STRIPE_PRICE_COACH=<COMPLETAR: price_xxxx>
STRIPE_PRICE_ELITE=<COMPLETAR: price_xxxx>
STRIPE_TRIAL_DAYS=14

# ── Garmin OAuth ──────────────────────────────────────
GARMIN_CLIENT_ID=<COMPLETAR>
GARMIN_CLIENT_SECRET=<COMPLETAR>
GARMIN_REDIRECT_URI=https://beta.labx.app/api/garmin/callback

# ── Strava OAuth ──────────────────────────────────────
STRAVA_CLIENT_ID=<COMPLETAR>
STRAVA_CLIENT_SECRET=<COMPLETAR>
STRAVA_REDIRECT_URI=https://beta.labx.app/api/strava/callback

# ── AI Coach (Anthropic) ──────────────────────────────
ANTHROPIC_API_KEY=<COMPLETAR: sk-ant-xxxx — obtener en console.anthropic.com>
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# ── Deploy tag ────────────────────────────────────────
DEPLOY_TAG=latest
"

# ── Write or print ───────────────────────────────────────────────────────────
if [[ "${WRITE_ENV}" == "true" ]]; then
    if [[ -f "${ENV_FILE}" ]] && [[ "${FORCE}" != "true" ]]; then
        echo "ERROR: ${ENV_FILE} ya existe. Usar --force para sobreescribir." >&2
        exit 1
    fi
    echo "${SECRETS_BLOCK}" > "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✅ Secretos escritos en: ${ENV_FILE}"
    echo "  Permisos: 600 (solo tu usuario puede leerlo)"
    echo ""
    echo "  SIGUIENTE PASO:"
    echo "  Editar ${ENV_FILE} y completar los campos <COMPLETAR>"
    echo "  Especialmente: ADMIN_PASS, SENTRY_DSN, ANTHROPIC_API_KEY"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  LabX — Secretos generados"
    echo "  Copiar al .env del servidor:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "${SECRETS_BLOCK}"
    echo ""
    echo "  Para escribir directamente: bash deploy/generate_secrets.sh --write"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi
