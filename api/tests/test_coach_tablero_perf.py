"""COACH-TABLERO-PERF (BUILD 365): tableros sin N+1 y Gantt en una peticion."""
from datetime import date, timedelta

from .conftest import login, auth_headers, engine_test
from .tablero_fixture import seed_team, count_queries
from api.models import User, CoachAthlete, WorkoutTemplate, AssignedWorkout, WorkoutLog
from api.auth import hash_password


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _urls():
    today = date.today()
    return {
        "sb": "/api/coach/status-board",
        "ad": f"/api/coach/adherence?start={(today - timedelta(days=30)).isoformat()}&end={(today + timedelta(days=7)).isoformat()}",
        "gantt": f"/api/coach/assignments/team?start={(today - timedelta(days=today.weekday())).isoformat()}"
                 f"&end={(today - timedelta(days=today.weekday()) + timedelta(days=6)).isoformat()}",
    }


def _count(client, h, url):
    client.get(url, headers=h)  # calienta caches/imports
    with count_queries(engine_test) as qc:
        r = client.get(url, headers=h)
    assert r.status_code == 200, r.text
    return qc.n, r.json()


def test_queries_independientes_del_numero_de_atletas(client, db, coach_user):
    h = _h(client)
    seed_team(db, coach_user, 10, prefix="a")
    small = {k: _count(client, h, u)[0] for k, u in _urls().items()}
    seed_team(db, coach_user, 60, prefix="b")
    big = {k: _count(client, h, u)[0] for k, u in _urls().items()}
    assert big == small, (small, big)
    assert max(big.values()) <= 15


def test_gantt_equivale_al_endpoint_por_atleta(client, db, coach_user):
    h = _h(client)
    seed_team(db, coach_user, 12)
    sin_sesiones = User(email="vacio@test.com", nombre="Vacio", password_hash=hash_password("Passw0rd123"),
                        rol="athlete", plan_nivel="basico", activo=True)
    db.add(sin_sesiones); db.flush()
    db.add(CoachAthlete(coach_id=coach_user.id, athlete_id=sin_sesiones.id, status="active"))
    db.commit()
    u = _urls()["gantt"]
    team = client.get(u, headers=h).json()
    qs = u.split("?")[1]
    assert len(team) == 13
    for t in team:
        old = client.get(f"/api/coach/assignments/athlete/{t['athlete_id']}?{qs}", headers=h).json()
        assert t["assignments"] == old
    assert [t for t in team if t["athlete_id"] == sin_sesiones.id][0]["assignments"] == []


def test_gantt_no_incluye_ajenos_ni_templates_de_otro_coach(client, db, coach_user):
    h = _h(client)
    seed_team(db, coach_user, 3)
    other = User(email="coach2@test.com", nombre="Otro", password_hash=hash_password("Passw0rd123"),
                 rol="coach", plan_nivel="basico", activo=True)
    ajeno = User(email="ajeno@test.com", nombre="Ajeno", password_hash=hash_password("Passw0rd123"),
                 rol="athlete", plan_nivel="basico", activo=True)
    db.add_all([other, ajeno]); db.flush()
    db.add(CoachAthlete(coach_id=other.id, athlete_id=ajeno.id, status="active"))
    tpl_otro = WorkoutTemplate(coach_id=other.id, sport="run", nombre="X", dur_min=30, tss=30)
    db.add(tpl_otro); db.flush()
    mine = db.query(User).filter(User.email == "p0@perf.com").first()
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    db.add(AssignedWorkout(template_id=tpl_otro.id, athlete_id=mine.id, date_iso=mon.isoformat()))
    db.commit()
    team = client.get(_urls()["gantt"], headers=h).json()
    ids = {t["athlete_id"] for t in team}
    assert ajeno.id not in ids and len(ids) == 3
    names = {a["template"]["nombre"] for t in team for a in t["assignments"]}
    assert "X" not in names


def test_gantt_grupo_ajeno_404(client, db, coach_user):
    r = client.get(_urls()["gantt"] + "&group_id=nope", headers=_h(client))
    assert r.status_code == 404
