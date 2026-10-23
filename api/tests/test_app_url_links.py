"""
Enlaces de correos y redirecciones sin APP_URL definida: deben apuntar al sitio
público (https://labxperformanceapp.com), nunca a localhost. Si APP_URL existe, manda ella.
"""
import re
from pathlib import Path

import pytest

from api import app_url
from api import mailer
from api.services import notification_service as ns
from api.routes import auth_routes

PUBLIC = "https://labxperformanceapp.com"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _sin_app_url(monkeypatch):
    monkeypatch.delenv("APP_URL", raising=False)


def _hrefs(html: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', html)


# ── función central ──
def test_default_es_el_sitio_publico():
    assert app_url.get_app_url() == PUBLIC


def test_app_url_definida_se_respeta(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://staging.example/")
    assert app_url.get_app_url() == "https://staging.example"


def test_app_url_vacia_cae_al_publico(monkeypatch):
    monkeypatch.setenv("APP_URL", "   ")
    assert app_url.get_app_url() == PUBLIC


# ── correos de mailer.py ──
def _capture_send(monkeypatch):
    got = {}

    def fake(*args, **kwargs):
        got["html"] = args[2] if len(args) > 2 else kwargs.get("html_body", "")

    monkeypatch.setattr(mailer, "send_email", fake)
    return got


@pytest.mark.parametrize("fn,args", [
    ("send_welcome", ("a@test.com", "Ana", "")),
    ("send_day3_drip", ("a@test.com", "Ana", "")),
    ("send_day7_drip", ("a@test.com", "Ana", "")),
])
def test_mailer_drips_y_bienvenida_sin_localhost(monkeypatch, fn, args):
    got = _capture_send(monkeypatch)
    getattr(mailer, fn)(*args)
    assert "localhost" not in got["html"]
    assert PUBLIC in got["html"]


def test_mailer_respeta_app_url_explicita(monkeypatch):
    got = _capture_send(monkeypatch)
    mailer.send_welcome("a@test.com", "Ana", "https://otro.example")
    assert "https://otro.example" in got["html"]
    assert "localhost" not in got["html"]


# ── notification_service: el marcador literal {{APP_URL}} ya no sale ──
@pytest.mark.parametrize("builder,args", [
    (ns.email_workout_assigned, ("Ana", "Rodaje", "2026-10-23", "Coach")),
    (ns.email_wellness_reminder, ("Ana",)),
    (ns.email_overtraining_alert, ("Ana", -20.0, 1.6)),
])
def test_notificaciones_enlaces_resueltos(builder, args):
    _subject, html = builder(*args)
    assert "{{APP_URL}}" not in html and "{{{{APP_URL}}}}" not in html
    assert "{get_app_url()}" not in html
    links = [h for h in _hrefs(html) if h.startswith("http")]
    assert links, "debería haber enlaces http"
    assert all(h.startswith(PUBLIC) for h in links), links


# ── almacenamiento local ──
def test_storage_url_usa_el_sitio_publico():
    from api.storage import LocalStorage
    url = LocalStorage(base_dir="/tmp").url("abc.jpg")
    assert url == f"{PUBLIC}/api/storage/abc.jpg"


# ── reset de contraseña (ya cubierto en test_password_reset_flow): mismo origen ──
def test_reset_link_mismo_origen_publico(monkeypatch):
    got = {}
    monkeypatch.setattr(mailer, "send_email", lambda *a, **k: got.setdefault("blob", str(a) + str(k)))
    auth_routes._send_reset_email("x@test.com", "Test", "tok")
    assert f"{PUBLIC}/reset-password.html?token=tok" in got["blob"]


# ── scheduler y workout_delivery: sin default localhost en el código ──
@pytest.mark.parametrize("rel", ["api/scheduler.py", "api/workout_delivery.py", "api/storage.py",
                                 "api/routes/stripe_routes.py", "api/routes/auth_routes.py",
                                 "api/mailer.py", "api/services/notification_service.py"])
def test_sin_default_localhost_en_codigo_de_enlaces(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert 'localhost:8000")' not in text, rel
