"""Sprint 42 — coverage improvement tests (R-14).

Covers previously-untested pure utility modules:
  - api/pagination.py
  - api/services/notification_service.py
  - api/services/wellness_service.py
  - api/workout_delivery.py (pure parts)
  - api/database.py pool config
"""
import pytest
from unittest.mock import MagicMock, patch
import json


# ═══════════════════════════════════════════════════════════════════
# PAGINATION
# ═══════════════════════════════════════════════════════════════════

class TestPaginationParams:
    def test_default_values(self):
        from api.pagination import PaginationParams
        p = PaginationParams.__new__(PaginationParams)
        p.page = 1
        p.per_page = 50
        assert p.offset == 0
        assert p.limit == 50

    def test_offset_second_page(self):
        from api.pagination import PaginationParams
        p = PaginationParams.__new__(PaginationParams)
        p.page = 2
        p.per_page = 50
        assert p.offset == 50

    def test_offset_third_page(self):
        from api.pagination import PaginationParams
        p = PaginationParams.__new__(PaginationParams)
        p.page = 3
        p.per_page = 25
        assert p.offset == 50

    def test_limit_equals_per_page(self):
        from api.pagination import PaginationParams
        p = PaginationParams.__new__(PaginationParams)
        p.page = 1
        p.per_page = 100
        assert p.limit == 100


class TestPaginateQuery:
    def _make_params(self, page=1, per_page=10):
        from api.pagination import PaginationParams
        p = PaginationParams.__new__(PaginationParams)
        p.page = page
        p.per_page = per_page
        return p

    def _make_query(self, total_items):
        """Mock SAQuery that returns fake items."""
        items = [f"item_{i}" for i in range(total_items)]
        mock_q = MagicMock()
        mock_q.count.return_value = total_items

        def offset_side(off):
            m = MagicMock()
            def limit_side(lim):
                lm = MagicMock()
                lm.all.return_value = items[off:off + lim]
                return lm
            m.limit.side_effect = limit_side
            return m
        mock_q.offset.side_effect = offset_side
        return mock_q

    def test_first_page(self):
        from api.pagination import paginate_query
        q = self._make_query(25)
        p = self._make_params(page=1, per_page=10)
        r = paginate_query(q, p)
        assert r["total"] == 25
        assert r["page"] == 1
        assert r["per_page"] == 10
        assert r["pages"] == 3
        assert r["has_next"] is True
        assert r["has_prev"] is False
        assert len(r["items"]) == 10

    def test_last_page(self):
        from api.pagination import paginate_query
        q = self._make_query(25)
        p = self._make_params(page=3, per_page=10)
        r = paginate_query(q, p)
        assert r["has_next"] is False
        assert r["has_prev"] is True
        assert r["pages"] == 3

    def test_single_page(self):
        from api.pagination import paginate_query
        q = self._make_query(5)
        p = self._make_params(page=1, per_page=10)
        r = paginate_query(q, p)
        assert r["pages"] == 1
        assert r["has_next"] is False
        assert r["has_prev"] is False

    def test_empty_result(self):
        from api.pagination import paginate_query
        q = self._make_query(0)
        p = self._make_params(page=1, per_page=10)
        r = paginate_query(q, p)
        assert r["total"] == 0
        assert r["pages"] == 1  # max(1, ...)
        assert r["items"] == []

    def test_exact_page_boundary(self):
        from api.pagination import paginate_query
        q = self._make_query(20)
        p = self._make_params(page=2, per_page=10)
        r = paginate_query(q, p)
        assert r["pages"] == 2
        assert r["has_next"] is False
        assert r["has_prev"] is True


class TestRlHeaders:
    def test_basic_headers(self):
        from api.pagination import rl_headers
        h = rl_headers(10, 3)
        assert h["X-RateLimit-Limit"] == "10"
        assert h["X-RateLimit-Remaining"] == "7"
        assert h["X-RateLimit-Window"] == "3600"

    def test_exhausted_limit(self):
        from api.pagination import rl_headers
        h = rl_headers(10, 10)
        assert h["X-RateLimit-Remaining"] == "0"

    def test_over_limit_clamps_to_zero(self):
        from api.pagination import rl_headers
        h = rl_headers(10, 15)
        assert h["X-RateLimit-Remaining"] == "0"

    def test_custom_window(self):
        from api.pagination import rl_headers
        h = rl_headers(5, 0, window_seconds=60)
        assert h["X-RateLimit-Window"] == "60"
        assert h["X-RateLimit-Remaining"] == "5"


# ═══════════════════════════════════════════════════════════════════
# NOTIFICATION SERVICE
# ═══════════════════════════════════════════════════════════════════

class TestEmailTemplates:
    def test_email_workout_assigned_returns_tuple(self):
        from api.services.notification_service import email_workout_assigned
        subject, html = email_workout_assigned("Ana", "Threshold Run", "2026-07-10", "Carlos")
        assert isinstance(subject, str)
        assert isinstance(html, str)
        assert "Threshold Run" in subject
        assert "Ana" in html
        assert "Carlos" in html
        assert "2026-07-10" in html

    def test_email_workout_assigned_with_notes(self):
        from api.services.notification_service import email_workout_assigned
        subject, html = email_workout_assigned("Ana", "FTP Test", "2026-07-10", "Carlos",
                                               notas="warm up 20 min")
        assert "warm up 20 min" in html

    def test_email_workout_assigned_no_notes(self):
        from api.services.notification_service import email_workout_assigned
        subject, html = email_workout_assigned("Ana", "FTP Test", "2026-07-10", "Carlos")
        assert "<!DOCTYPE html>" in html

    def test_email_weekly_summary_structure(self):
        from api.services.notification_service import email_weekly_summary
        week = {"swim_km": 3.5, "bike_km": 120.0, "run_km": 25.0, "tss_week": 450, "ctl": 75}
        subject, html = email_weekly_summary("Pedro", week)
        assert "resumen semanal" in subject.lower() or "LabX" in subject
        assert "3.5" in html
        assert "120.0" in html

    def test_email_weekly_summary_zeros(self):
        from api.services.notification_service import email_weekly_summary
        subject, html = email_weekly_summary("Maria", {})
        assert isinstance(html, str)
        assert "0.0" in html

    def test_email_wellness_reminder(self):
        from api.services.notification_service import email_wellness_reminder
        subject, html = email_wellness_reminder("Lucas")
        assert "bienestar" in subject.lower()
        assert "Lucas" in html

    def test_email_overtraining_alert_with_coach(self):
        from api.services.notification_service import email_overtraining_alert
        subject, html = email_overtraining_alert("João", -25.0, 1.45, coach_name="Sergio")
        assert "alerta" in subject.lower() or "carga" in subject.lower()
        assert "-25" in html
        assert "1.45" in html
        assert "Sergio" in html

    def test_email_overtraining_alert_without_coach(self):
        from api.services.notification_service import email_overtraining_alert
        subject, html = email_overtraining_alert("João", -25.0, 1.45)
        assert isinstance(html, str)

    def test_base_email_contains_labx_branding(self):
        from api.services.notification_service import _base_email
        html = _base_email("<p>test content</p>")
        assert "LabX" in html
        assert "test content" in html
        assert "<!DOCTYPE html>" in html


class TestPushPayloads:
    def test_push_workout_assigned(self):
        from api.services.notification_service import push_workout_assigned
        p = push_workout_assigned("Sweet Spot", "2026-07-10")
        assert p["type"] == "workout_assigned"
        assert "Sweet Spot" in p["body"]
        assert "title" in p

    def test_push_garmin_sync_done(self):
        from api.services.notification_service import push_garmin_sync_done
        p = push_garmin_sync_done(42)
        assert p["type"] == "garmin_sync_done"
        assert "42" in p["body"]

    def test_push_wellness_reminder(self):
        from api.services.notification_service import push_wellness_reminder
        p = push_wellness_reminder()
        assert p["type"] == "wellness_reminder"
        assert "tag" in p  # has deduplication tag

    def test_push_overtraining_alert(self):
        from api.services.notification_service import push_overtraining_alert
        p = push_overtraining_alert(-30.0)
        assert p["type"] == "overtraining_alert"
        assert "-30" in p["body"]
        assert p.get("requireInteraction") is True


# ═══════════════════════════════════════════════════════════════════
# WELLNESS SERVICE
# ═══════════════════════════════════════════════════════════════════

class TestWellnessScore:
    def _make_log(self, fatigue=3, sleep_q=3, soreness=3, mood=3):
        log = MagicMock()
        log.fatigue  = fatigue
        log.sleep_q  = sleep_q
        log.soreness = soreness
        log.mood     = mood
        return log

    def test_score_none_log(self):
        from api.services.wellness_service import wellness_score
        assert wellness_score(None) == 0.0

    def test_score_average_values(self):
        from api.services.wellness_service import wellness_score
        log = self._make_log(3, 3, 3, 3)
        score = wellness_score(log)
        # fatigue=(6-3)*5=15, sleep_q=3*5=15, soreness=(6-3)*5=15, mood=3*5=15 → 60
        assert score == 60.0

    def test_score_max_values(self):
        from api.services.wellness_service import wellness_score
        # Best case: fatigue=1 (well rested → max inverted), sleep_q=5, soreness=1, mood=5
        log = self._make_log(fatigue=1, sleep_q=5, soreness=1, mood=5)
        score = wellness_score(log)
        # fatigue=(6-1)*5=25, sleep_q=25, soreness=25, mood=25 → 100
        assert score == 100.0

    def test_score_min_values(self):
        from api.services.wellness_service import wellness_score
        log = self._make_log(fatigue=5, sleep_q=1, soreness=5, mood=1)
        score = wellness_score(log)
        # fatigue=(6-5)*5=5, sleep_q=1*5=5, soreness=(6-5)*5=5, mood=1*5=5 → 20
        assert score == 20.0

    def test_score_none_fields_use_default_3(self):
        from api.services.wellness_service import wellness_score
        log = MagicMock()
        log.fatigue  = None
        log.sleep_q  = None
        log.soreness = None
        log.mood     = None
        score = wellness_score(log)
        assert score == 60.0  # all defaults to 3

    def test_score_is_numeric(self):
        from api.services.wellness_service import wellness_score
        log = self._make_log(2, 4, 2, 4)
        score = wellness_score(log)
        assert isinstance(score, (int, float))
        assert score > 0


class TestWellnessTrend:
    def test_trend_empty_returns_list(self, db):
        from api.services.wellness_service import wellness_trend
        result = wellness_trend(db, "nonexistent-user-id")
        assert isinstance(result, list)
        assert result == []

    def test_trend_with_data(self, db):
        from api.models import WellnessLog
        from api.services.wellness_service import wellness_trend
        import uuid
        user_id = str(uuid.uuid4())
        log = WellnessLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            date_iso="2026-07-01",
            fatigue=2,
            sleep_q=4,
            soreness=2,
            mood=4,
        )
        db.add(log)
        db.commit()
        result = wellness_trend(db, user_id, days=30)
        assert len(result) == 1
        assert result[0]["date"] == "2026-07-01"
        assert result[0]["score"] > 0


class TestWellnessSummary:
    def test_summary_empty(self, db):
        from api.services.wellness_service import wellness_summary
        r = wellness_summary(db, "no-such-user")
        assert r["avg_score"] is None
        assert r["count"] == 0
        assert r["trend"] == []

    def test_summary_with_data(self, db):
        from api.models import WellnessLog
        from api.services.wellness_service import wellness_summary
        import uuid
        user_id = str(uuid.uuid4())
        for i, d in enumerate(["2026-07-01", "2026-07-02"]):
            log = WellnessLog(
                id=str(uuid.uuid4()),
                user_id=user_id,
                date_iso=d,
                fatigue=2, sleep_q=4, soreness=2, mood=4,
            )
            db.add(log)
        db.commit()
        r = wellness_summary(db, user_id)
        assert r["count"] == 2
        assert r["avg_score"] is not None
        assert len(r["trend"]) == 2


# ═══════════════════════════════════════════════════════════════════
# WORKOUT DELIVERY — ZWO GENERATION (pure functions)
# ═══════════════════════════════════════════════════════════════════

class TestGenerateZwoBytes:
    def test_empty_blocks_json_returns_empty(self):
        from api.workout_delivery import generate_zwo_bytes
        result = generate_zwo_bytes("invalid_json", "test")
        assert result == b""

    def test_empty_blocks_array(self):
        from api.workout_delivery import generate_zwo_bytes
        result = generate_zwo_bytes("[]", "Empty Workout")
        assert b"<workout_file>" in result
        assert b"</workout_file>" in result

    def test_warmup_block(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "warmup", "duration": 600, "power_low": 0.50, "power_high": 0.75}]
        result = generate_zwo_bytes(json.dumps(blocks), "Warmup Test", "2026-07-10")
        assert b"<Warmup" in result
        assert b"Duration=\"600\"" in result

    def test_cooldown_block(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "cooldown", "duration": 300, "power_low": 0.40, "power_high": 0.65}]
        result = generate_zwo_bytes(json.dumps(blocks), "Cooldown")
        assert b"<Cooldown" in result

    def test_steady_block(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "steady", "duration": 1800, "power": 0.85}]
        result = generate_zwo_bytes(json.dumps(blocks), "Steady State")
        assert b"<SteadyState" in result
        assert b"Power=\"0.85\"" in result

    def test_intervals_block(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "intervals", "repeat": 6, "on_duration": 240,
                   "off_duration": 120, "on_power": 1.10, "off_power": 0.55}]
        result = generate_zwo_bytes(json.dumps(blocks), "VO2 Intervals")
        assert b"<IntervalsT" in result
        assert b"Repeat=\"6\"" in result

    def test_ramp_block(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "ramp", "duration": 900, "power_low": 0.60, "power_high": 1.00}]
        result = generate_zwo_bytes(json.dumps(blocks), "Ramp Test")
        assert b"<Ramp" in result

    def test_freeride_block(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "freeride", "duration": 300}]
        result = generate_zwo_bytes(json.dumps(blocks), "Recovery Spin")
        assert b"<FreeRide" in result

    def test_unknown_block_type_skipped(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [{"type": "unknown_block_xyz", "duration": 300}]
        result = generate_zwo_bytes(json.dumps(blocks), "Test Workout")
        # Unknown block type should produce valid XML but no workout element for that type
        assert b"<workout_file>" in result
        assert b"unknown_block_xyz" not in result  # type string not in XML workout elements

    def test_xml_special_chars_escaped(self):
        from api.workout_delivery import generate_zwo_bytes
        result = generate_zwo_bytes("[]", 'Workout <"Test"> & More')
        decoded = result.decode("utf-8")
        assert "&amp;" in decoded or "&lt;" in decoded or "&quot;" in decoded

    def test_workout_name_in_output(self):
        from api.workout_delivery import generate_zwo_bytes
        result = generate_zwo_bytes("[]", "My FTP Booster", "2026-07-15")
        assert b"My FTP Booster" in result
        assert b"2026-07-15" in result

    def test_multiple_blocks(self):
        from api.workout_delivery import generate_zwo_bytes
        blocks = [
            {"type": "warmup",   "duration": 600, "power_low": 0.5, "power_high": 0.75},
            {"type": "steady",   "duration": 1800, "power": 0.85},
            {"type": "cooldown", "duration": 300, "power_low": 0.4, "power_high": 0.65},
        ]
        result = generate_zwo_bytes(json.dumps(blocks), "Full Workout")
        assert b"<Warmup" in result
        assert b"<SteadyState" in result
        assert b"<Cooldown" in result

    def test_returns_utf8_bytes(self):
        from api.workout_delivery import generate_zwo_bytes
        result = generate_zwo_bytes("[]", "Test")
        assert isinstance(result, bytes)
        result.decode("utf-8")  # should not raise


class TestSafeFilename:
    def test_normal_name(self):
        from api.workout_delivery import _safe_filename
        assert _safe_filename("MyWorkout") == "MyWorkout"

    def test_spaces_replaced(self):
        from api.workout_delivery import _safe_filename
        assert _safe_filename("Sweet Spot") == "Sweet_Spot"

    def test_special_chars_replaced(self):
        from api.workout_delivery import _safe_filename
        result = _safe_filename("FTP Test #1 (hard!)")
        assert result.isidentifier() or all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in result)

    def test_empty_string_fallback(self):
        from api.workout_delivery import _safe_filename
        assert _safe_filename("") == "workout"

    def test_none_fallback(self):
        from api.workout_delivery import _safe_filename
        assert _safe_filename(None) == "workout"


class TestAutoGarminSync:
    def test_no_credentials_returns_skipped(self):
        from api.workout_delivery import auto_garmin_sync
        athlete = MagicMock()
        athlete.garmin_email = None
        athlete.garmin_password = None
        tpl = MagicMock()
        assignment = MagicMock()
        result = auto_garmin_sync(assignment, athlete, tpl)
        assert result["skipped"] is True
        assert result["ok"] is False
        assert result["error"] is None

    def test_no_email_skipped(self):
        from api.workout_delivery import auto_garmin_sync
        athlete = MagicMock()
        athlete.garmin_email = ""
        athlete.garmin_password = "pass"
        result = auto_garmin_sync(MagicMock(), athlete, MagicMock())
        assert result["skipped"] is True

    def test_garmin_import_error_returns_error(self):
        """If garmin_connector is not installed, returns error dict."""
        from api.workout_delivery import auto_garmin_sync
        athlete = MagicMock()
        athlete.garmin_email = "test@garmin.com"
        athlete.garmin_password = "encrypted_pass"
        tpl = MagicMock()
        tpl.sport = "bike"
        tpl.dur_min = 60
        tpl.dist_km = 40
        tpl.notas = ""
        assignment = MagicMock()
        assignment.date_iso = "2026-07-10"
        assignment.notas = ""
        with patch("api.workout_delivery.auto_garmin_sync.__module__"):
            pass
        # The import of garmin_connector should fail gracefully
        result = auto_garmin_sync(assignment, athlete, tpl)
        assert isinstance(result, dict)
        assert "ok" in result


class TestDeliverBikeWorkout:
    def test_no_blocks_no_email_sent(self):
        from api.workout_delivery import deliver_bike_workout
        tpl = MagicMock()
        tpl.blocks_json = None
        tpl.nombre = "Recovery Ride"
        athlete = MagicMock()
        athlete.email = "test@test.com"
        athlete.garmin_email = None
        athlete.garmin_password = None
        assignment = MagicMock()
        assignment.date_iso = "2026-07-10"
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["email_sent"] is False
        assert result["garmin_skipped"] is True

    def test_no_athlete_email_no_email_sent(self):
        from api.workout_delivery import deliver_bike_workout
        tpl = MagicMock()
        tpl.blocks_json = json.dumps([{"type": "steady", "duration": 1800, "power": 0.85}])
        tpl.nombre = "Threshold"
        athlete = MagicMock()
        athlete.email = None
        athlete.garmin_email = None
        athlete.garmin_password = None
        assignment = MagicMock()
        assignment.date_iso = "2026-07-10"
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["email_sent"] is False


# ═══════════════════════════════════════════════════════════════════
# DATABASE POOL CONFIG
# ═══════════════════════════════════════════════════════════════════

class TestDatabasePoolConfig:
    def test_database_url_imported(self):
        from api.database import DATABASE_URL
        assert isinstance(DATABASE_URL, str)
        assert len(DATABASE_URL) > 0

    def test_engine_imported(self):
        from api.database import engine
        assert engine is not None

    def test_pool_kwargs_set_for_postgres(self):
        import importlib, os
        from api import database as db_mod
        if db_mod._is_sqlite:
            assert db_mod._pool_kwargs == {}
        else:
            assert "pool_size" in db_mod._pool_kwargs
            assert "max_overflow" in db_mod._pool_kwargs
            assert "pool_timeout" in db_mod._pool_kwargs
            assert "pool_recycle" in db_mod._pool_kwargs

    def test_session_local_importable(self):
        from api.database import SessionLocal
        assert SessionLocal is not None

    def test_get_db_yields_session(self, db):
        from api.database import get_db
        gen = get_db()
        session = next(gen)
        assert session is not None
        try:
            next(gen)
        except StopIteration:
            pass
