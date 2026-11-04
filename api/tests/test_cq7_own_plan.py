"""
CQ7 -- Mi Plan propio persistido en servidor: CRUD con auth, aislamiento por
usuario, conservacion de campos, '+ Mi Plan' de Indoor sin duplicar e
importacion unica desde localStorage (idempotente).
"""
from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import User

BASE = "/api/athlete/own-plan"
PW = "Cq7Pass-12345"


def _user(db, email, plan="elite"):
    u = User(email=email, nombre=email, password_hash=hash_password(PW),
             rol="athlete", plan_nivel=plan, activo=True)
    db.add(u)
    db.commit()
    return u


def _h(client, email):
    h = auth_headers(login(client, email, PW))
    client.cookies.clear()
    return h


SESS = {"sport": "run", "name": "Rodaje", "date_iso": "2026-11-05", "dur_min": 45,
        "dist_km": 8.5, "tss": 40, "notes": "suave", "calories": None,
        "created": "2026-11-04T10:00:00Z"}


def test_requires_auth(client):
    client.cookies.clear()
    assert client.get(BASE).status_code in (401, 403)


def test_crud_roundtrip_conserva_campos(client, db):
    _user(db, "cq7a@test.com")
    h = _h(client, "cq7a@test.com")
    r = client.post(BASE, json=SESS, headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["name"] == "Rodaje" and s["dur_min"] == 45 and s["dist_km"] == 8.5
    assert s["created"] == "2026-11-04T10:00:00Z"  # campo extra no se pierde

    r = client.put(f"{BASE}/{s['id']}", json={"date_iso": "2026-11-07", "status": "done",
                                              "rpe": 6}, headers=h)
    assert r.status_code == 200
    u = r.json()
    assert u["date_iso"] == "2026-11-07" and u["status"] == "done" and u["rpe"] == 6
    assert u["name"] == "Rodaje" and u["created"] == "2026-11-04T10:00:00Z"

    got = client.get(BASE, headers=h).json()["sessions"]
    assert [x["id"] for x in got] == [s["id"]]
    assert client.get(f"{BASE}?start=2026-11-08", headers=h).json()["sessions"] == []

    assert client.delete(f"{BASE}/{s['id']}", headers=h).status_code == 200
    assert client.get(BASE, headers=h).json()["sessions"] == []


def test_validaciones(client, db):
    _user(db, "cq7v@test.com")
    h = _h(client, "cq7v@test.com")
    assert client.post(BASE, json={**SESS, "date_iso": "5/11"}, headers=h).status_code == 400
    assert client.post(BASE, json={**SESS, "name": " "}, headers=h).status_code == 400


def test_otro_usuario_no_ve_ni_toca_el_plan_ajeno(client, db):
    _user(db, "cq7o@test.com")
    _user(db, "cq7x@test.com")
    ho = _h(client, "cq7o@test.com")
    hx = _h(client, "cq7x@test.com")
    sid = client.post(BASE, json=SESS, headers=ho).json()["id"]
    assert client.get(BASE, headers=hx).json()["sessions"] == []
    assert client.put(f"{BASE}/{sid}", json={"name": "x"}, headers=hx).status_code == 404
    assert client.delete(f"{BASE}/{sid}", headers=hx).status_code == 404
    assert len(client.get(BASE, headers=ho).json()["sessions"]) == 1


def test_indoor_mi_plan_no_duplica(client, db):
    _user(db, "cq7i@test.com")
    h = _h(client, "cq7i@test.com")
    body = {**SESS, "sport": "bike", "name": "Sweet spot", "indoor_workout_id": "iw-1"}
    a = client.post(BASE, json=body, headers=h).json()
    b = client.post(BASE, json=body, headers=h).json()
    assert a["duplicate"] is False and b["duplicate"] is True and a["id"] == b["id"]
    assert len(client.get(BASE, headers=h).json()["sessions"]) == 1
    # otro dia = otra sesion
    c = client.post(BASE, json={**body, "date_iso": "2026-11-06"}, headers=h).json()
    assert c["id"] != a["id"]


def test_import_una_sola_vez(client, db):
    _user(db, "cq7m@test.com")
    h = _h(client, "cq7m@test.com")
    local = [
        {**SESS, "id": "plan-111"},
        {**SESS, "id": "plan-222", "name": "Fondo", "date_iso": "2026-11-09"},
        {**SESS, "id": "api_5", "api_assignment_id": 5},  # cache del coach: no es propio
    ]
    r = client.post(f"{BASE}/import", json={"sessions": local}, headers=h).json()
    assert (r["created"], r["skipped"], r["invalid"]) == (2, 0, 1)
    r2 = client.post(f"{BASE}/import", json={"sessions": local}, headers=h).json()
    assert (r2["created"], r2["skipped"]) == (0, 2)
    assert len(client.get(BASE, headers=h).json()["sessions"]) == 2


def test_basico_no_accede(client, db):
    _user(db, "cq7b@test.com", plan="basico")
    h = _h(client, "cq7b@test.com")
    assert client.get(BASE, headers=h).status_code == 403
