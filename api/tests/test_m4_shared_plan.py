"""M4: planes compartibles por link de solo lectura + copiar a mi plan."""
from datetime import date

from .conftest import login, auth_headers
from ..models import PlanSession, TrainingPlan, User
from ..auth import hash_password


def _plan(db, coach, athlete):
    p = TrainingPlan(
        coach_id=coach.id, athlete_id=athlete.id, name="Plan 10K", description="Base",
        start_date="2026-01-05", end_date="2026-02-01", weeks=2, goal_ctl=50,
    )
    db.add(p)
    db.flush()
    for wk, dow, title, tss in [(1, 0, "Rodaje", 40), (1, 3, "Series", 70), (2, 2, "Fondo", 90)]:
        db.add(PlanSession(
            plan_id=p.id, athlete_id=athlete.id, week_number=wk, day_of_week=dow,
            date_iso=f"2026-01-{5 + (wk - 1) * 7 + dow:02d}", sport="run", title=title,
            tss_planned=tss, duration_min=60, coach_note="nota",
            athlete_note="SECRETO", tss_actual=33.0,
        ))
    db.commit()
    return p


def _share(client, coach_user, pid):
    h = auth_headers(login(client, "coach@test.com", "CoachPass123"))
    return client.post(f"/api/coach/plans/{pid}/share", headers=h), h


def test_valid_token_serves_readonly_view_without_auth(client, db, coach_user, athlete_user):
    p = _plan(db, coach_user, athlete_user)
    r, _ = _share(client, coach_user, p.id)
    assert r.status_code == 200
    tok = r.json()["share_token"]
    assert r.json()["share_url"].endswith(tok)
    # idempotente
    assert _share(client, coach_user, p.id)[0].json()["share_token"] == tok

    v = client.get(f"/api/public/plans/{tok}")
    assert v.status_code == 200
    d = v.json()
    assert d["name"] == "Plan 10K" and d["weeks"] == 2 and d["total_sessions"] == 3
    assert d["owner"] == {"name": "Coach Test"}
    assert [s["title"] for s in d["sessions_by_week"]["1"]] == ["Rodaje", "Series"]
    raw = v.text
    assert "SECRETO" not in raw and athlete_user.id not in raw and "tss_actual" not in raw
    assert "coach@test.com" not in raw


def test_invalid_and_revoked_token_404(client, db, coach_user, athlete_user):
    assert client.get("/api/public/plans/nope").status_code == 404
    p = _plan(db, coach_user, athlete_user)
    r, h = _share(client, coach_user, p.id)
    tok = r.json()["share_token"]
    assert client.delete(f"/api/coach/plans/{p.id}/share", headers=h).status_code == 200
    assert client.get(f"/api/public/plans/{tok}").status_code == 404
    ta = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    assert client.post(f"/api/plans/shared/{tok}/copy", json={}, headers=ta).status_code == 404
    # re-compartir genera un token nuevo
    new = _share(client, coach_user, p.id)[0].json()["share_token"]
    assert new != tok


def test_athlete_cannot_share_and_other_coach_cannot_share(client, db, coach_user, athlete_user):
    p = _plan(db, coach_user, athlete_user)
    ta = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    assert client.post(f"/api/coach/plans/{p.id}/share", headers=ta).status_code == 403
    assert client.delete(f"/api/coach/plans/{p.id}/share", headers=ta).status_code == 403
    db.add(User(email="c2@test.com", nombre="C2", password_hash=hash_password("CoachPass123"),
                rol="coach", plan_nivel="agegroup", activo=True))
    db.commit()
    h2 = auth_headers(login(client, "c2@test.com", "CoachPass123"))
    assert client.post(f"/api/coach/plans/{p.id}/share", headers=h2).status_code == 404
    db.refresh(p)
    assert p.share_token is None


def test_copy_requires_login(client, db, coach_user, athlete_user):
    p = _plan(db, coach_user, athlete_user)
    tok = _share(client, coach_user, p.id)[0].json()["share_token"]
    client.cookies.clear()   # el login del coach dejo la cookie de sesion
    assert client.post(f"/api/plans/shared/{tok}/copy", json={}).status_code in (401, 403)


def test_athlete_copy_is_complete_and_decoupled(client, db, coach_user, athlete_user):
    p = _plan(db, coach_user, athlete_user)
    tok = _share(client, coach_user, p.id)[0].json()["share_token"]
    other = User(email="b@test.com", nombre="B", password_hash=hash_password("AthlPass123"),
                 rol="athlete", plan_nivel="basico", activo=True)
    db.add(other)
    db.commit()
    h = auth_headers(login(client, "b@test.com", "AthlPass123"))
    r = client.post(f"/api/plans/shared/{tok}/copy", json={"start_date": "2026-03-02"}, headers=h)
    assert r.status_code == 201
    j = r.json()
    assert j["n_sessions"] == 3 and j["to_library"] is False and j["end_date"] == "2026-03-15"

    c = db.query(TrainingPlan).filter(TrainingPlan.id == j["plan_id"]).one()
    assert c.athlete_id == other.id and c.coach_id == other.id
    assert c.is_active and not c.is_template
    assert c.share_token is None and c.template_id is None and c.id != p.id
    cs = sorted(c.sessions, key=lambda s: s.date_iso)
    assert [s.date_iso for s in cs] == ["2026-03-02", "2026-03-05", "2026-03-11"]
    assert all(s.athlete_id == other.id and s.plan_id == c.id for s in cs)
    assert all(s.tss_actual is None and s.athlete_note is None for s in cs)

    # visible en /plans del atleta que copio
    assert j["plan_id"] in [x["id"] for x in client.get("/api/plans", headers=h).json()]

    # desacoplado: editar/borrar el original no toca la copia
    ids = {s.id for s in p.sessions}
    p.sessions[0].title = "CAMBIADO"
    db.query(PlanSession).filter(PlanSession.plan_id == p.id).delete()
    db.query(TrainingPlan).filter(TrainingPlan.id == p.id).delete()
    db.commit()
    db.expire_all()
    c = db.query(TrainingPlan).filter(TrainingPlan.id == j["plan_id"]).one()
    assert len(c.sessions) == 3 and "CAMBIADO" not in [s.title for s in c.sessions]
    assert not ids & {s.id for s in c.sessions}


def test_coach_copy_goes_to_library_and_default_start_is_future_monday(client, db, coach_user, athlete_user):
    p = _plan(db, coach_user, athlete_user)
    tok = _share(client, coach_user, p.id)[0].json()["share_token"]
    db.add(User(email="c2@test.com", nombre="C2", password_hash=hash_password("CoachPass123"),
                rol="coach", plan_nivel="agegroup", activo=True))
    db.commit()
    h2 = auth_headers(login(client, "c2@test.com", "CoachPass123"))
    r = client.post(f"/api/plans/shared/{tok}/copy", json={"plan_name": "Mi copia"}, headers=h2)
    assert r.status_code == 201 and r.json()["to_library"] is True
    start = date.fromisoformat(r.json()["start_date"])
    assert start.weekday() == 0 and start > date.today()
    lib = client.get("/api/coach/plan-templates", headers=h2).json()
    assert [t["name"] for t in lib] == ["Mi copia"]


def test_bad_start_date_400(client, db, coach_user, athlete_user):
    p = _plan(db, coach_user, athlete_user)
    tok = _share(client, coach_user, p.id)[0].json()["share_token"]
    ta = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    assert client.post(f"/api/plans/shared/{tok}/copy", json={"start_date": "x"}, headers=ta).status_code == 400
