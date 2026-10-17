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
from urllib.parse import urlparse

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
API_URL  = f"{BASE_URL}/api"

# ─────────────────────────────────────────────────────────────────────────────
# Guardrail contra producción (auditoría 2026-10-17): el suite registra
# cuentas reales vía POST /auth/register contra lo que sea que apunte
# E2E_BASE_URL — nunca hubo nada que impidiera apuntarlo a producción.
# Encontramos 77 cuentas e2e_*/onb_*/qa_* acumuladas en labxperformanceapp.com
# desde julio, incluida una con un payload XSS real (CVE interno, ya
# corregido en coach.html). Esto bloquea la corrida entera salvo --allow-prod
# explícito. No existe un entorno de "staging" separado en este proyecto —
# la única excepción segura por defecto es localhost/127.0.0.1.
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_HOSTS_BY_DEFAULT = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]"}


def pytest_addoption(parser):
    parser.addoption(
        "--allow-prod",
        action="store_true",
        default=False,
        help=(
            "Permite correr el suite E2E contra un E2E_BASE_URL que no sea "
            "localhost (incluida producción). Sin este flag, el suite se "
            "niega a arrancar si detecta un host no-local. Úsalo solo si "
            "sabés exactamente lo que estás haciendo: el suite registra "
            "cuentas reales vía /auth/register y, si falla a mitad de "
            "camino, puede dejarlas sin limpiar pese al teardown (ver "
            "_cleanup_test_users más abajo)."
        ),
    )


def pytest_configure(config):
    """
    Corre antes de recolectar un solo test. Si E2E_BASE_URL apunta a un host
    que no sea local y no se pasó --allow-prod, aborta todo el suite de
    inmediato (no solo salta tests individuales).
    """
    host = (urlparse(BASE_URL).hostname or "").lower()
    if host in _ALLOWED_HOSTS_BY_DEFAULT:
        return
    if config.getoption("--allow-prod"):
        print(
            f"\n[AVISO] E2E_BASE_URL={BASE_URL} (host no-local) — "
            f"corriendo de todas formas por --allow-prod.\n"
        )
        return
    pytest.exit(
        f"\n❌ E2E_BASE_URL={BASE_URL} apunta a un host no-local ('{host}').\n"
        f"   Este suite registra cuentas REALES vía /auth/register — correrlo\n"
        f"   contra ese host dejaría datos de test persistidos ahí.\n"
        f"   Si es intencional (staging dedicado, nunca producción), volvé a\n"
        f"   correr con --allow-prod. Si no, corré sin E2E_BASE_URL (usa\n"
        f"   http://localhost:8000 por defecto) o apuntalo a tu servidor local.\n",
        returncode=1,
    )

# Cuentas creadas durante la sesión (vía APIClient.register) — se limpian
# todas al final en pytest_sessionfinish, pase lo que pase con los tests.
_CREATED_TEST_USER_IDS: set[str] = set()

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
        return self.register_raw(email, password, nombre, rol).json()

    def register_raw(self, email: str, password: str = None, nombre: str = None,
                      rol: str = "atleta", **extra_json) -> requests.Response:
        """Como register(), pero devuelve la Response completa (para tests que
        necesitan inspeccionar status_code, ej. validación de campos
        obligatorios) y sigue trackeando el user_id si la cuenta se creó."""
        body = {"email": email, "rol": rol, **extra_json}
        if password is not None:
            body["password"] = password
        if nombre is not None:
            body["nombre"] = nombre
        r = self.session.post(f"{self.base}/auth/register", json=body)
        # Registrar el user_id para el teardown de fin de sesión — incluso
        # si el test que la creó falla después, esta cuenta debe limpiarse.
        try:
            uid = r.json().get("user_id")
            if uid:
                _CREATED_TEST_USER_IDS.add(uid)
        except Exception:
            pass
        return r

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


# ─────────────────────────────────────────────────────────────────────────────
# Teardown de cuentas de test (auditoría 2026-10-17)
# ─────────────────────────────────────────────────────────────────────────────
# El endpoint de auto-borrado (DELETE /auth/account, "GDPR Art. 17") NO limpia
# todas las tablas con FK a users.id (solo 5 de ~77) — no sirve para garantizar
# que no quede rastro. Se borra directo por DB, con la misma lista de tablas
# usada en la limpieza manual de producción de esta sesión, para que el
# teardown deje la base exactamente como estaba antes de correr el suite.
_USER_FK_TABLE_COLUMNS = [
    ("groups", "coach_id"), ("group_members", "athlete_id"),
    ("coach_athletes", "coach_id"), ("coach_athletes", "athlete_id"),
    ("workout_templates", "coach_id"), ("assigned_workouts", "athlete_id"),
    ("workout_logs", "user_id"), ("wellness_logs", "user_id"),
    ("week_templates", "coach_id"), ("athlete_notes", "coach_id"), ("athlete_notes", "athlete_id"),
    ("macrocycles", "coach_id"), ("blood_lab_exams", "user_id"), ("race_events", "user_id"),
    ("blood_lab_alerts", "user_id"), ("drip_logs", "user_id"), ("food_diary_entries", "user_id"),
    ("training_plans", "coach_id"), ("training_plans", "athlete_id"), ("plan_sessions", "athlete_id"),
    ("injury_risk_snapshots", "user_id"), ("nutrition_plans", "user_id"),
    ("social_follows", "follower_id"), ("social_follows", "following_id"),
    ("social_kudos", "user_id"), ("social_comments", "author_id"),
    ("garmin_activities", "user_id"), ("activity_photos", "user_id"),
    ("garmin_training_load", "user_id"), ("garmin_sync_status", "user_id"),
    ("password_reset_tokens", "user_id"), ("audit_logs", "user_id"),
    ("messages", "from_user_id"), ("messages", "to_user_id"), ("personal_records", "user_id"),
    ("garmin_health_daily", "user_id"), ("garmin_sleep_sessions", "user_id"),
    ("ai_sessions", "user_id"), ("ai_insights", "user_id"), ("ai_athlete_context", "user_id"),
    ("follows", "follower_id"), ("follows", "followed_id"),
    ("community_posts", "user_id"), ("community_posts", "flagged_by"),
    ("kudos", "user_id"), ("comments", "user_id"),
    ("community_groups", "owner_id"), ("community_group_members", "user_id"),
    ("challenges", "creator_id"), ("challenge_entries", "user_id"),
    ("community_notifications", "user_id"), ("community_notifications", "actor_id"),
    ("hydration_logs", "user_id"), ("weight_logs", "user_id"), ("supplement_logs", "user_id"),
    ("custom_foods", "user_id"), ("favorite_foods", "user_id"), ("nutrition_insights", "user_id"),
    ("recovery_scores", "user_id"), ("plan_adaptations", "user_id"),
    ("weekly_plan_snapshots", "user_id"), ("mental_checkins", "user_id"),
    ("mental_fatigue_scores", "user_id"), ("mental_protocol_sessions", "user_id"),
    ("race_results", "user_id"), ("race_plans", "user_id"),
    ("workout_prescriptions", "coach_id"), ("workout_prescriptions", "athlete_id"),
    ("prescription_feedbacks", "athlete_id"),
    ("training_phases", "coach_id"), ("training_phases", "athlete_id"),
    ("performance_benchmarks", "athlete_id"), ("performance_benchmarks", "coach_id"),
    ("plan_templates", "coach_id"), ("garmin_planned_workouts", "user_id"),
    ("running_shoes", "user_id"), ("bikes", "user_id"),
]


def _cleanup_test_users(user_ids: set[str]) -> None:
    """Borra por completo las cuentas creadas en esta sesión (y todo lo que
    referencie su user_id), directo por DB — corre siempre en
    pytest_sessionfinish, incluso si el suite terminó con tests fallidos."""
    if not user_ids:
        return
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from api.database import engine
        from sqlalchemy import text
    except Exception as e:
        print(f"\n[AVISO] Teardown de cuentas E2E omitido — no se pudo importar api.database: {e}")
        return

    ids = list(user_ids)
    placeholders = ",".join(f":id{i}" for i in range(len(ids)))
    params = {f"id{i}": v for i, v in enumerate(ids)}

    with engine.connect() as conn:
        for tbl, col in _USER_FK_TABLE_COLUMNS:
            try:
                conn.execute(text(f"DELETE FROM {tbl} WHERE {col} IN ({placeholders})"), params)
            except Exception:
                pass  # tabla sin esa columna en este deploy, o no existe — no bloquea el resto
        conn.execute(text(f"DELETE FROM users WHERE id IN ({placeholders})"), params)
        conn.commit()
    print(f"\n[TEARDOWN E2E] {len(ids)} cuenta(s) de test eliminada(s) (y sus datos asociados).")


def track_account_for_cleanup(email: str, password: str) -> None:
    """Para cuentas creadas por un camino que NO pasa por APIClient (ej. un
    formulario de registro real llenado con Playwright) — hace login una vez
    para obtener el user_id y lo registra para el teardown de fin de sesión.
    Si el login falla (la cuenta nunca se creó realmente, ej. un test
    negativo o el formulario no envió), no hace nada — no es un error."""
    try:
        r = requests.post(f"{API_URL}/auth/login", json={"email": email, "password": password}, timeout=5)
        if r.status_code == 200:
            uid = r.json().get("user_id")
            if uid:
                _CREATED_TEST_USER_IDS.add(uid)
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    """Hook de pytest — corre al final de TODA la sesión, independientemente
    de si los tests pasaron, fallaron, o hubo errores de colección."""
    _cleanup_test_users(_CREATED_TEST_USER_IDS)


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
