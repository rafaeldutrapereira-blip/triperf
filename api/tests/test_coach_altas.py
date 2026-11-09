"""COACH-ALTAS (BUILD 364): invitacion masiva y alta en lote a grupos."""
from .conftest import login, auth_headers
from api.models import User, CoachAthlete, Group, GroupMember
from .test_coach_destino_multiple import _mk_athletes, foreign  # noqa: F401


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _by_email(res):
    return {r["email"]: r["status"] for r in res["results"]}


def test_invitacion_masiva_estados_y_solo_validas(client, db, coach_user):
    existing, = _mk_athletes(db, coach_user, 1, prefix="ya")      # ya0@test.com
    existing.rol = "atleta"; db.commit()                          # el alta singular compara rol == "atleta"
    items = [
        {"email": "nuevo1@x.com", "nombre": "Nuevo Uno"},
        {"email": "no-es-correo"},
        {"email": existing.email},
        {"email": "nuevo2@x.com"},
        {"email": "NUEVO1@x.com"},                                 # repetido en la lista
    ]
    r = client.post("/api/coach/athletes/bulk", headers=_h(client), json={"items": items})
    assert r.status_code == 200, r.text
    st = _by_email(r.json())
    assert st["nuevo1@x.com"] == "invited" or st["nuevo1@x.com"] == "duplicate_in_list"
    sts = [x["status"] for x in r.json()["results"]]
    assert sts == ["invited", "invalid", "already_athlete", "invited", "duplicate_in_list"]
    assert r.json()["summary"] == {"invited": 2, "invalid": 1, "already_athlete": 1, "duplicate_in_list": 1}
    # solo se crearon las 2 validas
    db.expire_all()
    assert db.query(User).filter(User.email == "nuevo1@x.com").count() == 1
    assert db.query(User).filter(User.email == "nuevo2@x.com").count() == 1
    assert db.query(User).filter(User.email == "no-es-correo").count() == 0
    u = db.query(User).filter(User.email == "nuevo2@x.com").first()
    assert u.nombre == "nuevo2" and u.pending_invite is True and u.activo is False
    ca = db.query(CoachAthlete).filter(CoachAthlete.athlete_id == u.id).first()
    assert ca.status == "pending" and ca.coach_id == coach_user.id


def test_invitacion_masiva_igual_que_singular(client, db, coach_user):
    h = _h(client)
    s = client.post("/api/coach/athletes", headers=h, json={"email": "sing@x.com", "nombre": "Sing"})
    b = client.post("/api/coach/athletes/bulk", headers=h,
                    json={"items": [{"email": "bulk@x.com", "nombre": "Sing"}]})
    assert s.status_code == 201
    assert b.json()["results"][0]["detail"] == s.json()["status"] == "pending_new"
    a = db.query(User).filter(User.email == "sing@x.com").first()
    c = db.query(User).filter(User.email == "bulk@x.com").first()
    assert (a.rol, a.activo, a.pending_invite, a.plan_nivel) == (c.rol, c.activo, c.pending_invite, c.plan_nivel)


def test_invitacion_masiva_tope_y_cuenta_no_atleta(client, db, coach_user, foreign):  # noqa: F811
    h = _h(client)
    r = client.post("/api/coach/athletes/bulk", headers=h,
                    json={"items": [{"email": f"t{i}@x.com"} for i in range(201)]})
    assert r.status_code == 413
    r = client.post("/api/coach/athletes/bulk", headers=h, json={"items": [{"email": "coach2@test.com"}]})
    assert r.json()["results"][0]["status"] == "not_athlete_account"
    foreign.rol = "atleta"; db.commit()
    # atleta de otro coach: existe, sin relacion con este coach => queda pendiente (igual que singular)
    r = client.post("/api/coach/athletes/bulk", headers=h, json={"items": [{"email": foreign.email}]})
    assert r.json()["results"][0]["status"] == "invited"


def test_alta_en_lote_a_grupo(client, db, coach_user, foreign):  # noqa: F811
    h = _h(client)
    ath = _mk_athletes(db, coach_user, 4)
    g = Group(nombre="G", coach_id=coach_user.id); db.add(g); db.commit(); db.refresh(g)
    db.add(GroupMember(group_id=g.id, athlete_id=ath[0].id)); db.commit()
    ids = [a.id for a in ath] + [foreign.id]
    r = client.post(f"/api/coach/groups/{g.id}/members/bulk", headers=h, json={"user_ids": ids})
    assert r.status_code == 200, r.text
    st = {x["user_id"]: x["status"] for x in r.json()["results"]}
    assert st[ath[0].id] == "already_member"
    assert [st[a.id] for a in ath[1:]] == ["added"] * 3
    assert st[foreign.id] == "not_yours"
    # idempotente: no duplica
    r2 = client.post(f"/api/coach/groups/{g.id}/members/bulk", headers=h, json={"user_ids": ids})
    assert r2.json()["summary"] == {"already_member": 4, "not_yours": 1}
    db.expire_all()
    assert db.query(GroupMember).filter(GroupMember.group_id == g.id).count() == 4


def test_crear_grupo_con_seleccion_y_subgrupo(client, db, coach_user):
    h = _h(client)
    ath = _mk_athletes(db, coach_user, 3)
    r = client.post("/api/coach/groups/with-members", headers=h,
                    json={"nombre": "Maraton", "competencia": "Buenos Aires", "user_ids": [a.id for a in ath]})
    assert r.status_code == 201, r.text
    gid = r.json()["group_id"]
    assert r.json()["summary"] == {"added": 3}
    r = client.post("/api/coach/groups/with-members", headers=h,
                    json={"nombre": "Sub", "parent_group_id": gid, "user_ids": [ath[0].id]})
    sub = r.json()["group_id"]
    db.expire_all()
    assert db.query(Group).filter(Group.id == sub).first().parent_group_id == gid
    assert db.query(GroupMember).filter(GroupMember.group_id == gid).count() == 3
    assert db.query(GroupMember).filter(GroupMember.group_id == sub).count() == 1
    # nombre vacio
    assert client.post("/api/coach/groups/with-members", headers=h,
                       json={"nombre": "  ", "user_ids": []}).status_code == 422


def test_coach_no_puebla_grupos_ajenos(client, db, coach_user, foreign):  # noqa: F811
    h = _h(client)
    ath = _mk_athletes(db, coach_user, 1)
    other = db.query(User).filter(User.email == "coach2@test.com").first()
    g = Group(nombre="Ajeno", coach_id=other.id); db.add(g); db.commit(); db.refresh(g)
    r = client.post(f"/api/coach/groups/{g.id}/members/bulk", headers=h, json={"user_ids": [ath[0].id]})
    assert r.status_code == 403
    r = client.post("/api/coach/groups/with-members", headers=h,
                    json={"nombre": "X", "parent_group_id": g.id, "user_ids": [ath[0].id]})
    assert r.status_code == 403
    db.expire_all()
    assert db.query(GroupMember).filter(GroupMember.group_id == g.id).count() == 0
