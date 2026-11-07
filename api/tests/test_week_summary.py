"""Sprint 3 -- GET /api/training-plan/week-summary (franja semanal de Mi Plan)."""
from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import (
    GarminActivity, GarminHealthDaily, GarminSleepSession, GarminTrainingLoad,
    OwnPlanSession, User,
)

URL = "/api/training-plan/week-summary"
PW = "Ws3Pass-12345"
MON = "2026-11-02"  # lunes


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


def test_requires_auth(client):
    client.cookies.clear()
    assert client.get(f"{URL}?monday={MON}").status_code in (401, 403)


def test_fecha_invalida(client, db):
    _user(db, "ws_bad@test.com")
    h = _h(client, "ws_bad@test.com")
    assert client.get(f"{URL}?monday=2/11", headers=h).status_code == 400


def test_semana_vacia_no_inventa_nada(client, db):
    _user(db, "ws_empty@test.com")
    h = _h(client, "ws_empty@test.com")
    j = client.get(f"{URL}?monday={MON}", headers=h).json()
    assert len(j["days"]) == 7 and j["monday"] == MON and j["sunday"] == "2026-11-08"
    for d in j["days"]:
        assert d["wellness"] == {} and d["done"] == [] and d["planned"] == []
    assert j["summary"] == {"dur_min": None, "tss": None, "ctl": None, "atl": None,
                            "tsb": None, "ramp": None, "pmc_date": None}


def test_semana_con_datos_y_normaliza_al_lunes(client, db):
    u = _user(db, "ws_full@test.com")
    db.add_all([
        GarminActivity(user_id=u.id, activity_id="a1", name="Rodaje", sport="run",
                       date_iso="2026-11-03", dur_min=50, dist_km=9.0, tss=55.0),
        GarminActivity(user_id=u.id, activity_id="a2", name="Bici", sport="bike",
                       date_iso="2026-11-05", dur_min=70, dist_km=30.0, tss=60.0),
        GarminSleepSession(user_id=u.id, date_iso="2026-11-03", total_min=450),
        GarminHealthDaily(user_id=u.id, date_iso="2026-11-03", hrv_last_night=62.4,
                          resting_hr=48),
        GarminHealthDaily(user_id=u.id, date_iso="2026-11-04", resting_hr=50),
        OwnPlanSession(user_id=u.id, date_iso="2026-11-06", sport="swim", name="Nado",
                       dur_min=45, tss=40.0),
        GarminTrainingLoad(user_id=u.id, date_iso="2026-10-26", ctl=40, atl=45, tsb=-5, tss=30),
        GarminTrainingLoad(user_id=u.id, date_iso="2026-11-03", ctl=44, atl=50, tsb=-6, tss=55),
        GarminTrainingLoad(user_id=u.id, date_iso="2026-11-05", ctl=46, atl=52, tsb=-6, tss=60),
        GarminTrainingLoad(user_id=u.id, date_iso="2026-11-02", ctl=43, atl=47, tsb=-4, tss=0),
    ])
    db.commit()
    h = _h(client, "ws_full@test.com")
    j = client.get(f"{URL}?monday=2026-11-04", headers=h).json()  # miercoles -> lunes
    assert j["monday"] == MON
    d = {x["date_iso"]: x for x in j["days"]}
    assert d["2026-11-03"]["wellness"] == {"sleep_h": 7.5, "hrv": 62, "rhr": 48}
    assert d["2026-11-04"]["wellness"] == {"rhr": 50}  # solo lo que existe
    assert d["2026-11-03"]["done"][0]["tss"] == 55.0
    assert d["2026-11-06"]["planned"][0]["name"] == "Nado"
    s = j["summary"]
    assert s["dur_min"] == 120 and s["tss"] == 115.0
    # ultima fila <= domingo = 05/11; ramp contra la fila del 29/10 NO existe -> None
    assert (s["pmc_date"], s["ctl"], s["atl"], s["tsb"]) == ("2026-11-05", 46.0, 52.0, -6.0)
    assert s["ramp"] is None


def test_ramp_con_fila_de_hace_7_dias(client, db):
    u = _user(db, "ws_ramp@test.com")
    db.add_all([
        GarminTrainingLoad(user_id=u.id, date_iso="2026-11-01", ctl=40, atl=40, tsb=0, tss=0),
        GarminTrainingLoad(user_id=u.id, date_iso="2026-11-08", ctl=45.5, atl=50, tsb=-4.5, tss=70),
    ])
    db.commit()
    h = _h(client, "ws_ramp@test.com")
    s = client.get(f"{URL}?monday={MON}", headers=h).json()["summary"]
    assert s["pmc_date"] == "2026-11-08" and s["ramp"] == 5.5


def test_aislamiento_entre_usuarios(client, db):
    a = _user(db, "ws_a@test.com")
    _user(db, "ws_b@test.com")
    db.add(GarminActivity(user_id=a.id, activity_id="x", name="X", sport="run",
                          date_iso="2026-11-03", dur_min=30, tss=20.0))
    db.commit()
    h = _h(client, "ws_b@test.com")
    j = client.get(f"{URL}?monday={MON}", headers=h).json()
    assert all(d["done"] == [] for d in j["days"])
