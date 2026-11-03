"""CC5: tests de contrato de Comunidad contra los endpoints REALES (client + db).

test_community.py usa fakes en memoria y no detecto que Clubes/Desafios web
estaban rotos. Aqui se fija el contrato que consumen community.js / la app:
clubes (items, n_members, sport, is_private, join), desafios por club
(_ChallengeIn) y los campos del feed. La visibilidad/privacidad del feed vive
en test_comunidad_cc1.py y la forma n_comments/photos en
test_community_feed_integration.py; aqui se agrega un guard de forma completa.
"""
import pytest

from .conftest import login, auth_headers
from api.models import User, GarminActivity
from api.auth import hash_password


@pytest.fixture(autouse=True)
def _plan_agegroup(db, athlete_user):
    # Los endpoints de escritura exigen plan agegroup+; el fixture base es basico.
    athlete_user.plan_nivel = "agegroup"
    db.commit()


@pytest.fixture
def other_user(db) -> User:
    u = User(
        email="other@test.com", nombre="Other Test",
        password_hash=hash_password("OtherPass123"),
        rol="athlete", plan_nivel="agegroup", activo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _h(client, email="athlete@test.com", pw="AthlPass123"):
    token = login(client, email, pw)
    client.cookies.clear()  # la cookie de sesion pisaria al bearer del otro usuario
    return auth_headers(token)


def _create_club(client, h, **over):
    body = {"name": "Club Real", "sport": "running", "is_private": False}
    body.update(over)
    return client.post("/api/community/groups", json=body, headers=h)


def _challenge(**over):
    body = {"name": "Reto Noviembre", "metric": "km", "target": 100,
            "start_date": "2026-11-01", "end_date": "2026-11-30"}
    body.update(over)
    return body


# ── 1. Clubes ────────────────────────────────────────────────────────────────
class TestClubsContract:
    def test_list_returns_items_with_n_members(self, client, athlete_user):
        h = _h(client)
        assert _create_club(client, h).status_code == 201
        r = client.get("/api/community/groups", headers=h)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["items"], list) and len(data["items"]) == 1
        item = data["items"][0]
        for k in ("id", "name", "sport", "is_private", "n_members", "is_member", "owner_id"):
            assert k in item, f"falta {k} en el item de club"
        assert item["n_members"] == 1  # el creador queda como miembro
        assert item["is_member"] is True

    def test_create_respects_sport_and_privacy(self, client, athlete_user):
        h = _h(client)
        r = _create_club(client, h, name="Club Ciclismo Privado", sport="cycling", is_private=True)
        assert r.status_code == 201
        body = r.json()
        assert body["sport"] == "cycling"          # no el default "triathlon"
        assert body["is_private"] is True          # no el default publico
        assert body["invite_code"]                 # privado -> codigo para el creador
        assert body["n_members"] == 1

    def test_create_defaults_only_when_omitted(self, client, athlete_user):
        r = _h(client)
        r = client.post("/api/community/groups", json={"name": "Club Sin Deporte"}, headers=r)
        assert r.status_code == 201
        assert r.json()["sport"] == "triathlon" and r.json()["is_private"] is False

    def test_private_club_not_in_public_listing(self, client, athlete_user):
        h = _h(client)
        _create_club(client, h, name="Club Secreto", is_private=True)
        _create_club(client, h, name="Club Abierto")
        names = [i["name"] for i in client.get("/api/community/groups", headers=h).json()["items"]]
        assert names == ["Club Abierto"]
        mine = [i["name"] for i in client.get("/api/community/groups?mine=true", headers=h).json()["items"]]
        assert sorted(mine) == ["Club Abierto", "Club Secreto"]

    def test_create_rejects_short_name_and_duplicates(self, client, athlete_user):
        h = _h(client)
        assert _create_club(client, h, name="ab").status_code == 422
        assert _create_club(client, h).status_code == 201
        assert _create_club(client, h).status_code == 409

    def test_join_public_club_increments_members(self, client, athlete_user, other_user):
        gid = _create_club(client, _h(client)).json()["id"]
        h2 = _h(client, "other@test.com", "OtherPass123")
        r = client.post(f"/api/community/groups/{gid}/join", headers=h2)
        assert r.status_code == 200 and r.json()["ok"] is True
        item = client.get(f"/api/community/groups/{gid}", headers=h2).json()
        assert item["n_members"] == 2 and item["is_member"] is True
        # idempotente
        again = client.post(f"/api/community/groups/{gid}/join", headers=h2)
        assert again.json().get("already_member") is True

    def test_join_private_club_requires_invite_code(self, client, athlete_user, other_user):
        created = _create_club(client, _h(client), name="Club Con Codigo", is_private=True).json()
        h2 = _h(client, "other@test.com", "OtherPass123")
        assert client.post(f"/api/community/groups/{created['id']}/join", headers=h2).status_code == 403
        ok = client.post(f"/api/community/groups/{created['id']}/join?invite_code={created['invite_code']}",
                         headers=h2)
        assert ok.status_code == 200

    def test_join_unknown_club_404(self, client, athlete_user):
        assert client.post("/api/community/groups/no-existe/join", headers=_h(client)).status_code == 404


# ── 2. Desafios por club ─────────────────────────────────────────────────────
class TestChallengesContract:
    def test_create_and_list_with_real_payload(self, client, athlete_user):
        h = _h(client)
        gid = _create_club(client, h).json()["id"]
        r = client.post(f"/api/community/groups/{gid}/challenges", json=_challenge(), headers=h)
        assert r.status_code == 201
        assert r.json()["ok"] is True and r.json()["challenge_id"]
        lst = client.get(f"/api/community/groups/{gid}/challenges", headers=h)
        assert lst.status_code == 200
        items = lst.json()
        assert isinstance(items, list) and len(items) == 1
        ch = items[0]
        assert ch["name"] == "Reto Noviembre" and ch["metric"] == "km" and ch["target"] == 100
        for k in ("id", "sport", "start_date", "end_date", "is_active", "my_progress", "my_pct"):
            assert k in ch

    @pytest.mark.parametrize("metric", ["km", "tss", "activities", "hours"])
    def test_all_documented_metrics_accepted(self, client, athlete_user, metric):
        h = _h(client)
        gid = _create_club(client, h).json()["id"]
        r = client.post(f"/api/community/groups/{gid}/challenges", json=_challenge(metric=metric), headers=h)
        assert r.status_code == 201

    def test_invalid_metric_or_target_rejected(self, client, athlete_user):
        h = _h(client)
        gid = _create_club(client, h).json()["id"]
        url = f"/api/community/groups/{gid}/challenges"
        assert client.post(url, json=_challenge(metric="distance_km"), headers=h).status_code == 422
        assert client.post(url, json=_challenge(target=0), headers=h).status_code == 422
        assert client.post(url, json=_challenge(target=-5), headers=h).status_code == 422

    def test_challenge_not_listed_outside_its_club(self, client, athlete_user):
        h = _h(client)
        g1 = _create_club(client, h, name="Club Uno").json()["id"]
        g2 = _create_club(client, h, name="Club Dos").json()["id"]
        client.post(f"/api/community/groups/{g1}/challenges", json=_challenge(name="Solo Club Uno"), headers=h)
        assert [c["name"] for c in client.get(f"/api/community/groups/{g1}/challenges", headers=h).json()] == ["Solo Club Uno"]
        assert client.get(f"/api/community/groups/{g2}/challenges", headers=h).json() == []

    def test_only_admin_or_coach_member_can_create(self, client, athlete_user, other_user):
        gid = _create_club(client, _h(client)).json()["id"]
        h2 = _h(client, "other@test.com", "OtherPass123")
        client.post(f"/api/community/groups/{gid}/join", headers=h2)  # miembro normal
        r = client.post(f"/api/community/groups/{gid}/challenges", json=_challenge(), headers=h2)
        assert r.status_code == 403

    def test_challenge_creates_entry_for_each_member(self, client, athlete_user, other_user):
        h = _h(client)
        gid = _create_club(client, h).json()["id"]
        h2 = _h(client, "other@test.com", "OtherPass123")
        client.post(f"/api/community/groups/{gid}/join", headers=h2)
        client.post(f"/api/community/groups/{gid}/challenges", json=_challenge(), headers=h)
        mine = client.get(f"/api/community/groups/{gid}/challenges", headers=h2).json()
        assert len(mine) == 1 and mine[0]["my_progress"] == 0


# ── 3. Feed: forma completa de la tarjeta ────────────────────────────────────
class TestFeedCardShape:
    def test_feed_card_has_n_comments_photos_can_add_photos(self, client, db, athlete_user):
        db.add(GarminActivity(user_id=athlete_user.id, activity_id="cc5-a1", name="Rodaje",
                              sport="run", date_iso="2026-11-01", dur_min=40, dist_km=7.0, tss=45))
        db.commit()
        r = client.get("/api/community/activity-feed", headers=_h(client))
        assert r.status_code == 200
        body = r.json()
        assert len(body["feed"]) == 1
        card = body["feed"][0]
        assert card["n_comments"] == 0
        assert card["can_add_photos"] is True
        assert card["photos"] == []
        # paginacion de CC1
        for k in ("has_more", "next_offset", "limit", "offset"):
            assert k in body
