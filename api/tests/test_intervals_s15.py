"""S15 -- reenviar a intervals.icu actualiza el mismo evento (sin duplicados).
Conector mockeado: sin red real."""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from .test_intervals_icu import BASE, BIKE_BLOCKS, _user, _h
from .. import intervals_connector as ic
from ..models import IndoorWorkout


def _resp(status, body=b'{"id": 555}', js=None):
    r = MagicMock()
    r.status_code = status
    r.content = body
    r.json.return_value = js if js is not None else {"id": 555}
    return r


@contextmanager
def _http(post=None, put=None, delete=None):
    with patch("httpx.AsyncClient") as MockClient:
        c = AsyncMock()
        c.post = AsyncMock(side_effect=post) if isinstance(post, Exception) else AsyncMock(return_value=post)
        c.put = AsyncMock(return_value=put)
        c.delete = AsyncMock(side_effect=delete) if isinstance(delete, Exception) else AsyncMock(return_value=delete)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=c)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        yield c


def _setup(client, db, email):
    u = _user(db, email)
    h = _h(client, email)
    ic.save_tokens(u, "tok", "1", db)
    w = client.post(BASE, json={"name": "FTP", "sport": "bike",
                                "planned_date": "2026-11-10", "blocks": BIKE_BLOCKS}, headers=h).json()
    return h, w


def _stored(db, wid):
    db.expire_all()
    return db.query(IndoorWorkout).filter(IndoorWorkout.id == wid).first().intervals_event_id


def test_a_first_send_creates_and_persists_id(client, db):
    h, w = _setup(client, db, "s15a@test.com")
    with _http(post=_resp(200)) as c:
        r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    assert r.status_code == 200 and r.json() == {"ok": True, "event_id": 555}
    assert c.post.await_count == 1 and c.put.await_count == 0
    assert _stored(db, w["id"]) == "555"


def test_b_second_send_puts_no_post(client, db):
    h, w = _setup(client, db, "s15b@test.com")
    with _http(post=_resp(200)):
        client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    with _http(put=_resp(200)) as c:
        r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    assert r.status_code == 200 and r.json()["event_id"] == 555
    assert c.put.await_count == 1 and c.post.await_count == 0
    assert c.put.await_args.args[0].endswith("/athlete/0/events/555")
    assert _stored(db, w["id"]) == "555"


def test_c_put_404_creates_new_and_replaces_id(client, db):
    h, w = _setup(client, db, "s15c@test.com")
    with _http(post=_resp(200)):
        client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    with _http(put=_resp(404, b""), post=_resp(200, js={"id": 777})) as c:
        r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    assert r.status_code == 200 and r.json()["event_id"] == 777
    assert c.put.await_count == 1 and c.post.await_count == 1
    assert _stored(db, w["id"]) == "777"


def test_d_delete_attempts_remote_delete(client, db):
    h, w = _setup(client, db, "s15d1@test.com")
    with _http(post=_resp(200)):
        client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    with _http(delete=_resp(200, b"")) as c:
        r = client.delete(f"{BASE}/{w['id']}", headers=h)
    assert r.status_code == 200
    assert c.delete.await_count == 1
    assert c.delete.await_args.args[0].endswith("/athlete/0/events/555")
    assert client.get(f"{BASE}/{w['id']}", headers=h).status_code == 404


def test_d_remote_delete_error_local_delete_still_succeeds(client, db):
    import httpx
    h, w = _setup(client, db, "s15d2@test.com")
    with _http(post=_resp(200)):
        client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
    with _http(delete=httpx.ConnectError("boom")) as c:
        r = client.delete(f"{BASE}/{w['id']}", headers=h)
    assert r.status_code == 200 and c.delete.await_count == 1
    assert client.get(f"{BASE}/{w['id']}", headers=h).status_code == 404


def test_delete_without_event_makes_no_remote_call(client, db):
    h, w = _setup(client, db, "s15d3@test.com")
    with _http() as c:
        assert client.delete(f"{BASE}/{w['id']}", headers=h).status_code == 200
    assert c.delete.await_count == 0
