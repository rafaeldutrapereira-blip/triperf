"""
S28 — check-in unico de 9 campos en "Estado de hoy".

1. Comparativo antes/despues: con las mismas respuestas, el flujo viejo (dos
   formularios -> dos POST) y el flujo nuevo (formulario unico -> estado-checkin.js
   -> los mismos dos POST) deben dejar EXACTAMENTE los mismos puntajes Recovery y MFS.
2. Compatibilidad historica: un dia guardado con dos check-ins separados sigue
   leyendose igual por los endpoints de lectura.
3. Estructura de estado.html / i18n / sw.js.
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta

import pytest

from api.models import GarminHealthDaily, GarminSleepSession, GarminTrainingLoad, User
from api.auth import hash_password
from api.tests.conftest import auth_headers, login
from api.tests.text_match import squash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAY = datetime.utcnow().date().isoformat()

NODE = shutil.which("node")

# Respuestas (1-5) de los 9 campos. mood/motivation son los dos compartidos.
ANSWER_SETS = [
    dict(energy=4, soreness=3, stress=2, sleep_quality=5, mood=4, motivation=3, anxiety=5, focus=2, confidence=4),
    dict(energy=1, soreness=1, stress=1, sleep_quality=1, mood=1, motivation=1, anxiety=1, focus=1, confidence=1),
    dict(energy=5, soreness=5, stress=5, sleep_quality=5, mood=5, motivation=5, anxiety=5, focus=5, confidence=5),
    dict(energy=3, soreness=4, stress=3, sleep_quality=2, mood=3, motivation=2, anxiety=3, focus=4, confidence=1),
]


def _legacy_payloads(a, note=None):
    """Replica EXACTA de lo que armaban los dos formularios anteriores."""
    well = {"date_iso": DAY, "notes": note}
    for f in ("energy", "mood", "soreness", "motivation", "stress", "sleep_quality"):
        if a.get(f):
            well[f] = a[f]
    men = {
        "date_iso": DAY,
        "anxiety": a.get("anxiety") or None,
        "motivation": a.get("motivation") or None,
        "focus": a.get("focus") or None,
        "confidence": a.get("confidence") or None,
        "mood": a.get("mood") or None,
        "notes": note,
    }
    return well, men


def _unified_payloads(a, note=None):
    """Payloads reales del modulo JS que usa estado.html (ejecutado con node)."""
    script = (
        "const EC=require(process.argv[1]);"
        "const o=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(EC.buildPayloads(o.a,"
        "{dateIso:o.d,touched:{},notes:o.n,notesTouched:!!o.n})));"
    )
    out = subprocess.run(
        [NODE, "-e", script, os.path.join(ROOT, "estado-checkin.js"),
         json.dumps({"a": a, "d": DAY, "n": note})],
        capture_output=True, text=True, check=True,
    ).stdout
    r = json.loads(out)
    return r["well"], r["men"]


def _mk_user(db, email):
    u = User(email=email, nombre=email, password_hash=hash_password("Passw0rd!x"),
             rol="athlete", plan_nivel="elite", activo=True, fcmax=182)
    db.add(u)
    db.commit()
    db.refresh(u)
    # Datos fisiologicos identicos para que el Recovery tenga base real.
    db.add(GarminHealthDaily(user_id=u.id, date_iso=DAY, hrv_last_night=55.0, hrv_weekly_avg=60.0,
                             body_battery_max=80, body_battery_end=60))
    db.add(GarminSleepSession(user_id=u.id, date_iso=DAY, total_min=450, deep_min=80, light_min=250,
                              rem_min=100, awake_min=20))
    db.add(GarminTrainingLoad(user_id=u.id, date_iso=DAY, ctl=50.0, atl=55.0, tsb=-5.0, tss=60.0))
    db.commit()
    return u


def _scores(client, token):
    h = auth_headers(token)
    rec = client.get(f"/api/recovery/dashboard?date_iso={DAY}", headers=h).json()["recovery"]
    men = client.get(f"/api/mental/dashboard?date_iso={DAY}", headers=h).json()["today"]
    return (rec["score"], rec.get("factors")), (men["score"], men["level"])


def _run_flow(client, token, well, men):
    h = auth_headers(token)
    mfs = None
    if well:
        r = client.post("/api/recovery/wellness", json=well, headers=h)
        assert r.status_code in (200, 201), r.text
    if men:
        r = client.post("/api/mental/checkin", json=men, headers=h)
        assert r.status_code == 200, r.text
        mfs = (r.json()["mfs_score"], r.json()["mfs_level"])
    return mfs


@pytest.mark.skipif(NODE is None, reason="node no disponible")
@pytest.mark.parametrize("answers", ANSWER_SETS)
def test_mismos_datos_mismos_puntajes_recovery_y_mfs(client, db, answers):
    legacy = _mk_user(db, "legacy@test.com")
    unified = _mk_user(db, "unified@test.com")
    tl = login(client, "legacy@test.com", "Passw0rd!x")
    tu = login(client, "unified@test.com", "Passw0rd!x")

    lw, lm = _legacy_payloads(answers, note="nota")
    uw, um = _unified_payloads(answers, note="nota")
    # El payload resultante es identico al de los formularios anteriores
    assert uw == lw
    assert um == lm

    mfs_l = _run_flow(client, tl, lw, lm)
    mfs_u = _run_flow(client, tu, uw, um)
    assert mfs_l == mfs_u and mfs_l[0] is not None
    s_l, s_u = _scores(client, tl), _scores(client, tu)
    assert s_l == s_u
    assert s_l[0][0] is not None and s_l[1][0] is not None


@pytest.mark.skipif(NODE is None, reason="node no disponible")
def test_historico_dos_checkins_se_lee_igual_y_resave_sin_tocar_conserva(client, db):
    """Dia guardado con dos check-ins que difieren en mood/motivation."""
    _mk_user(db, "hist@test.com")
    t = login(client, "hist@test.com", "Passw0rd!x")
    h = auth_headers(t)
    client.post("/api/recovery/wellness", headers=h, json={
        "date_iso": DAY, "energy": 3, "mood": 2, "soreness": 3, "motivation": 5, "stress": 3, "sleep_quality": 4})
    client.post("/api/mental/checkin", headers=h, json={
        "date_iso": DAY, "anxiety": 4, "motivation": 1, "focus": 3, "confidence": 3, "mood": 4})
    before = _scores(client, t)
    w = client.get(f"/api/recovery/wellness/{DAY}", headers=h).json()
    m = client.get(f"/api/mental/dashboard?date_iso={DAY}", headers=h).json()["checkin"]
    assert (w["mood"], w["motivation"], m["mood"], m["motivation"]) == (2, 5, 4, 1)

    # Re-guardar desde el formulario unico SIN tocar nada: el estado mostrado es
    # el de bienestar; cada destino conserva su valor y los puntajes no cambian.
    script = (
        "const EC=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(EC.buildPayloads("
        "{energy:3,mood:2,soreness:3,motivation:5,stress:3,sleep_quality:4,anxiety:4,focus:3,confidence:3},"
        "{dateIso:process.argv[2],touched:{},"
        "stored:{well:{mood:2,motivation:5},men:{mood:4,motivation:1}}})));"
    )
    out = json.loads(subprocess.run([NODE, "-e", script, os.path.join(ROOT, "estado-checkin.js"), DAY],
                                    capture_output=True, text=True, check=True).stdout)
    _run_flow(client, t, out["well"], out["men"])
    assert _scores(client, t) == before


# ── Estructura ────────────────────────────────────────────────────────────────
def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_estado_tiene_un_solo_formulario_de_9_campos():
    html = _read("estado.html")
    fields = re.findall(r'data-reg-field="(\w+)"', html)
    assert sorted(fields) == sorted(
        ["energy", "soreness", "sleep_quality", "stress", "mood", "motivation", "anxiety", "focus", "confidence"])
    assert html.count('id="reg-save"') == 1
    # Los formularios viejos ya no existen
    for old in ("fis-ws-", "men-stars-", "FIS.saveWellness", "MEN.submitCheckin", "fis-well-notes", "men-checkin-notes"):
        assert old not in html, old
    # Anclas que usan dashboard.html / detalle.html / e2e siguen existiendo
    assert 'id="est-reg-fis"' in html and 'id="est-reg-men"' in html
    assert 'src="estado-checkin.js?v=1"' in html
    # Veredicto unico y detalle por grupos intactos
    assert 'id="est-detail"' in html and "est_group_phys" in html and "est_group_mental" in html


def test_estado_guarda_bienestar_antes_que_mental():
    js = squash(_read("estado.html"))
    i_w = js.index(squash("post('/recovery/wellness'"))
    i_m = js.index(squash("post('/mental/checkin'"))
    assert i_w < i_m


def test_i18n_x3_de_los_textos_nuevos():
    src = _read("i18n.js")
    for key in ("est_reg_grp_both", "est_reg_save", "est_reg_empty", "est_reg_err"):
        assert len(re.findall(r"\b%s:" % key, src)) == 3, key


def test_sw_precachea_el_modulo_nuevo():
    sw = _read("sw.js")
    assert "'/estado-checkin.js?v=1'" in sw


def test_recovery_coach_iframe_sigue_en_recovery_html():
    html = _read("recovery.html")
    assert "view=coach" in html or "'coach'" in html
