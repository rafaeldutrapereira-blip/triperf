#!/usr/bin/env bash
# =============================================================================
# LabX — Update Script (incremental — solo código, sin rebuild completo)
# Útil para cambios de config, static files, hotfixes sin tocar infraestructura.
#
# Uso:
#   bash deploy/update.sh               # Pull + restart rápido (usa imagen existente)
#   bash deploy/update.sh --static-only # Solo sincronizar static files (0 downtime)
#   bash deploy/update.sh --env-reload  # Recargar variables de entorno
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
LOG_FILE="/var/log/labx/deploy.log"
STATIC_DIR="/var/www/labx"

log()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] UPDATE: $*" | tee -a "${LOG_FILE}"; }
ok()   { echo -e "\033[1;32m[  OK]\033[0m $*"; log "OK: $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; log "WARN: $*"; }
err()  { echo -e "\033[1;31m[ ERR]\033[0m $*" >&2; log "ERR: $*"; exit 1; }
step() { echo -e "\n\033[1;36m━━━ $* ━━━\033[0m"; log "STEP: $*"; }

MODE="${1:---full}"
mkdir -p "$(dirname "${LOG_FILE}")"
cd "${APP_DIR}"

log "=================================================="
log "UPDATE START — mode=${MODE}"
log "=================================================="

# ══════════════════════════════════════════════════════════════════════════════
# --static-only: Sincronizar HTML/JS/CSS sin tocar los contenedores
# ══════════════════════════════════════════════════════════════════════════════
if [[ "${MODE}" == "--static-only" ]]; then
    step "Static files sync only"
    git pull origin main --quiet
    sudo mkdir -p "${STATIC_DIR}"
    sudo cp -f "${APP_DIR}"/*.html    "${STATIC_DIR}/"  2>/dev/null || true
    sudo cp -f "${APP_DIR}"/*.js      "${STATIC_DIR}/"  2>/dev/null || true
    sudo cp -f "${APP_DIR}"/*.css     "${STATIC_DIR}/"  2>/dev/null || true
    sudo cp -f "${APP_DIR}"/manifest.json "${STATIC_DIR}/" 2>/dev/null || true
    sudo cp -f "${APP_DIR}"/sw.js     "${STATIC_DIR}/"  2>/dev/null || true
    sudo cp -f "${APP_DIR}"/favicon.* "${STATIC_DIR}/"  2>/dev/null || true
    sudo chown -R www-data:www-data "${STATIC_DIR}"
    ok "Static files updated (zero downtime)"
    sudo nginx -t && sudo systemctl reload nginx
    ok "Nginx reloaded"
    log "UPDATE COMPLETE (static-only)"
    echo -e "\n\033[1;32m✅ Static files updated\033[0m"
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# --env-reload: Recargar contenedores con nuevas variables (sin rebuild)
# ══════════════════════════════════════════════════════════════════════════════
if [[ "${MODE}" == "--env-reload" ]]; then
    step "Env reload — restarting containers with current image"
    [[ -f .env ]] || err ".env not found"
    docker compose -f "${COMPOSE_FILE}" up -d --no-build --remove-orphans
    ok "Containers restarted with updated env"

    max_attempts=20; attempt=0
    until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        [[ $attempt -ge $max_attempts ]] && err "Health check failed after env reload"
        sleep 5
    done
    ok "Health check passed"
    log "UPDATE COMPLETE (env-reload)"
    echo -e "\n\033[1;32m✅ Env reloaded\033[0m"
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# --full (default): Pull + migrations + rebuild rápido + restart
# ══════════════════════════════════════════════════════════════════════════════

step "1. Pulling latest code"
git fetch origin
git pull origin main
CURRENT_SHA=$(git rev-parse --short HEAD)
ok "Code at: ${CURRENT_SHA}"

step "2. Checking for new migrations"
PENDING=$(docker compose -f "${COMPOSE_FILE}" run --rm api \
    alembic current 2>/dev/null | grep "(head)" || echo "")
if [[ -z "${PENDING}" ]]; then
    step "2b. Applying migrations"
    docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head \
        && ok "Migrations applied" \
        || err "Migrations failed"
else
    ok "Database already at head"
fi

step "3. Building updated image (incremental — uses cache)"
DEPLOY_TAG="${CURRENT_SHA}" docker compose -f "${COMPOSE_FILE}" build api

step "4. Restarting API and worker"
DEPLOY_TAG="${CURRENT_SHA}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps api worker
ok "Containers restarted"

step "5. Health check"
max_attempts=20; attempt=0
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [[ $attempt -ge $max_attempts ]] && err "Health check failed — run rollback.sh if needed"
    sleep 5
done
ok "Health check passed"

step "6. Syncing static files"
sudo mkdir -p "${STATIC_DIR}"
sudo cp -f "${APP_DIR}"/*.html    "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/*.js      "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/*.css     "${STATIC_DIR}/"  2>/dev/null || true
sudo cp -f "${APP_DIR}"/manifest.json "${STATIC_DIR}/" 2>/dev/null || true
sudo cp -f "${APP_DIR}"/sw.js     "${STATIC_DIR}/"  2>/dev/null || true
sudo chown -R www-data:www-data "${STATIC_DIR}"
ok "Static files updated"

step "7. Nginx reload"
sudo nginx -t && sudo systemctl reload nginx
ok "Nginx reloaded"

log "=================================================="
log "UPDATE COMPLETE — SHA=${CURRENT_SHA}"
log "=================================================="
echo ""
echo -e "\033[1;32m✅ Update complete — running ${CURRENT_SHA}\033[0m"
