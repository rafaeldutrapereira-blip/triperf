"""
S4 -- Workouts indoor propios persistidos en BD: CRUD, aislamiento por dueño,
gating de plan y migración idempotente desde localStorage (legacy_id).
"""
from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import User

BASE = "/api/athlete/indoor-workouts"
BLOCKS = [
    {"type": "warmup", "duration": 600, "power_pct": 55},
    {"type": "intervals", "repeat": 4, "on_duration": 240, "off_duration": 120,
     "on_pct": 105, "off_pct": 55},
    {"type": "cooldown", "duration": 300, "power_pct": 50},
]


def _user(db, email, plan="elite", rol="athlete"):
    u = User(email=email, nombre=email, password_hash=hash_password("S4Pass-12345"),
             rol=rol, plan_nivel=plan, activo=True)
    db.add(u)
    db.commit()
    return u


def _h(client, email):
    h = auth_headers(login(client, email, "S4Pass-12345"))
    client.cookies.clear()  # el login deja cookie de sesión; aquí se autentica solo por Bearer
    return h


def _mk(client, h, name="Sweet spot", **extra):
    body = {"name": name, "description": "d", "planned_date": "2026-11-05", "blocks": BLOCKS}
    body.update(extra)
    return client.post(BASE, json=body, headers=h)


def test_crud_roundtrip(client, db):
    _user(db, "s4a@test.com")
    h = _h(client, "s4a@test.com")

    r = _mk(client, h)
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["name"] == "Sweet spot" and w["sport"] == "bike"
    assert w["blocks"] == BLOCKS and w["planned_date"] == "2026-11-05"

    assert client.get(BASE, headers=h).json()["workouts"][0]["id"] == w["id"]
    assert client.get(f"{BASE}/{w['id']}", headers=h).json()["blocks"] == BLOCKS

    r = client.put(f"{BASE}/{w['id']}", json={"name": "Renombrado", "blocks": BLOCKS[:1]}, headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Renombrado" and len(r.json()["blocks"]) == 1
    assert r.json()["description"] == "d"  # update parcial no pisa lo no enviado

    assert client.delete(f"{BASE}/{w['id']}", headers=h).status_code == 200
    assert client.get(f"{BASE}/{w['id']}", headers=h).status_code == 404
    assert client.get(BASE, headers=h).json()["workouts"] == []


def test_validation(client, db):
    _user(db, "s4v@test.com")
    h = _h(client, "s4v@test.com")
    assert client.post(BASE, json={"name": "", "blocks": BLOCKS}, headers=h).status_code == 400
    assert client.post(BASE, json={"name": "x", "blocks": []}, headers=h).status_code == 400
    assert client.post(BASE, json={"name": "x", "blocks": ["no-dict"]}, headers=h).status_code == 400
    assert client.post(BASE, json={"name": "x", "blocks": BLOCKS, "sport": "swim"}, headers=h).status_code == 400
    assert client.post(BASE, json={"name": "x", "blocks": BLOCKS, "planned_date": "mañana"}, headers=h).status_code == 400


def test_owner_isolation(client, db):
    _user(db, "s4o1@test.com")
    _user(db, "s4o2@test.com")
    h1, h2 = _h(client, "s4o1@test.com"), _h(client, "s4o2@test.com")
    wid = _mk(client, h1).json()["id"]

    assert client.get(f"{BASE}/{wid}", headers=h2).status_code == 404
    assert client.put(f"{BASE}/{wid}", json={"name": "robado"}, headers=h2).status_code == 404
    assert client.delete(f"{BASE}/{wid}", headers=h2).status_code == 404
    assert client.get(BASE, headers=h2).json()["workouts"] == []
    # el dueño sigue intacto
    assert client.get(f"{BASE}/{wid}", headers=h1).json()["name"] == "Sweet spot"


def test_requires_auth_and_plan(client, db):
    assert client.get(BASE).status_code == 401
    _user(db, "s4b@test.com", plan="agegroup")
    h = _h(client, "s4b@test.com")
    assert client.get(BASE, headers=h).status_code == 403
    assert _mk(client, h).status_code == 403


def test_legacy_id_import_is_idempotent(client, db):
    _user(db, "s4l@test.com")
    h = _h(client, "s4l@test.com")
    a = _mk(client, h, legacy_id="wo-1700000000000").json()
    b = _mk(client, h, legacy_id="wo-1700000000000").json()
    assert a["id"] == b["id"]
    assert len(client.get(BASE, headers=h).json()["workouts"]) == 1
    # el mismo legacy_id en otra cuenta no colisiona
    _user(db, "s4l2@test.com")
    h2 = _h(client, "s4l2@test.com")
    c = _mk(client, h2, legacy_id="wo-1700000000000").json()
    assert c["id"] != a["id"]
