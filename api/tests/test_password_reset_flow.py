"""
Recuperación de contraseña: la página del formulario (reset-password.html) se
abre SIN sesión y nunca redirige al dashboard; y el enlace del correo apunta al
sitio público aunque APP_URL no esté configurada (producción carga .env, que no la define).
"""
import re
from pathlib import Path

from api.routes import auth_routes

ROOT = Path(__file__).resolve().parents[2]
RESET = (ROOT / "reset-password.html").read_text(encoding="utf-8")


def test_enlace_de_reset_usa_el_sitio_publico_sin_app_url(monkeypatch):
    monkeypatch.delenv("APP_URL", raising=False)
    captured = {}

    def fake_send(*args, **kwargs):
        captured["blob"] = " ".join(str(a) for a in args) + " " + " ".join(str(v) for v in kwargs.values())

    import api.mailer as mailer
    monkeypatch.setattr(mailer, "send_email", fake_send)
    auth_routes._send_reset_email("x@test.com", "Test", "tok123")
    assert "https://labxperformanceapp.com/reset-password.html?token=tok123" in captured["blob"]
    assert "localhost" not in captured["blob"]


def test_app_url_configurada_se_respeta(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://otro.example")
    assert auth_routes._get_app_url() == "https://otro.example"


def test_pagina_de_reset_sin_sesion_no_redirige(client):
    for path in ("/reset-password.html?token=abc123", "/reset-password.html"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        assert "location" not in {k.lower() for k in r.headers}, path


def test_pagina_de_reset_no_tiene_guard_ni_redirect_al_dashboard():
    assert "dashboard.html" not in RESET
    assert "LX_ROUTES.guard" not in RESET
    assert "KL.guard" not in RESET
    assert "sessionStorage" not in RESET and "kl_s" not in RESET


def test_pagina_de_reset_muestra_formulario_con_token():
    assert 'id="step-reset"' in RESET
    assert re.search(r"get\('token'\)", RESET)
