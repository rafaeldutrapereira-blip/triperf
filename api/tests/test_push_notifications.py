"""
Fase 1 Sprint B (auditoria CPO 2026-08-11, Gap #2): push notifications
nativas. La infraestructura VAPID/PushSubscription/send_push_to_user ya
existia (usada por asignacion de workouts y recordatorio de bienestar) —
estos tests cubren lo agregado en este sprint: envio real via pywebpush
(mockeado, sin red), limpieza de suscripciones vencidas, y el enganche
nuevo de _notif() (community_routes.py) para que kudos/comentarios/
follows tambien disparen push, no solo la notificacion in-app.
"""
import time
from unittest.mock import patch, MagicMock

import pytest

from .conftest import login, auth_headers
from api.routes.notification_routes import PushSubscription, send_push_to_user
from api.models import User
from api.auth import hash_password


def _make_subscription(db, user_id, endpoint="https://push.example.com/ep1"):
    import uuid
    sub = PushSubscription(
        id=str(uuid.uuid4()), user_id=user_id,
        endpoint=endpoint, p256dh="p256dh-fake", auth_key="auth-fake",
    )
    db.add(sub)
    db.commit()
    return sub


class TestSendPushToUser:
    def test_no_vapid_key_configured_returns_zero(self, db, athlete_user):
        _make_subscription(db, athlete_user.id)
        with patch("api.routes.notification_routes.VAPID_PRIVATE_KEY", ""):
            sent = send_push_to_user(athlete_user.id, {"title": "x", "body": "y"}, db)
        assert sent == 0

    def test_sends_to_all_subscriptions(self, db, athlete_user):
        _make_subscription(db, athlete_user.id, endpoint="https://push.example.com/a")
        _make_subscription(db, athlete_user.id, endpoint="https://push.example.com/b")
        with patch("api.routes.notification_routes.VAPID_PRIVATE_KEY", "fake-key"), \
             patch("pywebpush.webpush") as mock_webpush:
            sent = send_push_to_user(athlete_user.id, {"title": "x", "body": "y"}, db)
        assert sent == 2
        assert mock_webpush.call_count == 2

    def test_expired_subscription_gets_deleted(self, db, athlete_user):
        sub = _make_subscription(db, athlete_user.id)
        sub_id = sub.id
        from pywebpush import WebPushException
        fake_resp = MagicMock(status_code=410)
        exc = WebPushException("gone", response=fake_resp)
        with patch("api.routes.notification_routes.VAPID_PRIVATE_KEY", "fake-key"), \
             patch("pywebpush.webpush", side_effect=exc):
            sent = send_push_to_user(athlete_user.id, {"title": "x", "body": "y"}, db)
        assert sent == 0
        remaining = db.query(PushSubscription).filter(PushSubscription.id == sub_id).first()
        assert remaining is None

    def test_no_subscriptions_returns_zero(self, db, athlete_user):
        with patch("api.routes.notification_routes.VAPID_PRIVATE_KEY", "fake-key"):
            sent = send_push_to_user(athlete_user.id, {"title": "x", "body": "y"}, db)
        assert sent == 0


class TestVapidPublicKeyEndpoint:
    def test_returns_503_when_not_configured(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        with patch("api.routes.notification_routes.VAPID_PUBLIC_KEY", ""):
            r = client.get("/api/notifications/vapid-public-key", headers=auth_headers(token))
        assert r.status_code == 503

    def test_returns_key_when_configured(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        with patch("api.routes.notification_routes.VAPID_PUBLIC_KEY", "fake-public-key"):
            r = client.get("/api/notifications/vapid-public-key", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()["vapid_public_key"] == "fake-public-key"


class TestSubscribeUnsubscribe:
    def test_subscribe_then_unsubscribe(self, client, db, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/notifications/subscribe", json={
            "endpoint": "https://push.example.com/xyz",
            "p256dh": "p256dh-val", "auth_key": "auth-val",
        }, headers=auth_headers(token))
        assert r.status_code == 201
        assert db.query(PushSubscription).filter(PushSubscription.user_id == athlete_user.id).count() == 1

        r2 = client.delete("/api/notifications/unsubscribe?endpoint=https://push.example.com/xyz",
                            headers=auth_headers(token))
        assert r2.status_code == 200
        assert db.query(PushSubscription).filter(PushSubscription.user_id == athlete_user.id).count() == 0

    def test_subscribe_upserts_existing_endpoint(self, client, db, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        payload = {"endpoint": "https://push.example.com/same", "p256dh": "old", "auth_key": "old"}
        client.post("/api/notifications/subscribe", json=payload, headers=auth_headers(token))
        payload["p256dh"] = "new"
        client.post("/api/notifications/subscribe", json=payload, headers=auth_headers(token))
        rows = db.query(PushSubscription).filter(PushSubscription.user_id == athlete_user.id).all()
        assert len(rows) == 1
        assert rows[0].p256dh == "new"


class TestSocialPushIntegration:
    """El enganche nuevo de este sprint: _notif() (community_routes.py)
    ahora tambien dispara send_push_to_user en un hilo de background,
    ademas de la notificacion in-app que ya existia. Verifica que el
    kudo de un atleta a otro efectivamente llama a la funcion de push
    con el payload correcto — sin isolar esto en un modulo aparte, es
    el mismo mecanismo que ya usa la asignacion de workouts."""

    def test_kudo_triggers_push_to_post_owner(self, client, db, athlete_user):
        other = User(
            email="other@test.com", nombre="Other Athlete",
            password_hash=hash_password("OtherPass123"),
            rol="athlete", activo=True,
        )
        db.add(other)
        db.commit()

        owner_token = login(client, "athlete@test.com", "AthlPass123")
        r_post = client.post("/api/community/posts",
            json={"body": "Corrida de hoy", "post_type": "note"},
            headers=auth_headers(owner_token))
        assert r_post.status_code == 201
        post_id = r_post.json()["id"]

        other_token = login(client, "other@test.com", "OtherPass123")
        with patch("api.routes.notification_routes.send_push_to_user") as mock_push:
            r_kudo = client.post(f"/api/community/posts/{post_id}/kudo",
                json={"kudo_type": "fire"},
                headers=auth_headers(other_token))
            assert r_kudo.status_code == 201
            time.sleep(0.3)  # el push corre en un hilo de background
        assert mock_push.call_count == 1
        call_args = mock_push.call_args[0]
        assert call_args[0] == athlete_user.id  # dueño del post, no quien dio el kudo
        payload = call_args[1]
        assert payload["type"] == "community"
        assert payload["title"] == "Nuevo kudo"
        assert payload["url"] == "/community.html"

    def test_self_kudo_does_not_notify(self, client, db, athlete_user):
        """_notif() ya cortaba esto antes (if user_id == actor_id: return)
        — confirma que el push nuevo respeta la misma regla, no hay
        forma de auto-notificarse dando kudo a la propia actividad."""
        token = login(client, "athlete@test.com", "AthlPass123")
        r_post = client.post("/api/community/posts",
            json={"body": "Mi propia actividad", "post_type": "note"},
            headers=auth_headers(token))
        post_id = r_post.json()["id"]
        with patch("api.routes.notification_routes.send_push_to_user") as mock_push:
            client.post(f"/api/community/posts/{post_id}/kudo",
                json={"kudo_type": "power"}, headers=auth_headers(token))
            time.sleep(0.2)
        assert mock_push.call_count == 0
