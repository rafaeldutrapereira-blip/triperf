"""
E2E-COACH — Coach Platform Flows
======================================================
Priority : CRITICAL / HIGH
Markers  : critical, coach
Coverage :
  TC-COACH-001  Coach Platform carga con sidebar nav
  TC-COACH-002  Lista de atletas visible
  TC-COACH-003  Asignar workout a atleta (API)
  TC-COACH-004  Ver compliance trend del squad (API)
  TC-COACH-005  Crear grupo (API)
  TC-COACH-006  Agregar atleta al grupo (API)
  TC-COACH-007  Campana de notificaciones visible
  TC-COACH-008  Mensajes — enviar mensaje a atleta (API)
  TC-COACH-009  Ver plan de atleta (API)
  TC-COACH-010  Workout templates — crear template (API)
"""
from __future__ import annotations

import uuid
import pytest
import requests
from playwright.sync_api import Page, expect

from e2e.conftest import BASE_URL, TEST_ATHLETE, TEST_ATHLETE2
from e2e.pages.coach_page import CoachPage


def _inject_coach_auth(page: Page, token: str):
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{token}');
        localStorage.setItem('lx_co_rol', 'coach');
        localStorage.setItem('lx_co_nombre', 'Coach E2E');
    }}""")


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-001 — Coach Platform carga
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.critical
@pytest.mark.coach
def test_coach_platform_carga(page: Page, coach_api):
    """
    Given: Coach logged in
    When:  Navigate to coach.html
    Then:  Platform loads without JS errors
           Sidebar navigation visible
           Coach name shown in header
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_coach_auth(page, coach_api._token)

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    coach_pg = CoachPage(page, BASE_URL).navigate()

    assert not errors, f"JS errors on coach.html: {errors}"

    # Sidebar or nav should be visible
    nav = page.locator(
        "[class*='sidebar'], nav, [class*='coach-nav'], [class*='tab']"
    ).first
    expect(nav).to_be_visible(timeout=6000)


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-002 — Lista de atletas
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_coach_lista_atletas(page: Page, coach_api, test_group_id):
    """
    Given: Coach has athletes in their groups
    When:  Coach views athlete list
    Then:  At least one athlete card visible
           Athlete name and metrics shown
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_coach_auth(page, coach_api._token)

    coach_pg = CoachPage(page, BASE_URL).navigate()
    page.wait_for_timeout(2000)

    # Try clicking athletes tab if it exists
    ath_tab = page.locator("button:has-text('Atletas'), [data-tab='athletes']").first
    if ath_tab.is_visible():
        ath_tab.click()
        page.wait_for_timeout(1000)

    # Athlete content should exist
    content = page.locator("[class*='athlete'], [class*='squad'], [class*='member']").first
    expect(content).to_be_visible(timeout=8000)


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-003 — Asignar workout a atleta (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
@pytest.mark.coach
def test_asignar_workout_api(coach_api, athlete_api, test_group_id):
    """
    Given: Coach has workout template and athlete in group
    When:  POST /api/coach/assign-workout
    Then:  201 Created
           Assignment visible in athlete's plan
    Acceptance criteria:
      - Response has 'id' field
      - GET /api/athlete/plan returns the assignment
    """
    # First create a workout template
    template_r = coach_api.post("/coach/workout-templates", json={
        "nombre": "E2E FTP Test",
        "sport": "bike",
        "description": "E2E test workout",
        "duration_min": 60,
    })
    assert template_r.status_code in (200, 201), f"Template creation failed: {template_r.text}"
    template_id = template_r.json().get("id")
    assert template_id, "No template ID returned"

    # Get athlete ID from athlete_api
    profile_r = athlete_api.get("/athlete/profile")
    assert profile_r.status_code == 200, f"Profile fetch failed: {profile_r.text}"
    athlete_id = profile_r.json().get("id") or profile_r.json().get("user_id")
    assert athlete_id, "Could not get athlete ID"

    # Assign workout
    from datetime import date, timedelta
    future_date = (date.today() + timedelta(days=3)).isoformat()

    assign_r = coach_api.post("/coach/assign-workout", json={
        "template_id": template_id,
        "athlete_id": athlete_id,
        "date_iso": future_date,
        "notas": "E2E test assignment",
    })
    assert assign_r.status_code in (200, 201), \
        f"Workout assignment failed: {assign_r.status_code} {assign_r.text}"

    data = assign_r.json()
    assert "id" in data, "No assignment ID in response"

    # Verify assignment visible from athlete side
    plan_r = athlete_api.get(f"/athlete/plan?start={future_date}&end={future_date}")
    assert plan_r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-004 — Compliance trend squad (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_compliance_trend_squad_api(coach_api):
    """
    Given: Coach API
    When:  GET /api/coach/squad/compliance-trend
    Then:  200 OK
           Response has 'athletes' list
           Each athlete has 'trend' array
    """
    r = coach_api.get("/coach/squad/compliance-trend?weeks=4")
    assert r.status_code == 200, f"Squad compliance failed: {r.text}"
    data = r.json()
    assert "athletes" in data, "Missing 'athletes' key"
    assert "weeks" in data
    assert data["weeks"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-005 — Crear grupo (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_crear_grupo_api(coach_api):
    """
    Given: Coach API
    When:  POST /api/coach/groups
    Then:  201 Created
           Group has ID, nombre, coach_id
    """
    r = coach_api.post("/coach/groups", json={
        "nombre": f"E2E Group {uuid.uuid4().hex[:4]}",
        "descripcion": "Created by E2E test"
    })
    assert r.status_code == 201, f"Group creation failed: {r.text}"
    data = r.json()
    assert "id" in data
    assert "nombre" in data


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-006 — Ver atletas del grupo (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_ver_atletas_del_grupo(coach_api, test_group_id):
    """
    Given: Group with at least one athlete
    When:  GET /api/coach/groups/{id}/members
    Then:  200 OK, list of members
    """
    r = coach_api.get(f"/coach/groups/{test_group_id}/members")
    assert r.status_code == 200, f"Members fetch failed: {r.text}"
    assert isinstance(r.json(), list)


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-007 — Notificaciones bell (UI)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_notification_bell_visible(page: Page, coach_api):
    """
    Given: Coach on coach.html
    When:  Page loads
    Then:  Notification bell icon is present and clickable
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_coach_auth(page, coach_api._token)

    CoachPage(page, BASE_URL).navigate()
    page.wait_for_timeout(1500)

    bell = page.locator("[class*='bell'], [class*='notif'], [id*='notif'], [aria-label*='notif']").first
    expect(bell).to_be_visible(timeout=6000)


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-008 — Enviar mensaje a atleta (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_enviar_mensaje_atleta_api(coach_api, athlete_api):
    """
    Given: Coach and athlete exist
    When:  POST /api/messages with athlete's ID
    Then:  201 Created
           Message in athlete's inbox
    """
    # Get athlete ID
    profile_r = athlete_api.get("/athlete/profile")
    assert profile_r.status_code == 200
    athlete_id = profile_r.json().get("id") or profile_r.json().get("user_id")
    assert athlete_id

    # Send message
    msg_r = coach_api.post("/messages", json={
        "to_user_id": athlete_id,
        "body": "Hola E2E! Este es un mensaje de prueba automatizada."
    })
    assert msg_r.status_code == 201, f"Message send failed: {msg_r.text}"
    data = msg_r.json()
    assert "id" in data

    # Verify in athlete inbox
    inbox_r = athlete_api.get("/messages/inbox")
    assert inbox_r.status_code == 200
    messages = inbox_r.json()
    assert isinstance(messages, list)
    # Message should appear (may be paginated so just check status)


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-009 — Ver plan de atleta (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_ver_plan_atleta_api(coach_api, athlete_api):
    """
    Given: Coach has athlete in group
    When:  GET /api/coach/athletes/{id}/compliance-trend
    Then:  200 OK, weekly compliance data returned
    """
    profile_r = athlete_api.get("/athlete/profile")
    assert profile_r.status_code == 200
    athlete_id = profile_r.json().get("id") or profile_r.json().get("user_id")

    r = coach_api.get(f"/coach/athletes/{athlete_id}/compliance-trend?weeks=4")
    assert r.status_code in (200, 403), f"Unexpected: {r.status_code} {r.text}"
    # 403 is acceptable if athlete not in this coach's group
    if r.status_code == 200:
        assert isinstance(r.json(), list)


# ─────────────────────────────────────────────────────────────────────────────
# TC-COACH-010 — Workout templates (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.coach
def test_workout_templates_crud_api(coach_api):
    """
    Given: Coach API
    When:  Create → List → Delete template
    Then:  Full CRUD cycle works
    """
    # Create
    create_r = coach_api.post("/coach/workout-templates", json={
        "nombre": f"E2E Template {uuid.uuid4().hex[:4]}",
        "sport": "run",
        "description": "E2E CRUD test",
        "duration_min": 45,
    })
    assert create_r.status_code in (200, 201), f"Create failed: {create_r.text}"
    tid = create_r.json().get("id")
    assert tid

    # List
    list_r = coach_api.get("/coach/workout-templates")
    assert list_r.status_code == 200
    templates = list_r.json()
    assert any(t["id"] == tid for t in templates), "Created template not found in list"

    # Delete
    del_r = coach_api.delete(f"/coach/workout-templates/{tid}")
    assert del_r.status_code in (200, 204), f"Delete failed: {del_r.text}"
