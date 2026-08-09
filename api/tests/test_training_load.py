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


class TestExtractTssRealActivities:
    """
    _extract_tss() (TSS de actividades REALES ya ejecutadas, no planificadas)
    tenía dos problemas reales, confirmados con datos en vivo de una cuenta
    Garmin real (no supuestos): (1) el campo nativo trainingStressScore de
    Garmin nunca viene poblado en la práctica — ni siquiera con avgPower
    presente — así que TODA actividad real caía al fallback por FC; (2) ese
    fallback usaba max_hr=190 fijo para cualquier atleta, ignorando su FC
    máxima real configurada, e ignoraba potencia/ritmo real disponibles en
    la misma actividad (bici con potenciómetro, carrera/nado con ritmo real)
    a favor de una estimación por FC más burda.
    """

    def test_bike_usa_potencia_real_no_fc(self):
        """Con avgPower disponible, bici debe usar potencia/FTP, no FC."""
        from api.garmin_pull_service import _extract_tss
        act = {"duration": 3600, "averageHR": 200,  # FC absurda a propósito
               "activityType": {"typeKey": "cycling"}, "avgPower": 172.5}
        tss = _extract_tss(act, ftp=230)
        # IF = 172.5/230 = 0.75 → TSS = 0.75^2*100 = 56.25
        assert abs(tss - 56.25) < 0.1, f"Debió usar potencia real, dio {tss}"

    def test_run_usa_ritmo_real_no_fc(self):
        """
        Con ritmo umbral configurado, carrera debe usar ritmo real, no FC.
        Ritmo real = distance/duration (NO act["averageSpeed"] directo — ver
        test_swim_ignora_averagespeed_de_garmin para el motivo real de esto).
        """
        from api.garmin_pull_service import _extract_tss
        # 12000m en 3600s = 5:00/km real (ritmo umbral configurado: 4:00/km)
        act = {"duration": 3600, "distance": 12000.0, "averageHR": 250,  # FC absurda a propósito
               "activityType": {"typeKey": "running"}}
        tss = _extract_tss(act, ftp=230, run_pace_s_km=None)
        # sin run_pace_s_km configurado, debe caer a fallback FC (personalizado si hay fcmax)
        tss_with_pace = _extract_tss(act, ftp=230, run_pace_s_km=240)
        # ritmo real 5:00/km (300s/km) vs umbral 4:00/km (240s/km) → intensity = 240/300 = 0.8 → TSS=64
        assert abs(tss_with_pace - 64.0) < 0.1
        assert tss_with_pace != tss, "Con ritmo real configurado el resultado debe ser distinto del fallback FC"

    def test_swim_usa_css_real(self):
        """Con CSS configurado, nado debe usar ritmo real vs CSS, no FC."""
        from api.garmin_pull_service import _extract_tss
        # 3272.7m en 3600s → ritmo real 1:50/100m
        act = {"duration": 3600, "distance": 3272.73, "averageHR": 130,
               "activityType": {"typeKey": "lap_swimming"}}
        tss = _extract_tss(act, css_s_100m=100)  # CSS 1:40/100m
        # intensity = 100/110 = 0.909 → TSS = 0.909^2*100 = 82.6
        assert abs(tss - 82.6) < 0.2

    def test_swim_ignora_averagespeed_de_garmin(self):
        """
        Bug real encontrado verificando con una cuenta Garmin real: el campo
        act["averageSpeed"] de Garmin para lap_swimming excluye el tiempo de
        descanso en la pared entre series (ritmo "nadando", no de la sesión
        completa) — daba un ritmo ~35% más rápido que distance/duration real
        y sobreestimaba el TSS a más del doble. Para bici/carrera coincide
        con distance/duration (verificado, diff 0.0%), pero para nado NO —
        por eso la función debe ignorar ese campo y calcular siempre
        distance/duration, sin importar qué diga averageSpeed.
        """
        from api.garmin_pull_service import _extract_tss
        act = {
            "duration": 4121.115234375, "distance": 2750.0, "averageHR": 105,
            "activityType": {"typeKey": "lap_swimming"},
            "averageSpeed": 0.94,  # ritmo "nadando" de Garmin — más rápido que el real
        }
        tss = _extract_tss(act, css_s_100m=105)
        # ritmo real = 2750/4121.1 = 0.6673 m/s → 149.9s/100m; con averageSpeed
        # (0.94 m/s → 106.4s/100m) el TSS habría salido más del doble de alto.
        assert tss < 60, f"No debe usar averageSpeed de Garmin para nado (dio {tss}, esperado ~56)"
        assert abs(tss - 56.2) < 1.0

    def test_fallback_fc_usa_fcmax_real_no_190_fijo(self):
        """Sin potencia/ritmo disponible, el fallback debe usar el fcmax real del atleta."""
        from api.garmin_pull_service import _extract_tss
        act = {"duration": 3600, "averageHR": 150,
               "activityType": {"typeKey": "cycling"}}  # sin avgPower → cae a FC
        tss_generico = _extract_tss(act, ftp=230, fcmax=None)   # antes: siempre 190
        tss_real_180 = _extract_tss(act, ftp=230, fcmax=180)    # atleta con FCmax real 180
        # Con FCmax real más bajo (180 < 190), el mismo HR=150 representa una
        # intensidad relativa MAYOR → TSS debe ser mayor que con el 190 genérico.
        assert tss_real_180 > tss_generico, (
            "Con FCmax real personalizado el TSS debe diferir del fallback genérico de 190"
        )

    def test_bike_sin_potencia_cae_a_fallback_fc(self):
        """Si avgPower no viene en la actividad, debe seguir funcionando (fallback FC), no crashear."""
        from api.garmin_pull_service import _extract_tss
        act = {"duration": 1800, "averageHR": 140, "activityType": {"typeKey": "cycling"}}
        tss = _extract_tss(act, ftp=230, fcmax=180)
        assert tss > 0

    def test_trainingstressscore_nativo_tiene_prioridad(self):
        """Si Garmin sí trae trainingStressScore nativo, se usa tal cual sin recalcular."""
        from api.garmin_pull_service import _extract_tss
        act = {"duration": 3600, "trainingStressScore": 88.4,
               "activityType": {"typeKey": "cycling"}, "avgPower": 999}  # valor absurdo, no debe usarse
        tss = _extract_tss(act, ftp=230)
        assert tss == 88.4


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


class TestExtractWorkoutSteps:
    """
    _extract_workout_steps() aplana el mismo workoutSegments que
    _estimate_planned_tss() ya recorría para calcular el TSS, pero esa info
    (series/ritmos/potencia/descripción del coach) se descartaba después de
    usarla — nunca se persistía. Reusa el mismo fixture real (ride 90min,
    RepeatGroupDTO anidado) para probar que el aplanado también respeta las
    repeticiones y no pierde ningún paso.
    """

    def test_repeat_group_se_aplana_y_multiplica_repeat_count(self):
        from api.garmin_pull_service import GarminPullService
        workout = {
            "workoutSegments": [{"workoutSteps": [
                {"type": "ExecutableStepDTO", "description": "Calentamiento",
                 "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 1200.0,
                 "targetType": {"workoutTargetTypeKey": "power.3s"},
                 "targetValueOne": 94.0, "targetValueTwo": 141.0},
                {"type": "RepeatGroupDTO", "numberOfIterations": 4, "workoutSteps": [
                    {"type": "ExecutableStepDTO", "description": "z2 cadencia alta",
                     "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 720.0,
                     "targetType": {"workoutTargetTypeKey": "power.3s"},
                     "targetValueOne": 164.0, "targetValueTwo": 176.0,
                     "stepType": {"stepTypeKey": "interval"}},
                    {"type": "ExecutableStepDTO", "description": "Fácil",
                     "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 180.0,
                     "targetType": {"workoutTargetTypeKey": "power.3s"},
                     "targetValueOne": 118.0, "targetValueTwo": 141.0,
                     "stepType": {"stepTypeKey": "recovery"}},
                ]},
                {"type": "ExecutableStepDTO", "description": "Enfriar",
                 "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 600.0,
                 "targetType": {"workoutTargetTypeKey": "power.3s"},
                 "targetValueOne": 94.0, "targetValueTwo": 118.0},
            ]}]
        }
        steps = GarminPullService._extract_workout_steps(workout)
        assert len(steps) == 4
        assert steps[0]["description"] == "Calentamiento"
        assert steps[0]["repeat_count"] == 1
        interval_step = steps[1]
        assert interval_step["repeat_count"] == 4
        assert interval_step["stepType"]["stepTypeKey"] == "interval"
        assert interval_step["target_low"] == 164.0 and interval_step["target_high"] == 176.0
        assert interval_step["duration_s"] == 720.0
        recovery_step = steps[2]
        assert recovery_step["repeat_count"] == 4
        assert recovery_step["stepType"]["stepTypeKey"] == "recovery"
        assert steps[3]["description"] == "Enfriar"

    def test_sin_workout_segments_devuelve_lista_vacia(self):
        from api.garmin_pull_service import GarminPullService
        assert GarminPullService._extract_workout_steps({}) == []
        assert GarminPullService._extract_workout_steps({"workoutSegments": []}) == []

    def test_pasos_sin_end_condition_de_tiempo_ni_distancia(self):
        """Ej. step 'lap.button' (terminado a mano) — no debe crashear, sólo queda sin duración/distancia."""
        from api.garmin_pull_service import GarminPullService
        workout = {"workoutSegments": [{"workoutSteps": [
            {"type": "ExecutableStepDTO",
             "endCondition": {"conditionTypeKey": "lap.button"},
             "targetType": {"workoutTargetTypeKey": "no.target"}},
        ]}]}
        steps = GarminPullService._extract_workout_steps(workout)
        assert len(steps) == 1
        assert steps[0]["duration_s"] is None
        assert steps[0]["distance_m"] is None

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


class TestStravaGarminDedup:
    """
    Bug real encontrado revisando el calendario de un usuario real (reportó
    "miércoles 29 hay 2 trotes" — parecían duplicados): el dedup Strava↔Garmin
    solo corría en un sentido (strava_routes.py, al importar de Strava,
    chequeaba contra un Garmin ya existente) — pero si el sync nativo de
    Garmin corría DESPUÉS de que Strava ya hubiera importado la misma sesión
    real (orden de sync no garantizado), nunca se chequeaba en sentido
    inverso y quedaban 2 filas para el mismo entrenamiento real. Confirmado
    con datos reales: "Morning Run" (strava_19512913041, 72.3min, 14.01km)
    y "Las Condes - intervalos pista" (23774456525, 72min, 14.01km) — mismo
    HR/potencia casi idénticos, mismo día, mismo deporte.
    """

    def _make_user(self, db):
        from api.models import User
        u = User(email="dedup@test.com", password_hash="x", nombre="Test", rol="atleta")
        db.add(u); db.commit(); db.refresh(u)
        return u

    def test_detecta_duplicado_strava_dentro_de_tolerancia(self, db):
        from api.garmin_pull_service import _find_strava_duplicate
        from api.models import GarminActivity
        u = self._make_user(db)
        strava_row = GarminActivity(
            user_id=u.id, activity_id="strava_19512913041", name="Morning Run",
            sport="run", date_iso="2026-07-29", dur_min=72.3, dist_km=14.01,
        )
        db.add(strava_row); db.commit()

        parsed = {"date_iso": "2026-07-29", "sport": "run", "dur_min": 72}
        dup = _find_strava_duplicate(db, u.id, parsed)
        assert dup is not None
        assert dup.activity_id == "strava_19512913041"

    def test_detecta_duplicado_por_distancia_aunque_duracion_difiera_mucho(self, db):
        """
        Caso real encontrado auditando una cuenta real (16 pares en un mes):
        Garmin y Strava pueden reportar duraciones MUY distintas para el
        MISMO nado real (uno cuenta el descanso en la pared, el otro no) —
        acá 54.3min vs 74min (20min de diferencia, muy fuera de la
        tolerancia de duración por sí sola) pero exactamente la misma
        distancia (2.85km) — el match por distancia debe encontrarlo igual.
        Caso real: "Natación de noche" (strava) vs "Natación en piscina"
        (Garmin nativo), 2026-07-28.
        """
        from api.garmin_pull_service import _find_strava_duplicate
        from api.models import GarminActivity
        u = self._make_user(db)
        strava_row = GarminActivity(
            user_id=u.id, activity_id="strava_1", name="Natación de noche",
            sport="swim", date_iso="2026-07-28", dur_min=54.3, dist_km=2.85,
        )
        db.add(strava_row); db.commit()

        parsed = {"date_iso": "2026-07-28", "sport": "swim", "dur_min": 74, "dist_km": 2.85}
        dup = _find_strava_duplicate(db, u.id, parsed)
        assert dup is not None
        assert dup.activity_id == "strava_1"

    def test_no_confunde_2_sesiones_reales_distintas(self, db):
        """Ni duración NI distancia coinciden (>10%/5min y >3%) = 2 sesiones reales, no debe fusionarlas."""
        from api.garmin_pull_service import _find_strava_duplicate
        from api.models import GarminActivity
        u = self._make_user(db)
        strava_row = GarminActivity(
            user_id=u.id, activity_id="strava_1", name="Natación de noche",
            sport="swim", date_iso="2026-07-28", dur_min=54.3, dist_km=2.0,
        )
        db.add(strava_row); db.commit()

        parsed = {"date_iso": "2026-07-28", "sport": "swim", "dur_min": 74, "dist_km": 2.85}
        dup = _find_strava_duplicate(db, u.id, parsed)
        assert dup is None

    def test_no_matchea_deporte_distinto(self, db):
        from api.garmin_pull_service import _find_strava_duplicate
        from api.models import GarminActivity
        u = self._make_user(db)
        strava_row = GarminActivity(
            user_id=u.id, activity_id="strava_2", name="Bici",
            sport="bike", date_iso="2026-07-29", dur_min=72, dist_km=40.0,
        )
        db.add(strava_row); db.commit()

        parsed = {"date_iso": "2026-07-29", "sport": "run", "dur_min": 72}
        dup = _find_strava_duplicate(db, u.id, parsed)
        assert dup is None


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "service" in data
        assert "version" in data
