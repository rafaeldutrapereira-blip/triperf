"""
Tests — Blood Labs Intelligence Module
"""
import json
import pytest
from .conftest import login

from ..models import BloodLabExam, BloodLabAlert
from ..routes.blood_lab_routes import _analyze_marker, _sex, MARKERS


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: marcador analysis engine
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeMarker:
    def test_ferritin_optimal(self):
        result = _analyze_marker("ferritin", 80.0, "m")
        assert result["status"] == "ok"
        assert result["zone"] == "optimal"
        assert result["color"] == "green"

    def test_ferritin_very_low_critical(self):
        result = _analyze_marker("ferritin", 15.0, "m")
        assert result["status"] == "critical"
        assert result["zone"] in ("very_low", "low")
        assert result["color"] == "red"
        assert len(result["tip"]) > 10  # tip debe tener contenido

    def test_ferritin_suboptimal_range(self):
        result = _analyze_marker("ferritin", 35.0, "m")
        assert result["status"] == "warning"
        assert result["zone"] == "suboptimal"

    def test_hb_male_optimal(self):
        result = _analyze_marker("hb", 15.5, "m")
        assert result["status"] == "ok"

    def test_hb_female_low(self):
        result = _analyze_marker("hb", 11.5, "f")
        assert result["status"] == "critical"

    def test_hb_male_very_high(self):
        result = _analyze_marker("hb", 20.0, "m")
        assert result["status"] == "critical"
        assert result["zone"] == "very_high"

    def test_vitamin_d_deficit(self):
        result = _analyze_marker("vitamin_d", 15.0, "m")
        assert result["status"] == "critical"
        assert "suplementar" in result["tip"].lower() or "uplementa" in result["tip"].lower()

    def test_vitamin_d_optimal(self):
        result = _analyze_marker("vitamin_d", 50.0, "m")
        assert result["status"] == "ok"

    def test_cortisol_high_warning(self):
        result = _analyze_marker("cortisol", 22.0, "m")
        assert result["status"] == "warning"
        assert result["zone"] == "high"

    def test_cortisol_very_high_critical(self):
        result = _analyze_marker("cortisol", 30.0, "m")
        assert result["status"] == "critical"

    def test_unknown_marker(self):
        result = _analyze_marker("unknown_marker_xyz", 100.0, "m")
        assert result["status"] == "unknown"

    def test_pct_in_range_0_100(self):
        for key in ["hb", "ferritin", "vitamin_d", "cortisol"]:
            result = _analyze_marker(key, 10.0, "m")
            assert 0 <= result.get("pct", 50) <= 100, f"pct out of range for {key}"

    def test_all_defined_markers_have_tip(self):
        for key, m in MARKERS.items():
            assert m.get("name"), f"Missing name for {key}"
            assert m.get("unit"), f"Missing unit for {key}"
            assert m.get("cat"), f"Missing cat for {key}"
            # Debe haber al menos un tip
            has_tip = any(k.startswith("tip_") for k in m.keys())
            assert has_tip, f"No tip_ fields for {key}"


class TestSexHelper:
    def test_male_explicit(self):
        class FakeUser:
            sexo = "m"
        assert _sex(FakeUser()) == "m"

    def test_female_explicit(self):
        class FakeUser:
            sexo = "femenino"
        assert _sex(FakeUser()) == "f"

    def test_no_sexo_defaults_male(self):
        class FakeUser:
            sexo = None
        assert _sex(FakeUser()) == "m"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: endpoints
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, db, athlete_user):
    # Blood Labs es feature de plan Elite (ver api/plan_features.py)
    athlete_user.plan_nivel = "elite"
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_markers_catalog_no_auth(client):
    resp = client.get("/api/labs/markers")
    assert resp.status_code == 200
    data = resp.json()
    assert "hb" in data
    assert "ferritin" in data
    assert "vitamin_d" in data
    assert data["ferritin"]["name"] == "Ferritina"
    assert data["ferritin"]["unit"] == "ng/mL"


def test_create_exam_requires_auth(client):
    resp = client.post("/api/labs/exams", json={
        "date_iso": "2026-01-15",
        "values": {"hb": 14.5}
    })
    assert resp.status_code == 401


def test_create_exam_success(client, auth_headers):
    resp = client.post("/api/labs/exams", json={
        "date_iso": "2026-01-15",
        "lab_name": "Clínica Test",
        "context":  "Pre-temporada",
        "values": {
            "hb":        14.2,
            "hct":       43.5,
            "ferritin":  25.0,   # bajo → debe generar alerta
            "vitamin_d": 55.0,
            "cortisol":  12.0,
        }
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["markers"] == 5
    assert "exam_id" in data
    # Ferritina baja debe generar al menos 1 alerta
    assert data["alerts"] >= 1


def test_list_exams(client, auth_headers):
    resp = client.get("/api/labs/exams", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_exam_detail(client, auth_headers):
    # Create first
    create_resp = client.post("/api/labs/exams", json={
        "date_iso": "2026-02-10",
        "values": {"hb": 15.0, "ferritin": 80.0, "vitamin_d": 45.0}
    }, headers=auth_headers)
    assert create_resp.status_code == 200
    exam_id = create_resp.json()["exam_id"]

    # Get detail
    resp = client.get(f"/api/labs/exams/{exam_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == exam_id
    assert "markers" in data
    assert "hb" in data["markers"]
    hb = data["markers"]["hb"]
    assert hb["value"] == 15.0
    assert hb["status"] in ("ok", "warning", "critical")
    assert hb["tip"]


def test_get_exam_not_found(client, auth_headers):
    resp = client.get("/api/labs/exams/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


def test_labs_summary(client, auth_headers):
    resp = client.get("/api/labs/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "has_labs" in data


def test_get_alerts(client, auth_headers):
    resp = client.get("/api/labs/alerts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for alert in data:
        assert "severity" in alert
        assert alert["severity"] in ("info", "warning", "critical")
        assert "title" in alert


def test_correlation(client, auth_headers):
    resp = client.get("/api/labs/correlation?days=90", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_delete_exam(client, auth_headers):
    # Create
    create_resp = client.post("/api/labs/exams", json={
        "date_iso": "2026-03-01",
        "values": {"hb": 14.0}
    }, headers=auth_headers)
    exam_id = create_resp.json()["exam_id"]

    # Delete
    del_resp = client.delete(f"/api/labs/exams/{exam_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    # Verify gone
    get_resp = client.get(f"/api/labs/exams/{exam_id}", headers=auth_headers)
    assert get_resp.status_code == 404


def test_cannot_access_other_users_exam(client, auth_headers):
    """Seguridad: un usuario no puede ver exámenes de otro."""
    # Asume que "other-exam-id" no pertenece al usuario autenticado
    resp = client.get("/api/labs/exams/other-exam-id", headers=auth_headers)
    assert resp.status_code == 404  # debe retornar 404, no 403, para no revelar existencia


def test_create_exam_validates_values(client, auth_headers):
    resp = client.post("/api/labs/exams", json={
        "date_iso": "2026-01-10",
        "values": {}  # vacío → debe rechazar
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_create_exam_too_many_markers(client, auth_headers):
    values = {f"marker_{i}": float(i) for i in range(70)}
    resp = client.post("/api/labs/exams", json={
        "date_iso": "2026-01-10",
        "values": values
    }, headers=auth_headers)
    assert resp.status_code == 422
