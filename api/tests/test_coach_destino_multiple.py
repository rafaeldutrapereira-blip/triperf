"""COACH-DESTINO-MULTIPLE (BUILD 362): destino múltiple en batch, semana tipo y macrociclo."""
import pytest

from .conftest import login, auth_headers
from api.auth import hash_password
from api.models import (
    User, CoachAthlete, WorkoutTemplate, AssignedWorkout, Group, GroupMember,
    WeekTemplate, WeekTemplateDay, Macrocycle, MacrocycleWeek,
)


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _mk_athletes(db, coach, n, prefix="m"):
    out = []
    for i in range(n):
        u = User(email=f"{prefix}{i}@test.com", nombre=f"{prefix.upper()} {i}",
                 password_hash=hash_password("Passw0rd123"), rol="athlete",
                 plan_nivel="basico", activo=True)
        db.add(u); db.flush()
        db.add(CoachAthlete(coach_id=coach.id, athlete_id=u.id, status="active"))
        out.append(u)
    db.commit()
    return out


@pytest.fixture
def tpl(db, coach_user):
    t = WorkoutTemplate(coach_id=coach_user.id, sport="run", nombre="Easy", dur_min=45, tss=50)
    db.add(t); db.commit(); db.refresh(t)
    return t


@pytest.fixture
def foreign(db):
    other = User(email="coach2@test.com", nombre="Otro", password_hash=hash_password("Passw0rd123"),
                 rol="coach", plan_nivel="basico", activo=True)
    a = User(email="ajeno@test.com", nombre="Ajeno", password_hash=hash_password("Passw0rd123"),
             rol="athlete", plan_nivel="basico", activo=True)
    db.add_all([other, a]); db.flush()
    db.add(CoachAthlete(coach_id=other.id, athlete_id=a.id, status="active"))
    db.commit()
    return a


@pytest.fixture
def week(db, coach_user, tpl):
    wt = WeekTemplate(coach_id=coach_user.id, nombre="Base")
    db.add(wt); db.flush()
    for d in (0, 2, 4):
        db.add(WeekTemplateDay(week_template_id=wt.id, day_of_week=d, workout_template_id=tpl.id))
    db.commit(); db.refresh(wt)
    return wt


def _count(db, athlete_id):
    db.expire_all()
    return db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == athlete_id).count()


def test_batch_3_atletas_crea_3(client, db, coach_user, tpl):
    ath = _mk_athletes(db, coach_user, 3)
    r = client.post("/api/coach/assign/batch", headers=_h(client), json={"assignments": [
        {"template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10"} for a in ath]})
    assert r.status_code == 201
    b = r.json()
    assert b["created"] == 3 and b["errors"] == 0
    assert all(_count(db, a.id) == 1 for a in ath)


def test_batch_tope_500(client, db, coach_user, tpl):
    h = _h(client)
    item = {"template_id": tpl.id, "athlete_id": "x", "date_iso": "2026-11-10"}
    r = client.post("/api/coach/assign/batch", headers=h, json={"assignments": [item] * 501})
    assert r.status_code == 400
    r = client.post("/api/coach/assign/batch", headers=h, json={"assignments": [item] * 500})
    assert r.status_code == 201 and r.json()["errors"] == 500  # ids inexistentes: todos reportados


def test_batch_invalido_no_bloquea_y_se_reporta(client, db, coach_user, tpl, foreign):
    ath = _mk_athletes(db, coach_user, 2)
    items = [
        {"template_id": tpl.id, "athlete_id": ath[0].id, "date_iso": "2026-11-10"},
        {"template_id": tpl.id, "athlete_id": foreign.id, "date_iso": "2026-11-10"},
        {"template_id": tpl.id, "athlete_id": ath[1].id, "date_iso": "2026-11-10"},
    ]
    b = client.post("/api/coach/assign/batch", headers=_h(client), json={"assignments": items}).json()
    assert b["created"] == 2 and b["errors"] == 1
    assert b["detail"]["errors"][0]["index"] == 1
    assert _count(db, foreign.id) == 0


def test_batch_troceo_60_atletas_sin_duplicar(client, db, coach_user, tpl):
    """Simula el troceo del cliente (chunks de 25) y un reintento del mismo chunk."""
    ath = _mk_athletes(db, coach_user, 60)
    h = _h(client)
    items = [{"template_id": tpl.id, "athlete_id": a.id, "date_iso": "2026-11-10"} for a in ath]
    created = errors = 0
    for i in range(0, len(items), 25):
        b = client.post("/api/coach/assign/batch", headers=h, json={"assignments": items[i:i + 25]}).json()
        created += b["created"]; errors += b["errors"]
    assert created == 60 and errors == 0
    # reintentar un trozo no duplica: queda reportado como duplicado
    b = client.post("/api/coach/assign/batch", headers=h, json={"assignments": items[:25]}).json()
    assert b["created"] == 0 and b["errors"] == 25
    assert db.query(AssignedWorkout).count() == 60


def test_semana_tipo_a_5_atletas(client, db, coach_user, week):
    ath = _mk_athletes(db, coach_user, 5)
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=_h(client), json={
        "start_date": "2026-11-09", "athlete_ids": [a.id for a in ath]})
    assert r.status_code == 200
    b = r.json()
    assert b["created"] == 15 and b["athletes_ok"] == 5 and b["athletes_failed"] == 0
    assert [x["created"] for x in b["results"]] == [3] * 5
    for a in ath:
        assert _count(db, a.id) == 3
    rows = db.query(AssignedWorkout).all()
    assert all(r.group_id is None for r in rows)  # misma semántica que apply individual


def test_semana_tipo_invalido_no_bloquea(client, db, coach_user, week, foreign):
    ath = _mk_athletes(db, coach_user, 2)
    ids = [ath[0].id, foreign.id, "no-existe", ath[1].id, ath[0].id]
    b = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=_h(client), json={
        "start_date": "2026-11-09", "athlete_ids": ids}).json()
    assert b["athletes_ok"] == 2 and b["athletes_failed"] == 3 and b["created"] == 6
    fails = {r["athlete_id"]: r["error"] for r in b["results"] if not r["ok"]}
    assert set(fails) == {foreign.id, "no-existe", ath[0].id}
    assert _count(db, foreign.id) == 0 and _count(db, ath[0].id) == 3


def test_semana_tipo_multi_validaciones(client, db, coach_user, week):
    h = _h(client)
    a = _mk_athletes(db, coach_user, 1)[0]
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=h,
                    json={"start_date": "2026-11-09", "athlete_ids": []})
    assert r.status_code == 400
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=h,
                    json={"start_date": "2026-11-09", "athlete_ids": [a.id], "athlete_id": a.id})
    assert r.status_code == 400
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=h,
                    json={"start_date": "2026-11-09", "athlete_ids": ["z"] * 501})
    assert r.status_code == 400


def test_macrociclo_a_3_atletas(client, db, coach_user, week):
    mc = Macrocycle(coach_id=coach_user.id, nombre="Bloque")
    db.add(mc); db.flush()
    db.add(MacrocycleWeek(macrocycle_id=mc.id, position=1, week_template_id=week.id))
    db.add(MacrocycleWeek(macrocycle_id=mc.id, position=2, week_template_id=week.id))
    db.commit()
    ath = _mk_athletes(db, coach_user, 3)
    b = client.post(f"/api/coach/macrocycles/{mc.id}/apply", headers=_h(client), json={
        "start_date": "2026-11-09", "athlete_ids": [x.id for x in ath]}).json()
    assert b["created"] == 18 and b["athletes_ok"] == 3 and b["weeks_applied"] == 2
    for x in ath:
        assert _count(db, x.id) == 6


# ── Regresión: destinos singulares de siempre ───────────────────────────────
def test_regresion_apply_individual_y_grupo(client, db, coach_user, week):
    h = _h(client)
    a = _mk_athletes(db, coach_user, 1)[0]
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=h,
                    json={"start_date": "2026-11-09", "athlete_id": a.id})
    assert r.status_code == 200 and r.json()["created"] == 3 and "results" not in r.json()
    g = Group(coach_id=coach_user.id, nombre="G")
    db.add(g); db.commit()
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=h,
                    json={"start_date": "2026-11-09", "group_id": g.id})
    assert r.status_code == 200 and r.json()["created"] == 3
    # apply a grupo: filas con group_id y SIN expandir por miembro (semántica existente)
    rows = db.query(AssignedWorkout).filter(AssignedWorkout.group_id == g.id).all()
    assert len(rows) == 3 and all(x.athlete_id is None for x in rows)


def test_regresion_apply_individual_ajeno_403(client, db, coach_user, week, foreign):
    r = client.post(f"/api/coach/week-templates/{week.id}/apply", headers=_h(client),
                    json={"start_date": "2026-11-09", "athlete_id": foreign.id})
    assert r.status_code == 403


def test_regresion_assign_individual_y_grupo_expande(client, db, coach_user, tpl):
    h = _h(client)
    ath = _mk_athletes(db, coach_user, 2)
    r = client.post("/api/coach/assign", headers=h, json={
        "template_id": tpl.id, "athlete_id": ath[0].id, "date_iso": "2026-11-10"})
    assert r.status_code == 201
    g = Group(coach_id=coach_user.id, nombre="G")
    db.add(g); db.flush()
    for a in ath:
        db.add(GroupMember(group_id=g.id, athlete_id=a.id))
    db.commit()
    r = client.post("/api/coach/assign", headers=h, json={
        "template_id": tpl.id, "group_id": g.id, "date_iso": "2026-11-11"})
    assert r.status_code == 201
    # assign a grupo: una fila por miembro (expandido)
    rows = db.query(AssignedWorkout).filter(AssignedWorkout.group_id == g.id).all()
    assert sorted(x.athlete_id for x in rows) == sorted(a.id for a in ath)
