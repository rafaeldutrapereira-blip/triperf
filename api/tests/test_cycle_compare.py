"""
Tests para GET /athlete/cycle-compare — comparación de dos bloques de
entrenamiento (ej. mismo ciclo sept-dic de dos años distintos) alineados
por dias hasta la carrera, no por fecha de calendario.
"""
from datetime import date, timedelta

from ..models import RaceEvent, GarminTrainingLoad
from .conftest import login, auth_headers


def _seed_training_load(db, user_id, race_date_iso, weeks, ctl_start, ctl_end):
    """Crea una rampa lineal de CTL/ATL/TSB terminando el dia de la carrera."""
    race_date = date.fromisoformat(race_date_iso)
    start = race_date - timedelta(weeks=weeks)
    days = (race_date - start).days
    for i in range(days + 1):
        d = start + timedelta(days=i)
        frac = i / days if days else 0
        ctl = ctl_start + (ctl_end - ctl_start) * frac
        db.add(GarminTrainingLoad(
            user_id=user_id, date_iso=d.isoformat(),
            ctl=ctl, atl=ctl * 0.9, tsb=ctl * 0.1, tss=80.0,
        ))
    db.commit()


def _seed_race(db, user_id, name, date_iso, is_goal=False):
    r = RaceEvent(user_id=user_id, name=name, date_iso=date_iso, distance="703", is_goal_race=is_goal)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_cycle_compare_happy_path(client, db, athlete_user):
    race_a = _seed_race(db, athlete_user.id, "Ironman 70.3 A", "2026-01-15", is_goal=True)
    race_b = _seed_race(db, athlete_user.id, "Ironman 70.3 B", "2025-01-15")
    _seed_training_load(db, athlete_user.id, "2026-01-15", weeks=16, ctl_start=40, ctl_end=90)
    _seed_training_load(db, athlete_user.id, "2025-01-15", weeks=16, ctl_start=30, ctl_end=70)

    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        f"/api/athlete/cycle-compare?race_a={race_a.id}&race_b={race_b.id}&weeks=16",
        headers=auth_headers(token),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["cycle_a"]["race"]["id"] == race_a.id
    assert d["cycle_b"]["race"]["id"] == race_b.id
    assert d["cycle_a"]["stats"]["has_data"] is True
    assert d["cycle_b"]["stats"]["has_data"] is True
    # El ciclo A rampeo mas alto (90 vs 70) -> pico CTL mayor
    assert d["cycle_a"]["stats"]["peak_ctl"] > d["cycle_b"]["stats"]["peak_ctl"]
    # Cada punto trae days_to_race relativo a SU propia carrera (0 = dia de carrera)
    last_a = d["cycle_a"]["series"][-1]
    last_b = d["cycle_b"]["series"][-1]
    assert last_a["days_to_race"] == 0
    assert last_a["date_iso"] == "2026-01-15"
    assert last_b["days_to_race"] == 0
    assert last_b["date_iso"] == "2025-01-15"


def test_cycle_compare_no_training_data(client, db, athlete_user):
    """Carreras sin ningun dato de carga en la ventana previa -> has_data False, no error."""
    race_a = _seed_race(db, athlete_user.id, "Carrera sin datos A", "2026-06-01")
    race_b = _seed_race(db, athlete_user.id, "Carrera sin datos B", "2025-06-01")

    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        f"/api/athlete/cycle-compare?race_a={race_a.id}&race_b={race_b.id}",
        headers=auth_headers(token),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["cycle_a"]["stats"]["has_data"] is False
    assert d["cycle_b"]["stats"]["has_data"] is False
    assert d["cycle_a"]["series"] == []


def test_cycle_compare_race_not_found(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare?race_a=no-existe&race_b=tampoco-existe",
        headers=auth_headers(token),
    )
    assert r.status_code == 404


def test_cycle_compare_rejects_other_users_race(client, db, athlete_user, coach_user):
    """Un usuario no puede comparar usando la carrera de otro usuario."""
    foreign_race = _seed_race(db, coach_user.id, "Carrera de otro atleta", "2026-01-15")
    own_race = _seed_race(db, athlete_user.id, "Mi carrera", "2025-01-15")

    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        f"/api/athlete/cycle-compare?race_a={foreign_race.id}&race_b={own_race.id}",
        headers=auth_headers(token),
    )
    assert r.status_code == 404


def test_cycle_compare_requires_auth(client, db):
    r = client.get("/api/athlete/cycle-compare?race_a=x&race_b=y")
    assert r.status_code == 401


def test_cycle_compare_with_direct_dates(client, db, athlete_user):
    """No hace falta registrar una carrera — date_a/date_b alcanza."""
    _seed_training_load(db, athlete_user.id, "2026-01-15", weeks=16, ctl_start=40, ctl_end=95)
    _seed_training_load(db, athlete_user.id, "2025-01-15", weeks=16, ctl_start=30, ctl_end=72)

    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare"
        "?date_a=2026-01-15&label_a=Prep+2026"
        "&date_b=2025-01-15&label_b=Prep+2025"
        "&weeks=16",
        headers=auth_headers(token),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["cycle_a"]["race"]["id"] is None
    assert d["cycle_a"]["race"]["name"] == "Prep 2026"
    assert d["cycle_a"]["race"]["date_iso"] == "2026-01-15"
    assert d["cycle_b"]["race"]["name"] == "Prep 2025"
    assert d["cycle_a"]["stats"]["has_data"] is True
    assert d["cycle_a"]["stats"]["peak_ctl"] > d["cycle_b"]["stats"]["peak_ctl"]


def test_cycle_compare_direct_date_default_label(client, db, athlete_user):
    """Sin label_a/label_b, usa un nombre por defecto en vez de fallar."""
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare?date_a=2026-01-15&date_b=2025-01-15",
        headers=auth_headers(token),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["cycle_a"]["race"]["name"] == "Ciclo A"
    assert d["cycle_b"]["race"]["name"] == "Ciclo B"


def test_cycle_compare_invalid_date(client, db, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare?date_a=no-es-una-fecha&date_b=2025-01-15",
        headers=auth_headers(token),
    )
    assert r.status_code == 400


def test_cycle_compare_missing_anchor(client, db, athlete_user):
    """Sin race_a ni date_a (y lo mismo para B) -> 400, no 500."""
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare?date_b=2025-01-15",
        headers=auth_headers(token),
    )
    assert r.status_code == 400


def test_cycle_compare_without_cycle_c_returns_none(client, db, athlete_user):
    """Sin date_c/race_c, cycle_c va en null (ciclo C es opcional)."""
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare?date_a=2026-01-15&date_b=2025-01-15",
        headers=auth_headers(token),
    )
    assert r.status_code == 200
    assert r.json()["cycle_c"] is None


def test_cycle_compare_with_cycle_c(client, db, athlete_user):
    """Con date_c, se devuelven los 3 ciclos."""
    _seed_training_load(db, athlete_user.id, "2026-01-15", weeks=16, ctl_start=40, ctl_end=95)
    _seed_training_load(db, athlete_user.id, "2025-01-15", weeks=16, ctl_start=30, ctl_end=72)
    _seed_training_load(db, athlete_user.id, "2024-01-15", weeks=16, ctl_start=20, ctl_end=55)

    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get(
        "/api/athlete/cycle-compare"
        "?date_a=2026-01-15&date_b=2025-01-15&date_c=2024-01-15&label_c=Prep+2024",
        headers=auth_headers(token),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["cycle_c"] is not None
    assert d["cycle_c"]["race"]["name"] == "Prep 2024"
    assert d["cycle_c"]["stats"]["has_data"] is True
    # Los tres ciclos rampearon a picos distintos y crecientes
    assert d["cycle_a"]["stats"]["peak_ctl"] > d["cycle_b"]["stats"]["peak_ctl"] > d["cycle_c"]["stats"]["peak_ctl"]
