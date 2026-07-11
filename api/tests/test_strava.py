"""S10 — Tests para Strava OAuth routes."""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET",   "test-secret-key-labx-tests")
os.environ.setdefault("APP_ENV",      "test")
os.environ.setdefault("STRAVA_CLIENT_ID",     "test_client_id")
os.environ.setdefault("STRAVA_CLIENT_SECRET", "test_client_secret")

from .conftest import auth_headers, login


class TestStravaStatus:
    def test_status_unauthenticated(self, client):
        r = client.get("/api/strava/status")
        assert r.status_code == 401

    def test_status_not_connected(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/strava/status", headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is False
        assert data["athlete_id"] is None

    def test_status_connected(self, client, athlete_user, db):
        athlete_user.strava_athlete_id = "98765"
        athlete_user.strava_access_token = "gAAtest"
        db.commit()
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/strava/status", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()["connected"] is True
        assert r.json()["athlete_id"] == "98765"


class TestStravaDisconnect:
    def test_disconnect_not_connected(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.delete("/api/strava/disconnect", headers=auth_headers(token))
        assert r.status_code == 400

    def test_disconnect_clears_tokens(self, client, athlete_user, db):
        athlete_user.strava_athlete_id   = "12345"
        athlete_user.strava_access_token = "gAAtoken"
        db.commit()
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.delete("/api/strava/disconnect", headers=auth_headers(token))
        assert r.status_code == 200
        db.refresh(athlete_user)
        assert athlete_user.strava_access_token is None
        assert athlete_user.strava_athlete_id   is None


class TestStravaConnect:
    def test_connect_redirect(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/strava/connect",
                       headers=auth_headers(token),
                       follow_redirects=False)
        # Debe redirigir a Strava o lanzar 503 si STRAVA_CLIENT_ID es test
        assert r.status_code in (302, 307, 503)
