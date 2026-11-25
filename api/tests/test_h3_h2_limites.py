"""H3-H2-LIMITES: IP confiable (sin XFF) y contador 2FA que solo se borra tras ambos factores."""
import pyotp
import pytest

from api.audit import ip_from_request
from api.auth import hash_password
from api.models import LoginAttempt, User


class _Req:
    def __init__(self, headers=None, host="10.0.0.9"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})() if host else None


def _user(db, email="tfa@test.com", totp=True):
    secret = pyotp.random_base32()
    u = User(email=email, nombre="T", password_hash=hash_password("GoodPass123"),
             rol="athlete", plan_nivel="basico", activo=True,
             totp_enabled=totp, totp_secret=secret if totp else None)
    db.add(u); db.commit(); db.refresh(u)
    return u, secret


def _login(client, email, pw="GoodPass123", code=None, headers=None):
    body = {"email": email, "password": pw}
    if code is not None:
        body["totp_code"] = code
    return client.post("/api/auth/login", json=body, headers=headers or {})


# ── H3 ────────────────────────────────────────────────────────
def test_ip_ignora_xff():
    assert ip_from_request(_Req({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})) == "10.0.0.9"


def test_ip_respeta_cf_connecting_ip():
    r = _Req({"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": "1.1.1.1"})
    assert ip_from_request(r) == "203.0.113.7"


def test_ip_cf_invalida_cae_a_conexion():
    assert ip_from_request(_Req({"CF-Connecting-IP": "no-es-ip"})) == "10.0.0.9"


def test_xff_distinto_por_peticion_no_evita_429(client, db):
    _user(db, totp=False)
    codes = []
    for i in range(12):
        r = _login(client, "tfa@test.com", pw="Mala12345", headers={"X-Forwarded-For": f"9.9.9.{i}"})
        codes.append(r.status_code)
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_cf_connecting_ip_distintas_son_buckets_distintos(client, db):
    _user(db, totp=False)
    for i in range(12):
        r = _login(client, "tfa@test.com", pw="Mala12345", headers={"CF-Connecting-IP": f"198.51.100.{i}"})
        assert r.status_code == 401


# ── H2 ────────────────────────────────────────────────────────
def test_totp_erroneo_no_se_borra_con_siguiente_peticion(client, db):
    u, _ = _user(db)
    for _ in range(3):
        assert _login(client, u.email, code="000000").status_code == 401
        # peticion con contraseña correcta y sin codigo (needs_2fa) NO debe limpiar
        assert _login(client, u.email).json()["needs_2fa"] is True
    n = db.query(LoginAttempt).filter(LoginAttempt.ip == f"user:{u.id}").count()
    assert n == 3


def test_limite_por_usuario_aunque_cambie_la_ip(client, db):
    u, secret = _user(db)
    for i in range(10):
        r = _login(client, u.email, code="000000", headers={"CF-Connecting-IP": f"198.51.100.{i}"})
        assert r.status_code == 401
    # IP nueva, y hasta con el TOTP correcto: bloqueado
    r = _login(client, u.email, code=pyotp.TOTP(secret).now(), headers={"CF-Connecting-IP": "203.0.113.99"})
    assert r.status_code == 429


def test_backup_code_invalido_cuenta_para_el_limite(client, db):
    u, _ = _user(db)
    u.totp_backup_hash = "[]"; db.commit()
    for i in range(10):
        assert _login(client, u.email, code=f"BADBACKUP{i}", headers={"CF-Connecting-IP": f"198.51.100.{i}"}).status_code == 401
    assert _login(client, u.email, code="BADBACKUPX", headers={"CF-Connecting-IP": "203.0.113.50"}).status_code == 429


def test_login_completo_limpia_contadores(client, db):
    u, secret = _user(db)
    for _ in range(3):
        _login(client, u.email, code="000000")
    r = _login(client, u.email, code=pyotp.TOTP(secret).now())
    assert r.status_code == 200 and r.json()["access_token"]
    db.expire_all()
    assert db.query(LoginAttempt).count() == 0


# ── Flujos legitimos ──────────────────────────────────────────
def test_login_sin_2fa_ok(client, db):
    u, _ = _user(db, email="plain@test.com", totp=False)
    assert _login(client, u.email).status_code == 200


def test_registro_y_forgot_siguen_funcionando(client, db):
    r = client.post("/api/auth/forgot-password", json={"email": "nadie@test.com"})
    assert r.status_code < 500
    r = client.post("/api/auth/register", json={"email": "nuevo@test.com", "password": "GoodPass123", "nombre": "N"})
    assert r.status_code < 500
