"""
S1 — Service Layer: Training Load (CTL/ATL/TSB/ACWR/Zonas).
Extrae lógica de negocio de athlete_routes.py — reutilizable desde rutas, tests y tareas.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import GarminActivity, GarminTrainingLoad, User

ACWR_SPORT_LABELS = {
    "swim": "Natación",
    "bike": "Ciclismo",
    "run":  "Trote",
    "gym":  "Fuerza / Prep. física",
}


# ─── Constantes de carga de entrenamiento ─────────────────────
_CTL_TC  = 42   # días — Chronic Training Load time constant (Banister)
_ATL_TC  = 7    # días — Acute Training Load time constant
_ALPHA_CTL = 1 - math.exp(-1 / _CTL_TC)
_ALPHA_ATL = 1 - math.exp(-1 / _ATL_TC)


# ─── Zonas de entrenamiento ───────────────────────────────────

def hr_zones(fcmax: int) -> dict:
    """Zonas FC según modelo 5-zonas (adaptado para triatlón)."""
    return {
        "z1": (round(fcmax * 0.50), round(fcmax * 0.60)),
        "z2": (round(fcmax * 0.60), round(fcmax * 0.70)),
        "z3": (round(fcmax * 0.70), round(fcmax * 0.80)),
        "z4": (round(fcmax * 0.80), round(fcmax * 0.90)),
        "z5": (round(fcmax * 0.90), fcmax),
    }


def ftp_zones(ftp: int) -> dict:
    """Zonas de potencia ciclismo (Coggan 7-zonas)."""
    return {
        "z1_active_recovery":  (0,              round(ftp * 0.55)),
        "z2_endurance":        (round(ftp * 0.55), round(ftp * 0.75)),
        "z3_tempo":            (round(ftp * 0.75), round(ftp * 0.90)),
        "z4_threshold":        (round(ftp * 0.90), round(ftp * 1.05)),
        "z5_vo2max":           (round(ftp * 1.05), round(ftp * 1.20)),
        "z6_anaerobic":        (round(ftp * 1.20), round(ftp * 1.50)),
        "z7_neuromuscular":    (round(ftp * 1.50), 9999),
    }


def run_pace_zones(threshold_pace_str: str) -> dict:
    """
    Zonas de ritmo carrera. threshold_pace_str: "4:52" (min/km).
    Retorna dict zona → (pace_min, pace_max) en segundos/km.
    """
    try:
        parts = threshold_pace_str.split(":")
        pace_sec = int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return {}
    return {
        "z1_easy":     (round(pace_sec * 1.30), 9999),
        "z2_aerobic":  (round(pace_sec * 1.15), round(pace_sec * 1.30)),
        "z3_tempo":    (round(pace_sec * 1.05), round(pace_sec * 1.15)),
        "z4_threshold":(round(pace_sec * 0.97), round(pace_sec * 1.05)),
        "z5_vo2max":   (0, round(pace_sec * 0.97)),
    }


def swim_css_zones(css_str: str) -> dict:
    """Zonas de natación desde CSS (Critical Swim Speed). css_str: '1:48' (min/100m)."""
    try:
        parts = css_str.split(":")
        css_sec = int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return {}
    return {
        "z1_recovery":  (round(css_sec * 1.30), 9999),
        "z2_aerobic":   (round(css_sec * 1.15), round(css_sec * 1.30)),
        "z3_threshold": (round(css_sec * 1.00), round(css_sec * 1.15)),
        "z4_speed":     (0, round(css_sec * 1.00)),
    }


def athlete_zones(user: User) -> dict:
    """Devuelve todas las zonas del atleta según métricas disponibles en su perfil."""
    result: dict = {}
    if user.fcmax:
        result["hr"] = hr_zones(user.fcmax)
    if user.ftp:
        result["power"] = ftp_zones(user.ftp)
    if user.run_pace:
        result["run_pace"] = run_pace_zones(user.run_pace)
    if user.css:
        result["swim"] = swim_css_zones(user.css)
    return result


# ─── Cálculo ACWR mejorado (BP-03) ───────────────────────────

def compute_acwr(load_rows: list, safe_minimum: float = 1.0) -> tuple[float, str]:
    """
    BP-03: ACWR con guardia cuando acute=0 o datos insuficientes.
    Devuelve (acwr_value, zone_string).
    zone: "no_data" | "low" | "optimal" | "warning" | "danger"
    """
    if len(load_rows) < 7:
        return 0.0, "no_data"

    last7  = load_rows[-7:]
    last28 = load_rows[-28:]
    acute   = sum(r.tss for r in last7)  / max(len(last7), 1)
    chronic = sum(r.tss for r in last28) / max(len(last28), 1)

    # BP-03: Si acute o chronic son cero → "no_data" en lugar de 0.0
    if acute < safe_minimum or chronic < safe_minimum:
        return 0.0, "no_data"

    acwr = round(acute / chronic, 2)

    if acwr >= 1.5:    zone = "danger"
    elif acwr >= 1.3:  zone = "warning"
    elif acwr >= 0.8:  zone = "optimal"
    else:              zone = "low"

    return acwr, zone


def _acwr_zone(value: Optional[float]) -> str:
    if value is None:
        return "no_data"
    if value >= 1.5:   return "danger"
    if value >= 1.3:   return "warning"
    if value >= 0.8:   return "optimal"
    return "low"


def compute_acwr_by_sport(user_id: str, db: Session, min_sessions_28d: int = 3) -> dict:
    """
    ACWR (7:28) desglosado por disciplina — natación, ciclismo, trote, fuerza.
    Un ACWR agregado puede verse "óptimo" mientras una sola disciplina tiene
    un pico de carga peligroso (ej. mucho más trote esta semana compensado
    por menos ciclismo); las lesiones por sobreuso son tejido-específicas,
    así que el riesgo real está en la carga por disciplina, no solo la total.
    """
    # Sin tope de fecha: detalle.html?metric=acwr filtra estos gráficos por
    # período en el cliente (Semana/Mes/3M/6M/Año/Todo). Antes esta función
    # cortaba a los últimos 120 días fijos — 6 Meses/Año/Todo mostraban
    # siempre el mismo tramo (todos ≥120 días), dando la impresión de que
    # los botones de período no hacían nada para esas tres opciones.
    acts = (
        db.query(GarminActivity)
          .filter(
              GarminActivity.user_id == user_id,
              GarminActivity.sport.in_(list(ACWR_SPORT_LABELS.keys())),
          )
          .all()
    )

    daily_tss: dict[str, dict[str, float]] = {s: {} for s in ACWR_SPORT_LABELS}
    for a in acts:
        bucket = daily_tss[a.sport]
        bucket[a.date_iso] = bucket.get(a.date_iso, 0.0) + (a.tss or 0.0)

    if acts:
        start = min(date.fromisoformat(a.date_iso) for a in acts)
    else:
        start = date.today()
    window_days = (date.today() - start).days + 1
    days = [(start + timedelta(days=i)).isoformat() for i in range(window_days)]

    result: dict = {}
    for sport, label in ACWR_SPORT_LABELS.items():
        series = [daily_tss[sport].get(d, 0.0) for d in days]
        history = []
        for idx in range(6, len(days)):
            window7  = series[max(0, idx - 6):idx + 1]
            window28 = series[max(0, idx - 27):idx + 1]
            chronic28 = sum(window28) / len(window28)
            if chronic28 < 1.0:
                continue
            acute7 = sum(window7) / len(window7)
            history.append({"dt": days[idx], "acwr": round(acute7 / chronic28, 2)})

        sessions_28d = sum(1 for d in days[-28:] if daily_tss[sport].get(d, 0.0) > 0)
        latest = history[-1]["acwr"] if history else None
        result[sport] = {
            "label":             label,
            "acwr":              latest,
            "zone":              _acwr_zone(latest),
            "history":           history,
            "sessions_28d":      sessions_28d,
            "insufficient_data": sessions_28d < min_sessions_28d,
        }

    return result


# ─── Alertas de entrenamiento ─────────────────────────────────

def build_training_alerts(tsb: float, acwr: float, acwr_zone: str, ctl: float) -> list[dict]:
    """
    Genera alertas de sobreentrenamiento / sub-entrenamiento.
    Versión mejorada con soporte a 'no_data' zone.
    """
    alerts: list[dict] = []

    if acwr_zone == "no_data":
        alerts.append({
            "level":   "info",
            "type":    "acwr_no_data",
            "title":   "Sin datos suficientes para ACWR",
            "message": "Necesitas al menos 7 días de actividad para calcular tu ratio de carga.",
            "icon":    "ℹ️",
        })
    elif acwr_zone == "danger":
        alerts.append({
            "level":   "danger",
            "type":    "acwr_danger",
            "title":   "⚠️ Alto riesgo de lesión",
            "message": f"Tu ACWR es {acwr:.2f} — muy por encima del umbral seguro (>1.5). Reduce carga inmediatamente.",
            "icon":    "🚨",
        })
    elif acwr_zone == "warning":
        alerts.append({
            "level":   "warning",
            "type":    "acwr_warning",
            "title":   "Carga elevada",
            "message": f"Tu ACWR ({acwr:.2f}) indica sobrecarga moderada. Prioriza recuperación.",
            "icon":    "⚠️",
        })
    elif acwr_zone == "low" and ctl > 20:
        alerts.append({
            "level":   "info",
            "type":    "acwr_low",
            "title":   "Carga por debajo de lo óptimo",
            "message": "Tu ACWR es bajo. Puedes aumentar volumen o intensidad gradualmente.",
            "icon":    "📉",
        })

    # TSB warnings
    if tsb < -30:
        alerts.append({
            "level":   "danger",
            "type":    "tsb_overreach",
            "title":   "Sobreentrenamiento detectado",
            "message": f"Tu TSB ({tsb:.0f}) indica fatiga acumulada severa. Descanso obligatorio.",
            "icon":    "😴",
        })
    elif tsb < -15:
        alerts.append({
            "level":   "warning",
            "type":    "tsb_fatigue",
            "title":   "Fatiga acumulada",
            "message": f"TSB {tsb:.0f}. Mantén intensidad pero reduce volumen esta semana.",
            "icon":    "🔋",
        })
    elif tsb > 25 and ctl > 30:
        alerts.append({
            "level":   "success",
            "type":    "tsb_peak",
            "title":   "Estado de forma óptimo",
            "message": f"TSB {tsb:.0f} — estás fresco y en buena forma. Ideal para competir o testear.",
            "icon":    "🚀",
        })

    return alerts


# ─── Insight del día — síntesis multi-señal para el dashboard ────────────────

def build_daily_insight(
    *,
    tsb: float,
    atl: float,
    ctl: float,
    acwr: float,
    acwr_zone: str,
    hrv_last_night: Optional[float] = None,
    hrv_7d_avg: Optional[float] = None,
    hrv_trend: Optional[float] = None,
    sleep_total_h: Optional[float] = None,
    sleep_trend: Optional[float] = None,
    rhr_trend: Optional[float] = None,
    acwr_by_sport: Optional[dict] = None,
    mental_score: Optional[float] = None,
    injury_risk: Optional[dict] = None,
    compliance_week: Optional[float] = None,
) -> dict:
    """
    Combina TSB/ACWR (carga) + HRV/sueño/FC reposo (recuperación) en UNA sola
    conclusión accionable, en vez de dejar que el atleta cruce 5 números por
    su cuenta. Reglas priorizadas: primero lo que compromete salud (ACWR/TSB
    extremos), después combinaciones de fatiga+mala recuperación, y solo si
    nada de eso aplica, el caso positivo o el neutral por falta de datos.
    """
    poor_sleep = (sleep_total_h is not None and sleep_total_h < 6.5) or (sleep_trend is not None and sleep_trend < -0.5)
    hrv_down   = hrv_trend is not None and hrv_trend <= -4
    hrv_up     = hrv_trend is not None and hrv_trend > 0
    rhr_up     = rhr_trend is not None and rhr_trend >= 4
    hrv_pct    = round(hrv_trend / (hrv_last_night - hrv_trend) * 100) if (hrv_down and hrv_last_night) else None

    # tone: mismo lenguaje de color que el resto de LabX — rojo = preocupante,
    # ámbar = precaución, verde = bien, texto normal = sin señal fuerte.
    drivers = []
    if hrv_last_night is not None:
        hrv_tone = "bad" if hrv_down else "good" if hrv_up else "neutral"
        hrv_delta = f"↓ {abs(hrv_pct)}%" if hrv_pct else (f"↑ {hrv_trend:.0f}ms" if hrv_up else None)
        drivers.append({
            "label": "HRV anoche", "value": f"{round(hrv_last_night)}ms",
            "tone": hrv_tone, "delta": hrv_delta,
        })
    tsb_tone = "bad" if tsb < -20 else "caution" if tsb < -8 else "good" if tsb > 15 else "neutral"
    drivers.append({
        "label": "TSB (forma)", "value": f"{tsb:+.0f}".replace("+-", "-"),
        "tone": tsb_tone, "delta": None,
    })
    if sleep_total_h is not None:
        h = int(sleep_total_h); m = round((sleep_total_h - h) * 60)
        sleep_tone = "bad" if poor_sleep else "good" if (sleep_trend or 0) > 0 else "neutral"
        drivers.append({
            "label": "Sueño anoche", "value": f"{h}h {m:02d}m",
            "tone": sleep_tone, "delta": None,
        })

    def _insight_recovery_clause(hrv_down, hrv_last_night, poor_sleep, sleep_total_h):
        """Frase corta para el 'ver por qué' de los casos good/neutral,
        confirmando explícitamente que HRV/sueño SÍ se revisaron y están
        bien — sin esto, el texto técnico hablaba solo de TSB/ACWR aunque
        el insight combina también recuperación, dejando la impresión de
        que esos datos no se habían tenido en cuenta."""
        bits = []
        if hrv_last_night is not None and not hrv_down:
            bits.append(f"tu HRV de anoche ({round(hrv_last_night)}ms) se mantiene estable")
        if sleep_total_h is not None and not poor_sleep:
            h = int(sleep_total_h); m = round((sleep_total_h - h) * 60)
            bits.append(f"dormiste {h}h {m:02d}m")
        if not bits:
            return ""
        return " Además, " + " y ".join(bits) + "."

    def _base(severity, headline, message, message_technical=None, cta=None, cta_href=None):
        # message: lenguaje llano, sin jerga ni números — lo que ve todo el
        # mundo por default. message_technical: la versión con TSB/ACWR/ATL
        # exactos, detrás del toggle "ver por qué" para quien quiera el dato duro.
        # cta_href: a dónde lleva el botón — explícito por caso, en vez de
        # inferirlo del severity en el frontend (eso mandaba todos los casos
        # "reduce" a recovery.html, aunque el CTA hablara de carga/ACWR).
        return {"severity": severity, "headline": headline, "message": message,
                "message_technical": message_technical or message,
                "drivers": drivers, "cta_label": cta, "cta_href": cta_href}

    # 1. Combinación crítica: mala recuperación (HRV/sueño) + carga ya alta
    if hrv_down and poor_sleep and (tsb < -8 or acwr_zone in ("warning", "danger")):
        hrv_pct_txt = f" ({hrv_pct}%)" if hrv_pct else ""
        return _base(
            "reduce", "Reducir carga hoy",
            "Tu cuerpo no se recuperó bien anoche y venís acumulando cansancio de varios días. "
            "Hoy conviene una sesión suave o descanso — evita los intervalos de alta intensidad.",
            f"Tu HRV bajó{hrv_pct_txt} a {round(hrv_last_night)}ms y tu forma (TSB) está en {tsb:.0f} "
            f"con fatiga acumulada (ATL {atl:.0f}). Sumado a que dormiste menos de lo habitual, hoy conviene "
            f"una sesión aeróbica suave o descanso — evita intervalos de alta intensidad.",
            "Ver protocolo de recuperación sugerido",
            "recovery.html",
        )

    # 2. ACWR en zona de riesgo — prioridad de seguridad
    if acwr_zone == "danger":
        return _base(
            "reduce", "Riesgo de lesión",
            "Subiste tu carga de entrenamiento muy rápido esta semana respecto a tus semanas previas. "
            "Bajale el volumen o la intensidad hoy para reducir el riesgo de lesión.",
            f"Tu ACWR es {acwr:.2f}, muy por encima del rango seguro (0.8–1.3). Subiste la carga demasiado rápido "
            f"esta semana respecto a tu promedio de 28 días — reduce volumen o intensidad hoy.",
            "Ver histórico de carga",
            "detalle.html?metric=acwr",
        )

    # 2.5. Riesgo oculto por disciplina: el ACWR agregado puede verse bien
    # mientras UNA disciplina específica tiene un pico peligroso de carga —
    # las lesiones por sobreuso son tejido-específicas, así que un pico en
    # una sola disciplina no se "diluye" promediando con el resto.
    if acwr_by_sport:
        risky_sports = [
            s for s in acwr_by_sport.values()
            if s.get("zone") == "danger" and not s.get("insufficient_data") and s.get("acwr") is not None
        ]
        if risky_sports:
            worst = max(risky_sports, key=lambda s: s["acwr"])
            drivers.append({
                "label": "ACWR " + worst["label"], "value": f"{worst['acwr']:.2f}",
                "tone": "bad", "delta": None,
            })
            return _base(
                "reduce", f"Riesgo de lesión en {worst['label']}",
                f"Tu carga general se ve bien, pero en {worst['label'].lower()} subiste el volumen mucho más rápido "
                f"que en el resto de tu entrenamiento. Bajale el ritmo en esa disciplina esta semana.",
                f"ACWR de {worst['label']} = {worst['acwr']:.2f} (zona de riesgo, >1.5) mientras el ACWR general es "
                f"{acwr:.2f} ({acwr_zone}). Las lesiones por sobreuso son específicas de tejido — un pico aislado en "
                f"una disciplina no se compensa con el resto.",
                "Ver ACWR por disciplina",
                "detalle.html?metric=acwr",
            )

    # 2.75. Injury Risk Score consolidado (injury_risk_service.py: ACWR 35% +
    # HRV 30% + Monotonía 20% + Labs 15%) en zona alta/crítica por una vía
    # que las reglas 2/2.5 de arriba NO detectan porque solo miran ACWR —
    # ej. monotonía alta (misma carga todos los días) o un marcador de
    # sangre alterado pueden elevar el riesgo real aunque el ACWR se vea
    # en rango. Sin este bloque, esas señales quedaban calculadas (se ven
    # en su propia card del dashboard) pero nunca influían en el insight.
    if injury_risk and injury_risk.get("level") in ("high", "critical") and injury_risk.get("score") is not None:
        drivers.append({
            "label": "Riesgo de lesión", "value": f"{round(injury_risk['score'])}/100",
            "tone": "bad" if injury_risk["level"] == "critical" else "caution", "delta": None,
        })
        critical = injury_risk["level"] == "critical"
        return _base(
            "reduce" if critical else "caution",
            "Riesgo de lesión " + ("crítico" if critical else "alto"),
            "Tu score de riesgo de lesión — que combina tu carga, HRV, monotonía de entrenamiento y tus "
            "últimos exámenes de sangre — está elevado, aunque tu carga de hoy por sí sola no lo muestre. "
            "Priorizá recuperación antes de sumar más intensidad.",
            f"Injury Risk Score = {round(injury_risk['score'])}/100 ({injury_risk['level']}), motor que combina "
            f"ACWR (35%), HRV (30%), monotonía de entrenamiento (20%) y marcadores de sangre (15%). Puede estar "
            f"elevado por monotonía o labs aunque el ACWR aislado (hoy {acwr:.2f}) se vea en rango.",
            "Ver detalle de riesgo de lesión",
            "ai_coach.html",
        )

    # 3. Fatiga acumulada profunda (TSB muy negativo) aunque HRV/sueño no acompañen datos
    if tsb < -20:
        return _base(
            "caution", "Fatiga acumulada",
            "Venís acumulando cansancio por varios días seguidos de entrenamiento exigente. "
            "Mantené la intensidad baja y priorizá el descanso esta semana.",
            f"Tu TSB está en {tsb:.0f} — nivel de fatiga alto tras varios días de carga sostenida (ATL {atl:.0f}). "
            f"Mantén la intensidad baja y prioriza descanso esta semana para no entrar en sobreentrenamiento.",
            "Ver histórico PMC",
            "detalle.html?metric=ctl",
        )

    # 3.5. Fatiga mental alta (check-in de mental.html) aunque la carga y la
    # recuperación física se vean bien — Garmin no puede medir esto, es la
    # única señal subjetiva del atleta. Va ANTES de la señal física única
    # (regla 4) a propósito: esa regla es muy permisiva (se dispara con
    # cualquier señal leve, ej. dormir un poco menos) y si quedara primero
    # se comía silenciosamente una fatiga mental crítica real (bug detectado
    # con el check-in real de Rafael: MFS ~14/100 nunca se mostraba porque
    # el sueño levemente bajo de esa noche disparaba la regla 4 antes).
    # Solo se activa si hizo el check-in (mental_score no es None); nunca
    # se inventa el dato.
    if mental_score is not None and mental_score < 55:
        mfs_label = "crítica" if mental_score < 40 else "alta"
        drivers.append({
            "label": "Fatiga mental (check-in)", "value": f"{round(mental_score)}/100",
            "tone": "bad" if mental_score < 40 else "caution", "delta": None,
        })
        return _base(
            "caution" if mental_score >= 40 else "reduce",
            "Fatiga mental " + mfs_label,
            "Tu carga y tu recuperación física se ven bien, pero tu check-in mental de hoy muestra fatiga "
            + mfs_label + ". Considerá acortar la sesión o priorizar descanso mental — el rendimiento no es "
            "solo físico.",
            f"Mental Fatigue Score = {round(mental_score)}/100 (checkin de mental.html) mientras la carga física "
            f"(TSB {tsb:.0f}, ACWR {acwr:.2f}) está en rango razonable — la fatiga viene del lado subjetivo, no "
            f"del entrenamiento.",
            "Ver protocolos de recuperación mental",
            "mental.html",
        )

    # 4. Señal única de alerta (HRV o sueño o FC reposo, sin combinarse con carga alta)
    if hrv_down or poor_sleep or rhr_up:
        parts = []
        parts_plain = []
        if hrv_down:
            parts.append(f"tu HRV bajó a {round(hrv_last_night)}ms")
            parts_plain.append("tu recuperación nocturna bajó")
        if poor_sleep:
            parts.append("dormiste menos de lo habitual")
            parts_plain.append("dormiste menos de lo habitual")
        if rhr_up:
            parts.append(f"tu FC en reposo subió {rhr_trend:+.0f}bpm")
            parts_plain.append("tu frecuencia cardíaca en reposo subió")
        return _base(
            "caution", "Presta atención a tu recuperación",
            f"Hoy {', '.join(parts_plain)}. Tu entrenamiento sigue en un nivel razonable, pero prestá atención "
            f"a cómo te sentís antes de una sesión exigente.",
            f"Hoy {', '.join(parts)}. Tu carga de entrenamiento (TSB {tsb:.0f}, ACWR {acwr:.2f}) todavía está en rango "
            f"razonable, pero vale la pena monitorear cómo te sientes antes de una sesión exigente.",
        )

    # 5. Forma óptima — momento de exigir. Pero un TSB alto puede venir de dos
    # caminos muy distintos: buena forma real, o simplemente no haber
    # entrenado lo planificado (menos carga = menos fatiga = TSB sube igual,
    # sin que haya mejora real). Si hay compliance semanal baja, se corrige
    # el mensaje para no invitar a "exigir" cuando en realidad el atleta
    # viene de perderse sesiones del plan.
    if tsb > 15 and acwr_zone in ("optimal", "low") and not hrv_down:
        low_compliance = compliance_week is not None and compliance_week < 60
        if low_compliance:
            drivers.append({
                "label": "Cumplimiento semanal", "value": f"{round(compliance_week)}%",
                "tone": "caution", "delta": None,
            })
            return _base(
                "caution", "Fresco, pero por baja carga",
                "Tu forma se ve muy bien, pero es porque entrenaste menos de lo planificado esta semana — "
                "no necesariamente por una mejora real. Retomá el plan gradualmente en vez de forzar una "
                "sesión muy exigente hoy.",
                f"TSB {tsb:.0f} y ACWR {acwr:.2f} en rango saludable, pero solo cumpliste {round(compliance_week)}% "
                f"de las sesiones planificadas esta semana. El TSB alto puede reflejar menos carga acumulada en "
                f"vez de una mejora real de forma — conviene retomar el plan gradualmente.",
                "Ver tu plan de la semana",
                "training_plan.html",
            )
        return _base(
            "good", "Buen momento para exigir",
            "Estás en tu mejor momento de forma y tu recuperación se ve estable. "
            "Es un buen día para una sesión de calidad o un test.",
            # "Ver por qué" real: no repite la frase de arriba con 2 números
            # metidos adentro — explica CADA chequeo que se hizo y por qué
            # pasó, igual de detallado que los casos "reduce"/"caution" de
            # arriba. Antes este texto era casi idéntico al mensaje llano
            # (reportado por el usuario 2026-08-13: "el mensaje y ver
            # porqué son muy iguales").
            f"TSB +{tsb:.0f}, por encima del umbral de forma óptima (+15) — tu fatiga acumulada bajó lo suficiente "
            f"para que el cuerpo esté fresco. ACWR {acwr:.2f}, dentro del rango seguro (0.8–1.3), así que ese TSB alto "
            f"no viene de haber entrenado de menos esta semana." + _insight_recovery_clause(hrv_down, hrv_last_night, poor_sleep, sleep_total_h)
            + " Ningún indicador de fatiga o mala recuperación está activo — buen día para una sesión de calidad o un test.",
        )

    # 6. Neutral — todo en rango normal, sin señal fuerte en ninguna dirección
    return _base(
        "neutral", "Todo en rango normal",
        "Tu entrenamiento y tu recuperación están dentro de lo esperado hoy. Seguí tu plan con normalidad.",
        # Mismo criterio que el caso "good" de arriba: explicar los rangos
        # chequeados en vez de repetir el mensaje llano con TSB/ACWR pegados.
        f"TSB {tsb:+.0f}, dentro del rango normal (-8 a +15) — ni fatiga excesiva ni forma pico. "
        f"ACWR {acwr:.2f}, dentro del rango seguro (0.8–1.3) — la carga de esta semana está bien calibrada respecto "
        f"a tus últimas 4."
        + _insight_recovery_clause(hrv_down, hrv_last_night, poor_sleep, sleep_total_h)
        + " Ninguno de tus indicadores de carga o recuperación está fuera de rango — seguí tu plan de entrenamiento "
          "con normalidad.",
    )


# ─── Recálculo completo CTL/ATL/TSB ──────────────────────────

def recalculate_training_load(db: Session, user_id: str) -> int:
    """
    Recalcula CTL/ATL/TSB para todos los días del atleta usando el modelo EWMA de Banister.
    Devuelve el número de filas actualizadas/creadas.
    """
    from sqlalchemy import text

    acts = (
        db.query(GarminActivity)
          .filter(GarminActivity.user_id == user_id)
          .order_by(GarminActivity.date_iso)
          .all()
    )
    if not acts:
        return 0

    # Agrupar TSS por día
    tss_by_day: dict[str, float] = {}
    for a in acts:
        if a.date_iso:
            tss_by_day[a.date_iso] = tss_by_day.get(a.date_iso, 0.0) + (float(a.tss) if a.tss else 0.0)

    # Generar serie diaria continua
    dates = sorted(tss_by_day)
    if not dates:
        return 0

    start = date.fromisoformat(dates[0])
    end   = date.today()
    delta = (end - start).days + 1

    ctl, atl = 0.0, 0.0
    rows_written = 0

    for i in range(delta):
        d = start + timedelta(days=i)
        d_iso = d.isoformat()
        tss = tss_by_day.get(d_iso, 0.0)

        ctl = ctl + _ALPHA_CTL * (tss - ctl)
        atl = atl + _ALPHA_ATL * (tss - atl)
        tsb = round(ctl - atl, 2)

        # Upsert
        existing = db.query(GarminTrainingLoad).filter(
            GarminTrainingLoad.user_id == user_id,
            GarminTrainingLoad.date_iso == d_iso,
        ).first()
        if existing:
            existing.ctl = round(ctl, 2)
            existing.atl = round(atl, 2)
            existing.tsb = tsb
            existing.tss = round(tss, 2)
        else:
            db.add(GarminTrainingLoad(
                user_id  = user_id,
                date_iso = d_iso,
                ctl      = round(ctl, 2),
                atl      = round(atl, 2),
                tsb      = tsb,
                tss      = round(tss, 2),
            ))
        rows_written += 1

    db.commit()
    return rows_written
