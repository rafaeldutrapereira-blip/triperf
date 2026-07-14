"""
Tests para POST/GET/DELETE /athlete/personal-records (marcas manuales).

Bug encontrado: el formulario de athlete_profile.html manda
{sport, event, time, date, place}, pero el schema _PRIn pedia
{event, value_sec, value_disp, achieved_at} -> 422 en TODOS los casos,
el usuario solo veia "Error guardando record".
"""
from .conftest import login, auth_headers


def test_create_personal_record_matches_frontend_payload(client, db, athlete_user):
    """El payload real que manda athlete_profile.html debe aceptarse (antes daba 422)."""
    token = login(client, "athlete@test.com", "AthlPass123")
    body = {
        "sport": "run",
        "event": "10K",
        "time": "0:42:15",
        "date": "2026-05-01",
        "place": "Santiago, Chile",
    }
    r = client.post("/api/athlete/personal-records", json=body, headers=auth_headers(token))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["improved"] is True
    assert d["pr"]["sport"] == "run"
    assert d["pr"]["place"] == "Santiago, Chile"
    assert d["pr"]["value_disp"] == "0:42:15"
    assert d["pr"]["value_sec"] == 42 * 60 + 15


def test_personal_record_appears_in_get(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    client.post(
        "/api/athlete/personal-records",
        json={"sport": "swim", "event": "1500m", "time": "25:30", "date": "2026-01-01", "place": ""},
        headers=auth_headers(token),
    )
    r = client.get("/api/athlete/personal-records", headers=auth_headers(token))
    assert r.status_code == 200
    prs = r.json()
    assert len(prs) == 1
    assert prs[0]["sport"] == "swim"
    assert prs[0]["event"] == "1500m"
    assert prs[0]["value_sec"] == 25 * 60 + 30


def test_personal_record_time_formats(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    cases = [
        ("4:32:10", 4 * 3600 + 32 * 60 + 10),
        ("42:15", 42 * 60 + 15),
        ("90", 90.0),
    ]
    for i, (time_str, expected_sec) in enumerate(cases):
        r = client.post(
            "/api/athlete/personal-records",
            json={"event": f"evt-{i}", "time": time_str},
            headers=auth_headers(token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["pr"]["value_sec"] == expected_sec


def test_personal_record_invalid_time_format(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.post(
        "/api/athlete/personal-records",
        json={"event": "10K", "time": "no-es-un-tiempo"},
        headers=auth_headers(token),
    )
    assert r.status_code == 400


def test_personal_record_worse_time_not_saved_as_improvement(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    client.post(
        "/api/athlete/personal-records",
        json={"event": "5K", "time": "20:00"},
        headers=auth_headers(token),
    )
    r = client.post(
        "/api/athlete/personal-records",
        json={"event": "5K", "time": "22:00"},
        headers=auth_headers(token),
    )
    assert r.status_code == 201
    assert r.json()["improved"] is False

    r2 = client.get("/api/athlete/personal-records", headers=auth_headers(token))
    assert len(r2.json()) == 1  # no se creo un segundo registro


def test_delete_personal_record(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    created = client.post(
        "/api/athlete/personal-records",
        json={"event": "Maraton", "time": "3:30:00"},
        headers=auth_headers(token),
    ).json()
    pr_id = created["pr"]["id"]

    r = client.delete(f"/api/athlete/personal-records/{pr_id}", headers=auth_headers(token))
    assert r.status_code == 200

    r2 = client.get("/api/athlete/personal-records", headers=auth_headers(token))
    assert r2.json() == []


def test_personal_records_requires_auth(client, db):
    r = client.get("/api/athlete/personal-records")
    assert r.status_code == 401
    r2 = client.post("/api/athlete/personal-records", json={"event": "x", "time": "1:00"})
    assert r2.status_code == 401
