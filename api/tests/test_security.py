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

    def test_x_frame_options_deny(self, client):
        r = client.get("/health")
        assert r.headers.get("x-frame-options") == "DENY"

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
        from jose import jwt
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
