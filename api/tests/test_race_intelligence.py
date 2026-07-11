"""
Tests — Race Intelligence Module
"""
import json
import pytest

from ..routes.race_routes import _predict, _fmt_hms, _fmt_ms, DIST_CONFIG
from .conftest import login


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: motor de predicción
# ─────────────────────────────────────────────────────────────────────────────

class TestPredictEngine:
    _base_params = dict(
        ftp=250, css_sec=95, run_pace_sec=280,
        weight_kg=70, tsb=10, readiness=78,
        labs_factors={},
    )

    def test_predict_703_returns_valid_structure(self):
        result = _predict(dist="703", **self._base_params)
        assert result["total_sec"] > 0
        assert result["swim_sec"]  > 0
        assert result["bike_sec"]  > 0
        assert result["run_sec"]   > 0
        assert result["t1_sec"]    > 0
        assert result["t2_sec"]    > 0
        assert 0 < result["confidence_pct"] <= 100

    def test_predict_total_is_sum_of_parts(self):
        result = _predict(dist="703", **self._base_params)
        parts_sum = (result["swim_sec"] + result["t1_sec"] +
                     result["bike_sec"] + result["t2_sec"] + result["run_sec"])
        assert result["total_sec"] == parts_sum

    def test_predict_all_distances(self):
        for dist in DIST_CONFIG.keys():
            result = _predict(dist=dist, **self._base_params)
            assert result["total_sec"] > 0, f"No time for {dist}"

    def test_higher_ftp_faster_bike(self):
        slow = _predict(dist="703", **{**self._base_params, "ftp": 180})
        fast = _predict(dist="703", **{**self._base_params, "ftp": 320})
        assert fast["bike_sec"] < slow["bike_sec"]

    def test_lower_css_faster_swim(self):
        slow = _predict(dist="703", **{**self._base_params, "css_sec": 120})  # 2:00/100m
        fast = _predict(dist="703", **{**self._base_params, "css_sec":  80})  # 1:20/100m
        assert fast["swim_sec"] < slow["swim_sec"]

    def test_negative_tsb_penalizes_time(self):
        rested  = _predict(dist="703", **{**self._base_params, "tsb": +15})
        fatigued= _predict(dist="703", **{**self._base_params, "tsb": -30})
        assert rested["total_sec"] < fatigued["total_sec"]

    def test_low_ferritin_penalizes_time(self):
        normal  = _predict(dist="703", **{**self._base_params, "labs_factors": {"ferritin": 80}})
        defic   = _predict(dist="703", **{**self._base_params, "labs_factors": {"ferritin": 15}})
        assert defic["total_sec"] > normal["total_sec"]
        assert len(defic["labs_notes"]) > 0
        assert "Ferritina" in defic["labs_notes"][0]

    def test_optimal_labs_no_notes(self):
        result = _predict(dist="703", **{**self._base_params,
                          "labs_factors": {"ferritin": 90, "vitamin_d": 50, "hb": 15.5}})
        assert len(result["labs_notes"]) == 0

    def test_multiple_lab_penalties_accumulate(self):
        single  = _predict(dist="703", **{**self._base_params,
                           "labs_factors": {"ferritin": 15}})
        multiple= _predict(dist="703", **{**self._base_params,
                           "labs_factors": {"ferritin": 15, "vitamin_d": 10, "cortisol": 28}})
        assert multiple["total_sec"] > single["total_sec"]
        assert multiple["labs_mult"] < single["labs_mult"]
        assert len(multiple["labs_notes"]) >= 3

    def test_range_straddles_total(self):
        result = _predict(dist="703", **self._base_params)
        assert result["range_low_sec"]  < result["total_sec"]
        assert result["range_high_sec"] > result["total_sec"]

    def test_low_readiness_widens_confidence_band(self):
        high_r = _predict(dist="703", **{**self._base_params, "readiness": 90})
        low_r  = _predict(dist="703", **{**self._base_params, "readiness": 20})
        assert high_r["confidence_pct"] >= low_r["confidence_pct"]

    def test_conditions_affect_time(self):
        base = _predict(dist="703", **self._base_params, cond_mult=1.0)
        bad  = _predict(dist="703", **self._base_params, cond_mult=0.90, wind_mult=0.95)
        assert bad["total_sec"] > base["total_sec"]

    def test_ironman_longer_than_703(self):
        r703  = _predict(dist="703",  **self._base_params)
        rfull = _predict(dist="full", **self._base_params)
        assert rfull["total_sec"] > r703["total_sec"] * 1.5

    def test_run_only_for_marathon(self):
        result = _predict(dist="42k", **self._base_params)
        assert result["swim_sec"] == 0
        assert result["bike_sec"] == 0
        assert result["run_sec"]  > 0

    def test_unknown_distance_raises(self):
        with pytest.raises(ValueError):
            _predict(dist="unknown_dist", **self._base_params)


class TestFormatHelpers:
    def test_fmt_hms_basic(self):
        assert _fmt_hms(3661) == "1:01:01"
        assert _fmt_hms(18000) == "5:00:00"
        assert _fmt_hms(0) == "0:00:00"

    def test_fmt_ms_basic(self):
        assert _fmt_ms(95) == "1:35"
        assert _fmt_ms(300) == "5:00"
        assert _fmt_ms(0) == "0:00"

    def test_fmt_hms_round_trip_consistency(self):
        sec = 5 * 3600 + 12 * 60 + 34  # 5:12:34
        assert _fmt_hms(sec) == "5:12:34"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: endpoints
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_predict_endpoint(client, auth_headers):
    resp = client.post("/api/races/predict", json={"distance": "703"},
                       headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_sec" in data
    assert data["total_sec"] > 0
    assert "splits" in data
    assert "confidence_pct" in data
    assert "labs_notes" in data


def test_predict_invalid_distance(client, auth_headers):
    resp = client.post("/api/races/predict", json={"distance": "halfmarathon"},
                       headers=auth_headers)
    assert resp.status_code == 422


def test_create_race(client, auth_headers):
    resp = client.post("/api/races", json={
        "name":         "Test Race 70.3",
        "date_iso":     "2027-03-01",
        "distance":     "703",
        "location":     "Viña del Mar",
        "is_goal_race": True,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "race_id" in data


def test_list_races(client, auth_headers):
    resp = client.get("/api/races", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_race_detail(client, auth_headers):
    create_resp = client.post("/api/races", json={
        "name": "Detail Test Race",
        "date_iso": "2027-06-15",
        "distance": "full",
    }, headers=auth_headers)
    race_id = create_resp.json()["race_id"]

    resp = client.get(f"/api/races/{race_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == race_id
    assert data["name"] == "Detail Test Race"
    assert data["distance"] == "full"
    assert "prediction_now" in data


def test_save_race_result(client, auth_headers):
    create_resp = client.post("/api/races", json={
        "name": "Result Test Race",
        "date_iso": "2026-01-10",  # past race
        "distance": "703",
    }, headers=auth_headers)
    race_id = create_resp.json()["race_id"]

    result_resp = client.patch(f"/api/races/{race_id}/result", json={
        "swim_sec": 2100,    # 35:00
        "t1_sec":   180,
        "bike_sec": 9480,    # 2:38
        "t2_sec":   120,
        "run_sec":  6840,    # 1:54
        "notes":    "Gran carrera",
        "is_pr":    True,
    }, headers=auth_headers)
    assert result_resp.status_code == 200
    data = result_resp.json()
    assert data["ok"] is True
    assert data["actual_total"] is not None
    assert data["is_pr"] is True
    # Sum check: 2100+180+9480+120+6840 = 18720
    assert "actual_total" in data


def test_delete_race(client, auth_headers):
    create_resp = client.post("/api/races", json={
        "name": "Delete Test Race",
        "date_iso": "2027-12-01",
        "distance": "sprint",
    }, headers=auth_headers)
    race_id = create_resp.json()["race_id"]

    del_resp = client.delete(f"/api/races/{race_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    get_resp = client.get(f"/api/races/{race_id}", headers=auth_headers)
    assert get_resp.status_code == 404


def test_taper_check_endpoint(client, auth_headers):
    resp = client.get("/api/races/upcoming/taper-check", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "has_race" in data


def test_cannot_access_other_users_race(client, auth_headers):
    resp = client.get("/api/races/other-user-race-id", headers=auth_headers)
    assert resp.status_code == 404


def test_create_race_requires_name(client, auth_headers):
    resp = client.post("/api/races", json={
        "date_iso": "2027-01-01",
        "distance": "703",
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_create_race_requires_date(client, auth_headers):
    resp = client.post("/api/races", json={
        "name": "No Date Race",
        "distance": "703",
    }, headers=auth_headers)
    assert resp.status_code == 422
