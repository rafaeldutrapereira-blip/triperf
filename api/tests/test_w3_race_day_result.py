"""W3 - Race Day: Registrar Resultado envia race_id, errores visibles, TSB 0 valido."""
import os
import re
from datetime import datetime, timedelta

from api.models import GarminTrainingLoad, RaceEvent, RacePlan, RaceResult
from api.tests.conftest import auth_headers, login
from api.tests.text_match import squash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _setup(db, athlete_user, con_plan=True):
    athlete_user.plan_nivel = "elite"
    race = RaceEvent(user_id=athlete_user.id, name="Ironman W3",
                     date_iso=(datetime.utcnow().date() + timedelta(days=30)).isoformat(),
                     distance="full")
    db.add(race)
    db.commit()
    if con_plan:
        db.add(RacePlan(user_id=athlete_user.id, race_event_id=race.id,
                        total_pred_s=36000, bike_target_power=200, run_target_pace=330))
        db.commit()
    return race


def _hdr(client):
    return auth_headers(login(client, "athlete@test.com", "AthlPass123"))


BODY = {"swim_s": 3600, "t1_s": 200, "bike_s": 18000, "t2_s": 150, "run_s": 14400,
        "avg_power_bike_w": 195, "avg_pace_run_s_km": 340, "dnf": False}


def test_con_race_id_enlaza_y_calcula(client, db, athlete_user):
    race = _setup(db, athlete_user)
    h = _hdr(client)
    r = client.post("/api/races/record-result", json={**BODY, "race_id": race.id}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pred_error_s"] == 36350 - 36000
    assert d["pred_error_fmt"] and d["pacing_score"] is not None
    row = db.query(RaceResult).filter_by(user_id=athlete_user.id).one()
    assert row.race_event_id == race.id
    assert row.prediction_error_s == 350 and row.pacing_score is not None
    dash = client.get("/api/races/dashboard-s19", headers=h).json()
    assert dash["history"][0]["race_name"] == "Ironman W3"


def test_sin_race_id_comportamiento_previo(client, db, athlete_user):
    _setup(db, athlete_user)
    h = _hdr(client)
    r = client.post("/api/races/record-result", json=BODY, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pred_error_s"] is None and d["pred_error_fmt"] is None
    row = db.query(RaceResult).filter_by(user_id=athlete_user.id).one()
    assert row.race_event_id is None and row.prediction_error_s is None


def test_tsb_cero_no_es_none(client, db, athlete_user):
    _setup(db, athlete_user, con_plan=False)
    db.add(GarminTrainingLoad(user_id=athlete_user.id,
                              date_iso=datetime.utcnow().date().isoformat(),
                              ctl=60.0, atl=60.0, tsb=0.0))
    db.commit()
    fit = client.get("/api/races/dashboard-s19", headers=_hdr(client)).json()["fitness"]
    assert fit["tsb"] == 0.0 and fit["tsb"] is not None


def test_front_envia_race_id_y_chequea_ok():
    src = _read("race_day.html")
    i = src.index("function saveResult(")
    body = squash(src[i:src.index("function loadHistory(")])
    assert "payload.race_id=linkedRaceId" in body
    assert ".then(_okJson)" in body
    assert "_rdNextRaceId=nr.id" in squash(src)
    assert "rd_saved_no_race" in body
    for fn in ("function loadDashboard(", "function loadHistory("):
        j = src.index(fn)
        assert ".then(_okJson)" in squash(src[j:j + 900])
    dash = src[src.index("function loadDashboard("):src.index("function renderDashboard(")]
    assert "return r.json()" not in squash(dash)


def test_i18n_claves_tres_idiomas():
    i18n = _read("i18n.js")
    for k in ("rd_err_http", "rd_saved_no_race"):
        assert len(re.findall(r"\b%s:" % k, i18n)) == 3, k
