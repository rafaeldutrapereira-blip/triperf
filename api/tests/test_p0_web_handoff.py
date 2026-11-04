"""P0 — puente app -> web: handoff de un solo uso."""
from datetime import datetime, timedelta, timezone

from api.models import User, WebHandoff
from api.auth import hash_password
from api.tests.conftest import auth_headers, login

ISSUE = "/api/auth/web-handoff"
REDEEM = "/api/auth/web-handoff/redeem"


def _issue(client, token, destino="estado"):
    return client.post(ISSUE, json={"destino": destino}, headers=auth_headers(token))


def _token(client, athlete_user):
    return login(client, "athlete@test.com", "AthlPass123")


def test_issue_requires_auth(client):
    assert client.post(ISSUE, json={"destino": "estado"}).status_code == 401


def test_token_single_use(client, athlete_user):
    t = _token(client, athlete_user)
    h = _issue(client, t).json()["token"]
    assert client.post(REDEEM, json={"token": h}).status_code == 200
    assert client.post(REDEEM, json={"token": h}).status_code == 401


def test_expired_token_fails(client, athlete_user, db):
    t = _token(client, athlete_user)
    h = _issue(client, t).json()["token"]
    row = db.query(WebHandoff).first()
    row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db.commit()
    assert client.post(REDEEM, json={"token": h}).status_code == 401


def test_unknown_token_fails(client):
    assert client.post(REDEEM, json={"token": "nope"}).status_code == 401


def test_destino_outside_list_rejected(client, athlete_user):
    t = _token(client, athlete_user)
    for bad in ("https://evil.example", "//evil.example", "../x", "login", ""):
        assert _issue(client, t, bad).status_code == 400
    assert client.get("/api/auth/web-handoff/stats", headers=auth_headers(t)).status_code == 403


def test_redeem_returns_fixed_path_for_each_destino(client, athlete_user):
    t = _token(client, athlete_user)
    expected = {"estado": "/estado.html", "race_day": "/race_day.html", "gear": "/gear.html",
                "detalle": "/detalle.html", "analytics": "/analytics.html"}
    for d, path in expected.items():
        h = _issue(client, t, d).json()["token"]
        r = client.post(REDEEM, json={"token": h}).json()
        assert r["path"] == path and r["destino"] == d


def test_redeem_session_belongs_to_token_owner(client, athlete_user, db):
    other = User(email="otro@test.com", nombre="Otro", password_hash=hash_password("OtroPass123"),
                 rol="athlete", plan_nivel="basico", activo=True)
    db.add(other)
    db.commit()
    t = _token(client, athlete_user)
    h = _issue(client, t).json()["token"]
    # canje desde un cliente sin sesion previa: la sesion es del dueno del token
    r = client.post(REDEEM, json={"token": h})
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == athlete_user.id and body["user_id"] != other.id
    me = client.get("/api/auth/me", headers=auth_headers(body["access_token"]))
    assert me.json()["email"] == "athlete@test.com"
    assert "lx_access_token" in r.headers.get("set-cookie", "")


def test_inactive_user_cannot_redeem(client, athlete_user, db):
    t = _token(client, athlete_user)
    h = _issue(client, t).json()["token"]
    athlete_user.activo = False
    db.commit()
    assert client.post(REDEEM, json={"token": h}).status_code == 401


def test_counter_sums_by_destino(client, admin_user, athlete_user):
    t = _token(client, athlete_user)
    for d in ("estado", "estado", "gear"):
        h = _issue(client, t, d).json()["token"]
        client.post(REDEEM, json={"token": h})
    _issue(client, t, "gear")  # emitido, sin canjear
    from api.auth import create_token
    client.cookies.clear()  # la cookie de sesion del atleta tiene prioridad sobre el Bearer
    at = create_token(admin_user.id, admin_user.rol, admin_user.nombre, admin_user.token_gen or 1)
    s = client.get("/api/auth/web-handoff/stats", headers=auth_headers(at))
    assert s.status_code == 200, s.text
    pd = s.json()["por_destino"]
    assert pd["estado"] == {"emitidos": 2, "canjeados": 2}
    assert pd["gear"] == {"emitidos": 2, "canjeados": 1}
    assert pd["race_day"] == {"emitidos": 0, "canjeados": 0}


def test_handoff_page_served(client):
    r = client.get("/web-handoff.html")
    assert r.status_code == 200 and "web-handoff/redeem" in r.text
