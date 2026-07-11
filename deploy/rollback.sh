#!/usr/bin/env bash
# =============================================================================
# LabX — Rollback Script
# Revierte al tag de imagen anterior en caso de deploy fallido.
#
# Uso:
#   bash deploy/rollback.sh                   # Usa ROLLBACK_TAG del .env o pide el anterior
#   bash deploy/rollback.sh v1.2.3            # Rollback a tag específico
#   SKIP_TESTS=1 bash deploy/rollback.sh      # Sin smoke tests
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
LOG_FILE="/var/log/labx/deploy.log"

log()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] ROLLBACK: $*" | tee -a "${LOG_FILE}"; }
ok()   { echo -e "\033[1;32m[  OK]\033[0m $*"; log "OK: $*"; }
err()  { echo -e "\033[1;31m[ ERR]\033[0m $*" >&2; log "ERR: $*"; exit 1; }
step() { echo -e "\n\033[1;33m━━━ $* ━━━\033[0m"; log "STEP: $*"; }

mkdir -p "$(dirname "${LOG_FILE}")"
cd "${APP_DIR}"

# ── Detectar tag de rollback ──────────────────────────────────────────────────
ROLLBACK_TAG="${1:-}"

if [[ -z "${ROLLBACK_TAG}" ]]; then
    # Intentar obtener el tag anterior de las imágenes disponibles
    CURRENT_TAG=$(docker compose -f "${COMPOSE_FILE}" images api --format "{{.Tag}}" 2>/dev/null | head -1 || echo "latest")
    PREV_TAG=$(docker images labx-api --format "{{.Tag}}" 2>/dev/null | grep -v "${CURRENT_TAG}" | grep -v "^$" | head -1 || echo "")

    if [[ -z "${PREV_TAG}" ]]; then
        err "No previous image tag found. Specify a tag: bash rollback.sh <tag>"
    fi
    ROLLBACK_TAG="${PREV_TAG}"
fi

log "============================================"
log "ROLLBACK START — target tag: ${ROLLBACK_TAG}"
log "============================================"

echo -e "\n\033[1;31m⚠  ROLLBACK INITIATED\033[0m"
echo "Target tag: ${ROLLBACK_TAG}"
echo ""

# ── Verificar que la imagen existe ───────────────────────────────────────────
step "1. Verifying rollback image exists"
if ! docker image inspect "labx-api:${ROLLBACK_TAG}" >/dev/null 2>&1; then
    err "Image labx-api:${ROLLBACK_TAG} not found locally. Pull it first or specify a valid tag."
fi
ok "Image labx-api:${ROLLBACK_TAG} found"

# ── Snapshot del estado actual ────────────────────────────────────────────────
step "2. Saving current state snapshot"
CURRENT_TAG=$(docker compose -f "${COMPOSE_FILE}" ps api --format "{{.Image}}" 2>/dev/null | head -1 | sed 's/.*://' || echo "unknown")
log "Current running tag: ${CURRENT_TAG}"
echo "  Current: ${CURRENT_TAG} → Rolling back to: ${ROLLBACK_TAG}"

# ── Guardar tag previo para eventual re-rollback ─────────────────────────────
echo "${CURRENT_TAG}" > "${APP_DIR}/.last_deploy_tag"
ok "Current tag saved to .last_deploy_tag"

# ── Aplicar rollback ──────────────────────────────────────────────────────────
step "3. Applying rollback (DEPLOY_TAG=${ROLLBACK_TAG})"
DEPLOY_TAG="${ROLLBACK_TAG}" docker compose -f "${COMPOSE_FILE}" up -d --no-build api worker
ok "Containers updated to ${ROLLBACK_TAG}"

# ── Health check ─────────────────────────────────────────────────────────────
step "4. Health check post-rollback"
max_attempts=20
attempt=0
until curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [[ $attempt -ge $max_attempts ]] && err "Health check failed after rollback — MANUAL INTERVENTION REQUIRED"
    log "Health attempt ${attempt}/${max_attempts} — waiting 5s..."
    sleep 5
done
ok "Health check passed (attempt ${attempt})"

# ── Smoke tests ───────────────────────────────────────────────────────────────
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    step "5. Running smoke tests"
    bash "${SCRIPT_DIR}/smoke_test.sh" && ok "Smoke tests passed" || {
        log "WARNING: Smoke tests failed after rollback — system may be partially degraded"
        echo -e "\n\033[1;33m⚠  Smoke tests failed post-rollback. Check logs: /var/log/labx/deploy.log\033[0m"
    }
fi

# ── Nginx reload ─────────────────────────────────────────────────────────────
step "6. Reloading nginx"
sudo nginx -t && sudo systemctl reload nginx
ok "Nginx reloaded"

log "============================================"
log "ROLLBACK COMPLETE — now running: ${ROLLBACK_TAG}"
log "  To re-deploy forward: bash deploy/deploy.sh"
log "============================================"

echo ""
echo -e "\033[1;32m✅ Rollback complete — running ${ROLLBACK_TAG}\033[0m"
echo ""
echo "  To re-deploy forward:  bash deploy/deploy.sh"
echo "  To check status:       docker compose -f docker-compose.prod.yml ps"
