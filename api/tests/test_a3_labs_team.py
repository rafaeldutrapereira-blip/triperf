"""A3-LABS-TEAM: /labs/team, gear del atleta y /ai/coach-copilot exigen
CoachAthlete.status=='active' (una invitacion pendiente no da acceso)."""
from .conftest import login, auth_headers
from ..models import CoachAthlete, RunningShoe


def _coach_h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _rel(db, coach, athlete, status):
    db.add(CoachAthlete(coach_id=coach.id, athlete_id=athlete.id, activo=True, status=status))
    db.commit()


# ---- /labs/team ---------------------------------------------------------
def _team_ids(body):
    ids = set()
    for k in ("critical_athletes", "warning_athletes", "ok_athletes"):
        for a in body.get(k, []):
            ids.add(a.get("athlete_id") or a.get("user_id") or a.get("id"))
    return ids


def test_labs_team_pending_sees_nothing(client, coach_user, athlete_user, db):
    _rel(db, coach_user, athlete_user, "pending")
    r = client.get("/api/labs/team", headers=_coach_h(client))
    assert r.status_code == 200  # contrato actual: 200 con lista vacia
    b = r.json()
    assert b["athletes_count"] == 0
    assert _team_ids(b) == set()


def test_labs_team_active_counts_athlete(client, coach_user, athlete_user, db):
    _rel(db, coach_user, athlete_user, "active")
    r = client.get("/api/labs/team", headers=_coach_h(client))
    assert r.status_code == 200
    assert r.json()["athletes_count"] == 1


def test_labs_team_no_relation_empty(client, coach_user, athlete_user):
    r = client.get("/api/labs/team", headers=_coach_h(client))
    assert r.status_code == 200
    assert r.json()["athletes_count"] == 0


# ---- gear ---------------------------------------------------------------
def test_gear_pending_is_403_active_is_200(client, coach_user, athlete_user, db):
    db.add(RunningShoe(user_id=athlete_user.id, brand="Hoka", model="Clifton"))
    db.commit()
    _rel(db, coach_user, athlete_user, "pending")
    h = _coach_h(client)
    assert client.get(f"/api/coach/athletes/{athlete_user.id}/gear", headers=h).status_code == 403
    rel = db.query(CoachAthlete).filter_by(coach_id=coach_user.id).first()
    rel.status = "active"
    db.commit()
    r = client.get(f"/api/coach/athletes/{athlete_user.id}/gear", headers=h)
    assert r.status_code == 200
    assert len(r.json()["shoes"]) == 1


def test_athlete_own_gear_unaffected(client, athlete_user):
    h = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    assert client.get("/api/gear/summary", headers=h).status_code == 200


# ---- /ai/coach-copilot ----------------------------------------------------
def test_copilot_pending_excluded_active_included(client, coach_user, athlete_user, db):
    _rel(db, coach_user, athlete_user, "pending")
    h = _coach_h(client)
    r = client.get("/api/ai/coach-copilot", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["total_athletes"] == 0
    rel = db.query(CoachAthlete).filter_by(coach_id=coach_user.id).first()
    rel.status = "active"
    db.commit()
    r2 = client.get("/api/ai/coach-copilot", headers=h)
    assert r2.status_code == 200
    assert r2.json()["total_athletes"] == 1
