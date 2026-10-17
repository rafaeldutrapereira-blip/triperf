"""
Tests — i18n de emails transaccionales (api/mailer.py, i18n Sprint 5).

Cubre que cada send_*() genere el asunto/cuerpo correcto por idioma
("es"|"pt"|"en", con "es" como fallback para cualquier otro valor) sin
depender de RESEND_API_KEY real -- se monkeypatchea send_email para
capturar los argumentos sin llegar a la red.
"""
from __future__ import annotations

import pytest

from api import mailer


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def _fake_send_email(to, subject, html, *, tags=None, attachments=None):
        calls.append({"to": to, "subject": subject, "html": html, "tags": tags})
        return True

    monkeypatch.setattr(mailer, "send_email", _fake_send_email)
    return calls


def test_send_welcome_subject_per_lang(captured):
    mailer.send_welcome("a@b.com", "Rafael", lang="es")
    mailer.send_welcome("a@b.com", "Rafael", lang="pt")
    mailer.send_welcome("a@b.com", "Rafael", lang="en")
    subjects = [c["subject"] for c in captured]
    assert subjects == [
        "Bienvenido a LabX — Su plataforma de rendimiento ya está lista",
        "Bem-vindo ao LabX — Sua plataforma de performance já está pronta",
        "Welcome to LabX — Your performance platform is ready",
    ]
    # El cuerpo PT debe usar el saludo portugués, no quedar en español
    pt_html = captured[1]["html"]
    assert "Prezado(a)" in pt_html
    assert "Estimado/a" not in pt_html


def test_send_welcome_unknown_lang_falls_back_to_es(captured):
    mailer.send_welcome("a@b.com", "Rafael", lang="fr")
    assert captured[0]["subject"] == "Bienvenido a LabX — Su plataforma de rendimiento ya está lista"


def test_send_day3_drip_interpolates_name_per_lang(captured):
    mailer.send_day3_drip("a@b.com", "Ana", lang="pt")
    assert captured[0]["subject"] == "Ana, desbloqueie todo o seu potencial no LabX 🚀"
    assert "como está indo o treino" in captured[0]["html"]


def test_send_day7_drip_subject_en(captured):
    mailer.send_day7_drip("a@b.com", "Ana", lang="en")
    assert captured[0]["subject"] == "One week with LabX — do you have a coach, Ana? 🧑‍💼"


def test_send_login_alert_pt(captured, monkeypatch):
    monkeypatch.setattr(mailer, "_geolocate_ip", lambda ip: None)
    mailer.send_login_alert("a@b.com", "Ana", "8.8.8.8", "Mozilla/5.0 Chrome/1.0", lang="pt")
    assert captured[0]["subject"] == "LabX — Novo login detectado na sua conta"
    assert "Não disponível" in captured[0]["html"]  # geolocalização falló -> fallback PT, no "No disponible"


def test_send_gear_alert_100pct_en(captured):
    mailer.send_gear_alert("a@b.com", "Ana", "Hoka Clifton", "shoe", 100.0, 100, lang="en")
    assert "reached 100% of its useful life" in captured[0]["subject"]


def test_send_gear_alert_pct_pt(captured):
    mailer.send_gear_alert("a@b.com", "Ana", "Cadena", "component", 85.0, 80, lang="pt")
    assert "85% da sua vida útil" in captured[0]["subject"]


# ─────────────────────────────────────────────────────────────────────────
# Persistencia server-side del idioma (User.lang) — flujo real vía API
# ─────────────────────────────────────────────────────────────────────────

def test_register_persists_lang_from_body(client, db):
    from api.models import User

    r = client.post("/api/auth/register", json={
        "email": "pt_user@test.com",
        "nombre": "Usuário PT",
        "password": "Password123",
        "lang": "pt",
    })
    assert r.status_code == 201
    user = db.query(User).filter(User.email == "pt_user@test.com").first()
    assert user is not None
    assert user.lang == "pt"


def test_register_defaults_lang_to_es_when_missing(client, db):
    from api.models import User

    r = client.post("/api/auth/register", json={
        "email": "no_lang_user@test.com",
        "nombre": "Sin Idioma",
        "password": "Password123",
    })
    assert r.status_code == 201
    user = db.query(User).filter(User.email == "no_lang_user@test.com").first()
    assert user.lang == "es"


def test_register_rejects_invalid_lang_value(client, db):
    from api.models import User

    r = client.post("/api/auth/register", json={
        "email": "bad_lang_user@test.com",
        "nombre": "Lang Raro",
        "password": "Password123",
        "lang": "xx",
    })
    assert r.status_code == 201
    user = db.query(User).filter(User.email == "bad_lang_user@test.com").first()
    assert user.lang == "es"  # valor no soportado -> fallback, nunca se guarda tal cual


def test_patch_profile_updates_lang(client, db):
    from api.models import User
    from .conftest import auth_headers

    client.post("/api/auth/register", json={
        "email": "switcher@test.com",
        "nombre": "Switcher",
        "password": "Password123",
        "lang": "es",
    })
    login_r = client.post("/api/auth/login", json={"email": "switcher@test.com", "password": "Password123"})
    token = login_r.json()["access_token"]

    r = client.patch("/api/athlete/profile", json={"lang": "en"}, headers=auth_headers(token))
    assert r.status_code == 200
    user = db.query(User).filter(User.email == "switcher@test.com").first()
    assert user.lang == "en"


def test_patch_profile_ignores_invalid_lang(client, db):
    from api.models import User
    from .conftest import auth_headers

    client.post("/api/auth/register", json={
        "email": "switcher2@test.com",
        "nombre": "Switcher2",
        "password": "Password123",
        "lang": "es",
    })
    login_r = client.post("/api/auth/login", json={"email": "switcher2@test.com", "password": "Password123"})
    token = login_r.json()["access_token"]

    r = client.patch("/api/athlete/profile", json={"lang": "de"}, headers=auth_headers(token))
    assert r.status_code == 200
    user = db.query(User).filter(User.email == "switcher2@test.com").first()
    assert user.lang == "es"  # "de" no es soportado -> se ignora, queda el valor previo
