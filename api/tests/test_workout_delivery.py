"""
Tests — workout_delivery.py
Cubre las líneas no alcanzadas: 94-174 (send_zwo_email), 213-215, 236-247, 254-255.
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch


from api.workout_delivery import (
    generate_zwo_bytes,
    _safe_filename,
    send_zwo_email,
    auto_garmin_sync,
    deliver_bike_workout,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _blocks(*types) -> str:
    mapping = {
        "warmup":    {"type": "warmup",    "duration": 600, "power_low": 0.50, "power_high": 0.75},
        "cooldown":  {"type": "cooldown",  "duration": 300, "power_low": 0.40, "power_high": 0.60},
        "steady":    {"type": "steady",    "duration": 1200, "power": 0.80},
        "intervals": {"type": "intervals", "duration": 900,  "repeat": 5, "on_duration": 90,
                      "off_duration": 60, "on_power": 1.05, "off_power": 0.50},
        "ramp":      {"type": "ramp",      "duration": 600, "power_low": 0.60, "power_high": 1.00},
        "freeride":  {"type": "freeride",  "duration": 300},
        "unknown":   {"type": "unknown_block", "duration": 120},
    }
    return json.dumps([mapping[t] for t in types])


def _mock_tpl(blocks_json=None, nombre="Test Workout", sport="bike",
              dur_min=60, dist_km=None, notas=None):
    tpl = MagicMock()
    tpl.blocks_json = blocks_json
    tpl.nombre      = nombre
    tpl.sport       = sport
    tpl.dur_min     = dur_min
    tpl.dist_km     = dist_km
    tpl.notas       = notas
    return tpl


def _mock_athlete(has_garmin=True, has_email=True, garmin_encrypted=True):
    a = MagicMock()
    a.id           = "ath-test-001"
    a.nombre       = "Atleta Test"
    a.email        = "atleta@test.com" if has_email else None
    a.garmin_email = "g@test.com"    if has_garmin else None
    if has_garmin:
        from api.crypto import encrypt
        a.garmin_password = encrypt("testpassword123") if garmin_encrypted else "testpassword123"
    else:
        a.garmin_password = None
    return a


def _mock_assignment(date_iso="2026-09-15", notas=None):
    a = MagicMock()
    a.date_iso = date_iso
    a.notas    = notas
    return a


# ─── generate_zwo_bytes ──────────────────────────────────────────────────────

class TestGenerateZwoBytes:
    def test_warmup_block(self):
        result = generate_zwo_bytes(_blocks("warmup"), "WU Test")
        assert b"<Warmup" in result
        assert b'PowerLow="0.50"' in result

    def test_cooldown_block(self):
        result = generate_zwo_bytes(_blocks("cooldown"), "CD Test")
        assert b"<Cooldown" in result

    def test_steady_block(self):
        result = generate_zwo_bytes(_blocks("steady"), "SS Test")
        assert b"<SteadyState" in result
        assert b'Power="0.80"' in result

    def test_intervals_block(self):
        result = generate_zwo_bytes(_blocks("intervals"), "INT Test")
        assert b"<IntervalsT" in result
        assert b'Repeat="5"' in result
        assert b'OnPower="1.05"' in result

    def test_ramp_block(self):
        result = generate_zwo_bytes(_blocks("ramp"), "RAMP Test")
        assert b"<Ramp" in result
        assert b'PowerLow="0.60"' in result

    def test_freeride_block(self):
        result = generate_zwo_bytes(_blocks("freeride"), "FR Test")
        assert b"<FreeRide" in result

    def test_unknown_block_is_ignored(self):
        result = generate_zwo_bytes(_blocks("unknown"), "UNK Test")
        assert b"<workout_file>" in result
        assert b"<workout>" in result

    def test_all_block_types_combined(self):
        blocks = _blocks("warmup", "steady", "intervals", "ramp", "freeride", "cooldown")
        result = generate_zwo_bytes(blocks, "Full Workout", "2026-09-20")
        assert result.startswith(b"<?xml")
        assert b"LabX Coach" in result
        assert b"Full Workout" in result
        assert b"2026-09-20" in result

    def test_invalid_json_returns_empty(self):
        result = generate_zwo_bytes("not_json_at_all{{", "Bad Blocks")
        assert result == b""

    def test_xml_special_chars_escaped(self):
        result = generate_zwo_bytes(_blocks("steady"), 'Workout <"Test"> & More')
        assert b"&lt;" in result
        assert b"&gt;" in result
        assert b"&amp;" in result
        assert b"&quot;" in result

    def test_date_iso_included(self):
        result = generate_zwo_bytes(_blocks("steady"), "My Ride", "2026-10-01")
        assert b"2026-10-01" in result

    def test_empty_blocks_list(self):
        result = generate_zwo_bytes("[]", "Empty")
        assert b"<workout_file>" in result
        assert b"</workout_file>" in result


# ─── _safe_filename ──────────────────────────────────────────────────────────

class TestSafeFilename:
    def test_normal_name(self):
        assert _safe_filename("My Workout") == "My_Workout"

    def test_spaces_and_special(self):
        assert _safe_filename("Race Day 70.3!") == "Race_Day_70_3"

    def test_empty_string_fallback(self):
        assert _safe_filename("") == "workout"

    def test_none_fallback(self):
        assert _safe_filename(None) == "workout"

    def test_keeps_alphanumeric_hyphen_underscore(self):
        result = _safe_filename("Z2-Long_Ride")
        assert result == "Z2-Long_Ride"


# ─── send_zwo_email ──────────────────────────────────────────────────────────

class TestSendZwoEmail:
    def _make_zwo(self):
        return generate_zwo_bytes(_blocks("warmup", "steady", "cooldown"), "Email Workout", "2026-09-15")

    @patch("api.workout_delivery.send_email", return_value=True)  # patched at module level
    def test_email_sent_successfully(self, mock_send):
        zwo = self._make_zwo()
        result = send_zwo_email("ath@test.com", "Rafael", "Z2 Ride", "2026-09-15", zwo)
        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
        call_args   = mock_send.call_args[0] if mock_send.call_args[0] else []
        # Verificar que el email contiene el nombre del workout
        html_arg = call_kwargs.get("html") or (call_args[2] if len(call_args) > 2 else "")
        assert "Z2 Ride" in html_arg

    @patch("api.workout_delivery.send_email", return_value=False)  # patched at module level
    def test_email_returns_false_on_failure(self, mock_send):
        zwo = self._make_zwo()
        result = send_zwo_email("ath@test.com", "Rafael", "Workout", "2026-09-15", zwo)
        assert result is False

    @patch("api.workout_delivery.send_email", return_value=True)  # patched at module level
    def test_email_subject_contains_date_and_name(self, mock_send):
        zwo = self._make_zwo()
        send_zwo_email("ath@test.com", "Rafael", "Interval Power", "2026-09-20", zwo)
        call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
        subject = call_kwargs.get("subject", "")
        assert "2026-09-20" in subject
        assert "Interval Power" in subject

    @patch("api.workout_delivery.send_email", return_value=True)  # patched at module level
    def test_attachment_filename_sanitized(self, mock_send):
        zwo = self._make_zwo()
        send_zwo_email("ath@test.com", "Rafael", "Workout <Special>", "2026-09-15", zwo)
        call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
        attachments = call_kwargs.get("attachments", [])
        assert len(attachments) == 1
        fname = attachments[0]["filename"]
        assert "<" not in fname
        assert ">" not in fname
        assert fname.endswith(".zwo")

    @patch("api.workout_delivery.send_email", return_value=True)  # patched at module level
    def test_duration_hint_in_html(self, mock_send):
        blocks = _blocks("warmup", "steady", "cooldown")
        zwo = generate_zwo_bytes(blocks, "Duration Test", "2026-09-15")
        send_zwo_email("ath@test.com", "Rafael", "Duration Test", "2026-09-15", zwo)
        call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
        html = call_kwargs.get("html", "")
        assert "min" in html

    @patch("api.workout_delivery.send_email", return_value=True)  # patched at module level
    def test_athlete_name_in_html(self, mock_send):
        zwo = self._make_zwo()
        send_zwo_email("ath@test.com", "Camila López", "Ride", "2026-09-15", zwo)
        call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
        html = call_kwargs.get("html", "")
        assert "Camila" in html

    @patch("api.workout_delivery.send_email", return_value=True)  # patched at module level
    def test_empty_zwo_still_sends(self, mock_send):
        send_zwo_email("ath@test.com", "Rafael", "Bad ZWO", "2026-09-15", b"invalid_xml_bytes")
        mock_send.assert_called_once()


# ─── auto_garmin_sync ────────────────────────────────────────────────────────

class TestAutoGarminSync:
    def test_skip_when_no_garmin_email(self):
        athlete = _mock_athlete(has_garmin=False)
        tpl     = _mock_tpl()
        assignment = _mock_assignment()
        result = auto_garmin_sync(assignment, athlete, tpl)
        assert result["skipped"] is True
        assert result["ok"] is False
        assert result["error"] is None

    def test_skip_when_no_garmin_password(self):
        athlete = _mock_athlete(has_garmin=True)
        athlete.garmin_password = None
        tpl = _mock_tpl()
        result = auto_garmin_sync(_mock_assignment(), athlete, tpl)
        assert result["skipped"] is True

    @patch("api.workout_delivery.decrypt_credential", return_value="testpwd")  # module-level
    def test_garmin_connector_not_installed(self, mock_dec):
        athlete = _mock_athlete(has_garmin=True)
        tpl = _mock_tpl(nombre="Ride", sport="bike", dur_min=60)
        with patch.dict("sys.modules", {"garmin_connector": None}):
            result = auto_garmin_sync(_mock_assignment(), athlete, tpl)
        assert result["ok"] is False
        assert result["skipped"] is False

    @patch("api.workout_delivery.decrypt_credential", return_value="testpwd")  # module-level
    def test_garmin_sync_success(self, mock_dec):
        athlete = _mock_athlete(has_garmin=True)
        tpl = _mock_tpl(nombre="Intervals", sport="bike", dur_min=45, notas="Focus FTP")
        mock_connector = MagicMock()
        mock_connector.schedule_workout_for_athlete.return_value = {"workoutId": "GRM-123"}
        with patch.dict("sys.modules", {"garmin_connector": mock_connector}):
            result = auto_garmin_sync(_mock_assignment(), athlete, tpl)
        assert result["ok"] is True
        assert result["skipped"] is False
        assert result["error"] is None

    @patch("api.workout_delivery.decrypt_credential", return_value="testpwd")  # module-level
    def test_garmin_sync_api_error(self, mock_dec):
        athlete = _mock_athlete(has_garmin=True)
        tpl = _mock_tpl(nombre="Run", sport="run", dur_min=30)
        mock_connector = MagicMock()
        mock_connector.schedule_workout_for_athlete.side_effect = RuntimeError("401 Unauthorized")
        with patch.dict("sys.modules", {"garmin_connector": mock_connector}):
            result = auto_garmin_sync(_mock_assignment(), athlete, tpl)
        assert result["ok"] is False
        assert result["skipped"] is False
        assert "401" in result["error"]

    @patch("api.workout_delivery.decrypt_credential", return_value="testpwd")  # module-level
    def test_tpl_notes_fallback_to_assignment_notes(self, mock_dec):
        athlete = _mock_athlete(has_garmin=True)
        tpl = _mock_tpl(nombre="Z2", sport="bike", dur_min=90, notas=None)
        assignment = _mock_assignment(notas="Extra notes from assignment")
        captured = {}
        def fake_schedule(**kwargs):
            captured.update(kwargs)
            return {"workoutId": "X"}
        mock_connector = MagicMock()
        mock_connector.schedule_workout_for_athlete.side_effect = fake_schedule
        with patch.dict("sys.modules", {"garmin_connector": mock_connector}):
            auto_garmin_sync(assignment, athlete, tpl)
        session = captured.get("session", {})
        assert "Extra notes" in session.get("notes", "")


# ─── deliver_bike_workout ────────────────────────────────────────────────────

class TestDeliverBikeWorkout:
    @patch("api.workout_delivery.send_zwo_email", return_value=True)
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": True, "skipped": False, "error": None})
    def test_full_delivery_success(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=True, has_email=True)
        tpl        = _mock_tpl(blocks_json=_blocks("warmup", "steady"), nombre="Full Test")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["email_sent"]   is True
        assert result["garmin_ok"]    is True
        assert result["garmin_skipped"] is False

    @patch("api.workout_delivery.send_zwo_email", return_value=False)
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": False, "skipped": True, "error": None})
    def test_delivery_no_garmin_no_email(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=False, has_email=True)
        tpl        = _mock_tpl(blocks_json=None)
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["email_sent"] is False
        assert result["garmin_skipped"] is True

    @patch("api.workout_delivery.send_zwo_email", return_value=True)
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": False, "skipped": True, "error": None})
    def test_email_sent_but_no_garmin(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=False, has_email=True)
        tpl        = _mock_tpl(blocks_json=_blocks("steady"), nombre="No Garmin")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["garmin_skipped"] is True

    @patch("api.workout_delivery.send_zwo_email", side_effect=Exception("SMTP failure"))
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": True, "skipped": False, "error": None})
    def test_email_exception_does_not_crash(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=True, has_email=True)
        tpl        = _mock_tpl(blocks_json=_blocks("steady"), nombre="Exception Test")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["email_sent"] is False
        assert result["garmin_ok"]  is True

    @patch("api.workout_delivery.send_zwo_email", return_value=True)
    @patch("api.workout_delivery.auto_garmin_sync", side_effect=Exception("Garmin crash"))
    def test_garmin_exception_does_not_crash(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=True, has_email=True)
        tpl        = _mock_tpl(blocks_json=_blocks("steady"), nombre="Garmin Crash")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        assert result["email_sent"] is True
        assert result["garmin_ok"]  is False

    @patch("api.workout_delivery.send_zwo_email", return_value=True)
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": True, "skipped": False, "error": None})
    def test_skips_email_when_no_athlete_email(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=True, has_email=False)
        tpl        = _mock_tpl(blocks_json=_blocks("steady"), nombre="No Email")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        mock_email.assert_not_called()

    @patch("api.workout_delivery.send_zwo_email", return_value=True)
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": True, "skipped": False, "error": None})
    def test_skips_email_when_no_blocks(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=True, has_email=True)
        tpl        = _mock_tpl(blocks_json=None, nombre="No Blocks")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        mock_email.assert_not_called()

    @patch("api.workout_delivery.send_zwo_email", return_value=True)
    @patch("api.workout_delivery.auto_garmin_sync",
           return_value={"ok": True, "skipped": False, "error": None})
    def test_empty_zwo_skips_email(self, mock_garmin, mock_email):
        athlete    = _mock_athlete(has_garmin=True, has_email=True)
        tpl        = _mock_tpl(blocks_json="invalid_json{{", nombre="Bad JSON")
        assignment = _mock_assignment()
        result = deliver_bike_workout(assignment, athlete, tpl)
        mock_email.assert_not_called()
