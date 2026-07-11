#!/usr/bin/env bash
# =============================================================================
# LabX — Server Setup Script (Ubuntu 22.04 LTS)
# Ejecutar como root en el VPS una sola vez.
#
# Uso:
#   wget -O setup_server.sh https://raw.githubusercontent.com/TU_REPO/main/deploy/setup_server.sh
#   chmod +x setup_server.sh
#   sudo bash setup_server.sh
# =============================================================================
set -euo pipefail

LABX_USER="labx"
LABX_HOME="/opt/labx"
DOMAIN="${DOMAIN:-beta.labx.app}"
STATIC_DIR="/var/www/labx"
LOG_DIR="/var/log/labx"

log() { echo -e "\033[1;34m[SETUP]\033[0m $*"; }
ok()  { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
err() { echo -e "\033[1;31m[ERR ]\033[0m $*" >&2; exit 1; }

log "========================================================"
log "   LabX Private Beta — Server Setup"
log "   Domain: ${DOMAIN}"
log "   Host:   $(hostname)"
log "========================================================"

# ── 1. System Update ─────────────────────────────────────────────────────────
log "1/12  Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip \
    nginx certbot python3-certbot-nginx \
    ufw fail2ban \
    htop net-tools \
    postgresql-client-16 \
    jq
ok "System packages installed"

# ── 2. Docker ────────────────────────────────────────────────────────────────
log "2/12  Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    ok "Docker installed"
else
    ok "Docker already installed ($(docker --version))"
fi

# Docker Compose plugin
if ! docker compose version &>/dev/null; then
    apt-get install -y docker-compose-plugin
fi

# ── 3. Crear usuario labx ────────────────────────────────────────────────────
log "3/12  Creating labx system user..."
if ! id "${LABX_USER}" &>/dev/null; then
    useradd -m -s /bin/bash -d "${LABX_HOME}" "${LABX_USER}"
    usermod -aG docker "${LABX_USER}"
    ok "User ${LABX_USER} created"
else
    ok "User ${LABX_USER} already exists"
fi

mkdir -p "${LABX_HOME}"
chown -R "${LABX_USER}:${LABX_USER}" "${LABX_HOME}"

# ── 4. Firewall (UFW) ────────────────────────────────────────────────────────
log "4/12  Configuring firewall (UFW)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
# Bloquear puertos internos de Docker desde el exterior
ufw deny 8000/tcp
ufw deny 5432/tcp
ufw deny 6432/tcp
ufw deny 6379/tcp
ufw --force enable
ok "UFW configured"

# ── 5. Fail2ban ──────────────────────────────────────────────────────────────
log "5/12  Configuring fail2ban..."
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
action   = iptables-multiport[name=nginx-limit-req,port="http,https"]
logpath  = /var/log/nginx/*error.log
findtime = 600
maxretry = 10
bantime  = 7200
EOF
systemctl enable fail2ban
systemctl restart fail2ban
ok "Fail2ban configured"

# ── 6. Directorios ───────────────────────────────────────────────────────────
log "6/12  Creating directories..."
mkdir -p "${STATIC_DIR}"
mkdir -p "${LOG_DIR}"
mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled
chown -R "${LABX_USER}:www-data" "${STATIC_DIR}"
chmod -R 755 "${STATIC_DIR}"
ok "Directories created"

# ── 7. Nginx base config ─────────────────────────────────────────────────────
log "7/12  Configuring nginx..."
# Eliminar default site
rm -f /etc/nginx/sites-enabled/default

# nginx.conf base seguro
cat > /etc/nginx/nginx.conf <<'EOF'
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 1024;
    multi_accept on;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logs
    log_format combined '$remote_addr - $remote_user [$time_local] '
                        '"$request" $status $body_bytes_sent '
                        '"$http_referer" "$http_user_agent"';
    access_log /var/log/nginx/access.log combined;
    error_log  /var/log/nginx/error.log warn;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss;

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOF

nginx -t
systemctl enable nginx
systemctl start nginx
ok "Nginx configured"

# ── 8. Clonar repositorio ────────────────────────────────────────────────────
log "8/12  NOTE: Clone your repo manually as the labx user:"
log "       su - labx"
log "       git clone https://github.com/YOUR_ORG/labx.git ${LABX_HOME}/app"
log "       cp ${LABX_HOME}/app/.env.production.example ${LABX_HOME}/app/.env"
log "       # Edit .env with your secrets"

# ── 9. htpasswd para Private Beta ────────────────────────────────────────────
log "9/12  Creating Basic Auth placeholder..."
log "  Run: echo 'fundador:\$(openssl passwd -apr1 YOUR_PASSWORD)' > /etc/nginx/.htpasswd-beta"
log "  Add more users as needed"

# ── 10. Certbot placeholder ──────────────────────────────────────────────────
log "10/12 SSL certificate (Certbot):"
log "  Once DNS is pointing to this server, run:"
log "  certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@labx.app"

# ── 11. Logrotate ────────────────────────────────────────────────────────────
log "11/12 Configuring logrotate..."
cat > /etc/logrotate.d/labx <<'EOF'
/var/log/labx/*.log
/var/log/nginx/labx_*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        nginx -s reopen 2>/dev/null || true
    endscript
}
EOF
ok "Logrotate configured"

# ── 12. Cron para Certbot renewal ────────────────────────────────────────────
log "12/12 Configuring Certbot auto-renewal..."
cat > /etc/cron.d/certbot-labx <<'EOF'
0 3 * * * root certbot renew --quiet --deploy-hook "systemctl reload nginx"
EOF
ok "Certbot auto-renewal configured"

log "========================================================"
log "  SERVER SETUP COMPLETE"
log ""
log "  NEXT STEPS:"
log "  1. As labx user: clone repo to ${LABX_HOME}/app"
log "  2. Create .env from .env.production.example"
log "  3. Copy nginx config: cp deploy/nginx-beta.conf /etc/nginx/sites-available/beta.labx.app"
log "  4. Enable nginx site: ln -s /etc/nginx/sites-available/beta.labx.app /etc/nginx/sites-enabled/"
log "  5. Create htpasswd: echo 'fundador:\$(openssl passwd -apr1 PASS)' > /etc/nginx/.htpasswd-beta"
log "  6. Point DNS: beta.labx.app → $(curl -s ifconfig.me)"
log "  7. Get SSL: certbot --nginx -d beta.labx.app"
log "  8. Run: cd ${LABX_HOME}/app && bash deploy/deploy.sh"
log "========================================================"
