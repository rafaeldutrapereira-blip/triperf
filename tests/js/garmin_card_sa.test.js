// S-A: tarjeta unica Garmin (web y app) -- modelo de estados y visibilidad por rol
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
const web = fs.readFileSync(path.join(root, 'athlete_profile.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'athlete-app.html'), 'utf8');

for (const [label, src] of [['web', web], ['app', app]]) {
  const model = new Function(extract(src, 'garminCardModel') + '; return garminCardModel;')();
  test(label + ': sin conexion ofrece solo el flujo oficial', () => {
    const m = model(false, 'not_connected', false);
    assert.strictEqual(m.via, 'none');
    assert.strictEqual(m.showConnect, true);
    assert.strictEqual(m.adminConnectLegacy, undefined); // RETIRO-1: la accion ya no existe
    assert.strictEqual(m.showSwitch, false);
  });
  test(label + ': oficial no disponible no ofrece boton', () => {
    for (const st of ['unavailable', 'error']) {
      const m = model(false, st, false);
      assert.strictEqual(m.showConnect, false);
      assert.strictEqual(m.connected, false);
    }
  });
  test(label + ': legacy conectado (atleta) -> sync, desconectar y cambiar a oficial', () => {
    const m = model(true, 'not_connected', false);
    assert.strictEqual(m.via, 'legacy');
    assert.strictEqual(m.connected, true);
    assert.strictEqual(m.showSync, true);
    assert.strictEqual(m.disconnect, 'legacy');
    assert.strictEqual(m.showSwitch, true);
    assert.strictEqual(m.showConnect, false);
    assert.strictEqual(m.adminConnectLegacy, undefined);
    assert.strictEqual(model(true, 'unavailable', false).showSwitch, false);
  });
  test(label + ': oficial conectado manda sobre legacy', () => {
    const m = model(true, 'connected', false);
    assert.strictEqual(m.via, 'official');
    assert.strictEqual(m.disconnect, 'official');
    assert.strictEqual(m.showSync, false);
    assert.strictEqual(m.showSwitch, false);
    assert.strictEqual(m.adminDisconnectLegacy, false, 'atleta: legacy no se muestra');
  });
  test(label + ': solo admin ve la via legacy', () => {
    assert.strictEqual(model(false, 'not_connected', true).adminConnectLegacy, undefined);
    assert.strictEqual(model(true, 'connected', true).adminDisconnectLegacy, true);
    assert.strictEqual(model(true, 'connected', false).adminDisconnectLegacy, false);
  });
  test(label + ': garminIsAdmin lee api_rol de kl_s', () => {
    const mk = (v) =>
      new Function('S', extract(src, 'garminIsAdmin') + '; return garminIsAdmin;')(
        { getItem: () => v },
      );
    const run = (v) => {
      const S = { getItem: () => v };
      return new Function('sessionStorage', 'localStorage', extract(src, 'garminIsAdmin') + '; return garminIsAdmin();')(S, S);
    };
    void mk;
    assert.strictEqual(run(JSON.stringify({ api_rol: 'admin' })), true);
    assert.strictEqual(run(JSON.stringify({ api_rol: 'atleta' })), false);
    assert.strictEqual(run(JSON.stringify({ api_rol: 'coach' })), false);
    assert.strictEqual(run(null), false);
    assert.strictEqual(run('{no json'), false);
  });
}

test('web: RETIRO-1 sin formulario ni boton de conexion por credenciales', () => {
  for (const id of ['g-email', 'g-pass', 'garmin-form', 'btn-garmin-con']) {
    assert.strictEqual(web.indexOf('id="' + id + '"'), -1, id + ' ya no debe existir');
  }
});

test('app: fila unica, sin "(oficial)" y con enlace de cambio', () => {
  const code = 'var _t=function(k,f){return f;};var _escCm=function(x){return x;};' +
    extract(app, 'garminCardModel') + extract(app, '_garminRow') + '; return _garminRow;';
  const row = new Function(code)();
  const none = row(null, false, 'not_connected', false);
  assert.match(none, /garminOfficialConnect/);
  assert.doesNotMatch(none, /\(oficial\)/i);
  const legacy = row({ last_sync: 'x', activities_total: 3 }, true, 'not_connected', false);
  assert.match(legacy, /refreshGarminSync/);
  assert.match(legacy, /pf-garmin-switch/);
  const both = row({}, true, 'connected', false);
  assert.match(both, /garminOfficialDisconnect/);
  assert.doesNotMatch(both, /refreshGarminSync/);
  assert.doesNotMatch(row({}, true, 'connected', false), /pf-garmin-admin/);
  assert.match(row({}, true, 'connected', true), /pf-garmin-admin/);
});
