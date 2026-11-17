// BLOODLABS-TABLA (BUILD 393): comparacion de Blood Labs como tabla clinica.
// Ejecutar: node --test tests/js/bloodlabs_tabla_392.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..', '..');
const HTML = fs.readFileSync(path.join(ROOT, 'blood_labs.html'), 'utf8');
const I18N = fs.readFileSync(path.join(ROOT, 'i18n.js'), 'utf8');
const SW = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');

// Extrae una funcion top-level del <script> por balanceo de llaves.
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

function render(exams, details) {
  const el = { innerHTML: '' };
  const ctx = {
    EXAMS: exams,
    CAT_ORDER: ['hematologico', 'vitaminas'],
    EXAM_DETAIL: details,
    document: { getElementById: (id) => (id === 'bl-cmp-table' ? el : null) },
    _t: (k, d) => d,
    esc: (s) => String(s),
    _lxBe: (s) => s,
    fmtDate: (s) => s,
    catMeta: () => ({ hematologico: { icon: 'H', label: 'Hema' }, vitaminas: { icon: 'V', label: 'Vit' } }),
    zoneWords: (m) => 'zona:' + m.zone,
    loadExamDetail: (id) => Promise.resolve(details[id]),
    Promise,
  };
  vm.createContext(ctx);
  vm.runInContext(extractFn('renderCompareTable'), ctx);
  return ctx.renderCompareTable().then(() => el.innerHTML);
}

const mk = (v, st, z, cat, name) => ({ name, unit: 'u', cat, value: v, status: st, zone: z });
const DET = {
  e1: { id: 'e1', date_iso: '2026-05-01', lab_name: 'LabA', markers: { hb: mk(14, 'ok', 'optimal', 'hematologico', 'Hemoglobina'), vitd: mk(12, 'critical', 'low', 'vitaminas', 'Vit D') } },
  e2: { id: 'e2', date_iso: '2026-01-01', lab_name: 'LabA', markers: { hb: mk(13, 'warning', 'suboptimal', 'hematologico', 'Hemoglobina') } },
  e3: { id: 'e3', date_iso: '2026-09-01', lab_name: '', markers: { hb: mk(15, 'ok', 'optimal', 'hematologico', 'Hemoglobina'), vitd: mk(35, 'ok', 'optimal', 'vitaminas', 'Vit D') } },
};
const EX = [{ id: 'e3' }, { id: 'e1' }, { id: 'e2' }]; // el servidor los manda mas recientes primero

test('filas = marcadores y columnas = fechas de TODOS los examenes', async () => {
  const html = await render(EX, DET);
  assert.equal((html.match(/<tr data-marker=/g) || []).length, 2);
  assert.ok(html.includes('data-marker="hb"') && html.includes('data-marker="vitd"'));
  const head = html.slice(html.indexOf('<thead>'), html.indexOf('</thead>'));
  for (const d of ['2026-01-01', '2026-05-01', '2026-09-01']) assert.ok(head.includes(d), d);
  // orden cronologico de izquierda a derecha
  assert.ok(head.indexOf('2026-01-01') < head.indexOf('2026-05-01'));
  assert.ok(head.indexOf('2026-05-01') < head.indexOf('2026-09-01'));
});

test('una sola vista: sin paginar ni plegar por examen', async () => {
  const html = await render(EX, DET);
  assert.equal((html.match(/<table/g) || []).length, 1);
  assert.ok(!/<details|toggleCat|onclick/.test(html));
  // cada fila tiene una celda por examen (celda vacia = guion)
  const hbRow = html.slice(html.indexOf('data-marker="vitd"'));
  assert.equal((hbRow.match(/data-exam=/g) || []).length, 3);
  assert.ok(hbRow.includes('>—</td>'), 'Vit D sin valor en e2 queda como guion');
});

test('linea base: cada valor lleva su referencia del servidor y su color', async () => {
  const html = await render(EX, DET);
  assert.equal((html.match(/bl-cmp-ref/g) || []).length, 5); // 5 valores medidos
  assert.ok(html.includes('zona:optimal') && html.includes('zona:low') && html.includes('zona:suboptimal'));
  assert.ok(html.includes('bl-cmp-ok') && html.includes('bl-cmp-warn') && html.includes('bl-cmp-bad'));
});

test('vive en el Resumen, fuera de Ver detalle, y se dibuja al cambiar de examen', () => {
  const r0 = HTML.indexOf('id="tab-resumen"');
  const r1 = HTML.indexOf('id="tab-trends"');
  const RES = HTML.slice(r0, r1);
  const d0 = RES.indexOf('<details class="bl-all');
  assert.ok(RES.indexOf('id="bl-cmp-table"') > 0 && RES.indexOf('id="bl-cmp-table"') < d0);
  assert.ok(RES.indexOf('id="bl-plain"') < RES.indexOf('id="bl-cmp-table"'));
  assert.match(HTML, /renderVariations\(cur, comp\);\s*renderCompareTable\(\);/);
  assert.ok(HTML.includes('id="sel-exam"'));
});

test('Tendencias y primera pantalla del Resumen siguen presentes', () => {
  assert.match(HTML, /data-tab="trends"/);
  assert.match(HTML, /id="tab-trends"/);
  assert.ok(HTML.includes('id="trend-content"'));
  assert.match(HTML, /function renderTrendsTab\(/);
  assert.match(HTML, /data-tab="garmin"/);
  for (const id of ['bl-plain', 'alerts-container', 'bl-trs-read', 'bl-ver-todo']) {
    assert.ok(HTML.includes('id="' + id + '"'), id);
  }
});

test('textos por i18n ES/PT/EN y estilo por variables', () => {
  for (const k of ['bl_tbl_title', 'bl_tbl_marker', 'bl_tbl_note', 'bl_tbl_loading', 'bl_tbl_error', 'bl_tbl_empty', 'bl_tbl_ref']) {
    assert.equal((I18N.match(new RegExp(k + ': "', 'g')) || []).length, 3, k);
  }
  assert.match(HTML, /data-i18n="bl_tbl_title"/);
  const css = HTML.slice(HTML.indexOf('.bl-cmp-note {'), HTML.indexOf('.bl-l1-chips {'));
  assert.ok(css.length > 200);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(css) && !/rgba?\(/.test(css), 'sin colores fijos');
  assert.ok(css.includes('var(--green)') && css.includes('var(--red)'));
});

test('BUILD 393 y sello i18n.js?v=393', () => {
  assert.match(SW, /var BUILD_VERSION = '393'/);
  assert.ok(SW.includes("'/i18n.js?v=393'"));
  assert.ok(HTML.includes('i18n.js?v=393'));
});
