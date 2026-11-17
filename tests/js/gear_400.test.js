'use strict';
// GEAR (BUILD 400): Gear en capas ejecutivas (respuesta, porque, tecnico plegado).
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const R = (f) => fs.readFileSync(path.join(__dirname, '..', '..', f), 'utf8');
const HTML = R('gear.html');
const I18N = R('i18n.js');
const SW = R('sw.js');

test('capa 1 y 2: la respuesta y el porque quedan fuera del pliegue, antes del detalle', () => {
  const attn = HTML.indexOf('id="alert-banner"');
  const fold = HTML.indexOf('id="gear-l3-detail"');
  assert.ok(attn > 0 && fold > attn);
  assert.ok(HTML.indexOf('id="alert-text"') < fold);
  assert.ok(HTML.indexOf('id="gear-attn-list"') < fold);
});

test('capa 3: zapatillas, bicicletas y acciones plegadas por defecto, ids intactos', () => {
  const m = HTML.match(/<details[^>]*id="gear-l3-detail"[^>]*>/);
  assert.ok(m);
  assert.doesNotMatch(m[0], /\bopen\b/);
  const a = HTML.indexOf('id="gear-l3-detail"');
  const body = HTML.slice(a, HTML.indexOf('</details>', a));
  for (const id of ['pane-shoes', 'pane-bikes', 'shoes-grid', 'bikes-grid']) {
    assert.ok(body.includes('id="' + id + '"'), id);
  }
  assert.ok(body.includes('openModal(\'modal-shoe\')'));
});

test('el detalle abre solo si no hay nada que avisar o falla el resumen', () => {
  assert.match(HTML, /function gearOpenDetail\(\)/);
  const fn = HTML.slice(HTML.indexOf('function checkSummaryAlerts'), HTML.indexOf('function gearOpenDetail'));
  assert.strictEqual((fn.match(/gearOpenDetail\(\)/g) || []).length, 2);
});

test('i18n ES/PT/EN y sigla con nombre primero', () => {
  const m = I18N.match(/^[ ]+gear_l3_detail: ['"][^\n]*$/gm);
  assert.strictEqual(m.length, 3);
});

test('sellos de version', () => {
  assert.match(SW, /var BUILD_VERSION = '400'/);
  assert.ok(SW.includes("'/i18n.js?v=400'"));
  assert.ok(HTML.includes('i18n.js?v=400'));
});
