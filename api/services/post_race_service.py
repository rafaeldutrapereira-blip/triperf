"""
LabX Post-Race Intelligence Service
=====================================
Analiza la performance post-carrera comparando:
  - Predicción pre-carrera (race_events.pred_*)
  - Resultado real (race_events.actual_*)
  - Condiciones fisiológicas en la semana previa (TSB, CTL, HRV, labs)
  - Factores externos declarados (temperatura, viento, altitud, superficie)

Genera:
  1. Gap analysis por disciplina (swim/bike/run)
  2. Limitadores identificados (clasificados por evidencia: alta/media/baja)
  3. Briefing IA narrativo (Claude Haiku para costo, Sonnet para carrera A)
  4. Recomendaciones pre-race para próxima carrera
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    BloodLabExam,
    GarminHealthDaily,
    GarminTrainingLoad,
    RaceEvent,
    User,
)

logger = logging.getLogger("labx.post_race")

# ── Umbrales de análisis ──────────────────────────────────────────────────────

# Gap en segundos que se considera "significativo" por disciplina (>2% del tiempo predicho)
GAP_THRESHOLD_PCT = 0.02

# Factores fisiológicos que afectan rendimiento
PHYSIOLOGICAL_FACTORS = {
    "tsb_negative": {
        "condition": lambda tsb: tsb is not None and tsb < -10,
        "severity":  lambda tsb: "high" if tsb < -25 else "moderate",
        "label":     "Fatiga acumulada (TSB negativo)",
        "impact_pct":lambda tsb: min(8.0, abs(tsb) * 0.15),
        "rec":       "Aumentar taper a 14-18 días para próxima carrera A. TSB objetivo: +5 a +15.",
    },
    "tsb_too_high": {
        "condition": lambda tsb: tsb is not None and tsb > 25,
        "severity":  lambda tsb: "moderate",
        "label":     "Desentrenamiento excesivo (TSB muy alto)",
        "impact_pct":lambda tsb: min(3.0, (tsb - 20) * 0.1),
        "rec":       "Reducir taper a 10-12 días. Mantener 2-3 sesiones de calidad en la última semana.",
    },
    "low_ferritin": {
        "condition": lambda labs: labs.get("ferritin", 999) < 50,
        "severity":  lambda labs: "high" if labs.get("ferritin",999) < 30 else "moderate",
        "label":     "Ferritina baja pre-carrera",
        "impact_pct":lambda labs: 5.0 if labs.get("ferritin",999) < 30 else 2.0,
        "rec":       "Protocolo hierro: suplementar 3 meses antes. Objetivo ferritina >70 ng/mL.",
    },
    "high_cortisol": {
        "condition": lambda labs: labs.get("cortisol", 0) > 22,
        "severity":  lambda labs: "high" if labs.get("cortisol",0) > 28 else "moderate",
        "label":     "Cortisol elevado (estrés crónico)",
        "impact_pct":lambda labs: 3.0 if labs.get("cortisol",0) > 28 else 1.5,
        "rec":       "Reducir volumen total 15% las 3 semanas pre-race. Priorizar sueño 8-9h.",
    },
    "hrv_low": {
        "condition": lambda hrv_drop: hrv_drop is not None and hrv_drop > 8,
        "severity":  lambda hrv_drop: "high" if hrv_drop > 15 else "moderate",
        "label":     "HRV bajo en semana pre-carrera",
        "impact_pct":lambda hrv_drop: min(4.0, hrv_drop * 0.2),
        "rec":       "Monitorear HRV diario. Si drop >8% en los 3 días pre-race, reducir activación.",
    },
    "low_vitamin_d": {
        "condition": lambda labs: labs.get("vitamin_d", 999) < 30,
        "severity":  lambda labs: "moderate",
        "label":     "Vitamina D insuficiente",
        "impact_pct":lambda labs: 1.5,
        "rec":       "Suplementar vitamina D3 2000-4000 UI/día. Objetivo >40 ng/mL.",
    },
    "high_ck": {
        "condition": lambda labs: labs.get("ck", 0) > 300,
        "severity":  lambda labs: "high" if labs.get("ck",0) > 500 else "moderate",
        "label":     "CK elevada (daño muscular residual)",
        "impact_pct":lambda labs: min(5.0, labs.get("ck",0) / 200),
        "rec":       "Evitar sesiones de fuerza en los 5 días pre-race. Incluir baños de contraste.",
    },
}


def _fmt_delta(delta_sec: float, discipline: str) -> str:
    """Formatea el delta de tiempo en formato legible."""
    abs_d = abs(int(delta_sec))
    sign  = "+" if delta_sec > 0 else "-"
    if abs_d < 60:
        return f"{sign}{abs_d}s"
    return f"{sign}{abs_d//60}m{abs_d%60:02d}s"


def _pct_delta(actual: Optional[float], predicted: Optional[float]) -> Optional[float]:
    if actual and predicted and predicted > 0:
        return round((actual - predicted) / predicted * 100, 1)
    return None


def _get_labs_pre_race(user_id: str, race_date: str, db: Session) -> dict:
    """
    Obtiene los valores de blood labs del examen más reciente
    en los 90 días anteriores a la carrera.
    """
    cutoff = (date.fromisoformat(race_date) - timedelta(days=90)).isoformat()
    exam   = (
        db.query(BloodLabExam)
        .filter(
            BloodLabExam.user_id   == user_id,
            BloodLabExam.date_iso >= cutoff,
            BloodLabExam.date_iso <= race_date,
        )
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )
    if not exam:
        return {}
    import json as _json
    vals = {}
    try:
        vals = _json.loads(exam.values_json or "{}")
    except Exception:
        pass
    return {
        "ferritin":   vals.get("ferritin"),
        "hemoglobin": vals.get("hemoglobin") or vals.get("hb"),
        "cortisol":   vals.get("cortisol"),
        "vitamin_d":  vals.get("vitamin_d"),
        "ck":         vals.get("ck"),
        "hba1c":      vals.get("hba1c"),
        "exam_date":  exam.date_iso,
    }


def _get_tsb_pre_race(user_id: str, race_date: str, db: Session) -> Optional[float]:
    """TSB en la fecha de la carrera (o la más reciente antes)."""
    load = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso <= race_date,
        )
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    return round(load.tsb, 1) if load and load.tsb is not None else None


def _get_hrv_drop_pre_race(user_id: str, race_date: str, db: Session) -> Optional[float]:
    """
    HRV drop % promedio en los 3 días pre-carrera vs 7-day avg de la semana anterior.
    """
    race_dt = date.fromisoformat(race_date)
    # 3 días pre-race
    pre3_start = (race_dt - timedelta(days=3)).isoformat()
    # 7-14 días antes (baseline)
    base_start = (race_dt - timedelta(days=14)).isoformat()
    base_end   = (race_dt - timedelta(days=4)).isoformat()

    pre3 = (
        db.query(GarminHealthDaily)
        .filter(
            GarminHealthDaily.user_id  == user_id,
            GarminHealthDaily.date_iso >= pre3_start,
            GarminHealthDaily.date_iso <  race_date,
            GarminHealthDaily.hrv_last_night.isnot(None),
        )
        .all()
    )
    base = (
        db.query(GarminHealthDaily)
        .filter(
            GarminHealthDaily.user_id  == user_id,
            GarminHealthDaily.date_iso >= base_start,
            GarminHealthDaily.date_iso <= base_end,
            GarminHealthDaily.hrv_last_night.isnot(None),
        )
        .all()
    )
    if not pre3 or not base:
        return None

    avg_pre3 = sum(r.hrv_last_night for r in pre3) / len(pre3)
    avg_base = sum(r.hrv_last_night for r in base) / len(base)
    if avg_base <= 0:
        return None
    return round((avg_base - avg_pre3) / avg_base * 100, 1)


def analyze_race(race: RaceEvent, db: Session) -> dict:
    """
    Motor principal de análisis post-carrera.

    Retorna un dict estructurado con:
      - gap_analysis: delta por disciplina
      - limiting_factors: lista priorizada de factores causales
      - physiological_context: TSB, HRV, labs en el momento de la carrera
      - performance_index: score 0-100 de la ejecución vs predicción
      - recommendations: lista de recomendaciones para próxima carrera
    """
    pred_total  = race.pred_total_sec
    actual_total= race.actual_total_sec
    if not pred_total or not actual_total:
        return {"error": "Faltan datos de predicción o resultado real"}

    user_id    = race.user_id
    race_date  = race.date_iso

    # ── 1. Gap por disciplina ──────────────────────────────────────────────
    gap_swim   = (race.actual_swim_sec  or 0) - (race.pred_swim_sec  or 0)
    gap_bike   = (race.actual_bike_sec  or 0) - (race.pred_bike_sec  or 0)
    gap_run    = (race.actual_run_sec   or 0) - (race.pred_run_sec   or 0)
    gap_t1     = (race.actual_t1_sec    or 0) - (race.pred_t1_sec    or 0)
    gap_t2     = (race.actual_t2_sec    or 0) - (race.pred_t2_sec    or 0)
    gap_total  = actual_total - pred_total
    gap_pct    = _pct_delta(actual_total, pred_total) or 0

    gap_analysis = {
        "total":  {"pred": pred_total,          "actual": actual_total,        "delta_sec": gap_total,  "delta_pct": round(gap_pct, 1)},
        "swim":   {"pred": race.pred_swim_sec,  "actual": race.actual_swim_sec,"delta_sec": gap_swim,   "delta_fmt": _fmt_delta(gap_swim,  "swim")},
        "bike":   {"pred": race.pred_bike_sec,  "actual": race.actual_bike_sec,"delta_sec": gap_bike,   "delta_fmt": _fmt_delta(gap_bike,  "bike")},
        "run":    {"pred": race.pred_run_sec,   "actual": race.actual_run_sec, "delta_sec": gap_run,    "delta_fmt": _fmt_delta(gap_run,   "run")},
        "t1":     {"pred": race.pred_t1_sec,    "actual": race.actual_t1_sec,  "delta_sec": gap_t1,     "delta_fmt": _fmt_delta(gap_t1,    "t1")},
        "t2":     {"pred": race.pred_t2_sec,    "actual": race.actual_t2_sec,  "delta_sec": gap_t2,     "delta_fmt": _fmt_delta(gap_t2,    "t2")},
    }

    # Disciplina más limitante (mayor delta positivo = más lento de lo esperado)
    disc_gaps = [("swim", gap_swim), ("bike", gap_bike), ("run", gap_run)]
    disc_gaps.sort(key=lambda x: x[1], reverse=True)
    worst_discipline = disc_gaps[0][0] if disc_gaps[0][1] > 30 else None

    # ── 2. Contexto fisiológico ────────────────────────────────────────────
    labs       = _get_labs_pre_race(user_id, race_date, db)
    tsb        = _get_tsb_pre_race(user_id, race_date, db)
    hrv_drop   = _get_hrv_drop_pre_race(user_id, race_date, db)
    ctl_load   = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user_id, GarminTrainingLoad.date_iso <= race_date)
        .order_by(GarminTrainingLoad.date_iso.desc()).first()
    )
    ctl_val = round(ctl_load.ctl, 1) if ctl_load and ctl_load.ctl else None
    atl_val = round(ctl_load.atl, 1) if ctl_load and ctl_load.atl else None

    phys_context = {
        "tsb":        tsb,
        "ctl":        ctl_val,
        "atl":        atl_val,
        "hrv_drop":   hrv_drop,
        "labs":       labs,
    }

    # ── 3. Identificar factores limitantes ────────────────────────────────
    limiting_factors = []

    # TSB
    for f_id, f_cfg in PHYSIOLOGICAL_FACTORS.items():
        try:
            if "tsb" in f_id:
                if tsb is not None and f_cfg["condition"](tsb):
                    limiting_factors.append({
                        "id":        f_id,
                        "label":     f_cfg["label"],
                        "severity":  f_cfg["severity"](tsb),
                        "impact_pct":round(f_cfg["impact_pct"](tsb), 1),
                        "evidence":  f"TSB: {tsb:+.0f}",
                        "rec":       f_cfg["rec"],
                    })
            elif "hrv" in f_id:
                if hrv_drop is not None and f_cfg["condition"](hrv_drop):
                    limiting_factors.append({
                        "id":        f_id,
                        "label":     f_cfg["label"],
                        "severity":  f_cfg["severity"](hrv_drop),
                        "impact_pct":round(f_cfg["impact_pct"](hrv_drop), 1),
                        "evidence":  f"HRV drop pre-race: {hrv_drop:.1f}%",
                        "rec":       f_cfg["rec"],
                    })
            else:
                if labs and f_cfg["condition"](labs):
                    limiting_factors.append({
                        "id":        f_id,
                        "label":     f_cfg["label"],
                        "severity":  f_cfg["severity"](labs),
                        "impact_pct":round(f_cfg["impact_pct"](labs), 1),
                        "evidence":  _labs_evidence(f_id, labs),
                        "rec":       f_cfg["rec"],
                    })
        except Exception:
            continue

    # Disciplina más lenta con evidencia notable
    if worst_discipline and disc_gaps[0][1] > 60:
        label_map = {"swim": "Natación fue la disciplina más lenta vs predicción",
                     "bike": "Ciclismo fue la disciplina más limitante",
                     "run":  "Running fue la disciplina más lenta — típico de fatiga acumulada"}
        limiting_factors.append({
            "id":        f"discipline_{worst_discipline}",
            "label":     label_map.get(worst_discipline, f"Disciplina limitante: {worst_discipline}"),
            "severity":  "high" if disc_gaps[0][1] > 180 else "moderate",
            "impact_pct":round(disc_gaps[0][1] / (pred_total or 1) * 100, 1),
            "evidence":  f"Delta real vs predicho: {_fmt_delta(disc_gaps[0][1], worst_discipline)}",
            "rec":       _discipline_rec(worst_discipline),
        })

    # Ordenar por severidad + impacto
    sev_order = {"high": 0, "moderate": 1, "low": 2}
    limiting_factors.sort(key=lambda x: (sev_order.get(x["severity"], 2), -x.get("impact_pct", 0)))

    # ── 4. Performance Index ──────────────────────────────────────────────
    # 100 = exactamente en predicción; >100 = superó; <100 = por debajo
    perf_index = round(pred_total / actual_total * 100, 1) if actual_total > 0 else None

    # ── 5. Recomendaciones para próxima carrera ────────────────────────────
    recs = [f["rec"] for f in limiting_factors[:3] if f.get("rec")]
    if not recs:
        recs = ["La carrera fue consistente con la predicción. Continúa con el plan actual."]
    if perf_index and perf_index > 103:
        recs.insert(0, "Superaste la predicción. Considera ajustar el FTP/CSS al alza para próxima carrera.")

    return {
        "race_id":           race.id,
        "race_name":         race.name,
        "race_date":         race.date_iso,
        "distance":          race.distance,
        "gap_analysis":      gap_analysis,
        "limiting_factors":  limiting_factors,
        "physiological_context": phys_context,
        "performance_index": perf_index,
        "recommendations":   recs,
        "worst_discipline":  worst_discipline,
    }


def _labs_evidence(f_id: str, labs: dict) -> str:
    ev_map = {
        "low_ferritin":  f"Ferritina: {labs.get('ferritin')} ng/mL (óptimo >70)",
        "high_cortisol": f"Cortisol: {labs.get('cortisol')} μg/dL (óptimo <18)",
        "low_vitamin_d": f"Vitamina D: {labs.get('vitamin_d')} ng/mL (óptimo >40)",
        "high_ck":       f"CK: {labs.get('ck')} U/L (óptimo <200 en descanso)",
    }
    return ev_map.get(f_id, f"Labs anormales: {f_id}")


def _discipline_rec(disc: str) -> str:
    recs = {
        "swim": "Aumentar volumen de natación 20% en próximo bloque de build. Foco en técnica a ritmos sub-umbral.",
        "bike": "Revisar pacing strategy. FTP real puede diferir del estimado — test de 20min recomendado.",
        "run":  "La desaceleración en el run es el patrón más común en triatlón. Reducir IF de ciclismo 3-5% mejora el run significativamente.",
    }
    return recs.get(disc, "Revisar estrategia de carrera en esta disciplina.")


async def generate_post_race_ai_analysis(
    race: RaceEvent,
    analysis: dict,
    user: User,
    is_goal_race: bool = False,
) -> str:
    """
    Genera el análisis narrativo con Claude.
    Usa Haiku para carreras de entrenamiento, Sonnet para carreras A.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        gap_total  = analysis["gap_analysis"]["total"]
        factors    = analysis["limiting_factors"]
        phys       = analysis["physiological_context"]
        perf_idx   = analysis.get("performance_index", 100)
        worst_disc = analysis.get("worst_discipline")

        factors_text = "\n".join([f"- {f['label']} ({f['severity']}): {f['evidence']}" for f in factors[:4]])
        phys_text    = f"TSB: {phys.get('tsb','N/A'):+}, CTL: {phys.get('ctl','N/A')}, HRV drop pre-race: {phys.get('hrv_drop','N/A')}%"

        prompt = f"""Eres un coach de triatlón experto analizando la carrera post-race de {user.nombre or 'el atleta'}.

CARRERA: {race.name} — {race.distance or ''} — {race.date_iso}
RESULTADO: {_fmt_total(gap_total['actual'])} (predicción: {_fmt_total(gap_total['pred'])})
DELTA: {_fmt_delta(gap_total['delta_sec'], 'total')} ({gap_total['delta_pct']:+.1f}%)
PERFORMANCE INDEX: {perf_idx:.1f}/100

DISCIPLINA MÁS LIMITANTE: {worst_disc or 'ninguna identificada'}
GAPS: NAT {analysis['gap_analysis']['swim']['delta_fmt']} · BIKE {analysis['gap_analysis']['bike']['delta_fmt']} · RUN {analysis['gap_analysis']['run']['delta_fmt']}

CONTEXTO FISIOLÓGICO: {phys_text}

FACTORES LIMITANTES IDENTIFICADOS:
{factors_text or 'Ninguno significativo identificado'}

Genera un análisis post-carrera conciso en español (3-4 párrafos):
1. Evaluación general de la performance (una oración directa)
2. Análisis de los factores fisiológicos que más influyeron (específico, con números)
3. La disciplina más limitante y por qué
4. Las 2-3 acciones más importantes para la próxima carrera

Tono: Coach directo y constructivo. Sin frases vacías. Usa datos concretos."""

        model = "claude-sonnet-4-6" if is_goal_race else "claude-haiku-4-5-20251001"
        resp  = client.messages.create(
            model      = model,
            max_tokens = 600 if is_goal_race else 400,
            messages   = [{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip() if resp.content else ""

    except Exception as e:
        logger.error("Post-race AI analysis error: %s", e)
        return ""


def _fmt_total(secs: Optional[int]) -> str:
    if secs is None:
        return "—"
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h}:{m:02d}:{s:02d}"
