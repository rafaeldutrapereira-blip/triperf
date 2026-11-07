"""M1 — FTP Indoor (rodillo) separado del FTP principal."""
import importlib.util
from pathlib import Path

import sqlalchemy as sa

from api.tests.conftest import login, auth_headers

ROOT = Path(__file__).resolve().parents[2]


def _h(client, athlete_user):
    return auth_headers(login(client, "athlete@test.com", "AthlPass123"))


def test_lectura_ftp_indoor_null_por_defecto(client, athlete_user):
    r = client.get("/api/athlete/profile", headers=_h(client, athlete_user))
    assert r.status_code == 200
    assert r.json()["ftp"] == 220
    assert r.json()["ftp_indoor"] is None


def test_guardado_y_lectura(client, athlete_user):
    h = _h(client, athlete_user)
    assert client.patch("/api/athlete/profile", json={"ftp_indoor": 205}, headers=h).status_code == 200
    p = client.get("/api/athlete/profile", headers=h).json()
    assert p["ftp_indoor"] == 205 and p["ftp"] == 220  # el principal no se toca


def test_cero_vacia_y_vuelve_al_principal(client, db, athlete_user):
    from api.routes.athlete_routes import effective_indoor_ftp
    h = _h(client, athlete_user)
    client.patch("/api/athlete/profile", json={"ftp_indoor": 205}, headers=h)
    db.refresh(athlete_user)
    assert effective_indoor_ftp(athlete_user) == 205
    client.patch("/api/athlete/profile", json={"ftp_indoor": 0}, headers=h)
    db.refresh(athlete_user)
    assert athlete_user.ftp_indoor is None
    assert effective_indoor_ftp(athlete_user) == 220


def test_fuera_de_rango_rechazado(client, athlete_user):
    h = _h(client, athlete_user)
    assert client.patch("/api/athlete/profile", json={"ftp_indoor": 5000}, headers=h).status_code == 422
    assert client.patch("/api/athlete/profile", json={"ftp_indoor": -1}, headers=h).status_code == 422


def test_fallback_sin_ninguno():
    from api.routes.athlete_routes import effective_indoor_ftp

    class U: ftp = None; ftp_indoor = None
    assert effective_indoor_ftp(U) is None


def _capture_send(monkeypatch):
    seen = {}
    import garmin_connector

    def fake(session, **kw):
        seen["session"] = session
        return {"workoutId": "w1"}
    monkeypatch.setattr(garmin_connector, "schedule_workout_for_athlete", fake)
    return seen


def _send(client, h, db, user):
    from api.crypto import encrypt
    user.plan_nivel = "elite"
    user.garmin_email = "g@x.com"
    user.garmin_password = encrypt("pw")
    db.commit()
    body = {"name": "t", "date": "2026-11-10", "sport": "bike",
            "blocks": [{"type": "steady", "duration": 600, "power": 0.9}]}
    return client.post("/api/athlete/indoor-workout/send-to-garmin", json=body, headers=h)


def test_sesion_indoor_usa_ftp_indoor(client, db, athlete_user, monkeypatch):
    seen = _capture_send(monkeypatch)
    h = _h(client, athlete_user)
    client.patch("/api/athlete/profile", json={"ftp_indoor": 200}, headers=h)
    r = _send(client, h, db, athlete_user)
    assert r.status_code == 200, r.text
    assert seen["session"]["ftp"] == 200


def test_sesion_indoor_sin_ftp_indoor_usa_principal(client, db, athlete_user, monkeypatch):
    seen = _capture_send(monkeypatch)
    h = _h(client, athlete_user)
    r = _send(client, h, db, athlete_user)
    assert r.status_code == 200, r.text
    assert seen["session"]["ftp"] == 220


def test_migracion_ftp_indoor_idempotente(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = ROOT / "alembic" / "versions" / "b5c6d7e8f9a0_add_ftp_indoor_to_users.py"
    spec = importlib.util.spec_from_file_location("mig_m1", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "b4c5d6e7f8a9"
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE users (id VARCHAR PRIMARY KEY, ftp INTEGER)"))
        c.execute(sa.text("INSERT INTO users VALUES ('u1', 250)"))
    for _ in range(2):
        with eng.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mig.upgrade()
    with eng.connect() as c:
        cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(users)"))]
        assert cols.count("ftp_indoor") == 1
        assert c.execute(sa.text("SELECT ftp, ftp_indoor FROM users")).fetchone() == (250, None)


def test_ui_indoor_y_i18n():
    html = (ROOT / "indoor_workout.html").read_text(encoding="utf-8")
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    assert 'id="ftp-indoor-input"' in html and "ftp_indoor" in html
    assert i18n.count("iw_ftp_indoor_label:") == 3
