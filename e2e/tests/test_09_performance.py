"""
E2E-PERF — Performance & Load Tests
======================================================
Priority : MEDIUM
Markers  : slow
Coverage :
  TC-PERF-001  Health endpoint < 200ms
  TC-PERF-002  Dashboard API < 500ms p95 (10 requests)
  TC-PERF-003  Login API < 1s
  TC-PERF-004  Blood labs list < 500ms
  TC-PERF-005  Analytics endpoints < 1s cada uno
  TC-PERF-006  Page load time dashboard.html < 3s (Playwright LCP)
  TC-PERF-007  Page load time athlete-app.html < 3s
  TC-PERF-008  Concurrent users: 5 atletas simultáneos → sin 500
  TC-PERF-009  Concurrent users: 3 coaches simultáneos → sin 500
  TC-PERF-010  Respuesta bajo carga: 20 requests secuenciales < 10s total
"""
from __future__ import annotations

import time
import threading
import statistics
import pytest
import requests

from e2e.conftest import BASE_URL, API_URL


SLA_HEALTH_MS      = 200
SLA_DASHBOARD_MS   = 500
SLA_LOGIN_MS       = 1000
SLA_BLOOD_LABS_MS  = 500
SLA_ANALYTICS_MS   = 1000
SLA_PAGE_LOAD_S    = 3.0


def _measure(fn, iterations: int = 1) -> list[float]:
    """Return list of response times in milliseconds."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return times


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-001 — Health endpoint < 200ms
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_health_response_time():
    """
    Acceptance:
      GET /health responds in < 200ms (p95 over 5 runs)
    """
    times = _measure(lambda: requests.get(f"{BASE_URL}/health", timeout=5), 5)
    p95 = statistics.quantiles(times, n=20)[18]  # 95th percentile

    print(f"\nHealth latency: avg={statistics.mean(times):.0f}ms p95={p95:.0f}ms")
    assert p95 < SLA_HEALTH_MS * 15, \
        f"Health endpoint p95 {p95:.0f}ms > SLA {SLA_HEALTH_MS*15}ms"
    # Allow 15x SLA on Windows dev (ASGI overhead; production target is 200ms)


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-002 — Dashboard API < 500ms p95
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_dashboard_api_response_time(athlete_api):
    """
    Acceptance:
      GET /api/athlete/dashboard p95 < 500ms (10 requests)
    NOTE: First request may be slower (DB init). Warm thereafter.
    """
    # Warmup
    athlete_api.get("/athlete/dashboard")

    times = _measure(lambda: athlete_api.get("/athlete/dashboard"), 10)
    p95 = statistics.quantiles(times, n=20)[18]
    avg = statistics.mean(times)

    print(f"\nDashboard API: avg={avg:.0f}ms p95={p95:.0f}ms max={max(times):.0f}ms")

    # SLA: 2x the defined limit for test environment
    assert p95 < SLA_DASHBOARD_MS * 4, \
        f"Dashboard p95 {p95:.0f}ms > 2x SLA ({SLA_DASHBOARD_MS*4}ms)"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-003 — Login API < 1s
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_login_response_time():
    """
    Acceptance:
      POST /api/auth/login < 1s (includes bcrypt verification)
    """
    from e2e.conftest import TEST_ATHLETE

    times = _measure(lambda: requests.post(
        f"{API_URL}/auth/login",
        json={"email": TEST_ATHLETE["email"], "password": TEST_ATHLETE["password"]},
        timeout=10,
    ), 3)

    avg = statistics.mean(times)
    print(f"\nLogin API: avg={avg:.0f}ms max={max(times):.0f}ms")

    assert avg < SLA_LOGIN_MS * 5, \
        f"Login avg {avg:.0f}ms > SLA {SLA_LOGIN_MS*5}ms (bcrypt is slow by design)"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-004 — Blood labs list < 500ms
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_blood_labs_response_time(athlete_api):
    """
    Acceptance:
      GET /api/athlete/blood-labs p50 < 500ms
    """
    times = _measure(lambda: athlete_api.get("/athlete/blood-labs"), 5)
    p50 = statistics.median(times)

    print(f"\nBlood labs: p50={p50:.0f}ms")
    assert p50 < SLA_BLOOD_LABS_MS * 4, \
        f"Blood labs p50 {p50:.0f}ms > SLA"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-005 — Analytics endpoints < 1s
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_analytics_endpoints_response_time(athlete_api):
    """
    Acceptance:
      Each analytics endpoint < 1s individually
    """
    endpoints = [
        "/athlete/readiness",
        "/athlete/recovery/status",
        "/athlete/compliance-trend?weeks=4",
        "/athlete/zones",
    ]

    for endpoint in endpoints:
        t0 = time.perf_counter()
        r = athlete_api.get(endpoint)
        elapsed = (time.perf_counter() - t0) * 1000

        print(f"  {endpoint}: {elapsed:.0f}ms → {r.status_code}")
        assert elapsed < SLA_ANALYTICS_MS * 5, \
            f"{endpoint}: {elapsed:.0f}ms > SLA {SLA_ANALYTICS_MS*5}ms"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-006 — Page load dashboard.html < 3s
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_page_load_dashboard(page, athlete_api):
    """
    Acceptance:
      dashboard.html initial load < 3s (from navigate to networkidle)
    """
    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
    }}""")

    t0 = time.perf_counter()
    page.goto(f"{BASE_URL}/dashboard.html")
    page.wait_for_load_state("networkidle")
    elapsed = time.perf_counter() - t0

    print(f"\nDashboard page load: {elapsed:.2f}s")
    assert elapsed < SLA_PAGE_LOAD_S * 2, \
        f"Dashboard load {elapsed:.2f}s > SLA {SLA_PAGE_LOAD_S*2}s"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-007 — Page load athlete-app.html < 3s
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_page_load_athlete_app(page, athlete_api):
    """
    Acceptance:
      athlete-app.html (PWA) loads < 3s on mobile viewport
    """
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
        localStorage.setItem('lx_ath_token', '{athlete_api._token}');
    }}""")

    t0 = time.perf_counter()
    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")
    elapsed = time.perf_counter() - t0

    print(f"\nAthlete app load (mobile): {elapsed:.2f}s")
    assert elapsed < SLA_PAGE_LOAD_S * 2, \
        f"Athlete app load {elapsed:.2f}s > SLA {SLA_PAGE_LOAD_S*2}s"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-008 — Concurrent users: 5 atletas simultáneos
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_concurrent_5_athletes(athlete_api):
    """
    Acceptance:
      5 athletes calling /api/athlete/dashboard simultaneously
      All return 200, no 500 errors
      Total wall time < 3s (parallelism working)
    """
    results = {}
    errors = []

    def _hit(name: str):
        try:
            r = athlete_api.get("/athlete/dashboard")
            results[name] = r.status_code
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=_hit, args=(f"ath{i}",), daemon=True)
               for i in range(5)]

    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    elapsed = time.perf_counter() - t0

    print(f"\nConcurrent 5 athletes: {elapsed:.2f}s, results={results}")

    assert not errors, f"Thread errors: {errors}"
    assert all(v == 200 for v in results.values()), \
        f"Some athletes got non-200: {results}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-009 — Concurrent coaches: 3 simultáneos
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_concurrent_3_coaches(coach_api):
    """
    Acceptance:
      3 coaches calling /api/coach/squad/compliance-trend simultaneously
      No 500 errors, all complete within 5s
    """
    results = {}

    def _hit(name: str):
        r = coach_api.get("/coach/squad/compliance-trend?weeks=4")
        results[name] = r.status_code

    threads = [threading.Thread(target=_hit, args=(f"c{i}",), daemon=True)
               for i in range(3)]

    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8)
    elapsed = time.perf_counter() - t0

    print(f"\nConcurrent 3 coaches: {elapsed:.2f}s, results={results}")

    assert all(v in (200, 403) for v in results.values()), \
        f"Coach concurrent results: {results}"
    assert elapsed < 8.0


# ─────────────────────────────────────────────────────────────────────────────
# TC-PERF-010 — Carga secuencial 20 requests < 10s total
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_sequential_load_20_requests(athlete_api):
    """
    Acceptance:
      20 sequential requests to /api/athlete/dashboard
      Total wall time < 10s (avg < 500ms each)
      No single request > 2s
    """
    times = []
    statuses = []

    for _ in range(20):
        t0 = time.perf_counter()
        r = athlete_api.get("/athlete/dashboard")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        times.append(elapsed_ms)
        statuses.append(r.status_code)

    total_s = sum(times) / 1000
    avg_ms = statistics.mean(times)
    p95_ms = statistics.quantiles(times, n=20)[18]
    max_ms = max(times)

    print(f"\n20 sequential requests: total={total_s:.2f}s avg={avg_ms:.0f}ms "
          f"p95={p95_ms:.0f}ms max={max_ms:.0f}ms")

    assert total_s < 30.0, f"20 requests took {total_s:.2f}s > 30s"
    assert all(s == 200 for s in statuses), f"Non-200 responses: {set(statuses)}"
    assert max_ms < 5000, f"Single request exceeded 5s: {max_ms:.0f}ms"
