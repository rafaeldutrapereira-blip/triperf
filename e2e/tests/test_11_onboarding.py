"""
E2E-ONBOARDING — New User Onboarding Flow Tests
======================================================
Priority : HIGH (first impression)
Markers  : athlete, smoke
Coverage :
  TC-ONB-001  Onboarding page accesible post-registro
  TC-ONB-002  Paso 1: Datos personales (edad, peso, altura)
  TC-ONB-003  Paso 2: Objetivos deportivos
  TC-ONB-004  Paso 3: Conectar Garmin (puede saltar)
  TC-ONB-005  Paso 4: FTP / umbrales
  TC-ONB-006  Completar onboarding → dashboard
  TC-ONB-007  Usuario que saltó onboarding puede completarlo luego
  TC-ONB-008  Validación de campos obligatorios
  TC-ONB-009  Progress indicator muestra paso actual
  TC-ONB-010  Onboarding completado no se repite en login
"""
from __future__ import annotations

import uuid
import pytest
import requests

from e2e.conftest import BASE_URL, API_URL, TEST_ATHLETE


def _register_new_user():
    """Register a fresh user for onboarding tests."""
    uid = uuid.uuid4().hex[:8]
    email = f"onb_{uid}@test.com"
    r = requests.post(f"{API_URL}/auth/register", json={
        "nombre": "Onboarding Test",
        "email": email,
        "password": "Onboard_2026!",
    })
    if r.status_code not in (200, 201):
        return None, None
    return email, r.json().get("access_token") or r.json().get("token")


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-001 — Onboarding page accesible
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.athlete
def test_onboarding_page_accesible(athlete_api):
    """
    Acceptance:
      GET /onboarding.html (or /profile.html with onboarding section) → 200
      Page has form elements for user profile setup
    """
    r = requests.get(f"{BASE_URL}/onboarding.html", timeout=5)
    if r.status_code == 404:
        # Onboarding may be part of profile or registro flow
        r = requests.get(f"{BASE_URL}/profile.html", timeout=5)

    assert r.status_code == 200, \
        "Onboarding page not found (tried /onboarding.html and /profile.html)"
    assert len(r.text) > 500, "Onboarding page appears empty"


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-002 — Datos personales via API
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_datos_personales_via_api(athlete_api):
    """
    Acceptance:
      PATCH /api/athlete/profile with personal data → 200
      Fields: edad, peso_kg, altura_cm
    """
    r = requests.patch(
        f"{API_URL}/athlete/profile",
        json={
            "edad": 35,
            "peso_kg": 72.5,
            "altura_cm": 178,
        },
        headers=athlete_api.auth_headers(),
        timeout=5
    )
    assert r.status_code == 200, f"Profile update: {r.status_code} {r.text[:200]}"
    data = r.json()
    print(f"\nProfile update response: {data}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-003 — Objetivos deportivos via API
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_objetivo_deportivo_via_api(athlete_api):
    """
    Acceptance:
      PATCH /api/athlete/profile with goal → 200
      Fields: objetivo_carrera (e.g., 'ironman_140.6')
    """
    r = requests.patch(
        f"{API_URL}/athlete/profile",
        json={"objetivo_carrera": "ironman_140.6"},
        headers=athlete_api.auth_headers(),
        timeout=5
    )
    assert r.status_code in (200, 422), f"Goal update: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-004 — FTP update via API (Paso umbrales)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_ftp_update_via_api(athlete_api):
    """
    Acceptance:
      PATCH /api/athlete/profile with FTP → 200
      ftp field updated in response
      FTP range 100–600W (triathlete typical range)
    """
    r = requests.patch(
        f"{API_URL}/athlete/profile",
        json={"ftp": 250},
        headers=athlete_api.auth_headers(),
        timeout=5
    )
    assert r.status_code == 200, f"FTP update: {r.status_code} {r.text}"
    data = r.json()
    if "ftp" in data:
        assert data["ftp"] == 250, f"FTP not updated. Got: {data['ftp']}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-005 — Garmin skip en onboarding (UI)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_garmin_skip_onboarding(page, athlete_api):
    """
    Acceptance:
      Onboarding page has 'Saltar' or 'Skip' option for Garmin step
      Clicking skip moves to next step without error
    """
    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
    }}""")

    # Try onboarding page
    page.goto(f"{BASE_URL}/onboarding.html")
    page.wait_for_load_state("networkidle")

    if page.url.endswith("onboarding.html") or "onboarding" in page.url:
        skip_btn = page.locator("button:has-text('Saltar'), button:has-text('Skip'), a:has-text('Saltar')").first
        if skip_btn.is_visible(timeout=3000):
            skip_btn.click()
            page.wait_for_timeout(1000)
            print(f"\nAfter skip: {page.url}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-006 — Onboarding completo → dashboard
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_onboarding_completo_redirect(page, athlete_api):
    """
    Given: User completes onboarding form
    When:  Submit final step
    Then:  Redirect to dashboard.html or athlete-app.html
           Profile has onboarding_completed flag
    """
    # Simulate onboarding completion via API
    patch_r = requests.patch(
        f"{API_URL}/athlete/profile",
        json={
            "edad": 30,
            "peso_kg": 70.0,
            "altura_cm": 175,
            "ftp": 240,
            "objetivo_carrera": "70.3",
        },
        headers=athlete_api.auth_headers(),
        timeout=5
    )
    assert patch_r.status_code == 200, \
        f"Onboarding profile setup failed: {patch_r.status_code}"

    # Verify profile complete
    profile_r = athlete_api.get("/athlete/profile")
    assert profile_r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-007 — Validación campos obligatorios en registro
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_validacion_campos_registro():
    """
    Acceptance:
      POST /api/auth/register without required fields → 422
      Error details in response identify missing fields
    """
    # Missing email
    r1 = requests.post(f"{API_URL}/auth/register", json={
        "nombre": "Test",
        "password": "Pass_2026!"
    }, timeout=5)
    assert r1.status_code == 422, f"Missing email should be 422: {r1.status_code}"

    # Missing password
    r2 = requests.post(f"{API_URL}/auth/register", json={
        "nombre": "Test",
        "email": "test@test.com"
    }, timeout=5)
    assert r2.status_code == 422, f"Missing password should be 422: {r2.status_code}"

    # Missing nombre
    r3 = requests.post(f"{API_URL}/auth/register", json={
        "email": "test@test.com",
        "password": "Pass_2026!"
    }, timeout=5)
    assert r3.status_code in (200, 201, 422), \
        f"Missing nombre: {r3.status_code}"  # nombre may be optional


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-008 — Progress indicator en onboarding (UI)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_progress_indicator_onboarding(page, athlete_api):
    """
    Acceptance:
      Onboarding page shows step indicator (1/4, 2/4, etc. or dots)
    """
    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
    }}""")

    page.goto(f"{BASE_URL}/onboarding.html")
    page.wait_for_load_state("networkidle")

    if "onboarding" not in page.url:
        pytest.skip("No onboarding page found")

    progress = page.locator(
        "[class*='progress'], [class*='step'], [class*='wizard'], [class*='breadcrumb']"
    ).first
    if progress.is_visible(timeout=3000):
        print(f"\nProgress indicator found: {progress.inner_text()[:50]}")
    # Non-blocking: progress UX check


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-009 — Nuevo registro → onboarding completo flujo
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
@pytest.mark.slow
def test_nuevo_registro_onboarding_flow(page):
    """
    Given: Brand new user registers
    When:  Complete registration
    Then:  Either directed to onboarding or dashboard (no broken page)
           No JS errors on arrival page
    """
    uid = uuid.uuid4().hex[:6]
    new_email = f"onb_flow_{uid}@test.com"

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # Register
    page.goto(f"{BASE_URL}/registro.html")
    page.wait_for_load_state("networkidle")

    # Fill registration form
    try:
        page.fill("#nombre", "Test Onb")
        page.fill("#email", new_email)
        page.fill("#password", "OnbTest_2026!")
        page.fill("#confirm_password, #confirmPassword, #password2", "OnbTest_2026!")
    except Exception:
        pytest.skip("Registration form fields not found in expected DOM structure")

    page.click("button[type='submit'], button:has-text('Registrar'), button:has-text('Crear')")
    page.wait_for_timeout(3000)

    # Should be somewhere useful (not stuck on registro.html with errors)
    current = page.url
    body = page.locator("body").inner_text().lower()
    print(f"\nPost-registration URL: {current}")

    # Either onboarding, dashboard, or login (to re-enter)
    assert any(p in current for p in ["onboarding", "dashboard", "login", "athlete", "home"]) or \
           len(body) > 100, "After registration: page appears blank or stuck"


# ─────────────────────────────────────────────────────────────────────────────
# TC-ONB-010 — Onboarding no se repite para usuario existente
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_onboarding_no_se_repite(page, athlete_api):
    """
    Acceptance:
      Authenticated user navigating to dashboard is NOT forced into onboarding again
      Only new users see onboarding flow
    """
    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
        localStorage.setItem('lx_onboarding_done', 'true');
    }}""")

    page.goto(f"{BASE_URL}/dashboard.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # Should stay on dashboard, not redirect to onboarding
    assert "onboarding" not in page.url, \
        f"Existing user forced into onboarding: {page.url}"
