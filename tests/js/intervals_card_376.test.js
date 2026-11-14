// FUENTE-UNICA (376): modelo de la tarjeta de intervals.icu y Strava solo salida
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
const card = new Function(extract(web, 'intervalsCardModel') + '; return intervalsCardModel;')();
const hist = new Function(extract(web, 'histCardModel') + '; return histCardModel;')();

test('sin token: No conectado + boton Conectar, nada mas', () => {
  const m = card({ available: true, state: 'not_connected', connected: false });
  assert.strictEqual(m.badgeOn, false);
  assert.strictEqual(m.showConnect, true);
  assert.strictEqual(m.showDisconnect, false);
  assert.strictEqual(m.showReconnect, false);
  assert.strictEqual(m.athlete, '');
  assert.strictEqual(m.lastSync, '');
});

test('con token: atleta, ultima sync real y Reconectar/Desconectar', () => {
  const m = card({ available: true, state: 'connected', connected: true, athlete_id: 'i794934',
    last_sync: '2026-11-11T10:00:00', read_enabled: true });
  assert.strictEqual(m.badgeOn, true);
  assert.strictEqual(m.athlete, 'i794934');
  assert.strictEqual(m.lastSync, '2026-11-11T10:00:00');
  assert.strictEqual(m.showSync, true);
  assert.strictEqual(m.showReconnect && m.showDisconnect, true);
  assert.strictEqual(m.showConnect, false);
});

test('sin flag de lectura no se ofrece Sincronizar', () => {
  const m = card({ available: true, state: 'connected', connected: true, read_enabled: false });
  assert.strictEqual(m.showSync, false);
});

test('conexion invalida (401/403): NO figura como conectada, pide reconectar', () => {
  const m = card({ available: true, state: 'invalid', connected: false, has_token: true, athlete_id: 'i786864' });
  assert.strictEqual(m.badgeOn, false);
  assert.strictEqual(m.connected, false);
  assert.strictEqual(m.showSync, false);
  assert.strictEqual(m.showReconnect, true);
  assert.strictEqual(m.showDisconnect, true); // permite limpiar el token obsoleto
  assert.strictEqual(m.athlete, 'i786864');
});

test('servidor sin `state`: se deduce del status clasico', () => {
  assert.strictEqual(card({ connected: true, needs_reconnect: true }).state, 'needs_reconnect');
  assert.strictEqual(card({ connected: false }).state, 'not_connected');
});

test('no inventa ultima sync', () => {
  assert.strictEqual(card({ state: 'connected', connected: true }).lastSync, '');
});

test('Strava ya no tiene tarjeta ni modelo en Conexiones (STRAVA-FUERA 381)', () => {
  assert.ok(!/connStravaModel|id="strava-/.test(web));
});

test('historial: Strava no se ofrece nunca', () => {
  const base = { intervals: { connected: false }, state: {} };
  assert.strictEqual(hist({ ...base, strava: { connected: true, ingest_enabled: true } }).strava, undefined);
});

test('la pagina deja el boton Reconectar apuntando al flujo OAuth del servidor', () => {
  assert.ok(web.includes("/integrations/intervals/reconnect?ret=profile"));
  assert.ok(web.includes("/integrations/intervals/connect?ret=profile"));
  assert.ok(web.includes("method: 'DELETE'") && web.includes('/integrations/intervals/disconnect'));
});
