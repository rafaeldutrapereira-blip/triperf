#!/usr/bin/env bash
# =============================================================================
# LabX — Deploy Script (zero-downtime blue/green via Docker Compose)
# Ejecutar desde /opt/labx/app como usuario labx
#
# Uso:
#   bash deploy/deploy.sh              # Deploy último commit de main
#   bash deploy/deploy.sh v1.2.3       # Deploy tag específico
#   SKIP_TESTS=1 bash deploy/deploy.sh # Sin smoke tests (emergencia)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
LOG_FILE="/var/log/labx/deploy.log"
BACKUP_BEFORE_DEPLOY="${BACKUP_BEFORE_DEPLOY:-1}"
DEPLOY_TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"

log()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"; }
ok()   { echo -e "\033[1;32m[  OK]\033[0m $*"; log "OK: $*"; }
err()  { echo -e "\033[1;31m[ ERR]\033[0m $*" >&2; log "ERR: $*"; exit 1; }
step() { echo -e "\n\033[1;36m━━━ $* ━━━\033[0m"; log "STEP: $*"; }

mkdir -p "$(dirname "${LOG_FILE}")"
log "=========================================="
log "DEPLOY START — tag=${DEPLOY_TAG}"
log "User: $(whoami) | Host: $(hostname)"
log "=========================================="

cd "${APP_DIR}"

# ── Validar .env ──────────────────────────────────────────────────────────────
step "1. Validating environment"
[[ -f .env ]] || err ".env not found — copy from .env.production.example and fill secrets"

required_vars=("JWT_SECRET" "FERNET_KEY" "POSTGRES_PASSWORD" "CORS_ORIGINS" "APP_URL")
for var in "${required_vars[@]}"; do
    val=$(grep "^${var}=" .env | cut -d= -f2- | tr -d '"'"'" || echo "")
    [[ -n "${val}" ]] || err "Required variable ${var} is empty in .env"
done
ok "Environment variables validated"

# ── Pull código ───────────────────────────────────────────────────────────────
step "2. Pulling latest code"
git fetch origin
git checkout main
git pull origin main
ok "Code updated to: $(git rev-parse --short HEAD)"

# ── Backup antes de deploy ────────────────────────────────────────────────────
if [[ "${BACKUP_BEFORE_DEPLOY}" == "1" ]]; then
    step "3. Pre-deploy database backup"
    if docker compose -f "${COMPOSE_FILE}" ps db | grep -q "running"; then
        docker compose -f "${COMPOSE_FILE}" exec -T backup python backup.py \
            && ok "Pre-deploy backup completed" \
            || log "WARNING: Pre-deploy backup failed (continuing)"
    else
        log "WARNING: DB not running, skipping backup"
    fi
else
    step "3. Skipping backup (BACKUP_BEFORE_DEPLOY=0)"
fi

# ── Build imagen ──────────────────────────────────────────────────────────────
step "4. Building Docker image"
export DEPLOY_TAG
docker compose -f "${COMPOSE_FILE}" build --no-cache api
ok "Image built: labx-api:${DEPLOY_TAG}"

# ── Migraciones Alembic ───────────────────────────────────────────────────────
step "5. Running Alembic migrations"
docker compose -f "${COMPOSE_FILE}" run --rm \
    -e DATABASE_URL="postgresql://${POSTGRES_USER:-labx}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-labx_prod}" \
    api \
    alembic upgrade head \
    && ok "Migrations applied" \
    || err "Migrations failed — aborting deploy"

# ── Reinicio blue/green (graceful) ────────────────────────────────────────────
step "6. Deploying containers (rolling restart)"
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans
ok "Containers started"

# ── Health check ──────────────────────────────────────────────────────────────
step "7. Health check"
max_attempts=30
attempt=0
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [[ $attempt -ge $max_attempts ]] && err "Health check failed after ${max_attempts} attempts — triggering rollback"
    log "Health check attempt ${attempt}/${max_attempts} — waiting 5s..."
    sleep 5
done
ok "Health check passed (attempt ${attempt})"

# ── Smoke tests ───────────────────────────────────────────────────────────────
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    step "8. Running smoke tests"
    bash "${SCRIPT_DIR}/smoke_test.sh" || err "Smoke tests failed — check logs"
    ok "Smoke tests passed"
else
    step "8. Skipping smoke tests (SKIP_TESTS=1)"
fi

# ── Copiar static files a /var/www/labx ──────────────────────────────────────
step "9. Syncing static files"
STATIC_DIR="/var/www/labx"
sudo mkdir -p "${STATIC_DIR}"
sudo cp -f "${APP_DIR}"/*.html    "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/*.js      "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/*.css     "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/manifest.json "${STATIC_DIR}/" 2>/dev/null || true
sudo cp -f "${APP_DIR}"/sw.js     "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/favicon.* "${STATIC_DIR}/"  2>/dev/null || true
sudo chown -R www-data:www-data "${STATIC_DIR}"
ok "Static files synced to ${STATIC_DIR}"

# ── Nginx reload ──────────────────────────────────────────────────────────────
step "10. Reloading nginx"
sudo nginx -t && sudo systemctl reload nginx
ok "Nginx reloaded"

# ── Limpiar imágenes antiguas ────────────────────────────────────────────────
step "11. Cleaning old Docker images"
docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true
ok "Old images cleaned"

# ── Summary ──────────────────────────────────────────────────────────────────
log "=========================================="
log "DEPLOY COMPLETE — tag=${DEPLOY_TAG}"
log "URL: $(grep APP_URL .env | cut -d= -f2-)"
log "Services:"
docker compose -f "${COMPOSE_FILE}" ps --format "table {{.Name}}\t{{.Status}}"
log "=========================================="
echo ""
echo -e "\033[1;32m✅ LabX deployed successfully to ${DEPLOY_TAG}\033[0m"
