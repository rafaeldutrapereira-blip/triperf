"""COACH-UNIVERSO (BUILD 360): universo único de atletas del coach."""
import pytest
from datetime import date

from .conftest import login, auth_headers
from api.auth import hash_password
from api.models import (
    User, Group, GroupMember, CoachAthlete, WorkoutTemplate, WellnessLog,
)


def _user(db, email, nombre, rol="athlete"):
    u = User(email=email, nombre=nombre, password_hash=hash_password("Passw0rd123"),
             rol=rol, plan_nivel="basico", activo=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def loose(db, coach_user):
    """Atleta solo por CoachAthlete, sin grupo."""
    a = _user(db, "loose@test.com", "Suelto")
    db.add(CoachAthlete(coach_id=coach_user.id, athlete_id=a.id, status="active"))
    db.add(WellnessLog(user_id=a.id, date_iso=date.today().isoformat(), fatigue=5, soreness=2))
    db.commit()
    return a


@pytest.fixture
def grouped(db, coach_user, athlete_user):
    g = Group(coach_id=coach_user.id, nombre="G")
    db.add(g); db.flush()
    db.add(GroupMember(group_id=g.id, athlete_id=athlete_user.id))
    db.commit()
    return athlete_user


@pytest.fixture
def foreign(db):
    other = _user(db, "coach2@test.com", "Otro Coach", rol="coach")
    a = _user(db, "foreign@test.com", "Ajeno")
    g = Group(coach_id=other.id, nombre="G2")
    db.add(g); db.flush()
    db.add(GroupMember(group_id=g.id, athlete_id=a.id))
    db.add(CoachAthlete(coach_id=other.id, athlete_id=a.id, status="active"))
    db.add(WellnessLog(user_id=a.id, date_iso=date.today().isoformat(), fatigue=5, soreness=5))
    db.commit()
    return a


@pytest.fixture
def tpl(db, coach_user):
    t = WorkoutTemplate(coach_id=coach_user.id, sport="run", nombre="Easy", dur_min=45, tss=50)
    db.add(t); db.commit(); db.refresh(t)
    return t


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _ids(rows, key):
    return {r[key] for r in rows}


def test_loose_athlete_in_all_boards(client, coach_user, loose, grouped, foreign):
    h = _h(client)
    sb = client.get("/api/coach/status-board", headers=h).json()
    assert loose.id in _ids(sb, "athlete_id") and grouped.id in _ids(sb, "athlete_id")
    assert foreign.id not in _ids(sb, "athlete_id")

    ad = client.get("/api/coach/adherence?start=2020-01-01&end=2099-01-01", headers=h).json()
    assert loose.id in _ids(ad, "user_id") and grouped.id in _ids(ad, "user_id")
    assert foreign.id not in _ids(ad, "user_id")

    al = client.get("/api/coach/alerts", headers=h).json()["alerts"]
    assert loose.id in _ids(al, "athlete_id")
    assert foreign.id not in _ids(al, "athlete_id")

    tw = client.get("/api/coach/team-wellness", headers=h).json()
    assert loose.id in _ids(tw, "athlete_id")
    assert foreign.id not in _ids(tw, "athlete_id")

    sq = client.get("/api/coach/squad-overview", headers=h).json()
    ids = {a.get("athlete_id") or a.get("id") for a in sq["athletes"]}
    assert loose.id in ids and foreign.id not in ids


def test_assign_individual_loose_201(client, coach_user, loose, tpl):
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": loose.id, "date_iso": "2026-11-10"})
    assert r.status_code == 201


def test_assign_individual_foreign_403(client, coach_user, foreign, tpl):
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": foreign.id, "date_iso": "2026-11-10"})
    assert r.status_code == 403


def test_assign_individual_grouped_still_201(client, coach_user, grouped, tpl):
    r = client.post("/api/coach/assign", headers=_h(client), json={
        "template_id": tpl.id, "athlete_id": grouped.id, "date_iso": "2026-11-10"})
    assert r.status_code == 201


def test_batch_loose_ok_foreign_rejected(client, coach_user, loose, foreign, tpl):
    r = client.post("/api/coach/assign/batch", headers=_h(client), json={"assignments": [
        {"template_id": tpl.id, "athlete_id": loose.id, "date_iso": "2026-11-10"},
        {"template_id": tpl.id, "athlete_id": foreign.id, "date_iso": "2026-11-10"},
    ]})
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 1 and body["errors"] == 1
    assert body["detail"]["errors"][0]["index"] == 1
