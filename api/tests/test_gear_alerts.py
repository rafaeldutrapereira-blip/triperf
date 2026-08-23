"""
Tests — helpers de alerta de equipamiento (mailer.send_gear_alert,
notification_service.push_gear_alert). Unitarios: no golpean red real
(RESEND_API_KEY/VAPID_PRIVATE_KEY no configuradas en el entorno de test).
"""
from .. import mailer
from ..services.notification_service import push_gear_alert
from ..services.gear_service import life_pct


class TestLifePct:
    def test_below_target(self):
        assert life_pct(350.0, 700.0) == 50.0

    def test_zero_target_is_zero(self):
        assert life_pct(100.0, 0) == 0.0

    def test_caps_at_200(self):
        assert life_pct(2000.0, 700.0) == 200.0


class TestSendGearAlert:
    def test_send_gear_alert_80pct_does_not_raise_without_resend_key(self):
        mailer.send_gear_alert("athlete@test.com", "Ana", "Hoka Clifton", "shoe", 85.0, 80)

    def test_send_gear_alert_100pct_does_not_raise(self):
        mailer.send_gear_alert("athlete@test.com", "Ana", "Cadena (Canyon Aeroad)", "component", 105.0, 100)


class TestPushGearAlert:
    def test_push_payload_80pct_shoe(self):
        p = push_gear_alert("Hoka Clifton", "shoe", 85.0, 80)
        assert p["type"] == "gear_alert"
        assert "85" in p["title"]
        assert p["url"] == "/gear.html"

    def test_push_payload_100pct_component(self):
        p = push_gear_alert("Cadena", "component", 105.0, 100)
        assert "100" in p["title"] or "llegó" in p["title"]
        assert "reemplazarlo" in p["body"].lower()
