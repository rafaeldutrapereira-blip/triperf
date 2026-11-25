"""H1-XSS: nombres con marcado HTML no se guardan y la pagina publica escapa."""
import re
from pathlib import Path

import pytest

from api.models import GarminActivity, User
from api.auth import hash_password, clean_display_name
from .conftest import login, auth_headers

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = "<img src=x onerror=alert(1)>"


class TestCleanDisplayName:
    @pytest.mark.parametrize("name", [
        "María José Núñez", "Rafael Dutra Pereira", "O'Brien", "D’Angelo",
        "Jean-Luc Picard", "Ana & Co.", "  Pedro  ", "José Ñandú",
    ])
    def test_legitimos(self, name):
        assert clean_display_name(name) == name.strip()

    @pytest.mark.parametrize("name", [PAYLOAD, "a<b", "x>y", "<script>1</script>", "ok\x00", "a\nb"])
    def test_rechaza(self, name):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            clean_display_name(name)
        assert e.value.status_code == 422


class TestProfileAndRegister:
    def test_profile_rechaza_payload(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.patch("/api/athlete/profile", json={"nombre": PAYLOAD}, headers=auth_headers(token))
        assert r.status_code == 422
        r2 = client.get("/api/athlete/profile", headers=auth_headers(token))
        assert r2.json()["nombre"] == "Athlete Test"

    def test_profile_acepta_legitimo(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.patch("/api/athlete/profile", json={"nombre": "María O'Brien-Núñez"}, headers=auth_headers(token))
        assert r.status_code == 200
        r2 = client.get("/api/athlete/profile", headers=auth_headers(token))
        assert r2.json()["nombre"] == "María O'Brien-Núñez"

    def test_register_rechaza_payload(self, client, db):
        r = client.post("/api/auth/register", json={
            "email": "xss@test.com", "nombre": PAYLOAD, "password": "Password123"})
        assert r.status_code == 422
        assert db.query(User).filter(User.email == "xss@test.com").first() is None

    def test_register_acepta_legitimo(self, client):
        r = client.post("/api/auth/register", json={
            "email": "ok@test.com", "nombre": "Zoë D'Ávila", "password": "Password123"})
        assert r.status_code == 201

    def test_claim_invitacion_rechaza_payload(self, client, db):
        u = User(email="inv@test.com", nombre="Invitado", password_hash=hash_password("x" * 12),
                 rol="atleta", plan_nivel="basico", activo=False, pending_invite=True)
        db.add(u); db.commit()
        r = client.post("/api/auth/register", json={
            "email": "inv@test.com", "nombre": PAYLOAD, "password": "Password123"})
        assert r.status_code == 422
        db.refresh(u)
        assert u.nombre == "Invitado" and u.pending_invite


class TestPublicActivityPage:
    html = (ROOT / "public_activity.html").read_text(encoding="utf-8")

    def test_tiene_esc(self):
        assert "function esc(" in self.html

    def test_nombres_escapados(self):
        h = self.html
        assert "esc(d.owner.name ||" in h
        assert re.search(r"esc\(\s*d\.name\s*\|\|", h)
        assert "esc(msg)" in h

    def test_sin_interpolacion_cruda_de_datos(self):
        h = self.html
        i = h.index("content.innerHTML =\n              '<div class=\"card\">'")
        block = h[i:h.index("</script>", i)]
        # Ningun dato de usuario concatenado sin esc() en el bloque de render.
        for raw in (r"(?<!esc)\(d\.owner\.name", r"(?<!esc)\(d\.name", r"\+\s*d\.name",
                    r"\+\s*d\.owner\.name", r"(?<!esc)\(d\.date_iso"):
            assert not re.search(raw, block), raw

    def test_pagina_sigue_mostrando_dueno_y_actividad(self):
        assert "owner-name" in self.html and "act-title" in self.html


def test_endpoint_publico_sigue_devolviendo_dueno_y_actividad(client, db, athlete_user):
    act = GarminActivity(user_id=athlete_user.id, activity_id="a1", name="Rodaje & <b>x</b>",
                         sport="run", date_iso="2026-11-01", share_token="tok-h1xss")
    db.add(act); db.commit()
    r = client.get("/api/public/activities/tok-h1xss")
    assert r.status_code == 200
    d = r.json()
    assert d["owner"]["name"] == "Athlete Test"
    # El servidor devuelve el nombre de actividad tal cual; la pagina lo escapa.
    assert d["name"] == "Rodaje & <b>x</b>"
