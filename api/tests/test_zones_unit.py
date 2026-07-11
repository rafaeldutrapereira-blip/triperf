"""Sprint 32 — Training Zones unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.zones_service import (
    _fmt_pace_km,
    _fmt_pace_100m,
    bike_power_zones,
    run_pace_zones,
    swim_pace_zones,
    hr_zones,
    compute_zones,
    get_latest_zones,
    get_all_latest_zones,
    VALID_SPORTS,
)
from api.models import PerformanceBenchmark


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bm(**kwargs):
    bm = MagicMock(spec=PerformanceBenchmark)
    bm.id          = "bm-1"
    bm.athlete_id  = "ath-1"
    bm.sport       = "bike"
    bm.test_date   = "2026-01-15"
    bm.test_type   = "FTP test 20 min"
    bm.ftp_watts   = None
    bm.threshold_pace_sec_km   = None
    bm.threshold_pace_sec_100m = None
    bm.max_hr      = None
    bm.lthr        = None
    bm.weight_kg   = None
    for k, v in kwargs.items():
        setattr(bm, k, v)
    return bm


# ── Fmt pace km ───────────────────────────────────────────────────────────────

class TestFmtPaceKm:
    def test_exact_minutes(self):
        assert _fmt_pace_km(240) == "4:00/km"

    def test_with_seconds(self):
        assert _fmt_pace_km(270) == "4:30/km"

    def test_sub_minute(self):
        assert _fmt_pace_km(45) == "0:45/km"

    def test_zero_returns_dash(self):
        assert _fmt_pace_km(0) == "—"

    def test_negative_returns_dash(self):
        assert _fmt_pace_km(-10) == "—"

    def test_leading_zero_seconds(self):
        assert _fmt_pace_km(300) == "5:00/km"

    def test_odd_seconds(self):
        assert _fmt_pace_km(263) == "4:23/km"


# ── Fmt pace 100m ─────────────────────────────────────────────────────────────

class TestFmtPace100m:
    def test_exact(self):
        assert _fmt_pace_100m(95) == "1:35/100m"

    def test_sub_minute(self):
        assert _fmt_pace_100m(58) == "0:58/100m"

    def test_zero_returns_dash(self):
        assert _fmt_pace_100m(0) == "—"

    def test_negative_returns_dash(self):
        assert _fmt_pace_100m(-5) == "—"

    def test_two_minutes(self):
        assert _fmt_pace_100m(120) == "2:00/100m"


# ── Bike power zones ──────────────────────────────────────────────────────────

class TestBikePowerZones:
    def test_ftp_250_returns_5_zones(self):
        zones = bike_power_zones(250)
        assert len(zones) == 5

    def test_zone_numbers_sequential(self):
        zones = bike_power_zones(300)
        assert [z["zone"] for z in zones] == [1, 2, 3, 4, 5]

    def test_ftp_200_z4_min(self):
        zones = bike_power_zones(200)
        z4 = next(z for z in zones if z["zone"] == 4)
        assert z4["min_w"] == round(200 * 91 / 100)

    def test_z5_label_no_upper(self):
        zones = bike_power_zones(250)
        z5 = next(z for z in zones if z["zone"] == 5)
        assert z5["label"].startswith(">")

    def test_zero_ftp_returns_empty(self):
        assert bike_power_zones(0) == []

    def test_negative_ftp_returns_empty(self):
        assert bike_power_zones(-10) == []

    def test_zone_has_required_keys(self):
        z = bike_power_zones(300)[0]
        for key in ("zone", "name", "min_pct", "max_pct", "min_w", "max_w", "label"):
            assert key in z

    def test_ftp_wkg_not_returned_by_this_fn(self):
        # wkg is computed in compute_zones, not here
        zones = bike_power_zones(250)
        assert "ftp_wkg" not in zones[0]


# ── Run pace zones ────────────────────────────────────────────────────────────

class TestRunPaceZones:
    def test_returns_5_zones(self):
        assert len(run_pace_zones(270)) == 5

    def test_z4_contains_threshold(self):
        # T-pace 270 s/km → Z4 is ±5 to ±9 s
        zones = run_pace_zones(270)
        z4 = next(z for z in zones if z["zone"] == 4)
        assert z4["pace_min_sec"] <= 270 <= z4["pace_max_sec"]

    def test_z1_label_starts_with_lt(self):
        zones = run_pace_zones(300)
        z1 = zones[0]
        assert z1["label"].startswith("<")

    def test_z5_label_starts_with_gt(self):
        zones = run_pace_zones(270)
        z5 = zones[-1]
        assert z5["label"].startswith(">")

    def test_zero_returns_empty(self):
        assert run_pace_zones(0) == []

    def test_zone_has_pace_strs(self):
        z = run_pace_zones(270)[1]
        assert "pace_min_str" in z and "pace_max_str" in z

    def test_faster_zones_have_lower_sec(self):
        zones = run_pace_zones(300)
        # Z5 is faster (lower sec) than Z1
        z1_sec = zones[0]["pace_min_sec"]
        z5_sec = zones[4]["pace_min_sec"]
        assert z5_sec < z1_sec


# ── Swim pace zones ───────────────────────────────────────────────────────────

class TestSwimPaceZones:
    def test_returns_5_zones(self):
        assert len(swim_pace_zones(95)) == 5

    def test_z4_css_zone(self):
        zones = swim_pace_zones(95)
        z4 = next(z for z in zones if z["zone"] == 4)
        assert "CSS" in z4["name"] or "Umbral" in z4["name"]

    def test_z1_label_starts_with_lt(self):
        zones = swim_pace_zones(90)
        assert zones[0]["label"].startswith("<")

    def test_z5_label_starts_with_gt(self):
        zones = swim_pace_zones(90)
        assert zones[-1]["label"].startswith(">")

    def test_zero_returns_empty(self):
        assert swim_pace_zones(0) == []

    def test_zone_has_100m_suffix(self):
        z = swim_pace_zones(95)[2]
        assert "/100m" in z["pace_min_str"]


# ── HR zones ──────────────────────────────────────────────────────────────────

class TestHrZones:
    def test_returns_5_zones(self):
        assert len(hr_zones(185)) == 5

    def test_zone_numbers(self):
        assert [z["zone"] for z in hr_zones(185)] == [1, 2, 3, 4, 5]

    def test_z5_max_hr(self):
        zones = hr_zones(190)
        z5 = zones[-1]
        assert z5["min_bpm"] == round(190 * 90 / 100)

    def test_z5_label_gt(self):
        zones = hr_zones(190)
        assert zones[-1]["label"].startswith(">")

    def test_lthr_annotates_z4(self):
        zones = hr_zones(185, lthr=165)
        z4 = next(z for z in zones if z["zone"] == 4)
        assert z4["lthr_based"] is True
        assert "lthr_note" in z4

    def test_no_lthr_not_annotated(self):
        zones = hr_zones(185)
        z4 = next(z for z in zones if z["zone"] == 4)
        assert z4["lthr_based"] is False

    def test_zero_max_hr_returns_empty(self):
        assert hr_zones(0) == []

    def test_bpm_ranges_ascending(self):
        zones = hr_zones(200)
        for i in range(len(zones) - 1):
            assert zones[i]["max_bpm"] <= zones[i+1]["max_bpm"]


# ── compute_zones ─────────────────────────────────────────────────────────────

class TestComputeZones:
    def test_bike_with_ftp(self):
        bm = _bm(sport="bike", ftp_watts=250, weight_kg=70.0)
        result = compute_zones(bm)
        assert result["power_zones"] is not None
        assert len(result["power_zones"]) == 5
        assert result["ftp_wkg"] == round(250 / 70.0, 2)

    def test_bike_without_weight_no_wkg(self):
        bm = _bm(sport="bike", ftp_watts=250, weight_kg=None)
        result = compute_zones(bm)
        assert result["ftp_wkg"] is None

    def test_run_pace_zones(self):
        bm = _bm(sport="run", threshold_pace_sec_km=270)
        result = compute_zones(bm)
        assert result["pace_zones"] is not None
        assert result["threshold_pace_km"] == "4:30/km"

    def test_swim_pace_zones(self):
        bm = _bm(sport="swim", threshold_pace_sec_100m=95)
        result = compute_zones(bm)
        assert result["pace_zones"] is not None
        assert result["threshold_pace_100m"] == "1:35/100m"

    def test_hr_zones_always_computed_if_max_hr(self):
        bm = _bm(sport="bike", ftp_watts=250, max_hr=185)
        result = compute_zones(bm)
        assert result["hr_zones"] is not None

    def test_no_max_hr_no_hr_zones(self):
        bm = _bm(sport="bike", ftp_watts=250, max_hr=None)
        result = compute_zones(bm)
        assert result["hr_zones"] is None

    def test_wrong_sport_no_power_zones(self):
        bm = _bm(sport="run", ftp_watts=250)
        result = compute_zones(bm)
        assert result["power_zones"] is None

    def test_returns_required_keys(self):
        bm = _bm(sport="bike", ftp_watts=200)
        result = compute_zones(bm)
        for key in ("benchmark_id", "sport", "test_date", "ftp_watts", "power_zones", "pace_zones", "hr_zones"):
            assert key in result

    def test_benchmark_id_propagated(self):
        bm = _bm(sport="bike", ftp_watts=200)
        assert compute_zones(bm)["benchmark_id"] == "bm-1"


# ── get_latest_zones ──────────────────────────────────────────────────────────

class TestGetLatestZones:
    def _make_db(self, bm=None):
        db = MagicMock()
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = bm
        return db

    def test_returns_none_when_no_benchmark(self):
        db = self._make_db(None)
        assert get_latest_zones("ath-1", "bike", db) is None

    def test_returns_computed_zones_when_benchmark_exists(self):
        bm = _bm(sport="bike", ftp_watts=280)
        db = self._make_db(bm)
        result = get_latest_zones("ath-1", "bike", db)
        assert result is not None
        assert result["power_zones"] is not None

    def test_queries_correct_athlete(self):
        db = self._make_db(None)
        get_latest_zones("ath-xyz", "run", db)
        db.query.assert_called_once_with(PerformanceBenchmark)

    def test_run_sport_returns_pace_zones(self):
        bm = _bm(sport="run", threshold_pace_sec_km=300)
        db = self._make_db(bm)
        result = get_latest_zones("ath-1", "run", db)
        assert result["pace_zones"] is not None


# ── get_all_latest_zones ──────────────────────────────────────────────────────

class TestGetAllLatestZones:
    def test_returns_all_3_sports(self):
        db = MagicMock()
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = None
        result = get_all_latest_zones("ath-1", db)
        assert set(result.keys()) == {"bike", "run", "swim"}

    def test_none_when_no_data(self):
        db = MagicMock()
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = None
        result = get_all_latest_zones("ath-1", db)
        assert all(v is None for v in result.values())

    def test_valid_sports_set(self):
        assert VALID_SPORTS == {"bike", "run", "swim"}
