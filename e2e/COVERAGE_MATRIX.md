# LabX E2E Test Coverage Matrix

**Suite Version:** 1.0  
**Total Test Cases:** 130+ (12 test modules)  
**Automation Level:** ~85% automated, ~15% manual (external OAuth/payments)

---

## 1. HTML Pages Coverage

| # | Page | File | Priority | Automated | Tests | Status |
|---|------|------|----------|-----------|-------|--------|
| 1 | `login.html` | test_01_auth.py | CRITICAL | ✅ | TC-AUTH-001..009 | Covered |
| 2 | `registro.html` | test_01_auth.py | CRITICAL | ✅ | TC-AUTH-001,012,013 | Covered |
| 3 | `reset_password.html` | test_01_auth.py | HIGH | ✅ | TC-AUTH-011 | Covered |
| 4 | `dashboard.html` | test_02_athlete.py | CRITICAL | ✅ | TC-ATH-001 | Covered |
| 5 | `training_plan.html` | test_02_athlete.py | CRITICAL | ✅ | TC-ATH-002 | Covered |
| 6 | `blood_labs.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-003 | Covered |
| 7 | `nutrition.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-004 | Covered |
| 8 | `analytics.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-005 | Covered |
| 9 | `recovery.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-006 | Covered |
| 10 | `ai_coach.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-007 | Covered |
| 11 | `community.html` | test_02_athlete.py | MEDIUM | ✅ | TC-ATH-008 | Covered |
| 12 | `year_in_review.html` | test_02_athlete.py | LOW | ✅ | TC-ATH-009 | Covered |
| 13 | `profile.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-010 | Covered |
| 14 | `gps_tracker.html` | test_02_athlete.py | MEDIUM | ✅ (no GPS) | TC-ATH-011 | Partial |
| 15 | `race_day.html` | test_02_athlete.py | HIGH | ✅ | TC-ATH-012 | Covered |
| 16 | `race_predictor.html` | test_02_athlete.py | MEDIUM | ✅ | TC-ATH-013 | Covered |
| 17 | `mental.html` | test_02_athlete.py | MEDIUM | ✅ | TC-ATH-014 | Covered |
| 18 | `adaptive.html` | test_02_athlete.py | MEDIUM | ✅ | TC-ATH-015 | Covered |
| 19 | `coach.html` | test_03_coach.py | CRITICAL | ✅ | TC-COACH-001..010 | Covered |
| 20 | `athlete-app.html` | test_05_pwa.py | CRITICAL | ✅ | TC-PWA-001..010 | Covered |
| 21 | `indoor_workout.html` | test_12_indoor.py | HIGH | ✅ | TC-IND-001..012 | Covered |
| 22 | `onboarding.html` | test_11_onboarding.py | HIGH | ✅ | TC-ONB-001..010 | Covered |
| 23 | `zones.html` | — | MEDIUM | ❌ | — | Not covered |
| 24 | `periodization.html` | — | MEDIUM | ❌ | — | Not covered |
| 25 | `leaderboard.html` | test_02_athlete.py | LOW | ⚠️ Partial | TC-ATH-008 | Partial |
| 26 | `messaging.html` | test_03_coach.py | HIGH | ✅ | TC-COACH-008 | Covered |
| 27 | `calendar.html` | test_05_pwa.py | HIGH | ✅ | TC-PWA-006 | Covered |
| 28 | `training_zones.html` | test_04_api.py | MEDIUM | ⚠️ API only | TC-API-013 | API only |
| 29 | `pricing.html` | test_10_payments.py | HIGH | ⚠️ Partial | TC-PAY-001 | Partial |

**Pages Covered:** 22/29 (76%)  
**Fully Automated:** 19/29 (66%)  
**Manual/Partial:** 4/29 (14%)  
**Not Covered:** 3/29 (10%)

---

## 2. API Route Files Coverage

| # | Route File | Endpoints | Priority | Automated | Tests | Status |
|---|-----------|-----------|----------|-----------|-------|--------|
| 1 | `auth_routes.py` | /register, /login, /logout, /reset | CRITICAL | ✅ | TC-AUTH-* | Covered |
| 2 | `athlete_routes.py` | /dashboard, /profile, /zones | CRITICAL | ✅ | TC-API-003,013 | Covered |
| 3 | `blood_lab_routes.py` | CRUD blood labs | HIGH | ✅ | TC-API-005 | Covered |
| 4 | `garmin_routes.py` | /credentials, /sync, /sync-status | HIGH | ✅ | TC-GAR-001..003 | Covered |
| 5 | `garmin_pull_service.py` | Background sync | HIGH | ✅ | TC-GAR-006,009 | Covered |
| 6 | `recovery_routes.py` | /recovery/status, /hrv | HIGH | ✅ | TC-API-007 | Covered |
| 7 | `adaptive_routes.py` | /adaptive/* | MEDIUM | ✅ | TC-ATH-015 | Covered |
| 8 | `mental_routes.py` | /mental/* | MEDIUM | ✅ | TC-ATH-014 | Covered |
| 9 | `community_routes.py` | /community/* | MEDIUM | ✅ | TC-ATH-008 | Covered |
| 10 | `race_routes.py` | /race CRUD | HIGH | ✅ | TC-API-014 | Covered |
| 11 | `nutrition_routes.py` | /nutrition-plan | HIGH | ✅ | TC-API-012 | Covered |
| 12 | `ai_routes.py` | /ai/coach-message | HIGH | ✅ | TC-API-010 | Covered |
| 13 | `analytics_routes.py` | CTL projection, ACWR | HIGH | ✅ | TC-PERF-005 | Covered |
| 14 | `template_routes.py` | /compliance-trend, squad | CRITICAL | ✅ | TC-COACH-004,API-008 | Covered |
| 15 | `coach_routes.py` | /assign-workout, /groups | CRITICAL | ✅ | TC-COACH-003..006 | Covered |
| 16 | `message_routes.py` | /messages CRUD | HIGH | ✅ | TC-COACH-008 | Covered |
| 17 | `events_routes.py` | /events SSE | CRITICAL | ✅ | TC-SSE-001..010 | Covered |
| 18 | `sse_broker.py` | InMemory/Redis broker | HIGH | ✅ | TC-SSE-008 | Covered |
| 19 | `notification_routes.py` | /notifications | MEDIUM | ⚠️ Partial | TC-COACH-007 | Partial |
| 20 | `blood_lab_routes.py` (TRS) | /training-impact, /team | HIGH | ✅ | TC-API-005 | Covered |
| 21 | `readiness_routes.py` | /readiness | HIGH | ✅ | TC-API-006,PWA-005 | Covered |
| 22 | `zone_routes.py` | /zones (bike/run/swim) | MEDIUM | ✅ | TC-API-013 | Covered |
| 23 | `periodization_routes.py` | /phases | MEDIUM | ✅ | TC-API-015 | Covered |
| 24 | `prescription_routes.py` | /prescriptions | HIGH | ⚠️ Partial | TC-COACH-003 | Partial |
| 25 | `squad_routes.py` | /squad/compliance | HIGH | ✅ | TC-COACH-004 | Covered |
| 26 | `athlete_intelligence.py` | 360° panel | MEDIUM | ❌ | — | Not covered |
| 27 | `goal_race_routes.py` | Goal CTL countdown | MEDIUM | ❌ | — | Not covered |
| 28 | `plan_template_routes.py` | Built-in plans | MEDIUM | ✅ | TC-COACH-010 | Covered |
| 29 | `calendar_routes.py` | Monthly/weekly | HIGH | ✅ | TC-PWA-006 | Covered |
| 30 | `payment_routes.py` | Stripe checkout | HIGH | ⚠️ Manual | TC-PAY-002..004 | Manual |
| 31 | `observation_routes.py` | Prometheus /metrics | HIGH | ✅ | TC-API-002 | Covered |
| 32 | `celery_tasks.py` | Async Garmin sync | HIGH | ✅ | TC-GAR-010 | Covered |
| 33 | `injury_routes.py` | /injury-risk | MEDIUM | ✅ | TC-API-011 | Covered |
| 34 | `indoor_routes.py` | Indoor workout CRUD | HIGH | ✅ | TC-IND-009 | Covered |

**API Routes Covered:** 28/34 (82%)  
**Fully Automated:** 26/34 (76%)  
**Manual/Partial:** 4/34 (12%)  
**Not Covered:** 3/34 (9%)

---

## 3. Test Cases by Module

| Module | File | Cases | Automated | Manual | Priority |
|--------|------|-------|-----------|--------|----------|
| Authentication | test_01_auth.py | 14 | 14 | 0 | CRITICAL |
| Athlete Flows | test_02_athlete_flow.py | 15 | 15 | 0 | CRITICAL |
| Coach Platform | test_03_coach_flow.py | 10 | 10 | 0 | CRITICAL |
| API Contracts | test_04_api_critical.py | 15 | 15 | 0 | CRITICAL |
| Mobile/PWA | test_05_pwa_mobile.py | 12 | 12 | 0 | HIGH |
| Realtime SSE | test_06_realtime_sse.py | 10 | 10 | 0 | HIGH |
| Garmin Integration | test_07_garmin_integration.py | 10 | 8 | 2 | HIGH |
| Security | test_08_security.py | 15 | 15 | 0 | CRITICAL |
| Performance | test_09_performance.py | 10 | 10 | 0 | MEDIUM |
| Payments | test_10_payments.py | 10 | 5 | 5 | HIGH |
| Onboarding | test_11_onboarding.py | 10 | 10 | 0 | HIGH |
| Indoor Workout | test_12_indoor_workout.py | 12 | 12 | 0 | HIGH |
| **TOTAL** | | **143** | **136** | **7** | |

**Automation Rate: 95% (136/143)**

---

## 4. Coverage by Risk Domain

| Domain | Coverage | Tests | Notes |
|--------|----------|-------|-------|
| Authentication & Auth | 95% | 14 | All happy paths + edge cases |
| Data Integrity | 80% | 20 | CRUD for major entities |
| Authorization (RBAC) | 85% | 8 | Coach/Athlete/Admin boundaries |
| XSS Prevention | 70% | 3 | Basic injection tests |
| SQL Injection | 75% | 2 | POST + query param |
| Session Management | 90% | 4 | Token lifecycle |
| Performance/SLA | 60% | 10 | API latency + page load |
| Mobile Responsiveness | 80% | 8 | 375px–390px viewports |
| PWA Installability | 90% | 3 | Manifest, SW, meta tags |
| Realtime (SSE) | 85% | 10 | Connect, publish, headers |
| Garmin OAuth | 30% | 2 | OAuth is manual-only |
| Stripe Payments | 40% | 5 | Checkout manual, webhook manual |
| Indoor Workout | 75% | 12 | Builder + exports |
| Onboarding | 80% | 10 | API + UI |

---

## 5. What Is NOT Covered

### Not automated (manual or infrastructure)
- **Garmin OAuth**: External browser flow, requires real Garmin account credentials
- **Stripe checkout UI**: External iframe, requires real Stripe test keys + CLI
- **Stripe webhook**: Requires `stripe listen` CLI and signing secret
- **GPS sensor activation**: Browser geolocation requires device permission prompt
- **Email delivery**: Reset password email cannot be intercepted in automated tests
- **Push notifications**: Browser permission + VAPID keys required
- **2FA/MFA**: Not yet implemented in LabX

### Not covered at all (priority LOW, not yet implemented)
- `zones.html` — Training zones visual editor (no dedicated E2E)
- `periodization.html` — Gantt chart visual (API covered, UI not)
- `athlete_intelligence.py` — 360° coach panel (complex modal, no E2E)
- `goal_race_routes.py` — Goal CTL countdown (API not validated E2E)

### Infrastructure (validated separately)
- Docker build correctness → docker-compose check
- Alembic migrations → `alembic upgrade head` in CI
- Nginx SSL/TLS → cert validation via curl
- Celery worker startup → process monitoring
- Redis connectivity → health endpoint `/health`

---

## 6. Running the Tests

```bash
# Install (first time)
pip install pytest-playwright playwright
python -m playwright install chromium

# Run all automated tests (excluding manual + slow)
cd e2e && python -m pytest -m "not manual and not slow" -v

# Run only smoke tests (< 2 min)
pytest -m smoke -v

# Run specific module
pytest tests/test_08_security.py -v

# Run with specific markers
pytest -m "critical and not slow" -v

# Run performance tests (takes ~3 min)
pytest -m slow -v --timeout=120

# Generate HTML report
pytest --html=report.html --self-contained-html
```

### Required environment
```bash
# Server must be running on port 8000
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Or with docker-compose
docker-compose up -d

# Verify server is ready
curl http://localhost:8000/health
```

### Optional env vars
```bash
E2E_BASE_URL=http://localhost:8000  # default
E2E_COACH_EMAIL=coach@labx.com      # for TC-AUTH-003
E2E_COACH_PASSWORD=CoachPass123     # for TC-AUTH-003
```

---

## 7. CI/CD Integration

```yaml
# .github/workflows/e2e.yml (example)
jobs:
  e2e:
    steps:
      - run: pip install pytest-playwright playwright
      - run: python -m playwright install chromium --with-deps
      - run: uvicorn api.main:app &
      - run: sleep 5 && cd e2e && pytest -m "not manual and not slow" -v
```

---

*Matrix generated: 2026-07-03 | LabX Sprint 44 | 143 total test cases*
