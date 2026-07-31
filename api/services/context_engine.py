"""
LabX Context Engine — AthleteContext Builder
=============================================
Construye el snapshot diario completo del atleta para ser inyectado
en TODOS los prompts de IA. Es la base de toda la inteligencia de LabX.

El contexto incluye:
  - Identidad y perfil fisiológico
  - Carga de entrenamiento (CTL/ATL/TSB/ACWR/monotonía/strain)
  - Salud Garmin (HRV, Body Battery, sueño, estrés, SpO2)
  - LabX Readiness Score propio (0-100)
  - Carrera objetivo y días restantes
  - Últimas 7 actividades
  - Exámenes de sangre recientes
  - Insights activos (alertas no dismisseadas)

El contexto se persiste en ai_athlete_context para evitar recalcular
en cada llamada al chat. Se actualiza:
  1. Cada mañana a las 6am (scheduler)
  2. Tras cada sync de Garmin exitoso (background_sync_user)
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    AIAthleteContext, AIInsight, GarminActivity,
    GarminHealthDaily, GarminSleepSession, GarminTrainingLoad,
    User, WellnessLog, BloodLabExam,
)

logger = logging.getLogger("labx.context_engine")


# ─────────────────────────────────────────────────────────────────────────────
# LabX Readiness Score
# ─────────────────────────────────────────────────────────────────────────────

def compute_readiness_score(
    hrv_last: Optional[float],
    hrv_baseline_avg: Optional[float],
    sleep_score: Optional[int],
    body_battery: Optional[int],
    tsb: Optional[float],
    wellness_score: Optional[float],
) -> tuple[int, dict]:
    """
    LabX Readiness Score — combina 5 factores fisiológicos en un score 0-100.

    Pesos:
      HRV vs baseline    30%
      Calidad de sueño   25%
      TSB (forma)        20%
      Body Battery       15%
      Bienestar subj.    10%

    Retorna (score: int, factors: dict con desglose).
    """
    factors = {}

    # 1. HRV vs baseline personal (30%)
    if hrv_last and hrv_baseline_avg and hrv_baseline_avg > 0:
        hrv_ratio = hrv_last / hrv_baseline_avg
        hrv_score = min(100, max(0, hrv_ratio * 100))
    elif hrv_last:
        hrv_score = 65  # sin baseline: asume neutro
    else:
        hrv_score = 65  # sin dato: neutro
    factors["hrv"] = round(hrv_score)

    # 2. Sleep score Garmin (25%)
    sleep_s = min(100, max(0, sleep_score)) if sleep_score else 65
    factors["sleep"] = sleep_s

    # 3. TSB — Forma (20%)
    # TSB de -30 a +20 se mapea a 0-100
    if tsb is not None:
        tsb_score = min(100, max(0, (tsb + 30) / 50 * 100))
    else:
        tsb_score = 50
    factors["tsb"] = round(tsb_score)

    # 4. Body Battery mañana (15%)
    bb_score = min(100, max(0, body_battery)) if body_battery is not None else 65
    factors["body_battery"] = bb_score

    # 5. Bienestar subjetivo (10%)
    well_s = min(100, max(0, wellness_score)) if wellness_score else 65
    factors["wellness"] = round(well_s)

    # Weighted average
    score = (
        factors["hrv"]          * 0.30 +
        factors["sleep"]        * 0.25 +
        factors["tsb"]          * 0.20 +
        factors["body_battery"] * 0.15 +
        factors["wellness"]     * 0.10
    )
    return int(round(score)), factors


# ─────────────────────────────────────────────────────────────────────────────
# Injury Risk Score
# ─────────────────────────────────────────────────────────────────────────────

def compute_injury_risk(
    acwr: Optional[float],
    monotony: Optional[float],
    hrv_declining: bool,
    sleep_deficit: bool,
    wellness_soreness: Optional[int],
) -> float:
    """
    Modelo de riesgo de lesión basado en literatura científica (Gabbett 2016).
    Retorna un score 0.0-1.0.
      <0.30 verde (bajo)
      0.30-0.60 amarillo (monitorear)
      >0.60 rojo (acción requerida)
    """
    risk = 0.0

    # ACWR fuera de zona óptima (0.8-1.3)
    if acwr is not None:
        if acwr > 1.5:
            risk += 0.35
        elif acwr > 1.3:
            risk += 0.20
        elif acwr < 0.8 and acwr > 0:
            risk += 0.05  # subentrenamiento también es factor

    # Monotonía alta (>2.0 = entrenamiento muy uniforme sin descanso)
    if monotony is not None:
        if monotony > 2.5:
            risk += 0.25
        elif monotony > 2.0:
            risk += 0.15

    # HRV en declive 3 días consecutivos
    if hrv_declining:
        risk += 0.20

    # Déficit de sueño acumulado
    if sleep_deficit:
        risk += 0.15

    # Dolor muscular subjetivo elevado
    if wellness_soreness and wellness_soreness >= 4:
        risk += 0.15
    elif wellness_soreness and wellness_soreness == 3:
        risk += 0.05

    return min(1.0, round(risk, 2))


# ─────────────────────────────────────────────────────────────────────────────
# Builder principal
# ─────────────────────────────────────────────────────────────────────────────

def build_athlete_context(user_id: str, db: Session) -> dict:
    """
    Construye el contexto completo del atleta.
    Retorna un dict estructurado listo para serializar a JSON.
    """
    user: Optional[User] = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {}

    today     = date.today()
    today_iso = today.isoformat()

    # ── 1. Carga de entrenamiento ─────────────────────────────────────────────
    load_rows = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .limit(90)
        .all()
    )
    load_rows_sorted = list(reversed(load_rows))  # cronológico para análisis

    latest_load = load_rows[0] if load_rows else None
    ctl   = round(latest_load.ctl,  1) if latest_load else None
    atl   = round(latest_load.atl,  1) if latest_load else None
    tsb   = round(latest_load.tsb,  1) if latest_load else None
    acwr  = round(latest_load.acwr, 2) if latest_load and latest_load.acwr else None
    monotony = round(latest_load.monotony, 2) if latest_load and latest_load.monotony else None
    strain   = round(latest_load.strain,   1) if latest_load and latest_load.strain else None

    # Tendencia CTL (vs hace 7 días)
    ctl_7d_ago = load_rows[7].ctl if len(load_rows) > 7 else None
    ctl_trend  = round(ctl - ctl_7d_ago, 1) if ctl and ctl_7d_ago else None

    # Zona ACWR
    acwr_zone = "no_data"
    if acwr:
        if acwr < 0.8:      acwr_zone = "subload"
        elif acwr <= 1.3:   acwr_zone = "optimal"
        elif acwr <= 1.5:   acwr_zone = "caution"
        else:               acwr_zone = "danger"

    # ── 2. Datos de salud Garmin ──────────────────────────────────────────────
    health_rows = (
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == user_id)
        .order_by(GarminHealthDaily.date_iso.desc())
        .limit(14)
        .all()
    )
    health_today = health_rows[0] if health_rows else None
    health_yest  = health_rows[1] if len(health_rows) > 1 else None

    hrv_last_night = health_today.hrv_last_night    if health_today else None
    hrv_baseline   = health_today.hrv_weekly_avg    if health_today else None
    body_battery   = health_today.body_battery_end  if health_today else None
    stress_avg     = health_today.avg_stress        if health_today else None
    readiness_garmin = health_today.training_readiness if health_today else None

    # HRV declining: últimos 3 días consecutivos a la baja
    hrv_vals = [r.hrv_last_night for r in health_rows[:3] if r.hrv_last_night]
    hrv_declining = len(hrv_vals) == 3 and hrv_vals[0] < hrv_vals[1] < hrv_vals[2]

    # Tendencia HRV 7d
    hrv_7d = [r.hrv_last_night for r in health_rows[:7] if r.hrv_last_night]
    hrv_7d_avg = round(sum(hrv_7d) / len(hrv_7d), 1) if hrv_7d else None

    # ── 3. Sueño ──────────────────────────────────────────────────────────────
    sleep_rows = (
        db.query(GarminSleepSession)
        .filter(GarminSleepSession.user_id == user_id)
        .order_by(GarminSleepSession.date_iso.desc())
        .limit(7)
        .all()
    )
    sleep_last  = sleep_rows[0] if sleep_rows else None
    sleep_score = sleep_last.sleep_score if sleep_last else None
    sleep_total = sleep_last.total_min   if sleep_last else None
    sleep_deep  = sleep_last.deep_min    if sleep_last else None

    # Déficit de sueño: menos de 6h los últimos 3 días
    sleep_mins_recent = [r.total_min for r in sleep_rows[:3] if r.total_min]
    sleep_deficit = len(sleep_mins_recent) >= 2 and all(m < 360 for m in sleep_mins_recent)

    # ── 4. Bienestar subjetivo ────────────────────────────────────────────────
    wellness = (
        db.query(WellnessLog)
        .filter(WellnessLog.user_id == user_id, WellnessLog.date_iso == today_iso,
                WellnessLog.deleted_at.is_(None))
        .first()
    )
    wellness_score_raw = None
    wellness_soreness  = None
    if wellness:
        vals = [v for v in [wellness.fatigue, wellness.sleep_q,
                            wellness.soreness, wellness.mood] if v]
        if vals:
            wellness_score_raw = round(((sum(vals) / len(vals)) - 1) / 4 * 100)
        wellness_soreness = wellness.soreness

    # ── 5. LabX Readiness Score ───────────────────────────────────────────────
    readiness_score, readiness_factors = compute_readiness_score(
        hrv_last       = hrv_last_night,
        hrv_baseline_avg = hrv_baseline,
        sleep_score    = sleep_score,
        body_battery   = body_battery,
        tsb            = tsb,
        wellness_score = wellness_score_raw,
    )

    # ── 6. Injury Risk ────────────────────────────────────────────────────────
    injury_risk = compute_injury_risk(
        acwr              = acwr,
        monotony          = monotony,
        hrv_declining     = hrv_declining,
        sleep_deficit     = sleep_deficit,
        wellness_soreness = wellness_soreness,
    )

    # ── 7. Carrera objetivo ───────────────────────────────────────────────────
    days_to_race  = None
    race_name     = user.race_goal_name
    race_date_str = user.race_goal_date
    if race_date_str:
        try:
            race_dt    = date.fromisoformat(race_date_str[:10])
            days_to_race = (race_dt - today).days
            if days_to_race < 0:
                days_to_race = None  # carrera pasada
        except ValueError:
            pass

    # TSB proyectado al día de carrera (estimación simple exponencial)
    tsb_projected = None
    if tsb is not None and days_to_race and 0 < days_to_race <= 180:
        # Asume que el atleta mantiene carga actual; taper típico los últimos 14 días
        CTL_K = 1 - math.exp(-1 / 42)
        ATL_K = 1 - math.exp(-1 / 7)
        _ctl, _atl = ctl or 0, atl or 0
        avg_tss_daily = latest_load.tss if latest_load else 0
        for day in range(days_to_race):
            taper_factor = 0.5 if day >= days_to_race - 14 else 1.0
            daily_tss    = avg_tss_daily * taper_factor
            _ctl = _ctl * (1 - CTL_K) + daily_tss * CTL_K
            _atl = _atl * (1 - ATL_K) + daily_tss * ATL_K
        tsb_projected = round(_ctl - _atl, 1)

    # ── 8. Últimas 7 actividades ──────────────────────────────────────────────
    recent_acts = (
        db.query(GarminActivity)
        .filter(GarminActivity.user_id == user_id)
        .order_by(GarminActivity.date_iso.desc())
        .limit(7)
        .all()
    )
    activities_summary = [
        {
            "date":    a.date_iso,
            "sport":   a.sport,
            "dur_min": a.dur_min,
            "dist_km": a.dist_km,
            "tss":     round(a.tss, 0) if a.tss else 0,
            "avg_hr":  a.avg_hr,
        }
        for a in recent_acts
    ]

    # TSS semana actual
    week_start  = (today - timedelta(days=today.weekday())).isoformat()
    tss_week    = sum(a.tss or 0 for a in recent_acts if a.date_iso >= week_start)

    # ── 9. Sangre reciente ────────────────────────────────────────────────────
    blood_exams = (
        db.query(BloodLabExam)
        .filter(BloodLabExam.user_id == user_id)
        .order_by(BloodLabExam.date_iso.desc())
        .limit(2)
        .all()
    )
    labs_summary = []
    for exam in blood_exams:
        try:
            vals = json.loads(exam.values_json) if exam.values_json else {}
            labs_summary.append({"date": exam.date_iso, "markers": vals})
        except (json.JSONDecodeError, TypeError):
            pass

    # ── 10. Insights activos (no dismisseados) ────────────────────────────────
    active_insights = (
        db.query(AIInsight)
        .filter(
            AIInsight.user_id      == user_id,
            AIInsight.dismissed_at.is_(None),
            AIInsight.expires_at   > datetime.now(timezone.utc).replace(tzinfo=None),
        )
        .order_by(AIInsight.severity.desc(), AIInsight.created_at.desc())
        .limit(5)
        .all()
    )
    insights_summary = [
        {"type": i.type, "severity": i.severity, "title": i.title}
        for i in active_insights
    ]

    # ── Construcción del context dict ─────────────────────────────────────────
    context = {
        "meta": {
            "built_at":  datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "date_today": today_iso,
        },
        "identity": {
            "nombre":           user.nombre,
            "primary_sport":    "triathlon",
            "training_age_yrs": None,
        },
        "profile": {
            "weight_kg":  user.weight_kg,
            "height_cm":  user.height_cm,
            "ftp_w":      user.ftp,
            "fcmax":      user.fcmax,
            "vo2max":     user.vo2max,
            "css":        user.css,
            "run_pace":   user.run_pace,
        },
        "fitness": {
            "ctl":        ctl,
            "atl":        atl,
            "tsb":        tsb,
            "acwr":       acwr,
            "acwr_zone":  acwr_zone,
            "monotony":   monotony,
            "strain":     strain,
            "ctl_trend_7d": ctl_trend,
        },
        "health": {
            "hrv_last_night":   hrv_last_night,
            "hrv_7d_avg":       hrv_7d_avg,
            "hrv_declining":    hrv_declining,
            "hrv_baseline":     hrv_baseline,
            "body_battery":     body_battery,
            "sleep_score":      sleep_score,
            "sleep_total_h":    round(sleep_total / 60, 1) if sleep_total else None,
            "sleep_deep_h":     round(sleep_deep  / 60, 1) if sleep_deep  else None,
            "stress_avg":       stress_avg,
            "readiness_garmin": readiness_garmin,
        },
        "readiness": {
            "labx_score":   readiness_score,
            "factors":      readiness_factors,
            "injury_risk":  injury_risk,
            "injury_risk_level": (
                "critical" if injury_risk > 0.6 else
                "caution"  if injury_risk > 0.3 else
                "low"
            ),
        },
        "race": {
            "name":           race_name,
            "date":           race_date_str,
            "days_to_race":   days_to_race,
            "distance":       user.race_goal_dist,
            "tsb_projected":  tsb_projected,
        },
        "training": {
            "tss_week":      round(tss_week, 0),
            "last_activities": activities_summary,
        },
        "labs":     labs_summary,
        "alerts":   insights_summary,
    }

    return context


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia del contexto
# ─────────────────────────────────────────────────────────────────────────────

def refresh_athlete_context(user_id: str, db: Session) -> Optional[dict]:
    """
    Construye y persiste el contexto en ai_athlete_context.
    Llama tras sync Garmin exitoso y desde el scheduler diario.
    Retorna el context dict construido.
    """
    try:
        context = build_athlete_context(user_id, db)
        if not context:
            return None

        fitness   = context.get("fitness", {})
        health    = context.get("health", {})
        readiness = context.get("readiness", {})
        race      = context.get("race", {})

        # DRS real (readiness_service) — misma fuente que /readiness/daily y el resto de la app.
        # No usar readiness["labx_score"] aquí: es el motor legado (solo alimenta el prompt del AI Coach)
        # y da números distintos al DRS oficial (ver bug de dashboard.html, commit 3beb70b).
        try:
            from .readiness_service import compute_daily_readiness_for_user
            current_readiness = compute_daily_readiness_for_user(user_id, db).drs
        except Exception:
            current_readiness = readiness.get("labx_score")

        row = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == user_id).first()
        if row:
            row.context_json        = json.dumps(context, ensure_ascii=False, default=str)
            row.current_ctl         = fitness.get("ctl")
            row.current_atl         = fitness.get("atl")
            row.current_tsb         = fitness.get("tsb")
            row.current_acwr        = fitness.get("acwr")
            row.current_hrv         = health.get("hrv_last_night")
            row.current_readiness   = current_readiness
            row.injury_risk_score   = readiness.get("injury_risk")
            row.days_to_race        = race.get("days_to_race")
            row.context_built_at    = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            db.add(AIAthleteContext(
                user_id           = user_id,
                context_json      = json.dumps(context, ensure_ascii=False, default=str),
                current_ctl       = fitness.get("ctl"),
                current_atl       = fitness.get("atl"),
                current_tsb       = fitness.get("tsb"),
                current_acwr      = fitness.get("acwr"),
                current_hrv       = health.get("hrv_last_night"),
                current_readiness = current_readiness,
                injury_risk_score = readiness.get("injury_risk"),
                days_to_race      = race.get("days_to_race"),
                context_built_at  = datetime.now(timezone.utc).replace(tzinfo=None),
            ))

        # Persiste también el LabX Readiness Score en garmin_health_daily de hoy
        _save_readiness_to_health(user_id, db, context)

        db.commit()
        logger.info("Context refreshed user_id=%s readiness=%s risk=%.2f",
                    user_id, readiness.get("labx_score"), readiness.get("injury_risk", 0))
        return context

    except Exception as exc:
        db.rollback()
        logger.error("Context refresh error user_id=%s: %s", user_id, exc)
        return None


def _save_readiness_to_health(user_id: str, db: Session, context: dict) -> None:
    """Actualiza labx_readiness_score en garmin_health_daily de hoy."""
    from ..models import GarminHealthDaily
    import json as _json
    today_iso = date.today().isoformat()
    health_row = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == user_id,
        GarminHealthDaily.date_iso == today_iso,
    ).first()
    readiness = context.get("readiness", {})
    score     = readiness.get("labx_score")
    factors   = readiness.get("factors", {})
    if health_row and score is not None:
        health_row.labx_readiness_score   = score
        health_row.labx_readiness_factors = _json.dumps(factors)
    elif score is not None:
        db.add(GarminHealthDaily(
            user_id               = user_id,
            date_iso              = today_iso,
            labx_readiness_score  = score,
            labx_readiness_factors = _json.dumps(factors),
            synced_at             = datetime.now(timezone.utc).replace(tzinfo=None),
        ))


def get_context_for_prompt(user_id: str, db: Session) -> str:
    """
    Retorna el contexto del atleta formateado como string para el system prompt.
    Usa el contexto cacheado si tiene menos de 2h, lo reconstruye si es más viejo.
    """
    row = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == user_id).first()

    # Si el contexto tiene menos de 2h es válido
    if row and row.context_built_at:
        age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - row.context_built_at).total_seconds() / 3600
        if age_h < 2 and row.context_json:
            try:
                ctx = json.loads(row.context_json)
                return _format_context_for_prompt(ctx)
            except (json.JSONDecodeError, TypeError):
                pass

    # Reconstruir
    ctx = refresh_athlete_context(user_id, db)
    return _format_context_for_prompt(ctx) if ctx else ""


def _format_context_for_prompt(ctx: dict) -> str:
    """Convierte el context dict en un bloque de texto legible para Claude."""
    if not ctx:
        return ""

    identity = ctx.get("identity", {})
    profile  = ctx.get("profile",  {})
    fitness  = ctx.get("fitness",  {})
    health   = ctx.get("health",   {})
    readiness= ctx.get("readiness",{})
    race     = ctx.get("race",     {})
    training = ctx.get("training", {})
    labs     = ctx.get("labs",     [])
    alerts   = ctx.get("alerts",   [])

    today = ctx.get("meta", {}).get("date_today", "")
    lines = [f"═══ CONTEXTO DEL ATLETA — {today} ═══"]

    # Identidad y perfil
    nombre = identity.get("nombre", "Atleta")
    lines.append(f"\nATLETA: {nombre}")
    p = [
        f"Peso {profile['weight_kg']}kg" if profile.get("weight_kg") else "",
        f"FTP {profile['ftp_w']}W"       if profile.get("ftp_w")    else "",
        f"FCmax {profile['fcmax']}bpm"   if profile.get("fcmax")    else "",
        f"VO2max {profile['vo2max']}"    if profile.get("vo2max")   else "",
        f"CSS {profile['css']}"          if profile.get("css")      else "",
        f"Ritmo umbral {profile['run_pace']}/km" if profile.get("run_pace") else "",
    ]
    p_str = " · ".join(x for x in p if x)
    if p_str:
        lines.append(f"  Perfil: {p_str}")

    # Fitness y carga
    lines.append("\nCARGA DE ENTRENAMIENTO:")
    ctl  = fitness.get("ctl")
    atl  = fitness.get("atl")
    tsb  = fitness.get("tsb")
    acwr = fitness.get("acwr")
    if ctl  is not None: lines.append(f"  CTL (Fitness):  {ctl}")
    if atl  is not None: lines.append(f"  ATL (Fatiga):   {atl}")
    if tsb  is not None:
        tsb_interp = (
            "Forma óptima (fresco)" if tsb and tsb > 5 else
            "Ligeramente fatigado"  if tsb and tsb > -10 else
            "Fatigado"              if tsb and tsb > -20 else
            "Muy fatigado"
        )
        lines.append(f"  TSB (Forma):    {tsb} → {tsb_interp}")
    if acwr is not None:
        lines.append(f"  ACWR:           {acwr} ({fitness.get('acwr_zone','?')})")
    trend = fitness.get("ctl_trend_7d")
    if trend is not None:
        lines.append(f"  Tendencia CTL 7d: {'+' if trend >= 0 else ''}{trend}")

    # Salud y recuperación
    lines.append("\nSALUD Y RECUPERACIÓN:")
    hrv  = health.get("hrv_last_night")
    hrv7 = health.get("hrv_7d_avg")
    bb   = health.get("body_battery")
    sl   = health.get("sleep_score")
    rg   = health.get("readiness_garmin")
    if hrv  is not None: lines.append(f"  HRV anoche:        {hrv} ms{' (↓ DECLINANDO 3d)' if health.get('hrv_declining') else ''}")
    if hrv7 is not None: lines.append(f"  HRV promedio 7d:   {hrv7} ms")
    if bb   is not None: lines.append(f"  Body Battery mañana: {bb}%")
    if sl   is not None: lines.append(f"  Sleep Score:       {sl}/100 ({health.get('sleep_total_h','?')}h total, {health.get('sleep_deep_h','?')}h profundo)")
    if rg   is not None: lines.append(f"  Training Readiness Garmin: {rg}/100")

    # LabX Readiness Score
    rs = readiness.get("labx_score")
    if rs is not None:
        risk   = readiness.get("injury_risk_level", "low")
        lines.append(f"\nLABX READINESS: {rs}/100 · Riesgo lesión: {risk.upper()}")
        fac = readiness.get("factors", {})
        if fac:
            fac_str = " · ".join(f"{k}={v}" for k, v in fac.items())
            lines.append(f"  Factores: {fac_str}")

    # Carrera objetivo
    rn = race.get("name")
    rd = race.get("days_to_race")
    if rn:
        tsb_proj = race.get("tsb_projected")
        lines.append(f"\nCARRERA OBJETIVO: {rn}")
        if rd is not None:
            lines.append(f"  Días restantes: {rd}")
        if tsb_proj is not None:
            lines.append(f"  TSB proyectado el día de carrera: {tsb_proj}")

    # Entrenamiento reciente
    tss_w = training.get("tss_week", 0)
    acts  = training.get("last_activities", [])
    lines.append(f"\nENTRENAMIENTO RECIENTE (TSS esta semana: {tss_w}):")
    for a in acts[:5]:
        sport = a.get("sport", "?")
        dur   = a.get("dur_min", 0)
        dist  = a.get("dist_km", 0)
        tss_a = a.get("tss", 0)
        hr    = a.get("avg_hr")
        hr_s  = f" FC={hr}" if hr else ""
        lines.append(f"  {a.get('date','')} {sport}: {dur}min {dist}km TSS={tss_a}{hr_s}")

    # Labs — formato legible para el Coach IA
    if labs:
        lines.append("\nÚLTIMOS EXÁMENES DE SANGRE:")
        _KEY_NAMES = {
            "hb": "Hemoglobina", "ferritin": "Ferritina", "hct": "Hematocrito",
            "vitamin_d": "Vitamina D", "b12": "Vitamina B12",
            "cortisol": "Cortisol", "testosterone": "Testosterona",
            "crp": "PCR (inflamación)", "ck": "Creatinkinasa",
            "tsh": "TSH (tiroides)", "hba1c": "HbA1c",
            "magnesium": "Magnesio", "zinc": "Zinc",
            "ldl": "LDL", "hdl": "HDL", "glucose": "Glucosa",
        }
        _KEY_UNITS = {
            "hb": "g/dL", "ferritin": "ng/mL", "hct": "%",
            "vitamin_d": "ng/mL", "b12": "pg/mL",
            "cortisol": "μg/dL", "testosterone": "ng/dL",
            "crp": "mg/L", "ck": "U/L", "tsh": "mIU/L",
            "hba1c": "%", "magnesium": "mg/dL", "zinc": "μg/dL",
            "ldl": "mg/dL", "hdl": "mg/dL", "glucose": "mg/dL",
        }
        for lab in labs[:2]:
            markers = lab.get("markers", {})
            lines.append(f"  Fecha: {lab.get('date','')}")
            key_parts = []
            for k, v in markers.items():
                if v is None:
                    continue
                name = _KEY_NAMES.get(k, k)
                unit = _KEY_UNITS.get(k, "")
                key_parts.append(f"{name}: {v}{' '+unit if unit else ''}")
            if key_parts:
                lines.append("  " + " · ".join(key_parts[:10]))

    # Alertas activas
    if alerts:
        lines.append("\nALERTAS ACTIVAS:")
        for al in alerts:
            lines.append(f"  [{al.get('severity','info').upper()}] {al.get('title','')}")

    lines.append("\n═══════════════════════════════════")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Batch refresh — para el scheduler 6am
# ─────────────────────────────────────────────────────────────────────────────

def refresh_all_active_contexts(db_factory) -> None:
    """
    Refresca el contexto de todos los atletas activos con Garmin configurado.
    Diseñado para ejecutarse desde APScheduler (6am diario).
    db_factory: callable que retorna una sesión DB nueva.
    """
    from ..database import SessionLocal
    from ..models import User

    db = SessionLocal()
    try:
        athletes = (
            db.query(User)
            .filter(
                User.rol       == "atleta",
                User.activo    == True,
                User.garmin_email.isnot(None),
            )
            .all()
        )
        logger.info("Context refresh batch: %d atletas", len(athletes))
        for athlete in athletes:
            try:
                refresh_athlete_context(athlete.id, db)
            except Exception as exc:
                logger.error("Context refresh error athlete=%s: %s", athlete.id, exc)
                db.rollback()
    finally:
        db.close()
