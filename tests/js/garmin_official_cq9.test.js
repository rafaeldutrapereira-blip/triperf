// CQ9: estados honestos de la conexion oficial Garmin (web y app)
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function extract(src, name) {
  const i = src.indexOf('function ' + name + '(');
  assert.ok(i >= 0, name + ' no existe');
  const j = src.indexOf('{', i);
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
  const state = new Function(extract(src, 'garminOfficialState') + '; return garminOfficialState;')();
  test(label + ': los 3 estados + error', () => {
    assert.strictEqual(state(true, 200, { available: true, connected: true }), 'connected');
    assert.strictEqual(state(true, 200, { available: true, connected: false }), 'not_connected');
    assert.strictEqual(state(true, 200, { available: false, connected: false }), 'unavailable');
    assert.strictEqual(state(false, 0, null), 'error');
  });
  test(label + ': 503 jamas es conectado', () => {
    assert.strictEqual(state(false, 503, null), 'unavailable');
    assert.strictEqual(state(true, 503, { connected: true }), 'unavailable');
    assert.notStrictEqual(state(false, 500, null), 'connected');
    assert.strictEqual(state(true, 200, {}), 'not_connected');
  });
}

test('app: fila oficial pinta cada estado y el boton correcto', () => {
  const code = 'var _t=function(k,f){return f;};' + extract(app, '_garminOfficialRow') + '; return _garminOfficialRow;';
  const row = new Function(code)();
  const on = row('connected');
  assert.match(on, /garminOfficialDisconnect/);
  assert.match(on, /pf-conn-dot on/);
  const off = row('not_connected');
  assert.match(off, /garminOfficialConnect/);
  assert.match(off, /pf-conn-dot off/);
  for (const st of ['unavailable', 'error']) {
    const h = row(st);
    assert.doesNotMatch(h, /<button/);
    assert.doesNotMatch(h, /pf-conn-dot on/);
  }
  assert.match(row('unavailable'), /Pronto/);
});

test('web: setGarminOfficialUI solo muestra Conectar si not_connected', () => {
  const els = {};
  const doc = {
    getElementById: (id) => (els[id] = els[id] || { style: {}, textContent: '', setAttribute() {} }),
  };
  const fn = new Function('document', '_t',
    extract(web, 'setGarminOfficialUI') + '; return setGarminOfficialUI;')(doc, (k, f) => f);
  fn('unavailable');
  assert.strictEqual(els['btn-garmin-off-con'].style.display, 'none');
  assert.strictEqual(els['btn-garmin-off-dis'].style.display, 'none');
  assert.match(els['garmin-off-status'].textContent, /Pronto/);
  fn('connected');
  assert.strictEqual(els['btn-garmin-off-dis'].style.display, '');
  assert.strictEqual(els['btn-garmin-off-con'].style.display, 'none');
  fn('not_connected');
  assert.strictEqual(els['btn-garmin-off-con'].style.display, '');
});
