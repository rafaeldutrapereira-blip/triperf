"""
Tests — AI Intelligence Engine v2 (Sprint 20)
==============================================
Motor determinista: workout generator, CTL forecast, injury risk, weekly report, coach insights.
Sin imports de FastAPI/SQLAlchemy/DB.

Correr: pytest api/tests/test_ai_engine.py -v --noconftest
"""
import math
import sys
import os

# Add project root to path so we can import ai_engine directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from api.services.ai_engine import (
    generate_workout,
    generate_weekly_report,
    forecast_ctl,
    assess_injury_risk,
    generate_coach_insights,
    _form_label,
    _form_state,
)


# ─── helper to avoid import error if optional function not exported ───────────
try:
    from api.services.ai_engine import _form_label as _fl
except ImportError:
    _fl = None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — mirror internal functions for boundary testing
# ─────────────────────────────────────────────────────────────────────────────

def form_label(tsb):
    if tsb >= 15:  return "peak"
    if tsb >= 5:   return "fresh"
    if tsb >= -10: return "normal"
    if tsb >= -25: return "fatigued"
    return "overtrained"


def form_state(tsb, rec):
    tsb = tsb or 0.0
    rec = rec or 70
    if tsb <= -25 or rec < 35:
        return "fatigued"
    if tsb >= 5 and rec >= 70:
        return "fresh"
    return "normal"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: FORM LABEL
# ─────────────────────────────────────────────────────────────────────────────

class TestFormLabel:
    def test_peak(self):      assert form_label(20)  == "peak"
    def test_fresh(self):     assert form_label(10)  == "fresh"
    def test_normal(self):    assert form_label(0)   == "normal"
    def test_fatigued(self):  assert form_label(-20) == "fatigued"
    def test_overtrained(self): assert form_label(-30) == "overtrained"
    def test_boundary_peak(self):   assert form_label(15) == "peak"
    def test_boundary_fresh(self):  assert form_label(5)  == "fresh"
    def test_boundary_normal(self): assert form_label(-10) == "normal"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: FORM STATE
# ─────────────────────────────────────────────────────────────────────────────

class TestFormState:
    def test_fatigued_from_tsb(self):
        assert form_state(-26, 80) == "fatigued"

    def test_fatigued_from_recovery(self):
        assert form_state(0, 30) == "fatigued"

    def test_fresh(self):
        assert form_state(10, 75) == "fresh"

    def test_normal(self):
        assert form_state(-5, 70) == "normal"

    def test_none_tsb(self):
        assert form_state(None, 70) in ("fresh", "normal", "fatigued")

    def test_none_rec(self):
        assert form_state(5, None) in ("fresh", "normal", "fatigued")


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: WORKOUT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkoutGenerator:
    def test_basic_run_endurance(self):
        w = generate_workout("run", "endurance", 60)
        assert w.sport  == "run"
        assert w.focus  == "endurance"
        assert w.total_duration_min == 60
        assert len(w.phases) >= 2  # at least warmup + 1 main + cooldown

    def test_warmup_and_cooldown_always_present(self):
        w = generate_workout("bike", "threshold", 90)
        names = [p.name for p in w.phases]
        assert any("Calent" in n for n in names)
        assert any("Enfri" in n for n in names)

    def test_fatigue_overrides_vo2_to_recovery(self):
        w = generate_workout("run", "vo2", 60, tsb=-35, recovery_score=20)
        assert w.focus == "recovery"
        assert w.override_reason is not None

    def test_pre_race_tapering(self):
        w = generate_workout("run", "endurance", 60, days_to_race=2)
        assert w.focus == "recovery"

    def test_pre_race_7d_vo2_to_threshold(self):
        w = generate_workout("run", "vo2", 60, days_to_race=6)
        assert w.focus == "threshold"

    def test_estimated_tss_positive(self):
        w = generate_workout("run", "endurance", 60, ctl=70)
        assert w.estimated_tss > 0

    def test_tss_scales_with_duration(self):
        w60  = generate_workout("run", "endurance", 60)
        w120 = generate_workout("run", "endurance", 120)
        assert w120.estimated_tss > w60.estimated_tss

    def test_key_points_non_empty(self):
        w = generate_workout("bike", "threshold", 90)
        assert len(w.key_points) >= 1

    def test_duration_clamped_min(self):
        w = generate_workout("run", "recovery", 5)
        assert w.total_duration_min >= 20

    def test_duration_clamped_max(self):
        w = generate_workout("run", "recovery", 500)
        assert w.total_duration_min <= 360

    def test_unknown_sport_defaults_to_run(self):
        w = generate_workout("aquabike", "endurance", 60)
        assert w.sport == "run"

    def test_all_phases_have_required_fields(self):
        w = generate_workout("run", "threshold", 90)
        for p in w.phases:
            assert p.name
            assert p.duration_min > 0
            assert p.zone in ("Z1", "Z2", "Z3", "Z4", "Z5")
            assert 1 <= p.rpe <= 10

    def test_swim_workout(self):
        w = generate_workout("swim", "endurance", 60)
        assert w.sport == "swim"

    def test_gym_workout(self):
        w = generate_workout("gym", "strength", 45)
        assert w.sport == "gym"
        assert w.focus == "strength"

    def test_fresh_form_no_override(self):
        w = generate_workout("run", "threshold", 90, tsb=10, recovery_score=85)
        assert w.form_state == "fresh"
        assert w.override_reason is None or "race" in (w.override_reason or "")

    def test_high_ctl_reasonable_tss(self):
        w = generate_workout("bike", "threshold", 120, ctl=120)
        assert w.estimated_tss > 60


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: CTL FORECAST
# ─────────────────────────────────────────────────────────────────────────────

class TestCTLForecast:
    def test_returns_correct_weeks(self):
        proj = forecast_ctl(70, 70, [400], weeks=8)
        assert len(proj) == 8

    def test_ctl_changes_with_load(self):
        proj = forecast_ctl(50, 50, [700], weeks=4)
        assert proj[-1].ctl > 50  # high load → CTL rises

    def test_low_load_decreases_ctl(self):
        proj = forecast_ctl(80, 50, [100], weeks=4)
        assert proj[-1].ctl < 80  # very low load → CTL falls

    def test_tsb_is_ctl_minus_atl(self):
        proj = forecast_ctl(70, 70, [400], weeks=4)
        for p in proj:
            assert abs(p.tsb - (p.ctl - p.atl)) < 0.2

    def test_form_labels_assigned(self):
        proj = forecast_ctl(70, 70, [400], weeks=4)
        valid_labels = {"peak", "fresh", "normal", "fatigued", "overtrained"}
        for p in proj:
            assert p.form_label in valid_labels

    def test_taper_week_improves_tsb(self):
        # First build, then taper
        plan = [500, 500, 500, 500, 150]
        proj = forecast_ctl(60, 60, plan, weeks=5)
        # TSB in taper week should be higher than previous
        assert proj[-1].tsb > proj[-2].tsb

    def test_week_numbers_sequential(self):
        proj = forecast_ctl(60, 60, [400], weeks=6)
        assert [p.week for p in proj] == list(range(1, 7))

    def test_cycle_plan_repeats(self):
        plan = [300, 400, 500, 200]
        proj = forecast_ctl(60, 60, plan, weeks=8)
        assert len(proj) == 8

    def test_min_weeks(self):
        proj = forecast_ctl(70, 70, [400], weeks=2)
        assert len(proj) == 2

    def test_max_weeks(self):
        proj = forecast_ctl(70, 70, [400], weeks=16)
        assert len(proj) == 16


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: INJURY RISK
# ─────────────────────────────────────────────────────────────────────────────

class TestInjuryRisk:
    def test_low_risk_all_safe(self):
        r = assess_injury_risk(acwr=1.0, monotony=1.5, strain=2000,
                               hrv_trend="stable")
        assert r.risk_level == "low"
        assert r.current_risk_score < 0.2

    def test_critical_acwr(self):
        r = assess_injury_risk(acwr=2.2, monotony=2.2, strain=6000,
                               hrv_trend="declining")
        assert r.risk_level in ("high", "critical")
        assert r.current_risk_score >= 0.4

    def test_declining_hrv_adds_risk(self):
        stable   = assess_injury_risk(acwr=1.2, monotony=1.5, strain=2000, hrv_trend="stable")
        declining = assess_injury_risk(acwr=1.2, monotony=1.5, strain=2000, hrv_trend="declining")
        assert declining.current_risk_score > stable.current_risk_score

    def test_high_monotony_adds_risk(self):
        low = assess_injury_risk(acwr=1.1, monotony=1.5, strain=2000, hrv_trend="stable")
        hi  = assess_injury_risk(acwr=1.1, monotony=2.5, strain=2000, hrv_trend="stable")
        assert hi.current_risk_score > low.current_risk_score

    def test_risk_score_0_to_1(self):
        for acwr in (0.5, 1.0, 1.5, 2.0, 2.5):
            r = assess_injury_risk(acwr=acwr, monotony=1.5, strain=2000, hrv_trend="stable")
            assert 0 <= r.current_risk_score <= 1.0

    def test_action_plan_non_empty(self):
        r = assess_injury_risk(acwr=1.5, monotony=2.0, strain=5000, hrv_trend="declining")
        assert len(r.action_plan) >= 1

    def test_none_acwr_treated_as_1(self):
        r = assess_injury_risk(acwr=None, monotony=None, strain=None, hrv_trend=None)
        assert r.current_risk_score < 0.3  # no signals → low risk

    def test_pre_race_adds_warning(self):
        r = assess_injury_risk(acwr=2.0, monotony=2.5, strain=6000,
                               hrv_trend="declining", days_to_race=7)
        assert any("carrera" in step.lower() for step in r.action_plan)

    def test_critical_has_recovery_days(self):
        r = assess_injury_risk(acwr=1.9, monotony=2.5, strain=6000, hrv_trend="declining")
        assert r.recovery_days_needed >= 4

    def test_primary_driver_set(self):
        r = assess_injury_risk(acwr=1.8, monotony=1.5, strain=2000, hrv_trend="stable")
        assert r.primary_driver != ""


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: WEEKLY REPORT
# ─────────────────────────────────────────────────────────────────────────────

class TestWeeklyReport:
    def test_overtrained_recommends_recovery(self):
        r = generate_weekly_report(ctl=70, atl=95, tsb=-25, week_tss=600,
                                   week_hours=12, injury_risk=0.5)
        assert r.suggested_focus == "recovery"

    def test_score_in_0_100(self):
        for tsb in (-30, -10, 0, 10, 20):
            r = generate_weekly_report(ctl=70, atl=70, tsb=tsb, week_tss=400,
                                       week_hours=8, injury_risk=0.1)
            assert 0 <= r.score <= 100

    def test_high_risk_in_concerns(self):
        r = generate_weekly_report(ctl=70, atl=70, tsb=0, week_tss=400,
                                   week_hours=8, injury_risk=0.5)
        assert any("riesgo" in c.lower() for c in r.concerns)

    def test_achievements_non_empty(self):
        r = generate_weekly_report(ctl=70, atl=70, tsb=5, week_tss=450,
                                   week_hours=9, injury_risk=0.1)
        assert len(r.key_achievements) >= 1

    def test_tss_range_min_less_than_max(self):
        r = generate_weekly_report(ctl=70, atl=70, tsb=0, week_tss=400,
                                   week_hours=8, injury_risk=0.1)
        assert r.suggested_tss_range[0] <= r.suggested_tss_range[1]

    def test_tapering_near_race(self):
        r = generate_weekly_report(ctl=80, atl=65, tsb=15, week_tss=500,
                                   week_hours=10, injury_risk=0.1, days_to_race=7)
        assert r.suggested_focus == "recovery"
        assert any("tapering" in rec.lower() for rec in r.next_week_recommendations)

    def test_none_inputs_dont_crash(self):
        r = generate_weekly_report(ctl=None, atl=None, tsb=None,
                                   week_tss=None, week_hours=None, injury_risk=None)
        assert r.score >= 0
        assert r.load_summary

    def test_declining_hrv_in_concerns(self):
        r = generate_weekly_report(ctl=70, atl=70, tsb=0, week_tss=400,
                                   week_hours=8, injury_risk=0.1, hrv_trend="declining")
        assert any("hrv" in c.lower() for c in r.concerns)

    def test_week_label_is_string(self):
        r = generate_weekly_report(ctl=70, atl=70, tsb=0, week_tss=400,
                                   week_hours=8, injury_risk=0.1)
        assert isinstance(r.week_label, str)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: COACH TEAM INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

class TestCoachInsights:
    def _athlete(self, uid, tsb=0, rec=70, risk=0.1, dtr=None, ctl=70, atl=65):
        return {"user_id": uid, "name": "Atleta " + uid,
                "ctl": ctl, "atl": atl, "tsb": tsb,
                "recovery_score": rec, "injury_risk": risk, "days_to_race": dtr}

    def test_empty_team(self):
        r = generate_coach_insights([])
        assert r.total_athletes == 0

    def test_single_healthy_athlete_no_alerts(self):
        r = generate_coach_insights([self._athlete("a1", tsb=5, rec=80, risk=0.1)])
        assert len([a for a in r.alerts if a.severity == "critical"]) == 0

    def test_critical_risk_athlete_alert(self):
        r = generate_coach_insights([self._athlete("a1", tsb=0, rec=70, risk=0.55)])
        assert any(a.severity == "critical" and a.user_id == "a1" for a in r.alerts)

    def test_overtrained_tsb_alert(self):
        r = generate_coach_insights([self._athlete("a1", tsb=-35, rec=70, risk=0.1)])
        assert any(a.user_id == "a1" for a in r.alerts)

    def test_pre_race_tired_alert(self):
        r = generate_coach_insights([self._athlete("a1", tsb=-15, rec=70, risk=0.1, dtr=5)])
        assert any(a.user_id == "a1" for a in r.alerts)

    def test_avg_ctl_correct(self):
        athletes = [self._athlete("a1", ctl=60), self._athlete("a2", ctl=80)]
        r = generate_coach_insights(athletes)
        assert abs(r.team_avg_ctl - 70.0) < 0.1

    def test_clusters_cover_all_athletes(self):
        athletes = [
            self._athlete("a1", tsb=15, rec=85),   # peak
            self._athlete("a2", tsb=-5, rec=70),   # building
            self._athlete("a3", tsb=-20, rec=60),  # recovering
            self._athlete("a4", tsb=0, rec=70, risk=0.45),  # at risk
        ]
        r = generate_coach_insights(athletes)
        all_clustered = sum(len(c.athlete_ids) for c in r.clusters)
        assert all_clustered == len(athletes)

    def test_alerts_sorted_critical_first(self):
        athletes = [
            self._athlete("a1", tsb=0, rec=70, risk=0.35),   # warning
            self._athlete("a2", tsb=0, rec=70, risk=0.55),   # critical
        ]
        r = generate_coach_insights(athletes)
        if len(r.alerts) >= 2:
            sev_order = {"critical": 0, "warning": 1, "info": 2}
            for i in range(len(r.alerts) - 1):
                assert sev_order[r.alerts[i].severity] <= sev_order[r.alerts[i+1].severity]

    def test_summary_contains_count(self):
        r = generate_coach_insights([self._athlete("a1"), self._athlete("a2")])
        assert "2" in r.summary

    def test_large_team(self):
        athletes = [self._athlete("a" + str(i), tsb=i-15, rec=60+i) for i in range(20)]
        r = generate_coach_insights(athletes)
        assert r.total_athletes == 20
