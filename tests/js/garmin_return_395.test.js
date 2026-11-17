// GARMIN-OAUTH-RETURN (395): ?garmin=connected se reconoce, avisa y dispara el sync
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
const sw = fs.readFileSync(path.join(root, 'sw.js'), 'utf8');

function harness(search, inFrame) {
  const log = { toasts: [], syncs: 0, nav: [], screens: [], replaced: [] };
  const code =
    'var _garminReturn = null;' +
    extract(app, 'garminReturnAction') +
    extract(app, 'garminReturnRead') +
    extract(app, 'garminReturnConsume') +
    '; return {read: garminReturnRead, consume: garminReturnConsume, get: function(){return _garminReturn;}};';
  const win = { location: { search, pathname: '/athlete-app.html', hash: '' } };
  win.top = inFrame ? {} : win;
  const api = new Function(
    'window', 'history', 'URLSearchParams', '_t', 'toast', 'garminOfficialSync', '_lxTopNav', 'goScreen', 'setTimeout',
    code,
  )(
    win,
    { replaceState: (a, b, u) => log.replaced.push(u) },
    URLSearchParams,
    (k, fb) => fb,
    (m, c) => log.toasts.push([m, c]),
    () => { log.syncs++; return Promise.resolve(); },
    (u) => log.nav.push(u),
    (s) => log.screens.push(s),
    (fn) => { fn(); return 0; },
  );
  return { api, log };
}

test('?garmin=connected se reconoce, avisa y dispara el sync (dentro de la shell, vuelve al dashboard)', async () => {
  const { api, log } = harness('?garmin=connected', true);
  api.read();
  assert.strictEqual(api.get(), 'connected');
  assert.deepStrictEqual(log.replaced, ['/athlete-app.html']); // limpia el parametro
  assert.strictEqual(api.consume(), true);
  assert.strictEqual(log.toasts[0][1], 'ok');
  await new Promise((r) => setImmediate(r));
  assert.strictEqual(log.syncs, 1);
  assert.deepStrictEqual(log.nav, ['dashboard.html']);
});

test('?garmin=connected fuera de la shell: sync y pantalla Hoy', () => {
  const { api, log } = harness('?garmin=connected', false);
  api.read();
  api.consume();
  assert.strictEqual(log.syncs, 1);
  assert.deepStrictEqual(log.screens, ['screen-today']);
});

test('denied/error: aviso de error, a Perfil y SIN sync', () => {
  for (const v of ['denied', 'error', 'error_state']) {
    const { api, log } = harness('?garmin=' + v, false);
    api.read();
    api.consume();
    assert.strictEqual(log.syncs, 0, v);
    assert.strictEqual(log.toasts[0][1], 'err', v);
    assert.deepStrictEqual(log.screens, ['screen-profile'], v);
  }
});

test('garminOfficialSync devuelve la promesa (el retorno espera el sync antes de navegar)', () => {
  const body = extract(app, 'garminOfficialSync');
  assert.ok(/return Promise\.resolve\(\)/.test(body) && /return apiFetch\(/.test(body));
});

test('Polar/Wahoo siguen en WEARABLE_OAUTH y garmin no (tarjeta unica)', () => {
  const m = app.match(/var WEARABLE_OAUTH = \[([^\]]*)\]/);
  assert.ok(m && m[1].includes('polar') && m[1].includes('wahoo') && !m[1].includes('garmin'));
});

test('BUILD 395 y sello i18n.js?v=397', () => {
  assert.match(sw, /var BUILD_VERSION = '397'/);
  assert.ok(sw.includes("'/i18n.js?v=397'"));
  assert.ok(app.includes('i18n.js?v=397'));
});
