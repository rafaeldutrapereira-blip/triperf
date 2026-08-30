"""
Parciales deben excluir pausas reales (parado/descanso) del tiempo usado
para calcular el ritmo -- bug real reportado en vivo 2026-08-30: un
atleta se detuvo ~5min al inicio de una salida corta sin pausar el
reloj, y el parcial de ese km mostró "10:29/km" porque se usaba tiempo
transcurrido, no tiempo en movimiento.
"""
from ..routes.athlete_routes import (
    _compute_activity_splits, _total_paused_seconds, _PAUSE_GAP_THRESHOLD_S,
)


def _samples_no_pause(n_seconds=600, speed=3.33):
    """~2km sin pausas, ritmo constante (3.33 m/s ~ 5:00/km)."""
    return [{"t": float(i), "dist": speed * i} for i in range(n_seconds)]


class TestTotalPausedSeconds:
    def test_no_gaps_returns_zero(self):
        assert _total_paused_seconds(_samples_no_pause()) == 0.0

    def test_small_gap_below_threshold_not_counted(self):
        samples = [{"t": 0.0, "dist": 0.0}, {"t": _PAUSE_GAP_THRESHOLD_S - 1, "dist": 5.0}]
        assert _total_paused_seconds(samples) == 0.0

    def test_real_gap_above_threshold_counted(self):
        # Reproduce el caso real: salto de 309s con la distancia casi sin cambiar.
        samples = [{"t": 27.0, "dist": 87.2}, {"t": 336.0, "dist": 88.1}]
        assert _total_paused_seconds(samples) == 309.0

    def test_multiple_gaps_sum(self):
        # 3 huecos consecutivos por encima del umbral: 30s + 70s + 40s = 140s
        samples = [
            {"t": 0.0, "dist": 0.0}, {"t": 30.0, "dist": 0.5},
            {"t": 100.0, "dist": 300.0}, {"t": 140.0, "dist": 301.0},
        ]
        assert _total_paused_seconds(samples) == 140.0

    def test_less_than_2_samples_returns_zero(self):
        assert _total_paused_seconds([{"t": 0.0, "dist": 0.0}]) == 0.0
        assert _total_paused_seconds([]) == 0.0


class TestComputeActivitySplitsExcludesPauses:
    def test_split_without_pause_matches_elapsed_time(self):
        samples = _samples_no_pause(400, speed=1000 / 300)  # 1km cada 300s = 5:00/km
        splits = _compute_activity_splits(samples, "run")
        assert splits[0]["duration_s"] == 300
        assert splits[0]["avg_pace_s_per_km"] == 300

    def test_real_case_pause_excluded_from_first_split(self):
        """Reproduce el caso real reportado: km1 con una pausa real de
        309s no debe inflar el ritmo del parcial -- el tiempo en
        movimiento real de ese km (629-309=320s) es el que debe usarse,
        no los 629s transcurridos."""
        samples = []
        # 0-27s: primeros 87.2m corridos a ritmo normal
        for i in range(28):
            samples.append({"t": float(i), "dist": 87.2 * i / 27})
        # Pausa real: salto de t=27 a t=336, distancia casi sin cambiar
        samples.append({"t": 336.0, "dist": 88.1})
        # 336-629s: resto del km1 (911.9m) a ritmo normal
        remaining_dist = 1000.0 - 88.1
        remaining_time = 629.0 - 336.0
        n = 100
        for i in range(1, n + 1):
            samples.append({
                "t": 336.0 + remaining_time * i / n,
                "dist": 88.1 + remaining_dist * i / n,
            })
        # km2 completo, sin pausas, a ritmo real normal (294s/km real del caso)
        for i in range(1, 295):
            samples.append({"t": 629.0 + i, "dist": 1000.0 + (1000.0 / 294) * i})

        splits = _compute_activity_splits(samples, "run")
        assert len(splits) == 2

        # ANTES del fix: duration_s del km1 = 629 (10:29/km). Después:
        # se descuenta la pausa de 309s -> ~320s (5:20/km), no 10:29.
        assert splits[0]["duration_s"] < 400, "La pausa real no se está excluyendo del parcial"
        assert splits[0]["avg_pace_s_per_km"] < 400

        # km2 no tiene pausas -- no debe verse afectado
        assert abs(splits[1]["duration_s"] - 294) < 2

    def test_pause_at_segment_boundary_does_not_leak_into_next_split(self):
        """Una pausa justo al cruzar el límite del km no debe sumarse al
        parcial siguiente -- seg_paused_s se resetea en cada _flush()."""
        samples = [{"t": float(i), "dist": 1000.0 * i / 300} for i in range(301)]  # km1 real, 1 muestra/s
        # Pausa real de 100s exactamente en el límite del km1
        samples.append({"t": 400.0, "dist": 1000.5})
        samples += [{"t": 400.0 + i, "dist": 1000.5 + 1000.0 * i / 300} for i in range(1, 301)]  # km2 real
        splits = _compute_activity_splits(samples, "run")
        assert splits[0]["duration_s"] == 300  # sin pausa, no afectado
        # El segundo split arranca en t=400 (post-pausa) y termina en t=700:
        # 300s reales, sin pausas adentro de ESE segmento.
        assert splits[1]["duration_s"] == 300
