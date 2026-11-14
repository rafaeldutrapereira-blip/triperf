// SYNC-CONEXIONES (379): retorno OAuth de Garmin, mensajes del sync y vigilancia del push
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
const root = path.join(__dirname, '..', '..');
const app = fs.readFileSync(path.join(root, 'athlete-app.html'), 'utf8');
const web = fs.readFileSync(path.join(root, 'athlete_profile.html'), 'utf8');
const _t = (k, fb) => fb;

for (const [label, src] of [['app', app], ['web', web]]) {
  const msg = new Function('_t', extract(src, 'garminSyncMessage') + '; return garminSyncMessage;')(_t);
  const view = new Function('_t', extract(src, 'garminPushView') + '; return garminPushView;')(_t);

  test(label + ': sync ok informa cuantas actividades y no promete salud', () => {
    const m = msg(true, { status: 'ok', saved: 3 });
    assert.strictEqual(m.ok, true);
    assert.ok(m.text.includes('3'));
    assert.ok(!/salud|health/i.test(m.text));
  });
  test(label + ': cada fallo es un mensaje de error, nunca exito silencioso', () => {
    for (const st of ['needs_reconnect', 'not_connected', 'unavailable', 'pull_failed', 'otro']) {
      const m = msg(false, { status: st });
      assert.strictEqual(m.ok, false, st);
      assert.ok(m.text.length > 5, st);
    }
    assert.strictEqual(msg(false, null).ok, false);
    assert.strictEqual(msg(true, { status: 'syncing' }).ok, true); // via anterior
  });
  test(label + ': push vivo muestra ultimo envio sin advertencia', () => {
    const v = view({ reference_at: '2026-11-14T10:00:00', stale: false, last_gap: null }, (x) => x);
    assert.ok(v.line.includes('2026-11-14T10:00:00'));
    assert.strictEqual(v.warn, false);
    assert.strictEqual(v.msg, '');
  });
  test(label + ': push muerto >48 h advierte con la fecha', () => {
    const v = view({ reference_at: '2026-11-10T12:00:00', stale: true }, (x) => x);
    assert.strictEqual(v.warn, true);
    assert.ok(v.msg.includes('2026-11-10T12:00:00'));
  });
  test(label + ': push sin ningun envio es advertencia, no "conectado sin mas"', () => {
    const v = view({ reference_at: null, stale: true }, (x) => x);
    assert.strictEqual(v.warn, true);
    assert.ok(v.line.length > 0 && v.msg.length > 0);
  });
  test(label + ': hueco historico se muestra aunque el push haya revivido', () => {
    const v = view(
      { reference_at: '2026-11-14T10:00:00', stale: false, last_gap: { from: '2026-11-11', to: '2026-11-13' } },
      (x) => x,
    );
    assert.ok(v.gap.includes('2026-11-11') && v.gap.includes('2026-11-13'));
  });
  test(label + ': sin respuesta del servidor no se afirma nada', () => {
    assert.strictEqual(view(null), null);
  });
}

test('app: retorno ?garmin= -> accion por valor', () => {
  const act = new Function(extract(app, 'garminReturnAction') + '; return garminReturnAction;')();
  assert.deepStrictEqual(
    [act('connected', false).nav, act('connected', true).nav],
    ['today', 'top-dashboard'],
  );
  assert.strictEqual(act('connected', true).ok, true);
  for (const v of ['denied', 'error', 'error_state']) {
    const a = act(v, false);
    assert.strictEqual(a.ok, false, v);
    assert.strictEqual(a.nav, 'profile', v);
  }
  assert.strictEqual(act('x', false), null);
  assert.strictEqual(act(null, false), null);
});

test('app: la lista de tarjetas wearable NO incluye garmin (sin tarjeta duplicada)', () => {
  const m = app.match(/var WEARABLE_OAUTH = \[([^\]]*)\]/);
  assert.ok(m && !m[1].includes('garmin'));
});

test('modelo de tarjeta: sync oficial solo con conexion oficial', () => {
  for (const src of [app, web]) {
    const model = new Function(extract(src, 'garminCardModel') + '; return garminCardModel;')();
    assert.strictEqual(model(false, 'connected', false).showOfficialSync, true);
    assert.strictEqual(model(true, 'not_connected', false).showOfficialSync, false);
    assert.strictEqual(model(false, 'not_connected', false).showOfficialSync, false);
  }
});
