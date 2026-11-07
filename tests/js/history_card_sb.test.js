// S-B: paso "Trae tu historial" en Conexiones -- modelo de visibilidad y estado
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
const model = new Function(extract(web, 'histCardModel') + '; return histCardModel;')();
const IV_ON = { connected: true, read_enabled: true, available: true, needs_reconnect: false };
const IV_OFF = { connected: false, read_enabled: true, available: true };

test('sin ninguna conexion no se muestra', () => {
  assert.strictEqual(model({ intervals: IV_OFF, strava: { connected: false }, state: {} }).visible, false);
});
test('solo Garmin conectado: intervals aparece como "conectar", no como importador', () => {
  const m = model({ garminOn: true, intervals: IV_OFF, strava: { connected: false }, state: {} });
  assert.strictEqual(m.visible, true);
  assert.strictEqual(m.intervals, 'connect');
  assert.strictEqual(m.strava, 'hidden');
});
test('intervals conectado con lectura -> importar; sin permiso -> reconectar', () => {
  assert.strictEqual(model({ intervals: IV_ON, strava: {}, state: {} }).intervals, 'import');
  assert.strictEqual(model({ intervals: { ...IV_ON, needs_reconnect: true }, strava: {}, state: {} }).intervals, 'reconnect');
});
test('flag de lectura apagado: nunca se promete el importador', () => {
  const m = model({ garminOn: true, intervals: { connected: true, read_enabled: false, available: true }, strava: {}, state: {} });
  assert.strictEqual(m.intervals, 'hidden');
  assert.strictEqual(m.visible, false);
  const m2 = model({ garminOn: true, intervals: { connected: false, read_enabled: false, available: true }, strava: {}, state: {} });
  assert.strictEqual(m2.intervals, 'hidden');
});
test('Strava conectado ofrece su importador', () => {
  const m = model({ intervals: IV_OFF, strava: { connected: true, available: true }, state: {} });
  assert.strictEqual(m.strava, 'import');
  assert.strictEqual(m.visible, true);
  assert.strictEqual(model({ intervals: IV_OFF, strava: { connected: true, available: false }, state: {} }).strava, 'hidden');
});
test('descartada o ya importada: oculta', () => {
  const base = { intervals: IV_ON, strava: { connected: true, available: true } };
  assert.strictEqual(model({ ...base, state: { dismissed: true } }).visible, false);
  assert.strictEqual(model({ ...base, state: { done: true } }).visible, false);
});
test('estado por usuario en localStorage', () => {
  const store = {};
  const ls = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => (store[k] = v) };
  const code = 'var _profile={id:"u7"};' + extract(web, 'histKey') + extract(web, 'histState') + extract(web, 'histSave') +
    'histSave({dismissed:true}); return [histKey(), histState()];';
  const [key, st] = new Function('localStorage', code)(ls);
  assert.strictEqual(key, 'lx_history_step:u7');
  assert.deepStrictEqual(st, { dismissed: true });
});
test('el backfill se llama sin tocar el servicio y Strava con el tope de 90 dias', () => {
  assert.match(web, /\/integrations\/intervals\/backfill/);
  assert.match(web, /\/strava\/sync\?days=90/);
});
