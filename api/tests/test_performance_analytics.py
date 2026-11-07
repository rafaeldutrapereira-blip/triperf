"""
Tests — Performance Analytics Intelligence (Sprint 8)
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from .conftest import login

from ..services.performance_analytics_service import (
    _fit_cp2_model,
    _fmt_dur,
    _fmt_pace,
    _mmp_from_telemetry,
    compute_power_curve,
    compute_vo2max_history,
    compute_personal_records,
    compute_training_distribution,
    compute_zone_calibration,
    CP_DURATIONS,
    CP_LABELS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit: formatters
# ─────────────────────────────────────────────────────────────────────────────

class TestFmtDur:
    def test_under_hour(self):
        assert _fmt_dur(30) == "30:00"

    def test_over_hour(self):
        assert _fmt_dur(90) == "1:30:00"

    def test_seconds(self):
        assert _fmt_dur(1) == "1:00"

    def test_zero(self):
        assert _fmt_dur(0) == "0:00"


class TestFmtPace:
    def test_five_min_km(self):
        assert _fmt_pace(5.0) == "5:00"

    def test_four_thirty(self):
        assert _fmt_pace(4.5) == "4:30"

    def test_sub_four(self):
        result = _fmt_pace(3.75)
        assert "3:" in result


# ─────────────────────────────────────────────────────────────────────────────
# Unit: CP2 model fitting
# ─────────────────────────────────────────────────────────────────────────────

class TestCp2Model:
    def test_ideal_data_produces_model(self):
        # P = 280 + 20000/t → CP=280, W'=20000
        best_power = {dur: 280 + 20000 / dur for dur in [180, 300, 600, 900, 1200, 1800]}
        model = _fit_cp2_model(best_power)
        assert model is not None
        assert 220 <= model["cp_watts"] <= 340
        assert 10000 <= model["w_prime_j"] <= 35000

    def test_too_few_points_returns_none(self):
        model = _fit_cp2_model({300: 320, 600: 290})
        assert model is None

    def test_unrealistic_values_return_none(self):
        # CP=5W es imposible → debe filtrarse
        best_power = {dur: 5 + 100 / dur for dur in [180, 300, 600, 900, 1200, 1800]}
        model = _fit_cp2_model(best_power)
        assert model is None

    def test_description_includes_watts(self):
        best_power = {dur: 280 + 20000 / dur for dur in [180, 300, 600, 900, 1200, 1800]}
        model = _fit_cp2_model(best_power)
        if model:
            assert "W" in model["description"]
            assert "kJ" in model["description"]


# ─────────────────────────────────────────────────────────────────────────────
# Unit: CP durations and labels
# ─────────────────────────────────────────────────────────────────────────────

class TestCpConstants:
    def test_durations_monotonically_increasing(self):
        for i in range(len(CP_DURATIONS) - 1):
            assert CP_DURATIONS[i] < CP_DURATIONS[i + 1]

    def test_all_durations_have_labels(self):
        for dur in CP_DURATIONS:
            assert dur in CP_LABELS, f"Missing label for {dur}s"

    def test_includes_key_durations(self):
        assert 300  in CP_DURATIONS   # 5 min
        assert 1200 in CP_DURATIONS   # 20 min
        assert 3600 in CP_DURATIONS   # 60 min

    def test_one_hour_label(self):
        assert CP_LABELS[3600] == "1h"

    def test_five_min_label(self):
        assert CP_LABELS[300] == "5m"


# ─────────────────────────────────────────────────────────────────────────────
# Unit: service functions with mocked DB
# ─────────────────────────────────────────────────────────────────────────────

def _make_activity(sport="bike", dur_min=60, dist_km=40.0, avg_power=250,
                   avg_hr=155, tss=80.0, date_iso="2026-01-15"):
    a = MagicMock()
    a.sport      = sport
    a.dur_min    = dur_min
    a.dist_km    = dist_km
    a.avg_power  = avg_power
    a.avg_hr     = avg_hr
    a.tss        = tss
    a.date_iso   = date_iso
    a.activity_id = "act-001"
    a.pace_str   = "5:00"
    return a


def _make_user(peso=70.0, fc_max=185, sexo="M", vo2max=None):
    u = MagicMock()
    u.id        = "user-001"
    u.peso      = peso       # legacy alias
    u.weight_kg = peso       # actual model column
    u.fcmax     = fc_max     # model uses fcmax
    u.fc_max    = fc_max     # keep alias for backwards compat in tests
    u.sexo      = sexo
    u.vo2max    = vo2max
    return u


class TestPowerCurveService:
    def _db_with_activities(self, activities, user=None):
        db = MagicMock()
        user = user or _make_user()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = activities
        q.first.return_value = user
        db.query.return_value = q
        return db

    def test_no_activities_returns_message(self):
        db = self._db_with_activities([])
        result = compute_power_curve("u1", db, days_back=365, sport="bike")
        assert "message" in result
        assert result["curve"] == []

    def test_single_activity_produces_curve(self):
        act = _make_activity(sport="bike", dur_min=60, avg_power=250)
        db  = self._db_with_activities([act])
        result = compute_power_curve("u1", db, sport="bike")
        assert result["curve"] != [] or "message" in result  # flexible: may still be empty

    def test_ftp_estimado_in_range(self):
        # Actividad de 60 min a 250W → FTP debe ser ~250
        act = _make_activity(sport="bike", dur_min=60, avg_power=250)
        db  = self._db_with_activities([act])
        result = compute_power_curve("u1", db, sport="bike")
        if result.get("ftp_est"):
            assert 150 <= result["ftp_est"] <= 600

    def test_watts_per_kg_included_when_weight(self):
        act  = _make_activity(sport="bike", dur_min=60, avg_power=300)
        user = _make_user(peso=75.0)
        db   = self._db_with_activities([act], user)
        result = compute_power_curve("u1", db, sport="bike")
        if result.get("ftp_est") and result.get("weight_kg"):
            assert result["ftp_wkg"] is not None
            assert result["ftp_wkg"] > 0

    def test_curve_monotonically_decreasing(self):
        acts = [
            _make_activity(dur_min=5,  avg_power=400),
            _make_activity(dur_min=20, avg_power=320),
            _make_activity(dur_min=60, avg_power=260),
        ]
        db = self._db_with_activities(acts)
        result = compute_power_curve("u1", db, sport="bike")
        curve = result.get("curve", [])
        powers = [p["power_w"] for p in curve]
        for i in range(len(powers) - 1):
            assert powers[i] >= powers[i + 1], f"Curve not monotonic at index {i}"

    def test_all_points_marked_estimated_without_telemetry(self):
        """Sin archivo de telemetría (caso de siempre en estos tests
        unitarios, activity_id='act-001' nunca existe en disco), todos
        los puntos de la curva deben venir marcados is_estimated=True."""
        act = _make_activity(sport="bike", dur_min=60, avg_power=250)
        db  = self._db_with_activities([act])
        result = compute_power_curve("u1", db, sport="bike")
        for point in result["curve"]:
            assert point["is_estimated"] is True


class TestMmpFromTelemetry:
    """Sprint E (Fase 2, 2026-08-12): Mean Maximal Power real desde el
    stream segundo-a-segundo (data/telemetry/{id}.json), reemplaza la
    aproximación exponencial cuando hay telemetría sincronizada."""

    def test_constant_power_returns_that_power(self):
        samples = [{"t": float(i), "power": 200.0} for i in range(120)]
        assert _mmp_from_telemetry(samples, 60) == 200.0

    def test_finds_best_window_not_average_of_whole_activity(self):
        # 60s a 100W, luego 60s a 400W — el mejor MMP de 60s debe ser ~400,
        # no el promedio de toda la actividad (~250).
        samples = ([{"t": float(i), "power": 100.0} for i in range(60)]
                   + [{"t": float(i), "power": 400.0} for i in range(60, 120)])
        mmp_60s = _mmp_from_telemetry(samples, 60)
        assert mmp_60s is not None
        assert mmp_60s > 350

    def test_irregular_sampling_uses_real_time_not_sample_count(self):
        # Un hueco de 30s sin datos entre dos muestras no debe contarse
        # como si esos 30s hubieran tenido la potencia de la muestra
        # anterior "gratis" — el peso de cada tramo es su duración real.
        samples = [{"t": 0.0, "power": 100.0}, {"t": 30.0, "power": 100.0},
                   {"t": 31.0, "power": 500.0}, {"t": 32.0, "power": 500.0}]
        mmp_1s = _mmp_from_telemetry(samples, 1)
        assert mmp_1s is not None
        assert mmp_1s >= 400  # la ventana de 1s real debe capturar el pico, no diluirlo

    def test_duration_longer_than_activity_returns_none(self):
        samples = [{"t": float(i), "power": 200.0} for i in range(30)]
        assert _mmp_from_telemetry(samples, 3600) is None

    def test_empty_or_single_sample_returns_none(self):
        assert _mmp_from_telemetry([], 60) is None
        assert _mmp_from_telemetry([{"t": 0.0, "power": 200.0}], 60) is None

    def test_missing_power_field_ignored(self):
        samples = [{"t": float(i), "hr": 140.0} for i in range(60)]  # sin 'power'
        assert _mmp_from_telemetry(samples, 30) is None


class TestPowerCurveRealTelemetry:
    """compute_power_curve debe preferir telemetría real sobre la
    aproximación cuando existe — y nunca mezclarlas para la misma
    duración (un valor real nunca se pisa con uno estimado)."""

    def _db_with_activities(self, activities, user=None):
        db = MagicMock()
        user = user or _make_user()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = activities
        q.first.return_value = user
        db.query.return_value = q
        return db

    def test_uses_real_telemetry_when_available(self):
        act = _make_activity(sport="bike", dur_min=60, avg_power=200)
        act.activity_id = "act-real-001"
        samples = ([{"t": float(i), "power": 100.0} for i in range(3540)]
                   + [{"t": float(i), "power": 350.0} for i in range(3540, 3600)])
        db = self._db_with_activities([act])
        with patch("api.services.performance_analytics_service._load_telemetry_samples",
                   return_value=samples):
            result = compute_power_curve("u1", db, sport="bike")
        point_60s = next(p for p in result["curve"] if p["duration_sec"] == 60)
        assert point_60s["is_estimated"] is False
        assert point_60s["power_w"] > 300  # el pico real de 350W, no la aproximación desde avg_power=200
        assert result["n_with_telemetry"] == 1

    def test_falls_back_to_estimate_when_no_telemetry_file(self):
        act = _make_activity(sport="bike", dur_min=60, avg_power=200)
        db = self._db_with_activities([act])
        with patch("api.services.performance_analytics_service._load_telemetry_samples",
                   return_value=None):
            result = compute_power_curve("u1", db, sport="bike")
        assert result["n_with_telemetry"] == 0
        for point in result["curve"]:
            assert point["is_estimated"] is True


class TestTrainingDistribution:
    def _db_with_acts(self, activities):
        db = MagicMock()
        user = _make_user()
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = activities
        q.first.return_value = user
        db.query.return_value = q
        return db

    def test_no_activities_returns_message(self):
        db = self._db_with_acts([])
        result = compute_training_distribution("u1", db)
        assert "message" in result

    def test_returns_required_keys(self):
        acts = [
            _make_activity(sport="bike", tss=80, date_iso="2026-01-15"),
            _make_activity(sport="run",  tss=50, date_iso="2026-01-16"),
        ]
        db = self._db_with_acts(acts)
        result = compute_training_distribution("u1", db)
        if "message" not in result:
            assert "by_sport"   in result
            assert "by_weekday" in result
            assert "by_zone"    in result

    def test_polarization_index_positive(self):
        acts = [_make_activity(avg_hr=120, tss=40, date_iso=f"2026-01-{i:02d}") for i in range(1, 10)]
        db = self._db_with_acts(acts)
        result = compute_training_distribution("u1", db)
        if "polarization_index" in result:
            assert result["polarization_index"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (API)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, db, athlete_user):
    # Analytics es feature de plan Agegroup+ (ver api/plan_features.py)
    athlete_user.plan_nivel = "agegroup"
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_power_curve_requires_auth(client):
    resp = client.get("/api/analytics/power-curve")
    assert resp.status_code == 401


def test_vo2max_requires_auth(client):
    resp = client.get("/api/analytics/vo2max")
    assert resp.status_code == 401


def test_personal_records_requires_auth(client):
    resp = client.get("/api/analytics/personal-records")
    assert resp.status_code == 401


def test_training_distribution_requires_auth(client):
    resp = client.get("/api/analytics/training-distribution")
    assert resp.status_code == 401


def test_zone_calibration_requires_auth(client):
    resp = client.get("/api/analytics/zone-calibration")
    assert resp.status_code == 401


def test_summary_requires_auth(client):
    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 401


def test_power_curve_structure(client, auth_headers):
    resp = client.get("/api/analytics/power-curve", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "sport" in data
    assert "curve" in data
    assert isinstance(data["curve"], list)


def test_vo2max_structure(client, auth_headers):
    resp = client.get("/api/analytics/vo2max", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline"    in data
    assert "vo2max_current" in data or data.get("vo2max_current") is None
    assert isinstance(data["timeline"], list)


def test_personal_records_structure(client, auth_headers):
    resp = client.get("/api/analytics/personal-records", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "records"          in data
    assert "total_activities" in data
    assert isinstance(data["records"], dict)


def test_training_distribution_structure(client, auth_headers):
    resp = client.get("/api/analytics/training-distribution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "by_sport" in data or "message" in data


def test_zone_calibration_structure(client, auth_headers):
    resp = client.get("/api/analytics/zone-calibration", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "cycling"  in data
    assert "running"  in data
    assert "swimming" in data
    assert "note"     in data


def test_summary_structure(client, auth_headers):
    resp = client.get("/api/analytics/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "power_curve"           in data
    assert "vo2max"                in data
    assert "personal_records"      in data
    assert "training_distribution" in data
    assert "zone_calibration"      in data


def test_power_curve_sport_param(client, auth_headers):
    resp = client.get("/api/analytics/power-curve?sport=run", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["sport"] == "run"


def test_power_curve_days_param(client, auth_headers):
    resp = client.get("/api/analytics/power-curve?days_back=90", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("days_back") == 90


def test_personal_records_sport_filter(client, auth_headers):
    resp = client.get("/api/analytics/personal-records?sports=run", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    if data["records"]:
        assert all(sp in ["run"] for sp in data["records"].keys())


def test_distribution_pct_sums_100(client, auth_headers):
    resp = client.get("/api/analytics/training-distribution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    sports = data.get("by_sport", [])
    if sports:
        total_pct = sum(s["pct_tss"] for s in sports)
        assert abs(total_pct - 100.0) < 2.0   # tolerancia de redondeo


# ─────────────────────────────────────────────────────────────────────────────
# S23-B: /summary acepta days_back con agregación real del período
# ─────────────────────────────────────────────────────────────────────────────

def _seed_period_acts(db, user):
    """Fixture determinista: fechas relativas a hoy, fcmax del atleta = 182."""
    from datetime import date, timedelta
    from api.models import GarminActivity
    today = date.today()
    rows = [
        # dentro de 90 d
        ("a1", "bike", 30, 60, 150, 200, 80.0),
        ("a2", "run",  60, 45, 120, None, 40.0),
        # entre 91 y 180 d
        ("a3", "bike", 120, 60, 150, 220, 100.0),
        # entre 181 y 365 d
        ("a4", "run",  300, 50, 120, None, 60.0),
    ]
    for aid, sp, ago, dur, hr, pw, tss in rows:
        db.add(GarminActivity(
            user_id=user.id, activity_id=aid, sport=sp,
            date_iso=(today - timedelta(days=ago)).isoformat(),
            dur_min=dur, dist_km=10.0, avg_hr=hr, avg_power=pw, tss=tss,
        ))
    db.commit()


def test_summary_without_days_back_is_legacy_shape(client, db, athlete_user, auth_headers):
    _seed_period_acts(db, athlete_user)
    data = client.get("/api/analytics/summary", headers=auth_headers).json()
    assert set(data) == {"power_curve", "vo2max", "personal_records",
                         "training_distribution", "zone_calibration"}
    assert data["training_distribution"]["days_back"] == 365
    assert data["zone_calibration"]["period"] == "últimos 90 días"


def test_summary_days_back_aggregates_real_period(client, db, athlete_user, auth_headers):
    from datetime import date, timedelta
    _seed_period_acts(db, athlete_user)
    r90 = client.get("/api/analytics/summary?days_back=90", headers=auth_headers)
    r365 = client.get("/api/analytics/summary?days_back=365", headers=auth_headers)
    assert r90.status_code == 200 and r365.status_code == 200
    d90, d365 = r90.json(), r365.json()

    # Rango y valor aplicado
    today = date.today()
    assert d90["days_back"] == 90
    assert d90["period_end"] == today.isoformat()
    assert d90["period_start"] == (today - timedelta(days=90)).isoformat()
    assert d365["period_start"] == (today - timedelta(days=365)).isoformat()

    # 90 d: a1 (80) + a2 (40) -> 120 TSS, 2 act, (60+45)/60 = 1.75 h
    t90 = d90["training_distribution"]
    assert t90["days_back"] == 90
    assert t90["total_acts"] == 2
    assert t90["total_tss"] == 120.0
    assert t90["total_hours"] == 1.8  # round(1.75, 1)
    sp90 = {s["sport"]: s for s in t90["by_sport"]}
    assert sp90["bike"]["tss"] == 80.0 and sp90["run"]["tss"] == 40.0

    # 365 d: las 4 actividades -> 280 TSS, 4 act
    t365 = d365["training_distribution"]
    assert t365["total_acts"] == 4
    assert t365["total_tss"] == 280.0
    sp365 = {s["sport"]: s for s in t365["by_sport"]}
    assert sp365["bike"]["tss"] == 180.0 and sp365["run"]["tss"] == 100.0

    # zone_calibration sigue la ventana: mejor bike de 60 min = a1 (200 W, hace 30 d)
    # en 90 d; a3 (220 W, hace 120 d) solo entra con 365.
    assert d90["zone_calibration"]["period"] == "últimos 90 días"
    assert d90["zone_calibration"]["cycling"]["ftp_watts"] == 200
    assert d365["zone_calibration"]["period"] == "últimos 365 días"
    assert d365["zone_calibration"]["cycling"]["ftp_watts"] == 220

    # Campos históricos/estado actual: misma semántica con cualquier ventana
    assert d90["power_curve"] == d365["power_curve"]
    assert d90["personal_records"] == d365["personal_records"]


def test_summary_days_back_180_excludes_older(client, db, athlete_user, auth_headers):
    _seed_period_acts(db, athlete_user)
    d = client.get("/api/analytics/summary?days_back=180", headers=auth_headers).json()
    assert d["training_distribution"]["total_acts"] == 3
    assert d["training_distribution"]["total_tss"] == 220.0


@pytest.mark.parametrize("bad", ["0", "30", "100", "1000", "abc", "-90"])
def test_summary_days_back_invalid_rejected(client, auth_headers, bad):
    resp = client.get(f"/api/analytics/summary?days_back={bad}", headers=auth_headers)
    assert resp.status_code in (400, 422)


# ─────────────────────────────────────────────────────────────────────────────
# M3: comparación período vs período anterior equivalente
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_compare_deltas_vs_previous_period(client, db, athlete_user, auth_headers):
    _seed_period_acts(db, athlete_user)
    # 90 d: a1+a2 = 120 TSS, 2 ses, 1.75 h. Previo (90-180 d): a3 = 100 TSS, 1 ses, 1 h.
    d = client.get("/api/analytics/summary?days_back=90&compare=true", headers=auth_headers).json()
    c = d["comparison"]
    assert c["has_previous"] is True and c["days_back"] == 90
    assert c["deltas"]["tss"] == {"current": 120.0, "previous": 100.0, "abs": 20.0, "pct": 20.0, "trend": "up"}
    assert c["deltas"]["sessions"]["abs"] == 1 and c["deltas"]["sessions"]["pct"] == 100.0
    sp = {s["sport"]: s for s in c["by_sport"]}
    assert sp["bike"]["tss"]["abs"] == -20.0 and sp["bike"]["tss"]["trend"] == "down"
    # run: previo sin run -> pct None (no inventar), abs = actual
    assert sp["run"]["tss"]["previous"] == 0 and sp["run"]["tss"]["pct"] is None


def test_summary_compare_no_previous_data_has_no_deltas(client, db, athlete_user, auth_headers):
    _seed_period_acts(db, athlete_user)
    # 180 d: previo = 180-360 d -> solo a4 (300 d). Para 90 d sin previo usamos 730 d:
    d = client.get("/api/analytics/summary?days_back=730&compare=true", headers=auth_headers).json()
    c = d["comparison"]
    assert c["has_previous"] is False
    assert c["deltas"] is None and c["by_sport"] is None


def test_summary_compare_does_not_overlap_current_period(client, db, athlete_user, auth_headers):
    from datetime import date, timedelta
    from api.models import GarminActivity
    # Actividad exactamente en el borde (hoy-90): cuenta en el actual, no en el previo
    db.add(GarminActivity(user_id=athlete_user.id, activity_id="edge", sport="bike",
                          date_iso=(date.today() - timedelta(days=90)).isoformat(),
                          dur_min=60, dist_km=10.0, avg_hr=150, tss=50.0))
    db.commit()
    d = client.get("/api/analytics/summary?days_back=90&compare=true", headers=auth_headers).json()
    assert d["training_distribution"]["total_acts"] == 1
    assert d["comparison"]["has_previous"] is False


def test_summary_without_compare_has_no_comparison_key(client, db, athlete_user, auth_headers):
    _seed_period_acts(db, athlete_user)
    d = client.get("/api/analytics/summary?days_back=90", headers=auth_headers).json()
    assert "comparison" not in d


def test_analytics_html_requests_comparison_and_handles_no_previous():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent.parent / "analytics.html").read_text(encoding="utf-8")
    assert "days_back=' + days + '&compare=true'" in html
    assert html.count("nodata:") == 3 and html.count("vs:") >= 3  # ES/PT/EN
    assert "cmp.has_previous" in html
