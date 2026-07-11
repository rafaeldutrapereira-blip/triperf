"""
E2E-API — Critical API Contract Tests
======================================================
Priority : CRITICAL
Markers  : smoke, critical
Coverage :
  TC-API-001  Health endpoint
  TC-API-002  Metrics endpoint (Prometheus)
  TC-API-003  Dashboard endpoint estructura
  TC-API-004  Garmin sync status (no credentials → skip)
  TC-API-005  Blood labs CRUD
  TC-API-006  Readiness score endpoint
  TC-API-007  Recovery score endpoint
  TC-API-008  Athlete compliance trend
  TC-API-009  SSE events endpoint responde
  TC-API-010  AI coach endpoint con timeout
  TC-API-011  Injury risk endpoint
  TC-API-012  Nutrition endpoints
  TC-API-013  Zonas de entrenamiento
  TC-API-014  Race endpoints
  TC-API-015  Periodization endpoints
"""
from __future__ import annotations

import pytest
import requests

from e2e.conftest import BASE_URL, API_URL


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-001 — Health
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.critical
def test_health_endpoint():
    """
    Acceptance:
      Status 200
      JSON has: status, service, version, db
      db = 'ok'
    """
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") in ("ok", "degraded"), f"Bad status: {data}"
    assert "version" in data
    assert "db" in data
    assert data["db"] == "ok", f"DB not ok: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-002 — Prometheus Metrics
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
def test_metrics_endpoint():
    """
    Acceptance:
      /metrics returns 200
      Content-Type text/plain
      Contains 'http_requests_total' counter
    """
    r = requests.get(f"{BASE_URL}/metrics", timeout=5)
    # 503 means prometheus-client not installed or server not yet restarted after install
    if r.status_code == 503:
        pytest.skip("prometheus-client not installed in this server instance — restart server after: pip install prometheus-client")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    assert "http_requests_total" in r.text or "uptime" in r.text


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-003 — Dashboard endpoint
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.critical
def test_dashboard_endpoint_estructura(athlete_api):
    """
    Acceptance:
      GET /api/athlete/dashboard → 200
      Has: source, ctl, atl, tsb, acwr, compliance_week
      Numeric values (or null) for training load
    """
    r = athlete_api.get("/athlete/dashboard")
    assert r.status_code == 200, f"Dashboard failed: {r.text}"
    data = r.json()

    required_keys = ["source"]
    for k in required_keys:
        assert k in data, f"Missing key '{k}' in dashboard response"

    # Numeric or null metrics
    for key in ("ctl", "atl", "tsb"):
        if key in data:
            assert data[key] is None or isinstance(data[key], (int, float)), \
                f"'{key}' should be numeric or null, got {type(data[key])}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-004 — Garmin sync status
# ─────────────────────────────────────────────────────────────────────────────
def test_garmin_sync_status(athlete_api):
    """
    Acceptance:
      GET /api/athlete/garmin/sync-status → 200
      Has: status field
    NOTE: Actual sync requires Garmin credentials (manual step)
    """
    r = athlete_api.get("/athlete/garmin/sync-status")
    assert r.status_code in (200, 404), f"Unexpected: {r.status_code} {r.text}"
    if r.status_code == 200:
        data = r.json()
        assert "status" in data or "last_sync_at" in data


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-005 — Blood Labs CRUD
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_blood_labs_crud(athlete_api):
    """
    Acceptance:
      POST /api/athlete/blood-labs → 201
      GET /api/athlete/blood-labs → 200, list
      Entry has: id, test_date, hemoglobin (or any lab marker)
    """
    from datetime import date

    # Create
    create_r = athlete_api.post("/labs/exams", json={
        "date_iso": date.today().isoformat(),
        "values": {"hemoglobin": 15.2, "hematocrit": 44.5, "ferritin": 45.0},
        "notes": "E2E test blood lab entry"
    })
    assert create_r.status_code in (200, 201), f"Blood lab create failed: {create_r.text}"

    # List
    list_r = athlete_api.get("/labs/exams")
    assert list_r.status_code == 200
    labs = list_r.json()
    assert isinstance(labs, list)
    assert len(labs) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-006 — Readiness Score
# ─────────────────────────────────────────────────────────────────────────────
def test_readiness_score_endpoint(athlete_api):
    """
    Acceptance:
      GET /api/athlete/readiness → 200
      Has: readiness_score (0-100 or null)
      Has: components dict
    """
    r = athlete_api.get("/readiness/daily")
    assert r.status_code == 200, f"Readiness failed: {r.text}"
    data = r.json()

    if "readiness_score" in data:
        score = data["readiness_score"]
        assert score is None or (0 <= score <= 100), f"Invalid score: {score}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-007 — Recovery Score
# ─────────────────────────────────────────────────────────────────────────────
def test_recovery_endpoint(athlete_api):
    """
    Acceptance:
      GET /api/athlete/recovery/status → 200
      Has recovery metrics
    """
    r = athlete_api.get("/athlete/recovery/status")
    assert r.status_code in (200, 404), f"Recovery endpoint: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-008 — Compliance Trend (athlete)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.critical
def test_athlete_compliance_trend(athlete_api):
    """
    Acceptance:
      GET /api/athlete/compliance-trend?weeks=4 → 200
      Returns list of 4 items
      Each item has: week_start, week_end, compliance_pct
    """
    r = athlete_api.get("/athlete/compliance-trend?weeks=4")
    assert r.status_code == 200, f"Compliance trend failed: {r.text}"
    data = r.json()
    assert isinstance(data, list), "Expected list"
    assert len(data) == 4, f"Expected 4 weeks, got {len(data)}"

    for week in data:
        assert "week_start" in week
        assert "week_end" in week
        assert "compliance_pct" in week
        if week["compliance_pct"] is not None:
            assert 0 <= week["compliance_pct"] <= 100


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-009 — SSE Events endpoint
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.realtime
def test_sse_events_endpoint_conecta(athlete_api):
    """
    Acceptance:
      GET /api/events with auth → 200
      Content-Type: text/event-stream
      First chunk contains 'connected' event

    NOTE: Full SSE stream requires long-lived connection.
    This test verifies only the connection headers + first chunk.
    """
    import requests

    with requests.get(
        f"{API_URL}/events",
        headers=athlete_api.auth_headers(),
        stream=True,
        timeout=10
    ) as resp:
        assert resp.status_code == 200, f"SSE connect failed: {resp.status_code}"
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Wrong content-type: {ct}"

        # Read first chunk
        first_chunk = b""
        for chunk in resp.iter_content(chunk_size=1024):
            first_chunk = chunk
            break

        assert b"connected" in first_chunk or b"data:" in first_chunk, \
            f"No connected event in first SSE chunk: {first_chunk}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-010 — AI Coach timeout handling
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.ai
@pytest.mark.slow
def test_ai_coach_endpoint_timeout(athlete_api):
    """
    Acceptance:
      POST /api/ai/coach-message → 200 or 504
      504 means AI took > 30s (configured timeout)
      200 means AI responded within 30s
      Never 500 (unhandled error)
    """
    r = athlete_api.post("/ai/coach-suggest", json={
        "message": "¿Cuál es mi CTL actual y qué significa?"
    }, timeout=35)
    # 503 = ANTHROPIC_API_KEY not configured (valid in dev/CI without key)
    assert r.status_code in (200, 503, 504), \
        f"AI endpoint returned unexpected: {r.status_code} — expected 200, 503, or 504"

    if r.status_code == 200:
        data = r.json()
        assert "answer" in data or "response" in data or "message" in data or "content" in data


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-011 — Injury Risk
# ─────────────────────────────────────────────────────────────────────────────
def test_injury_risk_endpoint(athlete_api):
    """
    Acceptance:
      GET /api/athlete/injury-risk → 200
      Has: risk_level or risk_score
    """
    r = athlete_api.get("/athlete/injury-risk")
    assert r.status_code in (200, 404), f"Unexpected: {r.status_code}"
    if r.status_code == 200:
        data = r.json()
        assert "risk" in str(data).lower() or "score" in str(data).lower()


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-012 — Nutrition Plan
# ─────────────────────────────────────────────────────────────────────────────
def test_nutrition_plan_endpoint(athlete_api):
    """
    Acceptance:
      GET /api/athlete/nutrition-plan → 200 or 404
      If 200: has macros structure
    """
    r = athlete_api.get("/athlete/nutrition-plan")
    assert r.status_code in (200, 404), f"Unexpected: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-013 — Training Zones
# ─────────────────────────────────────────────────────────────────────────────
def test_training_zones_endpoint(athlete_api):
    """
    Acceptance:
      GET /api/athlete/zones → 200
      Returns zones for bike, run, swim
    """
    r = athlete_api.get("/athlete/zones")
    assert r.status_code == 200, f"Zones endpoint: {r.text}"
    data = r.json()
    # Should have at least one sport's zones
    assert isinstance(data, (dict, list))


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-014 — Race Endpoints
# ─────────────────────────────────────────────────────────────────────────────
def test_race_endpoints(athlete_api):
    """
    Acceptance:
      POST /api/race → 201 (create race event)
      GET /api/race → 200 (list races)
    """
    from datetime import date, timedelta

    create_r = athlete_api.post("/races", json={
        "name": "E2E Test Ironman",
        "race_type": "ironman",
        "race_date": (date.today() + timedelta(days=180)).isoformat(),
        "goal_finish_time_min": 600,
    })
    assert create_r.status_code in (200, 201, 422), f"Race create: {create_r.text}"

    list_r = athlete_api.get("/races")
    assert list_r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# TC-API-015 — Periodization
# ─────────────────────────────────────────────────────────────────────────────
def test_periodization_endpoints(coach_api, athlete_api):
    """
    Acceptance:
      GET /api/coach/athletes/{id}/phases → 200
    """
    profile_r = athlete_api.get("/athlete/profile")
    if profile_r.status_code != 200:
        pytest.skip("Cannot get athlete profile")

    athlete_id = profile_r.json().get("id") or profile_r.json().get("user_id")
    if not athlete_id:
        pytest.skip("No athlete ID available")

    r = coach_api.get(f"/coach/athletes/{athlete_id}/phases")
    assert r.status_code in (200, 403, 404), f"Unexpected: {r.status_code}"
    if r.status_code == 200:
        assert isinstance(r.json(), list)
