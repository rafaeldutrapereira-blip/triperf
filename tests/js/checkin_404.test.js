'use strict';
// UNIFICAR-CHECKIN (BUILD 404): el dashboard muestra el estado del check-in unico de Estado.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const R = (f) => fs.readFileSync(path.join(__dirname, '..', '..', f), 'utf8');
const HTML = R('dashboard.html');
const I18N = R('i18n.js');
const SW = R('sw.js');

test('no existe el bloque de captura #lx-checkin ni inputs/escala en la tarjeta', () => {
  assert.ok(!HTML.includes('id="lx-checkin"'));
  assert.ok(!/saveCheckin|_ckRender|lx-checkin-rows|lx-checkin-save/.test(HTML));
  assert.ok(!HTML.includes('/athlete/health/checkin'));
  const a = HTML.indexOf('id="lx-checkin-status"');
  const card = HTML.slice(a, HTML.indexOf('id="kc-mental"', a));
  assert.ok(!/<input|<select|<textarea|<button/.test(card));
});

test('la tarjeta de estado esta dentro de "Como te sientes", antes de Fatiga Mental, y enlaza a estado.html', () => {
  const head = HTML.indexOf('data-i18n="dash_x_feel"');
  const st = HTML.indexOf('id="lx-checkin-status"');
  const men = HTML.indexOf('id="kc-mental"');
  assert.ok(head > 0 && head < st && st < men);
  assert.match(HTML, /id="lx-ck-link"[^>]*href="estado\.html#est-reg"/);
  assert.match(HTML, /id="kc-mental"[\s\S]{0,300}estado\.html#est-reg-men/);
  const a = HTML.indexOf('id="lx-checkin-status"');
  const card = HTML.slice(a, men);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(card), 'sin colores fijos');
});

test('lee los GET existentes de Estado y no escribe', () => {
  const a = HTML.indexOf('function loadCheckin');
  const fn = HTML.slice(a, HTML.indexOf('Panel de Salud 360', a));
  assert.ok(fn.includes("'/recovery/wellness/' + day"));
  assert.ok(fn.includes("'/mental/dashboard?date_iso=' + day"));
  assert.ok(!/method:\s*'POST'/.test(fn));
});

function harness(well, men) {
  const els = {};
  const mk = (id) => (els[id] = { id, textContent: '', style: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } });
  ['lx-checkin-status', 'lx-ck-state', 'lx-ck-summary', 'lx-ck-link'].forEach(mk);
  const a = HTML.indexOf('function paintCheckinStatus');
  const code = HTML.slice(a, HTML.indexOf('function loadCheckin', a));
  const T = { est_checkin_done: 'HECHO', est_checkin_pending: 'PENDIENTE', est_checkin_edit: 'EDITAR', dash_ck_cta: 'COMPLETAR', rcw_energy_short: 'Energia', rcw_mood_short: 'Animo', rcw_legs_short: 'Piernas' };
  const ctx = { document: { getElementById: (i) => els[i] || null }, _t: (k, d) => T[k] || d };
  vm.createContext(ctx);
  vm.runInContext(code + '; paintCheckinStatus(W, M);', Object.assign(ctx, { W: well, M: men }));
  return els;
}

test('pendiente: sin registro hoy -> pendiente, sin resumen, CTA completar', () => {
  const e = harness({ logged: false }, { today: { has_checkin: false } });
  assert.strictEqual(e['lx-ck-state'].textContent, 'PENDIENTE');
  assert.strictEqual(e['lx-checkin-status'].attrs['data-state'], 'pending');
  assert.strictEqual(e['lx-ck-summary'].style.display, 'none');
  assert.strictEqual(e['lx-ck-link'].textContent, 'COMPLETAR');
});

test('fallo de red (null) cuenta como pendiente sin romper', () => {
  const e = harness(null, null);
  assert.strictEqual(e['lx-checkin-status'].attrs['data-state'], 'pending');
});

test('hecho: con wellness registrado -> hecho + resumen energia/animo/dolor + Editar', () => {
  const e = harness({ logged: true, energy: 4, mood: 3, soreness: 2 }, { today: { has_checkin: false } });
  assert.strictEqual(e['lx-ck-state'].textContent, 'HECHO');
  assert.strictEqual(e['lx-checkin-status'].attrs['data-state'], 'done');
  assert.strictEqual(e['lx-ck-summary'].textContent, 'Energia 4/5 · Animo 3/5 · Piernas 2/5');
  assert.strictEqual(e['lx-ck-link'].textContent, 'EDITAR');
});

test('hecho solo con check-in mental -> hecho sin resumen', () => {
  const e = harness({ logged: false }, { today: { has_checkin: true } });
  assert.strictEqual(e['lx-checkin-status'].attrs['data-state'], 'done');
  assert.strictEqual(e['lx-ck-summary'].style.display, 'none');
});

test('i18n ES/PT/EN, ckin_* retiradas, BUILD 404 en sw.js', () => {
  assert.strictEqual((I18N.match(/^\s+dash_ck_cta:/gm) || []).length, 3);
  assert.ok(!/(?<![A-Za-z_])ckin_[a-z_]+:/.test(I18N));
  assert.match(SW, /var BUILD_VERSION = '404'/);
  assert.ok(SW.includes("'/i18n.js?v=404'") && HTML.includes('i18n.js?v=404'));
});
