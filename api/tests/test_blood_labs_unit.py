"""
Tests — Blood Labs Training Impact Service (Sprint 22)
======================================================
Tests unitarios puros: sin DB, sin FastAPI, sin conftest.

Correr: pytest api/tests/test_blood_labs_unit.py -v --noconftest
"""
import sys
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from api.services.blood_labs_impact_service import (
    compute_training_impact,
    compute_team_labs_status,
    _eval_ferritin,
    _eval_hemoglobin,
    _eval_vitamin_d,
    _eval_cortisol,
    _eval_ck,
    _eval_testosterone,
    _eval_tsh,
    _eval_vitamin_b12,
    _eval_urea,
    _compute_trs,
    _compute_disciplines,
    _build_supplements,
)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Individual marker evaluations
# ─────────────────────────────────────────────────────────────────────────────

class TestFerritinEval:
    def test_critical_below_15(self):
        m = _eval_ferritin(12.0, "M")
        assert m.status == "critical"
        assert m.restriction_score >= 30
        assert m.intensity_cap == "zone1"
        assert m.volume_modifier <= 0.45

    def test_warning_15_to_30(self):
        m = _eval_ferritin(22.0, "M")
        assert m.status == "warning"
        assert m.intensity_cap == "zone2"
        assert 0.60 <= m.volume_modifier <= 0.70

    def test_suboptimal_30_to_50(self):
        m = _eval_ferritin(40.0, "M")
        assert m.status == "suboptimal"
        assert m.volume_modifier >= 0.80

    def test_optimal_above_50(self):
        m = _eval_ferritin(80.0, "M")
        assert m.status == "ok"
        assert m.restriction_score == 0
        assert m.volume_modifier == 1.0
        assert m.intensity_cap is None

    def test_supplement_hint_critical(self):
        m = _eval_ferritin(10.0, "M")
        assert m.supplement_hint is not None
        assert "hierro" in m.supplement_hint.lower() or "hierro" in m.supplement_hint.lower()


class TestHemoglobinEval:
    def test_critical_male_below_13_5(self):
        m = _eval_hemoglobin(12.8, "M")
        assert m.status == "critical"
        assert m.restriction_score >= 35

    def test_critical_female_below_12_5(self):
        m = _eval_hemoglobin(12.0, "F")
        assert m.status == "critical"

    def test_warning_male_below_14(self):
        m = _eval_hemoglobin(13.6, "M")
        assert m.status == "warning"

    def test_ok_male_above_14(self):
        m = _eval_hemoglobin(15.5, "M")
        assert m.status == "ok"
        assert m.restriction_score == 0

    def test_ok_female_above_13_5(self):
        m = _eval_hemoglobin(14.0, "F")
        assert m.status == "ok"


class TestVitaminDEval:
    def test_critical_below_20(self):
        m = _eval_vitamin_d(15.0, "M")
        assert m.status == "critical"
        assert m.volume_modifier < 0.80

    def test_warning_20_to_30(self):
        m = _eval_vitamin_d(25.0, "M")
        assert m.status == "warning"
        assert m.volume_modifier < 1.0

    def test_suboptimal_30_to_40(self):
        m = _eval_vitamin_d(35.0, "M")
        assert m.status == "suboptimal"

    def test_optimal_above_40(self):
        m = _eval_vitamin_d(55.0, "M")
        assert m.status == "ok"
        assert m.restriction_score == 0


class TestCortisolEval:
    def test_critical_above_30(self):
        m = _eval_cortisol(35.0, "M")
        assert m.status == "critical"
        assert m.volume_modifier <= 0.45

    def test_warning_22_to_30(self):
        m = _eval_cortisol(24.0, "M")
        assert m.status == "warning"

    def test_ok_normal(self):
        m = _eval_cortisol(12.0, "M")
        assert m.status == "ok"
        assert m.restriction_score == 0


class TestCKEval:
    def test_critical_above_1000(self):
        m = _eval_ck(1500.0, "M")
        assert m.status == "critical"
        assert m.volume_modifier <= 0.35

    def test_warning_500_to_1000(self):
        m = _eval_ck(700.0, "M")
        assert m.status == "warning"

    def test_suboptimal_300_to_500(self):
        m = _eval_ck(400.0, "M")
        assert m.status == "suboptimal"

    def test_ok_below_300(self):
        m = _eval_ck(120.0, "M")
        assert m.status == "ok"


class TestTestosteroneEval:
    def test_critical_male_below_200(self):
        m = _eval_testosterone(180.0, "M")
        assert m.status == "critical"
        assert m.restriction_score >= 20

    def test_warning_male_200_350(self):
        m = _eval_testosterone(280.0, "M")
        assert m.status == "warning"

    def test_ok_male_above_350(self):
        m = _eval_testosterone(550.0, "M")
        assert m.status == "ok"

    def test_female_low_threshold(self):
        m = _eval_testosterone(10.0, "F")
        assert m.status == "warning"

    def test_female_ok(self):
        m = _eval_testosterone(25.0, "F")
        assert m.status == "ok"


class TestTSHEval:
    def test_critical_high(self):
        m = _eval_tsh(6.0, "M")
        assert m.status == "critical"

    def test_critical_low(self):
        m = _eval_tsh(0.2, "M")
        assert m.status == "critical"

    def test_warning_borderline_high(self):
        m = _eval_tsh(4.0, "M")
        assert m.status == "warning"

    def test_ok_normal(self):
        m = _eval_tsh(1.5, "M")
        assert m.status == "ok"


class TestVitaminB12Eval:
    def test_critical_below_200(self):
        m = _eval_vitamin_b12(150.0, "M")
        assert m.status == "critical"

    def test_warning_200_to_300(self):
        m = _eval_vitamin_b12(250.0, "M")
        assert m.status == "warning"

    def test_ok_above_300(self):
        m = _eval_vitamin_b12(500.0, "M")
        assert m.status == "ok"


class TestUreaEval:
    def test_warning_above_9(self):
        m = _eval_urea(10.0, "M")
        assert m.status == "warning"

    def test_suboptimal_7_to_9(self):
        m = _eval_urea(7.5, "M")
        assert m.status == "suboptimal"

    def test_ok_normal(self):
        m = _eval_urea(5.0, "M")
        assert m.status == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: TRS computation
# ─────────────────────────────────────────────────────────────────────────────

class TestTRSComputation:
    def test_no_restrictions_trs_100(self):
        markers = [
            _eval_ferritin(80.0, "M"),
            _eval_hemoglobin(15.0, "M"),
            _eval_vitamin_d(50.0, "M"),
        ]
        trs, label, color = _compute_trs(markers)
        assert trs == 100
        assert label == "verde"

    def test_critical_ferritin_trs_below_65(self):
        markers = [
            _eval_ferritin(10.0, "M"),    # critical: -35
            _eval_hemoglobin(12.5, "M"),  # critical: -38
        ]
        trs, label, color = _compute_trs(markers)
        assert trs < 40
        assert label == "rojo"

    def test_single_warning_trs_yellow(self):
        markers = [
            _eval_ferritin(80.0, "M"),    # ok: 0
            _eval_hemoglobin(13.7, "M"),  # warning: -20
            _eval_vitamin_d(50.0, "M"),   # ok: 0
        ]
        trs, label, color = _compute_trs(markers)
        assert 65 <= trs < 85
        assert label == "amarillo"

    def test_trs_never_below_0(self):
        markers = [
            _eval_ferritin(5.0, "M"),
            _eval_hemoglobin(10.0, "M"),
            _eval_cortisol(40.0, "M"),
            _eval_ck(2000.0, "M"),
            _eval_testosterone(100.0, "M"),
        ]
        trs, _, _ = _compute_trs(markers)
        assert trs >= 0

    def test_trs_never_above_100(self):
        markers = [_eval_vitamin_d(60.0, "M")]
        trs, _, _ = _compute_trs(markers)
        assert trs <= 100


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Discipline restrictions
# ─────────────────────────────────────────────────────────────────────────────

class TestDisciplineRestrictions:
    def test_all_ok_means_any_intensity(self):
        markers = [
            _eval_ferritin(80.0, "M"),
            _eval_hemoglobin(15.0, "M"),
        ]
        disciplines = _compute_disciplines(markers)
        for d in disciplines:
            assert d.max_intensity == "any"
            assert d.volume_modifier >= 0.95

    def test_critical_ck_limits_run_more_than_swim(self):
        markers = [_eval_ck(1500.0, "M")]
        disciplines = _compute_disciplines(markers)
        run_d = next(d for d in disciplines if d.discipline == "run")
        swim_d = next(d for d in disciplines if d.discipline == "swim")
        assert run_d.volume_modifier <= swim_d.volume_modifier

    def test_critical_ferritin_limits_all_high_intensity(self):
        markers = [_eval_ferritin(10.0, "M")]
        disciplines = _compute_disciplines(markers)
        for d in disciplines:
            assert d.max_intensity in ("zone1", "zone2")

    def test_four_disciplines_always_returned(self):
        markers = [_eval_vitamin_d(25.0, "M")]
        disciplines = _compute_disciplines(markers)
        discipline_names = {d.discipline for d in disciplines}
        assert discipline_names == {"swim", "bike", "run", "strength"}

    def test_cortisol_limits_bike_volume(self):
        markers = [_eval_cortisol(32.0, "M")]
        disciplines = _compute_disciplines(markers)
        bike = next(d for d in disciplines if d.discipline == "bike")
        assert bike.volume_modifier <= 0.75


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Supplement builder
# ─────────────────────────────────────────────────────────────────────────────

class TestSupplementBuilder:
    def test_critical_markers_add_supplements(self):
        markers = [_eval_ferritin(10.0, "M")]
        supplements = _build_supplements(markers)
        assert len(supplements) >= 1
        assert any("hierro" in s["recommendation"].lower() or "Hierro" in s["recommendation"] for s in supplements)

    def test_ok_markers_no_supplements(self):
        markers = [
            _eval_ferritin(80.0, "M"),
            _eval_hemoglobin(15.0, "M"),
        ]
        supplements = _build_supplements(markers)
        assert len(supplements) == 0

    def test_no_duplicate_supplements(self):
        markers = [_eval_ferritin(10.0, "M"), _eval_ferritin(10.0, "M")]
        supplements = _build_supplements(markers)
        recs = [s["recommendation"] for s in supplements]
        assert len(recs) == len(set(recs))


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: compute_training_impact integration
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeTrainingImpact:
    def test_empty_values_returns_trs_100(self):
        report = compute_training_impact({}, sex="M", ctl=80, exam_date="2026-01-01")
        assert report.trs == 100
        assert report.trs_label == "verde"

    def test_unknown_markers_produce_no_restriction(self):
        report = compute_training_impact({"creatinine": 1.0, "ldl": 120}, "M")
        assert report.trs == 100
        assert not report.markers_evaluated

    def test_optimal_labs_trs_100(self):
        values = {"ferritin": 90.0, "hb": 15.5, "vitamin_d": 55.0}
        report = compute_training_impact(values, sex="M", ctl=80)
        assert report.trs == 100
        assert report.ctl_volume_modifier == 1.0
        assert not report.medical_referral

    def test_critical_ferritin_and_hb_trs_red(self):
        values = {"ferritin": 8.0, "hb": 12.0}
        report = compute_training_impact(values, sex="M", ctl=100)
        assert report.trs < 40
        assert report.trs_label == "rojo"
        assert report.medical_referral
        assert report.ctl_volume_modifier < 0.50

    def test_warning_vitamin_d_trs_below_100(self):
        # vitamin_d warning = restriction_score 8 → TRS 92 → verde but below 100
        values = {"vitamin_d": 22.0}
        report = compute_training_impact(values, sex="M", ctl=70)
        assert report.trs < 100
        assert report.ctl_volume_modifier < 1.0  # volume is reduced

    def test_disciplines_always_4(self):
        values = {"ferritin": 35.0, "vitamin_d": 25.0}
        report = compute_training_impact(values, sex="M")
        assert len(report.disciplines) == 4

    def test_key_actions_not_empty(self):
        values = {"ferritin": 10.0}
        report = compute_training_impact(values, sex="M", ctl=80)
        assert len(report.key_actions) >= 1

    def test_next_labs_days_shorter_for_critical(self):
        critical_report = compute_training_impact({"ferritin": 8.0}, "M")
        ok_report = compute_training_impact({"ferritin": 90.0}, "M")
        assert critical_report.next_labs_in_days < ok_report.next_labs_in_days

    def test_female_different_thresholds(self):
        # Hb 13.0 es warning en hombres pero ok en mujeres (umbral=12.5)
        report_m = compute_training_impact({"hb": 13.0}, sex="M")
        report_f = compute_training_impact({"hb": 13.0}, sex="F")
        assert report_m.trs <= report_f.trs  # hombres más restringidos

    def test_ctl_included_in_volume_recommendation(self):
        values = {"ferritin": 10.0}
        report_high_ctl = compute_training_impact(values, "M", ctl=120)
        report_low_ctl  = compute_training_impact(values, "M", ctl=30)
        # Acciones deben mencionar CTL diferente
        actions_high = " ".join(report_high_ctl.key_actions)
        actions_low  = " ".join(report_low_ctl.key_actions)
        # At least one report should reference CTL numerically
        assert any(char.isdigit() for char in actions_high + actions_low)

    def test_medical_referral_on_critical(self):
        values = {"tsh": 6.5}
        report = compute_training_impact(values, "M")
        assert report.medical_referral

    def test_no_medical_referral_all_ok(self):
        values = {"ferritin": 80.0, "hb": 15.0, "vitamin_d": 50.0}
        report = compute_training_impact(values, "M")
        assert not report.medical_referral

    def test_supplement_protocol_for_iron_deficiency(self):
        values = {"ferritin": 12.0, "hb": 13.0}
        report = compute_training_impact(values, "M")
        assert len(report.supplements) >= 1
        supplement_text = " ".join(s["recommendation"] for s in report.supplements).lower()
        assert "hierro" in supplement_text

    def test_exam_date_preserved(self):
        report = compute_training_impact({}, "M", exam_date="2026-05-01")
        assert report.exam_date == "2026-05-01"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: compute_team_labs_status
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeTeamLabsStatus:
    def _athlete(self, user_id: str, ferritin: float, hb: float, sex: str = "M", ctl: float = 60) -> dict:
        import json
        return {
            "user_id":    user_id,
            "name":       f"Atleta {user_id}",
            "sex":        sex,
            "values_json": json.dumps({"ferritin": ferritin, "hb": hb}),
            "exam_date":  "2026-06-01",
            "ctl":        ctl,
        }

    def test_empty_input(self):
        result = compute_team_labs_status([])
        assert result["athletes_count"] == 0
        assert result["team_avg_trs"] == 100

    def test_all_ok_no_alerts(self):
        athletes = [
            self._athlete("a1", ferritin=90, hb=15.5),
            self._athlete("a2", ferritin=75, hb=14.8),
        ]
        result = compute_team_labs_status(athletes)
        assert result["team_avg_trs"] == 100
        assert len(result["critical_athletes"]) == 0
        assert len(result["alerts"]) == 0

    def test_critical_athlete_in_critical_list(self):
        athletes = [
            self._athlete("crit1", ferritin=8, hb=11.5),    # should be critical
            self._athlete("ok1",   ferritin=80, hb=15.0),   # should be ok
        ]
        result = compute_team_labs_status(athletes)
        crit_ids = [a["user_id"] for a in result["critical_athletes"]]
        ok_ids   = [a["user_id"] for a in result["ok_athletes"]]
        assert "crit1" in crit_ids
        assert "ok1" in ok_ids

    def test_team_avg_trs_calculation(self):
        athletes = [
            self._athlete("a1", ferritin=8, hb=11.5),   # ~TRS 30
            self._athlete("a2", ferritin=90, hb=15.0),  # ~TRS 100
        ]
        result = compute_team_labs_status(athletes)
        assert 30 <= result["team_avg_trs"] <= 85

    def test_athletes_count_correct(self):
        athletes = [
            self._athlete("a1", 80, 15),
            self._athlete("a2", 70, 14),
            self._athlete("a3", 60, 13.5),
        ]
        result = compute_team_labs_status(athletes)
        assert result["athletes_count"] == 3

    def test_alerts_generated_for_critical(self):
        athletes = [self._athlete("crit", ferritin=5, hb=10)]
        result = compute_team_labs_status(athletes)
        assert len(result["alerts"]) >= 1
        assert result["alerts"][0]["severity"] == "critical"

    def test_invalid_json_handled_gracefully(self):
        athletes = [{
            "user_id": "bad", "name": "Bad", "sex": "M",
            "values_json": "not-valid-json", "exam_date": "2026-01-01", "ctl": 50
        }]
        result = compute_team_labs_status(athletes)
        assert result["athletes_count"] == 1

    def test_critical_athletes_sorted_by_trs_ascending(self):
        athletes = [
            self._athlete("worse", ferritin=5, hb=10),
            self._athlete("bad",   ferritin=10, hb=11),
        ]
        result = compute_team_labs_status(athletes)
        crits = result["critical_athletes"]
        if len(crits) >= 2:
            assert crits[0]["trs"] <= crits[1]["trs"]
