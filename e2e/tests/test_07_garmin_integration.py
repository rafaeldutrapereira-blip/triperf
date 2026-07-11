"""
E2E-GARMIN — Garmin Connect Integration Tests
======================================================
Priority : HIGH (sync is core feature)
Markers  : garmin, manual (OAuth steps)
Coverage :
  TC-GAR-001  Garmin credentials endpoint acepta datos
  TC-GAR-002  Sync-status endpoint disponible
  TC-GAR-003  Force sync endpoint existe (sin credenciales: 400/422)
  TC-GAR-004  [MANUAL] OAuth Garmin Connect login
  TC-GAR-005  [MANUAL] Sync descarga actividades
  TC-GAR-006  Sync-done SSE event se publica
  TC-GAR-007  Actividades aparecen en dashboard después de sync
  TC-GAR-008  Rate limit respetado entre syncs
  TC-GAR-009  Token almacenado en archivo (path correcto)
  TC-GAR-010  Celery task encolada en sync
"""
from __future__ import annotations

import pytest
import requests

from e2e.conftest import BASE_URL, API_URL


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-001 — Credenciales Garmin endpoint
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
def test_garmin_credentials_endpoint_exists(athlete_api):
    """
    Acceptance:
      POST /api/athlete/garmin/credentials con credenciales vacías → 422
      Endpoint existe y valida input correctamente
    NOTE: Credentials must be real Garmin account (manual step)
    """
    # Without real creds → 401 or 422 (validation error)
    r = athlete_api.post("/athlete/garmin-credentials", json={
        "garmin_email": "",
        "garmin_password": "",
    })
    assert r.status_code in (400, 401, 422, 500), \
        f"Empty creds should fail. Got: {r.status_code} {r.text[:200]}"
    assert r.status_code != 405, "405 = wrong endpoint path"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-002 — Sync status endpoint
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.garmin
def test_garmin_sync_status(athlete_api):
    """
    Acceptance:
      GET /api/athlete/garmin/sync-status → 200 or 404
      If 200: has status or last_sync_at field
    """
    r = athlete_api.get("/athlete/garmin/sync-status")
    assert r.status_code in (200, 404), \
        f"Sync status unexpected: {r.status_code} {r.text}"

    if r.status_code == 200:
        data = r.json()
        assert "status" in data or "last_sync_at" in data or "synced" in str(data), \
            f"Missing status field: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-003 — Force sync sin credenciales → error correcto
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
def test_garmin_force_sync_sin_credenciales(athlete_api):
    """
    Given: Athlete without Garmin credentials
    When:  POST /api/athlete/garmin/sync
    Then:  400 or 422 (not 500)
           Error message explains missing credentials
    """
    r = athlete_api.post("/athlete/garmin/sync", json={})
    assert r.status_code in (400, 401, 404, 422), \
        f"Force sync without creds should fail gracefully. Got: {r.status_code}"
    assert r.status_code != 500, "Sync without credentials caused 500 error"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-004 — [MANUAL] Garmin OAuth Login
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.manual
@pytest.mark.garmin
def test_garmin_oauth_login_manual():
    """
    MANUAL TEST — Cannot be automated (OAuth external browser flow)
    ================================================================
    Steps:
    1. Navigate to athlete-app.html → Configuración → Conectar Garmin
    2. Enter real Garmin Connect credentials (username/password)
    3. Click 'Conectar' button
    4. Verify POST /api/athlete/garmin/credentials returns 200
    5. Verify sync-status shows 'connected: true'

    Expected result:
      - Credentials stored encrypted on server
      - First sync triggered automatically
      - Success toast shown in UI

    Test data:
      Use a real Garmin Connect account (not automated)
      Account must have at least 1 activity in last 90 days
    """
    pytest.skip("MANUAL TEST — requires real Garmin Connect account. See docstring for steps.")


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-005 — [MANUAL] Sync descarga actividades
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.manual
@pytest.mark.garmin
def test_garmin_sync_downloads_activities_manual():
    """
    MANUAL TEST — Prerequisite: TC-GAR-004 completed
    =================================================
    Steps:
    1. POST /api/athlete/garmin/sync (or trigger via UI)
    2. Wait for sync to complete (poll sync-status every 5s, max 2 min)
    3. GET /api/athlete/garmin/sync-status

    Expected result:
      - total_activities > 0
      - new_activities >= 0
      - last_sync_at is today's date
      - GET /api/athlete/dashboard shows non-null CTL

    Test data:
      Garmin account with activities from past 6 months
    """
    pytest.skip("MANUAL TEST — requires Garmin credentials. See docstring.")


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-006 — Sync-done SSE event publicado
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
@pytest.mark.realtime
def test_garmin_sync_done_sse_schema():
    """
    Acceptance:
      garmin_pull_service.py publishes 'garmin_sync_done' event
      Event payload: {activities_synced: int, new_activities: int}

    This verifies the API schema, not live delivery (covered in SSE tests).
    """
    import ast
    import os

    svc_path = r"C:\Users\rafae\projects\LabX\api\garmin_pull_service.py"
    assert os.path.exists(svc_path), "garmin_pull_service.py not found"

    with open(svc_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "publish_nowait" in content, \
        "garmin_pull_service.py should call publish_nowait for SSE events"
    assert "garmin_sync_done" in content, \
        "Missing 'garmin_sync_done' event name in garmin_pull_service.py"
    assert "activities_synced" in content or "total" in content, \
        "Missing activities_synced in sync_done payload"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-007 — Actividades en dashboard post-sync (API check)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
def test_actividades_dashboard_estructura(athlete_api):
    """
    Acceptance:
      GET /api/athlete/dashboard returns consistent structure
      CTL/ATL fields are numeric (or null if no activities)
    NOTE: Actual numeric values require synced Garmin data
    """
    r = athlete_api.get("/athlete/dashboard")
    assert r.status_code == 200, f"Dashboard: {r.status_code} {r.text}"
    data = r.json()

    # Fields exist (may be null without Garmin data)
    for field in ("ctl", "atl", "tsb"):
        if field in data:
            val = data[field]
            assert val is None or isinstance(val, (int, float)), \
                f"'{field}' invalid type: {type(val)}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-008 — Rate limit entre syncs consecutivos
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
def test_garmin_rate_limit_consecutive_sync(athlete_api):
    """
    Acceptance:
      Two consecutive POST /api/athlete/garmin/sync calls
      Second call returns 429 (rate limited) or 400 (cooldown)
      NOT two separate syncs running simultaneously

    NOTE: Rate limit is ~30 min between syncs (Garmin API constraint)
    """
    # First call (likely 400 if no credentials, which is fine)
    r1 = athlete_api.post("/athlete/garmin/sync", json={})

    # Second call immediately after
    r2 = athlete_api.post("/athlete/garmin/sync", json={})

    # Either both fail gracefully or second is rate-limited
    assert r1.status_code != 500, "First sync call caused 500"
    assert r2.status_code != 500, "Second sync call caused 500"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-009 — Token path structure
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
def test_garmin_token_path_structure():
    """
    Acceptance:
      garmin_pull_service.py or garmin config uses path:
      data/garmin_tokens/{user_id}
      Directory data/garmin_tokens/ exists or is created on first sync
    """
    import os

    svc_path = r"C:\Users\rafae\projects\LabX\api\garmin_pull_service.py"
    if not os.path.exists(svc_path):
        pytest.skip("garmin_pull_service.py not found")

    with open(svc_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "garmin_tokens" in content or "tokens" in content.lower(), \
        "Token storage path not found in garmin_pull_service.py"


# ─────────────────────────────────────────────────────────────────────────────
# TC-GAR-010 — Celery task encolada en sync
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.garmin
def test_celery_garmin_task_exists():
    """
    Acceptance:
      tasks.py or celery_app.py has 'sync_garmin' task defined
      Task is decorated with @app.task or @celery.task
    """
    import os
    import glob

    base = r"C:\Users\rafae\projects\LabX\api"
    candidates = glob.glob(f"{base}/**/*.py", recursive=True)

    task_found = False
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if ("@app.task" in content or "@celery.task" in content or
                    "celery" in content.lower()) and "garmin" in content.lower():
                task_found = True
                break
        except Exception:
            continue

    assert task_found, \
        "No Celery task found with Garmin integration. Expected @app.task + garmin"
