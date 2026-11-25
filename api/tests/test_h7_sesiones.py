"""H7-SESIONES: cambiar/resetear la contrasena invalida las sesiones previas."""
from datetime import datetime, timedelta, timezone

from api.auth import _token_hash
from api.models import PasswordResetToken
from api.tests.conftest import login, auth_headers

EMAIL, OLD, NEW = "athlete@test.com", "AthlPass123", "NuevaClave456"


def _ok(client, tok):
    client.cookies.clear()  # la cookie reemitida tiene prioridad sobre el header; probar solo el bearer
    return client.get("/api/auth/me", headers=auth_headers(tok)).status_code


def test_change_password_revoca_tokens_previos(client, athlete_user):
    t1 = login(client, EMAIL, OLD)
    t2 = login(client, EMAIL, OLD)
    r = client.post("/api/auth/change-password", headers=auth_headers(t1),
                    json={"old_password": OLD, "new_password": NEW})
    assert r.status_code == 200
    assert _ok(client, t1) == 401
    assert _ok(client, t2) == 401
    # el token reemitido para quien cambia la clave si sirve
    assert _ok(client, r.json()["access_token"]) == 200


def test_reset_password_revoca_tokens_previos(client, db, athlete_user):
    t1 = login(client, EMAIL, OLD)
    assert _ok(client, t1) == 200
    raw = "h7-reset-token"
    db.add(PasswordResetToken(
        token_hash=_token_hash(raw), user_id=athlete_user.id,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)))
    db.commit()
    r = client.post("/api/auth/reset-password", json={"token": raw, "password": NEW})
    assert r.status_code == 200
    assert _ok(client, t1) == 401
    assert _ok(client, login(client, EMAIL, NEW)) == 200


def test_profile_sin_clave_actual_no_cambia_password(client, athlete_user):
    t = login(client, EMAIL, OLD)
    r = client.patch("/api/athlete/profile", headers=auth_headers(t), json={"password": NEW})
    assert r.status_code == 400
    assert _ok(client, t) == 200
    login(client, EMAIL, OLD)  # la clave vieja sigue vigente


def test_profile_con_clave_actual_incorrecta_rechaza(client, athlete_user):
    t = login(client, EMAIL, OLD)
    r = client.patch("/api/athlete/profile", headers=auth_headers(t),
                     json={"password": NEW, "old_password": "Otra12345"})
    assert r.status_code == 400
    login(client, EMAIL, OLD)


def test_profile_aplica_politica_de_fortaleza(client, athlete_user):
    t = login(client, EMAIL, OLD)
    r = client.patch("/api/athlete/profile", headers=auth_headers(t),
                     json={"password": "debil", "old_password": OLD})
    assert r.status_code == 422
    login(client, EMAIL, OLD)


def test_profile_con_clave_actual_cambia_y_revoca(client, athlete_user):
    t1 = login(client, EMAIL, OLD)
    t2 = login(client, EMAIL, OLD)
    r = client.patch("/api/athlete/profile", headers=auth_headers(t1),
                     json={"password": NEW, "old_password": OLD})
    assert r.status_code == 200
    assert _ok(client, t1) == 401
    assert _ok(client, t2) == 401
    assert _ok(client, r.json()["access_token"]) == 200
    login(client, EMAIL, NEW)


def test_profile_sin_password_no_toca_sesiones(client, athlete_user):
    t = login(client, EMAIL, OLD)
    r = client.patch("/api/athlete/profile", headers=auth_headers(t), json={"weight_kg": 70})
    assert r.status_code == 200 and "access_token" not in r.json()
    assert _ok(client, t) == 200


def test_revoke_all_sigue_funcionando(client, athlete_user):
    t1 = login(client, EMAIL, OLD)
    r = client.post("/api/auth/revoke-all", headers=auth_headers(t1))
    assert r.status_code == 200
    assert _ok(client, t1) == 401
    assert _ok(client, r.json()["access_token"]) == 200
