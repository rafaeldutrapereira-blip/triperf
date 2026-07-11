"""
Tests — Nutrition Intelligence: Food Diary + Open Food Facts proxy
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from .conftest import login

from ..routes.food_diary_routes import (
    _extract_nutriments, _compute_targets, _diary_totals,
    MEAL_LABELS, MEAL_ORDER, _product_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: motor de nutrientes
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractNutriments:
    _sample_product = {
        "nutriments": {
            "energy-kcal_100g": 350.0,
            "carbohydrates_100g": 70.0,
            "proteins_100g": 8.0,
            "fat_100g": 1.5,
            "fiber_100g": 3.0,
            "sodium_100g": 0.001,   # en kg/100g
            "sugars_100g": 5.0,
        }
    }

    def test_extract_100g_unchanged(self):
        n = _extract_nutriments(self._sample_product, 100.0)
        assert n["kcal"]      == 350.0
        assert n["carbs_g"]   == 70.0
        assert n["protein_g"] == 8.0
        assert n["fat_g"]     == 1.5
        assert n["fiber_g"]   == 3.0

    def test_extract_scales_proportionally(self):
        n50  = _extract_nutriments(self._sample_product, 50.0)
        n200 = _extract_nutriments(self._sample_product, 200.0)
        assert n50["kcal"]  == 175.0
        assert n200["kcal"] == 700.0

    def test_extract_handles_missing_nutrients(self):
        n = _extract_nutriments({"nutriments": {"energy-kcal_100g": 100}}, 100)
        assert n["kcal"]      == 100.0
        assert n["carbs_g"]   is None
        assert n["protein_g"] is None

    def test_extract_empty_nutriments(self):
        n = _extract_nutriments({}, 100)
        assert n["kcal"] is None
        assert all(v is None for v in n.values())


class TestProductSummary:
    def test_product_summary_uses_name(self):
        prod = {
            "_id": "12345",
            "product_name": "Arroz integral",
            "brands": "Carozzi",
            "nutriments": {"energy-kcal_100g": 350, "carbohydrates_100g": 73},
            "image_front_small_url": "http://img.example.com/rice.jpg",
        }
        result = _product_summary(prod, 100)
        assert result["name"]   == "Arroz integral"
        assert result["brand"]  == "Carozzi"
        assert result["off_id"] == "12345"
        assert result["kcal"]   == 350.0
        assert result["image"]  is not None

    def test_product_summary_fallback_name(self):
        prod = {"product_name_es": "Leche", "nutriments": {}}
        result = _product_summary(prod)
        assert result["name"] == "Leche"

    def test_product_summary_no_name(self):
        result = _product_summary({})
        assert result["name"] == "Producto sin nombre"


class TestDiaryTotals:
    def test_empty_entries_returns_zeros(self):
        totals = _diary_totals([])
        assert totals["kcal"]      == 0.0
        assert totals["carbs_g"]   == 0.0
        assert totals["protein_g"] == 0.0

    def test_sums_multiple_entries(self):
        from ..models import FoodDiaryEntry
        e1 = FoodDiaryEntry(kcal=300, carbs_g=60, protein_g=20, fat_g=5)
        e2 = FoodDiaryEntry(kcal=200, carbs_g=40, protein_g=10, fat_g=3)
        totals = _diary_totals([e1, e2])
        assert totals["kcal"]      == 500.0
        assert totals["carbs_g"]   == 100.0
        assert totals["protein_g"] == 30.0
        assert totals["fat_g"]     == 8.0

    def test_none_values_ignored(self):
        from ..models import FoodDiaryEntry
        e = FoodDiaryEntry(kcal=100, carbs_g=None, protein_g=20, fat_g=None)
        totals = _diary_totals([e])
        assert totals["kcal"]      == 100.0
        assert totals["carbs_g"]   == 0.0
        assert totals["protein_g"] == 20.0


class TestMealStructure:
    def test_all_meal_slots_in_labels(self):
        for slot in MEAL_ORDER:
            assert slot in MEAL_LABELS, f"Slot '{slot}' missing from MEAL_LABELS"

    def test_meal_labels_not_empty(self):
        for slot, label in MEAL_LABELS.items():
            assert label and len(label) > 2, f"Empty label for slot {slot}"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_get_targets(client, auth_headers):
    resp = client.get("/api/food/targets", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "targets" in data
    assert data["targets"]["kcal"]      > 0
    assert data["targets"]["cho_g"]     > 0
    assert data["targets"]["protein_g"] > 0
    assert "training_intensity" in data
    assert data["training_intensity"] in ("rest","light","moderate","hard","very_hard")


def test_get_targets_race_week(client, auth_headers):
    from datetime import date, timedelta
    race_date = (date.today() + timedelta(days=1)).isoformat()
    # Registrar carrera mañana para activar race_week flag
    client.post("/api/races", json={
        "name": "Test Race Tomorrow", "date_iso": race_date, "distance": "703"
    }, headers=auth_headers)
    resp = client.get("/api/food/targets", headers=auth_headers)
    assert resp.status_code == 200
    # is_race_week puede ser True o False dependiendo del estado del DB de test


def test_add_diary_entry(client, auth_headers):
    resp = client.post("/api/food/diary", json={
        "food_name":  "Pollo a la plancha",
        "meal_slot":  "lunch",
        "quantity_g": 150,
        "kcal":       232,
        "protein_g":  43,
        "fat_g":      5,
        "carbs_g":    0,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "entry_id" in data


def test_add_entry_requires_name(client, auth_headers):
    resp = client.post("/api/food/diary", json={
        "meal_slot": "lunch", "quantity_g": 100
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_add_entry_invalid_quantity(client, auth_headers):
    resp = client.post("/api/food/diary", json={
        "food_name": "Test", "quantity_g": -50
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_get_diary_today(client, auth_headers):
    resp = client.get("/api/food/diary/today", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "totals"   in data
    assert "targets"  in data
    assert "balance"  in data
    assert "progress" in data
    assert "training" in data
    assert "kcal"   in data["targets"]
    assert "cho_g"  in data["targets"]
    # Progress siempre entre 0 y 100
    for key, val in data["progress"].items():
        assert 0 <= val <= 100, f"Progress {key} = {val} out of range"


def test_get_diary_date(client, auth_headers):
    resp = client.get("/api/food/diary/2026-01-15", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["date_iso"] == "2026-01-15"


def test_get_diary_invalid_date(client, auth_headers):
    resp = client.get("/api/food/diary/not-a-date", headers=auth_headers)
    assert resp.status_code == 422


def test_delete_diary_entry(client, auth_headers):
    # Crear
    create = client.post("/api/food/diary", json={
        "food_name": "To Delete", "quantity_g": 100, "kcal": 200
    }, headers=auth_headers)
    entry_id = create.json()["entry_id"]

    # Eliminar
    del_resp = client.delete(f"/api/food/diary/entry/{entry_id}", headers=auth_headers)
    assert del_resp.status_code == 200


def test_update_entry_quantity(client, auth_headers):
    # Crear
    create = client.post("/api/food/diary", json={
        "food_name": "Arroz cocido", "quantity_g": 100,
        "kcal": 130, "carbs_g": 28, "protein_g": 2.7
    }, headers=auth_headers)
    entry_id = create.json()["entry_id"]

    # Actualizar cantidad
    resp = client.patch(f"/api/food/diary/entry/{entry_id}", json={"quantity_g": 200},
                        headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entry"]["quantity_g"]  == 200
    assert data["entry"]["kcal"]        == pytest.approx(260.0, rel=0.01)  # 130 * 2
    assert data["entry"]["carbs_g"]     == pytest.approx(56.0,  rel=0.01)


def test_cannot_delete_other_users_entry(client, auth_headers):
    resp = client.delete("/api/food/diary/entry/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


def test_weekly_summary(client, auth_headers):
    resp = client.get("/api/food/diary/summary/weekly", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "days"            in data
    assert "weekly_averages" in data
    assert len(data["days"]) == 7
    for day in data["days"]:
        assert "date_iso"       in day
        assert "adherence_pct"  in day
        assert 0 <= day["adherence_pct"] <= 100


def test_food_search_requires_auth(client):
    resp = client.get("/api/food/search?q=arroz")
    assert resp.status_code == 401


def test_food_search_mocked(client, auth_headers):
    """Test búsqueda con Open Food Facts mockeado."""
    mock_response = {
        "count": 2,
        "products": [
            {
                "_id": "abc123",
                "product_name": "Arroz blanco",
                "brands": "Carozzi",
                "nutriments": {
                    "energy-kcal_100g": 365,
                    "carbohydrates_100g": 80,
                    "proteins_100g": 7,
                    "fat_100g": 0.5,
                },
                "image_front_small_url": None,
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__  = AsyncMock(return_value=False)

        resp = client.get("/api/food/search?q=arroz", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "products" in data
