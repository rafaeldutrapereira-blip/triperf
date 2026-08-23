"""
Tests de autenticación: login, logout, register, 2FA, rate limit, reset password.
"""
import pytest
from .conftest import login, auth_headers


class TestLogin:
    def test_login_success(self, client, athlete_user):
        r = client.post("/api/auth/login", json={
            "email": "athlete@test.com",
            "password": "AthlPass123",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["access_token"]
        assert data["rol"] == "athlete"
        assert data["nombre"] == "Athlete Test"

    def test_login_wrong_password(self, client, athlete_user):
        r = client.post("/api/auth/login", json={
            "email": "athlete@test.com",
            "password": "WrongPassword",
        })
        assert r.status_code == 401
        msg = r.json()["errors"][0]["message"].lower()
        assert "inválidas" in msg or "incorrecta" in msg

    def test_login_nonexistent_email(self, client):
        r = client.post("/api/auth/login", json={
            "email": "noexiste@test.com",
            "password": "cualquiercosa",
        })
        assert r.status_code == 401

    def test_login_inactive_user(self, client, db, athlete_user):
        athlete_user.activo = False
        db.commit()
        r = client.post("/api/auth/login", json={
            "email": "athlete@test.com",
            "password": "AthlPass123",
        })
        assert r.status_code == 403

    def test_login_sets_cookie(self, client, athlete_user):
        r = client.post("/api/auth/login", json={
            "email": "athlete@test.com",
            "password": "AthlPass123",
        })
        assert r.status_code == 200
        assert "lx_access_token" in r.cookies

    def test_login_case_insensitive_email(self, client, athlete_user):
        r = client.post("/api/auth/login", json={
            "email": "ATHLETE@TEST.COM",
            "password": "AthlPass123",
        })
        assert r.status_code == 200


class TestNewDeviceDetection:
    """El correo de "nuevo dispositivo" no debe dispararse en cada login --
    solo cuando el navegador no trae la cookie lx_device_id de un
    dispositivo ya conocido. Antes se basaba en IP+user-agent, lo que
    disparaba una alerta en CADA login desde redes móviles (la IP cambia
    todo el tiempo por NAT de carrier)."""

    def _login(self, client, device_id=None):
        """client conserva cookies entre requests (jar de sesión) -- hay que
        limpiarlas explícitamente para simular "otro dispositivo" sin cookie,
        y setear la cookie a mano para simular volver a un dispositivo conocido."""
        client.cookies.clear()
        if device_id:
            client.cookies.set("lx_device_id", device_id)
        return client.post("/api/auth/login", json={"email": "athlete@test.com", "password": "AthlPass123"})

    def test_first_login_ever_does_not_alert(self, client, athlete_user, monkeypatch):
        calls = []
        monkeypatch.setattr("api.routes.auth_routes.send_login_alert", lambda *a, **k: calls.append(a))
        r = self._login(client)
        assert r.status_code == 200
        assert "lx_device_id" in r.cookies
        assert calls == []

    def test_same_device_cookie_does_not_realert(self, client, athlete_user, monkeypatch):
        calls = []
        monkeypatch.setattr("api.routes.auth_routes.send_login_alert", lambda *a, **k: calls.append(a))
        r1 = self._login(client)
        device_id = r1.cookies.get("lx_device_id")

        r2 = self._login(client, device_id=device_id)
        assert r2.status_code == 200
        assert calls == []  # mismo dispositivo, nunca alertó

    def test_missing_cookie_after_known_device_triggers_alert(self, client, athlete_user, monkeypatch):
        calls = []
        monkeypatch.setattr("api.routes.auth_routes.send_login_alert", lambda *a, **k: calls.append(a))
        self._login(client)  # dispositivo 1, registra sin alertar

        r2 = self._login(client)  # sin cookie -> "otro" dispositivo
        assert r2.status_code == 200
        assert len(calls) == 1

    def test_alternating_between_two_known_devices_does_not_realert(self, client, athlete_user, monkeypatch):
        calls = []
        monkeypatch.setattr("api.routes.auth_routes.send_login_alert", lambda *a, **k: calls.append(a))
        r1 = self._login(client)  # celular, dispositivo 1 (sin alerta, primer login)
        device_a = r1.cookies.get("lx_device_id")

        r2 = self._login(client)  # notebook, sin cookie -> dispositivo 2 (alerta 1)
        device_b = r2.cookies.get("lx_device_id")
        assert len(calls) == 1

        r3 = self._login(client, device_id=device_a)  # vuelve al celular
        assert len(calls) == 1  # sigue siendo 1 -- ya lo conocía

        r4 = self._login(client, device_id=device_b)  # vuelve a la notebook
        assert len(calls) == 1  # tampoco vuelve a alertar

    def test_legacy_hash_format_does_not_crash_login(self, client, athlete_user, db):
        """Regresión real: cuentas que ya tenían un login registrado ANTES
        de este cambio guardan el hash SHA-256 viejo (string de 16 hex
        chars, no JSON) en last_device_hash -- json.loads() sobre eso
        rompía el login con 500 para cualquier cuenta ya usada (bug
        reportado en vivo: "Error interno del servidor")."""
        athlete_user.last_device_hash = "a3f9c21b8e0d1234"  # formato viejo real
        db.commit()

        r = self._login(client)
        assert r.status_code == 200, r.text
        assert "lx_device_id" in r.cookies
    def test_me_authenticated(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/auth/me", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()["email"] == "athlete@test.com"

    def test_me_unauthenticated(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_me_invalid_token(self, client):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer token-invalido"})
        assert r.status_code == 401


class TestLogout:
    def test_logout_clears_cookie(self, client, athlete_user):
        r = client.post("/api/auth/login", json={
            "email": "athlete@test.com", "password": "AthlPass123",
        })
        assert r.status_code == 200
        r2 = client.post("/api/auth/logout")
        assert r2.status_code == 200
        assert r2.json()["ok"] is True

    def test_token_invalid_after_logout(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        client.post("/api/auth/logout", headers=auth_headers(token))
        # El token ahora debe estar en la blacklist
        r = client.get("/api/auth/me", headers=auth_headers(token))
        assert r.status_code == 401


class TestRegister:
    def test_register_success(self, client):
        r = client.post("/api/auth/register", json={
            "email": "nuevo@test.com",
            "nombre": "Nuevo Atleta",
            "password": "Password123",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["access_token"]
        assert data["rol"] == "atleta"

    def test_register_duplicate_email(self, client, athlete_user):
        r = client.post("/api/auth/register", json={
            "email": "athlete@test.com",
            "nombre": "Otro",
            "password": "Password123",
        })
        assert r.status_code == 409

    def test_register_short_password(self, client):
        r = client.post("/api/auth/register", json={
            "email": "otro@test.com",
            "nombre": "Test",
            "password": "1234567",  # 7 chars — debe fallar
        })
        assert r.status_code == 422


class TestRevokeAll:
    def test_revoke_all_invalidates_old_tokens(self, client, athlete_user):
        token1 = login(client, "athlete@test.com", "AthlPass123")
        # Revocar todas las sesiones
        r = client.post("/api/auth/revoke-all", headers=auth_headers(token1))
        assert r.status_code == 200
        new_token = r.json()["access_token"]
        # Clear the cookie that revoke-all set so we can test the old header token
        # (_extract_token prefers cookie over header, so without this the new
        # cookie would be used instead of the old token1 we're trying to test)
        client.cookies.clear()
        # Token viejo debe fallar
        r2 = client.get("/api/auth/me", headers=auth_headers(token1))
        assert r2.status_code == 401
        # Token nuevo debe funcionar
        r3 = client.get("/api/auth/me", headers=auth_headers(new_token))
        assert r3.status_code == 200


class TestChangePassword:
    def test_change_password_success(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/auth/change-password",
            json={"old_password": "AthlPass123", "new_password": "NewPassword456"},
            headers=auth_headers(token))
        assert r.status_code == 200
        # Verificar que puede logearse con la nueva contraseña
        r2 = client.post("/api/auth/login", json={
            "email": "athlete@test.com", "password": "NewPassword456",
        })
        assert r2.status_code == 200

    def test_change_password_wrong_old(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/auth/change-password",
            json={"old_password": "Incorrecta", "new_password": "NewPass123"},
            headers=auth_headers(token))
        assert r.status_code == 400

    def test_change_password_too_short(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/auth/change-password",
            json={"old_password": "AthlPass123", "new_password": "123"},
            headers=auth_headers(token))
        assert r.status_code == 422


class TestForgotReset:
    def test_forgot_password_always_ok(self, client):
        r = client.post("/api/auth/forgot-password", json={"email": "noexiste@test.com"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_reset_password_invalid_token(self, client):
        r = client.post("/api/auth/reset-password", json={
            "token": "token-invalido",
            "password": "NewPassword123",
        })
        assert r.status_code == 400

    def test_reset_password_flow(self, client, db, athlete_user):
        from datetime import datetime, timedelta, timezone
        from api.auth import _token_hash
        from api.models import PasswordResetToken
        # Crear token directamente en DB
        raw = "test-reset-token-12345"
        db.add(PasswordResetToken(
            token_hash=_token_hash(raw),
            user_id=athlete_user.id,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        ))
        db.commit()
        r = client.post("/api/auth/reset-password", json={
            "token": raw,
            "password": "ResetPassword123",
        })
        assert r.status_code == 200
        # Puede logearse con nueva contraseña
        r2 = client.post("/api/auth/login", json={
            "email": "athlete@test.com", "password": "ResetPassword123",
        })
        assert r2.status_code == 200


class TestRoleAuthorization:
    def test_athlete_cannot_access_admin(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/admin/users", headers=auth_headers(token))
        assert r.status_code == 403

    def test_athlete_cannot_access_coach_endpoints(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/coach/athletes", headers=auth_headers(token))
        assert r.status_code == 403

    def test_admin_can_access_admin(self, client, admin_user):
        token = login(client, "admin@test.com", "AdminPass123")
        r = client.get("/api/admin/users", headers=auth_headers(token))
        assert r.status_code == 200
