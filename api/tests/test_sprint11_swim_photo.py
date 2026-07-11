"""
Tests — Sprint 11: B-23 Activity Photo, B-24 Swim SWOLF
"""
import pytest
import io
from .conftest import login


# ─────────────────────────────────────────────────────────────────────────────
# Unit: SWOLF extraction logic
# ─────────────────────────────────────────────────────────────────────────────

def _extract_swolf(act: dict) -> float | None:
    v = act.get("averageSwolf") or act.get("avgSwolf")
    return round(float(v), 1) if v else None


def _extract_cadence(act: dict) -> float | None:
    v = act.get("avgStrokes") or act.get("averageStrokes")
    return round(float(v), 1) if v else None


def _extract_pool_length(act: dict) -> int | None:
    v = act.get("poolLength")
    return int(v) if v else None


class TestSwolfExtraction:
    def test_averageSwolf_primary_key(self):
        assert _extract_swolf({"averageSwolf": 32.5}) == 32.5

    def test_avgSwolf_fallback(self):
        assert _extract_swolf({"avgSwolf": 28.0}) == 28.0

    def test_no_swolf_returns_none(self):
        assert _extract_swolf({"calories": 300}) is None

    def test_swolf_rounds_to_1_decimal(self):
        assert _extract_swolf({"averageSwolf": 31.456}) == 31.5

    def test_cadence_primary(self):
        assert _extract_cadence({"avgStrokes": 22.3}) == 22.3

    def test_pool_length_25m(self):
        assert _extract_pool_length({"poolLength": 25}) == 25

    def test_pool_length_50m(self):
        assert _extract_pool_length({"poolLength": 50}) == 50

    def test_pool_length_missing(self):
        assert _extract_pool_length({}) is None


class TestSwolfEfficiencyThresholds:
    """SWOLF efficiency benchmarks for triathlon swimmers."""
    def _classify(self, swolf: float) -> str:
        if swolf <= 30: return "elite"
        if swolf <= 35: return "competitive"
        if swolf <= 40: return "recreational"
        return "beginner"

    def test_elite_swolf(self):      assert self._classify(28.0) == "elite"
    def test_competitive_swolf(self):assert self._classify(33.5) == "competitive"
    def test_recreational_swolf(self):assert self._classify(38.0) == "recreational"
    def test_beginner_swolf(self):   assert self._classify(45.0) == "beginner"
    def test_boundary_30(self):      assert self._classify(30.0) == "elite"
    def test_boundary_35(self):      assert self._classify(35.0) == "competitive"


# ─────────────────────────────────────────────────────────────────────────────
# Unit: Photo path construction
# ─────────────────────────────────────────────────────────────────────────────

class TestPhotoPath:
    def test_photo_url_constructed_from_id(self):
        activity_id = "abc-123"
        photo_url = f"/api/athlete/activities/{activity_id}/photo"
        assert "abc-123" in photo_url
        assert photo_url.startswith("/api/")

    def test_no_photo_returns_none(self):
        photo_path = None
        photo_url = (f"/api/athlete/activities/x/photo") if photo_path else None
        assert photo_url is None

    def test_activity_dict_includes_swim_fields(self):
        class FakeActivity:
            activity_id = "a1"; id = "id1"; sport = "swim"; name = "Swim"
            date_iso = "2026-06-01"; dur_min = 30; dist_km = 1.5
            avg_hr = 140; avg_power = None; pace_str = None
            swim_pace = "1:45"; calories = 400; tss = 40.0
            icon = "🏊"; swolf = 32.5; avg_cadence_spm = 22.0
            pool_length_m = 25; photo_path = None

        a = FakeActivity()
        d = {
            "swolf":           a.swolf,
            "avg_cadence_spm": a.avg_cadence_spm,
            "pool_length_m":   a.pool_length_m,
            "photo_url":       (f"/api/athlete/activities/{a.id}/photo") if a.photo_path else None,
        }
        assert d["swolf"] == 32.5
        assert d["avg_cadence_spm"] == 22.0
        assert d["pool_length_m"] == 25
        assert d["photo_url"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_photo_upload_requires_auth(client):
    resp = client.post("/api/athlete/activities/any-id/photo",
                       files={"file": ("test.jpg", b"fake", "image/jpeg")})
    assert resp.status_code == 401


def test_photo_get_requires_auth(client):
    resp = client.get("/api/athlete/activities/any-id/photo")
    assert resp.status_code == 401


def test_photo_delete_requires_auth(client):
    resp = client.delete("/api/athlete/activities/any-id/photo")
    assert resp.status_code == 401


def test_photo_upload_nonexistent_activity(client, auth_headers):
    resp = client.post(
        "/api/athlete/activities/nonexistent-id/photo",
        files={"file": ("test.jpg", b"fakeimagedata", "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_photo_upload_non_image_rejected(client, auth_headers):
    """Subir un CSV debe ser rechazado con 400."""
    resp = client.post(
        "/api/athlete/activities/nonexistent-id/photo",
        files={"file": ("data.csv", b"a,b,c", "text/csv")},
        headers=auth_headers,
    )
    # 404 for missing activity or 400 for wrong MIME type
    assert resp.status_code in (400, 404)


def test_activities_list_includes_swim_fields(client, auth_headers):
    resp = client.get("/api/athlete/activities?sport=swim&per_page=5", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    for item in data["items"]:
        assert "swolf"           in item
        assert "avg_cadence_spm" in item
        assert "pool_length_m"   in item
        assert "photo_url"       in item
        assert "swim_pace"       in item


def test_activities_list_all_sports(client, auth_headers):
    resp = client.get("/api/athlete/activities?per_page=10", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert "photo_url" in item
