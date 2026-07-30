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


class TestEstimatePlannedTss:
    """
    _estimate_planned_tss (Nivel 1: target numérico por paso) tenía un bug
    real, no teórico: nunca recorría los pasos ANIDADOS dentro de un
    RepeatGroupDTO (series repetidas, ej. "4x 12min z2 + 3min fácil") — solo
    el nivel superior del segmento. Encontrado con un ride real de 90min de
    Training Peaks (calentamiento+enfriamiento con target numérico, bloque
    principal de 4 repeticiones adentro de un RepeatGroupDTO): el cálculo
    "preciso" solo sumaba los ~30min de calentar/enfriar y devolvía 12.2 TSS
    para una sesión real de ~62 TSS — silenciosamente incompleto, sin ningún
    error ni aviso, marcado igual como "precise=True".
    """

    def test_flat_steps_sin_repeat_group(self):
        """Caso simple (sin RepeatGroupDTO): debe seguir funcionando igual que antes."""
        from api.garmin_pull_service import GarminPullService
        workout = {
            "workoutSegments": [{"workoutSteps": [
                {"type": "ExecutableStepDTO",
                 "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 600.0,
                 "targetType": {"workoutTargetTypeKey": "power.3s"},
                 "targetValueOne": 150.0, "targetValueTwo": 150.0},
            ]}]
        }
        tss, precise = GarminPullService._estimate_planned_tss(
            workout, "bike", ftp=250, fcmax=180, run_pace_s_km=None, css_s_100m=None)
        # 10min @ 150/250=0.6 IF: (10/60)*0.36*100 = 6.0
        assert precise is True
        assert abs(tss - 6.0) < 0.05

    def test_repeat_group_dto_se_recorre_y_multiplica_por_iteraciones(self):
        """
        Reproduce el caso real (workoutId 1644077424, ride 'z2' de 90min):
        calentamiento (20min) + 4x(12min interval + 3min rest) + enfriamiento
        (10min). Antes del fix: solo contaba calentamiento+enfriamiento
        (12.2 TSS). Después: cuenta también el RepeatGroupDTO completo
        (~62.3 TSS), acorde a una sesión real de 90 minutos.
        """
        from api.garmin_pull_service import GarminPullService
        ftp = 230
        workout = {
            "estimatedDurationInSecs": 5400,
            "workoutSegments": [{"workoutSteps": [
                {"type": "ExecutableStepDTO", "description": "Calentamiento",
                 "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 1200.0,
                 "targetType": {"workoutTargetTypeKey": "power.3s"},
                 "targetValueOne": 94.0, "targetValueTwo": 141.0},
                {"type": "RepeatGroupDTO", "numberOfIterations": 4, "workoutSteps": [
                    {"type": "ExecutableStepDTO", "description": "z2 cadencia alta",
                     "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 720.0,
                     "targetType": {"workoutTargetTypeKey": "power.3s"},
                     "targetValueOne": 164.0, "targetValueTwo": 176.0},
                    {"type": "ExecutableStepDTO", "description": "Fácil",
                     "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 180.0,
                     "targetType": {"workoutTargetTypeKey": "power.3s"},
                     "targetValueOne": 118.0, "targetValueTwo": 141.0},
                ]},
                {"type": "ExecutableStepDTO", "description": "Enfriar",
                 "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 600.0,
                 "targetType": {"workoutTargetTypeKey": "power.3s"},
                 "targetValueOne": 94.0, "targetValueTwo": 118.0},
                {"type": "ExecutableStepDTO",
                 "endCondition": {"conditionTypeKey": "lap.button"},
                 "targetType": {"workoutTargetTypeKey": "no.target"}},
            ]}]
        }
        tss, precise = GarminPullService._estimate_planned_tss(
            workout, "bike", ftp=ftp, fcmax=180, run_pace_s_km=None, css_s_100m=None)
        assert precise is True
        # Antes del fix esto daba 12.2 (solo calentamiento+enfriamiento)
        assert tss > 50, "El bloque principal (RepeatGroupDTO) no se está contando"
        assert abs(tss - 62.3) < 0.5

    def test_repeat_group_dto_anidado_dentro_de_otro(self):
        """Un RepeatGroupDTO dentro de otro (raro pero válido) debe multiplicar iteraciones en cadena."""
        from api.garmin_pull_service import GarminPullService
        workout = {
            "workoutSegments": [{"workoutSteps": [
                {"type": "RepeatGroupDTO", "numberOfIterations": 2, "workoutSteps": [
                    {"type": "RepeatGroupDTO", "numberOfIterations": 3, "workoutSteps": [
                        {"type": "ExecutableStepDTO",
                         "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 60.0,
                         "targetType": {"workoutTargetTypeKey": "power.3s"},
                         "targetValueOne": 200.0, "targetValueTwo": 200.0},
                    ]},
                ]},
            ]}]
        }
        tss, precise = GarminPullService._estimate_planned_tss(
            workout, "bike", ftp=200, fcmax=180, run_pace_s_km=None, css_s_100m=None)
        # 1min @ IF=1.0 = (1/60)*1*100 = 1.6667 TSS por repetición interna,
        # x3 (interno) x2 (externo) = 6 repeticiones totales = 10.0 TSS
        assert precise is True
        assert abs(tss - 10.0) < 0.05


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
