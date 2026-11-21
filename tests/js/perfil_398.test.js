'use strict';
// PERFIL (BUILD 398): Perfil en capas ejecutivas (respuesta, porque, tecnico plegado).
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const R = (f) => fs.readFileSync(path.join(__dirname, '..', '..', f), 'utf8');
const HTML = R('athlete_profile.html');
const I18N = R('i18n.js');
const SW = R('sw.js');

test('capa 1: respuesta en palabras antes de la cabecera (porque)', () => {
  const a = HTML.indexOf('id="prof-answer"');
  assert.ok(a > 0);
  assert.ok(a < HTML.indexOf('id="acct-glance"'));
  assert.ok(HTML.indexOf('id="acct-glance"') < HTML.indexOf('id="prof-index"'));
  assert.match(HTML, /id="prof-why"/);
});

test('la respuesta sale de datos reales y se repinta con cada fuente', () => {
  const fn = HTML.slice(HTML.indexOf('function renderProfileAnswer'), HTML.indexOf('function renderAccountGlance'));
  for (const src of ['profileCompleteness(_profile)', 'accountGlanceConns()', '_pendingInvites']) {
    assert.ok(fn.includes(src), src);
  }
  assert.match(HTML, /function renderAccountGlance\(\) \{\s*renderProfileAnswer\(\);/);
});

test('capa 3: contrasena, 2FA, notificaciones y sesiones plegadas por defecto, ids intactos', () => {
  const m = HTML.match(/<details[^>]*id="prof-l3-account"[^>]*>/);
  assert.ok(m);
  assert.doesNotMatch(m[0], /\bopen\b/);
  const a = HTML.indexOf('id="prof-l3-account"');
  const body = HTML.slice(a, HTML.indexOf('</details>', a));
  for (const id of ['pw-old', 'pw-new', 'btn-2fa-on', 'btn-2fa-off', 'notif-push', 'sessions-list']) {
    assert.ok(body.includes('id="' + id + '"'), id);
  }
  // la zona de peligro y las invitaciones quedan a la vista
  assert.ok(!body.includes('id="zona-peligro"'));
  assert.ok(!body.includes('id="pending-coach-invites-wrap"'));
});

test('i18n ES/PT/EN con los mismos marcadores', () => {
  const keys = ['prof_why', 'prof_ans_missing', 'prof_ans_complete', 'prof_ans_conn', 'prof_ans_conn_none', 'prof_ans_invites', 'prof_l3_account'];
  for (const k of keys) {
    const m = I18N.match(new RegExp('^[ ]+' + k + ': "([^"]*)"', 'gm'));
    assert.strictEqual(m.length, 3, k);
    const sets = m.map((x) => (x.match(/\{\w+\}/g) || []).sort().join());
    assert.strictEqual(new Set(sets).size, 1, k);
  }
  assert.match(I18N, /prof_l3_account: "Contraseña, verificación en dos pasos \(2FA\)/);
});

test('sellos de version', () => {
  assert.match(SW, /var BUILD_VERSION = '404'/);
  assert.ok(SW.includes("'/i18n.js?v=404'"));
  assert.ok(HTML.includes('i18n.js?v=404'));
});
