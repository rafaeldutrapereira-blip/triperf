"""MIPLAN-RESUMEN (BUILD 343): Mi Plan abre con el resumen, no con la lista.

Se ejecuta el JS real de training_plan.html (renderOverview y ayudantes) con node,
con los datos del plan simulados.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
HTML = (ROOT / "training_plan.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_sin_bloque_de_cumplimiento_ni_metas_fijas():
    assert 'id="s-compl"' not in HTML and 'id="compl-row"' not in HTML
    assert "renderWeeklyCompliance" not in HTML and "compl-arc" not in HTML
    assert "fetchPlanTSSRange" not in HTML and "COMPL_GRAD" not in HTML
    # sin respaldo de metas fijas (10/200/40/3) ni tarjetas "% de objetivo"
    assert "TARGETS" not in HTML and "renderSummary" not in HTML
    assert 'id="sum-grid"' not in HTML and 'id="list-tabs"' not in HTML


def test_el_resumen_manda_y_el_more_conserva_lo_avanzado():
    r = HTML[HTML.index("function render() {"):HTML.index("// VIEW SWITCHER")]
    assert "renderOverview();" in r and "renderList" not in r
    more = HTML[HTML.index('<details class="tp-more"'):HTML.index("</details>", HTML.index('<details class="tp-more"'))]
    assert 'data-view="month"' in more and 'id="sport-filters"' in more
    assert 'id="cal-area"' in more and 'id="s-compl"' not in more


def test_franja_s3_sin_fila_de_tiempo_duplicada():
    assert "tp_ws_time" not in HTML  # el tiempo planificado vive en la linea ejecutiva


def test_build_343_y_claves_trilingues():
    assert re.search(r"BUILD_VERSION = '(34[3-9]|3[5-9]\d|[4-9]\d\d)'", SW)
    for k in ("tp_ov_week_of", "tp_ov_week_from", "tp_ov_sess_1", "tp_ov_sess_n",
              "tp_ov_planned", "tp_ov_done", "tp_ov_none", "tp_ov_none_range", "tp_ov_none_short"):
        assert I18N.count("    " + k + ":") == 3, k
    assert "tp_compl_week" not in I18N


HARNESS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const cfg = JSON.parse(process.argv[2]);
function cut(a, b) {
  const i = html.indexOf(a), j = html.indexOf(b, i);
  if (i < 0 || j < 0) throw new Error('bloque no encontrado: ' + a);
  return html.slice(i, j);
}
const src = cut('function iso(d)', 'function isoWeekNum')
  + cut('function jsArg', 'function fmtDateLabel')
  + cut('function _wsEsc', 'function loadWeekSummary')
  + cut('var _openWk', '// PLANES REALES SINCRONIZADOS');
const els = { 'sess-cards': { innerHTML: '' } };
global.document = { getElementById: id => els[id] };
global.window = {};
global._t = (k, fb) => fb;
const run = new Function('cfg', 'document', 'window', '_t', `
  function daysShort() { return ['LUN','MAR','MIÉ','JUE','VIE','SÁB','DOM']; }
  function monthsS() { return ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC']; }
  var SPORT = { bike: {icon:'B', label:'Ciclismo'}, run: {icon:'R', label:'Carrera'} };
  var S = { view: cfg.view || 'week', filters: [] };
  var _wkSumCache = cfg.week || {};
  function todayIso() { return cfg.today; }
  function weekMon(d) { var m = new Date(d); m.setHours(0,0,0,0); m.setDate(m.getDate() - (m.getDay() || 7) + 1); return m; }
  function currentRange() { var m = weekMon(new Date(cfg.today + 'T12:00:00')); return { start: iso(m), end: iso(addDays(m, 6)) }; }
  function applyFilter(a) { return a; }
  function sessionsInRange(a, b) { return cfg.sessions.filter(s => s.date_iso >= a && s.date_iso <= b); }
  function pairPlanAndReal(arr) {
    var hp = {}, pa = {};
    arr.forEach(function (p) {
      if (p.source !== 'local' || !p.pair_act) return;
      hp[p.id] = true; pa[p.pair_act] = p;
    });
    return { hiddenPlanned: hp, planByActId: pa };
  }
  function findPlanned(id) { return cfg.sessions.find(s => s.id === id && s.source === 'local'); }
  ` + src + `
  renderOverview();
`);
run(cfg, global.document, global.window, global._t);
console.log(JSON.stringify({ html: els['sess-cards'].innerHTML }));
"""


def _run(sessions, today="2026-11-04", view="week", week=None):
    assert NODE, "node requerido"
    p = subprocess.run(
        [NODE, "-e", HARNESS, str(ROOT / "training_plan.html"),
         json.dumps(dict(sessions=sessions, today=today, view=view, week=week or {}))],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])["html"]


def _plan(i, date, sport, name, dur, **kw):
    d = dict(id=i, date_iso=date, sport=sport, name=name, dur_min=dur, source="local", status="planned")
    d.update(kw)
    return d


def _line(html):
    return re.search(r'id="tp-ov-line">(.*?)</div>', html).group(1)


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_linea_ejecutiva_con_datos_reales():
    sessions = [
        _plan("a", "2026-11-02", "bike", "Rodaje largo", 90, status="done", dur_real=88),
        _plan("b", "2026-11-03", "run", "Series", 60, pair_act=77),
        dict(activity_id=77, date_iso="2026-11-03", sport="run", name="Run", dur_min=58,
             dist_km=10, source="garmin", status="done"),
        _plan("c", "2026-11-06", "run", "Fondo", 30),
    ]
    h = _run(sessions)
    assert "Semana del 2 nov al 8 nov" in h
    # 3 planificadas (90+60+30 = 3h) y 2 hechas (una marcada, una emparejada con Garmin)
    assert _line(h) == "3 sesiones · 3h planificadas · 2 hechas ✓"
    assert h.count('id="tp-ov-line"') == 1  # un solo resumen visible en la semana actual
    assert "tp-mini done" in h and "✓" in h
    assert "TSS" not in h  # sin cifras tecnicas por sesion en el resumen
    assert 'tp-day today' in h and 'data-date-iso="2026-11-04"' in h


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_sin_plan_dice_la_verdad_sin_cifras():
    h = _run([])
    assert _line(h) == "Sin plan esta semana"
    assert not re.search(r"\d", _line(h))
    assert "planificadas" not in h and "hechas" not in h


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_semanas_siguientes_colapsadas_por_defecto():
    sessions = [_plan("n1", "2026-11-10", "bike", "Z2", 70), _plan("n2", "2026-11-12", "run", "Rodaje", 60)]
    h = _run(sessions)
    wk = re.findall(r"<details class=\"tp-wk\"([^>]*)>", h)
    assert len(wk) == 3
    assert all(" open" not in a for a in wk)
    assert "Semana del 9 nov</b> · 2 sesiones · 2h10 planificadas" in h
    assert "Semana del 16 nov</b> · Sin plan" in h
    assert "hechas" not in h.split('class="tp-wk"')[1]  # las futuras no llevan conteo de hechas
