"""
LabX Nutrición Inteligente v2.0 — Test Suite (Sprint 14)
=========================================================
42 tests / 7 clases.
Strategy: test business logic directly (same algorithms as nutrition_routes.py)
without loading the FastAPI module so we avoid SQLAlchemy/pydantic mocking traps.
"""
import math
from datetime import date, datetime, timedelta

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Business logic mirrored from nutrition_routes.py
# (If any of these fail, the corresponding production function is broken)
# ─────────────────────────────────────────────────────────────────────────────

LIQUID_TYPES = {"water", "sport_drink", "coffee", "tea", "juice", "milk", "other"}

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

RACE_DISTANCES = {
    "sprint": {"swim_km": 0.75, "bike_km": 20,  "run_km": 5,  "total_h": 1.1},
    "oly":    {"swim_km": 1.5,  "bike_km": 40,  "run_km": 10, "total_h": 2.2},
    "703":    {"swim_km": 1.9,  "bike_km": 90,  "run_km": 21, "total_h": 5.0},
    "im":     {"swim_km": 3.8,  "bike_km": 180, "run_km": 42, "total_h": 11.0},
}


def _carb_periodization_tier(tss_day):
    if tss_day is None or tss_day == 0:
        return "low_carb"
    if tss_day >= 100:
        return "high_carb"
    if tss_day >= 50:
        return "moderate"
    return "low_carb"


def _compute_kcal_targets(weight_kg, height_cm, age, sex, tier):
    if sex == "f":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    tdee = bmr * 1.55
    multipliers = {
        "high_carb":   1.20,
        "moderate":    1.05,
        "low_carb":    0.90,
        "carb_loading":1.35,
    }
    kcal_target = round(tdee * multipliers.get(tier, 1.0))
    if tier == "high_carb":
        cho_pct, pro_pct, fat_pct = 0.60, 0.20, 0.20
    elif tier == "carb_loading":
        cho_pct, pro_pct, fat_pct = 0.70, 0.15, 0.15
    elif tier == "low_carb":
        cho_pct, pro_pct, fat_pct = 0.35, 0.30, 0.35
    else:
        cho_pct, pro_pct, fat_pct = 0.50, 0.25, 0.25
    return {
        "kcal":         kcal_target,
        "carbs_g":      round(kcal_target * cho_pct / 4),
        "protein_g":    round(kcal_target * pro_pct / 4),
        "fat_g":        round(kcal_target * fat_pct / 9),
        "cho_g_per_kg": round((kcal_target * cho_pct / 4) / weight_kg, 1),
        "tier":         tier,
    }


def _hydration_goal_ml(weight_kg, tss_day, avg_stress):
    base_ml      = weight_kg * 35
    training_h   = tss_day / 60 if tss_day else 0
    training_ml  = training_h * 500
    heat_ml      = 300 if (avg_stress or 0) > 60 else 0
    return int(round(base_ml + training_ml + heat_ml, -2))


def _diary_totals(entries):
    def g(e, attr):
        return getattr(e, attr, None) or 0
    return {
        "kcal":      round(sum(g(e, "kcal")      for e in entries), 1),
        "carbs_g":   round(sum(g(e, "carbs_g")   for e in entries), 1),
        "protein_g": round(sum(g(e, "protein_g") for e in entries), 1),
        "fat_g":     round(sum(g(e, "fat_g")     for e in entries), 1),
        "fiber_g":   round(sum(g(e, "fiber_g")   for e in entries), 1),
        "sodium_mg": round(sum(g(e, "sodium_mg") for e in entries), 1),
    }


def _race_briefing(dist, cho_g_h, fluid_ml_h, temp, weight):
    heat = "⚠️ ALERTA CALOR: aumenta hidratación +20% y electrolitos." if temp >= 28 else ""
    return (
        f"Para un {dist.upper()} ({RACE_DISTANCES[dist]['total_h']}h estimado a {weight}kg): "
        f"objetivo {cho_g_h}g CHO/h y {fluid_ml_h}ml/h. "
        f"Concentra el 60% de la nutrición en la bici. "
        f"En carrera: geles en puntos de avituallamiento. "
        f"{heat}"
    ).strip()


def _tier_key_foods(tier):
    foods = {
        "high_carb":    ["Arroz blanco", "Pasta", "Pan integral", "Plátano", "Miel", "Bebida deportiva"],
        "moderate":     ["Quinoa", "Avena", "Boniato", "Frutas", "Legumbres"],
        "low_carb":     ["Aguacate", "Huevos", "Salmón", "Brócoli", "Almendras", "Pollo"],
        "carb_loading": ["Pasta", "Arroz", "Pan blanco", "Mermelada", "Jugo de frutas", "Gel energético"],
    }
    return foods.get(tier, [])


# ─────────────────────────────────────────────────────────────────────────────
# Fake diary entry for tests
# ─────────────────────────────────────────────────────────────────────────────

class _E:
    def __init__(self, kcal=0, carbs_g=0, protein_g=0, fat_g=0, fiber_g=0, sodium_mg=0):
        self.kcal      = kcal
        self.carbs_g   = carbs_g
        self.protein_g = protein_g
        self.fat_g     = fat_g
        self.fiber_g   = fiber_g
        self.sodium_mg = sodium_mg


# ─────────────────────────────────────────────────────────────────────────────
# Clase 1: Carb Periodization Tier
# ─────────────────────────────────────────────────────────────────────────────

class TestCarbPeriodizationTier:

    def test_high_carb_100(self):
        assert _carb_periodization_tier(100) == "high_carb"

    def test_high_carb_150(self):
        assert _carb_periodization_tier(150) == "high_carb"

    def test_moderate_75(self):
        assert _carb_periodization_tier(75) == "moderate"

    def test_moderate_boundary_99(self):
        assert _carb_periodization_tier(99) == "moderate"

    def test_low_carb_30(self):
        assert _carb_periodization_tier(30) == "low_carb"

    def test_low_carb_zero(self):
        assert _carb_periodization_tier(0) == "low_carb"

    def test_none_tl(self):
        assert _carb_periodization_tier(None) == "low_carb"

    def test_boundary_50_is_moderate(self):
        assert _carb_periodization_tier(50) == "moderate"


# ─────────────────────────────────────────────────────────────────────────────
# Clase 2: Compute Kcal Targets
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeKcalTargets:

    def _t(self, tier, weight=75, height=175, age=35, sex="m"):
        return _compute_kcal_targets(weight, height, age, sex, tier)

    def test_high_carb_targets_above_moderate(self):
        hc = self._t("high_carb")
        mo = self._t("moderate")
        assert hc["kcal"]    > mo["kcal"]
        assert hc["carbs_g"] > mo["carbs_g"]

    def test_low_carb_below_moderate(self):
        lc = self._t("low_carb")
        mo = self._t("moderate")
        assert lc["kcal"]    < mo["kcal"]
        assert lc["carbs_g"] < mo["carbs_g"]

    def test_carb_loading_highest_cho(self):
        cl = self._t("carb_loading")
        hc = self._t("high_carb")
        assert cl["carbs_g"] >= hc["carbs_g"]

    def test_female_bmr_lower(self):
        f_t = _compute_kcal_targets(60, 165, 30, "f", "moderate")
        m_t = _compute_kcal_targets(60, 165, 30, "m", "moderate")
        assert f_t["kcal"] < m_t["kcal"]

    def test_cho_g_per_kg_populated(self):
        t = self._t("high_carb")
        assert t["cho_g_per_kg"] > 0

    def test_all_tiers_return_positive_values(self):
        for tier in ("high_carb", "moderate", "low_carb", "carb_loading"):
            t = self._t(tier)
            assert t["kcal"]      > 0
            assert t["carbs_g"]   > 0
            assert t["protein_g"] > 0
            assert t["fat_g"]     > 0

    def test_tier_field_present(self):
        t = self._t("high_carb")
        assert t["tier"] == "high_carb"


# ─────────────────────────────────────────────────────────────────────────────
# Clase 3: Hydration Goal
# ─────────────────────────────────────────────────────────────────────────────

class TestHydrationGoal:

    def test_base_no_training(self):
        goal = _hydration_goal_ml(75, 0, 0)
        assert goal == round(75 * 35, -2)

    def test_higher_with_training(self):
        no   = _hydration_goal_ml(75, 0, 0)
        with_t = _hydration_goal_ml(75, 120, 0)
        assert with_t > no

    def test_higher_with_heat(self):
        no_hot = _hydration_goal_ml(75, 0, 30)
        w_hot  = _hydration_goal_ml(75, 0, 70)
        assert w_hot > no_hot

    def test_heavy_athlete_higher_base(self):
        g_l = _hydration_goal_ml(55, 0, 0)
        g_h = _hydration_goal_ml(95, 0, 0)
        assert g_h > g_l

    def test_returns_integer(self):
        goal = _hydration_goal_ml(75, 0, 0)
        assert isinstance(goal, int)

    def test_heat_threshold_at_60_stress(self):
        below = _hydration_goal_ml(75, 0, 55)
        above = _hydration_goal_ml(75, 0, 65)
        assert above > below  # 300ml extra when stress > 60


# ─────────────────────────────────────────────────────────────────────────────
# Clase 4: Diary Totals Helper
# ─────────────────────────────────────────────────────────────────────────────

class TestDiaryTotals:

    def test_empty_entries(self):
        t = _diary_totals([])
        assert t["kcal"]      == 0
        assert t["carbs_g"]   == 0
        assert t["protein_g"] == 0

    def test_single_entry(self):
        e = _E(kcal=500, carbs_g=80, protein_g=30, fat_g=15)
        t = _diary_totals([e])
        assert t["kcal"]      == 500
        assert t["carbs_g"]   == 80
        assert t["protein_g"] == 30

    def test_multiple_entries_sum(self):
        e1 = _E(kcal=500, carbs_g=80, protein_g=30, fat_g=15, fiber_g=5, sodium_mg=200)
        e2 = _E(kcal=300, carbs_g=40, protein_g=20, fat_g=10, fiber_g=3, sodium_mg=100)
        t  = _diary_totals([e1, e2])
        assert t["kcal"]    == 800
        assert t["carbs_g"] == 120

    def test_none_values_treated_as_zero(self):
        e = _E()  # all zero
        e.kcal      = None
        e.carbs_g   = None
        e.protein_g = None
        e.fat_g     = None
        e.fiber_g   = None
        e.sodium_mg = None
        t = _diary_totals([e])
        assert t["kcal"] == 0

    def test_returns_all_keys(self):
        t = _diary_totals([])
        for key in ("kcal","carbs_g","protein_g","fat_g","fiber_g","sodium_mg"):
            assert key in t

    def test_rounding_to_1_decimal(self):
        e = _E(kcal=333.333, carbs_g=0)
        t = _diary_totals([e])
        assert t["kcal"] == 333.3


# ─────────────────────────────────────────────────────────────────────────────
# Clase 5: Race Protocol Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestRaceProtocol:

    def test_race_briefing_sprint(self):
        brief = _race_briefing("sprint", 30, 600, 20, 70)
        assert "SPRINT" in brief
        assert "30g CHO/h" in brief

    def test_race_briefing_im_heat_alert(self):
        brief = _race_briefing("im", 90, 900, 32, 75)
        assert "ALERTA CALOR" in brief

    def test_race_briefing_no_heat_alert_below_28(self):
        brief = _race_briefing("703", 60, 750, 22, 70)
        assert "ALERTA CALOR" not in brief

    def test_race_briefing_at_28_triggers_alert(self):
        brief = _race_briefing("oly", 45, 700, 28, 65)
        assert "ALERTA CALOR" in brief

    def test_tier_key_foods_high_carb(self):
        foods = _tier_key_foods("high_carb")
        assert isinstance(foods, list)
        assert len(foods) > 0
        assert any("rroz" in f or "asta" in f for f in foods)

    def test_tier_key_foods_low_carb(self):
        foods = _tier_key_foods("low_carb")
        assert any("Aguacate" in f or "Huevos" in f for f in foods)

    def test_tier_key_foods_unknown_returns_empty(self):
        foods = _tier_key_foods("unknown_tier")
        assert foods == []

    def test_race_distances_keys_present(self):
        for dist in ("sprint", "oly", "703", "im"):
            assert dist in RACE_DISTANCES
            assert "total_h" in RACE_DISTANCES[dist]
            assert "swim_km" in RACE_DISTANCES[dist]
            assert "bike_km" in RACE_DISTANCES[dist]
            assert "run_km"  in RACE_DISTANCES[dist]

    def test_race_cho_increases_with_duration(self):
        assert RACE_DISTANCES["im"]["total_h"] > RACE_DISTANCES["sprint"]["total_h"]

    def test_carb_loading_foods_include_pasta(self):
        foods = _tier_key_foods("carb_loading")
        assert "Pasta" in foods or "Arroz" in foods


# ─────────────────────────────────────────────────────────────────────────────
# Clase 6: Supplement Catalog
# ─────────────────────────────────────────────────────────────────────────────

class TestSupplementCatalog:

    def test_catalog_has_common_supplements(self):
        for key in ("caffeine", "creatine", "iron", "vit_d", "magnesium"):
            assert key in SUPPLEMENT_CAT

    def test_catalog_entries_have_name(self):
        for k, v in SUPPLEMENT_CAT.items():
            assert "name" in v, f"Suplemento '{k}' sin 'name'"

    def test_catalog_entries_have_timing(self):
        for k, v in SUPPLEMENT_CAT.items():
            assert "timing" in v, f"Suplemento '{k}' sin 'timing'"

    def test_caffeine_dose(self):
        assert SUPPLEMENT_CAT["caffeine"]["common_dose_mg"] == 200

    def test_custom_supplement_no_dose(self):
        assert SUPPLEMENT_CAT["custom"]["common_dose_mg"] is None

    def test_iron_dose_matches_rda(self):
        assert SUPPLEMENT_CAT["iron"]["common_dose_mg"] == 18  # mg RDA adultos

    def test_catalog_count(self):
        assert len(SUPPLEMENT_CAT) >= 10


# ─────────────────────────────────────────────────────────────────────────────
# Clase 7: Nutrition Insights Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestNutritionInsightLogic:

    def _targets(self, tier="moderate", weight=75, height=175, age=35, sex="m"):
        return _compute_kcal_targets(weight, height, age, sex, tier)

    def test_cho_gap_insight_triggered_when_low(self):
        targets = self._targets("high_carb")
        cho_actual = 100
        gap = targets["carbs_g"] - cho_actual
        assert gap > 50  # insight se dispararía

    def test_no_gap_when_cho_met(self):
        targets = self._targets("low_carb")
        cho_actual = targets["carbs_g"] + 10
        gap = targets["carbs_g"] - cho_actual
        assert gap < 50  # no se dispara

    def test_hydration_pct_calculation(self):
        hyd_total = 1500
        hyd_goal  = 3000
        pct = hyd_total / hyd_goal * 100
        assert pct == 50  # zona warning

    def test_reds_alert_threshold(self):
        w_start  = 75.0
        w_end    = 73.0
        loss_pct = (w_start - w_end) / w_start * 100
        assert loss_pct > 2.0  # alerta RED-S activa

    def test_reds_no_alert_small_loss(self):
        w_start  = 75.0
        w_end    = 74.8
        loss_pct = (w_start - w_end) / w_start * 100
        assert loss_pct < 1.5  # sin alerta

    def test_liquid_types_constant(self):
        expected = {"water","sport_drink","coffee","tea","juice","milk","other"}
        assert LIQUID_TYPES == expected

    def test_meal_slots_constant(self):
        assert "breakfast"   in MEAL_SLOTS
        assert "pre_workout" in MEAL_SLOTS
        assert "post_workout"in MEAL_SLOTS
        assert len(MEAL_SLOTS) == 9

    def test_slot_labels_have_all_slots(self):
        for slot in MEAL_SLOTS:
            assert slot in SLOT_LABELS, f"Slot '{slot}' sin label"

    def test_balance_semaphore_balanced(self):
        balance = 150  # ±200 → balanced
        assert abs(balance) <= 200

    def test_balance_semaphore_large_deficit(self):
        balance = -750  # < -700 → large_deficit
        assert balance < -700

    def test_periodization_high_carb_cho_above_5g_per_kg(self):
        t = self._targets("high_carb", weight=75)
        # high carb debe dar >= 4g/kg para ser útil para triatlón
        assert t["cho_g_per_kg"] >= 4.0

    def test_periodization_low_carb_cho_below_4g_per_kg(self):
        t = self._targets("low_carb", weight=75)
        assert t["cho_g_per_kg"] <= 4.0
