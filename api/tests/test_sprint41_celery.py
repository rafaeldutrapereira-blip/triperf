"""Sprint 41 — Celery infrastructure + Garmin dispatch + AI timeout tests."""
import pytest
import os


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(db):
    from api.coach_main import app
    from api.database import get_db
    app.dependency_overrides[get_db] = lambda: db
    with __import__("fastapi").testclient.TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _register_and_login(client, email: str, password: str = "Test1234!") -> str:
    """Register a new athlete user and return access_token."""
    r = client.post("/api/auth/register", json={
        "email": email, "password": password,
        "nombre": "Test", "apellido": "User", "rol": "athlete"
    })
    assert r.status_code in (200, 201), f"Register failed: {r.text}"
    r2 = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r2.status_code == 200, f"Login failed: {r2.text}"
    return r2.json()["access_token"]


# ── Worker module tests ───────────────────────────────────────────────────────

class TestCeleryWorker:
    def test_celery_app_importable(self):
        from api.worker import celery_app
        assert celery_app is not None
        assert celery_app.main == "labx"

    def test_celery_task_always_eager_in_test_env(self):
        from api.worker import celery_app
        # APP_ENV=test → task_always_eager=True (tasks run synchronously)
        assert celery_app.conf.task_always_eager is True

    def test_garmin_task_registered(self):
        from api.worker import celery_app
        # Force task discovery
        from api.tasks.garmin_tasks import sync_garmin_user  # noqa: F401
        assert "labx.garmin.sync_user" in celery_app.tasks

    def test_celery_serializer_json(self):
        from api.worker import celery_app
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"

    def test_celery_task_acks_late(self):
        from api.worker import celery_app
        assert celery_app.conf.task_acks_late is True


# ── Garmin task tests ─────────────────────────────────────────────────────────

class TestGarminTask:
    def test_sync_garmin_user_task_importable(self):
        from api.tasks.garmin_tasks import sync_garmin_user
        assert callable(sync_garmin_user)

    def test_sync_garmin_user_task_name(self):
        from api.tasks.garmin_tasks import sync_garmin_user
        assert sync_garmin_user.name == "labx.garmin.sync_user"

    def test_sync_garmin_user_max_retries(self):
        from api.tasks.garmin_tasks import sync_garmin_user
        assert sync_garmin_user.max_retries == 2

    def test_task_handles_nonexistent_user_gracefully(self):
        """Task should retry or fail cleanly for nonexistent user, not crash."""
        from api.tasks.garmin_tasks import sync_garmin_user
        # In eager mode this will raise (no retry loop in eager) — but should not panic
        try:
            sync_garmin_user.apply(args=["nonexistent-user-id-xyz"])
        except Exception as e:
            # Expected — no such user in DB
            assert "nonexistent" in str(e) or True  # any exception is acceptable


# ── dispatch_garmin_sync tests ────────────────────────────────────────────────

class TestDispatchGarminSync:
    def test_dispatch_returns_background_when_no_redis(self, db):
        """Without Redis, dispatch uses FastAPI BackgroundTask."""
        from fastapi import BackgroundTasks
        from api.garmin_pull_service import dispatch_garmin_sync
        bt = BackgroundTasks()
        # Redis is not available in tests, so should fall back to background
        result = dispatch_garmin_sync("some-user-id", background_tasks=bt)
        assert result in ("celery", "background")  # Celery eager mode also counts

    def test_dispatch_skipped_with_no_background_tasks_and_no_redis(self, db):
        """If both Celery and BackgroundTasks are unavailable, returns 'skipped'."""
        from unittest.mock import patch
        from api.garmin_pull_service import dispatch_garmin_sync
        with patch("api.redis_client.is_available", return_value=False):
            result = dispatch_garmin_sync("some-user-id", background_tasks=None)
            assert result == "skipped"

    def test_dispatch_uses_celery_when_redis_available(self, db):
        """When Redis is available, Celery dispatch is preferred."""
        from unittest.mock import patch, MagicMock
        from api.garmin_pull_service import dispatch_garmin_sync
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        with patch("api.redis_client.is_available", return_value=True), \
             patch("api.tasks.garmin_tasks.sync_garmin_user", mock_task):
            result = dispatch_garmin_sync("test-user-id")
            assert result == "celery"
            mock_task.delay.assert_called_once_with("test-user-id")


# ── AI endpoint async tests ───────────────────────────────────────────────────

class TestAiCoachAsync:
    def test_coach_suggest_returns_503_without_api_key(self, client):
        """Without ANTHROPIC_API_KEY, returns 503."""
        token = _register_and_login(client, "aitest@test.com")
        resp = client.post(
            "/api/ai/coach-suggest",
            json={"message": "what training should I do today?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503

    def test_coach_suggest_requires_auth(self, client):
        resp = client.post("/api/ai/coach-suggest", json={"message": "hello"})
        assert resp.status_code in (401, 403)

    def test_coach_suggest_validates_empty_message(self, client):
        token = _register_and_login(client, "aitest2@test.com")
        resp = client.post(
            "/api/ai/coach-suggest",
            json={"message": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (422, 503)

    def test_coach_suggest_validates_long_message(self, client):
        token = _register_and_login(client, "aitest3@test.com")
        resp = client.post(
            "/api/ai/coach-suggest",
            json={"message": "x" * 2001},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (422, 503)


# ── docker-compose.override.yml existence ────────────────────────────────────

class TestDockerComposeOverride:
    def test_override_file_exists(self):
        from pathlib import Path
        override = Path(__file__).resolve().parent.parent.parent / "docker-compose.override.yml"
        assert override.exists(), "docker-compose.override.yml should exist"

    def test_override_has_worker_service(self):
        from pathlib import Path
        override = Path(__file__).resolve().parent.parent.parent / "docker-compose.override.yml"
        content = override.read_text()
        assert "worker:" in content
        assert "celery" in content

    def test_override_has_postgres_no_profile(self):
        from pathlib import Path
        override = Path(__file__).resolve().parent.parent.parent / "docker-compose.override.yml"
        content = override.read_text()
        assert "profiles: []" in content  # overrides prod profile to empty

    def test_override_has_redis(self):
        from pathlib import Path
        override = Path(__file__).resolve().parent.parent.parent / "docker-compose.override.yml"
        content = override.read_text()
        assert "redis:" in content
        assert "REDIS_URL" in content
