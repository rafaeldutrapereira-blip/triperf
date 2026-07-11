"""
Tests de coach routes: grupos, asignaciones, plan-vs-actual, templates.
"""
import pytest
from .conftest import login, auth_headers
from api.models import Group, GroupMember, WorkoutTemplate, AssignedWorkout


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def group_with_athlete(db, coach_user, athlete_user):
    """Crea un grupo del coach con el atleta como miembro."""
    g = Group(coach_id=coach_user.id, nombre="Grupo Test")
    db.add(g)
    db.flush()
    m = GroupMember(group_id=g.id, athlete_id=athlete_user.id)
    db.add(m)
    db.commit()
    db.refresh(g)
    return g


@pytest.fixture
def template(db, coach_user):
    """Crea un workout template del coach."""
    t = WorkoutTemplate(
        coach_id=coach_user.id,
        sport="run",
        nombre="Easy Run 45min",
        dur_min=45,
        tss=50,
        notas="Trote suave Z2",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ── Grupos ────────────────────────────────────────────────────

class TestGroups:
    def test_create_group(self, client, coach_user):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/groups",
            json={"nombre": "Grupo Alpha", "descripcion": "Elite"},
            headers=auth_headers(token))
        assert r.status_code == 201
        assert r.json()["nombre"] == "Grupo Alpha"

    def test_list_groups(self, client, coach_user, group_with_athlete):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get("/api/coach/groups", headers=auth_headers(token))
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_add_member(self, client, db, coach_user, athlete_user):
        token = login(client, "coach@test.com", "CoachPass123")
        # Crear grupo primero
        r = client.post("/api/coach/groups",
            json={"nombre": "Grupo Beta"},
            headers=auth_headers(token))
        assert r.status_code == 201
        group_id = r.json()["id"]

        # Agregar miembro
        r2 = client.post(f"/api/coach/groups/{group_id}/members",
            json={"user_id": athlete_user.id},
            headers=auth_headers(token))
        assert r2.status_code in (200, 201)

    def test_athlete_cannot_create_group(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/coach/groups",
            json={"nombre": "Intento"},
            headers=auth_headers(token))
        assert r.status_code == 403

    def test_coach_cannot_access_other_coach_group(self, client, db, coach_user):
        from api.models import User
        from api.auth import hash_password
        # Crear otro coach
        other = User(
            email="other@coach.com",
            nombre="Other Coach",
            password_hash=hash_password("Other123"),
            rol="coach", activo=True,
        )
        db.add(other)
        db.flush()
        g = Group(coach_id=other.id, nombre="Grupo Otro Coach")
        db.add(g)
        db.commit()

        token = login(client, "coach@test.com", "CoachPass123")
        # Intentar eliminar grupo ajeno
        r = client.delete(f"/api/coach/groups/{g.id}", headers=auth_headers(token))
        assert r.status_code in (403, 404)


# ── Workout Templates ─────────────────────────────────────────

class TestWorkoutTemplates:
    def test_create_template(self, client, coach_user):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/workouts",
            json={
                "sport": "bike",
                "nombre": "Bike Threshold",
                "dur_min": 90,
                "tss": 110,
                "notas": "2x20min al umbral",
            },
            headers=auth_headers(token))
        assert r.status_code == 201
        data = r.json()
        assert data["sport"] == "bike"
        assert data["nombre"] == "Bike Threshold"

    def test_list_templates(self, client, coach_user, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get("/api/coach/workouts", headers=auth_headers(token))
        assert r.status_code == 200
        tpls = r.json()
        assert len(tpls) >= 1

    def test_update_template(self, client, coach_user, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.put(f"/api/coach/workouts/{template.id}",
            json={"sport": "run", "nombre": "Easy Run Updated", "dur_min": 60, "tss": 65},
            headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()["dur_min"] == 60

    def test_delete_template(self, client, coach_user, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.delete(f"/api/coach/workouts/{template.id}",
                          headers=auth_headers(token))
        assert r.status_code in (200, 204)

    def test_sport_validated(self, client, coach_user):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/workouts",
            json={"sport": "polo_acuatico", "nombre": "Test", "dur_min": 60, "tss": 70},
            headers=auth_headers(token))
        # Debe fallar o aceptar como "other" — no debe 500
        assert r.status_code in (201, 400, 422)


# ── Asignaciones ─────────────────────────────────────────────

class TestAssignments:
    def test_assign_individual(self, client, coach_user, athlete_user,
                               group_with_athlete, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/assign",
            json={
                "template_id": template.id,
                "athlete_id":  athlete_user.id,
                "date_iso":    "2026-08-01",
            },
            headers=auth_headers(token))
        assert r.status_code == 201
        data = r.json()
        assert data["date_iso"] == "2026-08-01"

    def test_assign_to_group(self, client, coach_user, group_with_athlete, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/assign",
            json={
                "template_id": template.id,
                "group_id":    group_with_athlete.id,
                "date_iso":    "2026-08-02",
            },
            headers=auth_headers(token))
        assert r.status_code == 201

    def test_assign_invalid_date(self, client, coach_user, athlete_user,
                                 group_with_athlete, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/assign",
            json={
                "template_id": template.id,
                "athlete_id":  athlete_user.id,
                "date_iso":    "01-08-2026",  # formato incorrecto
            },
            headers=auth_headers(token))
        assert r.status_code == 422

    def test_assign_no_target_fails(self, client, coach_user, template):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/assign",
            json={"template_id": template.id, "date_iso": "2026-08-01"},
            headers=auth_headers(token))
        assert r.status_code == 400

    def test_list_assignments_for_athlete(self, client, db, coach_user,
                                          athlete_user, group_with_athlete, template):
        # Crear asignación manual
        aw = AssignedWorkout(
            template_id=template.id,
            athlete_id=athlete_user.id,
            date_iso="2026-08-05",
        )
        db.add(aw)
        db.commit()

        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get(f"/api/coach/assignments/athlete/{athlete_user.id}",
                       headers=auth_headers(token))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1

    def test_coach_cannot_assign_other_athlete(self, client, db, coach_user):
        """Coach no puede asignar a un atleta que no está en ningún grupo suyo."""
        from api.models import User, WorkoutTemplate
        from api.auth import hash_password
        stranger = User(
            email="stranger@test.com", nombre="Stranger",
            password_hash=hash_password("Pass123"),
            rol="athlete", activo=True,
        )
        db.add(stranger)
        tpl = WorkoutTemplate(
            coach_id=coach_user.id, sport="run",
            nombre="Test", dur_min=30, tss=30,
        )
        db.add(tpl)
        db.commit()

        token = login(client, "coach@test.com", "CoachPass123")
        r = client.post("/api/coach/assign",
            json={"template_id": tpl.id, "athlete_id": stranger.id, "date_iso": "2026-08-01"},
            headers=auth_headers(token))
        assert r.status_code == 403


# ── Plan vs Actual ────────────────────────────────────────────

class TestPlanVsActual:
    def test_plan_vs_actual_empty(self, client, coach_user, athlete_user,
                                  group_with_athlete):
        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get(
            f"/api/coach/athletes/{athlete_user.id}/plan-vs-actual"
            "?start=2026-08-01&end=2026-08-31",
            headers=auth_headers(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_plan_vs_actual_with_assignment(self, client, db, coach_user,
                                             athlete_user, group_with_athlete, template):
        aw = AssignedWorkout(
            template_id=template.id,
            athlete_id=athlete_user.id,
            date_iso="2026-08-10",
        )
        db.add(aw)
        db.commit()

        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get(
            f"/api/coach/athletes/{athlete_user.id}/plan-vs-actual"
            "?start=2026-08-01&end=2026-08-31",
            headers=auth_headers(token))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        assert items[0]["date_iso"] == "2026-08-10"

    def test_plan_vs_actual_denied_for_non_member(self, client, db, coach_user):
        from api.models import User
        from api.auth import hash_password
        outsider = User(
            email="out@test.com", nombre="Out",
            password_hash=hash_password("Out123"),
            rol="athlete", activo=True,
        )
        db.add(outsider)
        db.commit()

        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get(
            f"/api/coach/athletes/{outsider.id}/plan-vs-actual"
            "?start=2026-08-01&end=2026-08-31",
            headers=auth_headers(token))
        assert r.status_code == 403


# ── Adherencia ────────────────────────────────────────────────

class TestAdherence:
    def test_athlete_adherence(self, client, db, coach_user, athlete_user,
                               group_with_athlete, template):
        # Crear asignación completada
        aw = AssignedWorkout(
            template_id=template.id,
            athlete_id=athlete_user.id,
            date_iso="2026-07-01",
        )
        db.add(aw)
        db.commit()

        token = login(client, "coach@test.com", "CoachPass123")
        r = client.get("/api/coach/adherence?start=2026-07-01&end=2026-07-31",
                       headers=auth_headers(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)
