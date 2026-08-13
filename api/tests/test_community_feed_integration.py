"""
Tests de integración real (client+db) para GET /community/activity-feed —
antes de esta sesión (2026-08-13) este endpoint no tenía NINGUNA cobertura
de integración, solo unit tests con objetos fake (ver test_community.py).
Se agregan acá al conectar el feed de la app móvil (Comunidad: fotos +
comentarios) para no dejar sin probar el campo n_comments nuevo, ni la
forma real de photos/can_add_photos que ya usaba community.html (web) y
la app nunca leía.
"""
from .conftest import login, auth_headers
from api.models import Follow, GarminActivity, ActivityPhoto


def _make_activity(user_id, activity_id="act-feed-1", sport="run", date_iso="2026-08-10"):
    return GarminActivity(
        user_id=user_id, activity_id=activity_id, name="Easy Run",
        sport=sport, date_iso=date_iso, dur_min=45, dist_km=8.0, tss=50,
    )


class TestActivityFeedIntegration:
    def test_feed_includes_own_activity_with_zero_comments(self, client, db, athlete_user):
        db.add(_make_activity(athlete_user.id))
        db.commit()

        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/community/activity-feed", headers=auth_headers(token))
        assert r.status_code == 200
        feed = r.json()["feed"]
        assert len(feed) == 1
        assert feed[0]["n_comments"] == 0
        assert feed[0]["can_add_photos"] is True
        assert feed[0]["photos"] == []

    def test_feed_n_comments_reflects_real_comments(self, client, db, athlete_user):
        db.add(_make_activity(athlete_user.id))
        db.commit()
        token = login(client, "athlete@test.com", "AthlPass123")

        r_feed = client.get("/api/community/activity-feed", headers=auth_headers(token))
        post_id = r_feed.json()["feed"][0]["id"]

        client.post(f"/api/community/posts/{post_id}/comments",
                    json={"body": "Buen ritmo!"}, headers=auth_headers(token))
        client.post(f"/api/community/posts/{post_id}/comments",
                    json={"body": "Segundo comentario"}, headers=auth_headers(token))

        r_feed2 = client.get("/api/community/activity-feed", headers=auth_headers(token))
        assert r_feed2.json()["feed"][0]["n_comments"] == 2

    def test_comment_author_field_matches_frontend_expectation(self, client, db, athlete_user):
        """Bug real encontrado auditando community.html: el frontend leía
        c.author_name/c.user_name, pero el backend siempre devolvió
        "author" — este test fija el contrato real para que no vuelva a
        divergir entre frontend y backend."""
        db.add(_make_activity(athlete_user.id))
        db.commit()
        token = login(client, "athlete@test.com", "AthlPass123")
        post_id = client.get("/api/community/activity-feed",
                              headers=auth_headers(token)).json()["feed"][0]["id"]

        r = client.post(f"/api/community/posts/{post_id}/comments",
                         json={"body": "hola"}, headers=auth_headers(token))
        assert r.status_code == 201
        body = r.json()
        assert body["author"] == athlete_user.nombre
        assert "author_name" not in body
        assert "user_name" not in body

    def test_can_add_photos_false_for_someone_elses_activity(self, client, db, athlete_user, coach_user):
        """can_add_photos solo debe ser True para el dueño de la
        actividad — coach_user sigue a athlete_user y ve su feed, pero no
        puede subir fotos a una actividad ajena."""
        db.add(Follow(follower_id=coach_user.id, followed_id=athlete_user.id))
        db.add(_make_activity(athlete_user.id))
        db.commit()

        coach_token = login(client, "coach@test.com", "CoachPass123")
        r = client.get("/api/community/activity-feed", headers=auth_headers(coach_token))
        feed = [c for c in r.json()["feed"] if c["activity_id"] == "act-feed-1"]
        assert len(feed) == 1
        assert feed[0]["can_add_photos"] is False

    def test_manual_photo_appears_in_feed_with_deletable_flag(self, client, db, athlete_user):
        act = _make_activity(athlete_user.id)
        db.add(act)
        db.flush()
        db.add(ActivityPhoto(activity_id=act.id, user_id=athlete_user.id, storage_key="fake/key.jpg"))
        db.commit()

        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/community/activity-feed", headers=auth_headers(token))
        photos = r.json()["feed"][0]["photos"]
        assert len(photos) == 1
        assert photos[0]["deletable"] is True
        assert photos[0]["photo_id"] is not None
