"""
LabX Nutrition Intelligence
============================
Diario alimentario diario con integración Open Food Facts.

Endpoints:
  GET    /food/search                  — Búsqueda en Open Food Facts (proxy)
  GET    /food/product/{barcode}       — Producto por código de barras
  POST   /food/diary                   — Agregar entrada al diario
  GET    /food/diary/today             — Diario de hoy + targets dinámicos
  GET    /food/diary/{date}            — Diario de fecha específica
  DELETE /food/diary/entry/{id}        — Eliminar entrada
  PATCH  /food/diary/entry/{id}        — Actualizar cantidad
  GET    /food/diary/summary           — Resumen semanal de macros
  GET    /food/targets                 — Targets diarios según TSB/carga

Targets dinámicos (diferenciador vs competidores):
  - Día de entrenamiento intenso (ATL↑): CHO +20%, proteína +10%
  - Día de descanso / recuperación:       CHO -20%, grasa +10%
  - 48h antes de carrera:                 CHO +35% (carga)
  - Post-carrera (24h):                   Proteína +25%, CHO +15%
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    FoodDiaryEntry, GarminHealthDaily, GarminTrainingLoad, RaceEvent, User,
)
from ..auth import get_current_user

logger = logging.getLogger("labx.food_diary")
router = APIRouter(prefix="/food", tags=["nutrition_diary"])

# ─────────────────────────────────────────────────────────────────────────────
# Cache simple en memoria (en prod usar Redis)
# ─────────────────────────────────────────────────────────────────────────────

_OFF_CACHE: dict[str, tuple[float, object]] = {}   # key → (timestamp, data)
_CACHE_TTL = 3600 * 6  # 6 horas

OFF_BASE = "https://world.openfoodfacts.org"


def _cache_get(key: str):
    entry = _OFF_CACHE.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, data):
    _OFF_CACHE[key] = (time.time(), data)
    # Limpieza si cache crece demasiado
    if len(_OFF_CACHE) > 500:
        oldest = sorted(_OFF_CACHE.items(), key=lambda x: x[1][0])[:100]
        for k, _ in oldest:
            del _OFF_CACHE[k]


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de nutrientes desde Open Food Facts
# ─────────────────────────────────────────────────────────────────────────────

def _extract_nutriments(prod: dict, quantity_g: float = 100.0) -> dict:
    """
    Extrae macros de un producto Open Food Facts y los escala a quantity_g.
    Open Food Facts reporta valores por 100g en nutriments.
    """
    n   = prod.get("nutriments", {})
    qty = quantity_g / 100.0

    def _v(key: str) -> Optional[float]:
        v = n.get(key + "_100g") or n.get(key)
        return round(float(v) * qty, 1) if v is not None else None

    return {
        "kcal":       _v("energy-kcal"),
        "carbs_g":    _v("carbohydrates"),
        "protein_g":  _v("proteins"),
        "fat_g":      _v("fat"),
        "fiber_g":    _v("fiber"),
        "sodium_mg":  round((_v("sodium") or 0) * 1000, 1) if _v("sodium") else None,
        "sugar_g":    _v("sugars"),
    }


def _product_summary(prod: dict, quantity_g: float = 100.0) -> dict:
    """Convierte un producto OFF a formato LabX."""
    nutrients = _extract_nutriments(prod, quantity_g)
    return {
        "off_id":   prod.get("_id") or prod.get("id") or prod.get("code"),
        "name":     prod.get("product_name") or prod.get("product_name_es") or prod.get("product_name_pt") or "Producto sin nombre",
        "brand":    prod.get("brands", "").split(",")[0].strip() or None,
        "image":    prod.get("image_front_small_url") or prod.get("image_url"),
        "quantity_g": quantity_g,
        **nutrients,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de targets diarios según carga de entrenamiento
# ─────────────────────────────────────────────────────────────────────────────

def _compute_targets(user: User, db: Session, target_date: str = None) -> dict:
    """
    Calcula los targets nutricionales para una fecha específica.
    Usa el TSB/ATL del atleta y si hay carrera en 48h para ajustar CHO.
    """
    target_date = target_date or date.today().isoformat()
    weight = user.weight_kg or 70.0

    # Carga de entrenamiento más reciente
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == user.id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    ctl = round(load.ctl, 1) if load and load.ctl else 50.0
    atl = round(load.atl, 1) if load and load.atl else 50.0
    tsb = round(load.tsb, 1) if load and load.tsb else 0.0

    # Detectar fase de entrenamiento
    is_race_week = False
    is_post_race = False
    race_48h_name = None

    upcoming = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == user.id,
            RaceEvent.actual_total_sec.is_(None),
            RaceEvent.date_iso >= target_date,
            RaceEvent.date_iso <= (
                date.fromisoformat(target_date) + timedelta(days=3)
            ).isoformat(),
        )
        .first()
    )
    if upcoming:
        days_to = (date.fromisoformat(upcoming.date_iso) - date.fromisoformat(target_date)).days
        if days_to <= 2:
            is_race_week = True
            race_48h_name = upcoming.name

    recent_race = (
        db.query(RaceEvent)
        .filter(
            RaceEvent.user_id == user.id,
            RaceEvent.actual_total_sec.isnot(None),
            RaceEvent.date_iso >= (
                date.fromisoformat(target_date) - timedelta(days=2)
            ).isoformat(),
            RaceEvent.date_iso <= target_date,
        )
        .first()
    )
    if recent_race:
        is_post_race = True

    # Clasificar el día de entrenamiento por ATL
    training_intensity = "rest"  # rest | light | moderate | hard | very_hard
    if atl >= 100:
        training_intensity = "very_hard"
    elif atl >= 70:
        training_intensity = "hard"
    elif atl >= 40:
        training_intensity = "moderate"
    elif atl >= 20:
        training_intensity = "light"

    # Targets base (g/kg/día según intensidad)
    # Referencia: Burke et al., Sports Nutrition guidelines
    CHO_BASE = {
        "rest":      3.0,
        "light":     4.0,
        "moderate":  5.5,
        "hard":      7.0,
        "very_hard": 9.0,
    }
    PROTEIN_BASE = {
        "rest":      1.6,
        "light":     1.7,
        "moderate":  1.8,
        "hard":      2.0,
        "very_hard": 2.2,
    }
    FAT_BASE = 1.0  # g/kg, siempre estable

    cho_gkg     = CHO_BASE[training_intensity]
    protein_gkg = PROTEIN_BASE[training_intensity]
    fat_gkg     = FAT_BASE

    # Ajustes contextuales
    context_notes = []
    cho_mult = protein_mult = 1.0

    if is_race_week:
        cho_mult = 1.35          # carga de carbohidratos pre-carrera
        context_notes.append(f"🏁 Carga de carbohidratos — {race_48h_name} en <48h: +35% CHO")
    elif is_post_race:
        protein_mult = 1.25
        cho_mult     = 1.15
        context_notes.append("💪 Recuperación post-carrera: +25% proteína, +15% CHO")
    elif tsb < -15:
        protein_mult = 1.10      # mayor catabolismo muscular en sobreentrenamiento
        context_notes.append(f"⚠ TSB {tsb:+.0f}: Mayor síntesis proteica necesaria (+10% proteína)")
    elif tsb > 15 and training_intensity in ("rest", "light"):
        cho_mult = 0.80          # taper: menos CHO, no acumular peso
        context_notes.append(f"✓ TSB {tsb:+.0f} (taper): CHO reducido para evitar acumulación")

    cho_g     = round(cho_gkg     * cho_mult     * weight)
    protein_g = round(protein_gkg * protein_mult * weight)
    fat_g     = round(fat_gkg     * weight)
    kcal      = round(cho_g * 4 + protein_g * 4 + fat_g * 9)

    return {
        "date_iso":           target_date,
        "weight_kg":          weight,
        "training_intensity": training_intensity,
        "tsb":                tsb,
        "ctl":                ctl,
        "atl":                atl,
        "targets": {
            "kcal":      kcal,
            "cho_g":     cho_g,
            "protein_g": protein_g,
            "fat_g":     fat_g,
            "sodium_mg": 1500 + (int(atl) * 5),  # más sodio en días duros
        },
        "rationale": f"{training_intensity.replace('_', ' ').title()} training · {cho_gkg*cho_mult:.1f}g CHO/kg · {protein_gkg*protein_mult:.1f}g PRO/kg",
        "context_notes": context_notes,
        "is_race_week":  is_race_week,
        "is_post_race":  is_post_race,
    }


def _diary_totals(entries: list[FoodDiaryEntry]) -> dict:
    """Suma los macros de una lista de entradas."""
    totals = {"kcal": 0.0, "carbs_g": 0.0, "protein_g": 0.0, "fat_g": 0.0,
              "fiber_g": 0.0, "sodium_mg": 0.0, "sugar_g": 0.0}
    for e in entries:
        if e.kcal:     totals["kcal"]     += e.kcal
        if e.carbs_g:  totals["carbs_g"]  += e.carbs_g
        if e.protein_g:totals["protein_g"]+= e.protein_g
        if e.fat_g:    totals["fat_g"]    += e.fat_g
        if e.fiber_g:  totals["fiber_g"]  += e.fiber_g
        if e.sodium_mg:totals["sodium_mg"]+= e.sodium_mg
        if e.sugar_g:  totals["sugar_g"]  += e.sugar_g
    return {k: round(v, 1) for k, v in totals.items()}


MEAL_ORDER = [
    "breakfast", "morning_snack", "pre_workout",
    "lunch", "intra_workout", "afternoon_snack",
    "post_workout", "dinner", "other",
]

MEAL_LABELS = {
    "breakfast":       "Desayuno",
    "morning_snack":   "Media mañana",
    "pre_workout":     "Pre-entrenamiento",
    "lunch":           "Almuerzo",
    "intra_workout":   "Durante entreno",
    "afternoon_snack": "Merienda",
    "post_workout":    "Post-entrenamiento",
    "dinner":          "Cena",
    "other":           "Otros",
}


def _serialize_entry(e: FoodDiaryEntry) -> dict:
    return {
        "id":         e.id,
        "date_iso":   e.date_iso,
        "meal_slot":  e.meal_slot,
        "meal_label": MEAL_LABELS.get(e.meal_slot, e.meal_slot),
        "food_name":  e.food_name,
        "brand":      e.brand,
        "off_id":     e.off_id,
        "quantity_g": e.quantity_g,
        "kcal":       e.kcal,
        "carbs_g":    e.carbs_g,
        "protein_g":  e.protein_g,
        "fat_g":      e.fat_g,
        "fiber_g":    e.fiber_g,
        "sodium_mg":  e.sodium_mg,
        "sugar_g":    e.sugar_g,
        "notes":      e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_food(
    q:      str = Query(..., min_length=2, description="Nombre del alimento a buscar"),
    lang:   str = Query("es", description="Idioma (es/pt/en)"),
    page:   int = Query(1, ge=1, le=10),
    limit:  int = Query(20, ge=1, le=50),
    me:     User    = Depends(get_current_user),
):
    """
    Busca alimentos en Open Food Facts.
    Proxy del servidor para evitar CORS y agregar caché.
    Prioriza productos con datos nutricionales completos.
    """
    cache_key = f"search:{q}:{lang}:{page}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = f"{OFF_BASE}/cgi/search.pl"
    params = {
        "search_terms":      q,
        "search_simple":     1,
        "action":            "process",
        "json":              1,
        "page":              page,
        "page_size":         limit,
        "lc":                lang,
        "fields":            "product_name,product_name_es,product_name_pt,brands,nutriments,image_front_small_url,_id,code",
        "sort_by":           "unique_scans_n",   # más escaneados primero
        "nutrition_grades_tags": "",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "Open Food Facts tardó demasiado. Intenta de nuevo.")
    except Exception as e:
        logger.warning("OFF search error q=%s: %s", q, e)
        raise HTTPException(502, "Error al conectar con la base de datos de alimentos")

    products = data.get("products", [])

    # Filtrar y ordenar: priorizar los que tienen kcal/carbs completos
    def _has_nutrition(p: dict) -> bool:
        n = p.get("nutriments", {})
        return bool(n.get("energy-kcal_100g") or n.get("energy-kcal"))

    products_with_data = [p for p in products if _has_nutrition(p)]
    products_no_data   = [p for p in products if not _has_nutrition(p)]
    products_sorted    = products_with_data + products_no_data

    result = {
        "count":    data.get("count", 0),
        "page":     page,
        "query":    q,
        "products": [_product_summary(p) for p in products_sorted[:limit]],
    }
    _cache_set(cache_key, result)
    return result


@router.get("/product/{barcode}")
async def get_product_by_barcode(
    barcode: str,
    me: User = Depends(get_current_user),
):
    """Obtiene un producto por código de barras (EAN-13/EAN-8 o código OFF)."""
    cache_key = f"product:{barcode}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = f"{OFF_BASE}/api/v2/product/{barcode}"
    params = {"fields": "product_name,product_name_es,product_name_pt,brands,nutriments,image_front_small_url,_id,code"}

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("OFF product error barcode=%s: %s", barcode, e)
        raise HTTPException(404, "Producto no encontrado")

    if data.get("status") != 1 or not data.get("product"):
        raise HTTPException(404, "Producto no encontrado en Open Food Facts")

    result = _product_summary(data["product"])
    _cache_set(cache_key, result)
    return result


@router.post("/diary")
def add_diary_entry(
    body: dict,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Agrega un alimento al diario del día.

    Body:
      date_iso:   YYYY-MM-DD (default: hoy)
      meal_slot:  breakfast|lunch|dinner|... (default: other)
      food_name:  str (requerido)
      brand?:     str
      off_id?:    str (código Open Food Facts)
      quantity_g: float (default: 100)
      kcal, carbs_g, protein_g, fat_g, fiber_g, sodium_mg, sugar_g: float (opcional si off_id viene ya calculado)
    """
    food_name = (body.get("food_name") or "").strip()
    if not food_name:
        raise HTTPException(422, "food_name es requerido")

    quantity_g = float(body.get("quantity_g", 100.0))
    if quantity_g <= 0:
        raise HTTPException(422, "quantity_g debe ser positivo")
    if quantity_g > 5000:
        raise HTTPException(422, "quantity_g excede el máximo (5000g)")

    meal_slot = body.get("meal_slot", "other")
    if meal_slot not in MEAL_LABELS:
        meal_slot = "other"

    date_iso = (body.get("date_iso") or date.today().isoformat()).strip()

    entry = FoodDiaryEntry(
        user_id    = me.id,
        date_iso   = date_iso,
        meal_slot  = meal_slot,
        food_name  = food_name,
        brand      = (body.get("brand") or "").strip() or None,
        off_id     = (body.get("off_id") or "").strip() or None,
        quantity_g = quantity_g,
        kcal       = body.get("kcal"),
        carbs_g    = body.get("carbs_g"),
        protein_g  = body.get("protein_g"),
        fat_g      = body.get("fat_g"),
        fiber_g    = body.get("fiber_g"),
        sodium_mg  = body.get("sodium_mg"),
        sugar_g    = body.get("sugar_g"),
        notes      = (body.get("notes") or "").strip() or None,
    )
    db.add(entry)
    db.commit()

    return {"ok": True, "entry_id": entry.id}


@router.get("/targets")
def get_targets(
    date_iso: Optional[str] = Query(None, description="YYYY-MM-DD, default hoy"),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Retorna los targets nutricionales del día ajustados a la carga de entrenamiento."""
    return _compute_targets(me, db, date_iso)


@router.get("/diary/today")
def get_diary_today(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Retorna el diario de hoy completo: entradas por comida + totales + targets + balance.
    """
    today = date.today().isoformat()
    return _get_diary_for_date(today, me, db)


@router.get("/diary/{date_str}")
def get_diary_date(
    date_str: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Retorna el diario de una fecha específica."""
    try:
        date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(422, "Formato de fecha inválido. Use YYYY-MM-DD")
    return _get_diary_for_date(date_str, me, db)


def _get_diary_for_date(date_iso: str, me: User, db: Session) -> dict:
    entries = (
        db.query(FoodDiaryEntry)
        .filter(
            FoodDiaryEntry.user_id  == me.id,
            FoodDiaryEntry.date_iso == date_iso,
        )
        .order_by(FoodDiaryEntry.created_at)
        .all()
    )

    # Agrupar por meal_slot en orden lógico
    by_meal: dict[str, list] = {slot: [] for slot in MEAL_ORDER}
    for e in entries:
        slot = e.meal_slot if e.meal_slot in by_meal else "other"
        by_meal[slot].append(_serialize_entry(e))

    totals  = _diary_totals(entries)
    targets = _compute_targets(me, db, date_iso)

    # Balance vs targets
    tgt = targets["targets"]
    balance = {
        "kcal":      round(totals["kcal"]     - tgt["kcal"],      1),
        "cho_g":     round(totals["carbs_g"]  - tgt["cho_g"],     1),
        "protein_g": round(totals["protein_g"]- tgt["protein_g"], 1),
        "fat_g":     round(totals["fat_g"]    - tgt["fat_g"],     1),
    }
    progress = {
        "kcal_pct":    min(100, round(totals["kcal"]      / tgt["kcal"]      * 100)) if tgt["kcal"]      else 0,
        "cho_pct":     min(100, round(totals["carbs_g"]   / tgt["cho_g"]     * 100)) if tgt["cho_g"]     else 0,
        "protein_pct": min(100, round(totals["protein_g"] / tgt["protein_g"] * 100)) if tgt["protein_g"] else 0,
        "fat_pct":     min(100, round(totals["fat_g"]     / tgt["fat_g"]     * 100)) if tgt["fat_g"]     else 0,
    }

    # Garmin kcal quemadas hoy (si están disponibles)
    health = (
        db.query(GarminHealthDaily)
        .filter(
            GarminHealthDaily.user_id  == me.id,
            GarminHealthDaily.date_iso == date_iso,
        )
        .first()
    )
    garmin_burn = getattr(health, "active_kcal", None) or getattr(health, "calories_active", None)

    return {
        "date_iso":      date_iso,
        "entries_count": len(entries),
        "meals":         {slot: items for slot, items in by_meal.items() if items},
        "meal_order":    MEAL_ORDER,
        "meal_labels":   MEAL_LABELS,
        "totals":        totals,
        "targets":       tgt,
        "balance":       balance,
        "progress":      progress,
        "training":      {
            "intensity":  targets["training_intensity"],
            "rationale":  targets["rationale"],
            "notes":      targets["context_notes"],
        },
        "garmin_burn":   garmin_burn,
        "net_kcal":      round(totals["kcal"] - (garmin_burn or 0), 1) if garmin_burn else None,
    }


@router.patch("/diary/entry/{entry_id}")
def update_entry_quantity(
    entry_id: str,
    body:     dict,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    """Actualiza la cantidad (g) de una entrada y recalcula macros proporcionalmente."""
    entry = db.query(FoodDiaryEntry).filter(
        FoodDiaryEntry.id      == entry_id,
        FoodDiaryEntry.user_id == me.id,
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")

    new_qty = float(body.get("quantity_g", entry.quantity_g))
    if new_qty <= 0:
        raise HTTPException(422, "quantity_g debe ser positivo")

    if entry.quantity_g and entry.quantity_g > 0:
        ratio = new_qty / entry.quantity_g
        for field in ["kcal", "carbs_g", "protein_g", "fat_g", "fiber_g", "sodium_mg", "sugar_g"]:
            val = getattr(entry, field)
            if val is not None:
                setattr(entry, field, round(val * ratio, 1))

    entry.quantity_g = new_qty
    if "meal_slot" in body and body["meal_slot"] in MEAL_LABELS:
        entry.meal_slot = body["meal_slot"]
    if "notes" in body:
        entry.notes = (body["notes"] or "").strip() or None

    db.commit()
    return {"ok": True, "entry": _serialize_entry(entry)}


@router.delete("/diary/entry/{entry_id}")
def delete_entry(
    entry_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    entry = db.query(FoodDiaryEntry).filter(
        FoodDiaryEntry.id      == entry_id,
        FoodDiaryEntry.user_id == me.id,
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.get("/diary/summary/weekly")
def weekly_summary(
    end_date: Optional[str] = Query(None, description="Último día YYYY-MM-DD, default hoy"),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Resumen de los últimos 7 días: macros por día vs targets,
    adherencia y tendencias.
    """
    end   = date.fromisoformat(end_date) if end_date else date.today()
    start = end - timedelta(days=6)

    all_entries = (
        db.query(FoodDiaryEntry)
        .filter(
            FoodDiaryEntry.user_id  == me.id,
            FoodDiaryEntry.date_iso >= start.isoformat(),
            FoodDiaryEntry.date_iso <= end.isoformat(),
        )
        .all()
    )

    # Agrupar por fecha
    by_date: dict[str, list] = {}
    for e in all_entries:
        by_date.setdefault(e.date_iso, []).append(e)

    days_data = []
    total_adherence = 0
    logged_days = 0

    for i in range(7):
        d    = start + timedelta(days=i)
        d_iso = d.isoformat()
        entries = by_date.get(d_iso, [])
        totals  = _diary_totals(entries)
        targets = _compute_targets(me, db, d_iso)
        tgt     = targets["targets"]

        # Adherencia: % de kcal registradas vs target
        adherence = min(100, round(totals["kcal"] / tgt["kcal"] * 100)) if tgt["kcal"] and totals["kcal"] else 0

        if totals["kcal"] > 0:
            logged_days     += 1
            total_adherence += adherence

        days_data.append({
            "date_iso":   d_iso,
            "day_label":  ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][d.weekday()],
            "logged":     totals["kcal"] > 0,
            "kcal":       totals["kcal"],
            "cho_g":      totals["carbs_g"],
            "protein_g":  totals["protein_g"],
            "fat_g":      totals["fat_g"],
            "kcal_target":     tgt["kcal"],
            "cho_target":      tgt["cho_g"],
            "protein_target":  tgt["protein_g"],
            "fat_target":      tgt["fat_g"],
            "adherence_pct":   adherence,
            "intensity":       targets["training_intensity"],
        })

    avg_adherence = round(total_adherence / logged_days) if logged_days else 0

    # Promedios semanales
    week_totals = {
        "avg_kcal":      round(sum(d["kcal"]     for d in days_data) / 7, 1),
        "avg_cho_g":     round(sum(d["cho_g"]    for d in days_data) / 7, 1),
        "avg_protein_g": round(sum(d["protein_g"]for d in days_data) / 7, 1),
        "avg_fat_g":     round(sum(d["fat_g"]    for d in days_data) / 7, 1),
    }

    return {
        "start_date":     start.isoformat(),
        "end_date":       end.isoformat(),
        "logged_days":    logged_days,
        "avg_adherence":  avg_adherence,
        "days":           days_data,
        "weekly_averages":week_totals,
    }
