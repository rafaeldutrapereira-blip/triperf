// S-D: "Ver detalles" por conexion -- modelo, fecha honesta y HTML
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function extract(src, name) {
  const i = src.indexOf('function ' + name + '(');
  assert.ok(i >= 0, name + ' no existe');
  const j = src.indexOf('{', src.indexOf(')', i));
  let depth = 0;
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}' && --depth === 0) return src.slice(i, k + 1);
  }
  throw new Error('sin cierre ' + name);
}
const web = fs.readFileSync(path.join(__dirname, '..', '..', 'athlete_profile.html'), 'utf8');
const start = web.indexOf('var CONN_RECV');
const end = web.indexOf('function connRenderGarmin');
const block = web.slice(start, end);
const api = new Function(
  'esc', '_t',
  block + '; return { model: connDetailModel, html: connDetailsHtml, fmt: connFmtDate };',
)((s) => String(s), (k, f) => f);
const { model, html, fmt } = api;

test('Garmin oficial: sin sync ahora ni ultima sync (hueco), con reconectar', () => {
  const m = model('garmin', { connected: true, via: 'official' });
  assert.strictEqual(m.showSync, false);
  assert.strictEqual(m.lastSync, null);
  assert.strictEqual(m.showReconnect, true);
  assert.deepStrictEqual(m.send, []);
});
test('Garmin legacy: sync ahora, envia workouts, ultima sync del backend', () => {
  const m = model('garmin', { connected: true, via: 'legacy', lastSync: '2026-11-06 12:30' });
  assert.strictEqual(m.showSync, true);
  assert.deepStrictEqual(m.send, ['workouts']);
  assert.strictEqual(m.lastSync, '2026-11-06 12:30');
});
test('Polar/Wahoo/Strava conectados: sync ahora + reconectar', () => {
  for (const p of ['polar', 'wahoo', 'strava']) {
    const m = model(p, { connected: true });
    assert.strictEqual(m.showSync, true, p);
    assert.strictEqual(m.showReconnect, true, p);
  }
});
test('no conectado: sin botones ni ultima sync', () => {
  const m = model('polar', { connected: false, lastSync: '' });
  assert.strictEqual(m.showSync, false);
  assert.strictEqual(m.showReconnect, false);
  assert.ok(!html('polar', m, 'x').includes('Última sincronización'));
});
test('conectado sin sync registrada -> "sin sincronizaciones aun", jamas una fecha', () => {
  const h = html('polar', model('polar', { connected: true, lastSync: '' }), 'Conectado');
  assert.ok(h.includes('sin sincronizaciones aún'));
  assert.ok(!/\d{4}/.test(h.replace(/data-conn[^>]*>/, '')));
});
test('conectado con campo no expuesto (null) -> la fila no aparece', () => {
  const h = html('strava', model('strava', { connected: true }), 'Conectado');
  assert.ok(!h.includes('Última sincronización'));
  assert.ok(!h.includes('sin sincronizaciones'));
});
test('fecha invalida -> sin fecha inventada', () => {
  assert.strictEqual(fmt('basura'), null);
  assert.strictEqual(fmt(''), null);
  assert.strictEqual(fmt(null), null);
  assert.ok(fmt('2026-11-06 12:30'));
});
test('ultima sync con error se rotula', () => {
  const h = html('wahoo', model('wahoo', { connected: true, lastSync: '2026-11-06T12:30:00', lastStatus: 'error' }), 'c');
  assert.ok(h.includes('con error'));
});
test('cada tarjeta tiene su contenedor y el HTML no toca indoor', () => {
  for (const id of ['garmin-details', 'strava-details']) assert.ok(web.includes('id="' + id + '"'), id);
  assert.ok(web.includes('connDetailsHtml(\n                p,'));
  const indoor = fs.readFileSync(path.join(__dirname, '..', '..', 'indoor_workout.html'), 'utf8');
  assert.ok(!indoor.includes('connDetailsHtml'));
});
