"""
build_daily_insight() — casos "good"/"neutral": el usuario reportó
2026-08-13 que el mensaje llano y el texto de "Ver por qué" en el
dashboard eran casi idénticos (message_technical solo pegaba TSB/ACWR
adentro de la misma frase). Estos tests fijan que ahora el texto
técnico explica los umbrales reales chequeados (TSB/ACWR/HRV/sueño) y
es genuinamente distinto del mensaje llano, no una variación cosmética.
"""
from api.services.training_service import build_daily_insight


class TestDailyInsightWhyText:
    def test_good_case_technical_text_differs_meaningfully_from_plain_message(self):
        ins = build_daily_insight(
            tsb=18.0, atl=40.0, ctl=55.0, acwr=1.0, acwr_zone="optimal",
            hrv_last_night=62.0, hrv_trend=2.0,
            sleep_total_h=7.5, sleep_trend=0.2,
            compliance_week=95.0,
        )
        assert ins["severity"] == "good"
        assert ins["message"] != ins["message_technical"]
        assert "TSB" in ins["message_technical"]
        assert "ACWR" in ins["message_technical"]
        # el texto técnico debe confirmar explícitamente que HRV/sueño se
        # revisaron, no solo hablar de carga (TSB/ACWR)
        assert "HRV" in ins["message_technical"]
        assert "dormiste" in ins["message_technical"]

    def test_neutral_case_technical_text_differs_meaningfully_from_plain_message(self):
        ins = build_daily_insight(
            tsb=-3.0, atl=60.0, ctl=58.0, acwr=1.05, acwr_zone="optimal",
            hrv_last_night=55.0, hrv_trend=1.0,
            sleep_total_h=7.0, sleep_trend=0.1,
        )
        assert ins["severity"] == "neutral"
        assert ins["message"] != ins["message_technical"]
        assert "0.8" in ins["message_technical"] and "1.3" in ins["message_technical"]
        assert "-8" in ins["message_technical"] and "+15" in ins["message_technical"]

    def test_good_and_neutral_omit_recovery_clause_without_hrv_sleep_data(self):
        """Sin datos reales de HRV/sueño no se inventa la frase de
        recuperación — mismo criterio anti-dato-falso de siempre."""
        ins = build_daily_insight(
            tsb=20.0, atl=35.0, ctl=55.0, acwr=1.0, acwr_zone="optimal",
            compliance_week=90.0,
        )
        assert "HRV" not in ins["message_technical"]
        assert "dormiste" not in ins["message_technical"]

    def test_danger_case_unaffected(self):
        """No se tocó la lógica de los casos con señal fuerte (reduce) —
        solo good/neutral cambiaron."""
        ins = build_daily_insight(
            tsb=-25.0, atl=90.0, ctl=60.0, acwr=1.7, acwr_zone="danger",
        )
        assert ins["severity"] == "reduce"
        assert ins["headline"] == "Riesgo de lesión"
