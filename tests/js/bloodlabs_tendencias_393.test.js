// TENDENCIAS-BLOODLABS (BUILD 393): la pestana Tendencias dibuja los examenes cargados.
// Ejecutar: node --test tests/js/bloodlabs_tendencias_393.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..', '..');
const HTML = fs.readFileSync(path.join(ROOT, 'blood_labs.html'), 'utf8');
const SW = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');

function extractFn(name) {
  const i = HTML.indexOf('function ' + name + '(');
  assert.notEqual(i, -1, 'no se encontro ' + name);
  let depth = 0, started = false, j = HTML.indexOf('{', i);
  for (; j < HTML.length; j++) {
    if (HTML[j] === '{') { depth++; started = true; }
    else if (HTML[j] === '}') { depth--; if (started && depth === 0) break; }
  }
  return HTML.slice(i, j + 1);
}

function run(timeline) {
  const els = {
    'trends-stabs-bar': { innerHTML: '' },
    'trend-content': { innerHTML: '' },
    'trend-single': { innerHTML: '' },
    'trend-hemoglobin': {}, 'trend-ferritin': {}, 'trend-vitamin_d': {},
  };
  const charts = [];
  const ctx = {
    TIMELINE: timeline,
    CH: {},
    Chart: function (canvas, cfg) { charts.push(cfg); this.destroy = () => {}; },
    document: { getElementById: (id) => els[id] || null },
    _t: (k, d) => d,
    esc: (s) => String(s),
    fmtDate: (s) => s,
    Object,
  };
  vm.createContext(ctx);
  const m = HTML.match(/var TIMELINE_MARKERS = \{[\s\S]*?\n {6}\};/);
  assert.ok(m, 'TIMELINE_MARKERS');
  vm.runInContext(m[0] + '\n' + extractFn('renderTrendsTab'), ctx);
  ctx.renderTrendsTab();
  return { els, charts };
}

const row = (d, hb, fe, vd) => ({ exam_date: d, hemoglobin: hb, ferritin: fe, vitamin_d: vd });
const FIVE = {
  timeline: [
    row('2024-02-08', 15, 90, null), row('2025-03-27', 15, 85, 45),
    row('2026-01-17', 15, 80, 48), row('2026-01-22', 14.8, 82, null), row('2026-09-29', 15, null, 50),
  ],
  date_range: { from: '2024-02-08', to: '2026-09-29' }, exam_count: 5,
};

test('con 5 examenes la pestana dibuja tendencias y no el mensaje de vacio', () => {
  const { els, charts } = run(FIVE);
  const html = els['trend-content'].innerHTML;
  assert.ok(!html.includes('bl-empty'), 'no debe mostrar el vacio');
  assert.ok(html.includes('id="trend-hemoglobin"') && html.includes('id="trend-ferritin"') && html.includes('id="trend-vitamin_d"'));
  assert.equal(charts.length, 3);
  const hb = charts.find((c) => c.data.datasets[0].label === 'Hemoglobina');
  assert.equal(hb.data.labels.length, 5);
  assert.deepEqual(hb.data.datasets[0].data, [15, 15, 15, 14.8, 15]);
  assert.ok(els['trends-stabs-bar'].innerHTML.includes('5 '));
});

test('sin timeline (error o cuenta vacia) sigue el mensaje de vacio', () => {
  assert.ok(run(null).els['trend-content'].innerHTML.includes('bl-empty'));
});

test('la tabla de comparacion de la 392 sigue presente y la carga usa all=1', () => {
  assert.ok(HTML.includes('id="bl-cmp-table"'));
  assert.ok(HTML.includes('function renderCompareTable('));
  assert.ok(HTML.includes("/labs/timeline?all=1"));
});

test('BUILD 394 y sello i18n.js?v=394', () => {
  assert.match(SW, /var BUILD_VERSION = '394'/);
  assert.ok(SW.includes("'/i18n.js?v=394'"));
  assert.ok(HTML.includes('i18n.js?v=394'));
});
