"""
B4 - Plan (screen-week) = sesion + tira de 7 dias con el plan real.

Plan pinta una sesion de Garmin (include_garmin=1) y una Adicional (W21), sin anillos;
el bloque wpMob (Progreso Semanal) vive en Progreso, no en Plan; registrar manual guarda.
Se ejecuta el JS real de athlete-app.html con node, con DOM/apiFetch simulados.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE = shutil.which("node")
HTML = open(os.path.join(ROOT, "athlete-app.html"), encoding="utf-8").read()
SW = open(os.path.join(ROOT, "sw.js"), encoding="utf-8").read()


def _section(start, end):
    a = HTML.index(start)
    return HTML[a:HTML.index(end, a)]


WEEK = _section('<div class="screen" id="screen-week">', "<!-- SCREEN 5")
INSIGHTS = _section('<div id="pgr-insights-content">', '<div id="pgr-records-content"')


def test_plan_ya_no_tiene_anillos_ni_wpmob():
    assert "wp-mob-card" not in WEEK and "wpMobSport" not in WEEK
    assert "wk-rings-grid" not in HTML and "_wkSumSet" not in HTML
    assert 'id="wk-sessions-line"' in WEEK and 'id="wk-strip"' in WEEK
    assert 'id="week-grid"' in WEEK


def test_wpmob_vive_en_progreso():
    assert 'id="wp-mob-card"' in INSIGHTS and "wpMobSport('bike')" in INSIGHTS
    i = HTML.index("function loadProgressInsights()")
    assert "loadWeeklyProgressMobile();" in HTML[i:i + 200]
    j = HTML.index("function loadWeek()")
    assert "loadWeeklyProgressMobile" not in HTML[j:HTML.index("function renderWeekGrid", j)]


def test_loadweek_usa_plan_real_y_realizado():
    j = HTML.index("function loadWeek()")
    body = HTML[j:HTML.index("function renderWeekGrid", j)]
    assert "&include_garmin=1" in body
    assert "/athlete/plan/realizado?start=" in body
    assert "/athlete/dashboard" not in body


def test_build_y_claves_i18n():
    assert re.search(r"BUILD_VERSION = '293'", SW)
    i18n = open(os.path.join(ROOT, "i18n.js"), encoding="utf-8").read()
    for k in ("b4_sesiones_de", "b4_adicional", "b4_adicionales_n", "b4_sin_sesiones"):
        assert i18n.count(k + ":") == 3


HARNESS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const cfg = JSON.parse(process.argv[2]);
function cut(a, b) {
  const i = html.indexOf(a), j = html.indexOf(b, i);
  if (i < 0 || j < 0) throw new Error('bloque no encontrado: ' + a);
  return html.slice(i, j);
}
const src = cut('function _matchPlannedToReal', 'function renderTodayWorkout')
  + cut('var _weekAssignsFlat', '/* Detalle de una actividad de la semana al tocarla')
  + cut('var RPE_LABELS_LM', '/* ── Progreso Semanal (ventana');
const els = {};
function el(id) {
  return els[id] || (els[id] = { id, value: '1', innerHTML: '', textContent: '', style: {} });
}
const calls = [], toasts = [], opened = [];
global.document = { getElementById: el };
global.todayIso = () => '2026-11-04';
global._isoLocal = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
global._t = (k, fb) => fb;
global._tssLbl = () => 'TSS';
global._escCm = s => String(s);
global.SPORT_COL = {}; global.SPORT_EMOJI = {};
global._todayExtraRealFlat = ['hoy'];
global.showExtraActivityDetail = i => opened.push(global._todayExtraRealFlat[i]);
global.toast = (m, c) => toasts.push([m, c]);
global.loadToday = () => calls.push({ reload: 'today' });
global.loadWeek = () => calls.push({ reload: 'week' });
global.apiFetch = (url, opts) => {
  calls.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};
const api = new Function(src + `
  return { renderWeekGrid, showWeekExtraDetail, openLogManualModal, submitLogManual,
           get extra() { return _weekExtraFlat; } };`)();
(async () => {
  api.renderWeekGrid(cfg.assigns, '2026-11-02', cfg.real);
  api.showWeekExtraDetail(0);
  const out = { grid: els['week-grid'].innerHTML, strip: els['wk-strip'].innerHTML,
                line: els['wk-sessions-line'].innerHTML, opened,
                todayFlatKept: global._todayExtraRealFlat };
  api.openLogManualModal('a-77');
  els['lm-rpe'].value = '6'; els['lm-dur'].value = '45'; els['lm-dist'].value = '8.5';
  els['lm-notas'] = { value: ' sin reloj ' };
  api.submitLogManual();
  await new Promise(r => setTimeout(r, 20));
  out.calls = calls; out.toasts = toasts;
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def _run(assigns, real):
    p = subprocess.run(
        [NODE, "-e", HARNESS, os.path.join(ROOT, "athlete-app.html"),
         json.dumps(dict(assigns=assigns, real=real))],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def _plan(date, sport, name, dur, **kw):
    d = dict(date_iso=date, notas=None, logs=[],
             template=dict(sport=sport, nombre=name, dur_min=dur, dist_km=None, tss=40))
    d.update(kw)
    return d


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_plan_pinta_sesion_garmin_y_actividad_adicional():
    assigns = [
        _plan("2026-11-04", "bike", "Rodillo Garmin", 60, source="garmin", done=True),
        _plan("2026-11-05", "run", "Rodaje", 45),
    ]
    real = [
        dict(activity_id="g1", name="Rodillo", sport="bike", date_iso="2026-11-04", dur_min=58),
        dict(activity_id="n1", name="Natacion libre", sport="swim", date_iso="2026-11-04",
             dur_min=40, adicional=True),
    ]
    out = _run(assigns, real)
    g = out["grid"]
    assert "Rodillo Garmin" in g and "Rodaje" in g
    assert "Natacion libre" in g and "wk-wo-tag" in g and "Adicional" in g
    assert out["line"].count("1 de 2 sesiones") == 1 and "Adicionales: 1" in out["line"]
    assert out["strip"].count("wk-chip-dot") >= 3 and "wk-chip-today" in out["strip"]
    # la Adicional abre su detalle sin pisar el arreglo de Hoy
    assert [o["activity_id"] for o in out["opened"]] == ["n1"]
    assert out["todayFlatKept"] == ["hoy"]


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_semana_vacia_dice_sin_sesiones():
    out = _run([], [])
    assert "Sin sesiones planificadas" in out["line"]
    assert out["grid"].count("Descanso") == 7


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_registrar_manual_sigue_guardando():
    out = _run([_plan("2026-11-04", "run", "Rodaje", 45)], [])
    post = [c for c in out["calls"] if c.get("url") == "/athlete/log"][0]
    assert post["body"] == dict(assignment_id="a-77", rpe=6, dur_real=45, dist_real=8.5,
                                notas="sin reloj", completado=True)
    assert out["toasts"][0][1] == "ok"
    assert {"reload": "week"} in out["calls"]
