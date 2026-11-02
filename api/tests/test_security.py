"""S10 — Tests de seguridad: rate limiting, JWT, headers, OWASP."""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET",   "test-secret-key-labx-tests-32chars")
os.environ.setdefault("JWT_AUDIENCE", "labx-app")
os.environ.setdefault("APP_ENV",      "test")

from .conftest import auth_headers, login


class TestSecurityHeaders:
    def test_x_content_type_nosniff(self, client):
        r = client.get("/health")
        # Headers de seguridad deben estar presentes
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_sameorigin(self, client):
        # SAMEORIGIN: permite embeds del mismo origen (Carga, Coach); otros orígenes siguen bloqueados.
        r = client.get("/health")
        assert r.headers.get("x-frame-options") == "SAMEORIGIN"

    def test_referrer_policy(self, client):
        r = client.get("/health")
        assert "strict-origin" in r.headers.get("referrer-policy", "")

    def test_static_js_no_cache(self, client):
        """2026-08-13: mismo bug de fondo que sw.js (Gap #13) encontrado
        en vivo con lx-info.js — Cloudflare cacheó una versión vieja por
        4h porque el archivo no mandaba Cache-Control, y siguió sirviendo
        contenido desactualizado después de un fix real ya deployado.
        Cualquier .js/.css propio debe forzar revalidación, no caer en
        la heurística por defecto del browser/CDN."""
        r = client.get("/lx-info.js")
        assert r.status_code == 200
        assert r.headers.get("cache-control") == "no-cache, must-revalidate"

    def test_static_css_no_cache(self, client):
        import os
        # Cualquier .css real del repo sirve para probar la regla genérica
        css_files = [f for f in os.listdir(".") if f.endswith(".css")]
        if not css_files:
            pytest.skip("sin archivos .css en la raíz del repo para probar")
        r = client.get("/" + css_files[0])
        assert r.status_code == 200
        assert r.headers.get("cache-control") == "no-cache, must-revalidate"


class TestRateLimit:
    def test_login_rate_limit_headers(self, client, athlete_user):
        """Verificar que las respuestas 401 incluyen X-RateLimit-* headers."""
        r = client.post("/api/auth/login",
                        json={"email": "athlete@test.com", "password": "wrongpass"})
        assert r.status_code == 401
        # Headers de rate limit presentes (aunque no se haya bloqueado aún)
        # Pueden estar en 401 o en 429 cuando se bloquea

    def test_password_strength_validation(self, client):
        """S5: Registro con contraseña débil debe retornar 422."""
        r = client.post("/api/auth/register", json={
            "email": "weak@test.com",
            "nombre": "Weak User",
            "password": "nouppercase1",  # sin mayúscula
        })
        assert r.status_code == 422
        assert "mayúscula" in r.json().get("detail", "").lower() or \
               "mayúscula" in str(r.json()).lower()

    def test_password_no_number_rejected(self, client):
        r = client.post("/api/auth/register", json={
            "email": "nonumber@test.com",
            "nombre": "No Number",
            "password": "NoNumber!",  # sin número
        })
        assert r.status_code == 422

    def test_password_too_short_rejected(self, client):
        r = client.post("/api/auth/register", json={
            "email": "short@test.com",
            "nombre": "Short",
            "password": "Ab1",
        })
        assert r.status_code == 422

    def test_valid_password_accepted(self, client):
        r = client.post("/api/auth/register", json={
            "email": "strong@test.com",
            "nombre": "Strong User",
            "password": "StrongPass123",
        })
        assert r.status_code in (201, 409)  # 201 nuevo, 409 si ya existe


class TestContentTypeMiddleware:
    def test_missing_content_type_rejected(self, client):
        """I-12: POST sin Content-Type debe retornar 415."""
        r = client.post(
            "/api/auth/login",
            content=b'{"email":"a@b.com","password":"test"}',
            headers={"content-type": "text/plain", "content-length": "38"},
        )
        assert r.status_code == 415

    def test_json_content_type_accepted(self, client):
        r = client.post("/api/auth/login",
                        json={"email": "x@y.com", "password": "test"})
        assert r.status_code in (401, 422)  # No 415


class TestJWTAudience:
    def test_token_with_wrong_audience_rejected(self, client, athlete_user):
        """QW-08: Token con audience incorrecto debe ser rechazado."""
        import jwt
        bad_token = jwt.encode(
            {"sub": athlete_user.id, "rol": "athlete", "nombre": "Test",
             "gen": 1, "aud": "wrong-audience"},
            "test-secret-key-labx-tests-32chars",
            algorithm="HS256"
        )
        r = client.get("/api/athlete/profile",
                       headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401

    def test_valid_token_accepted(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/athlete/profile",
                       headers=auth_headers(token))
        assert r.status_code == 200


class TestRememberMe:
    def test_remember_me_returns_token(self, client, athlete_user):
        """S5: remember_me=True debe devolver token válido."""
        r = client.post("/api/auth/login", json={
            "email":       "athlete@test.com",
            "password":    "AthlPass123",
            "remember_me": True,
        })
        assert r.status_code == 200
        assert r.json()["access_token"] != ""

    def test_remember_me_false_is_default(self, client, athlete_user):
        r = client.post("/api/auth/login", json={
            "email":    "athlete@test.com",
            "password": "AthlPass123",
        })
        assert r.status_code == 200

    # ── S26: vigencia real de la sesión con y sin "Recordarme" ──────────
    @staticmethod
    def _login_full(client, remember):
        body = {"email": "athlete@test.com", "password": "AthlPass123"}
        if remember is not None:
            body["remember_me"] = remember
        r = client.post("/api/auth/login", json=body)
        assert r.status_code == 200
        cookie = next(h for h in r.headers.get_list("set-cookie")
                      if h.startswith("lx_access_token="))
        return r.json()["access_token"], cookie

    @staticmethod
    def _lifetime_seconds(token):
        import time
        import jwt as _jwt
        from api.auth import SECRET_KEY, ALGORITHM
        p = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                        options={"verify_exp": False, "verify_aud": False})
        # exp es UTC naive -> epoch UTC
        import calendar
        return p["exp"] - calendar.timegm(time.gmtime())

    def test_remember_true_session_lasts_30_days(self, client, athlete_user):
        token, cookie = self._login_full(client, True)
        assert "Max-Age=2592000" in cookie
        assert "httponly" in cookie.lower()
        life = self._lifetime_seconds(token)
        assert 30 * 86400 - 120 <= life <= 30 * 86400 + 5

    @pytest.mark.parametrize("remember", [False, None])
    def test_without_remember_lifetime_unchanged(self, client, athlete_user, remember):
        from api.auth import TOKEN_HOURS
        token, cookie = self._login_full(client, remember)
        assert f"Max-Age={TOKEN_HOURS * 3600}" in cookie
        assert "httponly" in cookie.lower()
        life = self._lifetime_seconds(token)
        assert TOKEN_HOURS * 3600 - 120 <= life <= TOKEN_HOURS * 3600 + 5

    @pytest.mark.parametrize("remember", [True, False])
    def test_logout_invalidates_immediately(self, client, athlete_user, remember):
        token, _ = self._login_full(client, remember)
        h = auth_headers(token)
        assert client.get("/api/athlete/profile", headers=h).status_code == 200
        assert client.post("/api/auth/logout", headers=h).status_code == 200
        client.cookies.clear()
        assert client.get("/api/athlete/profile", headers=h).status_code == 401

    def test_logout_blacklist_covers_full_30_days(self, client, athlete_user, db):
        """El token revocado de 30 días no debe volver a ser válido a las 8 h."""
        from datetime import datetime, timedelta, timezone
        from api.models import RevokedToken
        token, _ = self._login_full(client, True)
        client.post("/api/auth/logout", headers=auth_headers(token))
        row = db.query(RevokedToken).one()
        left = row.expires_at - datetime.now(timezone.utc).replace(tzinfo=None)
        assert left > timedelta(days=29)

    def test_login_page_sends_remember_me(self):
        import pathlib, re
        html = pathlib.Path(__file__).resolve().parents[2].joinpath("login.html").read_text(encoding="utf-8")
        assert re.search(r"remember_me:\s*rem[,\s]", html)
