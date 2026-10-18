"""
Free (plan basico) — acceso definido por Rafael:
- Comunidad: lectura. Las escrituras (posts, kudos, follows, grupos...) requieren agegroup+.
- Equipo: un par de zapatillas activo. Bicis y componentes requieren agegroup+.
"""
import pytest

from api.auth import hash_password
from api.models import User
from .conftest import auth_headers, login


def _token(client, db, email: str, plan: str) -> str:
    db.add(User(email=email, nombre="Free Access", password_hash=hash_password("FreeAccess-1"),
                rol="atleta", plan_nivel=plan, activo=True))
    db.commit()
    return login(client, email, "FreeAccess-1")


SHOE = {"brand": "Hoka", "model": "Clifton 9", "shoe_type": "rodaje"}


def test_basico_lee_comunidad(client, db):
    h = auth_headers(_token(client, db, "free-read@test.com", "basico"))
    assert client.get("/api/community/feed", headers=h).status_code == 200
    assert client.get("/api/community/groups", headers=h).status_code == 200


def test_basico_no_escribe_en_comunidad(client, db):
    h = auth_headers(_token(client, db, "free-write@test.com", "basico"))
    r = client.post("/api/community/posts", json={"body": "hola", "post_type": "note"}, headers=h)
    assert r.status_code == 403, r.text


def test_agegroup_escribe_en_comunidad(client, db):
    h = auth_headers(_token(client, db, "ag-write@test.com", "agegroup"))
    r = client.post("/api/community/posts", json={"body": "hola", "post_type": "note"}, headers=h)
    assert r.status_code != 403, r.text


def test_basico_un_par_de_zapatillas(client, db):
    h = auth_headers(_token(client, db, "free-shoes@test.com", "basico"))
    assert client.post("/api/gear/shoes", json=SHOE, headers=h).status_code == 200
    r = client.post("/api/gear/shoes", json={**SHOE, "model": "Mach 6"}, headers=h)
    assert r.status_code == 403, r.text
    assert "1 par" in r.text


def test_agegroup_sin_limite_de_zapatillas(client, db):
    h = auth_headers(_token(client, db, "ag-shoes@test.com", "agegroup"))
    assert client.post("/api/gear/shoes", json=SHOE, headers=h).status_code == 200
    assert client.post("/api/gear/shoes", json={**SHOE, "model": "Mach 6"}, headers=h).status_code == 200


def test_basico_lee_su_equipo(client, db):
    h = auth_headers(_token(client, db, "free-summary@test.com", "basico"))
    assert client.get("/api/gear/shoes", headers=h).status_code == 200
    assert client.get("/api/gear/summary", headers=h).status_code == 200


@pytest.mark.parametrize("method,path", [("GET", "/api/gear/bikes"), ("POST", "/api/gear/bikes")])
def test_basico_sin_bicis(client, db, method, path):
    h = auth_headers(_token(client, db, f"free-bike-{method.lower()}@test.com", "basico"))
    kwargs = {"json": {"brand": "Canyon", "model": "Ultimate"}} if method == "POST" else {}
    r = client.request(method, path, headers=h, **kwargs)
    assert r.status_code == 403, r.text
