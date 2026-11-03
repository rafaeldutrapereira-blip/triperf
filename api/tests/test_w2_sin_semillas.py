"""
W2 - Integridad: sin semillas ni metas genericas.

(a) nutrition.html: sin FTP/peso reales NO hay cifras ("Completa tu perfil") y no
    se llama a precise-splits con datos semilla.
(b) detalle.html: el insight de meta fija (CTL>=85) no se renderiza sin carrera real.
(c) /races/auto-plan marca ctl_estimated cuando cae al CTL=50 por defecto.
"""
import os
import re
import shutil
import subprocess
import textwrap
from datetime import datetime

import pytest

from api.models import GarminTrainingLoad
from api.tests.conftest import auth_headers, login
from api.tests.text_match import squash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE = shutil.which("node")


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _func(src, name):
    """Extrae el cuerpo de `function name(...) { ... }` por balanceo de llaves."""
    i = src.index("function %s(" % name)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(name)


# ---------------------------------------------------------------- (a) nutricion
def test_nutrition_estructura_sin_semilla():
    src = _read("nutrition.html")
    calc = squash(_func(src, "nutCalcLocal"))
    assert "if(!nutProfileReady())" in calc
    assert calc.index("nutProfileReady") < calc.index("predictSwim")
    fetch = squash(_func(src, "fetchPreciseSplits"))
    assert fetch.index("nutProfileReady") < fetch.index("precise-splits")
    assert "nut_complete_profile" in src
    assert "athlete_profile.html" in _func(src, "nutRenderIncomplete")


def test_nutrition_i18n_tres_idiomas():
    i18n = _read("i18n.js")
    for key in ("nut_complete_profile", "nut_complete_profile_hint",
                "dtw_race_target_dated", "rd_ctl_estimated_note"):
        assert len(re.findall(r"^\s*%s:" % key, i18n, re.M)) == 3, key


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_nutrition_sin_perfil_no_produce_cifras(tmp_path):
    src = _read("nutrition.html")
    code = "\n".join(_func(src, n) for n in
                     ("nutProfileReady", "nutRenderIncomplete", "nutCalcLocal", "fetchPreciseSplits"))
    js = textwrap.dedent("""
    var els = {};
    var document = { getElementById: function (id) {
      return els[id] || (els[id] = { textContent: '', innerHTML: '', id: id }); } };
    var _t = function (k, f) { return f; };
    var calls = { render: 0, fetch: 0 };
    function renderNutrition() { calls.render++; }
    function nutAuthTok() { return 'tok'; }
    function fetch() { calls.fetch++; return Promise.resolve(); }
    var ATH = { ftp: 235, css: 110, run: 300, weight: 62, ftpReal: false, weightReal: false };
    %s
    nutCalcLocal();
    fetchPreciseSplits();
    var out = JSON.stringify({ calls: calls, kpiTime: els['kpi-time'].innerHTML,
      choHr: els['kpi-cho-hr'].textContent, kcal: els['kpi-kcal'].textContent });
    console.log(out);
    """) % code
    f = tmp_path / "t.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    import json
    o =json.loads(r.stdout.strip().splitlines()[-1])
    assert o["calls"] == {"render": 0, "fetch": 0}
    assert "Completa tu perfil" in o["kpiTime"] and o["choHr"] == chr(0x2014)
    assert o["kcal"] == chr(0x2014)
    assert not re.search(r"\d", o["kpiTime"].replace("athlete_profile.html", ""))


# ------------------------------------------------------------------ (b) detalle
def test_detalle_sin_meta_fija_en_insights():
    src = _read("detalle.html")
    assert "dtw_race_target'" not in src          # la clave con CTL>=85 ya no se usa
    assert "CTL ≥ 85" not in src
    assert "dtw_race_target_dated" in src


@pytest.mark.skipif(not NODE, reason="node no disponible")
@pytest.mark.parametrize("kl,esperado", [
    ({}, False),
    ({"race_goal_date": ""}, False),
    ({"race_goal_date": "2020-01-01"}, False),   # carrera pasada
    ({"race_goal_date": "2999-05-17", "race_goal_name": "Ironman X"}, True),
])
def test_detalle_insight_carrera_solo_con_carrera_real(tmp_path, kl, esperado):
    import json
    src = _read("detalle.html")
    code = _func(src, "dtwRaceTargetInsight")
    js = ("var window = { KL_DATA: %s };\n"
          "function _t(k, f) { return f; }\n%s\n"
          "console.log(JSON.stringify(dtwRaceTargetInsight()));") % (json.dumps(kl), code)
    f = tmp_path / "t.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    val = json.loads(r.stdout.strip())
    if esperado:
        assert "2999-05-17" in val and "Ironman X" in val and "85" not in val
    else:
        assert val is None


# -------------------------------------------------------------------- (c) backend
def _plan(client, db, athlete_user, con_carga):
    athlete_user.plan_nivel = "elite"
    db.commit()
    if con_carga:
        db.add(GarminTrainingLoad(user_id=athlete_user.id,
                                  date_iso=datetime.utcnow().date().isoformat(),
                                  ctl=72.0, atl=70.0, tsb=2.0))
        db.commit()
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.post("/api/races/auto-plan", json={"race_type": "olympic"},
                    headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    return r.json()


def test_auto_plan_sin_carga_marca_ctl_estimado(client, db, athlete_user):
    d = _plan(client, db, athlete_user, con_carga=False)
    assert d["ctl_estimated"] is True
    assert d["ctl_used"] == 50.0


def test_auto_plan_con_carga_real_no_marca(client, db, athlete_user):
    d = _plan(client, db, athlete_user, con_carga=True)
    assert d["ctl_estimated"] is False
    assert d["ctl_used"] == 72.0


def test_race_day_ui_muestra_aviso_estimado():
    src = _read("race_day.html")
    assert "d.ctl_estimated" in src and "rd_ctl_estimated_note" in src


def test_sw_build_265():
    m = re.search(r"BUILD_VERSION = '(\d+)'", _read("sw.js"))
    assert m and int(m.group(1)) >= 265
