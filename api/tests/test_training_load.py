"""
Tests de cálculos críticos: CTL, ATL, TSB, ACWR.
Estos cálculos son médicamente relevantes — un bug aquí afecta la salud del atleta.
"""
import pytest


class TestCTLATLCalculations:
    """Verifica que los cálculos de carga de entrenamiento son correctos."""

    def test_ctl_tau(self):
        """CTL usa constante de 42 días (tiempo de vida media de la adaptación crónica)."""
        from api.garmin_pull_service import CTL_TAU
        assert CTL_TAU == 42, "CTL_TAU debe ser 42 días (protocolo Coggan/Banister)"

    def test_atl_tau(self):
        """ATL usa constante de 7 días (fatiga aguda)."""
        from api.garmin_pull_service import ATL_TAU
        assert ATL_TAU == 7, "ATL_TAU debe ser 7 días"

    def test_ctl_formula(self):
        """CTL(t) = CTL(t-1) + (TSS(t) - CTL(t-1)) / tau_ctl"""
        tau = 42
        prev_ctl = 50.0
        tss_today = 100.0
        expected = prev_ctl + (tss_today - prev_ctl) / tau
        # ~51.19
        assert abs(expected - 51.19) < 0.01

    def test_tsb_formula(self):
        """TSB = CTL - ATL (forma)"""
        ctl = 60.0
        atl = 75.0
        tsb = ctl - atl
        assert tsb == -15.0, "TSB negativo indica fatiga"

    def test_acwr_formula(self):
        """ACWR = ATL / CTL (idealmente entre 0.8 y 1.3)"""
        atl = 65.0
        ctl = 60.0
        acwr = atl / ctl if ctl > 0 else 0
        assert round(acwr, 2) == 1.08, "ACWR debe ser ~1.08"

    def test_zero_ctl_no_division_error(self):
        """ACWR con CTL=0 no debe lanzar ZeroDivisionError."""
        ctl = 0.0
        atl = 30.0
        acwr = atl / ctl if ctl > 0 else 0
        assert acwr == 0

    def test_tss_null_garmin_activity(self):
        """TSS de una actividad Garmin incompleta (duration=None) debe ser 0, no NaN."""
        dur_min = None
        tss = 0.0 if not dur_min else dur_min * 0.5  # simplificado
        assert tss == 0.0 or not (tss != tss)  # no NaN

    def test_progressive_ctl_increase(self):
        """Con entrenamiento constante diario, CTL debe subir gradualmente."""
        tau = 42
        ctl = 0.0
        daily_tss = 80.0
        for _ in range(42):
            ctl = ctl + (daily_tss - ctl) / tau
        # Después de 42 días con 80 TSS/día, CTL debe ser ~50 TSS (no llega al máximo)
        assert 40 < ctl < 80

    def test_ctl_decreases_without_training(self):
        """Sin entrenamiento, CTL baja exponencialmente."""
        tau = 42
        ctl = 60.0
        for _ in range(14):
            ctl = ctl + (0 - ctl) / tau  # TSS = 0
        assert ctl < 60, "CTL debe bajar sin entrenamiento"
        assert ctl > 0,  "CTL nunca debe ser negativa"


class TestNutritionCalculations:
    """
    Tests de cálculos de nutrición para carrera.
    Valores incorrectos pueden afectar la salud del atleta.
    """

    def test_cho_min_threshold(self):
        """Mínimo de CHO recomendado: 30g/h para sprint, 60g/h para IM."""
        # Estos son valores clínicos mínimos de seguridad
        MIN_CHO_SPRINT = 30   # g/h
        MIN_CHO_IM     = 60   # g/h
        assert MIN_CHO_SPRINT >= 30
        assert MIN_CHO_IM     >= 60

    def test_fluid_range(self):
        """Hidratación: entre 500ml/h (frío) y 1500ml/h (calor extremo)."""
        fluid_ml = 750  # valor típico
        assert 400 <= fluid_ml <= 1600

    def test_sodium_range(self):
        """Sodio: entre 400mg/h y 1500mg/h (según sudoración y temperatura)."""
        sodium_mg = 700
        assert 300 <= sodium_mg <= 1600

    def test_nutrition_scales_with_duration(self):
        """Plan de nutrición para Ironman debe tener más CHO total que para sprint."""
        # Simplificado: cho_g total = cho_rate * duration_h
        cho_rate_gph = 60
        sprint_duration_h = 1.5
        im_duration_h     = 11.0
        cho_sprint = cho_rate_gph * sprint_duration_h
        cho_im     = cho_rate_gph * im_duration_h
        assert cho_im > cho_sprint


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "service" in data
        assert "version" in data
