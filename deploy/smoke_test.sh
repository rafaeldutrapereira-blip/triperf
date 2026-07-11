#!/usr/bin/env bash
# =============================================================================
# LabX — Smoke Tests post-deploy
# Verificación rápida de que los endpoints críticos responden correctamente.
# =============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PASS=0
FAIL=0
SKIP=0

check() {
    local name="$1"
    local method="$2"
    local url="$3"
    local expected_status="$4"
    local body="${5:-}"

    if [[ -n "${body}" ]]; then
        status=$(curl -sf -o /dev/null -w "%{http_code}" \
            -X "${method}" "${BASE_URL}${url}" \
            -H "Content-Type: application/json" \
            -d "${body}" \
            --max-time 10 2>/dev/null || echo "000")
    else
        status=$(curl -sf -o /dev/null -w "%{http_code}" \
            -X "${method}" "${BASE_URL}${url}" \
            --max-time 10 2>/dev/null || echo "000")
    fi

    if [[ "${status}" == "${expected_status}" ]] || \
       (echo "${expected_status}" | grep -q "|" && echo "${status}" | grep -qE "^(${expected_status//|/|})$"); then
        echo -e "  \033[1;32m✅ PASS\033[0m ${name} → ${status}"
        PASS=$((PASS + 1))
    else
        echo -e "  \033[1;31m❌ FAIL\033[0m ${name} → got ${status}, expected ${expected_status}"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LabX Smoke Tests — $(date)"
echo "  Target: ${BASE_URL}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Infrastructure ────────────────────────────────────────────────────────────
echo ""
echo "[ Infrastructure ]"
check "Health endpoint"           GET  /health              200
check "Metrics endpoint"          GET  /api/metrics         200
check "OpenAPI schema"            GET  /api/openapi.json    "200|404"

# ── Auth ─────────────────────────────────────────────────────────────────────
echo ""
echo "[ Auth ]"
check "Login empty body → 422"    POST /api/auth/login      422 '{}'
check "Login bad creds → 401"     POST /api/auth/login      "401|400" '{"email":"none@x.com","password":"bad"}'
check "Register empty → 422"      POST /api/auth/register   422 '{}'

# ── Protected endpoints → 401 sin token ──────────────────────────────────────
echo ""
echo "[ Protected Endpoints → 401 ]"
check "Dashboard → 401"           GET  /api/athlete/dashboard  401
check "Profile → 401"             GET  /api/athlete/profile     401
check "Labs → 401"                GET  /api/labs/exams          401
check "Races → 401"               GET  /api/races               401
check "AI coach → 401"            POST /api/ai/coach-suggest    "401|422"

# ── Stripe ───────────────────────────────────────────────────────────────────
echo ""
echo "[ Payments ]"
check "Stripe plans → 200"        GET  /api/stripe/plans        "200|404"
check "Stripe webhook → 400"      POST /api/stripe/webhook      "400|422"

# ── Static pages (if served by API) ──────────────────────────────────────────
echo ""
echo "[ Static availability via nginx ]"
NGINX_URL="${APP_URL:-https://beta.labx.app}"
if curl -sf --max-time 5 "${NGINX_URL}/health" >/dev/null 2>&1; then
    nginx_status=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "${NGINX_URL}/login.html" 2>/dev/null || echo "000")
    if [[ "${nginx_status}" =~ ^(200|401)$ ]]; then
        echo -e "  \033[1;32m✅ PASS\033[0m login.html reachable via nginx → ${nginx_status}"
        PASS=$((PASS + 1))
    else
        echo -e "  \033[1;31m❌ FAIL\033[0m login.html not reachable → ${nginx_status}"
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "  \033[1;33m⚠  SKIP\033[0m nginx not reachable from this context (ok in local CI)"
    SKIP=$((SKIP + 1))
fi

# ── Summary ──────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL + SKIP))
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: ${PASS} PASS  |  ${FAIL} FAIL  |  ${SKIP} SKIP  (${TOTAL} total)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[[ $FAIL -eq 0 ]] || exit 1
exit 0
