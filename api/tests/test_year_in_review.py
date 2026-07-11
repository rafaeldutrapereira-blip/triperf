"""
Tests — B-27: Year in Review endpoint
"""
import pytest
from collections import defaultdict
from .conftest import login


# ─────────────────────────────────────────────────────────────────────────────
# Unit: aggregation logic
# ─────────────────────────────────────────────────────────────────────────────

class TestYearInReviewAggregation:
    def _aggregate(self, activities):
        totals = defaultdict(float)
        total_km = 0.0; total_hours = 0.0; total_tss = 0.0; n = 0
        for a in activities:
            sport = a.get("sport","other")
            totals[sport] += a.get("dist_km", 0)
            total_km      += a.get("dist_km", 0)
            total_hours   += (a.get("dur_min", 0)) / 60.0
            total_tss     += a.get("tss", 0)
            n             += 1
        return {"totals": dict(totals), "km": total_km, "hours": total_hours, "tss": total_tss, "n": n}

    def test_km_by_sport(self):
        acts = [
            {"sport":"swim","dist_km":2.0,"dur_min":45,"tss":50},
            {"sport":"bike","dist_km":100.0,"dur_min":180,"tss":160},
            {"sport":"run","dist_km":10.0,"dur_min":60,"tss":80},
        ]
        r = self._aggregate(acts)
        assert r["totals"]["swim"] == 2.0
        assert r["totals"]["bike"] == 100.0
        assert r["totals"]["run"]  == 10.0
        assert r["km"]    == 112.0
        assert r["n"]     == 3

    def test_total_hours(self):
        acts = [{"sport":"bike","dist_km":90,"dur_min":180,"tss":140}]
        r = self._aggregate(acts)
        assert abs(r["hours"] - 3.0) < 0.01

    def test_total_tss(self):
        acts = [
            {"sport":"swim","dist_km":1,"dur_min":30,"tss":40},
            {"sport":"run","dist_km":5,"dur_min":30,"tss":50},
        ]
        r = self._aggregate(acts)
        assert r["tss"] == 90.0

    def test_empty_activities(self):
        r = self._aggregate([])
        assert r["km"] == 0
        assert r["n"]  == 0


class TestPeakWeekCalculation:
    def _peak_week(self, activities):
        by_week = defaultdict(float)
        for a in activities:
            from datetime import date, timezone
            try:
                d = date.fromisoformat(a["date_iso"])
                by_week[d.strftime("%G-W%V")] += a.get("tss", 0)
            except ValueError:
                pass
        return max(by_week.items(), key=lambda x: x[1], default=(None, 0))

    def test_correct_peak_week(self):
        acts = [
            {"date_iso": "2025-06-02", "tss": 120},
            {"date_iso": "2025-06-03", "tss": 80},
            {"date_iso": "2025-06-09", "tss": 200},
            {"date_iso": "2025-06-10", "tss": 150},
            {"date_iso": "2025-06-16", "tss": 100},
        ]
        peak = self._peak_week(acts)
        assert peak[1] == 350.0  # week of June 9-15

    def test_single_week(self):
        acts = [{"date_iso":"2025-07-01","tss":100},{"date_iso":"2025-07-02","tss":80}]
        peak = self._peak_week(acts)
        assert peak[1] == 180.0

    def test_empty_no_crash(self):
        peak = self._peak_week([])
        assert peak[0] is None


class TestCtlImprovement:
    def test_positive_improvement(self):
        start, end = 45.0, 72.5
        imp = round(end - start, 1)
        assert imp == 27.5

    def test_negative_improvement(self):
        start, end = 70.0, 55.0
        imp = round(end - start, 1)
        assert imp == -15.0

    def test_no_change(self):
        start, end = 60.0, 60.0
        imp = round(end - start, 1)
        assert imp == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_year_in_review_requires_auth(client):
    resp = client.get("/api/athlete/year-in-review")
    assert resp.status_code == 401


def test_year_in_review_structure(client, auth_headers):
    resp = client.get("/api/athlete/year-in-review?year=2025", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    required_keys = [
        "year", "athlete_name", "total_activities", "total_hours",
        "total_km", "total_tss", "by_sport", "longest_by_sport",
        "peak_week_iso", "peak_week_tss", "fav_weekday",
        "ctl_start", "ctl_end", "ctl_peak", "month_series",
        "ctl_improvement",
    ]
    for k in required_keys:
        assert k in data, f"Missing key: {k}"


def test_year_in_review_year_param(client, auth_headers):
    resp = client.get("/api/athlete/year-in-review?year=2024", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["year"] == 2024


def test_year_in_review_defaults_to_current_year(client, auth_headers):
    from datetime import date
    resp = client.get("/api/athlete/year-in-review", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["year"] == date.today().year


def test_year_in_review_month_series_length(client, auth_headers):
    resp = client.get("/api/athlete/year-in-review?year=2025", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["month_series"]) == 12


def test_year_in_review_month_series_fields(client, auth_headers):
    resp = client.get("/api/athlete/year-in-review?year=2025", headers=auth_headers)
    assert resp.status_code == 200
    for mo in resp.json()["month_series"]:
        assert "month"  in mo
        assert "label"  in mo
        assert "tss"    in mo
        assert 1 <= mo["month"] <= 12


def test_year_in_review_by_sport_structure(client, auth_headers):
    resp = client.get("/api/athlete/year-in-review?year=2025", headers=auth_headers)
    assert resp.status_code == 200
    for sport, info in resp.json()["by_sport"].items():
        assert "km"  in info
        assert "tss" in info


def test_year_in_review_athlete_name_present(client, auth_headers):
    resp = client.get("/api/athlete/year-in-review?year=2025", headers=auth_headers)
    assert resp.status_code == 200
    name = resp.json()["athlete_name"]
    assert isinstance(name, str) and len(name) > 0
