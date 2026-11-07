"""CARRERAS-PERFIL — «Mis carreras del año»: CRUD /athlete/races sobre RaceEvent."""
from datetime import date, timedelta
from pathlib import Path

import pytest

from ..models import RaceEvent, User
from .conftest import login

ROOT = Path(__file__).resolve().parents[2]


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture
def headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def _post(client, headers, name, days, **kw):
    body = {"name": name, "date_iso": _d(days), "distance": "70.3", **kw}
    r = client.post("/api/athlete/races", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["race"]


def _goals(db, user_id):
    db.expire_all()
    return db.query(RaceEvent).filter(
        RaceEvent.user_id == user_id, RaceEvent.is_goal_race == True  # noqa: E712
    ).all()


def test_primera_futura_queda_principal_y_sincroniza_user(client, db, athlete_user, headers):
    r = _post(client, headers, "Pucon", 60, priority="A")
    assert r["is_goal_race"] is True and r["priority"] == "A"
    db.expire_all()
    u = db.query(User).filter(User.id == athlete_user.id).one()
    assert (u.race_goal_name, u.race_goal_date, u.race_goal_dist) == ("Pucon", _d(60), "70.3")


def test_segunda_no_es_principal_y_lista_ordenada_por_fecha(client, db, athlete_user, headers):
    _post(client, headers, "Tardia", 120)
    r2 = _post(client, headers, "Temprana", 30)
    assert r2["is_goal_race"] is False
    lst = client.get("/api/athlete/races", headers=headers).json()["races"]
    assert [x["name"] for x in lst] == ["Temprana", "Tardia"]
    assert [x["is_goal_race"] for x in lst] == [False, True]
    assert all(x["has_result"] is False for x in lst)
    assert len(_goals(db, athlete_user.id)) == 1


def test_lista_incluye_pasadas_del_anio_con_resultado_y_excluye_anteriores(client, db, athlete_user, headers):
    year = date.today().year
    db.add(RaceEvent(user_id=athlete_user.id, name="Enero", date_iso=f"{year}-01-02",
                     distance="10k", actual_total_sec=3000))
    db.add(RaceEvent(user_id=athlete_user.id, name="AnioPasado", date_iso=f"{year - 1}-12-31",
                     distance="10k"))
    db.commit()
    lst = client.get("/api/athlete/races", headers=headers).json()["races"]
    names = {x["name"]: x for x in lst}
    assert "AnioPasado" not in names
    assert names["Enero"]["has_result"] is True


def test_solo_carreras_propias(client, db, athlete_user, coach_user, headers):
    other = RaceEvent(user_id=coach_user.id, name="Ajena", date_iso=_d(10), distance="sprint")
    db.add(other)
    db.commit()
    assert client.get("/api/athlete/races", headers=headers).json()["races"] == []
    assert client.patch(f"/api/athlete/races/{other.id}", json={"name": "x"}, headers=headers).status_code == 404
    assert client.delete(f"/api/athlete/races/{other.id}", headers=headers).status_code == 404
    assert client.post(f"/api/athlete/races/{other.id}/principal", headers=headers).status_code == 404
    db.expire_all()
    assert db.query(RaceEvent).filter(RaceEvent.id == other.id).count() == 1


def test_patch_edita_y_sincroniza_si_es_principal(client, db, athlete_user, headers):
    r = _post(client, headers, "Pucon", 60)
    p = client.patch(f"/api/athlete/races/{r['id']}",
                     json={"name": "Pucon 2", "date_iso": _d(70), "distance": "ironman",
                           "location": "Chile", "priority": "B"}, headers=headers)
    assert p.status_code == 200
    race = p.json()["race"]
    assert (race["name"], race["distance"], race["location"], race["priority"]) == ("Pucon 2", "ironman", "Chile", "B")
    db.expire_all()
    u = db.query(User).filter(User.id == athlete_user.id).one()
    assert (u.race_goal_name, u.race_goal_date, u.race_goal_dist) == ("Pucon 2", _d(70), "ironman")


def test_validaciones(client, headers):
    base = {"name": "X", "date_iso": _d(5)}
    assert client.post("/api/athlete/races", json={**base, "name": "  "}, headers=headers).status_code == 422
    assert client.post("/api/athlete/races", json={**base, "date_iso": "07/11/2026"}, headers=headers).status_code == 422
    assert client.post("/api/athlete/races", json={**base, "priority": "Z"}, headers=headers).status_code == 422
    r = _post(client, headers, "Ok", 5)
    assert client.patch(f"/api/athlete/races/{r['id']}", json={"priority": "Q"}, headers=headers).status_code == 422


def test_marcar_principal_unica_y_sincroniza(client, db, athlete_user, headers):
    a = _post(client, headers, "A", 30)
    b = _post(client, headers, "B", 90, distance="olympic")
    assert a["is_goal_race"] is True and b["is_goal_race"] is False
    r = client.post(f"/api/athlete/races/{b['id']}/principal", headers=headers)
    assert r.status_code == 200 and r.json()["race"]["is_goal_race"] is True
    goals = _goals(db, athlete_user.id)
    assert [g.id for g in goals] == [b["id"]]
    u = db.query(User).filter(User.id == athlete_user.id).one()
    assert (u.race_goal_name, u.race_goal_date, u.race_goal_dist) == ("B", _d(90), "olympic")


def test_borrar_principal_promueve_la_futura_mas_cercana(client, db, athlete_user, headers):
    a = _post(client, headers, "Principal", 30)
    _post(client, headers, "Lejana", 200)
    _post(client, headers, "Cercana", 60)
    assert client.delete(f"/api/athlete/races/{a['id']}", headers=headers).status_code == 200
    goals = _goals(db, athlete_user.id)
    assert len(goals) == 1 and goals[0].name == "Cercana"
    u = db.query(User).filter(User.id == athlete_user.id).one()
    assert (u.race_goal_name, u.race_goal_date) == ("Cercana", _d(60))


def test_borrar_la_ultima_futura_limpia_campos_del_user(client, db, athlete_user, headers):
    a = _post(client, headers, "Unica", 30)
    assert client.delete(f"/api/athlete/races/{a['id']}", headers=headers).status_code == 200
    assert _goals(db, athlete_user.id) == []
    u = db.query(User).filter(User.id == athlete_user.id).one()
    assert (u.race_goal_name, u.race_goal_date, u.race_goal_dist) == (None, None, None)


def test_borrar_no_principal_no_toca_la_principal(client, db, athlete_user, headers):
    a = _post(client, headers, "Principal", 30)
    b = _post(client, headers, "Otra", 90)
    client.delete(f"/api/athlete/races/{b['id']}", headers=headers)
    goals = _goals(db, athlete_user.id)
    assert [g.id for g in goals] == [a["id"]]


def test_pasada_no_se_vuelve_principal_automaticamente(client, db, athlete_user, headers):
    r = _post(client, headers, "Ya corrida", -20)
    assert r["is_goal_race"] is False
    assert _goals(db, athlete_user.id) == []


def test_nueva_futura_reemplaza_principal_pasada_manteniendo_invariante(client, db, athlete_user, headers):
    old = RaceEvent(user_id=athlete_user.id, name="Vieja", date_iso=_d(-10), distance="10k", is_goal_race=True)
    db.add(old)
    db.commit()
    r = _post(client, headers, "Nueva", 40)
    assert r["is_goal_race"] is True
    goals = _goals(db, athlete_user.id)
    assert [g.name for g in goals] == ["Nueva"]


def test_sync_legacy_desde_campos_simples_sigue_funcionando(client, db, athlete_user, headers):
    _post(client, headers, "Lista", 30)
    r = client.patch("/api/athlete/profile",
                     json={"race_goal_name": "Legacy", "race_goal_date": _d(50), "race_goal_dist": "full"},
                     headers=headers)
    assert r.status_code == 200
    goals = _goals(db, athlete_user.id)
    assert len(goals) == 1 and goals[0].name == "Legacy"


def test_migracion_agrega_priority_sin_tocar_otras_tablas():
    src = (ROOT / "alembic" / "versions" / "c8d9e0f1a2b3_add_priority_to_race_events.py").read_text(encoding="utf-8")
    assert 'down_revision = "b7c8d9e0f1a2"' in src
    assert '"race_events", sa.Column("priority"' in src
    assert src.count("add_column") == 1
