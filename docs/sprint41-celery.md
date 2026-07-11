# Sprint 41 — Celery + Async AI + Docker Compose Override

**Roadmap items:** R-07 (Celery Garmin sync), R-08 (AI async timeout), R-09 (docker-compose local dev)

## Summary

Three infrastructure items delivered in one sprint:

1. **Celery worker** (`api/worker.py`, `api/tasks/garmin_tasks.py`) — async Garmin sync task queue
2. **Async AI endpoint** (`api/routes/ai_routes.py`) — non-blocking AI with 30s timeout
3. **docker-compose.override.yml** — zero-config local dev with PostgreSQL + Redis + worker

## Files Changed

| File | Change |
|------|--------|
| `api/worker.py` | Celery app definition, `task_always_eager=True` in test env |
| `api/tasks/__init__.py` | Package init |
| `api/tasks/garmin_tasks.py` | `sync_garmin_user` Celery task (max_retries=2, soft_time_limit=300) |
| `api/garmin_pull_service.py` | Added `dispatch_garmin_sync()` — Celery→BackgroundTask→skipped dispatch chain |
| `api/routes/auth_routes.py` | Login now calls `dispatch_garmin_sync()` |
| `api/routes/athlete_routes.py` | Force-sync now calls `dispatch_garmin_sync()` |
| `api/routes/ai_routes.py` | `coach_suggest` → `async def`, `AsyncAnthropic`, `asyncio.wait_for(30s)` |
| `docker-compose.override.yml` | New file: db+redis no-profile, celery worker service |
| `requirements-api.txt` | Created; includes `celery[redis]>=5.3.0` |

## Design Decisions

### Single dispatch point
`dispatch_garmin_sync(user_id, background_tasks=None, force=False)` is the only call site for Garmin sync dispatch. It tries Celery when Redis is reachable, falls back to FastAPI `BackgroundTasks`, returns `"skipped"` if neither is available.

### Test isolation
`task_always_eager = os.getenv("APP_ENV") == "test"` — tasks execute synchronously in the calling thread when `APP_ENV=test`. No broker required in CI.

### AI timeout without changing API contract
Rather than switching to 202+polling (which would require frontend changes), `coach_suggest` was converted to `async def` with `asyncio.wait_for(timeout=AI_TIMEOUT_SECONDS)`. Returns HTTP 504 on timeout. `AI_TIMEOUT_SECONDS` env var defaults to 30.

### docker-compose.override.yml
Auto-merged by Docker Compose. Overrides `db` and `redis` profiles from `["prod"]` to `[]` (always active), adds `worker` service. `docker compose up` now starts everything locally without flags.

## Environment Variables

| Var | Default | Purpose |
|-----|---------|---------|
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and backend |
| `AI_TIMEOUT_SECONDS` | `30` | AsyncAnthropic timeout |
| `APP_ENV` | (none) | Set to `test` for eager tasks |

## Test Results

- Sprint 41 tests: 20/20 (`api/tests/test_sprint41_celery.py`)
- Full suite: **1713 passed**
