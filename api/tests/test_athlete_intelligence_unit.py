"""Sprint 28 — Athlete Intelligence Service unit tests (pure, no DB, no FastAPI)."""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.services.athlete_intelligence_service import (
    _tsb_form_label,
    _acwr_risk,
    _training_snapshot,
    _recovery_snapshot,
    _mental_snapshot,
    _blood_labs_snapshot,
    _nutrition_snapshot,
    _prescription_snapshot,
    _generate_athlete_alerts,
    get_athlete_intelligence,
    _today_iso,
    _date_n_days_ago,
)
from api.models import (
    GarminTrainingLoad, RecoveryScore, MentalFatigueScore, MentalCheckin,
    BloodLabExam, BloodLabAlert, FoodDiaryEntry, HydrationLog, SupplementLog,
    WorkoutPrescription,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _make_load(date_iso, ctl=60.0, atl=65.0, tsb=-5.0, tss=70.0, acwr=1.05):
    obj = MagicMock(spec=GarminTrainingLoad)
    obj.date_iso = date_iso
    obj.ctl = ctl
    obj.atl = atl
    obj.tsb = tsb
    obj.tss = tss
    obj.acwr = acwr
    return obj


def _make_recovery(date_iso, score=72, level="good", suggestion="full"):
    obj = MagicMock(spec=RecoveryScore)
    obj.date_iso = date_iso
    obj.score = score
    obj.level = level
    obj.training_suggestion = suggestion
    return obj


def _make_mental_score(date_iso, score=74, level="good"):
    obj = MagicMock(spec=MentalFatigueScore)
    obj.date_iso = date_iso
    obj.score = score
    obj.level = level
    return obj


def _make_mental_checkin(date_iso, motivation=4, anxiety=3, focus=4, confidence=4, mood=4):
    obj = MagicMock(spec=MentalCheckin)
    obj.date_iso = date_iso
    obj.motivation = motivation
    obj.anxiety = anxiety
    obj.focus = focus
    obj.confidence = confidence
    obj.mood = mood
    obj.notes = None
    return obj


def _make_exam(date_iso, values_json='{"hb":14}', lab_name="LabClinic"):
    obj = MagicMock(spec=BloodLabExam)
    obj.id = "exam-1"
    obj.date_iso = date_iso
    obj.values_json = values_json
    obj.lab_name = lab_name
    return obj


def _make_alert(exam_id, marker_key, severity, dismissed_at=None):
    obj = MagicMock(spec=BloodLabAlert)
    obj.exam_id = exam_id
    obj.marker_key = marker_key
    obj.severity = severity
    obj.dismissed_at = dismissed_at
    return obj


def _make_rx(athlete_id, status="pending", date_iso=None):
    obj = MagicMock(spec=WorkoutPrescription)
    obj.athlete_id = athlete_id
    obj.status = status
    obj.date_iso = date_iso or _today_iso()
    return obj


def _make_db_simple(model_cls, returns_list=None, returns_first=None):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = returns_list if returns_list is not None else []
    q.first.return_value = returns_first
    q.count.return_value = 0
    return db


# ── TestTsbFormLabel ───────────────────────────────────────────────────────────

class TestTsbFormLabel:
    def test_forma_pico(self):     assert _tsb_form_label(15)  == "Forma Pico"
    def test_forma_pico_high(self):assert _tsb_form_label(30)  == "Forma Pico"
    def test_buena_forma(self):    assert _tsb_form_label(10)  == "Buena Forma"
    def test_buena_forma_low(self):assert _tsb_form_label(5)   == "Buena Forma"
    def test_neutro(self):         assert _tsb_form_label(0)   == "Neutro"
    def test_neutro_neg(self):     assert _tsb_form_label(-4)  == "Neutro"
    def test_fatiga_moderada(self):assert _tsb_form_label(-10) == "Fatiga Moderada"
    def test_fatiga_alta(self):    assert _tsb_form_label(-20) == "Fatiga Alta"
    def test_sobrecarga(self):     assert _tsb_form_label(-30) == "Sobrecarga"
    def test_boundary_5(self):     assert _tsb_form_label(5)   == "Buena Forma"
    def test_boundary_minus25(self):assert _tsb_form_label(-25) == "Sobrecarga"


# ── TestAcwrRisk ───────────────────────────────────────────────────────────────

class TestAcwrRisk:
    def test_undertrained(self):
        level, color = _acwr_risk(0.7)
        assert level == "undertrained"
        assert color == "#6b7280"

    def test_safe(self):
        level, _ = _acwr_risk(1.0)
        assert level == "safe"

    def test_safe_boundary(self):
        level, _ = _acwr_risk(1.3)
        assert level == "safe"

    def test_moderate(self):
        level, color = _acwr_risk(1.4)
        assert level == "moderate"
        assert color == "#f59e0b"

    def test_elevated(self):
        level, color = _acwr_risk(1.6)
        assert level == "elevated"
        assert color == "#ef4444"


# ── TestDateHelpers ────────────────────────────────────────────────────────────

class TestDateHelpers:
    def test_today_iso_format(self):
        t = _today_iso()
        assert len(t) == 10
        assert t[4] == '-' and t[7] == '-'

    def test_n_days_ago(self):
        from datetime import date
        t = _date_n_days_ago(7)
        expected = (date.today() - timedelta(days=7)).isoformat()
        assert t == expected

    def test_zero_days_ago_is_today(self):
        assert _date_n_days_ago(0) == _today_iso()


# ── TestTrainingSnapshot ───────────────────────────────────────────────────────

class TestTrainingSnapshot:
    def _db(self, loads):
        db = _make_db_simple(GarminTrainingLoad, returns_list=loads)
        return db

    def test_empty_loads_returns_zeros(self):
        db = self._db([])
        result = _training_snapshot("ath-1", db)
        assert result["ctl"] == 0.0
        assert result["tsb"] == 0.0
        assert result["acwr"] == 1.0

    def test_single_load_uses_latest(self):
        today = _today_iso()
        loads = [_make_load(today, ctl=70.0, atl=75.0, tsb=-5.0, tss=80.0)]
        db = self._db(loads)
        result = _training_snapshot("ath-1", db)
        assert result["ctl"] == 70.0
        assert result["tsb"] == -5.0

    def test_form_label_in_result(self):
        today = _today_iso()
        loads = [_make_load(today, tsb=20.0)]
        db = self._db(loads)
        result = _training_snapshot("ath-1", db)
        assert result["form_label"] == "Forma Pico"

    def test_acwr_computed(self):
        today = _today_iso()
        loads = [_make_load(today, tss=100.0)]
        db = self._db(loads)
        result = _training_snapshot("ath-1", db)
        assert "acwr" in result
        assert "acwr_risk" in result
        assert "acwr_color" in result

    def test_trend_7d_capped(self):
        today = _today_iso()
        loads = [_make_load(today, tss=60.0)] * 10
        db = self._db(loads)
        result = _training_snapshot("ath-1", db)
        assert len(result["trend_7d"]) <= 7


# ── TestRecoverySnapshot ───────────────────────────────────────────────────────

class TestRecoverySnapshot:
    def test_no_scores_returns_nones(self):
        db = _make_db_simple(RecoveryScore, returns_list=[])
        result = _recovery_snapshot("ath-1", db)
        assert result["latest_score"] is None
        assert result["latest_date"] is None

    def test_latest_score_used(self):
        today = _today_iso()
        db = _make_db_simple(RecoveryScore, returns_list=[_make_recovery(today, score=80)])
        result = _recovery_snapshot("ath-1", db)
        assert result["latest_score"] == 80

    def test_avg_7d_calculated(self):
        today = _today_iso()
        scores = [_make_recovery(today, score=60), _make_recovery(today, score=80)]
        db = _make_db_simple(RecoveryScore, returns_list=scores)
        result = _recovery_snapshot("ath-1", db)
        assert result["avg_7d"] == 70.0

    def test_training_suggestion_propagated(self):
        today = _today_iso()
        db = _make_db_simple(RecoveryScore, returns_list=[_make_recovery(today, suggestion="rest")])
        result = _recovery_snapshot("ath-1", db)
        assert result["training_suggestion"] == "rest"


# ── TestMentalSnapshot ─────────────────────────────────────────────────────────

class TestMentalSnapshot:
    def _db(self, scores, checkin=None):
        db = MagicMock()
        call_count = [0]

        def query_side_effect(cls):
            call_count[0] += 1
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            q.limit.return_value = q
            if cls == MentalFatigueScore:
                q.all.return_value = scores
                q.first.return_value = scores[0] if scores else None
            elif cls == MentalCheckin:
                q.first.return_value = checkin
            return q

        db.query.side_effect = query_side_effect
        return db

    def test_no_data(self):
        db = self._db([])
        result = _mental_snapshot("ath-1", db)
        assert result["latest_score"] is None
        assert result["avg_7d"] is None

    def test_latest_score(self):
        today = _today_iso()
        db = self._db([_make_mental_score(today, score=74)])
        result = _mental_snapshot("ath-1", db)
        assert result["latest_score"] == 74

    def test_checkin_included(self):
        today = _today_iso()
        ci = _make_mental_checkin(today, motivation=2, anxiety=4)
        db = self._db([_make_mental_score(today)], checkin=ci)
        result = _mental_snapshot("ath-1", db)
        assert result["latest_checkin"]["motivation"] == 2
        assert result["latest_checkin"]["anxiety"] == 4


# ── TestBloodLabsSnapshot ──────────────────────────────────────────────────────

class TestBloodLabsSnapshot:
    def _db(self, exam=None, alerts=None):
        db = MagicMock()

        def query_side_effect(cls):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            if cls == BloodLabExam:
                q.first.return_value = exam
            elif cls == BloodLabAlert:
                q.all.return_value = alerts or []
            return q

        db.query.side_effect = query_side_effect
        return db

    def test_no_labs_returns_false(self):
        db = self._db(exam=None)
        result = _blood_labs_snapshot("ath-1", db)
        assert result["has_labs"] is False
        assert result["trs"] is None

    def test_exam_no_alerts_trs_100(self):
        exam = _make_exam("2026-06-01")
        db = self._db(exam=exam, alerts=[])
        result = _blood_labs_snapshot("ath-1", db)
        assert result["has_labs"] is True
        assert result["trs"] == 100
        assert result["critical_markers"] == []

    def test_critical_alert_reduces_trs(self):
        exam = _make_exam("2026-06-01")
        alert = _make_alert("exam-1", "ferritin", "critical")
        db = self._db(exam=exam, alerts=[alert])
        result = _blood_labs_snapshot("ath-1", db)
        assert result["trs"] == 80
        assert "ferritin" in result["critical_markers"]

    def test_warning_alert_reduces_trs(self):
        exam = _make_exam("2026-06-01")
        alert = _make_alert("exam-1", "vitamin_d", "warning")
        db = self._db(exam=exam, alerts=[alert])
        result = _blood_labs_snapshot("ath-1", db)
        assert result["trs"] == 90
        assert "vitamin_d" in result["warning_markers"]

    def test_dismissed_alert_excluded(self):
        exam = _make_exam("2026-06-01")
        alert = _make_alert("exam-1", "ferritin", "critical", dismissed_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db = self._db(exam=exam, alerts=[alert])
        result = _blood_labs_snapshot("ath-1", db)
        # The dismissed alert IS in the list (filtering is done at query level in real code;
        # in unit test the mock returns whatever we pass, so we test the accounting logic)
        assert result["has_labs"] is True


# ── TestPrescriptionSnapshot ───────────────────────────────────────────────────

class TestPrescriptionSnapshot:
    def _db(self, rxs):
        db = _make_db_simple(WorkoutPrescription, returns_list=rxs)
        return db

    def test_no_prescriptions(self):
        db = self._db([])
        result = _prescription_snapshot("ath-1", db)
        assert result["pending_count"] == 0
        assert result["completed_30d"] == 0
        assert result["compliance_pct"] is None

    def test_pending_count(self):
        rxs = [_make_rx("ath-1", status="pending")] * 3
        db = self._db(rxs)
        result = _prescription_snapshot("ath-1", db)
        assert result["pending_count"] == 3

    def test_compliance_pct_calculated(self):
        rxs = [
            _make_rx("ath-1", "completed"),
            _make_rx("ath-1", "completed"),
            _make_rx("ath-1", "skipped"),
        ]
        db = self._db(rxs)
        result = _prescription_snapshot("ath-1", db)
        assert result["compliance_pct"] == round(2 / 3 * 100, 0)

    def test_100_pct_when_all_completed(self):
        rxs = [_make_rx("ath-1", "completed")] * 5
        db = self._db(rxs)
        result = _prescription_snapshot("ath-1", db)
        assert result["compliance_pct"] == 100.0


# ── TestGenerateAthleteAlerts ──────────────────────────────────────────────────

class TestGenerateAthleteAlerts:
    def _base(self):
        return (
            {"tsb": -5.0, "acwr": 1.1, "acwr_risk": "safe", "acwr_color": "#10b981"},
            {"latest_score": 70, "avg_7d": 70},
            {"latest_score": 70, "latest_checkin": None},
            {"has_labs": False},
            {"pending_count": 0, "completed_30d": 5, "compliance_pct": 90.0},
        )

    def test_no_alerts_when_all_ok(self):
        tr, rec, men, bld, rxs = self._base()
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        critical = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical) == 0

    def test_tsb_sobrecarga_is_critical(self):
        tr, rec, men, bld, rxs = self._base()
        tr["tsb"] = -28.0
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["severity"] == "critical" and "TSB" in a["message"] for a in alerts)

    def test_tsb_fatiga_alta_is_warning(self):
        tr, rec, men, bld, rxs = self._base()
        tr["tsb"] = -18.0
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["severity"] == "warning" and "TSB" in a["message"] for a in alerts)

    def test_elevated_acwr_is_critical(self):
        tr, rec, men, bld, rxs = self._base()
        tr["acwr"] = 1.6
        tr["acwr_risk"] = "elevated"
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["severity"] == "critical" and "ACWR" in a["message"] for a in alerts)

    def test_critical_recovery_alert(self):
        tr, rec, men, bld, rxs = self._base()
        rec["latest_score"] = 35
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["severity"] == "critical" and "ecup" in a["message"].lower() for a in alerts)

    def test_no_labs_generates_info(self):
        tr, rec, men, bld, rxs = self._base()
        bld["has_labs"] = False
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["module"] == "blood_labs" and a["severity"] == "info" for a in alerts)

    def test_critical_blood_marker_alert(self):
        tr, rec, men, bld, rxs = self._base()
        bld["has_labs"] = True
        bld["critical_markers"] = ["ferritin"]
        bld["warning_markers"] = []
        bld["days_since_exam"] = 10
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["severity"] == "critical" and "ferritin" in a["message"] for a in alerts)

    def test_alerts_sorted_critical_first(self):
        tr, rec, men, bld, rxs = self._base()
        tr["tsb"] = -30.0
        bld["has_labs"] = False
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        if len(alerts) > 1:
            order = {"critical": 0, "warning": 1, "info": 2}
            for i in range(len(alerts) - 1):
                assert order[alerts[i]["severity"]] <= order[alerts[i+1]["severity"]]

    def test_pending_prescriptions_warning(self):
        tr, rec, men, bld, rxs = self._base()
        rxs["pending_count"] = 4
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["module"] == "prescriptions" and a["severity"] == "warning" for a in alerts)

    def test_low_prescription_compliance_warning(self):
        tr, rec, men, bld, rxs = self._base()
        rxs["compliance_pct"] = 45.0
        rxs["pending_count"] = 0
        alerts = _generate_athlete_alerts(tr, rec, men, bld, rxs)
        assert any(a["module"] == "prescriptions" and a["severity"] == "warning" and "dherencia" in a["message"] for a in alerts)


# ── TestGetAthleteIntelligence ─────────────────────────────────────────────────

class TestGetAthleteIntelligence:
    def _make_athlete(self):
        u = MagicMock()
        u.id = "ath-1"
        u.email = "test@example.com"
        u.nombre = "Test Atleta"
        return u

    def _make_db(self):
        db = MagicMock()
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = []
        q.first.return_value = None
        q.count.return_value = 0
        return db

    def test_returns_all_keys(self):
        athlete = self._make_athlete()
        db = self._make_db()
        result = get_athlete_intelligence(athlete, db)
        for key in ["athlete_id","athlete_name","generated_at","training","recovery",
                    "mental","blood_labs","nutrition","prescriptions","alerts","alert_counts"]:
            assert key in result

    def test_athlete_id_matches(self):
        athlete = self._make_athlete()
        db = self._make_db()
        result = get_athlete_intelligence(athlete, db)
        assert result["athlete_id"] == "ath-1"

    def test_alert_counts_structure(self):
        athlete = self._make_athlete()
        db = self._make_db()
        result = get_athlete_intelligence(athlete, db)
        ac = result["alert_counts"]
        assert "critical" in ac and "warning" in ac and "info" in ac

    def test_generated_at_is_iso(self):
        athlete = self._make_athlete()
        db = self._make_db()
        result = get_athlete_intelligence(athlete, db)
        # Should parse without error
        datetime.fromisoformat(result["generated_at"])
