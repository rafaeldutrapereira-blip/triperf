"""
build_daily_insight() — el usuario reportó 2026-08-13 que el mensaje
llano y el texto de "Ver por qué" en el dashboard eran casi idénticos,
y después pidió explícitamente que ese detalle técnico se organizara
en bullets ejecutivos en vez de un párrafo (message_technical pasó de
string a lista). Más tarde el mismo día pidió que el mensaje PRINCIPAL
(no solo el "ver por qué") también quedara en bullets — se agregó
message_bullets (2 bullets en lenguaje llano: observación +
recomendación), y "message" quedó como el join de esos bullets por
compatibilidad con otros consumidores (ej. el tooltip "i" de
lx-info.js, que nunca esperó una lista).
"""
from api.services.training_service import build_daily_insight


def _joined(ins):
    return " ".join(ins["message_technical"])


class TestDailyInsightWhyText:
    def test_message_technical_is_a_list_of_bullets(self):
        ins = build_daily_insight(
            tsb=-3.0, atl=60.0, ctl=58.0, acwr=1.05, acwr_zone="optimal",
        )
        assert isinstance(ins["message_technical"], list)
        assert len(ins["message_technical"]) >= 1
        assert all(isinstance(b, str) and b for b in ins["message_technical"])

    def test_good_case_technical_bullets_differ_meaningfully_from_plain_message(self):
        ins = build_daily_insight(
            tsb=18.0, atl=40.0, ctl=55.0, acwr=1.0, acwr_zone="optimal",
            hrv_last_night=62.0, hrv_trend=2.0,
            sleep_total_h=7.5, sleep_trend=0.2,
            compliance_week=95.0,
        )
        assert ins["severity"] == "good"
        joined = _joined(ins)
        assert ins["message"] != joined
        assert "TSB" in joined and "ACWR" in joined
        # los bullets deben confirmar explícitamente que HRV/sueño se
        # revisaron, no solo hablar de carga (TSB/ACWR)
        assert "HRV" in joined
        assert "Sueño" in joined

    def test_neutral_case_technical_bullets_mention_real_thresholds(self):
        ins = build_daily_insight(
            tsb=-3.0, atl=60.0, ctl=58.0, acwr=1.05, acwr_zone="optimal",
            hrv_last_night=55.0, hrv_trend=1.0,
            sleep_total_h=7.0, sleep_trend=0.1,
        )
        assert ins["severity"] == "neutral"
        joined = _joined(ins)
        assert ins["message"] != joined
        assert "0.8" in joined and "1.3" in joined
        assert "-8" in joined and "+15" in joined

    def test_good_and_neutral_omit_recovery_bullets_without_hrv_sleep_data(self):
        """Sin datos reales de HRV/sueño no se inventan esos bullets —
        mismo criterio anti-dato-falso de siempre."""
        ins = build_daily_insight(
            tsb=20.0, atl=35.0, ctl=55.0, acwr=1.0, acwr_zone="optimal",
            compliance_week=90.0,
        )
        joined = _joined(ins)
        assert "HRV" not in joined
        assert "Sueño" not in joined

    def test_danger_case_returns_bullets_too(self):
        """Los casos con señal fuerte (reduce) ya tenían texto técnico
        rico — ahora también viaja como lista de bullets, no solo
        good/neutral."""
        ins = build_daily_insight(
            tsb=-25.0, atl=90.0, ctl=60.0, acwr=1.7, acwr_zone="danger",
        )
        assert ins["severity"] == "reduce"
        assert ins["headline"] == "Riesgo de lesión"
        assert isinstance(ins["message_technical"], list)
        assert len(ins["message_technical"]) >= 2
        assert any("ACWR" in b for b in ins["message_technical"])


class TestDailyInsightMessageBullets:
    """message_bullets: el mensaje PRINCIPAL (siempre visible, no detrás
    de "ver por qué") también en bullets — pedido explícito del usuario
    2026-08-13, mismo día que el fix de message_technical."""

    def test_message_bullets_is_a_list_ending_in_recommendation(self):
        ins = build_daily_insight(
            tsb=-3.0, atl=60.0, ctl=58.0, acwr=1.05, acwr_zone="optimal",
        )
        assert isinstance(ins["message_bullets"], list)
        assert len(ins["message_bullets"]) == 2
        assert ins["message_bullets"][-1].startswith("Recomendación:")

    def test_message_is_join_of_message_bullets(self):
        """message (compat con lx-info.js y otros consumidores viejos)
        debe seguir siendo exactamente el join de message_bullets, no
        divergir en contenido."""
        ins = build_daily_insight(
            tsb=-25.0, atl=90.0, ctl=60.0, acwr=1.7, acwr_zone="danger",
        )
        assert ins["message"] == " ".join(ins["message_bullets"])

    def test_all_severities_return_two_message_bullets(self):
        cases = [
            dict(tsb=-25.0, atl=90.0, ctl=60.0, acwr=1.7, acwr_zone="danger"),           # reduce
            dict(tsb=-3.0, atl=60.0, ctl=58.0, acwr=1.05, acwr_zone="optimal"),          # neutral
            dict(tsb=18.0, atl=40.0, ctl=55.0, acwr=1.0, acwr_zone="optimal"),           # good
            dict(tsb=-25.0, atl=40.0, ctl=55.0, acwr=1.0, acwr_zone="optimal"),          # caution (TSB muy negativo)
        ]
        for kwargs in cases:
            ins = build_daily_insight(**kwargs)
            assert isinstance(ins["message_bullets"], list), ins["severity"]
            assert len(ins["message_bullets"]) == 2, ins["severity"]
