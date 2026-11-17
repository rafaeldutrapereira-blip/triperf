'use strict';
// RACE-DAY (BUILD 397): Race Day en capas ejecutivas (respuesta, porque, tecnico plegado).
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const R = (f) => fs.readFileSync(path.join(__dirname, '..', '..', f), 'utf8');
const HTML = R('race_day.html');
const I18N = R('i18n.js');
const SW = R('sw.js');

test('Mi carrera: respuesta en palabras antes del plan y del detalle plegado', () => {
  const a = HTML.indexOf('id="rd-answer"');
  assert.ok(a > 0);
  assert.ok(a < HTML.indexOf('id="rd-l1"'));
  assert.ok(HTML.indexOf('id="rd-l1"') < HTML.indexOf('id="rd-l2"'));
  assert.ok(HTML.indexOf('id="rd-l2"') < HTML.indexOf('id="rd-advanced"'));
  assert.doesNotMatch(HTML, /<details[^>]*id="rd-plan-detail"[^>]* open/);
  assert.doesNotMatch(HTML, /<details[^>]*id="rd-advanced"[^>]* open/);
});

test('la respuesta sale de datos reales via renderPlanSummary', () => {
  assert.match(HTML, /function renderAnswer\(totalFmt, bikePower, runPace\)/);
  assert.match(HTML, /function renderPlanSummary\([^)]*\) \{\s*renderAnswer\(/);
  assert.match(HTML, /rd_ans_noplan/);
});

test('Mis carreras: respuesta, porque (historial) y formulario tecnico plegado', () => {
  const t = HTML.indexOf('id="tab-races"');
  const ans = HTML.indexOf('id="rd-hist-answer"', t);
  const hist = HTML.indexOf('id="history-list"', t);
  const det = HTML.indexOf('id="rd-result-detail"', t);
  assert.ok(t < ans && ans < hist && hist < det);
  assert.doesNotMatch(HTML, /<details[^>]*id="rd-result-detail"[^>]* open/);
  const body = HTML.slice(det, HTML.indexOf('id="res-analysis-box"'));
  for (const id of ['res-swim', 'res-bike', 'res-run', 'res-dnf', 'res-notes']) {
    assert.ok(body.includes('id="' + id + '"'), id);
  }
  assert.match(HTML, /function renderHistoryAnswer\(races\)/);
  assert.match(HTML, /r\.pacing_score && /);
});

test('i18n ES/PT/EN con los mismos marcadores y sigla con nombre', () => {
  const keys = ['rd_ans_days', 'rd_ans_race', 'rd_ans_noplan', 'rd_ans_plan', 'rd_ans_bike', 'rd_ans_run',
    'rd_hist_why', 'rd_hist_none', 'rd_hist_last', 'rd_hist_v_hi', 'rd_hist_v_mid', 'rd_hist_v_lo', 'rd_l3_record'];
  for (const k of keys) {
    const m = I18N.match(new RegExp('(?<![\w])' + k + ": '([^']*)'", 'g'));
    assert.strictEqual(m.length, 3, k);
    const sets = m.map((x) => (x.match(/\{\w+\}/g) || []).sort().join());
    assert.strictEqual(new Set(sets).size, 1, k);
  }
  for (const m of I18N.match(/rd_hist_last: '[^']*'/g)) assert.match(m, /\(Pacing Score\)/);
});

test('sin color oscuro fijo en lo nuevo, BUILD 397 y sello i18n', () => {
  const css = HTML.slice(HTML.indexOf('RACE-DAY (BUILD 397)'));
  const blk = css.slice(0, css.indexOf('</style>'));
  assert.doesNotMatch(blk, /#[0-9a-fA-F]{3,8}\b|rgb/);
  assert.match(SW, /var BUILD_VERSION = '397'/);
  assert.ok(HTML.includes('i18n.js?v=397'));
  assert.ok(SW.includes("'/i18n.js?v=397'"));
});
