#!/usr/bin/env bash
# =============================================================================
# LabX — Observability Stack Setup
# Levanta Prometheus + Grafana + exporters en el servidor de producción.
#
# Prerequisito: deploy/setup_server.sh ya ejecutado.
# Prerequisito: docker-compose.prod.yml está corriendo (red labx_prod_network existe).
#
# Uso:
#   bash deploy/setup_observability.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OBS_COMPOSE="${APP_DIR}/deploy/observability/docker-compose.observability.yml"
PROD_COMPOSE="${APP_DIR}/docker-compose.prod.yml"
LOG_FILE="/var/log/labx/observability.log"

log()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] OBS: $*" | tee -a "${LOG_FILE}"; }
ok()   { echo -e "\033[1;32m[  OK]\033[0m $*"; log "OK: $*"; }
err()  { echo -e "\033[1;31m[ ERR]\033[0m $*" >&2; log "ERR: $*"; exit 1; }
step() { echo -e "\n\033[1;36m━━━ $* ━━━\033[0m"; log "STEP: $*"; }

mkdir -p "$(dirname "${LOG_FILE}")"
cd "${APP_DIR}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LabX Observability Stack Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Verificar red existe ──────────────────────────────────────────────────────
step "1. Checking labx_prod_network"
if ! docker network ls | grep -q "labx_prod_network"; then
    log "Red labx_prod_network no existe — levantando stack principal primero"
    docker compose -f "${PROD_COMPOSE}" up -d --no-build 2>/dev/null || true
fi
ok "Red labx_prod_network disponible"

# ── Verificar GRAFANA_PASSWORD está seteado ───────────────────────────────────
step "2. Checking Grafana password"
if [[ -f .env ]]; then
    GRAFANA_PASS=$(grep "^GRAFANA_PASSWORD=" .env | cut -d= -f2- | tr -d '"' || echo "")
fi
if [[ -z "${GRAFANA_PASS:-}" ]]; then
    GRAFANA_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    echo "GRAFANA_PASSWORD=${GRAFANA_PASS}" >> .env
    log "GRAFANA_PASSWORD generado y añadido a .env: ${GRAFANA_PASS}"
    echo -e "\n\033[1;33m⚠  GRAFANA_PASSWORD generado: ${GRAFANA_PASS}\033[0m"
    echo "    Guardado en .env. Úsalo para acceder a Grafana."
fi
ok "Grafana password configurado"

# ── Habilitar nginx stub_status para nginx-exporter ──────────────────────────
step "3. Configuring nginx stub_status"
STUB_CONF="/etc/nginx/conf.d/stub_status.conf"
if [[ ! -f "${STUB_CONF}" ]]; then
    cat > "${STUB_CONF}" <<'EOF'
server {
    listen 8080;
    server_name localhost;
    access_log off;
    location /stub_status {
        stub_status;
        allow 127.0.0.1;
        deny all;
    }
}
EOF
    sudo nginx -t && sudo systemctl reload nginx
    ok "nginx stub_status habilitado en :8080"
else
    ok "nginx stub_status ya configurado"
fi

# ── Levantar stack de observabilidad ─────────────────────────────────────────
step "4. Starting observability stack"
docker compose \
    -f "${PROD_COMPOSE}" \
    -f "${OBS_COMPOSE}" \
    up -d prometheus grafana postgres-exporter redis-exporter node-exporter flower
ok "Observability stack started"

# ── Verificar servicios ───────────────────────────────────────────────────────
step "5. Verifying services"
sleep 10

check_service() {
    local name="$1"
    local url="$2"
    local status
    status=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 "${url}" 2>/dev/null || echo "000")
    if [[ "${status}" =~ ^(200|302|301)$ ]]; then
        echo -e "  \033[1;32m✅ ${name}\033[0m → ${status}"
    else
        echo -e "  \033[1;33m⚠  ${name}\033[0m → ${status} (puede tardar unos segundos más)"
    fi
}

check_service "Prometheus"         "http://127.0.0.1:9090/-/healthy"
check_service "Grafana"            "http://127.0.0.1:3000/api/health"
check_service "Postgres Exporter"  "http://127.0.0.1:9187/metrics"
check_service "Redis Exporter"     "http://127.0.0.1:9121/metrics"
check_service "Node Exporter"      "http://127.0.0.1:9100/metrics"
check_service "Flower"             "http://127.0.0.1:5555"

log "=================================================="
log "OBSERVABILITY SETUP COMPLETE"
log "=================================================="

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ACCESO (via SSH tunnel desde tu máquina local):"
echo ""
echo "  ssh -L 3000:localhost:3000 \\"
echo "       -L 9090:localhost:9090 \\"
echo "       -L 5555:localhost:5555 \\"
echo "       labx@beta.labx.app"
echo ""
echo "  Grafana:    http://localhost:3000  (admin / ${GRAFANA_PASS:-<ver .env>})"
echo "  Prometheus: http://localhost:9090"
echo "  Flower:     http://localhost:5555"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
