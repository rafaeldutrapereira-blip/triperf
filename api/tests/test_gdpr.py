"""
Tests — Sprint 37 GDPR: Data Export (Art. 20) & Account Deletion (Art. 17)
"""
import pytest
from .conftest import login


@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /athlete/me/export
# ─────────────────────────────────────────────────────────────────────────────

class TestGdprExport:
    def test_export_requires_auth(self, client):
        r = client.get("/api/athlete/me/export")
        assert r.status_code == 401

    def test_export_returns_200(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        assert r.status_code == 200

    def test_export_has_required_top_level_keys(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        data = r.json()
        required = {
            "export_date", "profile", "activities", "wellness_logs",
            "blood_lab_exams", "food_diary", "workout_logs",
            "assigned_workouts", "notes_from_coach", "messages",
        }
        for key in required:
            assert key in data, f"Missing key: {key}"

    def test_export_profile_has_id_and_email(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        profile = r.json()["profile"]
        assert "id" in profile
        assert "email" in profile
        assert profile["email"] == "athlete@test.com"

    def test_export_profile_omits_credentials(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        profile = r.json()["profile"]
        sensitive = ("password_hash", "totp_secret", "totp_backup_hash",
                     "garmin_password", "strava_access_token",
                     "strava_refresh_token", "last_device_hash")
        for field in sensitive:
            assert field not in profile, f"Sensitive field exposed: {field}"

    def test_export_collections_are_lists(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        data = r.json()
        list_keys = ("activities", "wellness_logs", "blood_lab_exams",
                     "food_diary", "workout_logs", "assigned_workouts",
                     "notes_from_coach", "messages")
        for key in list_keys:
            assert isinstance(data[key], list), f"{key} should be a list"

    def test_export_empty_collections_for_new_user(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        data = r.json()
        assert data["activities"] == []
        assert data["wellness_logs"] == []
        assert data["blood_lab_exams"] == []

    def test_export_includes_export_date_iso(self, client, auth_headers):
        r = client.get("/api/athlete/me/export", headers=auth_headers)
        export_date = r.json()["export_date"]
        assert isinstance(export_date, str)
        assert "T" in export_date  # ISO format with time component


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /athlete/me
# ─────────────────────────────────────────────────────────────────────────────

class TestGdprDelete:
    def test_delete_requires_auth(self, client):
        r = client.delete("/api/athlete/me")
        assert r.status_code == 401

    def test_delete_returns_200(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()
        r = client.delete("/api/athlete/me",
                          headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_delete_anonymizes_name(self, client, db, athlete_user):
        from api.models import User
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()
        client.delete("/api/athlete/me",
                      headers={"Authorization": f"Bearer {token}"})
        u = db.query(User).filter(User.id == athlete_user.id).first()
        db.refresh(u)
        assert u.nombre == "Deleted User"

    def test_delete_anonymizes_email(self, client, db, athlete_user):
        from api.models import User
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()
        client.delete("/api/athlete/me",
                      headers={"Authorization": f"Bearer {token}"})
        u = db.query(User).filter(User.id == athlete_user.id).first()
        db.refresh(u)
        assert "@deleted.invalid" in u.email

    def test_delete_sets_activo_false(self, client, db, athlete_user):
        from api.models import User
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()
        client.delete("/api/athlete/me",
                      headers={"Authorization": f"Bearer {token}"})
        u = db.query(User).filter(User.id == athlete_user.id).first()
        db.refresh(u)
        assert u.activo is False

    def test_delete_clears_garmin_credentials(self, client, db, athlete_user):
        from api.models import User
        from api.crypto import encrypt
        # Login BEFORE setting garmin to prevent background_sync_user from
        # firing (it uses production SessionLocal which has no test tables)
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()

        athlete_user.garmin_email    = "test@garmin.com"
        athlete_user.garmin_password = encrypt("secret123")
        db.commit()

        client.delete("/api/athlete/me",
                      headers={"Authorization": f"Bearer {token}"})
        db.expire_all()
        u = db.query(User).filter(User.id == athlete_user.id).first()
        assert u.garmin_email is None
        assert u.garmin_password is None

    def test_delete_clears_strava_tokens(self, client, db, athlete_user):
        from api.models import User
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()

        athlete_user.strava_access_token  = "tok_abc"
        athlete_user.strava_refresh_token = "ref_abc"
        db.commit()

        client.delete("/api/athlete/me",
                      headers={"Authorization": f"Bearer {token}"})
        db.expire_all()
        u = db.query(User).filter(User.id == athlete_user.id).first()
        assert u.strava_access_token is None
        assert u.strava_refresh_token is None

    def test_delete_response_has_message(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()
        r = client.delete("/api/athlete/me",
                          headers={"Authorization": f"Bearer {token}"})
        assert "message" in r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 37 Security Fixes — Report IDOR & Admin Garmin IDOR
# ─────────────────────────────────────────────────────────────────────────────

class TestReportPdfIDOR:
    def test_coach_without_group_cannot_get_pdf(self, client, coach_user, athlete_user):
        token = login(client, "coach@test.com", "CoachPass123")
        client.cookies.clear()
        r = client.get(
            f"/api/coach/report/athlete/{athlete_user.id}/pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_athlete_cannot_get_coach_pdf_endpoint(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        client.cookies.clear()
        r = client.get(
            f"/api/coach/report/athlete/{athlete_user.id}/pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


class TestAdminGarminIDOR:
    def test_coach_without_group_cannot_set_garmin(self, client, coach_user, athlete_user):
        token = login(client, "coach@test.com", "CoachPass123")
        client.cookies.clear()
        r = client.post(
            f"/api/admin/users/{athlete_user.id}/garmin",
            headers={"Authorization": f"Bearer {token}"},
            json={"garmin_email": "x@garmin.com", "garmin_password": "pass"},
        )
        assert r.status_code == 403

    def test_admin_can_set_any_athlete_garmin(self, client, admin_user, athlete_user):
        token = login(client, "admin@test.com", "AdminPass123")
        client.cookies.clear()
        r = client.post(
            f"/api/admin/users/{athlete_user.id}/garmin",
            headers={"Authorization": f"Bearer {token}"},
            json={"garmin_email": "x@garmin.com", "garmin_password": "pass"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
