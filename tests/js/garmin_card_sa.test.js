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
  test(label + ': matriz completa de estados -> acciones (GARMIN-CONECTA)', () => {
    const states = ['connected', 'not_connected', 'unavailable', 'error', '', null];
    for (const st of states) {
      for (const legacy of [false, true]) {
        for (const sync of [undefined, 'live', 'stale', 'needs_reauth', 'never']) {
          const m = model(legacy, st, false, sync);
          const off = st === 'connected';
          // sin conexion oficial ni legacy: SIEMPRE se ofrece conectar
          if (!off && !legacy) {
            assert.strictEqual(m.showConnect, true, 'sin accion en ' + st);
            assert.strictEqual(m.connected, false);
            assert.strictEqual(m.disconnect, null);
          } else assert.strictEqual(m.showConnect, false);
          // ningun estado deja la tarjeta sin accion
          assert.ok(
            m.showConnect || m.showSync || m.showSwitch || m.disconnect,
            'tarjeta muda en ' + st + '/' + legacy + '/' + sync,
          );
          // legacy caida conserva su salida (sync + desconectar / pasarse a oficial)
          if (!off && legacy && (sync === 'needs_reauth' || sync === 'never')) {
            assert.strictEqual(m.status, 'legacy_down');
            assert.strictEqual(m.connected, false);
            assert.strictEqual(m.showSync, true);
            assert.strictEqual(m.showSwitch, st === 'not_connected');
          }
        }
      }
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

test('app: la fila muestra Conectar en error/unavailable', () => {
  const code = 'var _t=function(k,f){return f;};var _escCm=function(x){return x;};' +
    extract(app, 'garminCardModel') + extract(app, '_garminRow') + '; return _garminRow;';
  const row = new Function(code)();
  for (const st of ['error', 'unavailable', 'not_connected']) {
    assert.match(row(null, false, st, false), /garminOfficialConnect\(\)">Conectar Garmin/, st);
  }
  assert.doesNotMatch(row(null, false, 'connected', false), /Conectar Garmin/);
  assert.match(row(null, false, 'error', false), /puedes conectar igual/);
});

// SHELL-CONECTA: la conexion navega la ventana superior (la shell monta la pagina en un marco)
function topHarness(src, fn, args, extraFns) {
  const top = { location: { href: '' } };
  const win = { top, location: { href: '' }, Capacitor: undefined, open: () => null };
  const code = extract(src, '_lxTopNav') + extract(src, fn) + '; ' + fn + '(' + args + ');';
  new Function('window', 'API', code)(win, 'https://x');
  return { top: top.location.href, self: win.location.href };
}

for (const [label, src] of [['web', web], ['app', app]]) {
  test(label + ': garminOfficialConnect navega window.top, no el marco', () => {
    const r = topHarness(src, 'garminOfficialConnect', '');
    assert.strictEqual(r.top, 'https://x/integrations/garmin/connect');
    assert.strictEqual(r.self, '');
  });
  test(label + ': wearableConnect (Polar/Wahoo) navega window.top', () => {
    for (const p of ['polar', 'wahoo']) {
      const r = topHarness(src, 'wearableConnect', "'" + p + "'");
      assert.strictEqual(r.top, 'https://x/integrations/' + p + '/connect');
      assert.strictEqual(r.self, '');
    }
  });
  test(label + ': _lxTopNav cae a la ventana propia si window.top no es accesible', () => {
    const win = { location: { href: '' } };
    Object.defineProperty(win, 'top', { get() { throw new Error('SecurityError'); } });
    new Function('window', extract(src, '_lxTopNav') + "; _lxTopNav('https://y/z');")(win);
    assert.strictEqual(win.location.href, 'https://y/z');
  });
}

test('web: Strava, intervals y checkout salen por la ventana superior', () => {
  assert.doesNotMatch(web, /window\.location\.href\s*=\s*API \+ '\/strava\/connect'/);
  assert.match(web, /_lxTopNav\(API \+ '\/strava\/connect'\)/);
  assert.match(web, /lnk\.target = '_top'/);
  assert.match(web, /_lxTopNav\(d\.checkout_url\)/);
});

test('indoor/dashboard/lx-upgrade: OAuth intervals y checkout usan window.top', () => {
  const rd = (f) => fs.readFileSync(path.join(root, f), 'utf8');
  assert.match(rd('indoor_workout.html'), /\(window\.top \|\| window\)\.location\.href = url/);
  assert.match(rd('dashboard.html'), /\(window\.top \|\| window\)\.location\.href = d\.checkout_url/);
  assert.match(rd('lx-upgrade.js'), /\(window\.top \|\| window\)\.location\.href = d\.checkout_url/);
});

test('app: garminOfficialConnect abre fuera del WebView (Browser, _system, fallback a window.top)', () => {
  const run = (cap, openRet) => {
    const calls = { browser: null, open: null };
    const top = { location: { href: '' } };
    const win = { top, Capacitor: cap, location: { href: '' }, open: (u, t) => ((calls.open = [u, t]), openRet) };
    if (cap && cap.Plugins && cap.Plugins.Browser)
      cap.Plugins.Browser.open = (o) => (calls.browser = o.url);
    new Function('window', 'API', extract(app, '_lxTopNav') + extract(app, 'garminOfficialConnect') + '; garminOfficialConnect();')(win, 'https://x');
    return { calls, href: top.location.href };
  };
  const native = () => ({ isNativePlatform: () => true, Plugins: { Browser: {} } });
  let r = run(native(), null);
  assert.strictEqual(r.calls.browser, 'https://x/integrations/garmin/connect');
  assert.strictEqual(r.href, '');
  const noPlugin = { isNativePlatform: () => true, Plugins: {} };
  r = run(noPlugin, {});
  assert.deepStrictEqual(r.calls.open, ['https://x/integrations/garmin/connect', '_system']);
  assert.strictEqual(r.href, '');
  r = run(noPlugin, null);
  assert.strictEqual(r.href, 'https://x/integrations/garmin/connect');
  r = run(undefined, null);
  assert.strictEqual(r.href, 'https://x/integrations/garmin/connect');
  assert.strictEqual(r.calls.open, null);
});
