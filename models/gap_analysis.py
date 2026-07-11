"""
3-Way Gap Analysis Engine.

Compares:
  A  — Garmin-based prediction (uses device metrics: Garmin FTP, VO2max, CSS)
  B  — Target time (athlete's race goal or course benchmark)
  C  — Manual prediction (uses manually entered FTP, CSS, threshold pace)

Gap A↔C : Calibration gap — identifies over/under-estimation by Garmin.
Gap C↔B : Performance gap — how far the athlete's fitness is from the race goal.
Gap A↔B : Garmin gap — whether the algorithm is being over/under-used.

Also generates context-specific training recommendations based on the
course profile (Curva B) and identified weakest discipline.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


# ── Data structures ───────────────────────────────────────────────────────

@dataclass
class SplitResult:
    swim_s: float
    bike_s: float
    run_s:  float
    t1_s:   float = 240.0   # default 4 min T1
    t2_s:   float = 180.0   # default 3 min T2

    @property
    def total_s(self) -> float:
        return self.swim_s + self.t1_s + self.bike_s + self.t2_s + self.run_s


@dataclass
class CourseProfile:
    """Summarised course characteristics for recommendation logic."""
    bike_elevation_gain_m: float = 800.0
    bike_distance_km:      float = 90.0
    run_elevation_gain_m:  float = 120.0
    run_distance_km:       float = 21.1
    wind_ms:               float = 0.0
    temperature_c:         float = 22.0
    altitude_m:            float = 0.0
    surface:               str   = "asfalto"


@dataclass
class AthleteMetrics:
    """Snapshot of athlete metrics for gap commentary."""
    garmin_ftp: float
    manual_ftp: float
    garmin_css: float   # sec/100m
    manual_css: float
    garmin_run_pace: float   # sec/km threshold
    manual_run_pace: float
    ctl: float
    atl: float
    tsb: float
    weight_kg: float


# ── Gap analysis ──────────────────────────────────────────────────────────

@dataclass
class GapReport:
    # Raw time gaps (positive = A/C is SLOWER than B)
    gap_a_vs_b_s: float
    gap_c_vs_b_s: float
    gap_a_vs_c_s: float

    # Discipline-level gaps (A vs C)
    swim_gap_s:  float
    bike_gap_s:  float
    run_gap_s:   float

    # Calibration issues
    ftp_discrepancy_pct:      float
    css_discrepancy_pct:      float
    run_pace_discrepancy_pct: float

    # Recommendations
    recommendations: list = field(default_factory=list)
    alerts:          list = field(default_factory=list)
    radar_data:      dict = field(default_factory=dict)

    @property
    def weakest_discipline(self) -> str:
        gaps = {'Natación': self.swim_gap_s, 'Ciclismo': self.bike_gap_s,
                'Carrera': self.run_gap_s}
        return max(gaps, key=gaps.get)

    @property
    def a_on_target(self) -> bool:
        return self.gap_a_vs_b_s <= 0

    @property
    def c_on_target(self) -> bool:
        return self.gap_c_vs_b_s <= 0


def analyse_gaps(
    prediction_a: SplitResult,      # Garmin-based
    prediction_c: SplitResult,      # Manual-based
    target_b:     SplitResult,      # Goal / course benchmark
    metrics:      AthleteMetrics,
    course:       CourseProfile,
) -> GapReport:
    """Compute full 3-way gap analysis and generate recommendations."""

    # ── Time gaps ──────────────────────────────────────────────────
    gap_a_b = prediction_a.total_s - target_b.total_s
    gap_c_b = prediction_c.total_s - target_b.total_s
    gap_a_c = prediction_a.total_s - prediction_c.total_s

    swim_gap = prediction_a.swim_s - prediction_c.swim_s
    bike_gap = prediction_a.bike_s - prediction_c.bike_s
    run_gap  = prediction_a.run_s  - prediction_c.run_s

    # ── Metric discrepancies ────────────────────────────────────────
    ftp_disc = (metrics.manual_ftp - metrics.garmin_ftp) / metrics.garmin_ftp * 100
    css_disc = (metrics.manual_css - metrics.garmin_css) / metrics.garmin_css * 100
    run_disc = (metrics.manual_run_pace - metrics.garmin_run_pace) / metrics.garmin_run_pace * 100

    alerts = []
    recommendations = []

    # ── Calibration alerts (A vs C) ─────────────────────────────────
    if abs(ftp_disc) > 8:
        if ftp_disc > 0:
            alerts.append({
                'type': 'warning',
                'msg': f"⚠️ Tu FTP manual ({metrics.manual_ftp:.0f}W) es {abs(ftp_disc):.0f}% "
                       f"mayor que el de Garmin ({metrics.garmin_ftp:.0f}W). "
                       "Considera validar con un test de 20 minutos o ramp test."
            })
        else:
            alerts.append({
                'type': 'info',
                'msg': f"ℹ️ Garmin estima tu FTP ({metrics.garmin_ftp:.0f}W) un {abs(ftp_disc):.0f}% "
                       f"por encima de tu registro manual ({metrics.manual_ftp:.0f}W). "
                       "El algoritmo puede estar sobreestimando tu umbral."
            })

    if abs(css_disc) > 10:
        alerts.append({
            'type': 'warning',
            'msg': f"⚠️ Diferencia de {abs(css_disc):.0f}% entre CSS Garmin y manual. "
                   "Ejecuta un test T-30 o CSS para calibrar el dato de natación."
        })

    if abs(run_disc) > 8:
        alerts.append({
            'type': 'warning',
            'msg': f"⚠️ Umbral carrera: discrepancia de {abs(run_disc):.0f}% entre perfil manual "
                   "y Garmin. Haz un test de 30' o usa la estimación del reloj tras un esfuerzo máximo."
        })

    # ── Fatigue / readiness alerts ───────────────────────────────────
    if metrics.tsb < -20:
        alerts.append({
            'type': 'danger',
            'msg': f"🔴 TSB actual: {metrics.tsb:.0f} (alta fatiga). "
                   "La predicción Garmin incluye penalización por carga acumulada. "
                   "Considera un bloque de recuperación de 7–10 días antes de la carrera."
        })
    elif metrics.tsb < -10:
        alerts.append({
            'type': 'warning',
            'msg': f"🟡 TSB: {metrics.tsb:.0f} — fatiga moderada. "
                   "Rendimiento óptimo esperado con 5–7 días de taper."
        })
    elif metrics.tsb > 15:
        alerts.append({
            'type': 'success',
            'msg': f"🟢 TSB: {metrics.tsb:.0f} — forma óptima. "
                   "Cuerpo descansado y listo para rendir al máximo."
        })

    # ── Performance recommendations (C vs B) ─────────────────────────
    elev_per_km = course.bike_elevation_gain_m / max(course.bike_distance_km, 1)
    is_hilly     = elev_per_km > 12       # > 12 m/km = hilly bike
    is_hot       = course.temperature_c > 27
    is_windy     = course.wind_ms > 5
    is_altitude  = course.altitude_m > 1500
    is_trail     = course.surface in ("trail", "mixto")

    if gap_c_b > 0:
        # Athlete is slower than goal — prescribe specific work
        deficit_min = gap_c_b / 60

        recommendations.append({
            'priority': 'high',
            'category': '🎯 Brecha de Rendimiento',
            'msg': f"Tu predicción manual está {deficit_min:.1f} min por encima de tu meta. "
                   "Necesitas ganancias en:"
        })

        # Identify biggest discipline gap (C vs B proportional)
        if gap_c_b > 0:
            swim_need = (target_b.swim_s - prediction_c.swim_s) / target_b.swim_s
            bike_need = (target_b.bike_s - prediction_c.bike_s) / target_b.bike_s
            run_need  = (target_b.run_s  - prediction_c.run_s)  / target_b.run_s

            if bike_need < -0.04:  # bike is slowest relative to goal
                if is_hilly:
                    recommendations.append({
                        'priority': 'high',
                        'category': '🚵 Ciclismo — Fuerza en Subida',
                        'msg': f"El circuito tiene {course.bike_elevation_gain_m:.0f}m D+ "
                               f"({elev_per_km:.0f}m/km). Bloque de 4–6 semanas: "
                               "Intervalos de 5–10 min al 105–115% FTP en subida, "
                               "y sesiones de Sweet Spot (88–93% FTP) × 3 × 15 min."
                    })
                elif is_windy:
                    recommendations.append({
                        'priority': 'high',
                        'category': '💨 Ciclismo — Aerodinámica y Ritmo',
                        'msg': "Circuito plano con viento. Prioriza: "
                               "1) Posición TT (reducir CdA < 0.28), "
                               "2) Intervalos de ritmo constante 88–93% FTP × 30 min × 3, "
                               "3) Practica pacing de viento lateral."
                    })
                else:
                    recommendations.append({
                        'priority': 'high',
                        'category': '🚵 Ciclismo — Potencia en Umbral',
                        'msg': "Incrementa FTP: 3 × semana, progresión 3:1 (carga:recuperación). "
                               "Enfoque en Threshold Intervals (95–100% FTP) 4 × 8 min."
                    })

            if run_need < -0.04:
                if is_hot:
                    recommendations.append({
                        'priority': 'high',
                        'category': '🌡️ Carrera — Adaptación al Calor',
                        'msg': f"Temperatura esperada: {course.temperature_c}°C. "
                               "Protocolo de aclimatación: "
                               "2–3 semanas de rodajes con capas extra o sauna post-entreno (20 min). "
                               "Estrategia de carrera: ritmo conservador primeros 5 km, "
                               "ice-packs en transición."
                    })
                if is_trail:
                    recommendations.append({
                        'priority': 'medium',
                        'category': '🏔️ Carrera — Específico de Terreno',
                        'msg': "Incorpora rodajes en trail o superficies similares "
                               "al circuito (1–2 × semana). Fortalece tobillos y core."
                    })
                else:
                    recommendations.append({
                        'priority': 'high',
                        'category': '🏃 Carrera — Umbral de Lactato',
                        'msg': "Trabajos clave para mejorar umbral: "
                               "1) Intervalos al umbral (T-pace): 4 × 1 km, "
                               "2) Rodajes progresivos (tempo-run) 20–30 min, "
                               "3) Run-off-bike: ladrillos bike → run × 2 semana."
                    })

            if swim_need < -0.05:
                recommendations.append({
                    'priority': 'medium',
                    'category': '🏊 Natación — CSS',
                    'msg': "Sesiones técnicas: CSS intervals (8–10 × 100m al paso de CSS +2s). "
                           "Practica salidas en aguas abiertas si el circuito es mar/lago."
                })

        # Altitude recommendations
        if is_altitude:
            recommendations.append({
                'priority': 'medium',
                'category': '⛰️ Altitud',
                'msg': f"La carrera es a {course.altitude_m:.0f} m s.n.m. "
                       "VO2max reducido ≈ 1% por cada 100m sobre 1500m. "
                       "Si es posible, llega 2–3 días antes para aclimatación. "
                       "Reduce expectativas de potencia y ritmo un 5–8%."
            })

    else:
        recommendations.append({
            'priority': 'success',
            'category': '✅ En Camino',
            'msg': f"Tu perfil manual proyecta un tiempo {abs(gap_c_b/60):.1f} min "
                   "por debajo de tu meta. ¡Mantén la planificación de taper y "
                   "optimiza la nutrición y estrategia de carrera!"
        })

    # ── Radar data (normalized 0–100 per discipline) ─────────────────
    def _pct_of_target(predicted_s: float, target_s: float) -> float:
        if target_s <= 0:
            return 100.0
        return max(0.0, min(150.0, (target_s / predicted_s) * 100.0))

    radar_data = {
        'disciplines': ['Natación', 'Ciclismo', 'Carrera'],
        'A_pct':  [_pct_of_target(prediction_a.swim_s, target_b.swim_s),
                   _pct_of_target(prediction_a.bike_s, target_b.bike_s),
                   _pct_of_target(prediction_a.run_s,  target_b.run_s)],
        'C_pct':  [_pct_of_target(prediction_c.swim_s, target_b.swim_s),
                   _pct_of_target(prediction_c.bike_s, target_b.bike_s),
                   _pct_of_target(prediction_c.run_s,  target_b.run_s)],
        'B_pct':  [100.0, 100.0, 100.0],
    }

    return GapReport(
        gap_a_vs_b_s=gap_a_b,
        gap_c_vs_b_s=gap_c_b,
        gap_a_vs_c_s=gap_a_c,
        swim_gap_s=swim_gap,
        bike_gap_s=bike_gap,
        run_gap_s=run_gap,
        ftp_discrepancy_pct=ftp_disc,
        css_discrepancy_pct=css_disc,
        run_pace_discrepancy_pct=run_disc,
        recommendations=recommendations,
        alerts=alerts,
        radar_data=radar_data,
    )
