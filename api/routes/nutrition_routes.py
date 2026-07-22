"""
LabX Nutrición Inteligente v2.0 — Sprint 14
============================================
Endpoints nuevos que complementan /food/* (food_diary_routes.py):

  GET    /nutrition/balance/{date_iso}         — Balance calórico vs Garmin burn
  GET    /nutrition/periodization              — Plan CHO alto/bajo según TSS
  GET    /nutrition/hydration/{date_iso}       — Ingesta hídrica del día
  POST   /nutrition/hydration                  — Registrar agua
  DELETE /nutrition/hydration/{log_id}         — Borrar ingesta
  GET    /nutrition/hydration/goal/{date_iso}  — Objetivo de hidratación del día

  POST   /nutrition/weight                     — Registrar peso
  GET    /nutrition/weight/history             — Historial de peso (90d)
  DELETE /nutrition/weight/{log_id}            — Borrar entrada de peso

  GET    /nutrition/supplements/{date_iso}     — Suplementos del día
  POST   /nutrition/supplements                — Registrar suplemento
  DELETE /nutrition/supplements/{log_id}       — Borrar suplemento

  GET    /nutrition/custom-foods               — Mis alimentos personalizados
  POST   /nutrition/custom-foods               — Crear alimento personalizado
  PUT    /nutrition/custom-foods/{food_id}     — Editar alimento personalizado
  DELETE /nutrition/custom-foods/{food_id}     — Borrar alimento personalizado

  GET    /nutrition/favorites                  — Mis favoritos (ordenados por uso)
  POST   /nutrition/favorites                  — Agregar favorito
  DELETE /nutrition/favorites/{fav_id}         — Quitar favorito

  GET    /nutrition/race-protocol              — Protocolo de carrera personalizado
  GET    /nutrition/insights/{date_iso}        — Insights IA del día
  GET    /nutrition/dashboard                  — Resumen completo (1 llamada para UI)
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import (
    User, FoodDiaryEntry, GarminActivity, GarminTrainingLoad,
    GarminHealthDaily, RaceEvent, NutritionPlan,
    HydrationLog, WeightLog, SupplementLog,
    CustomFood, FavoriteFood, NutritionInsight,
)
from ..plan_features import require_feature
from models.bike_physics import predict_bike, BikePhysicsParams
from models.run_physics import predict_run, RunPhysicsParams

logger = logging.getLogger("labx.nutrition")
router = APIRouter(prefix="/nutrition", tags=["nutrition_v2"])

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

LIQUID_TYPES   = {"water", "sport_drink", "coffee", "tea", "juice", "milk", "other"}
SUPPLEMENT_CAT = {
    "caffeine":    {"name": "Cafeína",     "common_dose_mg": 200,  "timing": "30-60min antes"},
    "creatine":    {"name": "Creatina",    "common_dose_mg": 5000, "timing": "post-entrenamiento"},
    "beta_alanine":{"name": "Beta-alanina","common_dose_mg": 3200, "timing": "pre-entrenamiento"},
    "iron":        {"name": "Hierro",      "common_dose_mg": 18,   "timing": "con el desayuno"},
    "vit_d":       {"name": "Vitamina D",  "common_dose_mg": 2000, "timing": "con una comida"},
    "omega3":      {"name": "Omega-3",     "common_dose_mg": 2000, "timing": "con una comida"},
    "magnesium":   {"name": "Magnesio",    "common_dose_mg": 400,  "timing": "antes de dormir"},
    "bcaa":        {"name": "BCAA",        "common_dose_mg": 5000, "timing": "post-entrenamiento"},
    "electrolytes":{"name": "Electrolitos","common_dose_mg": 1000, "timing": "durante ejercicio"},
    "collagen":    {"name": "Colágeno",    "common_dose_mg": 15000,"timing": "post-entrenamiento"},
    "custom":      {"name": "Personalizado","common_dose_mg": None, "timing": ""},
}

MEAL_SLOTS = [
    "breakfast", "morning_snack", "lunch",
    "afternoon_snack", "dinner",
    "pre_workout", "intra_workout", "post_workout", "other",
]

SLOT_LABELS = {
    "breakfast":       "Desayuno",
    "morning_snack":   "Snack AM",
    "lunch":           "Almuerzo",
    "afternoon_snack": "Snack PM",
    "dinner":          "Cena",
    "pre_workout":     "Pre-entrenamiento",
    "intra_workout":   "Durante entrenamiento",
    "post_workout":    "Post-entrenamiento",
    "other":           "Otro",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _today() -> str:
    return date.today().isoformat()


def _get_training_load(user_id: str, date_iso: str, db: Session) -> Optional[GarminTrainingLoad]:
    return db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == user_id,
        GarminTrainingLoad.date_iso == date_iso,
    ).first()


def _get_health_daily(user_id: str, date_iso: str, db: Session) -> Optional[GarminHealthDaily]:
    return db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == user_id,
        GarminHealthDaily.date_iso == date_iso,
    ).first()


def _diary_totals(entries: list[FoodDiaryEntry]) -> dict:
    return {
        "kcal":      round(sum(e.kcal      or 0 for e in entries), 1),
        "carbs_g":   round(sum(e.carbs_g   or 0 for e in entries), 1),
        "protein_g": round(sum(e.protein_g or 0 for e in entries), 1),
        "fat_g":     round(sum(e.fat_g     or 0 for e in entries), 1),
        "fiber_g":   round(sum(e.fiber_g   or 0 for e in entries), 1),
        "sodium_mg": round(sum(e.sodium_mg or 0 for e in entries), 1),
    }


def _carb_periodization_tier(tl: Optional[GarminTrainingLoad]) -> str:
    """
    Clasifica el día según TSS:
      high_carb   : TSS >= 100  (sesión larga/intensa)
      moderate    : TSS 50-99
      low_carb    : TSS < 50 o descanso
      carb_loading: 48h antes de carrera (manejado en /race-protocol)
    """
    if not tl or (tl.tss_day or 0) == 0:
        return "low_carb"
    tss = tl.tss_day or 0
    if tss >= 100:
        return "high_carb"
    if tss >= 50:
        return "moderate"
    return "low_carb"


def _compute_kcal_targets(me: User, tier: str) -> dict:
    """
    Calcula targets de macros según el perfil del atleta y el tier del día.
    Fórmula base: Mifflin-St Jeor × 1.55 (activo moderado) + ajuste por tier.
    """
    weight  = getattr(me, "peso_kg",   75.0) or 75.0
    height  = getattr(me, "altura_cm", 175.0) or 175.0
    age     = getattr(me, "edad",       35)   or 35
    sex     = getattr(me, "sexo",       "m")  or "m"

    # BMR Mifflin-St Jeor
    if sex == "f":
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age + 5

    tdee = bmr * 1.55  # factor actividad moderada

    # Ajuste por tier
    multipliers = {
        "high_carb":   1.20,
        "moderate":    1.05,
        "low_carb":    0.90,
        "carb_loading":1.35,
    }
    kcal_target = round(tdee * multipliers.get(tier, 1.0))

    # Distribución de macros por tier
    if tier == "high_carb":
        cho_pct, pro_pct, fat_pct = 0.60, 0.20, 0.20
    elif tier == "carb_loading":
        cho_pct, pro_pct, fat_pct = 0.70, 0.15, 0.15
    elif tier == "low_carb":
        cho_pct, pro_pct, fat_pct = 0.35, 0.30, 0.35
    else:
        cho_pct, pro_pct, fat_pct = 0.50, 0.25, 0.25

    return {
        "kcal":      kcal_target,
        "carbs_g":   round(kcal_target * cho_pct / 4),
        "protein_g": round(kcal_target * pro_pct / 4),
        "fat_g":     round(kcal_target * fat_pct / 9),
        "cho_g_per_kg": round((kcal_target * cho_pct / 4) / weight, 1),
        "tier":      tier,
    }


def _hydration_goal_ml(me: User, tl: Optional[GarminTrainingLoad],
                       health: Optional[GarminHealthDaily]) -> int:
    """
    Objetivo de hidratación diario:
    Base: 35ml/kg peso corporal
    +500ml por cada hora de entrenamiento
    +300ml si temperatura estimada > 25°C (proxy: avg_stress Garmin)
    """
    weight = getattr(me, "peso_kg", 75.0) or 75.0
    base_ml = weight * 35

    training_hours = (tl.tss_day or 0) / 60 if tl else 0  # estimado
    training_ml = training_hours * 500

    heat_ml = 0
    if health and (health.avg_stress or 0) > 60:  # high stress = hot day proxy
        heat_ml = 300

    return int(round(base_ml + training_ml + heat_ml, -2))  # redondear a 100ml


# ─────────────────────────────────────────────────────────────────────────────
# § BALANCE CALÓRICO (Garmin-Integrated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/balance/{date_iso}")
def calorie_balance(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    """
    Balance calórico real del día:
    kcal_in  = suma del diario alimentario
    kcal_burn= active_kcal (Garmin) + bmr_kcal (Garmin) o estimado
    balance  = kcal_in - kcal_burn
    """
    entries = db.query(FoodDiaryEntry).filter(
        FoodDiaryEntry.user_id  == me.id,
        FoodDiaryEntry.date_iso == date_iso,
    ).all()
    totals = _diary_totals(entries)

    health = _get_health_daily(me.id, date_iso, db)
    tl     = _get_training_load(me.id, date_iso, db)

    active_kcal = (health.active_kcal if health and health.active_kcal else None)
    bmr_kcal    = (health.bmr_kcal    if health and health.bmr_kcal    else None)

    # Estimado si no hay Garmin data
    if not active_kcal:
        tss = (tl.tss_day or 0) if tl else 0
        active_kcal = round(tss * 5.5)  # ~5.5 kcal/TSS (estimado conservador)

    if not bmr_kcal:
        weight = getattr(me, "peso_kg", 75.0) or 75.0
        height = getattr(me, "altura_cm", 175.0) or 175.0
        age    = getattr(me, "edad", 35) or 35
        bmr_kcal = round(10 * weight + 6.25 * height - 5 * age + 5)

    total_burn = (active_kcal or 0) + (bmr_kcal or 0)
    balance    = round(totals["kcal"] - total_burn)

    # Semáforo
    if abs(balance) <= 200:
        status = "balanced"
        status_label = "Equilibrado"
        status_color = "#10B981"
    elif balance < -700:
        status = "large_deficit"
        status_label = "Deficit grande — riesgo recuperación"
        status_color = "#EF4444"
    elif balance < -200:
        status = "deficit"
        status_label = "Deficit — considera comer más"
        status_color = "#F0A500"
    elif balance > 500:
        status = "large_surplus"
        status_label = "Superávit grande"
        status_color = "#A855F7"
    else:
        status = "surplus"
        status_label = "Superávit leve"
        status_color = "#7FB3CC"

    return {
        "date_iso":    date_iso,
        "kcal_in":     totals["kcal"],
        "active_kcal": active_kcal,
        "bmr_kcal":    bmr_kcal,
        "total_burn":  total_burn,
        "balance":     balance,
        "status":      status,
        "status_label":status_label,
        "status_color":status_color,
        "garmin_data_available": bool(health),
        "macros":      totals,
    }


# ─────────────────────────────────────────────────────────────────────────────
# § CARB PERIODIZATION
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/periodization")
def carb_periodization(
    days: int = Query(7, ge=1, le=14),
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    """
    Plan de carbohidratos para los próximos N días según TSS programado.
    Diferenciador único: combina datos reales de CTL/TSS con targets de macro.
    """
    today = date.today()
    plan  = []

    for i in range(days):
        d     = today + timedelta(days=i)
        d_iso = d.isoformat()
        tl    = _get_training_load(me.id, d_iso, db)
        tier  = _carb_periodization_tier(tl)
        targets = _compute_kcal_targets(me, tier)

        plan.append({
            "date_iso":    d_iso,
            "day_label":   ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][d.weekday()],
            "tss_planned": (tl.tss_day or 0) if tl else 0,
            "tier":        tier,
            "tier_label":  {
                "high_carb":    "🔥 Alto CHO",
                "moderate":     "⚡ Moderado",
                "low_carb":     "🥗 Bajo CHO",
                "carb_loading": "🚀 Carga de CHO",
            }.get(tier, tier),
            "kcal_target": targets["kcal"],
            "carbs_g":     targets["carbs_g"],
            "protein_g":   targets["protein_g"],
            "fat_g":       targets["fat_g"],
            "cho_g_per_kg":targets["cho_g_per_kg"],
            "key_foods":   _tier_key_foods(tier),
        })

    return {"plan": plan, "athlete_weight_kg": getattr(me, "peso_kg", 75) or 75}


def _tier_key_foods(tier: str) -> list[str]:
    foods = {
        "high_carb":    ["Arroz blanco", "Pasta", "Pan integral", "Plátano", "Miel", "Bebida deportiva"],
        "moderate":     ["Quinoa", "Avena", "Boniato", "Frutas", "Legumbres"],
        "low_carb":     ["Aguacate", "Huevos", "Salmón", "Brócoli", "Almendras", "Pollo"],
        "carb_loading": ["Pasta", "Arroz", "Pan blanco", "Mermelada", "Jugo de frutas", "Gel energético"],
    }
    return foods.get(tier, [])


# ─────────────────────────────────────────────────────────────────────────────
# § HIDRATACIÓN
# ─────────────────────────────────────────────────────────────────────────────

class _HydrationIn(BaseModel):
    amount_ml:   int
    liquid_type: str = "water"
    date_iso:    Optional[str] = None
    notes:       Optional[str] = None

    @field_validator("amount_ml")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0 or v > 5000:
            raise ValueError("amount_ml debe estar entre 1 y 5000")
        return v

    @field_validator("liquid_type")
    @classmethod
    def validate_type(cls, v):
        if v not in LIQUID_TYPES:
            raise ValueError(f"liquid_type debe ser uno de {LIQUID_TYPES}")
        return v


@router.get("/hydration/{date_iso}")
def get_hydration(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    logs = db.query(HydrationLog).filter(
        HydrationLog.user_id  == me.id,
        HydrationLog.date_iso == date_iso,
    ).order_by(HydrationLog.logged_at).all()

    tl     = _get_training_load(me.id, date_iso, db)
    health = _get_health_daily(me.id, date_iso, db)
    goal   = _hydration_goal_ml(me, tl, health)
    total  = sum(l.amount_ml for l in logs)
    pct    = round(total / goal * 100) if goal else 0

    return {
        "date_iso":   date_iso,
        "goal_ml":    goal,
        "total_ml":   total,
        "pct":        pct,
        "status":     "ok" if pct >= 80 else ("warning" if pct >= 50 else "low"),
        "by_type": {
            lt: sum(l.amount_ml for l in logs if l.liquid_type == lt)
            for lt in LIQUID_TYPES if any(l.liquid_type == lt for l in logs)
        },
        "logs": [
            {
                "id":          l.id,
                "amount_ml":   l.amount_ml,
                "liquid_type": l.liquid_type,
                "logged_at":   l.logged_at.isoformat(),
                "notes":       l.notes,
            }
            for l in logs
        ],
    }


@router.post("/hydration", status_code=201)
def add_hydration(
    body: _HydrationIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    d_iso = body.date_iso or _today()
    log   = HydrationLog(
        user_id     = me.id,
        date_iso    = d_iso,
        amount_ml   = body.amount_ml,
        liquid_type = body.liquid_type,
        notes       = body.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"ok": True, "id": log.id, "amount_ml": log.amount_ml}


@router.delete("/hydration/{log_id}")
def delete_hydration(
    log_id: str,
    db:     Session = Depends(get_db),
    me:     User    = Depends(require_feature("nutrition")),
):
    log = db.query(HydrationLog).filter(
        HydrationLog.id      == log_id,
        HydrationLog.user_id == me.id,
    ).first()
    if not log:
        raise HTTPException(404, "Registro no encontrado")
    db.delete(log)
    db.commit()
    return {"ok": True}


@router.get("/hydration/goal/{date_iso}")
def hydration_goal(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    tl     = _get_training_load(me.id, date_iso, db)
    health = _get_health_daily(me.id, date_iso, db)
    goal   = _hydration_goal_ml(me, tl, health)
    return {
        "date_iso": date_iso,
        "goal_ml":  goal,
        "goal_l":   round(goal / 1000, 1),
        "breakdown": {
            "base_ml":     int((getattr(me, "peso_kg", 75) or 75) * 35),
            "training_ml": goal - int((getattr(me, "peso_kg", 75) or 75) * 35),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# § PESO CORPORAL
# ─────────────────────────────────────────────────────────────────────────────

class _WeightIn(BaseModel):
    weight_kg:    float
    body_fat_pct: Optional[float] = None
    date_iso:     Optional[str]   = None
    notes:        Optional[str]   = None

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v):
        if v < 30 or v > 300:
            raise ValueError("Peso fuera de rango (30-300 kg)")
        return round(v, 1)


@router.post("/weight", status_code=201)
def log_weight(
    body: _WeightIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    d_iso = body.date_iso or _today()
    # Upsert por fecha
    existing = db.query(WeightLog).filter(
        WeightLog.user_id  == me.id,
        WeightLog.date_iso == d_iso,
    ).first()

    if existing:
        existing.weight_kg    = body.weight_kg
        existing.body_fat_pct = body.body_fat_pct
        existing.notes        = body.notes
        existing.source       = "manual"  # una carga manual siempre gana, aunque el día ya tuviera un valor de Garmin
    else:
        db.add(WeightLog(
            user_id      = me.id,
            date_iso     = d_iso,
            weight_kg    = body.weight_kg,
            body_fat_pct = body.body_fat_pct,
            notes        = body.notes,
            source       = "manual",
        ))
    db.commit()
    return {"ok": True, "date_iso": d_iso, "weight_kg": body.weight_kg}


@router.get("/weight/history")
def weight_history(
    days: int = Query(90, ge=7, le=365),
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    logs   = db.query(WeightLog).filter(
        WeightLog.user_id  == me.id,
        WeightLog.date_iso >= cutoff,
    ).order_by(WeightLog.date_iso).all()

    points = [{"date_iso": l.date_iso, "weight_kg": l.weight_kg, "body_fat_pct": l.body_fat_pct} for l in logs]

    # Tendencia lineal (regresión simple)
    trend = None
    if len(points) >= 3:
        n    = len(points)
        xs   = list(range(n))
        ys   = [p["weight_kg"] for p in points]
        x_m  = sum(xs) / n
        y_m  = sum(ys) / n
        num  = sum((xs[i] - x_m) * (ys[i] - y_m) for i in range(n))
        den  = sum((xs[i] - x_m) ** 2 for i in range(n))
        slope = (num / den) if den else 0
        trend = {
            "slope_kg_per_week": round(slope * 7, 2),
            "direction": "up" if slope > 0.01 else ("down" if slope < -0.01 else "stable"),
        }

    # Alerta RED-S (pérdida > 2% en 7 días)
    alerts = []
    if len(points) >= 2:
        last_week = [p for p in points if p["date_iso"] >= (date.today() - timedelta(days=7)).isoformat()]
        if len(last_week) >= 2:
            loss_pct = (last_week[0]["weight_kg"] - last_week[-1]["weight_kg"]) / last_week[0]["weight_kg"] * 100
            if loss_pct > 2.0:
                alerts.append({
                    "type":    "reds_risk",
                    "message": f"Pérdida de {loss_pct:.1f}% en 7 días — posible riesgo RED-S. Consulta con tu nutricionista.",
                    "severity":"high",
                })

    return {
        "points":     points,
        "current_kg": points[-1]["weight_kg"] if points else None,
        "first_kg":   points[0]["weight_kg"]  if points else None,
        "change_kg":  round(points[-1]["weight_kg"] - points[0]["weight_kg"], 1) if len(points) >= 2 else None,
        "trend":      trend,
        "alerts":     alerts,
        "n":          len(points),
    }


@router.delete("/weight/{log_id}")
def delete_weight(
    log_id: str,
    db:     Session = Depends(get_db),
    me:     User    = Depends(require_feature("nutrition")),
):
    log = db.query(WeightLog).filter(WeightLog.id == log_id, WeightLog.user_id == me.id).first()
    if not log:
        raise HTTPException(404, "Registro no encontrado")
    db.delete(log)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § SUPLEMENTOS
# ─────────────────────────────────────────────────────────────────────────────

class _SupplementIn(BaseModel):
    supplement: str
    dose_mg:    Optional[float] = None
    date_iso:   Optional[str]   = None
    notes:      Optional[str]   = None


@router.get("/supplements/catalog")
def supplement_catalog():
    """Catálogo de suplementos comunes para triatletas."""
    return {"catalog": SUPPLEMENT_CAT}


@router.get("/supplements/{date_iso}")
def get_supplements(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    logs = db.query(SupplementLog).filter(
        SupplementLog.user_id  == me.id,
        SupplementLog.date_iso == date_iso,
    ).order_by(SupplementLog.taken_at).all()

    return {
        "date_iso": date_iso,
        "logs": [
            {
                "id":         l.id,
                "supplement": l.supplement,
                "name":       SUPPLEMENT_CAT.get(l.supplement, {}).get("name", l.supplement),
                "dose_mg":    l.dose_mg,
                "taken_at":   l.taken_at.isoformat(),
                "notes":      l.notes,
            }
            for l in logs
        ],
    }


@router.post("/supplements", status_code=201)
def log_supplement(
    body: _SupplementIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    d_iso = body.date_iso or _today()
    log   = SupplementLog(
        user_id    = me.id,
        date_iso   = d_iso,
        supplement = body.supplement,
        dose_mg    = body.dose_mg,
        notes      = body.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"ok": True, "id": log.id}


@router.delete("/supplements/{log_id}")
def delete_supplement(
    log_id: str,
    db:     Session = Depends(get_db),
    me:     User    = Depends(require_feature("nutrition")),
):
    log = db.query(SupplementLog).filter(
        SupplementLog.id == log_id, SupplementLog.user_id == me.id
    ).first()
    if not log:
        raise HTTPException(404, "Registro no encontrado")
    db.delete(log)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § ALIMENTOS PERSONALIZADOS
# ─────────────────────────────────────────────────────────────────────────────

class _CustomFoodIn(BaseModel):
    name:         str
    brand:        Optional[str]  = None
    serving_g:    float          = 100.0
    kcal_100g:    float
    carbs_100g:   Optional[float]= None
    protein_100g: Optional[float]= None
    fat_100g:     Optional[float]= None
    fiber_100g:   Optional[float]= None
    sodium_100g:  Optional[float]= None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        v = v.strip()
        if not v: raise ValueError("name requerido")
        if len(v) > 100: raise ValueError("name máximo 100 caracteres")
        return v

    @field_validator("kcal_100g")
    @classmethod
    def valid_kcal(cls, v):
        if v < 0 or v > 900: raise ValueError("kcal_100g fuera de rango")
        return round(v, 1)


@router.get("/custom-foods")
def list_custom_foods(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    foods = db.query(CustomFood).filter(CustomFood.user_id == me.id).order_by(CustomFood.name).all()
    return [
        {
            "id":          f.id,
            "name":        f.name,
            "brand":       f.brand,
            "serving_g":   f.serving_g,
            "kcal_100g":   f.kcal_100g,
            "carbs_100g":  f.carbs_100g,
            "protein_100g":f.protein_100g,
            "fat_100g":    f.fat_100g,
        }
        for f in foods
    ]


@router.post("/custom-foods", status_code=201)
def create_custom_food(
    body: _CustomFoodIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    food = CustomFood(
        user_id      = me.id,
        name         = body.name,
        brand        = body.brand,
        serving_g    = body.serving_g,
        kcal_100g    = body.kcal_100g,
        carbs_100g   = body.carbs_100g,
        protein_100g = body.protein_100g,
        fat_100g     = body.fat_100g,
        fiber_100g   = body.fiber_100g,
        sodium_100g  = body.sodium_100g,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return {"ok": True, "id": food.id, "name": food.name}


@router.put("/custom-foods/{food_id}")
def update_custom_food(
    food_id: str,
    body:    _CustomFoodIn,
    db:      Session = Depends(get_db),
    me:      User    = Depends(require_feature("nutrition")),
):
    food = db.query(CustomFood).filter(CustomFood.id == food_id, CustomFood.user_id == me.id).first()
    if not food:
        raise HTTPException(404, "Alimento no encontrado")
    for field in ("name","brand","serving_g","kcal_100g","carbs_100g","protein_100g","fat_100g","fiber_100g","sodium_100g"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(food, field, val)
    db.commit()
    return {"ok": True}


@router.delete("/custom-foods/{food_id}")
def delete_custom_food(
    food_id: str,
    db:      Session = Depends(get_db),
    me:      User    = Depends(require_feature("nutrition")),
):
    food = db.query(CustomFood).filter(CustomFood.id == food_id, CustomFood.user_id == me.id).first()
    if not food:
        raise HTTPException(404, "Alimento no encontrado")
    db.delete(food)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § FAVORITOS
# ─────────────────────────────────────────────────────────────────────────────

class _FavoriteIn(BaseModel):
    food_ref:    str        # off_id o "custom:{id}"
    food_name:   str
    brand:       Optional[str]  = None
    default_g:   float          = 100.0
    kcal_100g:   Optional[float]= None
    carbs_100g:  Optional[float]= None
    protein_100g:Optional[float]= None
    fat_100g:    Optional[float]= None


@router.get("/favorites")
def list_favorites(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    favs = db.query(FavoriteFood).filter(
        FavoriteFood.user_id == me.id
    ).order_by(desc(FavoriteFood.use_count), desc(FavoriteFood.last_used)).limit(50).all()

    return [
        {
            "id":          f.id,
            "food_ref":    f.food_ref,
            "food_name":   f.food_name,
            "brand":       f.brand,
            "default_g":   f.default_g,
            "kcal_100g":   f.kcal_100g,
            "carbs_100g":  f.carbs_100g,
            "protein_100g":f.protein_100g,
            "fat_100g":    f.fat_100g,
            "use_count":   f.use_count,
            "last_used":   f.last_used.isoformat(),
        }
        for f in favs
    ]


@router.post("/favorites", status_code=201)
def add_favorite(
    body: _FavoriteIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    # Upsert: si ya existe, incrementar use_count
    existing = db.query(FavoriteFood).filter(
        FavoriteFood.user_id  == me.id,
        FavoriteFood.food_ref == body.food_ref,
    ).first()

    if existing:
        existing.use_count += 1
        existing.last_used  = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return {"ok": True, "id": existing.id, "action": "updated"}

    fav = FavoriteFood(
        user_id     = me.id,
        food_ref    = body.food_ref,
        food_name   = body.food_name,
        brand       = body.brand,
        default_g   = body.default_g,
        kcal_100g   = body.kcal_100g,
        carbs_100g  = body.carbs_100g,
        protein_100g= body.protein_100g,
        fat_100g    = body.fat_100g,
    )
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return {"ok": True, "id": fav.id, "action": "created"}


@router.delete("/favorites/{fav_id}")
def remove_favorite(
    fav_id: str,
    db:     Session = Depends(get_db),
    me:     User    = Depends(require_feature("nutrition")),
):
    fav = db.query(FavoriteFood).filter(
        FavoriteFood.id == fav_id, FavoriteFood.user_id == me.id
    ).first()
    if not fav:
        raise HTTPException(404, "Favorito no encontrado")
    db.delete(fav)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# § RACE DAY NUTRITION PROTOCOL
# ─────────────────────────────────────────────────────────────────────────────

RACE_DISTANCES = {
    "sprint": {"swim_km": 0.75, "bike_km": 20,  "run_km": 5,  "total_h": 1.1},
    "oly":    {"swim_km": 1.5,  "bike_km": 40,  "run_km": 10, "total_h": 2.2},
    "703":    {"swim_km": 1.9,  "bike_km": 90,  "run_km": 21, "total_h": 5.0},
    "im":     {"swim_km": 3.8,  "bike_km": 180, "run_km": 42, "total_h": 11.0},
}


@router.get("/race-protocol")
def race_protocol(
    distance:    str   = Query("703",  pattern="^(sprint|oly|703|im)$"),
    weight_kg:   float = Query(75.0,   ge=40, le=150),
    temp_celsius:float = Query(22.0,   ge=0,  le=45),
    ftp_w:       int   = Query(250,    ge=100, le=500),
    db:          Session = Depends(get_db),
    me:          User    = Depends(require_feature("nutrition")),
):
    """
    Genera protocolo de nutrición de carrera personalizado.
    Basado en: peso, temperatura, FTP, distancia.
    Supera a TriDot: integra con CTL/TSB real del atleta.
    """
    dist   = RACE_DISTANCES[distance]
    dur_h  = dist["total_h"]
    weight = weight_kg

    # Ajuste por temperatura
    heat_factor = 1.0 + max(0, (temp_celsius - 22) * 0.02)

    # Fluidos por hora (base 600ml + ajuste calor)
    fluid_ml_h = round(600 * heat_factor)
    fluid_ml_h = max(400, min(1200, fluid_ml_h))

    # Sodio por hora (base 800mg + ajuste calor)
    sodium_mg_h = round(800 * heat_factor)

    # Carbohidratos por hora según duración
    if dur_h <= 1.5:
        cho_g_h = 30   # ≤ 1.5h: puede correr en ayunas
    elif dur_h <= 2.5:
        cho_g_h = 45   # 1.5-2.5h: moderado
    elif dur_h <= 5:
        cho_g_h = 60   # 70.3: máximo simple
    else:
        cho_g_h = 90   # IM: múltiples fuentes CHO (glucosa + fructosa)

    # Total de carrera
    total_cho_g  = round(cho_g_h * dur_h)
    total_fluid_ml = round(fluid_ml_h * dur_h)
    total_sodium_mg= round(sodium_mg_h * dur_h)

    # Protocolo por segmento
    segments = []

    # PRE-RACE (30-60 min antes)
    segments.append({
        "phase":     "pre_race",
        "label":     "Pre-carrera (30-60 min antes)",
        "cho_g":     40,
        "fluid_ml":  500,
        "sodium_mg": 500,
        "tips": [
            "Desayuno ligero 3h antes (arroz/tostadas + plátano)",
            "Gel o banana 30min antes del start",
            "Hidratación 500ml en la hora previa",
        ],
    })

    # SWIM
    segments.append({
        "phase":     "swim",
        "label":     f"Natación ({dist['swim_km']}km)",
        "cho_g":     0,
        "fluid_ml":  0,
        "sodium_mg": 0,
        "tips":      ["Sin nutrición en el agua — concentrarse en ritmo"],
    })

    # T1
    segments.append({
        "phase":     "t1",
        "label":     "Transición 1",
        "cho_g":     0,
        "fluid_ml":  150,
        "sodium_mg": 200,
        "tips":      ["Sip de bebida isotónica en T1 si la carrera es larga"],
    })

    # BIKE — mayoría de la nutrición aquí
    bike_h    = dist["bike_km"] / 35  # velocidad promedio estimada
    bike_cho  = round(cho_g_h * bike_h)
    bike_fluid= round(fluid_ml_h * bike_h)
    gel_count = math.ceil(bike_cho / 25)  # geles de 25g CHO cada uno
    segments.append({
        "phase":      "bike",
        "label":      f"Ciclismo ({dist['bike_km']}km, ~{bike_h:.1f}h)",
        "cho_g":      bike_cho,
        "fluid_ml":   bike_fluid,
        "sodium_mg":  round(sodium_mg_h * bike_h),
        "protocol":   {
            "gels":       gel_count,
            "gel_every_min": 30,
            "bars":       max(0, math.ceil((bike_cho - gel_count*25) / 40)) if distance in ("703","im") else 0,
            "drink_every_min": 15,
            "salt_tabs":  math.ceil(bike_h) if temp_celsius > 28 else 0,
        },
        "tips": [
            f"Gel cada 30 min ({gel_count} geles en total en la bici)",
            f"Beber {fluid_ml_h//100*100}ml cada 15 min (~{fluid_ml_h}ml/h)",
            "Primera hora: foco en hidratación + electrolitos, no CHO",
            f"{'Combina glucosa + fructosa (2:1) para >60g/h' if cho_g_h >= 60 else 'Gel de glucosa simple es suficiente'}",
        ],
    })

    # T2
    segments.append({
        "phase":     "t2",
        "label":     "Transición 2",
        "cho_g":     10,
        "fluid_ml":  200,
        "sodium_mg": 300,
        "tips":      ["Cola pequeña o gel rápido si estómago lo tolera"],
    })

    # RUN
    run_h    = dist["run_km"] / 10
    run_cho  = round(cho_g_h * run_h * 0.7)  # 70% vs bici (intestino estresado)
    run_gel  = math.ceil(run_cho / 25)
    segments.append({
        "phase":      "run",
        "label":      f"Carrera ({dist['run_km']}km, ~{run_h:.1f}h)",
        "cho_g":      run_cho,
        "fluid_ml":   round(fluid_ml_h * run_h * 0.85),
        "sodium_mg":  round(sodium_mg_h * run_h),
        "protocol": {
            "gels":           run_gel,
            "gel_every_km":   round(dist["run_km"] / max(1, run_gel)),
            "cola_from_km":   dist["run_km"] * 0.6 if distance == "im" else None,
            "aid_station_sip":"agua + bebida isotónica",
        },
        "tips": [
            f"Gel en cada estación de alimentación (~{round(dist['run_km']/max(1,run_gel))}km)",
            "Preferir líquidos sobre sólidos si hay fatiga GI",
            "Cola-Coca en la segunda mitad del run (IM): cafeína + CHO rápidos",
        ],
    })

    # TSB actual del atleta
    today_iso = _today()
    tl = _get_training_load(me.id, today_iso, db)
    tsb_note = None
    if tl and tl.tsb is not None:
        if tl.tsb > 15:
            tsb_note = f"TSB actual: +{int(tl.tsb)} — Forma excelente. No sobrealimentes por nervios."
        elif tl.tsb > 0:
            tsb_note = f"TSB actual: +{int(tl.tsb)} — Buena forma. Sigue el protocolo normal."
        else:
            tsb_note = f"TSB actual: {int(tl.tsb)} — Llega con cierta fatiga. Prioriza CHO desde el inicio."

    return {
        "distance":      distance,
        "duration_h":    dur_h,
        "weight_kg":     weight,
        "temp_celsius":  temp_celsius,
        "totals": {
            "cho_g":       total_cho_g,
            "fluid_ml":    total_fluid_ml,
            "sodium_mg":   total_sodium_mg,
            "cho_g_per_h": cho_g_h,
            "fluid_ml_h":  fluid_ml_h,
            "sodium_mg_h": sodium_mg_h,
        },
        "segments":      segments,
        "tsb_note":      tsb_note,
        "heat_alert":    temp_celsius >= 28,
        "ai_briefing":   _race_briefing(distance, cho_g_h, fluid_ml_h, temp_celsius, weight),
    }


def _race_briefing(dist: str, cho_g_h: float, fluid_ml_h: float,
                   temp: float, weight: float) -> str:
    heat = "⚠️ ALERTA CALOR: aumenta hidratación +20% y electrolitos." if temp >= 28 else ""
    return (
        f"Para un {dist.upper()} ({RACE_DISTANCES[dist]['total_h']}h estimado a {weight}kg): "
        f"objetivo {cho_g_h}g CHO/h y {fluid_ml_h}ml/h. "
        f"Concentra el 60% de la nutrición en la bici. "
        f"En carrera: geles en puntos de avituallamiento. "
        f"{heat}"
    ).strip()


# ─────────────────────────────────────────────────────────────────────────────
# § IA — INSIGHTS NUTRICIONALES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/insights/{date_iso}")
def nutrition_insights(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    """
    Genera hasta 4 insights proactivos basados en:
    - Balance calórico del día
    - CHO vs target (carb periodization)
    - Hidratación
    - Tendencia de peso (última semana)
    - TSB actual
    """
    # Verificar cache
    cached = db.query(NutritionInsight).filter(
        NutritionInsight.user_id  == me.id,
        NutritionInsight.date_iso == date_iso,
    ).first()
    if cached and (datetime.now(timezone.utc).replace(tzinfo=None) - cached.generated_at).seconds < 3600:
        return {
            "date_iso":        date_iso,
            "insights":        json.loads(cached.insights or "[]"),
            "meal_suggestions":json.loads(cached.meal_suggestions or "[]"),
            "cached":          True,
        }

    # Calcular datos
    entries = db.query(FoodDiaryEntry).filter(
        FoodDiaryEntry.user_id  == me.id,
        FoodDiaryEntry.date_iso == date_iso,
    ).all()
    totals = _diary_totals(entries)

    tl     = _get_training_load(me.id, date_iso, db)
    health = _get_health_daily(me.id, date_iso, db)
    tier   = _carb_periodization_tier(tl)
    targets = _compute_kcal_targets(me, tier)

    # Hidratación
    hyd_logs = db.query(HydrationLog).filter(
        HydrationLog.user_id  == me.id,
        HydrationLog.date_iso == date_iso,
    ).all()
    hyd_total = sum(l.amount_ml for l in hyd_logs)
    hyd_goal  = _hydration_goal_ml(me, tl, health)

    # Peso última semana
    cutoff = (date.fromisoformat(date_iso) - timedelta(days=7)).isoformat()
    weight_points = db.query(WeightLog).filter(
        WeightLog.user_id  == me.id,
        WeightLog.date_iso >= cutoff,
    ).order_by(WeightLog.date_iso).all()

    insights:       list[str] = []
    meal_suggestions: list[dict] = []

    # Insight 1: CHO vs target
    cho_gap = targets["carbs_g"] - totals["carbs_g"]
    if cho_gap > 50 and totals["carbs_g"] > 0:
        insights.append(
            f"Estás a {int(cho_gap)}g de CHO del target ({int(totals['carbs_g'])}/{targets['carbs_g']}g). "
            f"Es un día {tier.replace('_',' ')}. Considera 1 taza de arroz o 2 plátanos antes de las 8pm."
        )
        meal_suggestions.append({
            "meal": "Snack tardío",
            "options": ["1 taza de arroz cocido (45g CHO)", "2 plátanos (54g CHO)", "2 rebanadas de pan integral + miel (50g CHO)"],
            "reason": f"+{int(cho_gap)}g CHO necesarios",
        })

    # Insight 2: Proteína post-entrenamiento
    tss = (tl.tss_day or 0) if tl else 0
    if tss > 80 and totals["protein_g"] < targets["protein_g"] * 0.7:
        insights.append(
            f"Entrenamiento intenso (TSS {int(tss)}) pero solo {int(totals['protein_g'])}g proteína "
            f"(meta: {targets['protein_g']}g). La ventana anabólica se cierra — añade proteína ahora."
        )
        meal_suggestions.append({
            "meal": "Snack proteico urgente",
            "options": ["200g yogurt griego (20g proteína)", "2 huevos + 1 lata atún (35g proteína)", "Batido de proteínas (25g proteína)"],
            "reason": "Recuperación muscular comprometida",
        })

    # Insight 3: Hidratación
    hyd_pct = hyd_total / hyd_goal * 100 if hyd_goal else 100
    if hyd_pct < 60:
        insights.append(
            f"Hidratación baja: {hyd_total}ml de {hyd_goal}ml objetivo ({int(hyd_pct)}%). "
            f"Riesgo de rendimiento reducido mañana. Bebe 500ml ahora."
        )

    # Insight 4: Peso (alerta RED-S)
    if len(weight_points) >= 2:
        w_loss = (weight_points[0].weight_kg - weight_points[-1].weight_kg)
        w_pct  = w_loss / weight_points[0].weight_kg * 100
        if w_pct > 1.5:
            insights.append(
                f"Has perdido {w_loss:.1f}kg esta semana ({w_pct:.1f}%). "
                "Una pérdida rápida puede afectar tu CTL y aumentar el riesgo de lesión. "
                "Revisa tu balance calórico."
            )

    # Insight 5: TSB muy negativo + bajo CHO
    if tl and (tl.tsb or 0) < -15 and cho_gap > 30:
        insights.append(
            f"TSB en {int(tl.tsb or 0)} (fatiga alta) y CHO bajo. Combinación de riesgo para el rendimiento. "
            "Prioriza recuperación con CHO + proteína hoy."
        )

    # Mensaje si todo está bien
    if not insights:
        insights.append(
            "Nutrición del día en orden. "
            f"CHO: {int(totals['carbs_g'])}/{targets['carbs_g']}g | "
            f"Proteína: {int(totals['protein_g'])}/{targets['protein_g']}g | "
            f"Hidratación: {hyd_total}ml/{hyd_goal}ml."
        )

    # Guardar cache
    if cached:
        cached.insights        = json.dumps(insights)
        cached.meal_suggestions= json.dumps(meal_suggestions)
        cached.generated_at    = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        db.add(NutritionInsight(
            user_id          = me.id,
            date_iso         = date_iso,
            insights         = json.dumps(insights),
            meal_suggestions = json.dumps(meal_suggestions),
        ))
    db.commit()

    return {
        "date_iso":        date_iso,
        "insights":        insights,
        "meal_suggestions":meal_suggestions,
        "cached":          False,
        "tier":            tier,
        "tier_label":      {"high_carb":"🔥 Alto CHO","moderate":"⚡ Moderado","low_carb":"🥗 Bajo CHO"}.get(tier, tier),
    }


# ─────────────────────────────────────────────────────────────────────────────
# § DASHBOARD — 1 sola llamada para toda la UI
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def nutrition_dashboard(
    date_iso: Optional[str] = Query(None),
    db:       Session = Depends(get_db),
    me:       User    = Depends(require_feature("nutrition")),
):
    """
    Endpoint maestro de la página de nutrición.
    Devuelve en 1 llamada: balance, macros, hidratación, peso, suplementos, insights.
    Minimiza round-trips del frontend.
    """
    d_iso = date_iso or _today()

    # Diario del día
    entries = db.query(FoodDiaryEntry).filter(
        FoodDiaryEntry.user_id  == me.id,
        FoodDiaryEntry.date_iso == d_iso,
    ).order_by(FoodDiaryEntry.created_at).all()
    totals = _diary_totals(entries)

    # Training load
    tl     = _get_training_load(me.id, d_iso, db)
    health = _get_health_daily(me.id, d_iso, db)
    tier   = _carb_periodization_tier(tl)
    targets = _compute_kcal_targets(me, tier)

    # Calorie burn (Garmin)
    active_kcal = (health.active_kcal if health and health.active_kcal else
                   round((tl.tss_day or 0) * 5.5 if tl else 0))
    weight_kg   = getattr(me, "peso_kg", 75.0) or 75.0
    height_cm   = getattr(me, "altura_cm", 175.0) or 175.0
    age         = getattr(me, "edad", 35) or 35
    bmr_kcal    = round(10 * weight_kg + 6.25 * height_cm - 5 * age + 5)
    total_burn  = active_kcal + bmr_kcal
    balance     = round(totals["kcal"] - total_burn)

    # Hidratación
    hyd_logs  = db.query(HydrationLog).filter(
        HydrationLog.user_id  == me.id,
        HydrationLog.date_iso == d_iso,
    ).all()
    hyd_total = sum(l.amount_ml for l in hyd_logs)
    hyd_goal  = _hydration_goal_ml(me, tl, health)

    # Peso hoy o más reciente
    weight_today = db.query(WeightLog).filter(
        WeightLog.user_id  == me.id,
        WeightLog.date_iso <= d_iso,
    ).order_by(desc(WeightLog.date_iso)).first()

    # Suplementos hoy
    supp_today = db.query(SupplementLog).filter(
        SupplementLog.user_id  == me.id,
        SupplementLog.date_iso == d_iso,
    ).all()

    # Porcentajes de cumplimiento
    def pct(actual, target):
        return min(100, round(actual / target * 100)) if target else 0

    # Entradas del diario agrupadas por slot
    by_slot: dict[str, list] = {}
    for e in entries:
        by_slot.setdefault(e.meal_slot, []).append({
            "id":         e.id,
            "food_name":  e.food_name,
            "quantity_g": e.quantity_g,
            "kcal":       e.kcal,
            "carbs_g":    e.carbs_g,
            "protein_g":  e.protein_g,
            "fat_g":      e.fat_g,
        })

    return {
        "date_iso":  d_iso,

        # Macros
        "macros": {
            "kcal":       totals["kcal"],
            "carbs_g":    totals["carbs_g"],
            "protein_g":  totals["protein_g"],
            "fat_g":      totals["fat_g"],
            "fiber_g":    totals["fiber_g"],
            "sodium_mg":  totals["sodium_mg"],
        },
        "targets":   targets,
        "pct": {
            "kcal":     pct(totals["kcal"],     targets["kcal"]),
            "carbs":    pct(totals["carbs_g"],  targets["carbs_g"]),
            "protein":  pct(totals["protein_g"],targets["protein_g"]),
            "fat":      pct(totals["fat_g"],    targets["fat_g"]),
        },
        "tier":       tier,
        "tier_label": {"high_carb":"🔥 Alto CHO","moderate":"⚡ Moderado","low_carb":"🥗 Bajo CHO","carb_loading":"🚀 Carga CHO"}.get(tier, tier),

        # Calorie balance
        "balance": {
            "kcal_in":     totals["kcal"],
            "active_kcal": active_kcal,
            "bmr_kcal":    bmr_kcal,
            "total_burn":  total_burn,
            "balance":     balance,
            "status":      "balanced" if abs(balance) <= 200 else ("deficit" if balance < 0 else "surplus"),
        },

        # Hidratación
        "hydration": {
            "total_ml":  hyd_total,
            "goal_ml":   hyd_goal,
            "pct":       pct(hyd_total, hyd_goal),
            "status":    "ok" if hyd_total >= hyd_goal * 0.8 else "low",
            "logs":      [{"id": l.id, "amount_ml": l.amount_ml, "liquid_type": l.liquid_type} for l in hyd_logs],
        },

        # Peso
        "weight": {
            "current_kg": weight_today.weight_kg if weight_today else None,
            "date_iso":   weight_today.date_iso  if weight_today else None,
        },

        # Suplementos
        "supplements": [
            {"id": s.id, "supplement": s.supplement,
             "name": SUPPLEMENT_CAT.get(s.supplement, {}).get("name", s.supplement),
             "dose_mg": s.dose_mg}
            for s in supp_today
        ],

        # Diario por slot
        "diary_by_slot": {
            slot: {
                "label":   SLOT_LABELS.get(slot, slot),
                "entries": by_slot.get(slot, []),
                "kcal":    sum(e["kcal"] or 0 for e in by_slot.get(slot, [])),
                "carbs_g": sum(e["carbs_g"] or 0 for e in by_slot.get(slot, [])),
            }
            for slot in MEAL_SLOTS
        },

        # Training context
        "training": {
            "tss_day":  (tl.tss_day or 0) if tl else 0,
            "ctl":      (tl.ctl or 0)     if tl else 0,
            "tsb":      (tl.tsb or 0)     if tl else 0,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# § COMPLIANCE — cumplimiento de macros (Sprint 24)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/compliance")
def get_nutrition_compliance(
    days: int = Query(default=7, ge=1, le=30),
    db:   Session = Depends(get_db),
    me:   User    = Depends(require_feature("nutrition")),
):
    """
    Compliance score de macros para los últimos N días.
    Combina datos del diario con los targets dinámicos del día.
    Útil para el widget de compliance en athlete-app.html y nutrition.html.
    """
    from ..services.nutrition_intelligence_service import compute_macro_compliance

    results = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        iso = d.isoformat()

        entries = (
            db.query(FoodDiaryEntry)
            .filter(FoodDiaryEntry.user_id == me.id, FoodDiaryEntry.date_iso == iso)
            .all()
        )

        totals = {
            "kcal": sum(e.kcal or 0 for e in entries),
            "carbs_g": sum(e.carbs_g or 0 for e in entries),
            "protein_g": sum(e.protein_g or 0 for e in entries),
            "fat_g": sum(e.fat_g or 0 for e in entries),
            "fiber_g": sum(e.fiber_g or 0 for e in entries),
        }

        if not entries:
            results.append({"date_iso": iso, "has_data": False, "compliance_score": None})
            continue

        tl   = _get_training_load(me.id, iso, db)
        tier = _carb_periodization_tier(tl)
        tgts = _compute_kcal_targets(me, tier)

        # Hydration
        hydration = (
            db.query(HydrationLog)
            .filter(HydrationLog.user_id == me.id, HydrationLog.date_iso == iso)
            .all()
        )
        hydration_ml = sum(h.amount_ml for h in hydration) if hydration else None

        compliance = compute_macro_compliance(
            kcal_target=tgts.get("kcal", 2200),
            kcal_actual=totals["kcal"],
            carbs_target_g=tgts.get("carbs_g", 280),
            carbs_actual_g=totals["carbs_g"],
            protein_target_g=tgts.get("protein_g", 140),
            protein_actual_g=totals["protein_g"],
            fat_target_g=tgts.get("fat_g", 70),
            fat_actual_g=totals["fat_g"],
            fiber_target_g=tgts.get("fiber_g", 30),
            fiber_actual_g=totals["fiber_g"],
            hydration_ml=hydration_ml,
        )

        results.append({
            "date_iso":         iso,
            "has_data":         True,
            "compliance_score": compliance.compliance_score,
            "compliance_label": compliance.compliance_label,
            "compliance_color": compliance.compliance_color,
            "gaps":             compliance.gaps,
            "excesses":         compliance.excesses,
            "hydration_ok":     compliance.hydration_ok,
            "macros_actual":    totals,
            "macros_target":    tgts,
        })

    avg_score = None
    scored = [r for r in results if r.get("compliance_score") is not None]
    if scored:
        avg_score = round(sum(r["compliance_score"] for r in scored) / len(scored))

    return {
        "days":      days,
        "avg_score": avg_score,
        "days_with_data": len(scored),
        "history":   results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# § LABS-SYNC — cruza blood labs con suplementación (Sprint 24)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/labs-sync")
def get_labs_nutrition_sync(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    """
    Blood Labs ↔ Supplement Protocol Bridge.

    Cruza los marcadores de labs alterados del último examen con el registro
    de suplementación de los últimos 30 días. Identifica brechas:
    atleta con ferritina baja pero sin hierro en suplementos → alerta proactiva.

    Diferenciador exclusivo de LabX: ningún competidor hace esta integración.
    """
    from ..models import BloodLabExam, SupplementLog
    from ..services.blood_labs_impact_service import compute_training_impact
    from ..services.nutrition_intelligence_service import compute_lab_nutrition_bridge

    # Último examen de sangre (últimos 90 días)
    cutoff_exam = (date.today() - timedelta(days=90)).isoformat()
    exam = (
        db.query(BloodLabExam)
        .filter(BloodLabExam.user_id == me.id, BloodLabExam.date_iso >= cutoff_exam)
        .order_by(BloodLabExam.date_iso.desc())
        .first()
    )

    if not exam:
        return {
            "has_labs": False,
            "message": "Sin análisis de sangre en los últimos 90 días. Sube un examen para activar esta función.",
        }

    import json
    try:
        values = json.loads(exam.values_json)
    except Exception:
        values = {}

    sex = "F" if (getattr(me, "sexo", None) == "F" or getattr(me, "sex", None) == "F") else "M"
    trs_report = compute_training_impact(values=values, sex=sex)

    markers_data = [
        {
            "key":    m.key,
            "name":   m.name,
            "status": m.status,
            "supplement_hint": m.supplement_hint,
        }
        for m in trs_report.markers_evaluated
        if m.status in ("warning", "critical")
    ]

    # Suplementos logueados en últimos 30 días
    cutoff_supp = (date.today() - timedelta(days=30)).isoformat()
    supp_logs = (
        db.query(SupplementLog)
        .filter(
            SupplementLog.user_id == me.id,
            SupplementLog.date_iso >= cutoff_supp,
        )
        .all()
    )

    supp_data = [
        {"supplement": sl.supplement, "dose_mg": sl.dose_mg, "date_iso": sl.date_iso}
        for sl in supp_logs
    ]

    bridge = compute_lab_nutrition_bridge(
        markers_evaluated=markers_data,
        supplement_logs_last_30d=supp_data,
    )

    return {
        "has_labs":            True,
        "exam_date":           exam.date_iso,
        "trs":                 trs_report.trs,
        "markers_flagged":     len(markers_data),
        "compliance_rate":     bridge.compliance_rate,
        "alert_count":         bridge.alert_count,
        "top_action":          bridge.top_action,
        "gaps": [
            {
                "marker":                 g.marker_name,
                "severity":               g.marker_status,
                "recommended_supplements": g.recommended_supplements,
                "is_being_supplemented":  g.is_being_supplemented,
                "days_logged":            g.days_logged_supplement,
                "action":                 g.action,
            }
            for g in bridge.gaps
        ],
        "covered": [
            {
                "marker":      c.marker_name,
                "supplement":  c.recommended_supplements[0] if c.recommended_supplements else "—",
                "days_logged": c.days_logged_supplement,
            }
            for c in bridge.covered
        ],
        "supplement_logs_last_30d": len(supp_data),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PRECISE SPLIT PREDICTION — física real (viento, pendiente, altitud, superficie)
# Usado por nutrition.html para reemplazar el modelo simple de cancha plana.
# ─────────────────────────────────────────────────────────────────────────────

_SPLIT_DIST_M = {
    "sprint":  {"swim": 750,  "bike": 20000,  "run": 5000,  "t1": 150, "t2": 60},
    "olympic": {"swim": 1500, "bike": 40000,  "run": 10000, "t1": 180, "t2": 90},
    "703":     {"swim": 1900, "bike": 90000,  "run": 21097, "t1": 240, "t2": 120},
    "ironman": {"swim": 3800, "bike": 180000, "run": 42195, "t1": 300, "t2": 180},
}


class PreciseSplitsIn(BaseModel):
    race_key:            str   = "703"
    ftp_w:                float = 240.0
    css_sec_100m:         float = 110.0
    weight_kg:            float = 70.0
    run_threshold_s_km:   float = 300.0
    bike_if:              float = 0.80    # intensity factor efectivo (post-ajuste usuario)
    run_fraction:         float = 0.97    # % del ritmo umbral efectivo (post-ajuste usuario)
    bike_elevation_gain_m: float = 0.0
    bike_elevation_loss_m: Optional[float] = None   # si es None, se asume = gain (circuito neto cero)
    run_elevation_gain_m:  float = 0.0
    run_elevation_loss_m:  Optional[float] = None   # si es None, se asume = gain (circuito neto cero)
    wind_ms:              float = 0.0     # positivo = viento en contra
    altitude_m:           float = 0.0
    temperature_c:        float = 22.0
    surface:              str   = "asfalto"   # asfalto | trail | mixto
    cda:                  float = 0.32
    crr:                  float = 0.003

    @field_validator("race_key")
    @classmethod
    def _valid_race(cls, v: str) -> str:
        if v not in _SPLIT_DIST_M:
            raise ValueError(f"race_key inválido: {v}")
        return v

    @field_validator("surface")
    @classmethod
    def _valid_surface(cls, v: str) -> str:
        if v not in ("asfalto", "trail", "mixto"):
            raise ValueError(f"surface inválido: {v}")
        return v


@router.post("/precise-splits")
def precise_splits(
    body: PreciseSplitsIn,
    me:   User = Depends(require_feature("nutrition")),
):
    """
    Predicción de tiempos/gasto calórico con física real:
    - Bici: arrastre aerodinámico + rodadura + gravedad + viento (Newton-Raphson),
      densidad del aire ajustada por altitud/temperatura.
    - Run: costo metabólico Minetti (pendiente), penalización de altitud (VO2max),
      factor de superficie, factor de temperatura, fatiga post-bici.
    Reemplaza el modelo simple (cancha plana, sin viento) usado por defecto.
    """
    d = _SPLIT_DIST_M[body.race_key]
    bike_gain = body.bike_elevation_gain_m
    bike_loss = body.bike_elevation_loss_m if body.bike_elevation_loss_m is not None else body.bike_elevation_gain_m
    run_gain  = body.run_elevation_gain_m
    run_loss  = body.run_elevation_loss_m if body.run_elevation_loss_m is not None else body.run_elevation_gain_m

    bike_params = BikePhysicsParams(
        weight_kg=body.weight_kg, ftp_w=body.ftp_w, cda=body.cda, crr=body.crr,
        distance_km=d["bike"] / 1000.0,
        elevation_gain_m=bike_gain, elevation_loss_m=bike_loss,
        altitude_m=body.altitude_m, temperature_c=body.temperature_c, wind_ms=body.wind_ms,
        if_factor=body.bike_if,
    )
    bike_result = predict_bike(bike_params)

    run_params = RunPhysicsParams(
        threshold_pace_s_km=body.run_threshold_s_km, weight_kg=body.weight_kg,
        distance_km=d["run"] / 1000.0,
        elevation_gain_m=run_gain, elevation_loss_m=run_loss, surface=body.surface,
        altitude_m=body.altitude_m, temperature_c=body.temperature_c,
        race_fraction=body.run_fraction, bike_if=body.bike_if,
    )
    run_result = predict_run(run_params)

    swim_sec = (d["swim"] / 100.0) * body.css_sec_100m
    t1_sec, t2_sec = d["t1"], d["t2"]
    total_sec = swim_sec + t1_sec + bike_result["time_s"] + t2_sec + run_result["time_s"]

    swim_kcal = 8.0 * body.weight_kg * (swim_sec / 3600.0)
    bike_kcal = (bike_result["avg_power_w"] * bike_result["time_s"]) / (0.23 * 4184)
    run_kcal  = body.weight_kg * (d["run"] / 1000.0) * 1.04 * run_result["factors"]["elevation"]

    return {
        "race_key":   body.race_key,
        "swim":  {"time_s": round(swim_sec), "kcal": round(swim_kcal)},
        "t1_s":  t1_sec,
        "bike":  {
            "time_s":       round(bike_result["time_s"]),
            "avg_power_w":  bike_result["avg_power_w"],
            "avg_speed_kmh": bike_result["avg_speed_kmh"],
            "kcal":         round(bike_kcal),
        },
        "t2_s":  t2_sec,
        "run":   {
            "time_s":             round(run_result["time_s"]),
            "effective_pace_s_km": round(run_result["effective_pace_s_km"], 1),
            "factors":            run_result["factors"],
            "kcal":               round(run_kcal),
        },
        "total_time_s": round(total_sec),
        "total_kcal":   round(swim_kcal + bike_kcal + run_kcal),
        "conditions": {
            "bike_elevation_gain_m": bike_gain, "bike_elevation_loss_m": bike_loss,
            "run_elevation_gain_m": run_gain, "run_elevation_loss_m": run_loss,
            "wind_ms": body.wind_ms, "altitude_m": body.altitude_m,
            "temperature_c": body.temperature_c, "surface": body.surface,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# DIET PLAN — dieta diaria personalizada según gasto calórico real de entrenamiento
# Estándar ISSN/IOC para atletas de resistencia. Usado por el ícono ℹ de
# "Calorías Quemadas — Últimas 8 Semanas" en nutrition.html (lx-info.js → showDietPlan).
# ─────────────────────────────────────────────────────────────────────────────

_MEAL_SPLIT = [
    ("Desayuno", 0.25), ("Snack AM", 0.10), ("Almuerzo", 0.30),
    ("Snack PM", 0.10), ("Cena", 0.25),
]
_MENU_EXAMPLES = {
    "Desayuno": [
        "Avena + plátano + 2 huevos + café",
        "Pan integral + palta + huevo + fruta",
        "Yogur griego + granola + frutos rojos + miel",
    ],
    "Snack AM": ["Fruta + puñado de nueces (~25g)", "Yogur natural + miel"],
    "Almuerzo": [
        "Arroz o quinoa + pollo/pescado + verduras salteadas + aceite de oliva",
        "Legumbres + arroz + ensalada + palta",
    ],
    "Snack PM": ["Batido de proteína + plátano", "Tostada integral + palta + huevo"],
    "Cena": [
        "Proteína magra + camote/papa + verduras al vapor",
        "Pescado + quinoa + ensalada",
    ],
}


def _activity_kcal(a: GarminActivity, weight_kg: float) -> float:
    if a.calories:
        return float(a.calories)
    dur_min = a.dur_min or 0
    sport = (a.sport or "").lower()
    if sport == "bike":
        power = a.avg_power or (weight_kg * 2.5)
        return (power * dur_min * 60) / (0.23 * 4184)
    if sport == "run":
        dist_km = a.dist_km or (dur_min * 0.17)
        return weight_kg * dist_km * 1.04
    if sport in ("swim", "pool_swimming", "open_water"):
        return 8.0 * weight_kg * (dur_min / 60.0)
    return 7.0 * weight_kg * (dur_min / 60.0)  # genérico (gym/otras)


@router.get("/diet-plan")
def diet_plan(
    db: Session = Depends(get_db),
    me: User    = Depends(require_feature("nutrition")),
):
    """
    Dieta diaria personalizada según estándar ISSN/IOC para atletas de resistencia:
    - BMR (Mifflin-St Jeor, promedio sexo-neutral) + gasto real de entrenamiento (Garmin, 14d)
    - CHO g/kg escalado por volumen de entrenamiento diario promedio (3-5/5-7/6-10/8-12 g/kg)
    - Proteína 1.6 g/kg (rango ISSN 1.4-2.0 para resistencia)
    - Grasa: resto de kcal, piso de seguridad 0.8 g/kg (función hormonal)
    - Distribuye en 5 comidas con ejemplos de menú concretos
    """
    weight = me.weight_kg or 70.0
    height = me.height_cm or 170
    age    = me.age or 35

    bmr = 10 * weight + 6.25 * height - 5 * age - 78  # promedio fórmulas H/M Mifflin-St Jeor

    days = 14
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    acts = db.query(GarminActivity).filter(
        GarminActivity.user_id == me.id, GarminActivity.date_iso >= cutoff
    ).all()
    total_kcal = sum(_activity_kcal(a, weight) for a in acts)
    total_min  = sum(a.dur_min or 0 for a in acts)
    avg_daily_train_kcal = total_kcal / days
    avg_daily_train_min  = total_min / days

    tdee = bmr * 1.3 + avg_daily_train_kcal  # 1.3 = NEAT/vida diaria fuera del entreno

    if avg_daily_train_min < 30:
        cho_per_kg, tier = 4.0, "Día liviano"
    elif avg_daily_train_min < 90:
        cho_per_kg, tier = 6.0, "Carga moderada"
    elif avg_daily_train_min < 180:
        cho_per_kg, tier = 8.0, "Carga alta"
    else:
        cho_per_kg, tier = 10.0, "Carga muy alta"

    protein_per_kg = 1.6
    cho_g       = round(weight * cho_per_kg)
    protein_g   = round(weight * protein_per_kg)
    cho_kcal    = cho_g * 4
    protein_kcal = protein_g * 4
    fat_floor_kcal = weight * 0.8 * 9
    fat_kcal    = max(tdee - cho_kcal - protein_kcal, fat_floor_kcal)
    fat_g       = round(fat_kcal / 9)
    total_kcal_target = round(cho_kcal + protein_kcal + fat_kcal)

    meals = []
    for name, pct in _MEAL_SPLIT:
        meals.append({
            "name": name, "pct": pct,
            "kcal": round(total_kcal_target * pct),
            "cho_g": round(cho_g * pct),
            "protein_g": round(protein_g * pct),
            "menu_examples": _MENU_EXAMPLES[name],
        })

    return {
        "weight_kg": weight,
        "bmr": round(bmr),
        "tdee": round(tdee),
        "avg_daily_train_kcal": round(avg_daily_train_kcal),
        "avg_daily_train_min": round(avg_daily_train_min),
        "days_analyzed": days,
        "activities_analyzed": len(acts),
        "tier": tier,
        "targets": {
            "kcal": total_kcal_target,
            "cho_g": cho_g, "cho_per_kg": cho_per_kg,
            "protein_g": protein_g, "protein_per_kg": protein_per_kg,
            "fat_g": fat_g,
        },
        "meals": meals,
        "standard_note": "Guías ISSN (Kerksick et al. 2018) / IOC Consensus 2010 para atletas de resistencia: "
                          "3–5 g/kg CHO días livianos hasta 8–12 g/kg en carga muy alta; proteína 1.4–2.0 g/kg; "
                          "grasa mínimo 0.8 g/kg para no comprometer función hormonal.",
    }
