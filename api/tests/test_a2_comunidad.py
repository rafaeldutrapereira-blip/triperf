"""A2-COMUNIDAD: privacidad de busqueda, perfil, posts/comentarios, grupos
privados y mensajes."""
import json
from datetime import date

from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import (
    User, CoachAthlete, Follow, CommunityPost, Comment, CommunityGroup,
    CommunityGroupMember, Challenge, ChallengeEntry, Message, GarminActivity,
)

PW = "Passw0rd!123"


def _mk(db, email, nombre, rol="athlete", plan="elite", **kw):
    u = User(email=email, nombre=nombre, password_hash=hash_password(PW),
             rol=rol, plan_nivel=plan, activo=True, **kw)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _h(client, u):
    return auth_headers(login(client, u.email, PW))


# ---- busqueda -------------------------------------------------------------
def test_search_email_no_distingue_existente_de_inexistente(client, db):
    me = _mk(db, "me@t.com", "Yo Mismo")
    _mk(db, "secreto.persona@t.com", "Zeta Persona")
    h = _h(client, me)
    a = client.get("/api/community/search", params={"q": "secreto.persona@t.com"}, headers=h)
    b = client.get("/api/community/search", params={"q": "noexiste.nadie@t.com"}, headers=h)
    assert a.status_code == b.status_code == 200
    assert a.json()["results"] == b.json()["results"] == []
    assert a.json()["count"] == b.json()["count"] == 0


def test_search_por_nombre_funciona_y_oculta_ctl_no_compartido(client, db):
    me = _mk(db, "me@t.com", "Yo Mismo")
    _mk(db, "a@t.com", "Carla Fondista")
    priv = _mk(db, "b@t.com", "Carla Privada",
               community_share_prefs=json.dumps({"share_details": False}))
    r = client.get("/api/community/search", params={"q": "Carla"}, headers=_h(client, me))
    names = {x["name"] for x in r.json()["results"]}
    assert names == {"Carla Fondista", "Carla Privada"}
    for x in r.json()["results"]:
        assert "email" not in x
        if x["id"] == priv.id:
            assert x["ctl"] is None


def test_search_excluye_inactivos(client, db):
    me = _mk(db, "me@t.com", "Yo Mismo")
    u = _mk(db, "x@t.com", "Dormido Perez")
    u.activo = False
    db.commit()
    r = client.get("/api/community/search", params={"q": "Dormido"}, headers=_h(client, me))
    assert r.json()["results"] == []


# ---- perfil ---------------------------------------------------------------
def _act(db, uid):
    db.add(GarminActivity(user_id=uid, activity_id="act-" + uid[:6],
                          date_iso=date.today().isoformat(),
                          sport="run", dist_km=10.0, dur_min=60, tss=50.0))
    db.commit()


def test_perfil_respeta_share_prefs(client, db):
    me = _mk(db, "me@t.com", "Yo Mismo")
    pub = _mk(db, "p@t.com", "Publico")
    priv = _mk(db, "q@t.com", "Privado",
               community_share_prefs=json.dumps({"share_details": False}))
    _act(db, pub.id)
    _act(db, priv.id)
    h = _h(client, me)
    ok = client.get(f"/api/community/profile/{pub.id}", headers=h).json()
    assert ok["season_stats"]["km"] == 10.0
    no = client.get(f"/api/community/profile/{priv.id}", headers=h)
    assert no.status_code == 200
    assert no.json()["season_stats"] is None
    assert no.json()["stats_shared"] is False


def test_perfil_propio_y_coach_ven_stats(client, db):
    priv = _mk(db, "q@t.com", "Privado",
               community_share_prefs=json.dumps({"share_details": False}))
    coach = _mk(db, "c@t.com", "Coach", rol="coach")
    db.add(CoachAthlete(coach_id=coach.id, athlete_id=priv.id, activo=True, status="active"))
    db.commit()
    _act(db, priv.id)
    assert client.get("/api/community/profile/me", headers=_h(client, priv)).json()["season_stats"]["km"] == 10.0
    assert client.get(f"/api/community/profile/{priv.id}", headers=_h(client, coach)).json()["season_stats"]["km"] == 10.0


# ---- posts / comentarios ----------------------------------------------------
def _post(db, uid, vis):
    p = CommunityPost(user_id=uid, post_type="note", body="hola", visibility=vis)
    db.add(p)
    db.commit()
    db.refresh(p)
    db.add(Comment(post_id=p.id, user_id=uid, body="comentario"))
    db.commit()
    return p


def test_post_followers_invisible_a_no_seguidores(client, db):
    owner = _mk(db, "o@t.com", "Owner")
    fan = _mk(db, "f@t.com", "Seguidor")
    ext = _mk(db, "e@t.com", "Extrano")
    db.add(Follow(follower_id=fan.id, followed_id=owner.id))
    db.commit()
    p = _post(db, owner.id, "followers")
    assert client.get(f"/api/community/posts/{p.id}", headers=_h(client, ext)).status_code == 403
    assert client.get(f"/api/community/posts/{p.id}", headers=_h(client, fan)).status_code == 200
    assert client.get(f"/api/community/posts/{p.id}", headers=_h(client, owner)).status_code == 200


def test_comentarios_sin_acceso_al_post(client, db):
    owner = _mk(db, "o@t.com", "Owner")
    ext = _mk(db, "e@t.com", "Extrano")
    for vis in ("followers", "private", "coach_only"):
        p = _post(db, owner.id, vis)
        assert client.get(f"/api/community/posts/{p.id}/comments", headers=_h(client, ext)).status_code == 403
        assert len(client.get(f"/api/community/posts/{p.id}/comments", headers=_h(client, owner)).json()) == 1
    pub = _post(db, owner.id, "public")
    assert len(client.get(f"/api/community/posts/{pub.id}/comments", headers=_h(client, ext)).json()) == 1
    assert client.get("/api/community/posts/nope/comments", headers=_h(client, ext)).status_code == 404


# ---- grupos privados --------------------------------------------------------
def _group(db, owner, private):
    g = CommunityGroup(owner_id=owner.id, name="G-" + str(private), is_private=private,
                       invite_code="inv" + str(private))
    db.add(g)
    db.commit()
    db.refresh(g)
    db.add(CommunityGroupMember(group_id=g.id, user_id=owner.id, role="admin"))
    ch = Challenge(group_id=g.id, creator_id=owner.id, name="Reto", metric="km", target=100.0,
                   start_date="2026-01-01", end_date="2026-12-31")
    db.add(ch)
    db.commit()
    db.refresh(ch)
    db.add(ChallengeEntry(challenge_id=ch.id, user_id=owner.id))
    db.commit()
    return g, ch


def _group_urls(g, ch):
    return (f"/api/community/groups/{g.id}", f"/api/community/groups/{g.id}/members",
            f"/api/community/groups/{g.id}/challenges",
            f"/api/community/challenges/{ch.id}/leaderboard")


def test_grupo_privado_rechaza_no_miembros(client, db):
    owner = _mk(db, "o@t.com", "Owner")
    ext = _mk(db, "e@t.com", "Extrano")
    g, ch = _group(db, owner, True)
    for url in _group_urls(g, ch):
        assert client.get(url, headers=_h(client, ext)).status_code == 403, url
    for url in _group_urls(g, ch):
        assert client.get(url, headers=_h(client, owner)).status_code == 200, url


def test_grupo_publico_sigue_abierto(client, db):
    owner = _mk(db, "o@t.com", "Owner")
    ext = _mk(db, "e@t.com", "Extrano")
    g, ch = _group(db, owner, False)
    for url in _group_urls(g, ch):
        assert client.get(url, headers=_h(client, ext)).status_code == 200, url


# ---- mensajes ---------------------------------------------------------------
def test_mensaje_a_desconocido_se_rechaza(client, db):
    a = _mk(db, "a@t.com", "A")
    b = _mk(db, "b@t.com", "B")
    r = client.post("/api/messages", json={"to_user_id": b.id, "body": "hola"}, headers=_h(client, a))
    assert r.status_code == 404
    ghost = client.post("/api/messages", json={"to_user_id": "no-existe", "body": "hola"},
                        headers=_h(client, a))
    assert ghost.status_code == 404 and ghost.json()["errors"] == r.json()["errors"]
    assert db.query(Message).count() == 0


def test_mensaje_coach_atleta_activo_en_ambas_direcciones(client, db):
    coach = _mk(db, "c@t.com", "Coach", rol="coach")
    ath = _mk(db, "a@t.com", "Atl")
    db.add(CoachAthlete(coach_id=coach.id, athlete_id=ath.id, activo=True, status="active"))
    db.commit()
    assert client.post("/api/messages", json={"to_user_id": ath.id, "body": "x"}, headers=_h(client, coach)).status_code == 201
    assert client.post("/api/messages", json={"to_user_id": coach.id, "body": "y"}, headers=_h(client, ath)).status_code == 201


def test_mensaje_relacion_pendiente_no_basta(client, db):
    coach = _mk(db, "c@t.com", "Coach", rol="coach")
    ath = _mk(db, "a@t.com", "Atl")
    db.add(CoachAthlete(coach_id=coach.id, athlete_id=ath.id, activo=True, status="pending"))
    db.commit()
    assert client.post("/api/messages", json={"to_user_id": ath.id, "body": "x"}, headers=_h(client, coach)).status_code == 404


def test_mensaje_hilo_previo_permite_responder(client, db):
    a = _mk(db, "a@t.com", "A")
    b = _mk(db, "b@t.com", "B")
    db.add(Message(from_user_id=a.id, to_user_id=b.id, body="antiguo"))
    db.commit()
    assert client.post("/api/messages", json={"to_user_id": a.id, "body": "re"}, headers=_h(client, b)).status_code == 201


def test_mensaje_admin_puede_escribir(client, db):
    adm = _mk(db, "ad@t.com", "Adm", rol="admin")
    b = _mk(db, "b@t.com", "B")
    assert client.post("/api/messages", json={"to_user_id": b.id, "body": "soporte"}, headers=_h(client, adm)).status_code == 201
