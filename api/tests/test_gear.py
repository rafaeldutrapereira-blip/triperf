"""
Tests — Gestión de Equipamiento y Mantenimiento (zapatillas, bicicletas,
componentes). Todo contra la BD real de test (SQLite in-memory) vía
TestClient real -- sin mocks de la capa de negocio.
"""
from .conftest import login, auth_headers

from ..models import CoachAthlete


def _auth(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return auth_headers(token)


# ─────────────────────────────────────────────────────────────────────────────
# Zapatillas
# ─────────────────────────────────────────────────────────────────────────────

class TestShoes:
    def test_create_shoe_defaults_target_km_by_type(self, client, athlete_user):
        h = _auth(client, athlete_user)
        r = client.post("/api/gear/shoes", json={"brand": "Hoka", "model": "Clifton 9", "shoe_type": "rodaje"}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["target_km"] == 700.0
        assert body["accumulated_km"] == 0.0
        assert body["life_pct"] == 0.0
        assert body["status"] == "active"

    def test_create_shoe_missing_brand_400(self, client, athlete_user):
        h = _auth(client, athlete_user)
        r = client.post("/api/gear/shoes", json={"model": "Clifton 9"}, headers=h)
        assert r.status_code == 400

    def test_create_shoe_invalid_type_400(self, client, athlete_user):
        h = _auth(client, athlete_user)
        r = client.post("/api/gear/shoes", json={"brand": "Hoka", "model": "X", "shoe_type": "no-existe"}, headers=h)
        assert r.status_code == 400

    def test_list_shoes_filters_by_status(self, client, athlete_user):
        h = _auth(client, athlete_user)
        create = client.post("/api/gear/shoes", json={"brand": "Asics", "model": "Nimbus"}, headers=h).json()
        client.delete(f"/api/gear/shoes/{create['id']}", headers=h)

        active = client.get("/api/gear/shoes?status=active", headers=h).json()["shoes"]
        retired = client.get("/api/gear/shoes?status=retired", headers=h).json()["shoes"]
        assert all(s["id"] != create["id"] for s in active)
        assert any(s["id"] == create["id"] for s in retired)
        assert retired[0]["status"] == "retired"

    def test_update_shoe_target_km(self, client, athlete_user):
        h = _auth(client, athlete_user)
        shoe = client.post("/api/gear/shoes", json={"brand": "Nike", "model": "Pegasus"}, headers=h).json()
        r = client.patch(f"/api/gear/shoes/{shoe['id']}", json={"target_km": 500.0, "nickname": "Rojas"}, headers=h)
        assert r.status_code == 200
        assert r.json()["target_km"] == 500.0

    def test_set_default_shoe_unassigns_previous_default(self, client, athlete_user):
        h = _auth(client, athlete_user)
        s1 = client.post("/api/gear/shoes", json={"brand": "A", "model": "1"}, headers=h).json()
        s2 = client.post("/api/gear/shoes", json={"brand": "B", "model": "2"}, headers=h).json()

        r1 = client.post(f"/api/gear/shoes/{s1['id']}/set-default", json={"workout_subtype": "rodaje"}, headers=h)
        assert r1.json()["default_for"] == ["rodaje"]

        r2 = client.post(f"/api/gear/shoes/{s2['id']}/set-default", json={"workout_subtype": "rodaje"}, headers=h)
        assert r2.json()["default_for"] == ["rodaje"]

        s1_after = client.get("/api/gear/shoes", headers=h).json()["shoes"]
        s1_reloaded = next(s for s in s1_after if s["id"] == s1["id"])
        assert s1_reloaded["default_for"] == []

    def test_cannot_access_other_users_shoe(self, client, athlete_user, coach_user):
        h_athlete = _auth(client, athlete_user)
        shoe = client.post("/api/gear/shoes", json={"brand": "A", "model": "1"}, headers=h_athlete).json()

        token_coach = login(client, "coach@test.com", "CoachPass123")
        h_coach = auth_headers(token_coach)
        r = client.patch(f"/api/gear/shoes/{shoe['id']}", json={"nickname": "hack"}, headers=h_coach)
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Bicicletas y componentes
# ─────────────────────────────────────────────────────────────────────────────

class TestBikesAndComponents:
    def test_create_bike_as_default_unmarks_previous_default(self, client, athlete_user):
        h = _auth(client, athlete_user)
        b1 = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad", "is_default": True}, headers=h).json()
        assert b1["is_default"] is True

        b2 = client.post("/api/gear/bikes", json={"brand": "Trek", "model": "Madone", "is_default": True}, headers=h).json()
        assert b2["is_default"] is True

        bikes = client.get("/api/gear/bikes", headers=h).json()["bikes"]
        b1_reloaded = next(b for b in bikes if b["id"] == b1["id"])
        assert b1_reloaded["is_default"] is False

    def test_create_bike_invalid_type_400(self, client, athlete_user):
        h = _auth(client, athlete_user)
        r = client.post("/api/gear/bikes", json={"brand": "X", "model": "Y", "bike_type": "avion"}, headers=h)
        assert r.status_code == 400

    def test_create_component_km_tracking(self, client, athlete_user):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        r = client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "cadena", "tracking_unit": "km", "target_value": 3000},
            headers=h,
        )
        assert r.status_code == 200, r.text
        comp = r.json()
        assert comp["life_pct"] == 0.0
        assert comp["accumulated_value"] == 0.0

    def test_create_battery_component_uses_charge_pct_not_life_pct(self, client, athlete_user):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        r = client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "bateria_grupo", "tracking_unit": "carga_pct", "target_value": 100, "charge_pct": 92},
            headers=h,
        )
        assert r.status_code == 200, r.text
        comp = r.json()
        assert comp["life_pct"] is None
        assert comp["charge_pct"] == 92

    def test_missing_target_value_400(self, client, athlete_user):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        r = client.post(f"/api/gear/bikes/{bike['id']}/components", json={"component_type": "cadena"}, headers=h)
        assert r.status_code == 400

    def test_component_appears_in_bike_out(self, client, athlete_user):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "cubiertas", "tracking_unit": "km", "target_value": 4000},
            headers=h,
        )
        bikes = client.get("/api/gear/bikes", headers=h).json()["bikes"]
        b = next(x for x in bikes if x["id"] == bike["id"])
        assert len(b["components"]) == 1
        assert b["components"][0]["component_type"] == "cubiertas"

    def test_replaced_component_not_listed_active(self, client, athlete_user):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        comp = client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "cadena", "tracking_unit": "km", "target_value": 3000},
            headers=h,
        ).json()
        client.delete(f"/api/gear/bikes/{bike['id']}/components/{comp['id']}", headers=h)

        bikes = client.get("/api/gear/bikes", headers=h).json()["bikes"]
        b = next(x for x in bikes if x["id"] == bike["id"])
        assert len(b["components"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Mantenimiento (service log)
# ─────────────────────────────────────────────────────────────────────────────

class TestMaintenanceLog:
    def test_service_with_reset_zeroes_accumulated(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        comp = client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "cadena", "tracking_unit": "km", "target_value": 3000},
            headers=h,
        ).json()

        from ..models import BikeComponent
        row = db.query(BikeComponent).filter(BikeComponent.id == comp["id"]).first()
        row.accumulated_value = 2850.0
        db.commit()

        r = client.post(
            f"/api/gear/bikes/{bike['id']}/components/{comp['id']}/service",
            json={"description": "Cambio de cadena por desgaste", "resets_accumulated": True, "cost": 35000},
            headers=h,
        )
        assert r.status_code == 200, r.text

        bikes = client.get("/api/gear/bikes", headers=h).json()["bikes"]
        b = next(x for x in bikes if x["id"] == bike["id"])
        comp_after = next(c for c in b["components"] if c["id"] == comp["id"])
        assert comp_after["accumulated_value"] == 0.0

    def test_service_without_reset_keeps_accumulated(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        comp = client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "pastillas_freno", "tracking_unit": "km", "target_value": 2000},
            headers=h,
        ).json()

        from ..models import BikeComponent
        row = db.query(BikeComponent).filter(BikeComponent.id == comp["id"]).first()
        row.accumulated_value = 500.0
        db.commit()

        r = client.post(
            f"/api/gear/bikes/{bike['id']}/components/{comp['id']}/service",
            json={"description": "Revisión de rutina, sin cambio", "resets_accumulated": False},
            headers=h,
        )
        assert r.status_code == 200

        bikes = client.get("/api/gear/bikes", headers=h).json()["bikes"]
        b = next(x for x in bikes if x["id"] == bike["id"])
        comp_after = next(c for c in b["components"] if c["id"] == comp["id"])
        assert comp_after["accumulated_value"] == 500.0

    def test_service_missing_description_400(self, client, athlete_user):
        h = _auth(client, athlete_user)
        bike = client.post("/api/gear/bikes", json={"brand": "Canyon", "model": "Aeroad"}, headers=h).json()
        comp = client.post(
            f"/api/gear/bikes/{bike['id']}/components",
            json={"component_type": "cadena", "tracking_unit": "km", "target_value": 3000},
            headers=h,
        ).json()
        r = client.post(f"/api/gear/bikes/{bike['id']}/components/{comp['id']}/service", json={}, headers=h)
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Summary agregado + vista de coach
# ─────────────────────────────────────────────────────────────────────────────

class TestSummaryAndCoachView:
    def test_summary_flags_gear_above_80pct(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        shoe = client.post("/api/gear/shoes", json={"brand": "Hoka", "model": "Clifton", "target_km": 700}, headers=h).json()

        from ..models import RunningShoe
        row = db.query(RunningShoe).filter(RunningShoe.id == shoe["id"]).first()
        row.accumulated_km = 600.0  # 85.7%
        db.commit()

        r = client.get("/api/gear/summary", headers=h)
        assert r.status_code == 200
        assert r.json()["alerts_count"] == 1

    def test_coach_view_requires_active_relationship(self, client, athlete_user, coach_user, db):
        shoe_token = login(client, "athlete@test.com", "AthlPass123")
        client.post("/api/gear/shoes", json={"brand": "Hoka", "model": "Clifton"}, headers=auth_headers(shoe_token))

        token_coach = login(client, "coach@test.com", "CoachPass123")
        h_coach = auth_headers(token_coach)

        r = client.get(f"/api/coach/athletes/{athlete_user.id}/gear", headers=h_coach)
        assert r.status_code == 403

        rel = CoachAthlete(coach_id=coach_user.id, athlete_id=athlete_user.id, activo=True)
        db.add(rel)
        db.commit()

        r2 = client.get(f"/api/coach/athletes/{athlete_user.id}/gear", headers=h_coach)
        assert r2.status_code == 200
        assert len(r2.json()["shoes"]) == 1


class TestManualActivityShoeAssignment:
    def _make_run(self, db, user_id, dist_km=10.0):
        import uuid
        from ..models import GarminActivity
        act = GarminActivity(
            id=str(uuid.uuid4()), user_id=user_id, activity_id=str(uuid.uuid4()),
            sport="run", date_iso="2026-08-20", date_label="2026-08-20",
            dur_min=50.0, dist_km=dist_km,
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    def test_get_shoe_for_unassigned_activity(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        act = self._make_run(db, athlete_user.id)
        r = client.get(f"/api/gear/activities/{act.id}/shoe", headers=h)
        assert r.status_code == 200
        assert r.json()["shoe_id"] is None

    def test_assign_shoe_manually_to_unassigned_activity(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        shoe = client.post("/api/gear/shoes", json={"brand": "Nike", "model": "Vaporfly"}, headers=h).json()
        act = self._make_run(db, athlete_user.id, dist_km=15.0)

        r = client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": shoe["id"]}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["shoe_id"] == shoe["id"]

        shoes = client.get("/api/gear/shoes", headers=h).json()["shoes"]
        s = next(s for s in shoes if s["id"] == shoe["id"])
        assert s["accumulated_km"] == 15.0

    def test_reassign_activity_moves_km_between_shoes(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        shoe_a = client.post("/api/gear/shoes", json={"brand": "Nike", "model": "A"}, headers=h).json()
        shoe_b = client.post("/api/gear/shoes", json={"brand": "Adidas", "model": "B"}, headers=h).json()
        act = self._make_run(db, athlete_user.id, dist_km=12.0)

        client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": shoe_a["id"]}, headers=h)
        r = client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": shoe_b["id"]}, headers=h)
        assert r.status_code == 200
        assert r.json()["shoe_id"] == shoe_b["id"]

        shoes = {s["id"]: s for s in client.get("/api/gear/shoes", headers=h).json()["shoes"]}
        assert shoes[shoe_a["id"]]["accumulated_km"] == 0.0
        assert shoes[shoe_b["id"]]["accumulated_km"] == 12.0

    def test_unassign_activity_removes_km(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        shoe = client.post("/api/gear/shoes", json={"brand": "Nike", "model": "A"}, headers=h).json()
        act = self._make_run(db, athlete_user.id, dist_km=8.0)
        client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": shoe["id"]}, headers=h)

        r = client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": None}, headers=h)
        assert r.status_code == 200
        assert r.json()["shoe_id"] is None

        shoes = client.get("/api/gear/shoes", headers=h).json()["shoes"]
        s = next(s for s in shoes if s["id"] == shoe["id"])
        assert s["accumulated_km"] == 0.0

    def test_assign_to_nonexistent_shoe_404(self, client, athlete_user, db):
        h = _auth(client, athlete_user)
        act = self._make_run(db, athlete_user.id)
        r = client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": "does-not-exist"}, headers=h)
        assert r.status_code == 404

    def test_cannot_assign_shoe_to_non_run_activity(self, client, athlete_user, db):
        import uuid
        from ..models import GarminActivity
        h = _auth(client, athlete_user)
        shoe = client.post("/api/gear/shoes", json={"brand": "Nike", "model": "A"}, headers=h).json()
        act = GarminActivity(id=str(uuid.uuid4()), user_id=athlete_user.id, activity_id=str(uuid.uuid4()),
                              sport="bike", date_iso="2026-08-20", date_label="2026-08-20", dur_min=60.0, dist_km=30.0)
        db.add(act)
        db.commit()

        r = client.post(f"/api/gear/activities/{act.id}/shoe", json={"shoe_id": shoe["id"]}, headers=h)
        assert r.status_code == 400

    def test_cannot_access_other_users_activity(self, client, athlete_user, coach_user, db):
        act = self._make_run(db, athlete_user.id)
        token_coach = login(client, "coach@test.com", "CoachPass123")
        h_coach = auth_headers(token_coach)
        r = client.get(f"/api/gear/activities/{act.id}/shoe", headers=h_coach)
        assert r.status_code == 404
