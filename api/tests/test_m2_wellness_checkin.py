"""M2 — check-in subjetivo (energia, animo, dolor_muscular, estres) en garmin_health_daily."""
import importlib.util
import re
from datetime import date, timedelta
from pathlib import Path

import sqlalchemy as sa

from api import garmin_ingest as gi
from api import intervals_sync_service as iss
from api.models import GarminHealthDaily
from api.tests.conftest import login, auth_headers

ROOT = Path(__file__).resolve().parents[2]
URL = "/api/athlete/health/checkin"
FIELDS = ("energia", "animo", "dolor_muscular", "estres")


def _h(client, athlete_user):
    return auth_headers(login(client, "athlete@test.com", "AthlPass123"))


def test_lectura_vacia(client, athlete_user):
    r = client.get(URL, headers=_h(client, athlete_user))
    assert r.status_code == 200
    j = r.json()
    assert j["saved"] is False and all(j[f] is None for f in FIELDS)


def test_guardado_y_lectura(client, db, athlete_user):
    h = _h(client, athlete_user)
    body = {"energia": 4, "animo": 3, "dolor_muscular": 2, "estres": 5}
    assert client.post(URL, json=body, headers=h).status_code == 200
    j = client.get(URL, headers=h).json()
    assert j["saved"] is True and {f: j[f] for f in FIELDS} == body
    # Guardado parcial: solo actualiza lo enviado
    assert client.post(URL, json={"animo": 1}, headers=h).status_code == 200
    j = client.get(URL, headers=h).json()
    assert j["animo"] == 1 and j["energia"] == 4
    assert db.query(GarminHealthDaily).count() == 1


def test_fecha_pasada_y_no_pisa_dispositivo(client, db, athlete_user):
    h = _h(client, athlete_user)
    d = (date.today() - timedelta(days=2)).isoformat()
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso=d, resting_hr=48, hrv_last_night=70.0))
    db.commit()
    assert client.post(URL, json={"date_iso": d, "energia": 3}, headers=h).status_code == 200
    db.expire_all()
    row = db.query(GarminHealthDaily).filter_by(date_iso=d).one()
    assert row.energia == 3 and row.resting_hr == 48 and row.hrv_last_night == 70.0
    assert client.get(URL + "?date_iso=" + d, headers=h).json()["energia"] == 3


def test_validacion_rango(client, athlete_user):
    h = _h(client, athlete_user)
    for bad in (0, 6, -1):
        assert client.post(URL, json={"energia": bad}, headers=h).status_code in (400, 422)
    assert client.post(URL, json={}, headers=h).status_code == 400


def test_validacion_fecha(client, athlete_user):
    h = _h(client, athlete_user)
    fut = (date.today() + timedelta(days=1)).isoformat()
    assert client.post(URL, json={"date_iso": fut, "energia": 3}, headers=h).status_code == 400
    assert client.post(URL, json={"date_iso": "ayer", "energia": 3}, headers=h).status_code == 400
    assert client.get(URL + "?date_iso=2999-01-01", headers=h).status_code == 400


def test_requiere_auth(client):
    assert client.get(URL).status_code in (401, 403)
    assert client.post(URL, json={"energia": 3}).status_code in (401, 403)


def _row_con_checkin(db, user, d):
    row = GarminHealthDaily(user_id=user.id, date_iso=d, energia=4, animo=3, dolor_muscular=2, estres=1)
    db.add(row)
    db.commit()
    return row


def test_regresion_sync_garmin_oficial_no_pisa(db, athlete_user):
    d = date.today().isoformat()
    _row_con_checkin(db, athlete_user, d)
    gi._upsert_daily(db, athlete_user.id, {
        "calendarDate": d, "steps": 9000, "restingHeartRateInBeatsPerMinute": 50,
        "averageStressLevel": 30})
    db.commit()
    db.expire_all()
    r = db.query(GarminHealthDaily).filter_by(date_iso=d).one()
    assert r.steps == 9000 and r.avg_stress == 30
    assert (r.energia, r.animo, r.dolor_muscular, r.estres) == (4, 3, 2, 1)


def test_regresion_sync_intervals_no_pisa(db, athlete_user):
    d = date.today().isoformat()
    _row_con_checkin(db, athlete_user, d)
    iss._upsert_wellness(db, athlete_user.id,
                         {"id": d, "restingHR": 52, "hrv": 65, "steps": 8000,
                          "fatigue": 4, "soreness": 5, "mood": 1, "stress": 5},
                         {"ignored_fields": 0})
    db.commit()
    db.expire_all()
    r = db.query(GarminHealthDaily).filter_by(date_iso=d).one()
    assert r.resting_hr == 52
    assert (r.energia, r.animo, r.dolor_muscular, r.estres) == (4, 3, 2, 1)


def test_regresion_ningun_sync_referencia_las_columnas():
    # Garmin legacy (garmin_pull_service), oficial (garmin_ingest) e intervals
    for mod in ("garmin_pull_service.py", "garmin_ingest.py", "intervals_sync_service.py"):
        src = (ROOT / "api" / mod).read_text(encoding="utf-8")
        for f in FIELDS:
            pat = r"\.%s\b|\b%s\s*=[^=]|[\"']%s[\"']" % (f, f, f)
            assert not re.search(pat, src), f"{mod} no debe tocar {f}"


def test_migracion_aditiva():
    path = next((ROOT / "alembic" / "versions").glob("b6c7d8e9f0a1_*.py"))
    spec = importlib.util.spec_from_file_location("m2mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "b5c6d7e8f9a0" and set(mod._COLS) == set(FIELDS)


def test_ui_e_i18n():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    assert 'id="lx-checkin"' in html and "/athlete/health/checkin" in html
    for k in ("ckin_title", "ckin_energy", "ckin_mood", "ckin_soreness", "ckin_stress",
              "ckin_save", "ckin_saved", "ckin_saved_prev", "ckin_pick", "ckin_error"):
        assert len(re.findall(r"(?<![A-Za-z_])%s:" % k, i18n)) == 3, k
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 329
