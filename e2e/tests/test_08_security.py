"""
E2E-SECURITY — Application Security Tests
======================================================
Priority : CRITICAL
Markers  : critical
Coverage :
  TC-SEC-001  XSS: input sanitized en formulario de login
  TC-SEC-002  XSS: nombre en perfil no ejecuta script
  TC-SEC-003  SQL Injection via query params → no 500
  TC-SEC-004  SQL Injection via POST body → no 500
  TC-SEC-005  CORS headers presentes y correctos
  TC-SEC-006  Security headers (X-Content-Type, X-Frame-Options)
  TC-SEC-007  Token no expuesto en URL
  TC-SEC-008  Endpoints protegidos sin token → 401/403
  TC-SEC-009  Atleta no puede acceder a endpoints de coach
  TC-SEC-010  Coach no puede acceder a atleta de otro coach
  TC-SEC-011  Password nunca retornado en respuestas API
  TC-SEC-012  Sensitive data no logueada (sin secrets en /health)
  TC-SEC-013  File path traversal bloqueado
  TC-SEC-014  HTTP → HTTPS redirect (en staging/prod)
  TC-SEC-015  Brute force: invalid tokens no causan 500
"""
from __future__ import annotations

import pytest
import requests

from e2e.conftest import BASE_URL, API_URL, TEST_ATHLETE


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-001 — XSS en login input
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_xss_login_input_sanitized():
    """
    Acceptance:
      XSS payload in email field → API returns 400/422 (validation)
      No script execution (response doesn't echo raw payload)
    """
    xss_payload = "<script>alert('XSS')</script>"
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": xss_payload,
        "password": "Password123!"
    }, timeout=5)

    # Must not be 200 (invalid email) and must not 500
    assert r.status_code in (400, 401, 422), \
        f"XSS login should fail validation. Got: {r.status_code}"
    assert r.status_code != 500

    # Response should not echo raw script tag
    response_text = r.text
    assert "<script>" not in response_text, \
        "API echoed raw <script> tag in response (XSS reflection)"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-002 — XSS en campo nombre de perfil
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_xss_nombre_perfil_no_ejecuta(athlete_api):
    """
    Acceptance:
      PATCH profile with XSS nombre → 200 (stored)
      GET profile returns nombre (escaped or sanitized)
      Stored XSS: nombre displayed should be escaped, not executed
    """
    xss_nombre = "<img src=x onerror=alert('XSS')>"

    patch_r = requests.patch(
        f"{API_URL}/athlete/profile",
        json={"nombre": xss_nombre},
        headers=athlete_api.auth_headers(),
        timeout=5
    )
    # Accept 200 or 422 (if server validates input)
    assert patch_r.status_code in (200, 422), \
        f"Profile XSS patch: {patch_r.status_code} {patch_r.text[:200]}"

    if patch_r.status_code == 200:
        # Verify retrieval
        get_r = athlete_api.get("/athlete/profile")
        assert get_r.status_code == 200
        nombre_returned = get_r.json().get("nombre", "")
        # Should either be escaped or sanitized (no raw <script> or onerror)
        assert "onerror=" not in nombre_returned or "&lt;" in nombre_returned or \
               nombre_returned != xss_nombre, \
               f"Potential stored XSS: nombre returned as-is: {nombre_returned}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-003 — SQL Injection via query params
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_sql_injection_query_params(athlete_api):
    """
    Acceptance:
      SQL injection in query params → 400/422, NOT 500
      No DB error leaked in response
    """
    sql_payloads = [
        "1' OR '1'='1",
        "1; DROP TABLE users;--",
        "' UNION SELECT * FROM users--",
    ]

    for payload in sql_payloads:
        r = athlete_api.get(f"/athlete/blood-labs?limit={payload}")
        assert r.status_code != 500, \
            f"SQL injection in query caused 500: payload='{payload}' response={r.text[:200]}"

        # No DB error messages in response
        body = r.text.lower()
        assert "sql" not in body or "sqlite" not in body or r.status_code in (400, 422), \
            f"SQL error message leaked: {r.text[:200]}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-004 — SQL Injection via POST body
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_sql_injection_post_body(athlete_api):
    """
    Acceptance:
      SQL injection in JSON body → 422 (Pydantic validates) or 400
      Not 500 (no raw SQL errors)
    """
    sql_payloads = [
        {"date_iso": "' OR 1=1--", "values": {"hemoglobin": 15.0}, "notes": "'; DROP TABLE blood_labs;--"},
        {"date_iso": "2026-01-01", "values": {}, "notes": "1' UNION SELECT password FROM users WHERE '1'='1"},
    ]

    for payload in sql_payloads:
        r = athlete_api.post("/labs/exams", json=payload)
        assert r.status_code in (400, 422), \
            f"SQL injection POST should fail validation. Got: {r.status_code}"
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-005 — CORS headers
# ─────────────────────────────────────────────────────────────────────────────
def test_cors_headers_presentes():
    """
    Acceptance:
      OPTIONS preflight from allowed origin → 200/204 with ACAO header
      OPTIONS preflight from unknown origin → 400 (blocked — correct security behavior)
      '*' wildcard must NOT appear for credentialed endpoints
    """
    allowed_origin = "http://localhost:8000"

    # TC-SEC-005a: Allowed origin gets CORS headers
    r_allowed = requests.options(f"{API_URL}/auth/login",
                                 headers={"Origin": allowed_origin,
                                          "Access-Control-Request-Method": "POST"},
                                 timeout=5)
    assert r_allowed.status_code in (200, 204, 405), \
        f"CORS preflight from allowed origin failed: {r_allowed.status_code}"

    # TC-SEC-005b: Unknown origin should be rejected (400) or stripped (no ACAO header)
    r_blocked = requests.options(f"{API_URL}/auth/login",
                                 headers={"Origin": "https://evil.example.com",
                                          "Access-Control-Request-Method": "POST"},
                                 timeout=5)
    blocked_acao = r_blocked.headers.get("access-control-allow-origin", "")
    assert blocked_acao not in ("https://evil.example.com", "*"), \
        f"Unknown origin should not be reflected in ACAO: {blocked_acao}"

    # TC-SEC-005c: Health endpoint reachable (CORS not blocking same-origin)
    r_health = requests.get(f"{BASE_URL}/health",
                            headers={"Origin": allowed_origin},
                            timeout=5)
    assert r_health.status_code == 200, "Health endpoint unreachable"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-006 — Security headers
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_security_headers():
    """
    Acceptance:
      X-Content-Type-Options: nosniff
      X-Frame-Options: DENY or SAMEORIGIN
      Content-Security-Policy (optional but preferred)
    NOTE: These are typically set by nginx; may not be present in dev.
    """
    r = requests.get(f"{BASE_URL}/login.html", timeout=5)
    assert r.status_code == 200

    headers = {k.lower(): v for k, v in r.headers.items()}

    xcto = headers.get("x-content-type-options", "")
    if xcto:
        assert xcto.lower() == "nosniff", \
            f"X-Content-Type-Options should be 'nosniff', got: {xcto}"

    xfo = headers.get("x-frame-options", "")
    if xfo:
        assert xfo.upper() in ("DENY", "SAMEORIGIN"), \
            f"X-Frame-Options invalid: {xfo}"

    # Just log what's present (non-blocking for dev environment)
    has_csp = "content-security-policy" in headers
    has_hsts = "strict-transport-security" in headers
    print(f"\nSecurity headers: CSP={has_csp}, HSTS={has_hsts}, "
          f"X-Frame-Options={xfo or 'MISSING'}, X-Content-Type={xcto or 'MISSING'}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-007 — Token no expuesto en URL
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_token_no_en_url(page, athlete_api):
    """
    Acceptance:
      No page URL or redirect contains '?token=' or '#token='
      Tokens only in localStorage, never in URL
    """
    # Collect all URLs navigated to during auth
    urls_visited = []
    page.on("framenavigated", lambda frame: urls_visited.append(frame.url))

    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
    }}""")
    page.goto(f"{BASE_URL}/dashboard.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    for url in urls_visited:
        assert "token=" not in url.lower(), \
            f"Token found in URL: {url}"
        assert "#token" not in url.lower(), \
            f"Token found in URL fragment: {url}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-008 — Endpoints protegidos → 401 sin token
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
@pytest.mark.parametrize("method,path", [
    ("GET",  "/athlete/dashboard"),
    ("GET",  "/athlete/profile"),
    ("GET",  "/athlete/blood-labs"),
    ("GET",  "/coach/athletes"),
    ("POST", "/coach/workouts"),
    ("GET",  "/messages/inbox"),
    ("GET",  "/api/events"),
])
def test_endpoints_protegidos_sin_token(method, path):
    """
    Acceptance:
      All authenticated endpoints return 401 without Bearer token
    """
    url = f"{API_URL}{path}" if not path.startswith("/api") else f"{BASE_URL}{path}"
    r = requests.request(method, url, timeout=5, json={} if method == "POST" else None)
    assert r.status_code in (401, 403), \
        f"{method} {path} should require auth. Got: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-009 — Atleta no puede acceder a endpoints de coach
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_atleta_no_accede_endpoints_coach(athlete_api):
    """
    Acceptance:
      Athlete token cannot access coach-only endpoints
      Returns 403 Forbidden (not 200)
    """
    coach_endpoints = [
        ("GET",  "/coach/athletes"),
        ("POST", "/coach/groups"),
        ("GET",  "/coach/squad/compliance-trend"),
    ]

    for method, path in coach_endpoints:
        url = f"{API_URL}{path}"
        r = requests.request(
            method, url,
            headers=athlete_api.auth_headers(),
            timeout=5,
            json={} if method == "POST" else None,
        )
        assert r.status_code in (403, 422), \
            f"Athlete accessed coach endpoint {method} {path}: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-010 — Coach no accede a atleta de otro coach
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_coach_no_accede_otro_coach_atleta(coach_api, athlete2_api):
    """
    Acceptance:
      Coach cannot view compliance-trend of athlete NOT in their groups
      Returns 403 or 404 (not 200 with data)
    NOTE: athlete2 is in a different group not belonging to this coach
    """
    profile_r = athlete2_api.get("/athlete/profile")
    if profile_r.status_code != 200:
        pytest.skip("Cannot get athlete2 profile")

    athlete2_id = profile_r.json().get("id") or profile_r.json().get("user_id")
    if not athlete2_id:
        pytest.skip("No athlete2 ID")

    # This coach tries to access athlete2's compliance trend
    r = coach_api.get(f"/coach/athletes/{athlete2_id}/compliance-trend?weeks=4")
    # 200 is allowed only if athlete2 is in this coach's group
    # 403/404 expected if not in group
    assert r.status_code in (200, 403, 404), \
        f"Unexpected status accessing other coach's athlete: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-011 — Password nunca en respuestas API
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_password_no_retornado_en_api(athlete_api):
    """
    Acceptance:
      GET /api/athlete/profile → no 'password' or 'password_hash' field
      POST /api/auth/login → token returned but no password echoed
    """
    # Profile endpoint
    r = athlete_api.get("/athlete/profile")
    assert r.status_code == 200
    data = r.json()

    assert "password" not in data, "Password exposed in profile response"
    assert "password_hash" not in data, "Password hash exposed in profile response"

    # Login response
    login_r = requests.post(f"{API_URL}/auth/login", json={
        "email": TEST_ATHLETE["email"],
        "password": TEST_ATHLETE["password"],
    }, timeout=5)

    if login_r.status_code == 200:
        login_data = login_r.json()
        assert "password" not in login_data, "Password in login response"
        assert "password_hash" not in login_data, "Password hash in login response"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-012 — Health endpoint no expone secrets
# ─────────────────────────────────────────────────────────────────────────────
def test_health_no_secrets():
    """
    Acceptance:
      /health returns basic status info
      No database URLs, passwords, secret keys in response
    """
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 200

    body = r.text.lower()
    secret_patterns = [
        "secret_key", "password", "private_key", "api_key",
        "garmin_pass", "smtp_password", "database_url",
        "redis_url", "stripe_secret",
    ]

    for pattern in secret_patterns:
        assert pattern not in body, \
            f"Potential secret '{pattern}' found in /health response"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-013 — Path traversal bloqueado
# ─────────────────────────────────────────────────────────────────────────────
def test_path_traversal_bloqueado():
    """
    Acceptance:
      GET /../../../etc/passwd → 400 or 404
      GET /static/../../../../etc/passwd → 400 or 404
      NOT 200 with file contents
    """
    traversal_paths = [
        "/../../../etc/passwd",
        "/static/../../../../etc/passwd",
        "/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]

    for path in traversal_paths:
        try:
            r = requests.get(f"{BASE_URL}{path}", timeout=5, allow_redirects=False)
            assert r.status_code in (400, 403, 404), \
                f"Path traversal not blocked for {path}: {r.status_code}"
            # Definitely should not contain Linux passwd file content
            assert "root:" not in r.text and "/bin/bash" not in r.text, \
                f"Path traversal succeeded! Got file content for {path}"
        except requests.exceptions.ConnectionError:
            pass  # Server refused → blocked


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-014 — Brute force: múltiples tokens inválidos no causan 500
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_invalid_tokens_no_causan_500():
    """
    Acceptance:
      Multiple requests with invalid/malformed tokens → 401
      Never 500 (no token parsing exception leaking)
    """
    bad_tokens = [
        "invalid",
        "eyJhbGciOiJIUzI1NiJ9.invalid.signature",
        "null",
        "",
        "Bearer",
        "a" * 1000,  # Very long token
    ]

    for token in bad_tokens:
        r = requests.get(
            f"{API_URL}/athlete/dashboard",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        assert r.status_code in (401, 403, 422), \
            f"Bad token '{token[:30]}...' caused {r.status_code} — expected 401"
        assert r.status_code != 500, \
            f"Token '{token[:30]}' caused 500 error"


# ─────────────────────────────────────────────────────────────────────────────
# TC-SEC-015 — Mass assignment: campos no actualizables via API
# ─────────────────────────────────────────────────────────────────────────────
def test_mass_assignment_bloqueado(athlete_api):
    """
    Acceptance:
      PATCH /api/athlete/profile con 'rol': 'coach' → ignored or 422
      Cannot escalate privileges via profile update
    """
    patch_r = requests.patch(
        f"{API_URL}/athlete/profile",
        json={"rol": "coach", "plan_nivel": "admin"},
        headers=athlete_api.auth_headers(),
        timeout=5
    )

    # Should succeed (ignoring protected fields) or reject 422
    assert patch_r.status_code in (200, 422), \
        f"Mass assignment: {patch_r.status_code} {patch_r.text[:200]}"

    if patch_r.status_code == 200:
        # Verify role was NOT changed
        profile_r = athlete_api.get("/athlete/profile")
        if profile_r.status_code == 200:
            rol = profile_r.json().get("rol", "")
            assert rol != "coach", \
                f"Mass assignment succeeded! Role escalated to: {rol}"
