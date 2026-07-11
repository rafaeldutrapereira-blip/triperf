"""
Tests de athlete routes: profile, plan, log, wellness, blood labs.
"""
import pytest
from .conftest import login, auth_headers
from api.models import Group, GroupMember, WorkoutTemplate, AssignedWorkout


def _create_assigned(db, coach, athlete, date="2026-07-01") -> AssignedWorkout:
    tpl = WorkoutTemplate(
        coach_id="coach-id", sport="run", nombre="Test Run", dur_min=60, tss=80
    )
    db.add(tpl)
    db.flush()
    aw = AssignedWorkout(
        template_id=tpl.id,
        athlete_id=athlete.id,
        date_iso=date,
    )
    db.add(aw)
    db.commit()
    db.refresh(aw)
    return aw


class TestAthleteProfile:
    def test_get_profile(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/athlete/profile", headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "athlete@test.com"
        assert data["ftp"] == 220

    def test_update_profile(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.patch("/api/athlete/profile",
            json={"ftp": 250, "weight_kg": 70.5, "race_goal_name": "Ironman Pucón"},
            headers=auth_headers(token))
        assert r.status_code == 200
        # Verificar que los datos se guardaron
        r2 = client.get("/api/athlete/profile", headers=auth_headers(token))
        assert r2.json()["ftp"] == 250
        assert r2.json()["race_goal_name"] == "Ironman Pucón"

    def test_profile_unauthenticated(self, client):
        r = client.get("/api/athlete/profile")
        assert r.status_code == 401


class TestAthletePlan:
    def test_get_empty_plan(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/athlete/plan", headers=auth_headers(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_plan_with_assignment(self, client, db, coach_user, athlete_user):
        tpl = WorkoutTemplate(
            coach_id=coach_user.id, sport="bike", nombre="Bike Tempo", dur_min=90, tss=100
        )
        db.add(tpl)
        db.flush()
        aw = AssignedWorkout(
            template_id=tpl.id,
            athlete_id=athlete_user.id,
            date_iso="2026-07-15",
        )
        db.add(aw)
        db.commit()

        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/athlete/plan?start=2026-07-01&end=2026-07-31",
                       headers=auth_headers(token))
        assert r.status_code == 200
        plan = r.json()
        assert len(plan) >= 1
        assert any(a["date_iso"] == "2026-07-15" for a in plan)


class TestWorkoutLog:
    def test_log_workout(self, client, db, coach_user, athlete_user):
        tpl = WorkoutTemplate(
            coach_id=coach_user.id, sport="run", nombre="Easy Run", dur_min=45, tss=50
        )
        db.add(tpl)
        db.flush()
        aw = AssignedWorkout(
            template_id=tpl.id,
            athlete_id=athlete_user.id,
            date_iso="2026-07-10",
        )
        db.add(aw)
        db.commit()

        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/athlete/log",
            json={
                "assignment_id": aw.id,
                "tss_real": 48,
                "dur_real": 44,
                "rpe": 6,
                "completado": True,
                "notas": "Bien",
            },
            headers=auth_headers(token))
        assert r.status_code in (200, 201)

    def test_log_requires_auth(self, client):
        r = client.post("/api/athlete/log", json={"assignment_id": "fake"})
        assert r.status_code == 401


class TestWellness:
    def test_log_wellness(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/athlete/wellness",
            json={
                "date_iso": "2026-07-01",
                "fatigue": 2,
                "sleep_q": 4,
                "soreness": 1,
                "mood": 5,
            },
            headers=auth_headers(token))
        assert r.status_code in (200, 201)

    def test_get_wellness(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/athlete/wellness", headers=auth_headers(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_wellness_values_validated(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/athlete/wellness",
            json={
                "date_iso": "2026-07-01",
                "fatigue": 99,  # fuera de rango 1-5
                "sleep_q": 4,
                "soreness": 1,
                "mood": 5,
            },
            headers=auth_headers(token))
        # Debería fallar o clampear — verificar que no guarda 99
        if r.status_code in (200, 201):
            r2 = client.get("/api/athlete/wellness", headers=auth_headers(token))
            entries = [e for e in r2.json() if e.get("date_iso") == "2026-07-01"]
            if entries:
                assert entries[0].get("fatigue", 99) <= 5


class TestBloodLabs:
    def test_upload_blood_lab(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/athlete/blood-labs",
            json={
                "date_iso": "2026-07-01",
                "lab_name": "Laboratorio X",
                "context": "Pre-temporada",
                "values_json": '{"hb": 14.2, "hct": 42.1}',
            },
            headers=auth_headers(token))
        assert r.status_code in (200, 201)

    def test_get_blood_labs(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/athlete/blood-labs", headers=auth_headers(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)
