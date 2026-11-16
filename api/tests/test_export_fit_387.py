"""
EXPORT-FIT (BUILD 387) -- el .fit generado re-parsea con fitparse y sus pasos
coinciden con los bloques (bici, run, natacion); endpoint 200/404/400; sin FTP
el objetivo queda abierto (nunca vatios inventados).
"""
import io

import pytest

from .conftest import login, auth_headers
from ..auth import hash_password
from ..fit_export import FitExportError, build_workout_fit, fit_crc, safe_filename
from ..models import User

fitparse = pytest.importorskip("fitparse")

BASE = "/api/athlete/indoor-workouts"
BIKE = [
    {"type": "warmup", "duration": 600, "power_low": 0.5, "power_high": 0.75},
    {"type": "steady", "duration": 300, "power": 0.8},
    {"type": "intervals", "repeat": 4, "on_duration": 240, "off_duration": 120,
     "on_power": 1.0, "off_power": 0.5},
    {"type": "freeride", "duration": 120},
    {"type": "cooldown", "duration": 300, "power_low": 0.6, "power_high": 0.6},
]
RUN = [
    {"type": "steady", "mode": "pace", "duration": 900, "val": 300},        # 5:00/km
    {"type": "intervals", "mode": "hr", "repeat": 3, "on_duration": 180, "off_duration": 90,
     "on_val": 0.9, "off_val": 0.7},
    {"type": "ramp", "mode": "pace", "duration": 300, "val_low": 330, "val_high": 270},
]
SWIM = [
    {"type": "warmup", "reps": 1, "dist": 200, "rest": 0, "stroke": "full"},
    {"type": "main", "reps": 4, "dist": 100, "rest": 20, "pace": 100, "stroke": "full", "equipment": "fins"},
    {"type": "drill", "reps": 2, "dist": 50, "rest": 0, "stroke": "kick"},
]


def _parse(data):
    ff = fitparse.FitFile(io.BytesIO(data), check_crc=True)
    msgs = list(ff.get_messages())
    by = {}
    for m in msgs:
        by.setdefault(m.name, []).append({f.name: f.raw_value for f in m.fields})
    return by


def test_crc_y_cabecera():
    r = build_workout_fit("x", "bike", BIKE, ftp=250)
    assert r.data[8:12] == b".FIT"
    assert fit_crc(r.data[:-2]) == int.from_bytes(r.data[-2:], "little")
    assert fit_crc(b"") == 0


def test_bici_pasos_coinciden_con_bloques():
    r = build_workout_fit("Sweet spot ñ", "bike", BIKE, ftp=250)
    by = _parse(r.data)
    assert by["file_id"][0]["type"] == 5
    assert by["workout"][0]["sport"] == 2 and by["workout"][0]["num_valid_steps"] == len(by["workout_step"])
    assert by["workout"][0]["wkt_name"].startswith("Sweet spot")
    st = by["workout_step"]
    # warmup = rampa -> abierto (no se aproxima)
    assert st[0]["duration_time"] == 600000 and st[0]["target_type"] == 2 and st[0]["intensity"] == 2
    # steady 80% de 250 = 200 W (+1000)
    assert st[1]["duration_time"] == 300000 and st[1]["target_type"] == 4
    assert st[1]["custom_target_power_low"] == st[1]["custom_target_power_high"] == 1200
    # intervalos: on 250 W, off 125 W, repetir desde el paso 2, 4 veces
    assert (st[2]["duration_time"], st[2]["custom_target_power_low"]) == (240000, 1250)
    assert (st[3]["duration_time"], st[3]["custom_target_power_low"]) == (120000, 1125)
    assert st[4]["duration_type"] == 6 and st[4]["duration_step"] == 2 and st[4]["repeat_steps"] == 4
    # freeride abierto sin ser "degradado"; cooldown constante = 150 W exacto
    assert st[5]["target_type"] == 2 and st[5]["duration_time"] == 120000
    assert st[6]["custom_target_power_low"] == 1150 and st[6]["intensity"] == 3
    assert [o["reason"] for o in r.open_steps] == ["ramp"] and r.open_steps[0]["step"] == 1
    assert not r.missing_ftp


def test_bici_sin_ftp_no_inventa_vatios():
    for ftp in (None, 0):
        r = build_workout_fit("x", "bike", BIKE, ftp=ftp)
        assert r.missing_ftp
        for s in _parse(r.data)["workout_step"]:
            assert s.get("custom_target_power_low") is None
            assert s["target_type"] == 2
        reasons = {o["reason"] for o in r.open_steps}
        assert "no_ftp" in reasons


def test_run_ritmo_fc_y_rampa_abierta():
    r = build_workout_fit("Rodaje", "run", RUN, fcmax=190)
    by = _parse(r.data)
    assert by["workout"][0]["sport"] == 1
    st = by["workout_step"]
    # 300 s/km = 3.333 m/s = 3333 mm/s
    assert st[0]["target_type"] == 0 and st[0]["custom_target_speed_low"] == 3333
    # FC: 0.9*190 = 171 bpm (+100) y 0.7*190 = 133 (+100)
    assert st[1]["target_type"] == 1 and st[1]["custom_target_heart_rate_low"] == 271
    assert st[2]["custom_target_heart_rate_low"] == 233
    assert st[3]["duration_type"] == 6 and st[3]["repeat_steps"] == 3
    assert st[4]["target_type"] == 2   # rampa de ritmo: abierta
    assert [o["reason"] for o in r.open_steps] == ["ramp"]


def test_run_hr_sin_fcmax_abierto():
    r = build_workout_fit("x", "run", RUN, fcmax=None)
    assert r.missing_fcmax
    reasons = [o["reason"] for o in r.open_steps]
    assert reasons.count("no_fcmax") == 2
    for s in _parse(r.data)["workout_step"][1:3]:
        assert s["target_type"] == 2


def test_natacion_distancia_descanso_y_ritmo():
    r = build_workout_fit("Nado", "swim", SWIM)
    by = _parse(r.data)
    assert by["workout"][0]["sport"] == 5 and by["workout"][0]["sub_sport"] == 17
    st = by["workout_step"]
    # calentamiento 200 m (distancia en cm)
    assert st[0]["duration_type"] == 1 and st[0]["duration_distance"] == 20000
    # 4x100 con 20 s entre series: (100m + descanso) x3 + 100m final
    assert st[1]["duration_distance"] == 10000 and st[1]["custom_target_speed_low"] == 1000  # 100 s/100m
    assert st[1]["equipment"] == 1
    assert st[2]["duration_type"] == 0 and st[2]["duration_time"] == 20000 and st[2]["intensity"] == 1
    assert st[3]["duration_type"] == 6 and st[3]["duration_step"] == 1 and st[3]["repeat_steps"] == 3
    assert st[4]["duration_distance"] == 10000
    # 2x50 patada sin descanso -> repetir el paso 2 veces, sin objetivo inventado
    assert st[5]["duration_distance"] == 5000 and st[5]["target_type"] == 2
    assert st[6]["repeat_steps"] == 2 and st[6]["duration_step"] == 5
    assert r.open_steps == []


def test_sin_pasos_validos_lanza():
    with pytest.raises(FitExportError):
        build_workout_fit("x", "bike", [{"type": "zzz"}, "no-dict"], ftp=200)
    with pytest.raises(FitExportError):
        build_workout_fit("x", "bike", [], ftp=200)


def test_bloque_desconocido_se_cuenta():
    r = build_workout_fit("x", "bike", BIKE + [{"type": "zzz"}], ftp=200)
    assert r.skipped_blocks == 1


def test_nombre_de_archivo():
    assert safe_filename("Sweet spot ñ/áé", "2026-11-05") == "Sweet_spot_n_ae_2026-11-05.fit"


# ── endpoint ─────────────────────────────────────────────────────────────
def _user(db, email, ftp=None, ftp_indoor=None, fcmax=None, plan="elite"):
    u = User(email=email, nombre=email, password_hash=hash_password("S4Pass-12345"),
             rol="athlete", plan_nivel=plan, activo=True, ftp=ftp, ftp_indoor=ftp_indoor, fcmax=fcmax)
    db.add(u)
    db.commit()
    return u


def _h(client, email):
    h = auth_headers(login(client, email, "S4Pass-12345"))
    client.cookies.clear()
    return h


def _mk(client, h, blocks, sport="bike", name="Sweet spot"):
    r = client.post(BASE, json={"name": name, "sport": sport, "planned_date": "2026-11-05",
                                "blocks": blocks}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_endpoint_descarga_bici_con_ftp_indoor(client, db):
    _user(db, "fit1@test.com", ftp=220, ftp_indoor=250)
    h = _h(client, "fit1@test.com")
    wid = _mk(client, h, BIKE)
    r = client.get(f"{BASE}/{wid}/export-fit", headers=h)
    assert r.status_code == 200
    assert 'attachment; filename="Sweet_spot_2026-11-05.fit"' == r.headers["content-disposition"]
    assert r.headers["x-labx-fit-missing-ftp"] == "0"
    assert r.headers["x-labx-fit-open-steps"] == "1:ramp"
    st = _parse(r.content)["workout_step"]
    assert st[1]["custom_target_power_low"] == 1200   # 0.8 x 250 (FTP indoor)


def test_endpoint_sin_ftp_avisa(client, db):
    _user(db, "fit2@test.com")
    h = _h(client, "fit2@test.com")
    wid = _mk(client, h, BIKE)
    r = client.get(f"{BASE}/{wid}/export-fit", headers=h)
    assert r.status_code == 200
    assert r.headers["x-labx-fit-missing-ftp"] == "1"
    assert "no_ftp" in r.headers["x-labx-fit-open-steps"]
    assert all(s.get("custom_target_power_low") is None for s in _parse(r.content)["workout_step"])


def test_endpoint_run_y_swim(client, db):
    _user(db, "fit3@test.com", fcmax=190)
    h = _h(client, "fit3@test.com")
    rid = _mk(client, h, RUN, sport="run", name="Rodaje")
    r = client.get(f"{BASE}/{rid}/export-fit", headers=h)
    assert r.status_code == 200 and r.headers["x-labx-fit-missing-fcmax"] == "0"
    sid = _mk(client, h, SWIM, sport="swim", name="Nado")
    r = client.get(f"{BASE}/{sid}/export-fit", headers=h)
    assert r.status_code == 200 and _parse(r.content)["workout"][0]["sport"] == 5


def test_endpoint_ajeno_404(client, db):
    _user(db, "fit4a@test.com", ftp=200)
    _user(db, "fit4b@test.com", ftp=200)
    wid = _mk(client, _h(client, "fit4a@test.com"), BIKE)
    assert client.get(f"{BASE}/{wid}/export-fit", headers=_h(client, "fit4b@test.com")).status_code == 404
    assert client.get(f"{BASE}/no-existe/export-fit", headers=_h(client, "fit4b@test.com")).status_code == 404


def test_endpoint_sin_bloques_400(client, db):
    from ..models import IndoorWorkout
    u = _user(db, "fit5@test.com", ftp=200)
    h = _h(client, "fit5@test.com")
    w = IndoorWorkout(user_id=u.id, name="vacio", sport="bike", blocks_json="[]")
    db.add(w)
    db.commit()
    r = client.get(f"{BASE}/{w.id}/export-fit", headers=h)
    assert r.status_code == 400
    # bloques todos invalidos tambien -> 400 claro (no un archivo vacio)
    w2 = IndoorWorkout(user_id=u.id, name="raro", sport="bike", blocks_json='[{"type":"zzz"}]')
    db.add(w2)
    db.commit()
    assert client.get(f"{BASE}/{w2.id}/export-fit", headers=h).status_code == 400


def test_endpoint_requiere_plan(client, db):
    _user(db, "fit6@test.com", plan="basico")
    h = _h(client, "fit6@test.com")
    assert client.get(f"{BASE}/x/export-fit", headers=h).status_code in (402, 403)
