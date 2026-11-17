// BLOODLABS-SIMPLE (BUILD 391): vista ejecutiva de Blood Labs con detalle plegado.
// Ejecutar: node --test tests/js/bloodlabs_simple_391.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const HTML = fs.readFileSync(path.join(ROOT, 'blood_labs.html'), 'utf8');
const I18N = fs.readFileSync(path.join(ROOT, 'i18n.js'), 'utf8');
const SW = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');

const idx = (needle, from = 0) => {
  const i = HTML.indexOf(needle, from);
  assert.notEqual(i, -1, 'no se encontro ' + needle);
  return i;
};

// Limites del panel Resumen y del unico <details> de ese panel.
const rStart = idx('id="tab-resumen"');
const rEnd = idx('id="tab-trends"');
const RESUMEN = HTML.slice(rStart, rEnd);
const dStart = RESUMEN.indexOf('<details class="bl-all');
const dEnd = RESUMEN.indexOf('</details>', dStart);
const FOLD = RESUMEN.slice(dStart, dEnd);
const FIRST = RESUMEN.slice(0, dStart); // primera pantalla del Resumen

test('el Resumen tiene un unico <details>, cerrado por defecto', () => {
  assert.equal((RESUMEN.match(/<details/g) || []).length, 1);
  assert.ok(dStart > 0 && dEnd > dStart);
  const tag = RESUMEN.slice(dStart, RESUMEN.indexOf('>', dStart));
  assert.ok(!/\sopen[\s>=]/.test(tag + '>'), 'no debe tener open');
  assert.match(tag, /id="bl-ver-todo"/);
});

test('primera pantalla: respuesta en llano + alertas + TRS (y variaciones)', () => {
  for (const id of ['bl-plain', 'alerts-container', 'bl-trs-read', 'bl-variations']) {
    assert.ok(FIRST.includes('id="' + id + '"'), id + ' debe estar fuera del pliegue');
  }
  assert.ok(FIRST.indexOf('id="bl-plain"') < FIRST.indexOf('id="alerts-container"'));
  assert.ok(FIRST.indexOf('id="alerts-container"') < FIRST.indexOf('id="bl-trs-read"'));
});

test('el detalle (impacto, sistemas, KPIs, radar, IA, tabla) esta plegado', () => {
  for (const id of [
    'clinical-summary', 'bl-systems', 'kpi-trs', 'kpi-markers', 'kpi-next',
    'ch-radar', 'btn-ai-analyze', 'ai-interpretation-box', 'bm-table-container',
  ]) {
    assert.ok(FOLD.includes('id="' + id + '"'), id + ' debe estar dentro de Ver detalle');
    assert.ok(!FIRST.includes('id="' + id + '"'), id + ' no debe estar en la primera pantalla');
  }
});

test('el control usa i18n (sin texto fijo propio) y colores por variables', () => {
  assert.match(FOLD, /<summary data-i18n="bl_see_detail">/);
  const m = /bl_see_detail: "([^"]+)"/g;
  const vals = [...I18N.matchAll(m)].map((x) => x[1]);
  assert.equal(vals.length, 3, 'ES/PT/EN');
  assert.deepEqual(vals, ['Ver detalle', 'Ver detalhe', 'See details']);
  const css = HTML.slice(idx('.bl-all > summary'), idx('.bl-all > summary') + 200);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(css), 'sin colores fijos en el control');
});

test('comparacion y evolucion siguen presentes y fuera del pliegue', () => {
  // selectores de examen y de comparacion, con su handler
  assert.match(HTML, /<select id="sel-exam" onchange="switchExam\(\)">/);
  assert.match(HTML, /<select id="sel-comp" onchange="switchExam\(\)">/);
  assert.ok(idx('id="sel-exam"') < rStart);
  // variaciones entre examenes visibles
  assert.ok(FIRST.includes('id="bl-variations"'));
  assert.match(HTML, /document\.getElementById\('bl-variations'\)/);
  // pestana Tendencias: boton, panel y render
  assert.match(HTML, /data-tab="trends"/);
  assert.match(HTML, /id="tab-trends"/);
  assert.ok(HTML.includes('id="trend-content"'));
  assert.ok(!FOLD.includes('id="tab-trends"'));
  // la pestana Garmin queda como estaba
  assert.match(HTML, /data-tab="garmin"/);
  assert.match(HTML, /id="tab-garmin"/);
});

test('el radar se redibuja al abrir el detalle (canvas medido solo abierto)', () => {
  assert.match(HTML, /getElementById\('bl-ver-todo'\)[\s\S]{0,200}addEventListener\('toggle'/);
});

test('BUILD 395 y sello i18n.js?v=400', () => {
  assert.match(SW, /var BUILD_VERSION = '400'/);
  assert.ok(SW.includes("'/i18n.js?v=400'"));
  assert.ok(HTML.includes('i18n.js?v=400'));
});
