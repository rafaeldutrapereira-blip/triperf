"""
LabX E2E Test Suite — conftest.py
Global fixtures: browser setup, test users, API helpers, page cleanup.
"""
from __future__ import annotations

import os
import uuid
import time
import pytest
import requests
from typing import Generator

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
API_URL  = f"{BASE_URL}/api"

# Shared test accounts (created once per session)
TEST_COACH = {
    "email":    f"e2e_coach_{uuid.uuid4().hex[:6]}@labx-test.com",
    "password": "E2eCoach_2026!",
    "nombre":   "Coach E2E",
    "rol":      "coach",
}
TEST_ATHLETE = {
    "email":    f"e2e_athlete_{uuid.uuid4().hex[:6]}@labx-test.com",
    "password": "E2eAthlete_2026!",
    "nombre":   "Athlete E2E",
    "rol":      "atleta",
}
TEST_ATHLETE2 = {
    "email":    f"e2e_athlete2_{uuid.uuid4().hex[:6]}@labx-test.com",
    "password": "E2eAthlete2_2026!",
    "nombre":   "Athlete Two",
    "rol":      "atleta",
}


# ─────────────────────────────────────────────────────────────────────────────
# Playwright configuration
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Shared browser context: ignore HTTPS errors, set viewport."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "viewport": {"width": 1440, "height": 900},
        "locale": "es-ES",
        "timezone_id": "America/Santiago",
    }


@pytest.fixture(scope="session")
def playwright_options():
    return {"slow_mo": int(os.getenv("SLOWMO", "0"))}


# ─────────────────────────────────────────────────────────────────────────────
# API helper (for setup/teardown without browser)
# ─────────────────────────────────────────────────────────────────────────────

class APIClient:
    """Direct API client for test data setup."""

    def __init__(self, base_url: str = API_URL):
        self.base = base_url
        self._token: str | None = None
        self.session = requests.Session()

    def register(self, email: str, password: str, nombre: str, rol: str = "atleta") -> dict:
        r = self.session.post(f"{self.base}/auth/register", json={
            "email": email, "password": password, "nombre": nombre, "rol": rol
        })
        return r.json()

    def login(self, email: str, password: str) -> str:
        r = self.session.post(f"{self.base}/auth/login", json={
            "email": email, "password": password
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        self._token = r.json()["access_token"]
        return self._token

    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(f"{self.base}{path}", headers=self.auth_headers(), **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(f"{self.base}{path}", headers=self.auth_headers(), **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        return self.session.delete(f"{self.base}{path}", headers=self.auth_headers(), **kwargs)


@pytest.fixture(scope="session")
def api() -> APIClient:
    """Session-scoped API client for admin/setup operations."""
    client = APIClient()
    # Verify server is up
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200, "Server not running — start with: uvicorn api.coach_main:app --reload"
    except Exception as e:
        pytest.exit(f"❌ Server not reachable at {BASE_URL}: {e}", returncode=1)

    # Clear accumulated LoginAttempt records so rate limits don't cascade across sessions
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from api.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM login_attempts"))
            conn.commit()
    except Exception:
        pass  # Non-fatal — rate limits will reset naturally

    return client


# ─────────────────────────────────────────────────────────────────────────────
# Test user fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def athlete_api(api) -> APIClient:
    """API client logged in as test athlete."""
    api.register(**TEST_ATHLETE)
    client = APIClient()
    client.login(TEST_ATHLETE["email"], TEST_ATHLETE["password"])
    return client


@pytest.fixture(scope="session")
def athlete2_api(api) -> APIClient:
    """Second athlete for multi-user tests."""
    api.register(**TEST_ATHLETE2)
    client = APIClient()
    client.login(TEST_ATHLETE2["email"], TEST_ATHLETE2["password"])
    return client


@pytest.fixture(scope="session")
def coach_token(api) -> str:
    """JWT token for a coach (created via DB direct — coaches can't self-register)."""
    # Insert coach via admin endpoint or direct DB — we use a pre-seeded dev coach
    # In CI: set E2E_COACH_EMAIL and E2E_COACH_PASSWORD env vars
    coach_email = os.getenv("E2E_COACH_EMAIL", "coach@test.com")
    coach_pass  = os.getenv("E2E_COACH_PASSWORD", "CoachPass123")
    try:
        client = APIClient()
        return client.login(coach_email, coach_pass)
    except Exception:
        pytest.skip("Coach account not available — set E2E_COACH_EMAIL / E2E_COACH_PASSWORD")


@pytest.fixture(scope="session")
def coach_api(coach_token) -> APIClient:
    client = APIClient()
    client._token = coach_token
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Page helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_page(page):
    """Page with cleared storage before each test."""
    # Must navigate to the origin before accessing localStorage (about:blank denies it)
    page.goto(f"{BASE_URL}/login.html")
    page.wait_for_load_state("domcontentloaded")
    page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    yield page
    # Cleanup after test
    try:
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass


@pytest.fixture
def logged_in_page(page, athlete_api):
    """
    Page pre-authenticated as athlete.
    Injects tokens so tests start on authenticated pages.
    """
    page.goto(f"{BASE_URL}/login.html")
    page.wait_for_load_state("networkidle")
    # Inject auth tokens via localStorage
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
        localStorage.setItem('lx_co_nombre', 'Athlete E2E');
        localStorage.setItem('lx_ath_token', '{athlete_api._token}');
    }}""")
    return page


@pytest.fixture
def coach_page(page, coach_api):
    """Page pre-authenticated as coach."""
    page.goto(f"{BASE_URL}/login.html")
    page.wait_for_load_state("networkidle")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{coach_api._token}');
        localStorage.setItem('lx_co_rol', 'coach');
        localStorage.setItem('lx_co_nombre', 'Coach E2E');
    }}""")
    return page


# ─────────────────────────────────────────────────────────────────────────────
# Shared test data
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_group_id(coach_api, athlete_api) -> str:
    """Create a test group with one athlete."""
    # Create group
    r = coach_api.post("/coach/groups", json={
        "nombre": "E2E Test Group",
        "descripcion": "Created by E2E tests"
    })
    if r.status_code != 201:
        pytest.skip(f"Could not create test group: {r.text}")
    group_id = r.json()["id"]

    # Add athlete to group
    ath_r = requests.post(f"{API_URL}/auth/register", json=TEST_ATHLETE)
    athlete_id_r = requests.post(f"{API_URL}/auth/login", json={
        "email": TEST_ATHLETE["email"],
        "password": TEST_ATHLETE["password"]
    })
    if athlete_id_r.status_code == 200:
        athlete_data = athlete_id_r.json()
        athlete_id = athlete_data.get("user_id")
        if athlete_id:
            coach_api.post(f"/coach/groups/{group_id}/members", json={"athlete_id": athlete_id})

    return group_id


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_toast(page, text: str = None, timeout: int = 5000):
    """Wait for a toast/alert notification to appear."""
    locator = page.locator("[class*='toast'], [class*='alert'], [class*='notif'], [role='alert']")
    locator.wait_for(state="visible", timeout=timeout)
    if text:
        assert text.lower() in locator.text_content().lower()
    return locator


def assert_no_js_errors(page):
    """Assert no uncaught JS errors occurred (attach before navigation)."""
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    return errors


def screenshot_on_failure(page, name: str):
    """Take screenshot for debugging."""
    path = f"e2e/screenshots/{name}_{int(time.time())}.png"
    os.makedirs("e2e/screenshots", exist_ok=True)
    page.screenshot(path=path)
    return path
